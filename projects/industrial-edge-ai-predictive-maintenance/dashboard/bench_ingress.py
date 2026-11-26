"""Separate read-only bench ledger. USB provenance is declared, never attested."""
from datetime import datetime,timezone
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import secrets
import time
from typing import Literal

from fastapi import HTTPException,Query,Request,Response
from pydantic import BaseModel,ConfigDict,Field,field_validator
from maintenance_requests import READ_ROLES,fresh_actor,require_role
from team_accounts import StrictModel,reauthenticate
import local_notifications

spec=importlib.util.spec_from_file_location('edgeops_capture_contract',Path(__file__).resolve().parents[1]/'phase-01-hardware/scripts/capture_serial.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
BOUNDARY=dict(scope='unverified-bench-readings',production_ready=False,hardware_verified=False,
              calibration_verified=False,equipment_authorized=False,automatic_incidents=False)
MAX_RECORDS=100000


class Issue(StrictModel):
    label:str=Field(strict=True,min_length=3,max_length=80)
    device_id:str=Field(strict=True,pattern=r'^[A-Za-z0-9_-]{1,64}$')
    lifetime_minutes:int=Field(strict=True,ge=5,le=10080)


class Revoke(StrictModel):
    expected_revision:int=Field(strict=True,ge=1)


class Sample(BaseModel):
    model_config=ConfigDict(extra='forbid')
    run_id:str=Field(strict=True,pattern=r'^[a-f0-9]{32}$')
    frame_index:int=Field(strict=True,ge=0,le=1000000000)
    source_type:Literal['measured-unverified','software-fixture']
    gateway_received_at:str=Field(strict=True,max_length=40)
    frame:dict

    @field_validator('gateway_received_at')
    @classmethod
    def timestamp(cls,value):
        date=datetime.fromisoformat(value)
        if date.tzinfo is None or not 2000<=date.year<=2100:raise ValueError('Use a bounded timestamp with explicit timezone')
        return date.astimezone(timezone.utc).isoformat(timespec='microseconds')

    @field_validator('frame')
    @classmethod
    def contract(cls,value):
        # Reuse the firmware V1 contract, including exact booleans and finite numbers.
        capture.parse_record(json.dumps(value,allow_nan=False));return value


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS bench_credentials(
        id TEXT PRIMARY KEY,token_hash TEXT NOT NULL UNIQUE,label TEXT NOT NULL,device_id TEXT NOT NULL,
        issuer_id INTEGER NOT NULL REFERENCES users(id),issuer_revision INTEGER NOT NULL,
        created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,revoked_at INTEGER,revision INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS bench_runs(
        id TEXT PRIMARY KEY,credential_id TEXT NOT NULL REFERENCES bench_credentials(id),device_id TEXT NOT NULL,
        source_type TEXT NOT NULL,created_at TEXT NOT NULL,last_received_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS bench_samples(
        run_id TEXT NOT NULL REFERENCES bench_runs(id),frame_index INTEGER NOT NULL,
        content_hash TEXT NOT NULL,payload_json TEXT NOT NULL,received_at TEXT NOT NULL,
        PRIMARY KEY(run_id,frame_index))''')


def active(db,row):
    if row['revoked_at'] or row['expires_at']<=time.time():return False
    user=db.execute('SELECT * FROM users WHERE id=?',(row['issuer_id'],)).fetchone()
    return bool(user and user['role']=='admin' and not user['disabled'] and
                row['issuer_revision']==local_notifications.account_revision(db,user['id']))


def public(db,row):
    return {key:row[key] for key in ('id','label','device_id','created_at','expires_at','revoked_at','revision')}|{'active':active(db,row),'permission':'unverified-bench:ingest'}


def authorize(db,request):
    # HTTPS or actual loopback only. Proxy trust is configured by the hosting launcher.
    if request.url.scheme!='https' and (not request.client or request.client.host not in ('127.0.0.1','::1')):
        raise HTTPException(403,'Bench ingestion requires HTTPS')
    token=request.headers.get('authorization','')
    if not token.startswith('Bearer edgeops_bench_') or len(token)!=len('Bearer edgeops_bench_')+64:raise HTTPException(401,'Bench credential required')
    row=db.execute('SELECT * FROM bench_credentials WHERE token_hash=?',(digest(token[7:]),)).fetchone()
    if not row or not active(db,row):raise HTTPException(401,'Bench credential inactive')
    return row


def present(row):
    payload=json.loads(row['payload_json'])
    if digest(canonical(payload))!=row['content_hash']:raise HTTPException(503,'Bench reading integrity check failed')
    body=Sample.model_validate(payload);frame=body.frame
    values={
        'acceleration_x_mps2':frame['ax_mps2'] if frame['adxl345_valid'] else None,
        'acceleration_y_mps2':frame['ay_mps2'] if frame['adxl345_valid'] else None,
        'acceleration_z_mps2':frame['az_mps2'] if frame['adxl345_valid'] else None,
        'temperature_c':frame['temp_c'] if frame['ds18b20_valid'] else None,
        'bus_voltage_v':frame['bus_v'] if frame['ina219_valid'] else None,
        'current_a':frame['current_ma']/1000 if frame['ina219_valid'] else None}
    return {**payload,'content_hash':row['content_hash'],'server_received_at':row['received_at'],
            'values':values,'device_boot_id':None,'device_utc':None,'quality':'declared sensor flags; unverified calibration',**BOUNDARY}


def install_routes(app,database,require_user,require_csrf,matches,audit):
    @app.get('/api/bench/credentials')
    def credentials(request:Request,response:Response):
        current=require_user(request);response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,('admin',))
            return {**BOUNDARY,'credentials':[public(db,row) for row in db.execute('SELECT * FROM bench_credentials ORDER BY created_at DESC,id')]}

    @app.post('/api/bench/credentials')
    def issue(body:Issue,request:Request,response:Response):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            if db.execute('SELECT count(*) FROM bench_credentials').fetchone()[0]>=100:raise HTTPException(429,'Bench credential retention capacity reached')
            identifier=secrets.token_hex(16);token='edgeops_bench_'+secrets.token_hex(32);now=int(time.time())
            db.execute('INSERT INTO bench_credentials VALUES(?,?,?,?,?,?,?,?,NULL,1)',
                (identifier,digest(token),body.label,body.device_id,actor['id'],local_notifications.account_revision(db,actor['id']),now,now+body.lifetime_minutes*60))
            audit(db,actor['email'],'bench_credential_issued',identifier)
            result=public(db,db.execute('SELECT * FROM bench_credentials WHERE id=?',(identifier,)).fetchone())
        response.status_code=201;response.headers['Cache-Control']='no-store'
        return {**BOUNDARY,'credential':result,'token':token,'token_shown_once':True}

    @app.post('/api/bench/credentials/{identifier}/revoke')
    def revoke(identifier:str,body:Revoke,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            row=db.execute('SELECT * FROM bench_credentials WHERE id=?',(identifier,)).fetchone()
            if not row:raise HTTPException(404,'Bench credential not found')
            if row['revision']!=body.expected_revision:raise HTTPException(409,'Credential changed; refresh before revoking')
            if not row['revoked_at']:
                db.execute('UPDATE bench_credentials SET revoked_at=?,revision=revision+1 WHERE id=?',(int(time.time()),identifier))
                audit(db,actor['email'],'bench_credential_revoked',identifier)
            return {**BOUNDARY,'revoked':True}

    @app.post('/api/bench/readings')
    def ingest(body:Sample,request:Request,response:Response):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');credential=authorize(db,request)
            if body.frame['device_id']!=credential['device_id']:raise HTTPException(403,'Frame device does not match the scoped credential')
            run=db.execute('SELECT * FROM bench_runs WHERE id=?',(body.run_id,)).fetchone()
            if run and (run['credential_id']!=credential['id'] or run['source_type']!=body.source_type):raise HTTPException(409,'Run scope changed')
            payload=canonical(body.model_dump());content_hash=digest(payload)
            previous=db.execute('SELECT * FROM bench_samples WHERE run_id=? AND frame_index=?',(body.run_id,body.frame_index)).fetchone()
            if previous:
                present(previous)
                if not hmac.compare_digest(previous['content_hash'],content_hash):raise HTTPException(409,'Frame identity conflict; original preserved')
            else:
                if db.execute('SELECT count(*) FROM bench_samples').fetchone()[0]>=MAX_RECORDS:raise HTTPException(429,'Bench retention capacity reached; gateway must retain pending data')
                now=datetime.now(timezone.utc).isoformat(timespec='microseconds')
                if not run:
                    if db.execute('SELECT count(*) FROM bench_runs').fetchone()[0]>=1000:raise HTTPException(429,'Bench run capacity reached')
                    db.execute('INSERT INTO bench_runs VALUES(?,?,?,?,?,?)',(body.run_id,credential['id'],credential['device_id'],body.source_type,now,now))
                    audit(db,'bench:'+credential['id'],'bench_run_started',body.run_id)
                db.execute('INSERT INTO bench_samples VALUES(?,?,?,?,?)',(body.run_id,body.frame_index,content_hash,payload,now))
                db.execute('UPDATE bench_runs SET last_received_at=? WHERE id=?',(now,body.run_id))
            response.status_code=200 if previous else 201
            return {**BOUNDARY,'run_id':body.run_id,'frame_index':body.frame_index,'content_hash':content_hash,'stored':True}

    @app.get('/api/bench/readings')
    def readings(request:Request,response:Response,run_id:str=Query(default='',max_length=32,pattern=r'^[a-f0-9]*$'),limit:int=Query(default=20,ge=1,le=100)):
        current=require_user(request);response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            runs=[dict(row) for row in db.execute('SELECT * FROM bench_runs ORDER BY last_received_at DESC,id LIMIT 100')]
            selected=run_id or (runs[0]['id'] if runs else '')
            rows=db.execute('SELECT * FROM bench_samples WHERE run_id=? ORDER BY frame_index DESC LIMIT ?',(selected,limit)).fetchall()
            return {**BOUNDARY,'runs':runs,'run_id':selected,'items':[present(row) for row in rows],
                    'total_in_run':db.execute('SELECT count(*) FROM bench_samples WHERE run_id=?',(selected,)).fetchone()[0],
                    'record_limit':MAX_RECORDS,'generated_at':datetime.now(timezone.utc).isoformat(),
                    'provenance':'Gateway-declared USB readings, not authenticated sensor identity or fault validation'}
