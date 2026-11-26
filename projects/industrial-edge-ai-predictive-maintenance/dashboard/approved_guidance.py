"""Role-filtered, extractive approved guidance. No LLM, remote fetch or tool execution."""
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
from typing import Literal
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from maintenance_requests import fresh_actor, require_role, READ_ROLES, WRITE_ROLES

BOUNDARY=dict(scope='local-approved-guidance',answer_mode='extractive-document-search',
              llm_connected=False,tool_execution=False,production_ready=False,equipment_authorized=False)


class Document(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    request_key:str=Field(strict=True,pattern=r'^[a-f0-9]{32}$')
    title:str=Field(strict=True,min_length=5,max_length=120)
    source_label:str=Field(strict=True,min_length=5,max_length=200)
    content:str=Field(strict=True,min_length=30,max_length=1500)
    permitted_roles:list[Literal['admin','operator','auditor']]=Field(min_length=1,max_length=3)
    rights_declared:bool=Field(strict=True)
    supersedes:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')


class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    expected_revision:int=Field(strict=True,ge=1)
    action:Literal['submit','approve','reject','retire']
    note:str=Field(strict=True,min_length=10,max_length=800)


class Question(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    question:str=Field(strict=True,min_length=5,max_length=500)


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS approved_guidance_documents(
        id TEXT PRIMARY KEY,creator_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,
        request_hash TEXT NOT NULL,title TEXT NOT NULL,source_label TEXT NOT NULL,content TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,permitted_roles TEXT NOT NULL,rights_declared INTEGER NOT NULL,
        supersedes TEXT REFERENCES approved_guidance_documents(id),state TEXT NOT NULL,revision INTEGER NOT NULL,
        reviewer_id INTEGER REFERENCES users(id),reviewer_revision INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        UNIQUE(creator_id,request_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS approved_guidance_events(
        document_id TEXT NOT NULL REFERENCES approved_guidance_documents(id),revision INTEGER NOT NULL,
        actor_id INTEGER NOT NULL REFERENCES users(id),action TEXT NOT NULL,note TEXT NOT NULL,time_utc TEXT NOT NULL,
        PRIMARY KEY(document_id,revision))''')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def sha(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def can_read(row,actor):
    return actor['role']=='admin' or row['creator_id']==actor['id'] or (row['state']=='approved' and actor['role'] in json.loads(row['permitted_roles']))


def present(row,actor):
    if sha(row['content'])!=row['content_sha256']:raise HTTPException(503,'Stored guidance content integrity check failed')
    return {key:row[key] for key in ('id','creator_id','title','source_label','content','content_sha256','rights_declared','supersedes','state','revision','reviewer_id','created_at','updated_at')}|{'permitted_roles':json.loads(row['permitted_roles'])}


def reviewer_active(db,row):
    import local_notifications
    user=db.execute('SELECT * FROM users WHERE id=?',(row['reviewer_id'],)).fetchone()
    return bool(user and user['role']=='admin' and not user['disabled'] and local_notifications.account_revision(db,user['id'])==row['reviewer_revision'])


def install_routes(app,database,require_user,require_csrf,audit):
    def actor_for(db,request,write=False):
        current=require_user(request)
        if write:require_csrf(request,current)
        actor=fresh_actor(db,current);require_role(actor,WRITE_ROLES if write else READ_ROLES);return actor

    @app.get('/api/guidance/documents')
    def documents(request:Request,response:Response):
        response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=actor_for(db,request)
            rows=[present(row,actor)|{'approval_current':reviewer_active(db,row) if row['state']=='approved' else False} for row in db.execute('SELECT * FROM approved_guidance_documents ORDER BY created_at DESC LIMIT 500') if can_read(row,actor)]
            return dict(documents=rows,role=actor['role'],user_id=actor['id'],**BOUNDARY)

    @app.post('/api/guidance/documents')
    def create(body:Document,request:Request,response:Response):
        if body.rights_declared is not True:raise HTTPException(422,'Declare document-use rights before submitting content')
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=actor_for(db,request,True)
            request_hash=sha(canonical(body.model_dump()))
            previous=db.execute('SELECT * FROM approved_guidance_documents WHERE creator_id=? AND request_key=?',(actor['id'],body.request_key)).fetchone()
            if previous:
                if previous['request_hash']!=request_hash:raise HTTPException(409,'Request key reused for different guidance')
                return dict(document=present(previous,actor),created=False,**BOUNDARY)
            if db.execute('SELECT count(*) FROM approved_guidance_documents').fetchone()[0]>=500:raise HTTPException(429,'Guidance capacity reached; review retention before adding documents')
            if body.supersedes:
                old=db.execute('SELECT * FROM approved_guidance_documents WHERE id=?',(body.supersedes,)).fetchone()
                if not old or not can_read(old,actor):raise HTTPException(404,'Previous document revision unavailable')
            identity=secrets.token_hex(16);stamp=now()
            db.execute('INSERT INTO approved_guidance_documents VALUES(?,?,?,?,?,?,?,?,?,?,?,\'draft\',1,NULL,NULL,?,?)',
                (identity,actor['id'],body.request_key,request_hash,body.title,body.source_label,body.content,sha(body.content),canonical(sorted(set(body.permitted_roles))),1,body.supersedes,stamp,stamp))
            db.execute('INSERT INTO approved_guidance_events VALUES(?,1,?,?,?,?)',(identity,actor['id'],'created','Use rights are owner-declared, not independently verified.',stamp))
            audit(db,actor['email'],'guidance_created',identity);response.status_code=201
            return dict(document=present(db.execute('SELECT * FROM approved_guidance_documents WHERE id=?',(identity,)).fetchone(),actor),created=True,**BOUNDARY)

    @app.post('/api/guidance/documents/{identity}/action')
    def decision(identity:str,body:Decision,request:Request):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=actor_for(db,request,True)
            row=db.execute('SELECT * FROM approved_guidance_documents WHERE id=?',(identity,)).fetchone()
            if not row or not can_read(row,actor):raise HTTPException(404,'Guidance unavailable')
            present(row,actor)
            transitions={'submit':('draft','submitted'),'approve':('submitted','approved'),'reject':('submitted','rejected'),'retire':('approved','retired')}
            if row['revision']!=body.expected_revision or row['state']!=transitions[body.action][0]:raise HTTPException(409,'Document state or revision changed')
            if body.action=='submit' and row['creator_id']!=actor['id']:raise HTTPException(403,'Only the creator submits guidance')
            if body.action in ('approve','reject') and (actor['role']!='admin' or row['creator_id']==actor['id']):raise HTTPException(403,'Independent active administrator required')
            if body.action=='retire' and actor['role']!='admin':raise HTTPException(403,'Administrator required to retire guidance')
            import local_notifications
            db.execute('''UPDATE approved_guidance_documents SET state=?,revision=revision+1,updated_at=?,
                reviewer_id=CASE WHEN ?='approve' THEN ? ELSE reviewer_id END,
                reviewer_revision=CASE WHEN ?='approve' THEN ? ELSE reviewer_revision END WHERE id=?''',
                (transitions[body.action][1],now(),body.action,actor['id'],body.action,local_notifications.account_revision(db,actor['id']),identity))
            if body.action=='approve' and row['supersedes']:
                parent=db.execute('SELECT * FROM approved_guidance_documents WHERE id=?',(row['supersedes'],)).fetchone()
                if parent['state']!='approved':raise HTTPException(409,'The superseded source changed; create a draft from its current revision')
                if parent['state']=='approved':
                    db.execute("UPDATE approved_guidance_documents SET state='retired',revision=revision+1,updated_at=? WHERE id=?",(now(),parent['id']))
                    db.execute('INSERT INTO approved_guidance_events VALUES(?,?,?,?,?,?)',(parent['id'],parent['revision']+1,actor['id'],'superseded','Replaced by independently approved document '+identity,now()))
            db.execute('INSERT INTO approved_guidance_events VALUES(?,?,?,?,?,?)',(identity,row['revision']+1,actor['id'],body.action,body.note,now()))
            audit(db,actor['email'],'guidance_'+body.action,identity)
            return dict(document=present(db.execute('SELECT * FROM approved_guidance_documents WHERE id=?',(identity,)).fetchone(),actor),**BOUNDARY)

    @app.post('/api/guidance/search')
    def search(body:Question,request:Request):
        with database() as db:
            db.execute('BEGIN');actor=actor_for(db,request)
            terms={token for token in re.findall(r'\w+',body.question.lower()) if len(token)>2}
            excluded={'the','and','what','how','why','when','are','for','can','should','with','from','this','that'}
            terms-=excluded
            matches=[]
            for row in db.execute("SELECT * FROM approved_guidance_documents WHERE state='approved' ORDER BY id LIMIT 500"):
                if not can_read(row,actor) or not reviewer_active(db,row):continue
                present(row,actor)
                for index,sentence in enumerate(re.split(r'(?<=[.!?])\s+|\n+',row['content'])):
                    words=set(re.findall(r'\w+',sentence.lower()));hits=len(words&terms)
                    if hits:
                        matches.append((hits,row['id'],index,dict(document_id=row['id'],revision=row['revision'],content_sha256=row['content_sha256'],title=row['title'],source_label=row['source_label'],excerpt=sentence[:500],matched_terms=sorted(words&terms))))
            matches.sort(key=lambda item:(-item[0],item[1],item[2]));citations=[item[3] for item in matches[:3]]
            return dict(generated_at=now(),status='source-excerpts' if citations else 'abstained',citations=citations,
                        explanation='Matching approved source excerpts only; no diagnosis or instruction generation.' if citations else 'No matching currently approved source accessible to this account. No answer inferred.',
                        query_retained=False,**BOUNDARY)
