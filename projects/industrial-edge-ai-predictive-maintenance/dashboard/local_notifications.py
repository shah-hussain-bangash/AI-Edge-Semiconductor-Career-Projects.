"""Opt-in, durable local incident notifications. No external transport."""
from datetime import datetime, timezone
import json
import secrets
from typing import Literal

from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from maintenance_requests import READ_ROLES, fresh_actor, require_role

BOUNDARY = dict(scope='local-synthetic-notifications', source_type='synthetic',
                production_ready=False, external_notifications_sent=False,
                equipment_authorized=False, hardware_connected=False)
MAX_RECORDS = 20000


class Preference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(strict=True, ge=0)
    enabled: bool = Field(strict=True)
    severities: list[Literal['info', 'watch', 'critical']] = Field(max_length=3)


def now():
    return datetime.now(timezone.utc).isoformat()


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS local_notification_preferences(
        user_id INTEGER PRIMARY KEY REFERENCES users(id), enabled INTEGER NOT NULL,
        severities_json TEXT NOT NULL, revision INTEGER NOT NULL, account_revision INTEGER NOT NULL,
        updated_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS local_notification_outbox(
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        incident_id TEXT NOT NULL, incident_revision INTEGER NOT NULL,
        preference_revision INTEGER NOT NULL, account_revision INTEGER NOT NULL,
        severity TEXT NOT NULL, action TEXT NOT NULL, title TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending','delivered','suppressed')),
        created_at TEXT NOT NULL, delivered_at TEXT, read_at TEXT,
        UNIQUE(user_id,incident_id,incident_revision),
        FOREIGN KEY(incident_id,incident_revision) REFERENCES synthetic_incident_events(incident_id,revision))''')
    db.execute('CREATE INDEX IF NOT EXISTS local_notification_recipient ON local_notification_outbox(user_id,state,created_at)')


def account_revision(db, user_id):
    return db.execute('SELECT COALESCE((SELECT revision FROM account_controls WHERE user_id=?),1)', (user_id,)).fetchone()[0]


def eligible(db, actor, incident_id):
    import incidents
    disabled = db.execute('SELECT disabled FROM users WHERE id=?', (actor['id'],)).fetchone()
    if disabled and disabled['disabled']: return False
    try:
        incidents.visible(db, incident_id, actor)
        return True
    except HTTPException:
        return False


def preference(db, actor):
    row = db.execute('SELECT * FROM local_notification_preferences WHERE user_id=?', (actor['id'],)).fetchone()
    return dict(enabled=bool(row and row['enabled'] and row['account_revision'] == account_revision(db, actor['id'])),
                severities=json.loads(row['severities_json']) if row else [],
                revision=row['revision'] if row else 0,
                requires_reconfirmation=bool(row and row['account_revision'] != account_revision(db, actor['id'])))


def enqueue(db, incident, severity, action):
    """Same transaction as incident event. Only users who can see that event are routed."""
    # Older isolated consumers may initialize only incidents; production initializes both.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='local_notification_preferences'").fetchone(): return
    candidates = db.execute('''SELECT p.*,u.role,u.email,u.id FROM local_notification_preferences p
        JOIN users u ON u.id=p.user_id WHERE p.enabled=1''').fetchall()
    recipients = [p for p in candidates if p['account_revision'] == account_revision(db,p['id'])
                  and severity in json.loads(p['severities_json']) and eligible(db,p,incident['id'])]
    additions = [p for p in recipients if not db.execute('''SELECT 1 FROM local_notification_outbox
        WHERE user_id=? AND incident_id=? AND incident_revision=?''', (p['id'],incident['id'],incident['revision'])).fetchone()]
    if db.execute('SELECT count(*) FROM local_notification_outbox').fetchone()[0] + len(additions) > MAX_RECORDS:
        raise HTTPException(429,'Local notification capacity reached; incident change was not saved. No records were deleted.')
    for p in additions:
        db.execute('INSERT INTO local_notification_outbox VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
            (secrets.token_hex(16),p['id'],incident['id'],incident['revision'],p['revision'],p['account_revision'],
             severity,action,incident['title'],'pending',now()))


def deliver(db, actor, limit=100):
    if not 1<=limit<=100:raise ValueError('Delivery batch must be between 1 and 100')
    pref = preference(db,actor)
    rows = db.execute("SELECT * FROM local_notification_outbox WHERE user_id=? AND state='pending' ORDER BY created_at,id LIMIT ?", (actor['id'],limit)).fetchall()
    result = dict(delivered=0,suppressed=0)
    for row in rows:
        permitted = (pref['enabled'] and row['preference_revision'] == pref['revision']
                     and row['account_revision'] == account_revision(db,actor['id'])
                     and row['severity'] in pref['severities'] and eligible(db,actor,row['incident_id']))
        state = 'delivered' if permitted else 'suppressed'
        db.execute('UPDATE local_notification_outbox SET state=?,delivered_at=? WHERE id=?',
                   (state, now() if permitted else None,row['id']))
        result[state] += 1
    result['remaining_pending'] = db.execute("SELECT count(*) FROM local_notification_outbox WHERE user_id=? AND state='pending'", (actor['id'],)).fetchone()[0]
    return result


def accessible(db, row, actor):
    return row['user_id'] == actor['id'] and row['account_revision'] == account_revision(db,actor['id']) and eligible(db,actor,row['incident_id'])


def install_routes(app,database,require_user,require_csrf,audit):
    @app.get('/api/local-notifications')
    def inbox(request:Request,response:Response,offset:int=Query(default=0,ge=0,le=MAX_RECORDS),limit:int=Query(default=20,ge=1,le=100)):
        current=require_user(request);response.headers['Cache-Control']='no-store'
        with database() as db:
            db.execute('BEGIN');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            rows=[r for r in db.execute("SELECT * FROM local_notification_outbox WHERE user_id=? AND state='delivered' ORDER BY created_at DESC,id DESC",(actor['id'],)) if accessible(db,r,actor)]
            counts={r['state']:r['n'] for r in db.execute('SELECT state,count(*) n FROM local_notification_outbox WHERE user_id=? GROUP BY state',(actor['id'],))}
            return {**BOUNDARY,'preference':preference(db,actor),'items':[dict(r) for r in rows[offset:offset+limit]],
                    'total':len(rows),'unread':sum(r['read_at'] is None for r in rows),'offset':offset,'limit':limit,
                    'own_outbox_counts':counts,'record_limit':MAX_RECORDS,'delivery_mode':'Manual delivery or opted-in dashboard worker; inspect /api/local-notification-worker for status'}

    @app.post('/api/local-notifications/preference')
    def save(body:Preference,request:Request):
        current=require_user(request);require_csrf(request,current)
        if len(set(body.severities)) != len(body.severities) or body.enabled and not body.severities:
            raise HTTPException(422,'Choose distinct severities; an enabled route needs at least one')
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            previous=preference(db,actor)
            if previous['revision'] != body.expected_revision:raise HTTPException(409,'Notification preference changed; refresh before saving')
            if previous['enabled']==body.enabled and set(previous['severities'])==set(body.severities) and not previous['requires_reconfirmation']:
                return {**BOUNDARY,'preference':previous}
            db.execute("UPDATE local_notification_outbox SET state='suppressed' WHERE user_id=? AND state='pending'",(actor['id'],))
            db.execute('''INSERT INTO local_notification_preferences VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                enabled=excluded.enabled,severities_json=excluded.severities_json,revision=excluded.revision,
                account_revision=excluded.account_revision,updated_at=excluded.updated_at''',
                (actor['id'],body.enabled,json.dumps(sorted(body.severities)),previous['revision']+1,account_revision(db,actor['id']),now()))
            audit(db,actor['email'],'local_notification_preference_saved',str(previous['revision']+1))
            return {**BOUNDARY,'preference':preference(db,actor)}

    @app.post('/api/local-notifications/deliver')
    def dispatch(request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            result=deliver(db,actor)
            if result['delivered'] or result['suppressed']:audit(db,actor['email'],'local_notification_delivery',json.dumps(result,sort_keys=True))
            return {**BOUNDARY,**result}

    @app.post('/api/local-notifications/{identifier}/read')
    def mark_read(identifier:str,request:Request):
        current=require_user(request);require_csrf(request,current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE');actor=fresh_actor(db,current);require_role(actor,READ_ROLES)
            row=db.execute("SELECT * FROM local_notification_outbox WHERE id=? AND state='delivered'",(identifier,)).fetchone()
            if not row or not accessible(db,row,actor):raise HTTPException(404,'Local notification not found')
            if not row['read_at']:
                db.execute('UPDATE local_notification_outbox SET read_at=? WHERE id=?',(now(),identifier))
                audit(db,actor['email'],'local_notification_read',identifier)
            return {**BOUNDARY,'id':identifier,'read':True,'incident_acknowledged':False}
