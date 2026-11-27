"""Opt-in supervised local delivery; SQLite serializes and leases each bounded pass."""
import json
import secrets
import threading
import time

from fastapi import HTTPException, Request, Response
from pydantic import Field
from maintenance_requests import READ_ROLES, fresh_actor, require_role
from team_accounts import StrictModel, reauthenticate
import local_notifications as inbox
import followup_reminders


class Configure(StrictModel):
    expected_revision: int = Field(strict=True,ge=0)
    enabled: bool = Field(strict=True)
    interval_seconds: int = Field(strict=True,ge=5,le=300)


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS local_notification_worker_config(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),enabled INTEGER NOT NULL,
        revision INTEGER NOT NULL,interval_seconds INTEGER NOT NULL,
        issuer_id INTEGER NOT NULL REFERENCES users(id),issuer_revision INTEGER NOT NULL,
        reason TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS local_notification_worker_status(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),worker_id TEXT NOT NULL,
        lease_until REAL NOT NULL,last_pass REAL NOT NULL,config_revision INTEGER NOT NULL,
        passes INTEGER NOT NULL,delivered INTEGER NOT NULL,suppressed INTEGER NOT NULL,
        last_error TEXT)''')


def authorized(db,row):
    if not row or not row['enabled']:return False
    user=db.execute('SELECT * FROM users WHERE id=?',(row['issuer_id'],)).fetchone()
    return bool(user and not user['disabled'] and user['role']=='admin'
                and row['issuer_revision']==inbox.account_revision(db,user['id']))


def status(db,epoch=None):
    epoch=time.time() if epoch is None else epoch
    config=db.execute('SELECT * FROM local_notification_worker_config').fetchone()
    report=db.execute('SELECT * FROM local_notification_worker_status').fetchone()
    active=authorized(db,config)
    state='disabled' if not config or not config['enabled'] else 'authorization-changed' if not active else 'awaiting-pass'
    if active and report and report['config_revision']==config['revision']:
        state='delivery-error' if report['last_error'] else 'recent-pass' if epoch-report['last_pass']<=max(30,config['interval_seconds']*2) and epoch>=report['last_pass'] else 'pass-stale'
    return {'enabled':bool(config and config['enabled']),'effective_enabled':active,
            'revision':config['revision'] if config else 0,'interval_seconds':config['interval_seconds'] if config else 5,
            'state':state,'last_pass_epoch':report['last_pass'] if report else None,
            'passes':report['passes'] if report else 0,'delivered':report['delivered'] if report else 0,
            'suppressed':report['suppressed'] if report else 0,
            'reason':config['reason'] if config else None,'last_error':report['last_error'] if report else None,
            'batch_limit':100,'scope':'local-synthetic-notification-worker','production_ready':False,
            'external_notifications_sent':False,'scheduler':'Dashboard process only; no installed operating-system service'}


def tick(database,audit,worker_id,epoch=None):
    epoch=time.time() if epoch is None else epoch
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        config=db.execute('SELECT * FROM local_notification_worker_config').fetchone()
        if not authorized(db,config):return 'disabled'
        previous=db.execute('SELECT * FROM local_notification_worker_status').fetchone()
        if previous and previous['worker_id']!=worker_id and previous['lease_until']>epoch:return 'lease-held'
        if previous and previous['config_revision']==config['revision'] and previous['last_pass']+config['interval_seconds']>epoch:return 'not-due'
        reminders=followup_reminders.process(db,epoch,limit=100)
        delivered=reminders['created'];suppressed=reminders['cancelled']
        remaining=100-delivered-suppressed
        recipients=db.execute('''SELECT user_id FROM local_notification_outbox WHERE state='pending'
            GROUP BY user_id ORDER BY min(created_at),user_id LIMIT 100''').fetchall()
        for recipient in recipients:
            if not remaining:break
            actor=db.execute('SELECT * FROM users WHERE id=?',(recipient['user_id'],)).fetchone()
            if not actor:raise RuntimeError('Notification recipient integrity failure')
            result=inbox.deliver(db,actor,limit=remaining)
            delivered+=result['delivered'];suppressed+=result['suppressed']
            remaining-=result['delivered']+result['suppressed']
            if not remaining:break
        db.execute('''INSERT INTO local_notification_worker_status VALUES(1,?,?,?,?,?,?,?,NULL)
            ON CONFLICT(singleton) DO UPDATE SET worker_id=excluded.worker_id,lease_until=excluded.lease_until,
            last_pass=excluded.last_pass,config_revision=excluded.config_revision,passes=excluded.passes,
            delivered=excluded.delivered,suppressed=excluded.suppressed,last_error=NULL''',
            (worker_id,epoch+max(30,config['interval_seconds']*2),epoch,config['revision'],
             (previous['passes'] if previous else 0)+1,(previous['delivered'] if previous else 0)+delivered,
             (previous['suppressed'] if previous else 0)+suppressed))
        if delivered or suppressed:audit(db,'local-notification-worker','local_notification_automatic_delivery',json.dumps({'delivered':delivered,'suppressed':suppressed,'config_revision':config['revision']}))
        return 'completed'


class Worker:
    def __init__(self,database,audit):
        self.database=database;self.audit=audit;self.id=secrets.token_hex(16)
        self.stop_event=threading.Event();self.thread=None

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear();self.thread=threading.Thread(target=self.run,name='local-inbox-delivery',daemon=True);self.thread.start()

    def run(self):
        while not self.stop_event.is_set():
            try:tick(self.database,self.audit,self.id)
            except Exception:
                # A failed transaction rolls back deliveries. Never persist raw exception messages.
                try:
                    with self.database() as db:
                        db.execute('BEGIN IMMEDIATE')
                        config=db.execute('SELECT * FROM local_notification_worker_config').fetchone()
                        previous=db.execute('SELECT * FROM local_notification_worker_status').fetchone()
                        if authorized(db,config) and (not previous or previous['worker_id']==self.id or previous['lease_until']<=time.time()):
                            if previous:db.execute("UPDATE local_notification_worker_status SET worker_id=?,last_error='delivery-pass-failed' WHERE singleton=1",(self.id,))
                            else:db.execute("INSERT INTO local_notification_worker_status VALUES(1,?,0,0,?,0,0,0,'delivery-pass-failed')",(self.id,config['revision']))
                except Exception:pass  # Unavailable storage is represented by a stale heartbeat.
            self.stop_event.wait(1)

    def stop(self):
        self.stop_event.set()
        # Thread.start() can fail after the object is assigned. Joining an
        # unstarted thread would mask that startup failure during cleanup.
        if self.thread and self.thread.ident is not None:self.thread.join(timeout=12)
        if self.thread and self.thread.is_alive():return
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE local_notification_worker_status SET lease_until=0 WHERE worker_id=?',(self.id,))


def install_routes(app,database,require_user,require_csrf,matches,audit):
    @app.get('/api/local-notification-worker')
    def inspect(request:Request,response:Response):
        current=require_user(request);response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            return {**status(db),'can_manage':actor['role']=='admin'}

    @app.post('/api/local-notification-worker')
    def configure(body:Configure,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=reauthenticate(db,current,body.current_password,matches,audit)
            previous=status(db)
            if previous['revision']!=body.expected_revision:raise HTTPException(409,'Worker settings changed; refresh before saving')
            db.execute('''INSERT INTO local_notification_worker_config VALUES(1,?,?,?,?,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET enabled=excluded.enabled,revision=excluded.revision,
                interval_seconds=excluded.interval_seconds,issuer_id=excluded.issuer_id,
                issuer_revision=excluded.issuer_revision,reason=excluded.reason,updated_at=excluded.updated_at''',
                (body.enabled,previous['revision']+1,body.interval_seconds,actor['id'],inbox.account_revision(db,actor['id']),body.reason,inbox.now()))
            db.execute('UPDATE local_notification_worker_status SET lease_until=0')
            audit(db,actor['email'],'local_notification_worker_configured',json.dumps({'enabled':body.enabled,'revision':previous['revision']+1}))
            return status(db)
