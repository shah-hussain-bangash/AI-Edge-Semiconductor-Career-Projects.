"""Authenticated runner reports, not process inspection or hardware liveness."""
from datetime import datetime, timezone
import time

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from service_credentials import authenticate, status, require_service_transport
from maintenance_requests import fresh_actor, require_role, READ_ROLES

BOUNDARY = {'scope': 'local-synthetic-runner-status', 'production_ready': False,
            'hardware_connected': False, 'broker_connected': False}


class Heartbeat(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(strict=True, pattern=r'^[0-9a-f]{32}$')
    sequence: int = Field(strict=True, ge=0, le=2147483647)
    state: Literal['running', 'stopped']
    interval_seconds: int = Field(strict=True, ge=1, le=300)
    passes: int = Field(strict=True, ge=0, le=2147483647)
    attempts: int = Field(strict=True, ge=0, le=2147483647)
    pass_errors: int = Field(strict=True, ge=0, le=2147483647)
    last_outcome: Literal['not-attempted', 'idle', 'delivered', 'pending', 'blocked',
                          'inflight', 'pass-error', 'heartbeat-unavailable']


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS service_runner_reports(
        credential_id TEXT PRIMARY KEY REFERENCES service_credentials(id),
        run_id TEXT NOT NULL, sequence INTEGER NOT NULL, state TEXT NOT NULL,
        interval_seconds INTEGER NOT NULL, passes INTEGER NOT NULL,
        attempts INTEGER NOT NULL, pass_errors INTEGER NOT NULL,
        last_outcome TEXT NOT NULL, received_at INTEGER NOT NULL, lease_until INTEGER NOT NULL)''')


def utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def install_routes(app, database, require_user, audit):
    @app.post('/api/edge/heartbeat')
    def heartbeat(body: Heartbeat, request: Request, response: Response):
        require_service_transport(request)
        if body.attempts > body.passes or body.pass_errors > body.passes:
            raise HTTPException(422, 'Runner counters are inconsistent')
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            credential = authenticate(db, request)
            prior = db.execute('SELECT * FROM service_runner_reports WHERE credential_id=?',
                               (credential['id'],)).fetchone()
            now = int(time.time())
            if prior:
                if prior['run_id'] == body.run_id:
                    if body.sequence == prior['sequence'] and all(getattr(body, key) == prior[key] for key in (
                            'state','interval_seconds','passes','attempts','pass_errors','last_outcome')):
                        response.headers['Cache-Control'] = 'no-store'
                        return {**BOUNDARY, 'report_received_at': utc(prior['received_at']),
                                'report_lease_until': utc(prior['lease_until']),
                                'run_id': body.run_id, 'sequence': body.sequence}
                    if prior['state'] == 'stopped' or body.sequence <= prior['sequence']:
                        raise HTTPException(409, 'Runner report is stopped, stale or replayed')
                    if any(getattr(body, key) < prior[key] for key in ('passes', 'attempts', 'pass_errors')):
                        raise HTTPException(409, 'Runner counters cannot move backwards within a run')
                elif prior['state'] != 'stopped' and prior['lease_until'] > now:
                    raise HTTPException(409, 'Another runner still holds this credential report lease')
            if (not prior or prior['run_id'] != body.run_id) and (body.state != 'running' or body.sequence != 0):
                raise HTTPException(409, 'A new run must start with running sequence zero')
            lease_until = now if body.state == 'stopped' else now + max(30, body.interval_seconds*3+15)
            db.execute('''INSERT INTO service_runner_reports VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(credential_id) DO UPDATE SET run_id=excluded.run_id,
                sequence=excluded.sequence,state=excluded.state,interval_seconds=excluded.interval_seconds,
                passes=excluded.passes,attempts=excluded.attempts,pass_errors=excluded.pass_errors,
                last_outcome=excluded.last_outcome,received_at=excluded.received_at,lease_until=excluded.lease_until''',
                (credential['id'], body.run_id, body.sequence, body.state, body.interval_seconds,
                 body.passes, body.attempts, body.pass_errors, body.last_outcome, now, lease_until))
            if not prior or prior['run_id'] != body.run_id or body.state == 'stopped':
                audit(db, 'service:'+credential['id'], 'service_runner_'+body.state, body.run_id)
        response.headers['Cache-Control'] = 'no-store'
        return {**BOUNDARY, 'report_received_at': utc(now), 'report_lease_until': utc(lease_until),
                'run_id': body.run_id, 'sequence': body.sequence}

    @app.get('/api/service-runners')
    def reports(request: Request, response: Response):
        current = require_user(request)
        with database() as db:
            db.execute('BEGIN')
            require_role(fresh_actor(db, current), READ_ROLES)
            rows = db.execute('''SELECT r.*,c.label,c.device_id,c.site_id,c.asset_id
                FROM service_runner_reports r JOIN service_credentials c ON c.id=r.credential_id
                ORDER BY r.received_at DESC,r.credential_id LIMIT 100''').fetchall()
            now = int(time.time());result = []
            for row in rows:
                credential = db.execute('SELECT * FROM service_credentials WHERE id=?', (row['credential_id'],)).fetchone()
                credential_status = status(db, credential)
                observed = ('credential-inactive' if credential_status != 'active' else
                            'reported-stopped' if row['state'] == 'stopped' else
                            'heartbeat-stale' if row['lease_until'] <= now else 'recent-heartbeat')
                result.append({**{k: row[k] for k in ('credential_id','label','device_id','site_id','asset_id',
                    'run_id','sequence','state','interval_seconds','passes','attempts','pass_errors','last_outcome')},
                    'credential_status': credential_status, 'observation': observed,
                    'received_at': utc(row['received_at']), 'report_lease_until': utc(row['lease_until'])})
        response.headers['Cache-Control'] = 'no-store'
        return {**BOUNDARY, 'observed_at': utc(now), 'runners': result,
                'counter_source': 'Runner-declared counters; not independently measured process or equipment state'}
