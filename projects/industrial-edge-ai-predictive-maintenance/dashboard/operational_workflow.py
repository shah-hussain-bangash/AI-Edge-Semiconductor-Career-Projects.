"""Local observed-threshold reviews and work records, isolated from synthetic exercises.

No diagnosis, equipment commands, physical verification or external dispatch.
"""
from datetime import datetime, timezone
import hashlib
import json
import secrets
from typing import Literal

from fastapi import HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, Field
from maintenance_requests import fresh_actor, require_role, READ_ROLES, WRITE_ROLES
from team_accounts import StrictModel, reauthenticate
import local_notifications

BOUNDARY = dict(scope='local-observation-review', production_ready=False,
                equipment_authorized=False, physical_work_verified=False,
                model_inference=False, external_notifications_sent=False,
                tenant_isolation=False)
CHANNELS = {'temperature_c':('temp_c','ds18b20_valid',1),
            'current_a':('current_ma','ina219_valid',1000),
            'bus_voltage_v':('bus_v','ina219_valid',1),
            'acceleration_x_mps2':('ax_mps2','adxl345_valid',1),
            'acceleration_y_mps2':('ay_mps2','adxl345_valid',1),
            'acceleration_z_mps2':('az_mps2','adxl345_valid',1)}


class Asset(StrictModel):
    site_id: str = Field(strict=True, pattern=r'^[A-Za-z0-9_-]{1,64}$')
    asset_id: str = Field(strict=True, pattern=r'^[A-Za-z0-9_-]{1,64}$')
    device_id: str = Field(strict=True, pattern=r'^[A-Za-z0-9_-]{1,64}$')
    label: str = Field(strict=True, min_length=3, max_length=100)
    source_type: Literal['measured-unverified','software-fixture']


class Revision(StrictModel):
    expected_revision: int = Field(strict=True, ge=1)


class Rule(StrictModel):
    asset: str = Field(strict=True, pattern=r'^[a-f0-9]{32}$')
    expected_asset_revision: int = Field(strict=True, ge=1)
    channel: Literal['temperature_c','current_a','bus_voltage_v','acceleration_x_mps2','acceleration_y_mps2','acceleration_z_mps2']
    comparison: Literal['above','below']
    threshold: float = Field(strict=True, allow_inf_nan=False, ge=-1e12, le=1e12)
    window_frames: int = Field(strict=True, ge=1, le=10000)
    max_age_seconds: int = Field(strict=True, ge=1, le=3600)
    enabled: bool = Field(strict=True, default=False)


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_revision: int = Field(strict=True, ge=1)
    note: str = Field(strict=True, min_length=10, max_length=1500)
    action: Literal['acknowledge','resolve','submit','approve','reject','start','complete','verify']
    evidence_refs: str = Field(strict=True, default='', max_length=1500)


class Assignment(Revision):
    assignee_id: int = Field(strict=True, ge=1)


