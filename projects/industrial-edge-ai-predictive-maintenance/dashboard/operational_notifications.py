"""Durable per-user workflow inbox and opt-in TLS SMTP outbox.

No external email is configured or sent by installation. SMTP retries can be
at-least-once; stable Message-ID is not a provider deduplication guarantee.
"""
from datetime import datetime, timezone
from email.message import EmailMessage
import os
import base64
import json
import re
import secrets
import smtplib
import ssl
import time
from fastapi import HTTPException, Request, Response, Query
from pydantic import Field
from maintenance_requests import fresh_actor, require_role, READ_ROLES
from team_accounts import StrictModel, reauthenticate

BOUNDARY=dict(scope='local-workflow-notifications',production_ready=False,
              equipment_authorized=False,external_delivery_requires_configuration=True)


class Configuration(StrictModel):
    enabled:bool=Field(strict=True)
    expected_revision:int=Field(strict=True,ge=0)


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS operational_notifications(
        id TEXT PRIMARY KEY,event_id INTEGER NOT NULL REFERENCES operational_events(id),
        user_id INTEGER NOT NULL REFERENCES users(id),kind TEXT NOT NULL,record_id TEXT NOT NULL,
        source_type TEXT NOT NULL,subject TEXT NOT NULL,read_at TEXT,email_state TEXT NOT NULL,
        attempts INTEGER NOT NULL,next_attempt REAL NOT NULL,lease_id TEXT,lease_until REAL,
        created_at TEXT NOT NULL,delivered_at TEXT,last_error TEXT,
        UNIQUE(event_id,user_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS operational_email_configuration(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),enabled INTEGER NOT NULL,
        revision INTEGER NOT NULL,issuer_id INTEGER NOT NULL REFERENCES users(id),issuer_revision INTEGER NOT NULL,
        reason TEXT NOT NULL,updated_at TEXT NOT NULL)''')


def smtp_settings():
    host=os.environ.get('EDGEOPS_SMTP_HOST','').strip()
    username=os.environ.get('EDGEOPS_SMTP_USERNAME','')
    password=os.environ.get('EDGEOPS_SMTP_PASSWORD','')
    sender=os.environ.get('EDGEOPS_SMTP_FROM','').strip()
    mode=os.environ.get('EDGEOPS_SMTP_TLS','starttls')
    try:port=int(os.environ.get('EDGEOPS_SMTP_PORT','465' if mode=='ssl' else '587'))
    except ValueError:return None
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',host) or not 1<=port<=65535 or mode not in ('ssl','starttls'):return None
    if not re.fullmatch(r'[^\s<>@\r\n]+@[^\s<>@\r\n]+',sender) or not username or not password:return None
    return dict(host=host,port=port,username=username,password=password,sender=sender,mode=mode)


def config(db):
    import local_notifications
    row=db.execute('SELECT * FROM operational_email_configuration WHERE singleton=1').fetchone()
    active=False
    if row:
        user=db.execute('SELECT * FROM users WHERE id=?',(row['issuer_id'],)).fetchone()
        active=bool(user and user['role']=='admin' and not user['disabled'] and local_notifications.account_revision(db,user['id'])==row['issuer_revision'])
    return dict(enabled=bool(row and row['enabled'] and active),revision=row['revision'] if row else 0,
                authority_current=active,provider_configured=smtp_settings() is not None,
                scheduling='Explicit local worker or administrator batch only; no operating-system job installed',
                secrets_location='Process environment only; credentials are never returned',**BOUNDARY)


def eligible(db,user_id,kind,record_id):
    user=db.execute('SELECT * FROM users WHERE id=? AND disabled=0',(user_id,)).fetchone()
    if not user or user['role'] not in READ_ROLES:return None
    table='operational_cases' if kind=='case' else 'operational_orders'
    row=db.execute('SELECT * FROM '+table+' WHERE id=?',(record_id,)).fetchone()
    if not row:return None
    allowed=user['role'] in ('admin','auditor') or (row['assignee_id']==user_id if kind=='case' else user_id in (row['creator_id'],row['technician_id']))
    return user if allowed else None


def enqueue(db,event_id,kind,row,action):
    if kind not in ('case','order'):return
    if db.execute('SELECT count(*) FROM operational_notifications').fetchone()[0]>=20000:raise HTTPException(429,'Notification retention capacity reached; original transaction preserved for retry')
    if kind=='case':
        rule=db.execute('SELECT issuer_id FROM operational_rules WHERE id=?',(row['rule_id'],)).fetchone()
        recipients={rule['issuer_id'],row['assignee_id']}
    else:recipients={row['creator_id'],row['technician_id']}
    for user_id in recipients-{None}:
        if not eligible(db,user_id,kind,row['id']):continue
        if db.execute('SELECT count(*) FROM operational_notifications').fetchone()[0]>=20000:raise HTTPException(429,'Notification retention capacity reached')
        label={'threshold_reobserved':'review reopened after a newer observation','review_note_added':'review note added'}.get(action,action)
        subject='EDGEOPS '+kind+' '+label+' — '+row['source_type']
        email_state='pending' if row['source_type']=='measured-unverified' else 'local-only-fixture'
        db.execute('INSERT INTO operational_notifications VALUES(?,?,?,?,?,?,?,NULL,?,0,0,NULL,NULL,?,NULL,NULL)',
                   (secrets.token_hex(16),event_id,user_id,kind,row['id'],row['source_type'],subject,email_state,datetime.now(timezone.utc).isoformat()))


def send(settings,row,recipient):
    message=EmailMessage();message['Subject']=row['subject'];message['From']=settings['sender'];message['To']=recipient
    message['Message-ID']='<edgeops-'+row['id']+'@'+settings['sender'].rsplit('@',1)[1]+'>'
    message.set_content('A local EDGEOPS workflow record changed.\nRecord: '+row['record_id']+'\nSource: '+row['source_type']+'\nRecorded event: '+row['created_at']+'\nDelivery may be delayed. Open your configured portal and review the current record.\nThis notice is not a diagnosis, verification or authorization to operate equipment.')
    connection=smtplib.SMTP_SSL(settings['host'],settings['port'],timeout=10,context=ssl.create_default_context()) if settings['mode']=='ssl' else smtplib.SMTP(settings['host'],settings['port'],timeout=10)
    with connection as smtp:
        smtp.ehlo()
        if settings['mode']=='starttls':smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
        smtp.login(settings['username'],settings['password'])
        refused=smtp.send_message(message)
        if refused:raise ValueError('Recipient refused')


def deliver(database,limit=5):
    if type(limit) is not int or not 1<=limit<=5:raise ValueError('Use a bounded batch of 1 to 5 messages')
    delivered=failed=cancelled=0
    for _ in range(limit):
        with database() as db:
            db.execute('BEGIN IMMEDIATE');configuration=config(db);settings=smtp_settings()
            if not configuration['enabled'] or not settings:return dict(delivered=delivered,failed=failed,cancelled=cancelled,stop_reason='disabled-or-unconfigured',**BOUNDARY)
            stamp=time.time()
            row=db.execute("SELECT * FROM operational_notifications WHERE email_state='pending' AND next_attempt<=? AND (lease_until IS NULL OR lease_until<?) ORDER BY created_at,id LIMIT 1",(stamp,stamp)).fetchone()
            if not row:break
            user=eligible(db,row['user_id'],row['kind'],row['record_id'])
            if not user:
                db.execute("UPDATE operational_notifications SET email_state='cancelled',last_error='recipient-access-changed' WHERE id=?",(row['id'],));cancelled+=1;continue
            lease=secrets.token_hex(16)
            db.execute('UPDATE operational_notifications SET lease_id=?,lease_until=?,attempts=attempts+1 WHERE id=?',(lease,stamp+120,row['id']))
            row=dict(row);recipient=user['email'];configuration_revision=configuration['revision']
        # Recheck current authority/access after claiming. The SMTP boundary is
        # not transactional with SQLite; a change after this check can race send.
        with database() as db:
            current=config(db);user=eligible(db,row['user_id'],row['kind'],row['record_id'])
            allowed=current['enabled'] and current['revision']==configuration_revision and user and user['email']==recipient
        if not allowed:
            with database() as db:db.execute("UPDATE operational_notifications SET lease_id=NULL,lease_until=NULL,last_error='configuration-or-access-changed' WHERE id=? AND lease_id=?",(row['id'],lease))
            cancelled+=1;continue
        try:send(settings,row,recipient)
        except Exception:
            with database() as db:
                attempts=row['attempts']+1
                db.execute("UPDATE operational_notifications SET email_state=?,next_attempt=?,lease_id=NULL,lease_until=NULL,last_error='smtp-delivery-unconfirmed' WHERE id=? AND lease_id=?",
                           ('blocked' if attempts>=5 else 'pending',time.time()+min(3600,30*2**attempts),row['id'],lease))
            failed+=1
        else:
            with database() as db:db.execute("UPDATE operational_notifications SET email_state='delivered',delivered_at=?,lease_id=NULL,lease_until=NULL,last_error=NULL WHERE id=? AND lease_id=?",(datetime.now(timezone.utc).isoformat(),row['id'],lease))
            delivered+=1
    return dict(delivered=delivered,failed=failed,cancelled=cancelled,stop_reason='bounded-batch-finished',delivery_semantics='At least once; a lost SMTP response can cause duplicate delivery.',**BOUNDARY)


def install_routes(app,database,require_user,require_csrf,matches,audit):
    @app.get('/api/operational/notifications')
    def inbox(request:Request,response:Response,limit:int=Query(default=100,ge=1,le=100),
              unread_only:bool=False,cursor:str|None=Query(default=None,max_length=300)):
        response.headers['Cache-Control']='no-store'
        before=None
        if cursor is not None:
            try:
                decoded=json.loads(base64.b64decode(cursor.encode('ascii'),altchars=b'-_',validate=True))
                if set(decoded)!= {'time','id'} or not isinstance(decoded['time'],str) or len(decoded['time'])>64 or not isinstance(decoded['id'],str) or not re.fullmatch('[a-f0-9]{32}',decoded['id']):raise ValueError()
                stamp=datetime.fromisoformat(decoded['time'])
                if stamp.tzinfo is None or stamp.utcoffset().total_seconds()!=0:raise ValueError()
                before=decoded
            except (ValueError,TypeError,KeyError,UnicodeError):raise HTTPException(422,'Invalid inbox cursor; refresh the first page') from None
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,require_user(request));require_role(actor,READ_ROLES)
            # Filter current access BEFORE the page limit, including missing records.
            scope="""n.user_id=? AND (
                (n.kind='case' AND EXISTS(SELECT 1 FROM operational_cases c WHERE c.id=n.record_id AND (? OR c.assignee_id=?))) OR
                (n.kind='order' AND EXISTS(SELECT 1 FROM operational_orders o WHERE o.id=n.record_id AND (? OR o.creator_id=? OR o.technician_id=?))))"""
            broad=actor['role'] in ('admin','auditor');params=[actor['id'],broad,actor['id'],broad,actor['id'],actor['id']]
            unread=db.execute('SELECT count(*) FROM operational_notifications n WHERE '+scope+' AND n.read_at IS NULL',params).fetchone()[0]
            where=scope+(' AND n.read_at IS NULL' if unread_only else '')
            if before:
                where+=' AND (n.created_at<? OR (n.created_at=? AND n.id<?))';params+=[before['time'],before['time'],before['id']]
            rows=db.execute('SELECT n.* FROM operational_notifications n WHERE '+where+' ORDER BY n.created_at DESC,n.id DESC LIMIT ?',params+[limit+1]).fetchall()
            has_more=len(rows)>limit;rows=rows[:limit]
            items=[{key:row[key] for key in ('id','kind','record_id','source_type','subject','read_at','email_state','attempts','created_at','delivered_at','last_error')} for row in rows]
            next_cursor=base64.urlsafe_b64encode(json.dumps(dict(time=rows[-1]['created_at'],id=rows[-1]['id']),separators=(',',':')).encode()).decode() if has_more else None
            return dict(items=items,unread_count=unread,page=dict(limit=limit,has_more=has_more,next_cursor=next_cursor,unread_only=unread_only),email=config(db),role=actor['role'],**BOUNDARY)

    @app.post('/api/operational/notifications/{identity}/read')
    def read(identity:str,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            row=db.execute('SELECT * FROM operational_notifications WHERE id=? AND user_id=?',(identity,actor['id'])).fetchone()
            if not row or not eligible(db,actor['id'],row['kind'],row['record_id']):raise HTTPException(404,'Notification unavailable')
            db.execute('UPDATE operational_notifications SET read_at=COALESCE(read_at,?) WHERE id=?',(datetime.now(timezone.utc).isoformat(),identity))
            return dict(read=True,case_acknowledged=False,**BOUNDARY)

    @app.post('/api/operational/email/configuration')
    def configure(body:Configuration,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit);previous=config(db)
            if previous['revision']!=body.expected_revision:raise HTTPException(409,'Email configuration changed; refresh')
            if body.enabled and not smtp_settings():raise HTTPException(422,'Configure the private SMTP environment before enabling external delivery')
            import local_notifications
            db.execute('INSERT INTO operational_email_configuration VALUES(1,?,?,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET enabled=excluded.enabled,revision=excluded.revision,issuer_id=excluded.issuer_id,issuer_revision=excluded.issuer_revision,reason=excluded.reason,updated_at=excluded.updated_at',
                       (int(body.enabled),previous['revision']+1,actor['id'],local_notifications.account_revision(db,actor['id']),body.reason,datetime.now(timezone.utc).isoformat()))
            audit(db,actor['email'],'operational_email_configured',str(body.enabled));return config(db)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--once',action='store_true',required=True);parser.parse_args()
    from server import database,DB_PATH
    if not DB_PATH.is_file():raise SystemExit('Configured dashboard database missing; no database or message created.')
    try:print(__import__('json').dumps(deliver(database),sort_keys=True))
    except Exception:raise SystemExit('Delivery unavailable; review configuration and the retained outbox. No credentials printed.')
