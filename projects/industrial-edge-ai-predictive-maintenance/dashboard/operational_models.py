"""Single-channel statistical baselines on retained runs, not failure/RUL prediction.

Run splits are host-run splits; unknown physical boot identity remains unknown.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import secrets
import re
from typing import Literal
from statistics import mean, pstdev
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from maintenance_requests import fresh_actor, require_role, READ_ROLES, WRITE_ROLES
from team_accounts import StrictModel, reauthenticate
from operational_workflow import CHANNELS
import local_notifications

BOUNDARY=dict(scope='local-statistical-baselines',production_ready=False,equipment_authorized=False,
              failure_prediction_validated=False,remaining_useful_life_available=False,onnx_runtime=False)


class Fit(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    request_key:str=Field(strict=True,pattern=r'^[a-f0-9]{32}$')
    asset:str=Field(strict=True,pattern=r'^[a-f0-9]{32}$')
    expected_asset_revision:int=Field(strict=True,ge=1)
    channel:str=Field(strict=True,min_length=3,max_length=50)
    run_ids:list[str]=Field(min_length=3,max_length=10)
    qualification_note:str=Field(strict=True,min_length=20,max_length=1000)
    minimum_score_threshold:float=Field(strict=True,allow_inf_nan=False,ge=0,le=1000,default=3.0)


class Release(StrictModel):
    expected_revision:int=Field(strict=True,ge=1)
    artifact_sha256:str=Field(strict=True,pattern=r'^[a-f0-9]{64}$')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS operational_models(
        id TEXT PRIMARY KEY,creator_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,request_hash TEXT NOT NULL,
        asset TEXT NOT NULL REFERENCES operational_assets(id),asset_revision INTEGER NOT NULL,channel TEXT NOT NULL,source_type TEXT NOT NULL,
        artifact TEXT NOT NULL,artifact_sha256 TEXT NOT NULL,report TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL,
        reviewer_id INTEGER REFERENCES users(id),reviewer_revision INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        UNIQUE(creator_id,request_key))''')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS operational_active_model ON operational_models(asset,channel) WHERE state='active'")
    db.execute('''CREATE TABLE IF NOT EXISTS operational_model_events(
        id INTEGER PRIMARY KEY,model_id TEXT NOT NULL REFERENCES operational_models(id),revision INTEGER NOT NULL,
        actor_id INTEGER NOT NULL REFERENCES users(id),action TEXT NOT NULL,note TEXT NOT NULL,time_utc TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS operational_scores(
        model_id TEXT NOT NULL REFERENCES operational_models(id),run_id TEXT NOT NULL,frame_index INTEGER NOT NULL,
        observation_hash TEXT NOT NULL,source_type TEXT NOT NULL,score REAL,threshold REAL NOT NULL,
        decision TEXT NOT NULL,received_at TEXT NOT NULL,PRIMARY KEY(model_id,run_id,frame_index))''')


def artifact(row):
    value=json.loads(row['artifact'])
    if digest(value)!=row['artifact_sha256']:raise HTTPException(503,'Stored baseline artifact integrity failure')
    if value.get('report_sha256')!=digest(json.loads(row['report'])):raise HTTPException(503,'Stored baseline report integrity failure')
    if value.get('format')!='edgeops-statistical-baseline-v1' or value.get('channel')!=row['channel'] or value.get('source_type')!=row['source_type']:raise HTTPException(503,'Stored baseline compatibility failure')
    if any(type(value.get(key)) not in (float,int) or not math.isfinite(value[key]) for key in ('center','scale','threshold')) or value['scale']<=0 or value['threshold']<0:raise HTTPException(503,'Stored baseline numeric failure')
    return value


def current(db,row):
    user=db.execute('SELECT * FROM users WHERE id=?',(row['reviewer_id'],)).fetchone()
    asset=db.execute('SELECT * FROM operational_assets WHERE id=?',(row['asset'],)).fetchone()
    return bool(row['state']=='active' and user and user['role']=='admin' and not user['disabled'] and
                local_notifications.account_revision(db,user['id'])==row['reviewer_revision'] and asset and
                not asset['retired'] and asset['revision']==row['asset_revision'])


def consume(db,body,content_hash,received_at):
    rows=db.execute('''SELECT m.* FROM operational_models m JOIN operational_assets a ON a.id=m.asset
        WHERE m.state='active' AND a.device_id=? AND a.source_type=?''',(body.frame['device_id'],body.source_type)).fetchall()
    for row in rows:
        if not current(db,row):continue
        if db.execute('SELECT count(*) FROM operational_scores').fetchone()[0]>=50000:raise HTTPException(429,'Baseline score capacity reached; retain original gateway data for retry')
        model=artifact(row);raw,flag,divisor=CHANNELS[row['channel']]
        score=abs(body.frame[raw]/divisor-model['center'])/model['scale'] if body.frame[flag] else None
        invalid_numeric=score is not None and not math.isfinite(score)
        if invalid_numeric:score=None
        # Independent source and clock policies still govern operational cases.
        # A deviation score never creates a diagnosis or work order implicitly.
        db.execute('INSERT INTO operational_scores VALUES(?,?,?,?,?,?,?,?,?)',(row['id'],body.run_id,body.frame_index,content_hash,body.source_type,score,model['threshold'],
                   'numeric-abstention' if invalid_numeric else 'unavailable' if score is None else 'baseline-deviation' if score>model['threshold'] else 'within-baseline',received_at))


def install_routes(app,database,require_user,require_csrf,matches,audit):
    @app.get('/api/operational/models')
    def catalog(request:Request):
        current_user=require_user(request)
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current_user);require_role(actor,READ_ROLES)
            models=[]
            for row in db.execute('SELECT * FROM operational_models ORDER BY created_at DESC LIMIT 100'):
                model={key:row[key] for key in ('id','creator_id','asset','channel','source_type','state','revision','artifact_sha256','created_at','updated_at')}
                model.update(artifact=artifact(row),report=json.loads(row['report']),release_current=current(db,row));models.append(model)
            scores=[dict(row) for row in db.execute('SELECT * FROM operational_scores ORDER BY received_at DESC LIMIT 100')]
            return dict(models=models,scores=scores,role=actor['role'],user_id=actor['id'],
                        runs=[dict(row) for row in db.execute('SELECT * FROM bench_runs ORDER BY created_at DESC LIMIT 100')],
                        assets=[dict(row) for row in db.execute('SELECT * FROM operational_assets ORDER BY created_at DESC LIMIT 100')],**BOUNDARY)

    @app.post('/api/operational/models')
    def fit(body:Fit,request:Request):
        current_user=require_user(request);require_csrf(request,current_user)
        if body.channel not in CHANNELS or len(set(body.run_ids))!=len(body.run_ids) or any(not re.fullmatch('[a-f0-9]{32}',x) for x in body.run_ids):raise HTTPException(422,'Use a supported channel and at least three distinct capture runs')
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=fresh_actor(db,current_user);require_role(actor,WRITE_ROLES)
            request_hash=digest(body.model_dump());previous=db.execute('SELECT * FROM operational_models WHERE creator_id=? AND request_key=?',(actor['id'],body.request_key)).fetchone()
            if previous:
                if previous['request_hash']!=request_hash:raise HTTPException(409,'Training request identity reused with different inputs')
                return dict(id=previous['id'],created=False,**BOUNDARY)
            asset=db.execute('SELECT * FROM operational_assets WHERE id=?',(body.asset,)).fetchone()
            if not asset or asset['retired'] or asset['revision']!=body.expected_asset_revision:raise HTTPException(409,'Choose a current mapping')
            if db.execute('SELECT count(*) FROM operational_models').fetchone()[0]>=100:raise HTTPException(429,'Candidate model capacity reached')
            run_data=[];raw,flag,divisor=CHANNELS[body.channel]
            import bench_ingress
            for identity in body.run_ids:
                run=db.execute('SELECT * FROM bench_runs WHERE id=?',(identity,)).fetchone()
                if not run or run['device_id']!=asset['device_id'] or run['source_type']!=asset['source_type']:raise HTTPException(422,'Runs must match the exact mapping and source lane')
                samples=db.execute('SELECT * FROM bench_samples WHERE run_id=? ORDER BY frame_index LIMIT 1001',(identity,)).fetchall()
                if len(samples)>1000:raise HTTPException(422,'A run exceeds the bounded 1,000-record study size; prepare a reviewed subset outside this service')
                values=[];hashes=[];invalid=0
                for sample in samples:
                    verified=bench_ingress.present(sample);hashes.append(sample['content_hash'])
                    if verified['frame'][flag]:
                        value=verified['frame'][raw]/divisor
                        if abs(value)>1e12:raise HTTPException(422,'Selected channel exceeds bounded baseline numeric support')
                        values.append(value)
                    else:invalid+=1
                if len(values)<5:raise HTTPException(422,'Each run needs at least five declared-valid observations for the selected channel')
                run_data.append(dict(id=identity,created_at=run['created_at'],values=values,hashes=hashes,invalid=invalid))
            run_data.sort(key=lambda run:(run['created_at'],run['id']))
            training=[value for run in run_data[:-2] for value in run['values']]
            validation=run_data[-2]['values'];holdout=run_data[-1]['values']
            center=mean(training);scale=max(pstdev(training),1e-6)
            validation_scores=sorted(abs(value-center)/scale for value in validation)
            threshold=max(body.minimum_score_threshold,validation_scores[math.ceil(.95*len(validation_scores))-1])
            model=dict(format='edgeops-statistical-baseline-v1',channel=body.channel,source_type=asset['source_type'],center=center,scale=scale,threshold=threshold,
                       feature='single declared-valid channel value in contract SI units',scale_floor=1e-6)
            report=dict(training_runs=[run['id'] for run in run_data[:-2]],validation_runs=[run_data[-2]['id']],holdout_runs=[run_data[-1]['id']],
                training_records=len(training),validation_records=len(validation),holdout_records=len(holdout),
                holdout_deviation_records=sum(abs(value-center)/scale>threshold for value in holdout),
                data_sha256=digest([dict(run=run['id'],hashes=run['hashes']) for run in run_data]),
                invalid_records=sum(run['invalid'] for run in run_data),qualification_note=body.qualification_note,
                physical_session_independence_verified=False,label_quality='owner-declared study context; no failure ground truth',
                split_basis='Chronological host-run creation; no random row split. Physical boot identity unavailable.',
                fitting_basis='Centers/scales use training runs only; threshold uses validation only; holdout does not affect artifact.',
                accuracy=None,failure_prediction_validated=False,calibration_verified=False)
            model['report_sha256']=digest(report)
            identity=secrets.token_hex(16);stamp=now()
            db.execute('INSERT INTO operational_models VALUES(?,?,?,?,?,?,?,?,?,?,?,\'candidate\',1,NULL,NULL,?,?)',
                (identity,actor['id'],body.request_key,request_hash,asset['id'],asset['revision'],body.channel,asset['source_type'],canonical(model),digest(model),canonical(report),stamp,stamp))
            db.execute('INSERT INTO operational_model_events(model_id,revision,actor_id,action,note,time_utc) VALUES(?,1,?,?,?,?)',(identity,actor['id'],'fitted',body.qualification_note,stamp))
            audit(db,actor['email'],'operational_model_fitted',identity)
            return dict(id=identity,created=True,artifact=model,artifact_sha256=digest(model),report=report,**BOUNDARY)

    @app.post('/api/operational/models/{identity}/{action}')
    def release(identity:str,action:Literal['activate','rollback','retire'],body:Release,request:Request):
        current_user=require_user(request);require_csrf(request,current_user)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current_user,body.current_password,matches,audit)
            row=db.execute('SELECT * FROM operational_models WHERE id=?',(identity,)).fetchone()
            if not row:raise HTTPException(404,'Baseline unavailable')
            artifact(row)
            if row['revision']!=body.expected_revision or row['artifact_sha256']!=body.artifact_sha256:raise HTTPException(409,'Model revision or artifact changed')
            if action in ('activate','rollback'):
                if actor['id']==row['creator_id']:raise HTTPException(403,'An independent administrator must activate a candidate')
                asset=db.execute('SELECT * FROM operational_assets WHERE id=?',(row['asset'],)).fetchone()
                if row['state']!=('candidate' if action=='activate' else 'retired') or asset['retired'] or asset['revision']!=row['asset_revision']:raise HTTPException(409,'Candidate or mapping changed')
                old=list(db.execute("SELECT * FROM operational_models WHERE asset=? AND channel=? AND state='active'",(row['asset'],row['channel'])))
                for previous in old:
                    db.execute("UPDATE operational_models SET state='retired',revision=revision+1,updated_at=? WHERE id=?",(now(),previous['id']))
                    db.execute('INSERT INTO operational_model_events(model_id,revision,actor_id,action,note,time_utc) VALUES(?,?,?,?,?,?)',(previous['id'],previous['revision']+1,actor['id'],'replaced','Replaced by independently activated '+identity,now()))
                db.execute("UPDATE operational_models SET state='active',revision=revision+1,reviewer_id=?,reviewer_revision=?,updated_at=? WHERE id=?",(actor['id'],local_notifications.account_revision(db,actor['id']),now(),identity))
            else:
                if row['state']!='active':raise HTTPException(409,'Only an active baseline can be retired')
                db.execute("UPDATE operational_models SET state='retired',revision=revision+1,updated_at=? WHERE id=?",(now(),identity))
            db.execute('INSERT INTO operational_model_events(model_id,revision,actor_id,action,note,time_utc) VALUES(?,?,?,?,?,?)',(identity,row['revision']+1,actor['id'],action,body.reason,now()))
            audit(db,actor['email'],'operational_model_'+action,identity)
            return dict(id=identity,state='active' if action in ('activate','rollback') else 'retired',**BOUNDARY)
