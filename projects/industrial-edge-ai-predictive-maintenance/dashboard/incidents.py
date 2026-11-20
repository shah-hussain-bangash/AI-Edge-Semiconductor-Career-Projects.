"""Saved synthetic incident exercises; no live detection, escalation or equipment effects."""
from datetime import datetime, timezone
import hashlib
import json
import secrets
from typing import Literal

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from maintenance_requests import ASSETS, READ_ROLES, WRITE_ROLES, fresh_actor, require_role

BOUNDARY = {'scope': 'local-synthetic-incidents', 'source_type': 'synthetic',
            'hardware_connected': False, 'equipment_authorized': False, 'production_ready': False,
            'automatic_detection': False, 'external_notifications_sent': False}
STATES = ('open', 'acknowledged', 'resolved')
TRANSITIONS = {'acknowledge': ('open', 'acknowledged'), 'resolve': ('acknowledged', 'resolved'),
               'reopen': ('resolved', 'open')}
MAX_INCIDENTS, MAX_REVISIONS = 1000, 200


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class CreateIncident(StrictModel):
    request_key: str = Field(pattern=r'^[0-9a-f]{32}$', strict=True)
    source_type: Literal['synthetic']
    asset_id: str = Field(strict=True)
    title: str = Field(min_length=5, max_length=120, strict=True)
    observation: str = Field(min_length=10, max_length=2000, strict=True)
    severity: Literal['info', 'watch', 'critical']
    evidence_refs: str = Field(default='', max_length=1000, strict=True)

    @field_validator('asset_id')
    @classmethod
    def known_asset(cls, value):
        if value not in ASSETS: raise ValueError('Select a synthetic workspace asset')
        return value


