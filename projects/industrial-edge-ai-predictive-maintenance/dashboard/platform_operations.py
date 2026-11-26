"""Local metrics, schema journal, reviewed retention and protected-backup job queue."""
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from typing import Literal
from fastapi import HTTPException, Request, Response
from pydantic import Field
from maintenance_requests import fresh_actor,require_role
from team_accounts import StrictModel,reauthenticate
import private_crypto

BOUNDARY=dict(scope='local-platform-operations',production_ready=False,hosting_deployed=False,
              high_availability=False,multi_tenant=False,off_machine_recovery_verified=False)
STARTED=time.monotonic();LOCK=threading.Lock();COUNTS={};LATENCY_SUM=0.;LATENCY_COUNT=0
BUCKETS={bound:0 for bound in (.01,.05,.1,.25,.5,1.,2.,5.,10.)}
TABLES=('operational_evidence','operational_assets','operational_rules','operational_cases','operational_evaluations','operational_orders',
        'operational_events','operational_notifications','operational_email_configuration','operational_models',
        'operational_model_events','operational_scores','approved_guidance_documents','approved_guidance_events',
        'account_mfa','account_mfa_recovery','account_mfa_denials','platform_retention_plans','platform_backup_jobs','platform_backup_policy','platform_worker_status')


class Plan(StrictModel):
    request_key:str=Field(strict=True,pattern=r'^[a-f0-9]{32}$')
    domain:Literal['read-notifications','baseline-scores']
    keep_days:int=Field(strict=True,ge=1,le=3650)


class Apply(StrictModel):
    expected_revision:int=Field(strict=True,ge=1)
    target_sha256:str=Field(strict=True,pattern=r'^[a-f0-9]{64}$')


class BackupJob(StrictModel):
    request_key:str=Field(strict=True,pattern=r'^[a-f0-9]{32}$')


