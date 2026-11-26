"""Atomic, opt-in synthetic threshold correlation with explicit human handoff."""
from datetime import datetime,timezone
import hashlib
import json
import secrets
from typing import Literal

from fastapi import HTTPException,Request,Response,Query
from pydantic import BaseModel,ConfigDict,Field,field_validator
from acquisition_registry import Identifier
from maintenance_requests import ASSETS,READ_ROLES,WRITE_ROLES,fresh_actor,require_role
from team_accounts import StrictModel,reauthenticate
import observation_queries as observations
import incidents

BOUNDARY={'scope':'local-synthetic-correlation','source_type':'synthetic','production_ready':False,
          'hardware_connected':False,'equipment_authorized':False,'external_notifications_sent':False}
MAX_POLICIES=50
MAX_CASES=1000
MAX_EVALUATIONS=60000
CHANNELS=Literal['acceleration_x_mps2','acceleration_y_mps2','acceleration_z_mps2',
                 'motor_case_temperature_c','bus_voltage_v','current_a']


class Definition(BaseModel):
    model_config=ConfigDict(extra='forbid')
    label:str=Field(strict=True,min_length=5,max_length=100)
    device_id:Identifier
    expected_binding_revision:int=Field(strict=True,ge=1)
    channel:CHANNELS
    comparison:Literal['above','below']
    threshold:float=Field(strict=True,allow_inf_nan=False,ge=-1e12,le=1e12)
    window_size:int=Field(strict=True,ge=1,le=1000000)
    max_age_seconds:int=Field(strict=True,ge=1,le=86400)
    severity:Literal['watch','critical']
    calibration_policy:Literal['verified_only','allow_declared_unverified_for_synthetic']

    @field_validator('label')
    @classmethod
    def substantive(cls,value):
        value=value.strip()
        if len(value)<5:raise ValueError('Use a substantive policy label')
        return value


class CreatePolicy(Definition):
    current_password:str=Field(strict=True,min_length=1,max_length=256)
    reason:str=Field(strict=True,min_length=10,max_length=800)

    @field_validator('reason')
    @classmethod
    def explanation(cls,value):
        if len(value.strip())<10:raise ValueError('Explain activation in at least ten characters')
        return value.strip()


class DisablePolicy(StrictModel):
    expected_revision:int=Field(strict=True,ge=1)


