"""One local reminder per opted-in recipient and saved incident follow-up generation."""
from datetime import datetime, timezone
import hashlib
import json
import secrets

from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from maintenance_requests import READ_ROLES, fresh_actor, require_role
import local_notifications as inbox
import incidents

MAX_RECORDS=10000
BOUNDARY=dict(scope='local-synthetic-followup-reminders',production_ready=False,
              external_notifications_sent=False,source_type='synthetic',equipment_authorized=False)


class Preference(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:int=Field(strict=True,ge=0)
    enabled:bool=Field(strict=True)


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS followup_reminder_preferences(
        user_id INTEGER PRIMARY KEY REFERENCES users(id),enabled INTEGER NOT NULL,
        revision INTEGER NOT NULL,account_revision INTEGER NOT NULL,updated_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS followup_reminders(
        id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
        incident_id TEXT NOT NULL REFERENCES synthetic_incidents(id),schedule_key TEXT NOT NULL,
        due_at TEXT NOT NULL,schedule_updated_at TEXT NOT NULL,incident_revision INTEGER NOT NULL,
        preference_revision INTEGER NOT NULL,subscription_revision INTEGER NOT NULL,
        account_revision INTEGER NOT NULL,title TEXT NOT NULL,severity TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('delivered','cancelled')),delivered_at TEXT NOT NULL,read_at TEXT,
        UNIQUE(user_id,incident_id,schedule_key))''')
    db.execute('CREATE INDEX IF NOT EXISTS followup_reminder_recipient ON followup_reminders(user_id,state)')
    db.execute('CREATE INDEX IF NOT EXISTS followup_reminder_schedule ON followup_reminders(user_id,incident_id,schedule_updated_at,due_at)')


def preference(db,actor):
    row=db.execute('SELECT * FROM followup_reminder_preferences WHERE user_id=?',(actor['id'],)).fetchone()
    return dict(enabled=bool(row and row['enabled'] and row['account_revision']==inbox.account_revision(db,actor['id'])),
        revision=row['revision'] if row else 0,requires_reconfirmation=bool(row and row['account_revision']!=inbox.account_revision(db,actor['id'])))


def schedule_key(incident_id,due_at,updated_at):
    return hashlib.sha256(json.dumps([incident_id,due_at,updated_at],separators=(',',':')).encode()).hexdigest()


def actionable(db,row,actor,epoch):
    if row['user_id']!=actor['id'] or row['state']!='delivered':return False
    own=preference(db,actor);subscription=inbox.preference(db,actor)
    if (not own['enabled'] or not subscription['enabled'] or own['revision']!=row['preference_revision']
        or subscription['revision']!=row['subscription_revision'] or row['account_revision']!=inbox.account_revision(db,actor['id'])
        or not inbox.eligible(db,actor,row['incident_id'])):return False
    current=db.execute('''SELECT i.state,f.due_at,f.updated_at FROM synthetic_incidents i
        JOIN incident_followups f ON f.incident_id=i.id WHERE i.id=?''',(row['incident_id'],)).fetchone()
    return bool(current and current['state']!='resolved' and current['due_at']
        and schedule_key(row['incident_id'],current['due_at'],current['updated_at'])==row['schedule_key']
        and datetime.fromisoformat(current['due_at']).timestamp()<=epoch
        and incidents.current_severity(db,row['incident_id']) in subscription['severities'])


def process(db,epoch,limit=100):
    """Caller owns worker lease and write transaction; cancellation and delivery share its budget."""
    if not 0<=limit<=100:raise ValueError('Reminder budget must be between zero and 100')
    created=cancelled=0
    if not limit:return dict(created=0,cancelled=0)
    for row in db.execute("SELECT * FROM followup_reminders WHERE state='delivered' ORDER BY delivered_at,id").fetchall():
        actor=db.execute('SELECT * FROM users WHERE id=?',(row['user_id'],)).fetchone()
        if not actor or not actionable(db,row,actor,epoch):
            db.execute("UPDATE followup_reminders SET state='cancelled' WHERE id=?",(row['id'],));cancelled+=1
            if cancelled==limit:return dict(created=0,cancelled=cancelled)
    retained=db.execute('SELECT count(*) FROM followup_reminders').fetchone()[0]
    if retained>=MAX_RECORDS:return dict(created=0,cancelled=cancelled)
    candidates=db.execute('''SELECT i.*,f.due_at,f.updated_at schedule_updated_at,
        p.user_id recipient_id FROM synthetic_incidents i JOIN incident_followups f ON f.incident_id=i.id
        LEFT JOIN incident_triage t ON t.incident_id=i.id
        CROSS JOIN followup_reminder_preferences p JOIN users u ON u.id=p.user_id
        JOIN local_notification_preferences n ON n.user_id=u.id
        LEFT JOIN account_controls acontrol ON acontrol.user_id=u.id
        WHERE i.state!='resolved' AND f.due_at IS NOT NULL AND p.enabled=1 AND n.enabled=1 AND u.disabled=0
        AND f.due_at<=? AND p.account_revision=COALESCE(acontrol.revision,1) AND n.account_revision=COALESCE(acontrol.revision,1)
        AND instr(n.severities_json,'"'||COALESCE(t.severity,i.severity)||'"')>0
        AND NOT EXISTS(SELECT 1 FROM followup_reminders r WHERE r.user_id=p.user_id AND r.incident_id=i.id
            AND r.schedule_updated_at=f.updated_at AND r.due_at=f.due_at)
        AND u.role IN ('admin','operator','auditor') AND (u.role!='operator' OR i.creator_id=u.id OR
            EXISTS(SELECT 1 FROM incident_assignments a WHERE a.incident_id=i.id AND a.assignee_id=u.id))
        ORDER BY f.due_at,i.id,p.user_id''',(datetime.fromtimestamp(epoch,timezone.utc).isoformat(timespec='microseconds'),))
    for candidate in candidates:
        if datetime.fromisoformat(candidate['due_at']).timestamp()>epoch:continue
        actor=db.execute('SELECT * FROM users WHERE id=?',(candidate['recipient_id'],)).fetchone()
        own=preference(db,actor);subscription=inbox.preference(db,actor)
        severity=incidents.current_severity(db,candidate['id'])
        if not own['enabled'] or not subscription['enabled'] or severity not in subscription['severities']:continue
        key=schedule_key(candidate['id'],candidate['due_at'],candidate['schedule_updated_at'])
        if db.execute('SELECT 1 FROM followup_reminders WHERE user_id=? AND incident_id=? AND schedule_key=?',(actor['id'],candidate['id'],key)).fetchone():continue
        db.execute('INSERT INTO followup_reminders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)',
            (secrets.token_hex(16),actor['id'],candidate['id'],key,candidate['due_at'],candidate['schedule_updated_at'],candidate['revision'],
             own['revision'],subscription['revision'],inbox.account_revision(db,actor['id']),candidate['title'],severity,'delivered',datetime.fromtimestamp(epoch,timezone.utc).isoformat()))
        created+=1
        if created+cancelled==limit or retained+created>=MAX_RECORDS:break
    return dict(created=created,cancelled=cancelled)


def install_routes(app,database,require_user,require_csrf,audit):
    @app.get('/api/follow-up-reminders')
    def inspect(request:Request,response:Response,offset:int=Query(default=0,ge=0,le=MAX_RECORDS),limit:int=Query(default=20,ge=1,le=100)):
        current=require_user(request);response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            epoch=datetime.now(timezone.utc).timestamp()
            rows=[dict(row) for row in db.execute("SELECT * FROM followup_reminders WHERE user_id=? AND state='delivered' ORDER BY delivered_at DESC,id DESC",(actor['id'],)) if actionable(db,row,actor,epoch)]
            import notification_worker
            return {**BOUNDARY,'preference':preference(db,actor),'subscription':inbox.preference(db,actor),
                'items':rows[offset:offset+limit],'total':len(rows),'unread':sum(row['read_at'] is None for row in rows),
                'offset':offset,'limit':limit,'worker':notification_worker.status(db),
                'capacity_reached':db.execute('SELECT count(*) FROM followup_reminders').fetchone()[0]>=MAX_RECORDS,
                'record_limit':MAX_RECORDS,'clock_source':'local-service-clock',
                'policy':'One reminder per recipient and saved due-date generation; no repeat after reopen or resubscribe'}

    @app.post('/api/follow-up-reminders/preference')
    def save(body:Preference,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            previous=preference(db,actor)
            if body.expected_revision!=previous['revision']:raise HTTPException(409,'Reminder preference changed; refresh before saving')
            if previous['enabled']==body.enabled and not previous['requires_reconfirmation']:return {**BOUNDARY,'preference':previous}
            if body.enabled and not inbox.preference(db,actor)['enabled']:raise HTTPException(409,'Enable your incident notification subscription and select severities first')
            db.execute("UPDATE followup_reminders SET state='cancelled' WHERE user_id=? AND state='delivered'",(actor['id'],))
            db.execute('''INSERT INTO followup_reminder_preferences VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                enabled=excluded.enabled,revision=excluded.revision,account_revision=excluded.account_revision,updated_at=excluded.updated_at''',
                (actor['id'],body.enabled,previous['revision']+1,inbox.account_revision(db,actor['id']),inbox.now()))
            audit(db,actor['email'],'followup_reminder_preference',json.dumps({'enabled':body.enabled,'revision':previous['revision']+1}))
            return {**BOUNDARY,'preference':preference(db,actor)}

    @app.post('/api/follow-up-reminders/{identifier}/read')
    def read(identifier:str,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            row=db.execute('SELECT * FROM followup_reminders WHERE id=?',(identifier,)).fetchone()
            if not row or not actionable(db,row,actor,datetime.now(timezone.utc).timestamp()):raise HTTPException(404,'Current follow-up reminder not found')
            if not row['read_at']:
                db.execute('UPDATE followup_reminders SET read_at=? WHERE id=?',(inbox.now(),identifier))
                audit(db,actor['email'],'followup_reminder_read',identifier)
            return {**BOUNDARY,'id':identifier,'read':True,'incident_acknowledged':False,'due_date_changed':False}