class WorkOrder(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_key: str = Field(strict=True, pattern=r'^[a-f0-9]{32}$')
    case_id: str = Field(strict=True, pattern=r'^[a-f0-9]{32}$')
    expected_case_revision: int = Field(strict=True, ge=1)
    title: str = Field(strict=True, min_length=5, max_length=120)
    procedure: str = Field(strict=True, min_length=20, max_length=2000)
    technician_id: int = Field(strict=True, ge=1)


def now(): return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def receipt_timing(reading,reference):
    """Display-only receipt timing, never acquisition freshness or cable status."""
    result=dict(state='no-readings' if reading is None else 'timing-unavailable',
        server_age_seconds=None,gateway_delay_seconds=None,display_window_seconds=15,
        acquisition_time_verified=False)
    if reading is None:return result
    try:
        server=datetime.fromisoformat(reading['server_received_at'])
        gateway=datetime.fromisoformat(reading['gateway_received_at'])
        current=datetime.fromisoformat(reference)
        if any(value.tzinfo is None for value in (server,gateway,current)):return result
        age=(current-server).total_seconds();delay=(server-gateway).total_seconds()
        result.update(server_age_seconds=round(age,3),gateway_delay_seconds=round(delay,3))
        result['state']='clock-difference' if age < -5 or delay < -5 else 'stale-receipt' if age>15 else 'delayed-receipt' if delay>15 else 'recent-receipt'
    except (KeyError,TypeError,ValueError):pass
    return result


def init_schema(db):
    schema='''CREATE TABLE IF NOT EXISTS operational_assets(
        id TEXT PRIMARY KEY,site_id TEXT NOT NULL,asset_id TEXT NOT NULL,label TEXT NOT NULL,
        device_id TEXT NOT NULL,source_type TEXT NOT NULL,revision INTEGER NOT NULL,retired INTEGER NOT NULL,
        issuer_id INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
        UNIQUE(device_id,source_type));
        CREATE TABLE IF NOT EXISTS operational_rules(
        id TEXT PRIMARY KEY,asset TEXT NOT NULL REFERENCES operational_assets(id),asset_revision INTEGER NOT NULL,
        channel TEXT NOT NULL,comparison TEXT NOT NULL,threshold REAL NOT NULL,window_frames INTEGER NOT NULL,
        max_age_seconds INTEGER NOT NULL,enabled INTEGER NOT NULL,revision INTEGER NOT NULL,
        issuer_id INTEGER NOT NULL REFERENCES users(id),issuer_revision INTEGER NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operational_cases(
        id TEXT PRIMARY KEY,rule_id TEXT NOT NULL REFERENCES operational_rules(id),asset TEXT NOT NULL REFERENCES operational_assets(id),
        run_id TEXT NOT NULL,bucket INTEGER NOT NULL,source_type TEXT NOT NULL,state TEXT NOT NULL,
        revision INTEGER NOT NULL,matched_records INTEGER NOT NULL,first_frame INTEGER NOT NULL,last_frame INTEGER NOT NULL,
        first_snapshot TEXT NOT NULL,last_snapshot TEXT NOT NULL,assignee_id INTEGER REFERENCES users(id),created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        UNIQUE(rule_id,run_id,bucket));
        CREATE TABLE IF NOT EXISTS operational_evaluations(
        rule_id TEXT NOT NULL,run_id TEXT NOT NULL,frame_index INTEGER NOT NULL,content_hash TEXT NOT NULL,
        decision TEXT NOT NULL,case_id TEXT,PRIMARY KEY(rule_id,run_id,frame_index));
        CREATE TABLE IF NOT EXISTS operational_orders(
        id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES operational_cases(id),creator_id INTEGER NOT NULL REFERENCES users(id),
        request_key TEXT NOT NULL,request_hash TEXT NOT NULL,case_revision INTEGER NOT NULL,case_snapshot TEXT NOT NULL,case_snapshot_sha256 TEXT NOT NULL,source_type TEXT NOT NULL,
        title TEXT NOT NULL,procedure TEXT NOT NULL,technician_id INTEGER NOT NULL REFERENCES users(id),
        state TEXT NOT NULL,revision INTEGER NOT NULL,approver_id INTEGER REFERENCES users(id),approver_revision INTEGER,
        executor_id INTEGER REFERENCES users(id),evidence_refs TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        UNIQUE(creator_id,request_key));
        CREATE TABLE IF NOT EXISTS operational_events(
        id INTEGER PRIMARY KEY,kind TEXT NOT NULL,record_id TEXT NOT NULL,revision INTEGER NOT NULL,
        actor_id INTEGER REFERENCES users(id),action TEXT NOT NULL,note TEXT NOT NULL,snapshot_json TEXT NOT NULL,time_utc TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS operational_cases_updated ON operational_cases(updated_at);
        CREATE INDEX IF NOT EXISTS operational_events_record ON operational_events(kind,record_id,id);
    '''
    for statement in schema.split(';'):
        if statement.strip():db.execute(statement)


def event(db,kind,row,actor,action,note,audit):
    if db.execute('SELECT count(*) FROM operational_events').fetchone()[0]>=50000:raise HTTPException(429,'Review history capacity reached; preserve records and reconcile retention')
    inserted=db.execute('INSERT INTO operational_events(kind,record_id,revision,actor_id,action,note,snapshot_json,time_utc) VALUES(?,?,?,?,?,?,?,?)',
               (kind,row['id'],row['revision'],actor['id'] if actor else None,action,note,canonical(dict(row)),now()))
    import operational_notifications
    operational_notifications.enqueue(db,inserted.lastrowid,kind,row,action)
    audit(db,actor['email'] if actor else 'observation-rule', 'operational_'+action,row['id'])


def eligible(db,identifier):
    row=db.execute('SELECT * FROM users WHERE id=? AND disabled=0',(identifier,)).fetchone()
    if not row or row['role'] not in WRITE_ROLES:raise HTTPException(422,'Choose an active local operator or administrator')
    return row


def present_order(row):
    value=dict(row)
    if hashlib.sha256(row['case_snapshot'].encode()).hexdigest()!=row['case_snapshot_sha256']:raise HTTPException(503,'Captured work context integrity check failed')
    value['case_snapshot']=json.loads(row['case_snapshot'])
    return value


def visible(db,table,identifier,actor):
    row=db.execute('SELECT * FROM '+table+' WHERE id=?',(identifier,)).fetchone()
    if not row:raise HTTPException(404,'Operational review record not found')
    allowed=actor['role'] in ('admin','auditor')
    if table=='operational_cases':allowed=allowed or row['assignee_id']==actor['id']
    else:allowed=allowed or actor['id'] in (row['creator_id'],row['technician_id'])
    if not allowed:raise HTTPException(404,'Operational review record not found')
    return row


def consume(db,body,content_hash,received_at,audit):
    """Runs only on a NEW bench insert, in the same write transaction. No retroactive replay."""
    policies=db.execute('''SELECT r.*,a.source_type,a.device_id,a.retired,a.revision current_asset_revision,
        u.disabled,u.role FROM operational_rules r JOIN operational_assets a ON a.id=r.asset
        JOIN users u ON u.id=r.issuer_id WHERE r.enabled=1 AND a.device_id=? AND a.source_type=?''',
        (body.frame['device_id'],body.source_type)).fetchall()
    for policy in policies:
        if (policy['retired'] or policy['asset_revision']!=policy['current_asset_revision'] or policy['disabled'] or policy['role']!='admin'
            or policy['issuer_revision']!=local_notifications.account_revision(db,policy['issuer_id'])):continue
        if db.execute('SELECT count(*) FROM operational_evaluations').fetchone()[0]>=50000:
            raise HTTPException(429,'Operational review capacity reached; retain gateway data until capacity is reconciled')
        frame=body.frame;raw,flag,divisor=CHANNELS[policy['channel']]
        value=frame[raw]/divisor if frame[flag] else None
        age=(datetime.fromisoformat(received_at)-datetime.fromisoformat(body.gateway_received_at)).total_seconds()
        decision='unavailable' if value is None else 'stale-or-future' if not -5<=age<=policy['max_age_seconds'] else 'within-threshold'
        matched=value is not None and decision=='within-threshold' and (value>policy['threshold'] if policy['comparison']=='above' else value<policy['threshold'])
        case_id=None
        if matched:
            bucket=body.frame_index//policy['window_frames']
            case=db.execute('SELECT * FROM operational_cases WHERE rule_id=? AND run_id=? AND bucket=?',(policy['id'],body.run_id,bucket)).fetchone()
            snapshot=canonical(dict(run_id=body.run_id,frame_index=body.frame_index,content_hash=content_hash,
                                    source_type=body.source_type,frame=frame,channel=policy['channel'],value=value,
                                    server_received_at=received_at,gateway_received_at=body.gateway_received_at,
                                    physical_verification=False,rule=dict(policy)))
            if not case:
                if db.execute('SELECT count(*) FROM operational_cases').fetchone()[0]>=2000:raise HTTPException(429,'Operational case capacity reached')
                case_id=secrets.token_hex(16)
                db.execute('INSERT INTO operational_cases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (case_id,policy['id'],policy['asset'],body.run_id,bucket,body.source_type,'open',1,1,body.frame_index,body.frame_index,snapshot,snapshot,None,received_at,received_at))
                case=db.execute('SELECT * FROM operational_cases WHERE id=?',(case_id,)).fetchone()
                event(db,'case',case,None,'threshold_observed','Observed threshold crossing requires human review; no fault diagnosis or equipment action.',audit)
            else:
                case_id=case['id']
                reopen=case['state']=='resolved' and body.frame_index>case['last_frame']
                # Network arrival order is not host frame order. Preserve the
                # extrema instead of replacing the newest capture with a retry
                # or delayed, lower-index frame from the same run/bucket.
                captures=[(case['first_frame'],case['first_snapshot']),(case['last_frame'],case['last_snapshot']),(body.frame_index,snapshot)]
                first=min(captures,key=lambda capture:capture[0]);last=max(captures,key=lambda capture:capture[0])
                db.execute('UPDATE operational_cases SET matched_records=matched_records+1,first_frame=?,first_snapshot=?,last_frame=?,last_snapshot=?,updated_at=? WHERE id=?',
                           (first[0],first[1],last[0],last[1],received_at,case_id))
                if reopen:
                    db.execute("UPDATE operational_cases SET state='open',revision=revision+1 WHERE id=?",(case_id,))
                    reopened=db.execute('SELECT * FROM operational_cases WHERE id=?',(case_id,)).fetchone()
                    event(db,'case',reopened,None,'threshold_reobserved',
                        'Newer matching host frame '+str(body.frame_index)+' arrived after recorded resolution. Review again; the earlier decision is retained and no physical recurrence is certified.',audit)
            decision='threshold-observed'
        db.execute('INSERT INTO operational_evaluations VALUES(?,?,?,?,?,?)',(policy['id'],body.run_id,body.frame_index,content_hash,decision,case_id))


def install_routes(app,database,require_user,require_csrf,matches,audit):
    def actor_for(db,request,write=False):
        current=require_user(request)
        if write:require_csrf(request,current)
        actor=fresh_actor(db,current);require_role(actor,WRITE_ROLES if write else READ_ROLES)
        return actor

    @app.get('/api/operational/summary')
    def summary(request:Request,response:Response):
        response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=actor_for(db,request);generated_at=now()
            assets=[]
            import bench_ingress
            for row in db.execute('SELECT * FROM operational_assets ORDER BY created_at DESC LIMIT 100'):
                asset=dict(row)
                latest=db.execute('''SELECT s.* FROM bench_samples s JOIN bench_runs r ON r.id=s.run_id
                    WHERE r.device_id=? AND r.source_type=? ORDER BY s.received_at DESC,s.frame_index DESC LIMIT 1''',(row['device_id'],row['source_type'])).fetchone()
                asset['latest']=bench_ingress.present(latest) if latest else None
                asset['receipt']=receipt_timing(asset['latest'],generated_at)
                assets.append(asset)
            cases=[dict(row) for row in db.execute('SELECT * FROM operational_cases'+(' WHERE assignee_id=?' if actor['role']=='operator' else '')+' ORDER BY updated_at DESC LIMIT 200',(actor['id'],) if actor['role']=='operator' else ())]
            orders=[dict(row) for row in db.execute('SELECT * FROM operational_orders'+(' WHERE creator_id=? OR technician_id=?' if actor['role']=='operator' else '')+' ORDER BY updated_at DESC LIMIT 200',(actor['id'],actor['id']) if actor['role']=='operator' else ())]
            orders=[present_order(row) for row in orders]
            for row in cases:
                row['first_snapshot']=json.loads(row['first_snapshot']);row['last_snapshot']=json.loads(row['last_snapshot'])
            rules=[dict(row) for row in db.execute('SELECT * FROM operational_rules ORDER BY created_at DESC LIMIT 100')]
            assignees=[dict(row) for row in db.execute("SELECT id,email,role FROM users WHERE disabled=0 AND role IN ('admin','operator') ORDER BY email,id LIMIT 100")] if actor['role'] in WRITE_ROLES else []
            return dict(assets=assets,rules=rules,cases=cases,orders=orders,assignees=assignees,generated_at=generated_at,role=actor['role'],user_id=actor['id'],**BOUNDARY)

    @app.post('/api/operational/assets')
    def create_asset(body:Asset,request:Request,response:Response):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            previous=db.execute('SELECT * FROM operational_assets WHERE device_id=? AND source_type=?',(body.device_id,body.source_type)).fetchone()
            if previous:
                if any(previous[k]!=getattr(body,k) for k in ('site_id','asset_id','device_id','label','source_type')) or previous['retired']:raise HTTPException(409,'Mapping exists; original mapping preserved')
                return dict(asset=dict(previous),created=False,**BOUNDARY)
            if db.execute('SELECT count(*) FROM operational_assets').fetchone()[0]>=100:raise HTTPException(429,'Asset registry capacity reached')
            identity=secrets.token_hex(16)
            db.execute('INSERT INTO operational_assets VALUES(?,?,?,?,?,?,1,0,?,?)',(identity,body.site_id,body.asset_id,body.label,body.device_id,body.source_type,actor['id'],now()))
            row=db.execute('SELECT * FROM operational_assets WHERE id=?',(identity,)).fetchone();event(db,'asset',row,actor,'asset_registered',body.reason,audit)
            response.status_code=201;return dict(asset=dict(row),created=True,**BOUNDARY)

    @app.get('/api/operational/assets/{identity}/readings')
    def asset_readings(identity:str,request:Request,limit:int=Query(default=100,ge=1,le=200)):
        with database() as db:
            db.execute('BEGIN');actor_for(db,request)
            asset=db.execute('SELECT * FROM operational_assets WHERE id=?',(identity,)).fetchone()
            if not asset:raise HTTPException(404,'Observation asset unavailable')
            run=db.execute('SELECT * FROM bench_runs WHERE device_id=? AND source_type=? ORDER BY last_received_at DESC,id DESC LIMIT 1',(asset['device_id'],asset['source_type'])).fetchone()
            import bench_ingress
            rows=db.execute('SELECT * FROM bench_samples WHERE run_id=? ORDER BY frame_index DESC LIMIT ?',(run['id'],limit)).fetchall() if run else []
            return dict(asset=dict(asset),run=dict(run) if run else None,items=[bench_ingress.present(row) for row in reversed(rows)],
                        order='Host frame index within the latest run; not verified device sampling time',**BOUNDARY)

    @app.post('/api/operational/assets/{identity}/retire')
    def retire(identity:str,body:Revision,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            row=db.execute('SELECT * FROM operational_assets WHERE id=?',(identity,)).fetchone()
            if not row:raise HTTPException(404,'Mapping not found')
            if row['revision']!=body.expected_revision:raise HTTPException(409,'Mapping changed; refresh')
            if row['retired']:raise HTTPException(409,'Mapping already retired')
            db.execute('UPDATE operational_assets SET retired=1,revision=revision+1 WHERE id=?',(identity,))
            db.execute('UPDATE operational_rules SET enabled=0,revision=revision+1 WHERE asset=? AND enabled=1',(identity,))
            row=db.execute('SELECT * FROM operational_assets WHERE id=?',(identity,)).fetchone();event(db,'asset',row,actor,'asset_retired',body.reason,audit)
            return dict(asset=dict(row),**BOUNDARY)

    @app.post('/api/operational/rules')
    def create_rule(body:Rule,request:Request,response:Response):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            asset=db.execute('SELECT * FROM operational_assets WHERE id=?',(body.asset,)).fetchone()
            if not asset or asset['retired'] or asset['revision']!=body.expected_asset_revision:raise HTTPException(409,'Select a current active mapping')
            if db.execute('SELECT count(*) FROM operational_rules').fetchone()[0]>=100:raise HTTPException(429,'Rule capacity reached')
            if body.enabled and db.execute('SELECT 1 FROM operational_rules WHERE asset=? AND channel=? AND enabled=1',(body.asset,body.channel)).fetchone():raise HTTPException(409,'Disable the current channel rule before replacing it')
            identity=secrets.token_hex(16)
            db.execute('INSERT INTO operational_rules VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?,?)',
                (identity,body.asset,asset['revision'],body.channel,body.comparison,body.threshold,body.window_frames,body.max_age_seconds,int(body.enabled),actor['id'],local_notifications.account_revision(db,actor['id']),body.reason,now()))
            row=db.execute('SELECT * FROM operational_rules WHERE id=?',(identity,)).fetchone();event(db,'rule',row,actor,'rule_created',body.reason,audit)
            response.status_code=201;return dict(rule=dict(row),**BOUNDARY)

    @app.post('/api/operational/rules/{identity}/disable')
    def disable(identity:str,body:Revision,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            row=db.execute('SELECT * FROM operational_rules WHERE id=?',(identity,)).fetchone()
            if not row:raise HTTPException(404,'Rule not found')
            if row['revision']!=body.expected_revision:raise HTTPException(409,'Rule changed; refresh')
            db.execute('UPDATE operational_rules SET enabled=0,revision=revision+1 WHERE id=?',(identity,))
            row=db.execute('SELECT * FROM operational_rules WHERE id=?',(identity,)).fetchone();event(db,'rule',row,actor,'rule_disabled',body.reason,audit)
            return dict(rule=dict(row),**BOUNDARY)

    @app.post('/api/operational/cases/{identity}/assign')
    def assign(identity:str,body:Assignment,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            row=visible(db,'operational_cases',identity,actor);eligible(db,body.assignee_id)
            if row['revision']!=body.expected_revision:raise HTTPException(409,'Case changed; refresh')
            db.execute('UPDATE operational_cases SET assignee_id=?,revision=revision+1,updated_at=? WHERE id=?',(body.assignee_id,now(),identity))
            row=visible(db,'operational_cases',identity,actor);event(db,'case',row,actor,'case_assigned',body.reason,audit)
            return dict(record=dict(row),**BOUNDARY)

    @app.post('/api/operational/cases/{identity}/action')
    def case_action(identity:str,body:Action,request:Request):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=actor_for(db,request,True);row=visible(db,'operational_cases',identity,actor)
            transitions={'acknowledge':('open','acknowledged'),'resolve':('acknowledged','resolved')}
            if body.action not in transitions or row['state']!=transitions[body.action][0] or row['revision']!=body.expected_revision:raise HTTPException(409,'Case state or revision changed')
            if body.action=='resolve' and not body.evidence_refs.strip():raise HTTPException(422,'Resolution needs evidence references; not physical verification')
            db.execute('UPDATE operational_cases SET state=?,revision=revision+1,updated_at=? WHERE id=?',(transitions[body.action][1],now(),identity))
            row=visible(db,'operational_cases',identity,actor);event(db,'case',row,actor,body.action,body.note+' | '+body.evidence_refs,audit)
            return dict(record=dict(row),**BOUNDARY)

    @app.post('/api/operational/orders')
    def create_order(body:WorkOrder,request:Request,response:Response):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=actor_for(db,request,True)
            request_hash=hashlib.sha256(canonical(body.model_dump()).encode()).hexdigest()
            old=db.execute('SELECT * FROM operational_orders WHERE creator_id=? AND request_key=?',(actor['id'],body.request_key)).fetchone()
            if old:
                if old['request_hash']!=request_hash:raise HTTPException(409,'Request key reused with different content')
                visible(db,'operational_cases',old['case_id'],actor);return dict(record=present_order(old),created=False,**BOUNDARY)
            case=visible(db,'operational_cases',body.case_id,actor);eligible(db,body.technician_id)
            if case['state']=='resolved' or case['revision']!=body.expected_case_revision:raise HTTPException(409,'Select a current unresolved case')
            if db.execute('SELECT count(*) FROM operational_orders').fetchone()[0]>=2000:raise HTTPException(429,'Work record capacity reached')
            identity=secrets.token_hex(16);stamp=now()
            snapshot=canonical(dict(case))
            values=(identity,case['id'],actor['id'],body.request_key,request_hash,case['revision'],snapshot,hashlib.sha256(snapshot.encode()).hexdigest(),case['source_type'],body.title,body.procedure,body.technician_id,'draft',1,None,None,None,'',stamp,stamp)
            db.execute('INSERT INTO operational_orders VALUES('+','.join('?' for _ in values)+')',values)
            row=db.execute('SELECT * FROM operational_orders WHERE id=?',(identity,)).fetchone();event(db,'order',row,actor,'order_created','Created from case revision '+str(case['revision']),audit)
            response.status_code=201;return dict(record=present_order(row),created=True,**BOUNDARY)

    @app.post('/api/operational/orders/{identity}/action')
    def order_action(identity:str,body:Action,request:Request):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=actor_for(db,request,True);row=visible(db,'operational_orders',identity,actor)
            present_order(row)
            transitions={'submit':('draft','submitted'),'approve':('submitted','approved'),'reject':('submitted','rejected'),
                         'start':('approved','in-progress'),'complete':('in-progress','verification-pending'),'verify':('verification-pending','closed')}
            if row['revision']!=body.expected_revision or body.action not in transitions or row['state']!=transitions[body.action][0]:raise HTTPException(409,'Work record state or revision changed')
            if body.action=='submit' and actor['id']!=row['creator_id']:raise HTTPException(403,'Only the creator submits a draft')
            if body.action in ('approve','reject','verify'):
                if actor['role']!='admin' or actor['id'] in (row['creator_id'],row['executor_id']):raise HTTPException(403,'Independent active administrator required')
                case=db.execute('SELECT * FROM operational_cases WHERE id=?',(row['case_id'],)).fetchone()
                if body.action=='approve' and (case['revision']!=row['case_revision'] or case['state']=='resolved'):raise HTTPException(409,'Source case changed; prepare a new draft from its current revision')
            if body.action in ('start','complete') and actor['id']!=row['technician_id']:raise HTTPException(403,'Only the assigned technician records execution')
            if body.action=='start':
                case=db.execute('SELECT * FROM operational_cases WHERE id=?',(row['case_id'],)).fetchone()
                if not case or case['revision']!=row['case_revision'] or case['state']=='resolved':raise HTTPException(409,'Source case changed after approval; prepare a new independently reviewed draft')
                approver=db.execute('SELECT * FROM users WHERE id=?',(row['approver_id'],)).fetchone()
                if not approver or approver['disabled'] or approver['role']!='admin' or row['approver_revision']!=local_notifications.account_revision(db,approver['id']):raise HTTPException(409,'Approval authority changed; prepare a new independently reviewed draft')
            if body.action in ('complete','verify') and not body.evidence_refs.strip():raise HTTPException(422,'Completion/review requires evidence references')
            db.execute('''UPDATE operational_orders SET state=?,revision=revision+1,updated_at=?,
                approver_id=CASE WHEN ?='approve' THEN ? ELSE approver_id END,
                approver_revision=CASE WHEN ?='approve' THEN ? ELSE approver_revision END,
                executor_id=CASE WHEN ?='start' THEN ? ELSE executor_id END,
                evidence_refs=CASE WHEN ?!='' THEN ? ELSE evidence_refs END WHERE id=?''',
                (transitions[body.action][1],now(),body.action,actor['id'],body.action,local_notifications.account_revision(db,actor['id']),body.action,actor['id'],body.evidence_refs,body.evidence_refs,identity))
            row=db.execute('SELECT * FROM operational_orders WHERE id=?',(identity,)).fetchone();event(db,'order',row,actor,body.action,body.note,audit)
            return dict(record=present_order(row),**BOUNDARY)

    @app.get('/api/operational/{kind}/{identity}/history')
    def history(kind:Literal['case','order'],identity:str,request:Request):
        with database() as db:
            db.execute('BEGIN');actor=actor_for(db,request)
            row=visible(db,'operational_cases' if kind=='case' else 'operational_orders',identity,actor)
            events=[]
            for saved in db.execute('SELECT id,revision,action,note,time_utc,snapshot_json FROM operational_events WHERE kind=? AND record_id=? ORDER BY id DESC LIMIT 200',(kind,identity)):
                entry={key:saved[key] for key in ('id','revision','action','note','time_utc')}
                if kind=='case':
                    try:
                        captured=json.loads(saved['snapshot_json']);observation=json.loads(captured['last_snapshot'])
                        entry.update(captured_state=captured['state'],captured_last_frame=captured['last_frame'],
                            captured_channel=observation['channel'],captured_value=observation['value'],captured_source_type=captured['source_type'])
                    except (KeyError,TypeError,ValueError):raise HTTPException(503,'Saved review context unavailable; no history is inferred') from None
                events.append(entry)
            return dict(record=present_order(row) if kind=='order' else dict(row),events=events,**BOUNDARY)