class Handoff(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:int=Field(strict=True,ge=1)
    note:str=Field(strict=True,min_length=10,max_length=800)

    @field_validator('note')
    @classmethod
    def explanation(cls,value):
        if len(value.strip())<10:raise ValueError('Explain the human handoff')
        return value.strip()


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def sha(value):return hashlib.sha256(value.encode()).hexdigest()


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS correlation_policies(
        id TEXT PRIMARY KEY,device_id TEXT NOT NULL REFERENCES acquisition_bindings(device_id),
        site_id TEXT NOT NULL,asset_id TEXT NOT NULL,binding_revision INTEGER NOT NULL,
        channel TEXT NOT NULL,definition TEXT NOT NULL,config_hash TEXT NOT NULL,
        issuer_id INTEGER NOT NULL REFERENCES users(id),issuer_revision INTEGER NOT NULL,
        disabled INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL,created_at TEXT NOT NULL,
        disabled_at TEXT,activation_reason TEXT NOT NULL,disable_reason TEXT)''')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS correlation_active_channel ON correlation_policies(device_id,channel) WHERE disabled=0')
    db.execute('''CREATE TABLE IF NOT EXISTS correlation_cases(
        id TEXT PRIMARY KEY,policy_id TEXT NOT NULL REFERENCES correlation_policies(id),
        boot_id TEXT NOT NULL,bucket INTEGER NOT NULL,first_event_key TEXT NOT NULL REFERENCES acquisition_observations(event_key),
        matched_events INTEGER NOT NULL,min_sequence INTEGER NOT NULL,max_sequence INTEGER NOT NULL,
        revision INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        UNIQUE(policy_id,boot_id,bucket))''')
    db.execute('''CREATE TABLE IF NOT EXISTS correlation_evaluations(
        policy_id TEXT NOT NULL REFERENCES correlation_policies(id),event_key TEXT NOT NULL REFERENCES acquisition_observations(event_key),
        decision TEXT NOT NULL,case_id TEXT REFERENCES correlation_cases(id),evaluated_at TEXT NOT NULL,
        PRIMARY KEY(policy_id,event_key))''')
    db.execute('CREATE INDEX IF NOT EXISTS correlation_case_evidence ON correlation_evaluations(case_id,event_key)')
    db.execute('''CREATE TABLE IF NOT EXISTS correlation_handoffs(
        case_id TEXT PRIMARY KEY REFERENCES correlation_cases(id),incident_id TEXT NOT NULL REFERENCES synthetic_incidents(id),
        actor_id INTEGER NOT NULL REFERENCES users(id),case_revision INTEGER NOT NULL,
        request_hash TEXT NOT NULL,snapshot_json TEXT NOT NULL,created_at TEXT NOT NULL)''')


def definition(row):
    try:
        parsed=Definition.model_validate_json(row['definition'])
        if (sha(canonical(parsed.model_dump()))!=row['config_hash'] or parsed.device_id!=row['device_id']
                or parsed.channel!=row['channel'] or parsed.expected_binding_revision!=row['binding_revision']):
            raise ValueError()
        return parsed
    except (ValueError,TypeError):raise HTTPException(503,'Saved correlation policy failed integrity checks') from None


def effective_status(db,row):
    if row['disabled']:return 'disabled'
    issuer=db.execute('''SELECT u.disabled,u.role,COALESCE(c.revision,1) revision FROM users u
        LEFT JOIN account_controls c ON c.user_id=u.id WHERE u.id=?''',(row['issuer_id'],)).fetchone()
    if not issuer or issuer['disabled'] or issuer['role']!='admin' or issuer['revision']!=row['issuer_revision']:
        return 'issuer-changed'
    binding=db.execute('SELECT * FROM acquisition_bindings WHERE device_id=?',(row['device_id'],)).fetchone()
    if (not binding or binding['status']!='active' or binding['revision']!=row['binding_revision']
            or binding['site_id']!=row['site_id'] or binding['asset_id']!=row['asset_id']):return 'binding-changed'
    return 'active'


def public_policy(db,row):
    return {**definition(row).model_dump(),'id':row['id'],'site_id':row['site_id'],'asset_id':row['asset_id'],
            'config_hash':row['config_hash'],'revision':row['revision'],'status':effective_status(db,row),
            'created_at':row['created_at'],'disabled_at':row['disabled_at'],
            'activation_reason':row['activation_reason'],'disable_reason':row['disable_reason'],'issuer_id':row['issuer_id']}


def evaluate(db,audit,actor_label,body,event_key,now):
    """Only called for a newly committed source inside its authorized write transaction."""
    obs=body.observation
    policies=db.execute('SELECT * FROM correlation_policies WHERE device_id=? AND disabled=0 ORDER BY id',
                        (obs.device_id,)).fetchall()
    for row in policies:
        config=definition(row)
        if effective_status(db,row)!='active':continue
        if (row['site_id']!=obs.site_id or row['asset_id']!=obs.asset_id or row['binding_revision']!=body.binding_revision):
            raise HTTPException(503,'Active correlation scope is inconsistent')
        if db.execute('SELECT count(*) FROM correlation_evaluations').fetchone()[0]>=MAX_EVALUATIONS:
            raise HTTPException(429,'Correlation evidence capacity reached; new observation was not accepted')
        value=getattr(obs.measurements,config.channel)
        quality=getattr(obs.quality,observations.CHANNELS[config.channel]['sensor'])
        decision='not-matched';case_id=None
        if quality!='valid' or value is None:decision='quality-unusable'
        elif config.calibration_policy=='verified_only' and obs.quality.calibration!='verified':decision='calibration-unverified'
        elif obs.timestamp.clock_quality!='device_clock_verified' or obs.timestamp.device_time_utc is None:decision='clock-unverified'
        elif not 0<=(datetime.fromisoformat(now)-obs.timestamp.device_time_utc).total_seconds()<=config.max_age_seconds:decision='stale-or-future'
        elif ((config.comparison=='above' and value>config.threshold) or
              (config.comparison=='below' and value<config.threshold)):
            decision='matched';bucket=obs.sequence//config.window_size
            case_id=sha(canonical([row['id'],obs.boot_id,bucket]))
            previous=db.execute('SELECT * FROM correlation_cases WHERE id=?',(case_id,)).fetchone()
            if previous:
                db.execute('''UPDATE correlation_cases SET matched_events=matched_events+1,
                    min_sequence=min(min_sequence,?),max_sequence=max(max_sequence,?),revision=revision+1,
                    updated_at=? WHERE id=?''',(obs.sequence,obs.sequence,now,case_id))
            else:
                if db.execute('SELECT count(*) FROM correlation_cases').fetchone()[0]>=MAX_CASES:
                    raise HTTPException(429,'Correlation case capacity reached; new observation was not accepted')
                db.execute('INSERT INTO correlation_cases VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (case_id,row['id'],obs.boot_id,bucket,event_key,1,obs.sequence,obs.sequence,1,now,now))
                audit(db,actor_label,'synthetic_correlation_detected',canonical({'case_id':case_id,'policy_id':row['id']}))
        db.execute('INSERT INTO correlation_evaluations VALUES(?,?,?,?,?)',(row['id'],event_key,decision,case_id,now))


def case_summary(db,row,actor):
    policy=db.execute('SELECT * FROM correlation_policies WHERE id=?',(row['policy_id'],)).fetchone()
    config=public_policy(db,policy)
    link=db.execute('SELECT * FROM correlation_handoffs WHERE case_id=?',(row['id'],)).fetchone()
    incident_id=None
    if link:
        try:incidents.visible(db,link['incident_id'],actor);incident_id=link['incident_id']
        except HTTPException:pass
    return {**dict(row),'policy':config,'handoff_recorded':bool(link),'incident_id':incident_id,
            'handoff_case_revision':link['case_revision'] if link else None,
            'new_evidence_since_handoff':bool(link and link['case_revision']!=row['revision']),
            'can_handoff':actor['role'] in WRITE_ROLES and not link}


def source_record(db,key):
    source=db.execute('SELECT * FROM acquisition_observations WHERE event_key=?',(key,)).fetchone()
    if not source:raise HTTPException(503,'Correlation source observation unavailable')
    result=observations.present(source,datetime.now(timezone.utc),60)
    result['committing_principal']=source['actor']
    return result


def install_routes(app,database,require_user,require_csrf,matches,audit):
    @app.get('/api/correlation/policies')
    def policies(request:Request,response:Response):
        current=require_user(request)
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            result=[public_policy(db,row) for row in db.execute('SELECT * FROM correlation_policies ORDER BY created_at DESC,id LIMIT 50')]
        response.headers['Cache-Control']='no-store'
        return {**BOUNDARY,'policies':result,'can_manage':actor['role']=='admin','retained_policy_limit':MAX_POLICIES,
                'response_generated_at':datetime.now(timezone.utc).isoformat()}

    @app.post('/api/correlation/policies')
    def create(body:CreatePolicy,request:Request,response:Response):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            binding=db.execute('SELECT * FROM acquisition_bindings WHERE device_id=?',(body.device_id,)).fetchone()
            if not binding or binding['status']!='active' or binding['revision']!=body.expected_binding_revision:
                raise HTTPException(409,'Reload an active exact synthetic binding')
            if binding['asset_id'] not in ASSETS:raise HTTPException(422,'Choose a test binding with an explicit dashboard asset')
            if db.execute('SELECT count(*) FROM correlation_policies').fetchone()[0]>=MAX_POLICIES:
                raise HTTPException(429,'Retained policy capacity reached')
            if db.execute('SELECT 1 FROM correlation_policies WHERE device_id=? AND channel=? AND disabled=0',(body.device_id,body.channel)).fetchone():
                raise HTTPException(409,'Disable the retained active channel policy before creating a replacement')
            config=Definition.model_validate(body.model_dump(exclude={'current_password','reason'}))
            config_json=canonical(config.model_dump());identifier=secrets.token_hex(16);now=datetime.now(timezone.utc).isoformat()
            issuer_revision=db.execute('SELECT COALESCE((SELECT revision FROM account_controls WHERE user_id=?),1)',(actor['id'],)).fetchone()[0]
            db.execute('INSERT INTO correlation_policies VALUES(?,?,?,?,?,?,?,?,?,?,0,1,?,NULL,?,NULL)',
                (identifier,body.device_id,binding['site_id'],binding['asset_id'],binding['revision'],body.channel,
                 config_json,sha(config_json),actor['id'],issuer_revision,now,body.reason))
            audit(db,actor['email'],'synthetic_correlation_policy_activated',identifier)
            result=public_policy(db,db.execute('SELECT * FROM correlation_policies WHERE id=?',(identifier,)).fetchone())
        response.status_code=201;response.headers['Cache-Control']='no-store'
        return {**BOUNDARY,'policy':result,'applies_to':'Newly committed synthetic observations only; no historical re-evaluation'}

    @app.post('/api/correlation/policies/{identifier}/disable')
    def disable(identifier:str,body:DisablePolicy,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            row=db.execute('SELECT * FROM correlation_policies WHERE id=?',(identifier,)).fetchone()
            if not row:raise HTTPException(404,'Policy not found')
            if row['revision']!=body.expected_revision:raise HTTPException(409,'Policy changed; refresh before disabling')
            if not row['disabled']:
                db.execute('UPDATE correlation_policies SET disabled=1,revision=revision+1,disabled_at=?,disable_reason=? WHERE id=?',
                    (datetime.now(timezone.utc).isoformat(),body.reason,identifier))
                audit(db,actor['email'],'synthetic_correlation_policy_disabled',identifier)
            return {**BOUNDARY,'policy':public_policy(db,db.execute('SELECT * FROM correlation_policies WHERE id=?',(identifier,)).fetchone())}

    @app.get('/api/correlation/cases')
    def cases(request:Request,response:Response,device_id:str=Query(default='',max_length=64,pattern=r'^[A-Za-z0-9_-]*$'),
              offset:int=Query(default=0,ge=0,le=1000),limit:int=Query(default=20,ge=1,le=100)):
        current=require_user(request)
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            where=' WHERE p.device_id=?' if device_id else '';args=[device_id] if device_id else []
            total=db.execute('SELECT count(*) FROM correlation_cases c JOIN correlation_policies p ON p.id=c.policy_id'+where,args).fetchone()[0]
            rows=db.execute('SELECT c.* FROM correlation_cases c JOIN correlation_policies p ON p.id=c.policy_id'+where+
                ' ORDER BY c.created_at DESC,c.id LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
            evaluations=dict(db.execute('SELECT decision,count(*) FROM correlation_evaluations GROUP BY decision'))
            result=[case_summary(db,row,actor) for row in rows]
        response.headers['Cache-Control']='no-store'
        return {**BOUNDARY,'cases':result,'total':total,'offset':offset,'limit':limit,'device_id':device_id,
            'evaluation_totals_all_devices':evaluations,'case_limit':MAX_CASES,'evaluation_limit':MAX_EVALUATIONS,
            'response_generated_at':datetime.now(timezone.utc).isoformat()}

    @app.get('/api/correlation/cases/{identifier}')
    def case_detail(identifier:str,request:Request,response:Response,offset:int=Query(default=0,ge=0,le=60000),limit:int=Query(default=20,ge=1,le=100),
                    case_revision:int|None=Query(default=None,ge=1)):
        current=require_user(request)
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            row=db.execute('SELECT * FROM correlation_cases WHERE id=?',(identifier,)).fetchone()
            if not row:raise HTTPException(404,'Correlation case not found')
            if case_revision is not None and row['revision']!=case_revision:
                raise HTTPException(409,'Case evidence changed; refresh before paging')
            evidence=db.execute('SELECT event_key FROM correlation_evaluations WHERE case_id=? ORDER BY event_key LIMIT ? OFFSET ?',
                                (identifier,limit,offset)).fetchall()
            result={**BOUNDARY,'case':case_summary(db,row,actor),'first_accepted_source':source_record(db,row['first_event_key']),
                'evidence':[source_record(db,item['event_key']) for item in evidence],'offset':offset,'limit':limit,
                'total_evidence':row['matched_events'],'evidence_order':'event-key ascending; not physical event time'}
        response.headers['Cache-Control']='no-store';return result

    @app.post('/api/correlation/cases/{identifier}/handoff')
    def handoff(identifier:str,body:Handoff,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=fresh_actor(db,current);require_role(actor,WRITE_ROLES)
            row=db.execute('SELECT * FROM correlation_cases WHERE id=?',(identifier,)).fetchone()
            if not row:raise HTTPException(404,'Correlation case not found')
            digest=sha(canonical(body.model_dump()));prior=db.execute('SELECT * FROM correlation_handoffs WHERE case_id=?',(identifier,)).fetchone()
            if prior:
                if prior['actor_id']!=actor['id'] or prior['request_hash']!=digest:
                    raise HTTPException(409,'Case already handed off; open the existing authorized incident')
                incident=incidents.visible(db,prior['incident_id'],actor)
                return {**BOUNDARY,'created':False,'incident_detail':incidents.detail(db,incident,actor)}
            if row['revision']!=body.expected_revision:raise HTTPException(409,'Case evidence changed; refresh before handoff')
            summary=case_summary(db,row,actor);source=source_record(db,row['first_event_key'])
            note=('Automatic synthetic case '+identifier+'; immutable policy '+row['policy_id']+' / '+summary['policy']['config_hash']+
                  '; case revision '+str(row['revision'])+'. Sequence grouping is not a verified physical fault. Human review: '+body.note)
            request_body=incidents.ObservationIncident(request_key=sha('correlation-handoff:'+identifier)[:32],
                event_key=source['event_key'],content_hash=source['content_hash'],title=('Synthetic threshold: '+summary['policy']['label'])[:120],
                observation=note,severity=summary['policy']['severity'])
            result=incidents.create_from_observation_in_transaction(db,actor,request_body,audit)
            db.execute('INSERT INTO correlation_handoffs VALUES(?,?,?,?,?,?,?)',(identifier,result['incident']['id'],actor['id'],row['revision'],
                digest,canonical(summary),datetime.now(timezone.utc).isoformat()))
            audit(db,actor['email'],'synthetic_correlation_handoff',identifier)
            incident=incidents.visible(db,result['incident']['id'],actor)
            return {**BOUNDARY,'created':True,'incident_detail':incidents.detail(db,incident,actor)}
