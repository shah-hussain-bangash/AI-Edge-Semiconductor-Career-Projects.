"""Bounded private evidence files stored with the database; no inline rendering or safety certification."""
import hashlib
import json
import re
import secrets
from fastapi import HTTPException, Request, Response
from maintenance_requests import fresh_actor, require_role, READ_ROLES, WRITE_ROLES
from operational_workflow import visible, now

MAX_FILE=2*1024*1024
MAX_TOTAL=32*1024*1024
TABLES={'case':'operational_cases','order':'operational_orders'}


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS operational_evidence(
        id TEXT PRIMARY KEY,kind TEXT NOT NULL,record_id TEXT NOT NULL,uploader_id INTEGER NOT NULL REFERENCES users(id),
        filename TEXT NOT NULL,content_type TEXT NOT NULL,payload BLOB NOT NULL,sha256 TEXT NOT NULL,
        byte_count INTEGER NOT NULL,created_at TEXT NOT NULL,scan_state TEXT NOT NULL)''')


def record(db,kind,identifier,actor):
    if kind not in TABLES or not re.fullmatch('[a-f0-9]{32}',identifier):raise HTTPException(404,'Evidence record not found')
    return visible(db,TABLES[kind],identifier,actor)


def validate(filename,media,data):
    if not filename or len(filename)>150 or any(ord(c)<32 or ord(c)==127 or c in '/\\' for c in filename):raise HTTPException(422,'Use a plain filename of at most 150 characters')
    if not 0<len(data)<=MAX_FILE:raise HTTPException(413,'Evidence file must be between 1 byte and 2 MiB')
    if media=='image/png':valid=data.startswith(b'\x89PNG\r\n\x1a\n')
    elif media=='image/jpeg':valid=data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9')
    elif media=='application/pdf':valid=data.startswith(b'%PDF-')
    elif media in ('text/plain','text/csv','application/json'):
        try:
            text=data.decode('utf-8');valid=not any(ord(c)<32 and c not in '\r\n\t' for c in text)
            if media=='application/json':json.loads(text,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        except (UnicodeError,ValueError,RecursionError):valid=False
    else:raise HTTPException(415,'Use UTF-8 text, CSV, JSON, PNG, JPEG or PDF')
    if not valid:raise HTTPException(422,'File does not match the declared supported format')


def metadata(row):return {key:row[key] for key in ('id','kind','record_id','uploader_id','filename','content_type','sha256','byte_count','created_at','scan_state')}


def install_routes(app,database,require_user,require_csrf,audit):
    @app.get('/api/operational/evidence/{kind}/{identifier}')
    def listing(kind:str,identifier:str,request:Request):
        current=require_user(request)
        with database() as db:
            actor=fresh_actor(db,current);require_role(actor,READ_ROLES);record(db,kind,identifier,actor)
            rows=db.execute('SELECT * FROM operational_evidence WHERE kind=? AND record_id=? ORDER BY created_at,id',(kind,identifier)).fetchall()
            return dict(files=[metadata(row) for row in rows],malware_scanned=False,production_ready=False)

    @app.post('/api/operational/evidence/{kind}/{identifier}',status_code=201)
    async def upload(kind:str,identifier:str,request:Request):
        current=require_user(request);require_csrf(request,current)
        filename=request.query_params.get('filename','');media=request.headers.get('content-type','').split(';')[0].lower()
        data=await request.body();validate(filename,media,data)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            actor=fresh_actor(db,current);require_role(actor,WRITE_ROLES);row=record(db,kind,identifier,actor)
            if row['state'] in ('resolved','rejected','verification-pending','closed'):raise HTTPException(409,'Evidence is frozen at this review stage')
            digest=hashlib.sha256(data).hexdigest()
            existing=db.execute('SELECT * FROM operational_evidence WHERE kind=? AND record_id=? AND sha256=? AND filename=? AND content_type=?',(kind,identifier,digest,filename,media)).fetchone()
            if existing:return dict(file=metadata(existing),duplicate=True,malware_scanned=False)
            count,total=db.execute('SELECT count(*),coalesce(sum(byte_count),0) FROM operational_evidence').fetchone()
            if count>=256 or total+len(data)>MAX_TOTAL:raise HTTPException(429,'Private evidence capacity reached; preserve and review retention before adding files')
            identity=secrets.token_hex(16)
            db.execute('INSERT INTO operational_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)',(identity,kind,identifier,actor['id'],filename,media,data,digest,len(data),now(),'not-scanned'))
            audit(db,actor['email'],'operational_evidence_uploaded',identity)
            saved=db.execute('SELECT * FROM operational_evidence WHERE id=?',(identity,)).fetchone()
            return dict(file=metadata(saved),duplicate=False,malware_scanned=False)

    @app.get('/api/operational/evidence/files/{identifier}/download')
    def download(identifier:str,request:Request):
        current=require_user(request)
        with database() as db:
            actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            row=db.execute('SELECT * FROM operational_evidence WHERE id=?',(identifier,)).fetchone()
            if not row:raise HTTPException(404,'Evidence file not found')
            record(db,row['kind'],row['record_id'],actor)
            if hashlib.sha256(row['payload']).hexdigest()!=row['sha256']:raise HTTPException(503,'Evidence integrity check failed')
            return Response(bytes(row['payload']),media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="evidence-'+row['id']+'.bin"','X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})
