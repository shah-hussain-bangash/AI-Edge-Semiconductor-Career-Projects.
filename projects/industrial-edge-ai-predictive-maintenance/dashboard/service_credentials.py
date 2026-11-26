"""Scoped, expiring service credentials for local synthetic ingestion only."""
import hashlib
import re
import secrets
import time

from fastapi import HTTPException, Request, Response
from pydantic import Field
from acquisition_registry import DeliveryInput, Identifier
from delivery_service import matching_binding, commit_in_transaction
from maintenance_requests import fresh_actor, require_role
from team_accounts import StrictModel, reauthenticate

BOUNDARY = {'scope': 'local-synthetic-service-identity', 'production_ready': False,
            'hardware_connected': False, 'equipment_authorized': False,
            'measured_ingest_enabled': False, 'broker_connected': False}
MAX_CREDENTIALS = 100
PREFIX = 'edgeops_svc_'


class Issue(StrictModel):
    label: str = Field(strict=True, min_length=1, max_length=80, pattern=r'^\S(?:[^\r\n]{0,78}\S)?$')
    device_id: Identifier
    expected_binding_revision: int = Field(strict=True, ge=1)
    lifetime_minutes: int = Field(strict=True, ge=1, le=1440)


class Revoke(StrictModel):
    expected_revision: int = Field(strict=True, ge=1)


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS service_credentials(
        id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, label TEXT NOT NULL,
        issuer_id INTEGER NOT NULL REFERENCES users(id), issuer_revision INTEGER NOT NULL,
        device_id TEXT NOT NULL REFERENCES acquisition_bindings(device_id),
        site_id TEXT NOT NULL, asset_id TEXT NOT NULL, binding_revision INTEGER NOT NULL,
        created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        revoked_at INTEGER, revision INTEGER NOT NULL, last_used_at INTEGER)''')


def status(db, row):
    if row['revoked_at'] is not None:
        return 'revoked'
    if row['expires_at'] <= int(time.time()):
        return 'expired'
    issuer = db.execute('''SELECT u.disabled,u.role,COALESCE(c.revision,1) revision
        FROM users u LEFT JOIN account_controls c ON c.user_id=u.id WHERE u.id=?''',
        (row['issuer_id'],)).fetchone()
    if not issuer or issuer['disabled'] or issuer['role'] != 'admin' or issuer['revision'] != row['issuer_revision']:
        return 'issuer-changed'
    binding = db.execute('SELECT * FROM acquisition_bindings WHERE device_id=?', (row['device_id'],)).fetchone()
    if (not binding or binding['status'] != 'active' or
            any(binding[k] != row[k] for k in ('site_id', 'asset_id')) or
            binding['revision'] != row['binding_revision']):
        return 'binding-changed'
    return 'active'


def present(db, row):
    data = {key: row[key] for key in ('id', 'label', 'device_id', 'site_id', 'asset_id',
        'binding_revision', 'revision', 'created_at', 'expires_at', 'revoked_at', 'last_used_at')}
    data['status'] = status(db, row)
    data['permission'] = 'synthetic-observation:ingest'
    data['diagnostics_permission'] = 'synthetic-runner:heartbeat'
    data['mqtt_diagnostics_permission'] = 'synthetic-mqtt-ingress:heartbeat'
    return data


def authenticate(db, request):
    headers = request.headers.getlist('authorization')
    if len(headers) != 1 or not re.fullmatch(r'Bearer edgeops_svc_[0-9a-f]{64}', headers[0]):
        raise HTTPException(401, 'Service credential required')
    digest = hashlib.sha256(headers[0][7:].encode()).hexdigest()
    row = db.execute('SELECT * FROM service_credentials WHERE token_hash=?', (digest,)).fetchone()
    if not row or status(db, row) != 'active':
        raise HTTPException(401, 'Service credential unavailable or inactive')
    return row


def require_service_transport(request):
    if request.url.scheme != 'https' and (not request.client or request.client.host not in ('127.0.0.1', '::1')):
        raise HTTPException(403, 'Service credentials require HTTPS or a loopback development connection')


def install_routes(app, database, require_user, require_csrf, matches, audit):
    @app.get('/api/service-credentials')
    def listing(request: Request, response: Response):
        current = require_user(request)
        with database() as db:
            db.execute('BEGIN')
            require_role(fresh_actor(db, current), ('admin',))
            rows = db.execute('SELECT * FROM service_credentials ORDER BY created_at DESC,id LIMIT ?',
                              (MAX_CREDENTIALS,)).fetchall()
            response.headers['Cache-Control'] = 'no-store'
            return {**BOUNDARY, 'credentials': [present(db, row) for row in rows],
                    'retained_limit': MAX_CREDENTIALS}

    @app.post('/api/service-credentials')
    def issue(body: Issue, request: Request, response: Response):
        current = require_user(request)
        require_csrf(request, current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            actor = reauthenticate(db, current, body.current_password, matches, audit)
            binding = db.execute('SELECT * FROM acquisition_bindings WHERE device_id=?',
                                 (body.device_id,)).fetchone()
            if not binding or binding['status'] != 'active' or binding['revision'] != body.expected_binding_revision:
                raise HTTPException(409, 'Reload an active exact test binding before issuing a credential')
            if db.execute('SELECT count(*) FROM service_credentials').fetchone()[0] >= MAX_CREDENTIALS:
                raise HTTPException(429, 'Retained service credential capacity reached')
            revision = db.execute('SELECT COALESCE((SELECT revision FROM account_controls WHERE user_id=?),1)',
                                  (actor['id'],)).fetchone()[0]
            token = PREFIX + secrets.token_hex(32)
            identifier = secrets.token_hex(16)
            now = int(time.time())
            db.execute('INSERT INTO service_credentials VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identifier, hashlib.sha256(token.encode()).hexdigest(), body.label,
                 actor['id'], revision, binding['device_id'], binding['site_id'], binding['asset_id'],
                 binding['revision'], now, now + body.lifetime_minutes * 60, None, 1, None))
            row = db.execute('SELECT * FROM service_credentials WHERE id=?', (identifier,)).fetchone()
            audit(db, actor['email'], 'service_credential_issued', identifier)
            result = {**BOUNDARY, 'credential': present(db, row), 'token': token,
                      'token_returned_once': True}
        response.status_code = 201
        response.headers['Cache-Control'] = 'no-store'
        return result

    @app.post('/api/service-credentials/{identifier}/revoke')
    def revoke(identifier: str, body: Revoke, request: Request, response: Response):
        current = require_user(request)
        require_csrf(request, current)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            actor = reauthenticate(db, current, body.current_password, matches, audit)
            row = db.execute('SELECT * FROM service_credentials WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise HTTPException(404, 'Service credential not found')
            if row['revision'] != body.expected_revision:
                raise HTTPException(409, 'Credential changed; refresh before revoking')
            if row['revoked_at'] is None:
                db.execute('UPDATE service_credentials SET revoked_at=?,revision=revision+1 WHERE id=?',
                           (int(time.time()), identifier))
                audit(db, actor['email'], 'service_credential_revoked', identifier)
            row = db.execute('SELECT * FROM service_credentials WHERE id=?', (identifier,)).fetchone()
            result = {**BOUNDARY, 'credential': present(db, row)}
        response.headers['Cache-Control'] = 'no-store'
        return result

    @app.post('/api/edge/observations')
    def ingest(body: DeliveryInput, request: Request, response: Response):
        require_service_transport(request)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            credential = authenticate(db, request)
            obs = body.observation
            if (any(getattr(obs, key) != credential[key] for key in ('site_id', 'asset_id', 'device_id'))
                    or body.binding_revision != credential['binding_revision']):
                raise HTTPException(403, 'Observation outside credential scope')
            matching_binding(db, body)
            created, receipt, conflict = commit_in_transaction(db, audit, 'service:' + credential['id'], body)
            db.execute('UPDATE service_credentials SET last_used_at=? WHERE id=?',
                       (int(time.time()), credential['id']))
        if conflict:
            raise HTTPException(409, 'Same source identity has different content; original preserved')
        response.status_code = 201 if created else 200
        response.headers['Cache-Control'] = 'no-store'
        return receipt
