"""Bounded authenticated MQTT ingress reports; no hardware or broker attestation."""
from datetime import datetime, timezone
import json
import time
from typing import Literal

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from service_credentials import authenticate, status, require_service_transport
from maintenance_requests import fresh_actor, require_role, READ_ROLES

BOUNDARY={'scope':'local-synthetic-mqtt-ingress','production_ready':False,
          'hardware_connected':False,'broker_connection_verified_by_server':False}


class Report(BaseModel):
    model_config=ConfigDict(extra='forbid')
    run_id: str=Field(strict=True,pattern=r'^[0-9a-f]{32}$')
    sequence: int=Field(strict=True,ge=0,le=2147483647)
    state: Literal['connecting','connected','stopped']
    topic: str=Field(strict=True,min_length=1,max_length=256)
    client_id: str=Field(strict=True,pattern=r'^[A-Za-z0-9_-]{1,23}$')
    interval_seconds: int=Field(strict=True,ge=1,le=300)
    received: int=Field(strict=True,ge=0,le=2147483647)
    accepted_messages: int=Field(strict=True,ge=0,le=2147483647)
    ack_requests: int=Field(strict=True,ge=0,le=2147483647)
    refused: int=Field(strict=True,ge=0,le=2147483647)
    last_event_key: str|None=Field(default=None,pattern=r'^[0-9a-f]{64}$')
    last_error: Literal['none','invalid-message','out-of-scope','capacity-refused',
        'spool-unavailable','ack-unavailable','broker-unavailable','report-unavailable','identity-conflict']


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS service_mqtt_reports(
        credential_id TEXT PRIMARY KEY REFERENCES service_credentials(id),
        run_id TEXT NOT NULL, sequence INTEGER NOT NULL, state TEXT NOT NULL,
        report_json TEXT NOT NULL, received_at INTEGER NOT NULL, lease_until INTEGER NOT NULL)''')


def utc(value):return datetime.fromtimestamp(value,timezone.utc).isoformat()


def install_routes(app,database,require_user,audit):
    @app.post('/api/edge/mqtt-heartbeat')
    def report(body:Report,request:Request,response:Response):
        require_service_transport(request)
        if body.ack_requests>body.accepted_messages or body.accepted_messages+body.refused>body.received:
            raise HTTPException(422,'MQTT report counters are inconsistent')
        payload=json.dumps(body.model_dump(),sort_keys=True,separators=(',',':'))
        with database() as db:
            db.execute('BEGIN IMMEDIATE');credential=authenticate(db,request)
            expected='edgeops/synthetic/'+credential['site_id']+'/'+credential['asset_id']+'/'+credential['device_id']+'/telemetry'
            if body.topic!=expected:raise HTTPException(403,'MQTT topic outside credential scope')
            prior=db.execute('SELECT * FROM service_mqtt_reports WHERE credential_id=?',(credential['id'],)).fetchone()
            now=int(time.time())
            if prior:
                if prior['run_id']==body.run_id:
                    if prior['sequence']==body.sequence and prior['report_json']==payload:
                        response.headers['Cache-Control']='no-store'
                        return {**BOUNDARY,'run_id':body.run_id,'sequence':body.sequence,
                            'report_received_at':utc(prior['received_at']),'report_lease_until':utc(prior['lease_until'])}
                    if prior['state']=='stopped' or body.sequence<=prior['sequence']:
                        raise HTTPException(409,'MQTT report is stopped, stale or replayed')
                    previous=json.loads(prior['report_json'])
                    if any(getattr(body,key)<previous[key] for key in ('received','accepted_messages','ack_requests','refused')):
                        raise HTTPException(409,'MQTT report counters cannot move backwards')
                elif prior['state']!='stopped' and prior['lease_until']>now:
                    raise HTTPException(409,'Another MQTT bridge holds this credential report lease')
            if (not prior or prior['run_id']!=body.run_id) and (body.sequence!=0 or body.state!='connecting'):
                raise HTTPException(409,'A new MQTT bridge must start with connecting sequence zero')
            until=now if body.state=='stopped' else now+max(30,body.interval_seconds*3+15)
            db.execute('''INSERT INTO service_mqtt_reports VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(credential_id) DO UPDATE SET run_id=excluded.run_id,sequence=excluded.sequence,
                state=excluded.state,report_json=excluded.report_json,received_at=excluded.received_at,
                lease_until=excluded.lease_until''',(credential['id'],body.run_id,body.sequence,body.state,payload,now,until))
            if not prior or prior['run_id']!=body.run_id or body.state=='stopped':
                audit(db,'service:'+credential['id'],'mqtt_ingress_'+body.state,body.run_id)
        response.headers['Cache-Control']='no-store'
        return {**BOUNDARY,'run_id':body.run_id,'sequence':body.sequence,
                'report_received_at':utc(now),'report_lease_until':utc(until)}

    @app.get('/api/mqtt-ingress')
    def listing(request:Request,response:Response):
        current=require_user(request)
        with database() as db:
            db.execute('BEGIN');require_role(fresh_actor(db,current),READ_ROLES)
            rows=db.execute('''SELECT m.*,c.label,c.device_id FROM service_mqtt_reports m
                JOIN service_credentials c ON c.id=m.credential_id
                ORDER BY m.received_at DESC,m.credential_id LIMIT 100''').fetchall()
            now=int(time.time());reports=[]
            for row in rows:
                credential=db.execute('SELECT * FROM service_credentials WHERE id=?',(row['credential_id'],)).fetchone()
                active=status(db,credential)
                observed=('credential-inactive' if active!='active' else 'reported-stopped' if row['state']=='stopped'
                    else 'report-stale' if row['lease_until']<=now else 'recent-report')
                reports.append({**json.loads(row['report_json']),'credential_id':row['credential_id'],
                    'label':row['label'],'device_id':row['device_id'],'credential_status':active,
                    'observation':observed,'service_received_at':utc(row['received_at']),
                    'report_lease_until':utc(row['lease_until'])})
        response.headers['Cache-Control']='no-store'
        return {**BOUNDARY,'observed_at':utc(now),'reports':reports,
                'counter_source':'Bridge-declared counts; ACK requests are not central commits or broker-confirmed receipts'}
