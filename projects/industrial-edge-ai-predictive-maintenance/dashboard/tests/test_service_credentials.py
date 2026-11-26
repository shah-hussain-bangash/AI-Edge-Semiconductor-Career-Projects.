"""Disposable service identity tests; no real credential or installation used."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import recovery
import service_credentials
import service_delivery_worker
from edge_delivery import Spool
import test_acquisition_registry as fixture


class ServiceCredentialTests(unittest.TestCase):
    login = fixture.AcquisitionRegistryApiTests.login
    post = fixture.AcquisitionRegistryApiTests.post

    def setUp(self):
        fixture.AcquisitionRegistryApiTests.setUp(self)
        self.post('/api/acquisition-bindings', fixture.binding())
        self.edge = TestClient(self.server.app, base_url='https://testserver')
        self.addCleanup(self.edge.close)

    def issue(self, **changes):
        return self.post('/api/service-credentials', {
            'label': 'Disposable integration test', 'device_id': 'test-device',
            'expected_binding_revision': 1, 'lifetime_minutes': 60,
            'current_password': self.password, 'reason': 'Scoped synthetic integration test only.', **changes})

    def envelope(self):
        obs = fixture.observation()
        obs['boot_id'] = 'test-boot'
        obs['quality']['session_quality'] = 'verified'
        return {'binding_revision': 1, 'observation': obs}

    def ingest(self, token, body=None):
        return self.edge.post('/api/edge/observations', json=body or self.envelope(),
                              headers={'Authorization': 'Bearer ' + token})

    def revoke(self, row, **changes):
        return self.post('/api/service-credentials/' + row['id'] + '/revoke', {
            'expected_revision': row['revision'], 'current_password': self.password,
            'reason': 'Revoke disposable synthetic integration credential.', **changes})

    def test_hash_only_metadata_once_and_durable_service_ingest_without_session(self):
        response = self.issue();self.assertEqual(response.status_code, 201, response.text)
        issued = response.json();token = issued['token']
        self.assertEqual(response.headers['cache-control'], 'no-store')
        metadata = self.http.get('/api/service-credentials').json()
        self.assertNotIn(token, json.dumps(metadata));self.assertNotIn('token_hash', json.dumps(metadata))
        with self.server.database() as db:
            stored = db.execute('SELECT * FROM service_credentials').fetchone()
            self.assertEqual(stored['token_hash'], hashlib.sha256(token.encode()).hexdigest())
            self.assertNotIn(token, json.dumps(dict(stored)))
        self.assertEqual(self.edge.get('/api/me').status_code, 401)
        first = self.ingest(token);self.assertEqual(first.status_code, 201, first.text)
        self.server.init_db()
        second = self.ingest(token);self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json());self.assertFalse(first.json()['production_ready'])
        with self.server.database() as db:
            row = db.execute('SELECT actor FROM acquisition_observations').fetchone()
            self.assertTrue(row['actor'].startswith('service:'))
            self.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0], 1)
            self.assertNotIn(token, json.dumps([dict(x) for x in db.execute('SELECT * FROM audit')]))

    def test_management_reauth_csrf_roles_and_lifetime_validation(self):
        self.assertEqual(self.issue(current_password='wrong').status_code, 403)
        for lifetime in (0, 1441, True, '60'):
            self.assertEqual(self.issue(lifetime_minutes=lifetime).status_code, 422)
        self.assertEqual(self.post('/api/service-credentials', {}, csrf=False).status_code, 422)
        body = {'label': 'test', 'device_id': 'test-device', 'expected_binding_revision': 1,
                'lifetime_minutes': 1, 'current_password': self.password, 'reason': 'CSRF test for integration.'}
        self.assertEqual(self.post('/api/service-credentials', body, csrf=False).status_code, 403)
        for role in ('operator', 'auditor'):
            self.login(role);self.assertEqual(self.issue().status_code, 403)
            self.assertEqual(self.http.get('/api/service-credentials').status_code, 403)
        self.http.cookies.clear();self.assertEqual(self.http.get('/api/service-credentials').status_code, 401)

    def test_exact_scope_binding_retirement_measured_rejection_and_cookie_denial(self):
        token = self.issue().json()['token']
        for key in ('site_id', 'asset_id', 'device_id'):
            body = self.envelope();body['observation'][key] = 'other'
            self.assertEqual(self.ingest(token, body).status_code, 403)
        body = self.envelope();body['binding_revision'] = 2
        self.assertEqual(self.ingest(token, body).status_code, 403)
        body = self.envelope();body['observation']['source_type'] = 'measured'
        self.assertEqual(self.ingest(token, body).status_code, 422)
        self.assertEqual(self.http.post('/api/edge/observations', json=self.envelope()).status_code, 403)
        self.assertEqual(self.edge.post('/api/edge/observations', json=self.envelope()).status_code, 401)
        self.assertEqual(self.post('/api/acquisition-bindings/test-device/retire', {'expected_revision': 1}).status_code, 200)
        self.assertEqual(self.ingest(token).status_code, 401)
        self.assertEqual(self.http.get('/api/service-credentials').json()['credentials'][0]['status'], 'binding-changed')

    def test_expiry_revocation_stale_revision_and_duplicate_headers(self):
        data = self.issue().json();token = data['token'];row = data['credential']
        response = self.edge.post('/api/edge/observations', json=self.envelope(), headers=[
            ('Authorization', 'Bearer ' + token), ('Authorization', 'Bearer ' + token)])
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.revoke(row, expected_revision=2).status_code, 409)
        self.assertEqual(self.revoke(row).status_code, 200)
        self.assertEqual(self.ingest(token).status_code, 401)
        expired = self.issue().json()
        with self.server.database() as db:
            db.execute('UPDATE service_credentials SET expires_at=0 WHERE id=?', (expired['credential']['id'],))
        self.assertEqual(self.ingest(expired['token']).status_code, 401)

    def test_issuer_access_and_revision_changes_deny_service_access(self):
        data = self.issue().json()
        with self.server.database() as db:
            issuer = db.execute('SELECT issuer_id FROM service_credentials').fetchone()[0]
            db.execute('UPDATE users SET disabled=1 WHERE id=?', (issuer,))
        self.assertEqual(self.ingest(data['token']).status_code, 401)
        with self.server.database() as db:
            db.execute('UPDATE users SET disabled=0 WHERE id=?', (issuer,))
            db.execute("INSERT INTO account_controls VALUES(?,2,'test')", (issuer,))
        self.assertEqual(self.ingest(data['token']).status_code, 401)

    def test_concurrent_duplicate_and_changed_content_preserve_original(self):
        token = self.issue().json()['token']
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: self.ingest(token).status_code, range(2)))
        self.assertEqual(sorted(statuses), [200, 201])
        body = self.envelope();body['observation']['measurements']['acceleration_x_mps2'] = 1
        self.assertEqual(self.ingest(token, body).status_code, 409)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='synthetic_ingest_conflict'").fetchone()[0], 1)

    def test_backup_restore_revokes_service_credentials(self):
        data = self.issue().json();root = Path(self.temp.name)
        recovery.create_backup(self.server.DB_PATH, root/'backup')
        report = recovery.restore_backup(root/'backup', root/'restored')
        self.assertEqual(report['service_credentials_revoked'], 1)
        with closing(sqlite3.connect(root/'restored'/'dashboard.sqlite3')) as db:
            self.assertIsNotNone(db.execute('SELECT revoked_at FROM service_credentials').fetchone()[0])

    def test_plaintext_remote_transport_and_session_cannot_replace_bearer(self):
        token = self.issue().json()['token']
        remote = TestClient(self.server.app, base_url='http://testserver')
        self.addCleanup(remote.close)
        self.assertEqual(remote.post('/api/edge/observations', json=self.envelope(),
            headers={'Authorization': 'Bearer '+token}).status_code, 403)
        self.assertEqual(self.edge.post('/api/acquisition/ingest', json=self.envelope(),
            headers={'Authorization': 'Bearer '+token}).status_code, 401)

    def test_credential_capacity_and_no_create_on_stale_binding(self):
        self.assertEqual(self.issue(expected_binding_revision=2).status_code, 409)
        with patch.object(service_credentials, 'MAX_CREDENTIALS', 1):
            self.assertEqual(self.issue().status_code, 201)
            self.assertEqual(self.issue().status_code, 429)

    def test_worker_uses_bearer_without_browser_login_and_rejects_remote_origin(self):
        token = self.issue().json()['token'];path = Path(self.temp.name)/'spool.db'
        Spool(path).enqueue(self.envelope())
        seen = []
        real_client = service_delivery_worker.httpx.Client
        import httpx
        def send(request):
            seen.append((request.url.path, request.headers.get('authorization')))
            return self.edge.post(request.url.path, content=request.content,
                                  headers={'Authorization': request.headers['authorization'], 'content-type': 'application/json'})
        def client(**kwargs):
            return real_client(**kwargs, transport=httpx.MockTransport(send))
        with patch.object(service_delivery_worker.httpx, 'Client', side_effect=client):
            result = service_delivery_worker.run_once(path, 'http://127.0.0.1:8877', token)
        self.assertTrue(result['attempted']);self.assertEqual(Spool(path).status()['counts']['delivered'], 1)
        self.assertEqual(seen, [('/api/edge/observations', 'Bearer ' + token)])
        with self.assertRaises(ValueError):
            service_delivery_worker.run_once(path, 'http://example.invalid', token)


if __name__ == '__main__':
    unittest.main()