class IncidentAction(StrictModel):
    expected_revision: int = Field(strict=True, ge=1)
    action: Literal['acknowledge', 'resolve', 'reopen']
    note: str = Field(min_length=10, max_length=800, strict=True)
    evidence_refs: str = Field(default='', max_length=1000, strict=True)


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS synthetic_incidents(
        id TEXT PRIMARY KEY, creator_id INTEGER NOT NULL REFERENCES users(id), creator_email TEXT NOT NULL,
        request_key TEXT NOT NULL, creation_hash TEXT NOT NULL, asset_id TEXT NOT NULL,
        title TEXT NOT NULL, observation TEXT NOT NULL, severity TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('open','acknowledged','resolved')), revision INTEGER NOT NULL,
        evidence_refs TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(creator_id,request_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS synthetic_incident_events(
        incident_id TEXT NOT NULL REFERENCES synthetic_incidents(id), revision INTEGER NOT NULL,
        action TEXT NOT NULL, actor_id INTEGER NOT NULL REFERENCES users(id), actor_email TEXT NOT NULL,
        note TEXT NOT NULL, evidence_refs TEXT NOT NULL, time_utc TEXT NOT NULL, snapshot_json TEXT NOT NULL,
        PRIMARY KEY(incident_id,revision))''')
    db.execute('CREATE INDEX IF NOT EXISTS incident_creator_state ON synthetic_incidents(creator_id,state,updated_at)')


def present(row, actor):
    data = {key: value for key, value in dict(row).items() if key not in ('request_key','creation_hash','creator_id')}
    writable = actor['role'] in WRITE_ROLES and (actor['role'] == 'admin' or row['creator_id'] == actor['id'])
    data['actions'] = [action for action, (start, _) in TRANSITIONS.items()
                       if writable and row['state'] == start and row['revision'] < MAX_REVISIONS]
    return data


def visible(db, incident_id, actor):
    require_role(actor, READ_ROLES)
    row = db.execute('SELECT * FROM synthetic_incidents WHERE id=?', (incident_id,)).fetchone()
    if not row or actor['role'] == 'operator' and row['creator_id'] != actor['id']:
        raise HTTPException(404, 'Incident exercise not found')
    return row


def detail(db, row, actor):
    events = db.execute('''SELECT revision,action,actor_email,note,evidence_refs,time_utc
        FROM synthetic_incident_events WHERE incident_id=? ORDER BY revision DESC LIMIT ?''',
                        (row['id'], MAX_REVISIONS)).fetchall()
    return {'incident': present(row, actor), 'history': [dict(event) for event in events], **BOUNDARY}


def event(db, row, actor, action, note, evidence, audit):
    snapshot = present(row, actor); snapshot.pop('actions')
    db.execute('INSERT INTO synthetic_incident_events VALUES(?,?,?,?,?,?,?,?,?)',
               (row['id'], row['revision'], action, actor['id'], actor['email'], note, evidence,
                row['updated_at'], json.dumps(snapshot, sort_keys=True)))
    audit(db, actor['email'], 'synthetic_incident_' + action,
          json.dumps({'incident_id': row['id'], 'revision': row['revision'], 'scope': BOUNDARY['scope']}))


def install_routes(app, database, require_user, require_csrf, audit):
    @app.get('/api/incidents')
    def list_incidents(request: Request, state: str = 'all', q: str = Query(default='', max_length=160),
                       offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=50)):
        actor = require_user(request); require_role(actor, READ_ROLES)
        if state not in ('all', *STATES): raise HTTPException(422, 'Unknown incident state')
        scope, args = ('creator_id=?', [actor['id']]) if actor['role'] == 'operator' else ('1=1', [])
        where, values = scope, list(args)
        if state != 'all': where += ' AND state=?'; values.append(state)
        if q.strip():
            query = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            where += " AND (title LIKE ? ESCAPE '\\' OR asset_id LIKE ? ESCAPE '\\')"; values += [query, query]
        with database() as db:
            db.execute('BEGIN')
            counts = {name: 0 for name in STATES}
            for row in db.execute('SELECT state,count(*) n FROM synthetic_incidents WHERE ' + scope + ' GROUP BY state', args): counts[row['state']] = row['n']
            total = db.execute('SELECT count(*) FROM synthetic_incidents WHERE ' + where, values).fetchone()[0]
            rows = db.execute('SELECT * FROM synthetic_incidents WHERE ' + where + ' ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?', [*values, limit, offset]).fetchall()
        return {'incidents': [present(row, actor) for row in rows], 'counts': counts, 'total': total,
                'offset': offset, 'limit': limit, 'can_create': actor['role'] in WRITE_ROLES,
                'visibility': 'own records' if actor['role'] == 'operator' else 'all local records', **BOUNDARY}

    @app.get('/api/incidents/{incident_id}')
    def get_incident(incident_id: str, request: Request):
        actor = require_user(request)
        with database() as db:
            db.execute('BEGIN')
            return detail(db, visible(db, incident_id, actor), actor)

    @app.post('/api/incidents')
    def create_incident(body: CreateIncident, request: Request):
        current = require_user(request); require_csrf(request, current)
        payload = body.model_dump(exclude={'request_key'})
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            actor = fresh_actor(db, current); require_role(actor, WRITE_ROLES)
            prior = db.execute('SELECT * FROM synthetic_incidents WHERE creator_id=? AND request_key=?', (actor['id'], body.request_key)).fetchone()
            if prior:
                if prior['creation_hash'] != digest: raise HTTPException(409, 'Save key conflicts with another incident; reload before creating a new exercise')
                return {**detail(db, prior, actor), 'created': False}
            if db.execute('SELECT count(*) FROM synthetic_incidents').fetchone()[0] >= MAX_INCIDENTS:
                raise HTTPException(409, 'Local exercise capacity reached; no records are automatically deleted')
            now = datetime.now(timezone.utc).isoformat(); identifier = secrets.token_hex(16)
            db.execute('''INSERT INTO synthetic_incidents VALUES(?,?,?,?,?,?,?,?,?,'open',1,?,?,?)''',
                       (identifier, actor['id'], actor['email'], body.request_key, digest, body.asset_id,
                        body.title, body.observation, body.severity, body.evidence_refs, now, now))
            row = visible(db, identifier, actor)
            event(db, row, actor, 'create', body.observation, body.evidence_refs, audit)
            return {**detail(db, row, actor), 'created': True}

    @app.post('/api/incidents/{incident_id}/actions')
    def act(incident_id: str, body: IncidentAction, request: Request):
        current = require_user(request); require_csrf(request, current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            actor = fresh_actor(db, current); require_role(actor, WRITE_ROLES)
            row = visible(db, incident_id, actor)
            if row['revision'] != body.expected_revision: raise HTTPException(409, 'Incident changed; reload the current record before acting')
            if row['revision'] >= MAX_REVISIONS: raise HTTPException(409, 'Exercise history capacity reached; records remain retained')
            start, target = TRANSITIONS[body.action]
            if row['state'] != start: raise HTTPException(409, 'Action is not valid for the current incident state')
            if body.action == 'resolve' and not body.evidence_refs:
                raise HTTPException(422, 'Resolution requires a synthetic evidence reference; references are recorded, not independently verified')
            now = datetime.now(timezone.utc).isoformat()
            db.execute('UPDATE synthetic_incidents SET state=?,revision=revision+1,updated_at=? WHERE id=?', (target, now, incident_id))
            row = visible(db, incident_id, actor)
            event(db, row, actor, body.action, body.note, body.evidence_refs, audit)
            return detail(db, row, actor)