class BackupPolicy(StrictModel):
    expected_revision:int=Field(strict=True,ge=0)
    enabled:bool=Field(strict=True)
    interval_hours:int=Field(strict=True,ge=1,le=168)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS platform_retention_plans(
        id TEXT PRIMARY KEY,creator_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,request_hash TEXT NOT NULL,
        domain TEXT NOT NULL,keep_days INTEGER NOT NULL,cutoff TEXT NOT NULL,targets TEXT NOT NULL,target_sha256 TEXT NOT NULL,
        state TEXT NOT NULL,revision INTEGER NOT NULL,reviewer_id INTEGER REFERENCES users(id),reason TEXT NOT NULL,
        created_at TEXT NOT NULL,applied_at TEXT,UNIQUE(creator_id,request_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS platform_backup_jobs(
        id TEXT PRIMARY KEY,creator_id INTEGER NOT NULL REFERENCES users(id),creator_revision INTEGER NOT NULL,request_key TEXT NOT NULL,
        state TEXT NOT NULL,created_at TEXT NOT NULL,finished_at TEXT,lease_until REAL,report TEXT,last_error TEXT,
        UNIQUE(creator_id,request_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS platform_backup_policy(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),enabled INTEGER NOT NULL,interval_hours INTEGER NOT NULL,
        revision INTEGER NOT NULL,issuer_id INTEGER NOT NULL REFERENCES users(id),issuer_revision INTEGER NOT NULL,
        last_queued REAL NOT NULL,reason TEXT NOT NULL)''')
    db.execute('CREATE TABLE IF NOT EXISTS platform_worker_status(singleton INTEGER PRIMARY KEY CHECK(singleton=1),last_pass REAL NOT NULL,worker_id TEXT NOT NULL,last_error TEXT)')
    db.execute('''CREATE TABLE IF NOT EXISTS platform_schema_journal(
        component TEXT PRIMARY KEY,version INTEGER NOT NULL,schema_sha256 TEXT NOT NULL,applied_at TEXT NOT NULL)''')
    fingerprint=digest([dict(name=name,sql=db.execute("SELECT sql FROM sqlite_master WHERE name=? AND type='table'",(name,)).fetchone()[0]) for name in TABLES])
    row=db.execute("SELECT * FROM platform_schema_journal WHERE component='local-operations'").fetchone()
    if row and (row['version']!=1 or row['schema_sha256']!=fingerprint):raise RuntimeError('Unsupported operational schema change; preserve the database and review the migration')
    if not row:db.execute("INSERT INTO platform_schema_journal VALUES('local-operations',1,?,?)",(fingerprint,now()))


def observe(path,status,seconds):
    global LATENCY_SUM,LATENCY_COUNT
    group='operational' if path.startswith('/api/operational/') else 'guidance' if path.startswith('/api/guidance/') else 'platform' if path.startswith('/api/platform/') else 'other'
    bucket=str(status//100)+'xx'
    with LOCK:
        COUNTS[group,bucket]=COUNTS.get((group,bucket),0)+1;LATENCY_SUM+=seconds;LATENCY_COUNT+=1
        for bound in BUCKETS:
            if seconds<=bound:BUCKETS[bound]+=1


def backup_ready():
    path=os.environ.get('EDGEOPS_PROTECTED_BACKUP_DIR','')
    folder=Path(path) if path else None
    return dict(private_key_ready=private_crypto.configured(),output_directory_ready=bool(folder and folder.is_dir() and not folder.is_symlink()),
                scheduler='Separate opt-in platform worker; no operating-system service installed',encrypted_payload_limit_mib=64)


def _eligible_targets(db,domain,cutoff):
    if domain=='read-notifications':
        rows=db.execute("SELECT * FROM operational_notifications WHERE created_at<? AND read_at IS NOT NULL AND email_state IN ('delivered','cancelled','local-only-fixture') ORDER BY id LIMIT 5001",(cutoff,)).fetchall()
        return [dict(key=dict(id=row['id']),sha256=digest(dict(row))) for row in rows]
    rows=db.execute('SELECT * FROM operational_scores WHERE received_at<? ORDER BY model_id,run_id,frame_index LIMIT 5001',(cutoff,)).fetchall()
    return [dict(key={name:row[name] for name in ('model_id','run_id','frame_index')},sha256=digest(dict(row))) for row in rows]


def install_routes(app,database,require_user,require_csrf,matches,audit):
    def reader(db,request):
        current=require_user(request);actor=fresh_actor(db,current);require_role(actor,('admin','auditor'));return actor

    @app.get('/api/platform/status')
    def status(request:Request,response:Response):
        response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=reader(db,request)
            tables={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in TABLES}
            deadline=time.monotonic()+1
            db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
            try:checks=db.execute('PRAGMA quick_check(1)').fetchall()
            except sqlite3.Error:raise HTTPException(503,'Operational database check timed out or failed') from None
            finally:db.set_progress_handler(None,0)
            if len(checks)!=1 or checks[0][0]!='ok':raise HTTPException(503,'Operational database check failed')
            with LOCK:traffic=[dict(group=group,status=code,count=count) for (group,code),count in COUNTS.items()];duration=dict(count=LATENCY_COUNT,total_seconds=LATENCY_SUM,buckets=[dict(upper_seconds=b,count=n) for b,n in BUCKETS.items()])
            from operational_notifications import config
            return dict(role=actor['role'],user_id=actor['id'],generated_at=now(),uptime_seconds=time.monotonic()-STARTED,
                database='available',schema=[dict(row) for row in db.execute('SELECT * FROM platform_schema_journal')],record_counts=tables,
                requests=traffic,request_duration=duration,email=config(db),backup=backup_ready(),
                worker=dict(db.execute('SELECT * FROM platform_worker_status WHERE singleton=1').fetchone() or dict(last_pass=None,last_error='worker-not-observed')),
                jobs=[{key:row[key] for key in ('id','creator_id','state','created_at','finished_at','report','last_error')} for row in db.execute('SELECT * FROM platform_backup_jobs ORDER BY created_at DESC LIMIT 50')],
                backup_policy=dict(db.execute('SELECT enabled,interval_hours,revision,last_queued FROM platform_backup_policy WHERE singleton=1').fetchone() or dict(enabled=0,interval_hours=24,revision=0,last_queued=0)),
                retention=[{key:row[key] for key in ('id','creator_id','domain','keep_days','cutoff','target_sha256','state','revision','created_at','applied_at')}|{'target_count':len(json.loads(row['targets']))} for row in db.execute('SELECT * FROM platform_retention_plans ORDER BY created_at DESC LIMIT 100')],**BOUNDARY)

    @app.get('/api/platform/metrics')
    def metrics(request:Request):
        with database() as db:
            db.execute('BEGIN');reader(db,request)
            lines=['# TYPE edgeops_workflow_records gauge']
            for name in TABLES:lines.append('edgeops_workflow_records{table="'+name+'"} '+str(db.execute('SELECT count(*) FROM '+name).fetchone()[0]))
        with LOCK:
            lines+=['# TYPE edgeops_http_requests_total counter']+['edgeops_http_requests_total{group="'+group+'",status="'+status+'"} '+str(count) for (group,status),count in sorted(COUNTS.items())]
            lines+=['# TYPE edgeops_http_duration_seconds histogram']+['edgeops_http_duration_seconds_bucket{le="'+str(bound)+'"} '+str(count) for bound,count in BUCKETS.items()]
            lines+=['edgeops_http_duration_seconds_bucket{le="+Inf"} '+str(LATENCY_COUNT),'edgeops_http_duration_seconds_count '+str(LATENCY_COUNT),'edgeops_http_duration_seconds_sum '+str(LATENCY_SUM)]
        return Response('\n'.join(lines)+'\n',media_type='text/plain; version=0.0.4',headers={'Cache-Control':'no-store'})

    @app.get('/api/platform/release.zip')
    def release_source(request:Request):
        with database() as db:
            db.execute('BEGIN');reader(db,request)
        import release_bundle
        try:
            raw,manifest=release_bundle.build(Path(__file__).resolve().parents[1]);release_bundle.verify(raw)
        except Exception:raise HTTPException(503,'Source release unavailable. Commit and review source changes before creating a release package.') from None
        return Response(raw,media_type='application/zip',headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="edgeops-source-'+manifest['source_commit'][:12]+'.zip"','X-Edgeops-Archive-SHA256':hashlib.sha256(raw).hexdigest()})

    @app.post('/api/platform/retention')
    def propose(body:Plan,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            request_hash=digest({key:value for key,value in body.model_dump().items() if key!='current_password'})
            old=db.execute('SELECT * FROM platform_retention_plans WHERE creator_id=? AND request_key=?',(actor['id'],body.request_key)).fetchone()
            if old:
                if old['request_hash']!=request_hash:raise HTTPException(409,'Retention request identity reused with changed content')
                return dict(id=old['id'],target_count=len(json.loads(old['targets'])),target_sha256=old['target_sha256'],state=old['state'],created=False,**BOUNDARY)
            if db.execute('SELECT count(*) FROM platform_retention_plans').fetchone()[0]>=100:raise HTTPException(429,'Retention plan history capacity reached')
            cutoff=(datetime.now(timezone.utc)-timedelta(days=body.keep_days)).isoformat(timespec='microseconds')
            targets=_eligible_targets(db,body.domain,cutoff)
            if len(targets)>5000:raise HTTPException(422,'Retention preview exceeds the bounded 5,000-record review; use a separately reviewed archive procedure')
            identity=secrets.token_hex(16)
            db.execute('INSERT INTO platform_retention_plans VALUES(?,?,?,?,?,?,?,?,?,\'planned\',1,NULL,?,?,NULL)',
                (identity,actor['id'],body.request_key,request_hash,body.domain,body.keep_days,cutoff,canonical(targets),digest(targets),body.reason,now()))
            audit(db,actor['email'],'retention_proposed',identity+' '+str(len(targets)))
            return dict(id=identity,target_count=len(targets),target_sha256=digest(targets),state='planned',created=True,**BOUNDARY)

    @app.post('/api/platform/retention/{identity}/apply')
    def apply(identity:str,body:Apply,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            plan=db.execute('SELECT * FROM platform_retention_plans WHERE id=?',(identity,)).fetchone()
            if not plan:raise HTTPException(404,'Retention plan unavailable')
            if actor['id']==plan['creator_id']:raise HTTPException(403,'Independent administrator required for deletion')
            if plan['target_sha256']!=body.target_sha256:raise HTTPException(409,'Retention preview hash changed')
            if plan['state']=='applied':return dict(id=identity,applied=True,already_applied=True,**BOUNDARY)
            if plan['state']!='planned' or plan['revision']!=body.expected_revision:raise HTTPException(409,'Retention plan changed')
            targets=json.loads(plan['targets'])
            if digest(targets)!=plan['target_sha256']:raise HTTPException(503,'Retention plan integrity check failed')
            table='operational_notifications' if plan['domain']=='read-notifications' else 'operational_scores'
            for target in targets:
                names=tuple(target['key']);where=' AND '.join(name+'=?' for name in names)
                allowed={'id'} if table=='operational_notifications' else {'model_id','run_id','frame_index'}
                if set(names)!=allowed:raise HTTPException(503,'Retention plan key mismatch')
                row=db.execute('SELECT * FROM '+table+' WHERE '+where,tuple(target['key'][name] for name in names)).fetchone()
                if not row or digest(dict(row))!=target['sha256']:raise HTTPException(409,'A previewed record changed; create a new reviewed plan')
            for target in targets:
                names=tuple(target['key']);db.execute('DELETE FROM '+table+' WHERE '+' AND '.join(name+'=?' for name in names),tuple(target['key'][name] for name in names))
            db.execute("UPDATE platform_retention_plans SET state='applied',revision=revision+1,reviewer_id=?,applied_at=? WHERE id=?",(actor['id'],now(),identity))
            audit(db,actor['email'],'retention_applied',identity+' '+str(len(targets))+' '+body.target_sha256)
            return dict(id=identity,applied=True,deleted_records=len(targets),backup_copies_deleted=False,**BOUNDARY)

    @app.post('/api/platform/backup-jobs')
    def queue(body:BackupJob,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            ready=backup_ready()
            if not ready['private_key_ready'] or not ready['output_directory_ready']:raise HTTPException(422,'Configure private encryption key and backup directory before queueing a job')
            old=db.execute('SELECT * FROM platform_backup_jobs WHERE creator_id=? AND request_key=?',(actor['id'],body.request_key)).fetchone()
            if old:return dict(id=old['id'],state=old['state'],created=False,**BOUNDARY)
            if db.execute('SELECT count(*) FROM platform_backup_jobs').fetchone()[0]>=100:raise HTTPException(429,'Backup job history capacity reached')
            identity=secrets.token_hex(16)
            import local_notifications
            db.execute('INSERT INTO platform_backup_jobs VALUES(?,?,?,?,\'pending\',?,NULL,NULL,NULL,NULL)',(identity,actor['id'],local_notifications.account_revision(db,actor['id']),body.request_key,now()))
            audit(db,actor['email'],'protected_backup_queued',identity);return dict(id=identity,state='pending',created=True,**BOUNDARY)

    @app.post('/api/platform/backup-policy')
    def schedule(body:BackupPolicy,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            row=db.execute('SELECT * FROM platform_backup_policy WHERE singleton=1').fetchone();revision=row['revision'] if row else 0
            if revision!=body.expected_revision:raise HTTPException(409,'Backup policy changed')
            ready=backup_ready()
            if body.enabled and (not ready['private_key_ready'] or not ready['output_directory_ready']):raise HTTPException(422,'Configure private backup storage before enabling a schedule')
            import local_notifications
            db.execute('INSERT INTO platform_backup_policy VALUES(1,?,?,?,?,?,0,?) ON CONFLICT(singleton) DO UPDATE SET enabled=excluded.enabled,interval_hours=excluded.interval_hours,revision=excluded.revision,issuer_id=excluded.issuer_id,issuer_revision=excluded.issuer_revision,reason=excluded.reason',
                (int(body.enabled),body.interval_hours,revision+1,actor['id'],local_notifications.account_revision(db,actor['id']),body.reason))
            audit(db,actor['email'],'backup_policy_saved',str(body.enabled));return dict(enabled=body.enabled,revision=revision+1,**BOUNDARY)

    @app.post('/api/platform/backup-jobs/{identity}/cancel')
    def cancel_job(identity:str,body:StrictModel,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            job=db.execute('SELECT * FROM platform_backup_jobs WHERE id=?',(identity,)).fetchone()
            if not job:raise HTTPException(404,'Backup job unavailable')
            if job['state']!='pending':raise HTTPException(409,'Only a pending job can be cancelled; a running operation is not force-stopped')
            db.execute("UPDATE platform_backup_jobs SET state='cancelled',finished_at=?,last_error='cancelled-by-administrator' WHERE id=?",(now(),identity))
            audit(db,actor['email'],'backup_job_cancelled',identity)
            return dict(id=identity,state='cancelled',**BOUNDARY)
