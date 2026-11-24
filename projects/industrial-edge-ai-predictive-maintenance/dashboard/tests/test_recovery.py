"""Real snapshots/restores in disposable directories; never touches the live store."""
from contextlib import closing, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import recovery
from experiment_registry import register_experiment, verify_experiment
from test_experiment_registry import demo_rows


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='edgeops-recovery-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.backup = self.root / 'live.sqlite3', self.root / 'backup'
        with closing(sqlite3.connect(self.source)) as db:
            db.executescript('''
              CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,role TEXT,password_hash TEXT);
              CREATE TABLE sessions(token_hash TEXT,user_id INTEGER REFERENCES users(id));
              CREATE TABLE audit(time_utc TEXT,actor TEXT,action TEXT,detail TEXT);
              CREATE TABLE maintenance_requests(id TEXT,notes TEXT);
              CREATE TABLE readiness_records(id TEXT,evidence TEXT);
              INSERT INTO users VALUES(1,'test@example.invalid','admin','test-only-password-hash');
              INSERT INTO sessions VALUES('test-only-session',1);
              INSERT INTO maintenance_requests VALUES('PLAN-1','preserve planning notes');
              INSERT INTO readiness_records VALUES('REQ-01','preserve evidence and decisions');
            ''')
        self.artifacts = self.root / 'experiments'
        self.run = register_experiment(demo_rows(), self.artifacts)

    def create(self):
        return recovery.create_backup(self.source, self.backup, artifacts=self.artifacts)

    def test_round_trip_preserves_identity_domains_and_verified_reports_but_revokes_sessions(self):
        self.create()
        original = self.source.read_bytes()
        restored = self.root / 'restored'
        result = recovery.restore_backup(self.backup, restored)
        self.assertTrue(result['verified'])
        self.assertEqual(result['sessions_revoked'], 1)
        self.assertEqual(original, self.source.read_bytes())
        with closing(sqlite3.connect(restored / 'dashboard.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT email,role,password_hash FROM users').fetchone(),
                             ('test@example.invalid', 'admin', 'test-only-password-hash'))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT notes FROM maintenance_requests').fetchone()[0], 'preserve planning notes')
            self.assertEqual(db.execute('SELECT evidence FROM readiness_records').fetchone()[0], 'preserve evidence and decisions')
            self.assertEqual(db.execute('SELECT action FROM audit').fetchone()[0], 'recovery_restore')
        self.assertEqual(verify_experiment(restored / 'artifacts', self.run['run_id']), verify_experiment(self.artifacts, self.run['run_id']))

    def test_wal_commits_are_included_in_online_snapshot(self):
        db = sqlite3.connect(self.source)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute("INSERT INTO maintenance_requests VALUES('PLAN-2','committed in WAL')")
            db.commit()
            self.create()
        finally:
            db.close()
        self.assertEqual(next(e['table_counts']['maintenance_requests'] for e in recovery.verify_backup(self.backup)['files'] if e['role']=='dashboard'), 2)

    def test_corrupt_backup_cannot_publish_restore(self):
        self.create()
        (self.backup / 'dashboard.sqlite3').write_bytes(b'tampered')
        destination = self.root / 'restored'
        with self.assertRaises(ValueError):
            recovery.restore_backup(self.backup, destination)
        self.assertFalse(destination.exists())

    def test_existing_destination_and_source_are_never_overwritten(self):
        self.create()
        snapshot = self.source.read_bytes()
        with self.assertRaises(ValueError):
            recovery.restore_backup(self.backup, self.root)
        with self.assertRaises(ValueError):
            self.create()
        with self.assertRaises(ValueError):
            recovery.restore_backup(self.backup, self.backup / 'nested-restore')
        self.assertFalse((self.backup / 'nested-restore').exists())
        recovery.verify_backup(self.backup)
        self.assertEqual(snapshot, self.source.read_bytes())

    def test_missing_source_does_not_create_database_or_completed_backup(self):
        missing = self.root / 'absent.sqlite3'
        with self.assertRaises(FileNotFoundError):
            recovery.create_backup(missing, self.backup)
        self.assertFalse(missing.exists())
        self.assertFalse(self.backup.exists())

    def test_manifest_path_traversal_and_extra_files_are_rejected(self):
        self.create()
        path = self.backup / 'manifest.json'
        original = path.read_text(encoding='utf-8')
        manifest = json.loads(original)
        manifest['files'][0]['path'] = '../live.sqlite3'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(ValueError):
            recovery.verify_backup(self.backup)
        path.write_text(original, encoding='utf-8')
        (self.backup / 'unexpected.env').write_text('test-only', encoding='utf-8')
        with self.assertRaises(ValueError):
            recovery.verify_backup(self.backup)

    def test_validly_hashed_but_corrupt_database_still_fails_integrity(self):
        self.create()
        path = self.backup / 'manifest.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        data = b'not a database'
        (self.backup / 'dashboard.sqlite3').write_bytes(data)
        entry = next(e for e in manifest['files'] if e['role'] == 'dashboard')
        entry.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(sqlite3.DatabaseError):
            recovery.verify_backup(self.backup)

    def test_bad_artifact_is_not_published_as_success(self):
        next((self.artifacts / 'runs').glob('*.json')).write_bytes(b'altered')
        with self.assertRaises(ValueError):
            self.create()
        self.assertFalse(self.backup.exists())

    def test_manifest_root_must_be_an_object(self):
        self.create()
        original = self.source.read_bytes()
        for value in ([], None, 'private-test-marker', 1, True):
            with self.subTest(value=value):
                (self.backup / 'manifest.json').write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, '^Unsupported backup manifest$'):
                    recovery.restore_backup(self.backup, self.root / 'restored')
                self.assertFalse((self.root / 'restored').exists())
        self.assertEqual(original, self.source.read_bytes())
        self.assertEqual([], list(self.root.glob('.edgeops-pending-*')))

    def test_ambiguous_and_nonstandard_manifest_json_is_rejected(self):
        self.create()
        path = self.backup / 'manifest.json'
        original = path.read_text(encoding='utf-8')
        manifest = json.loads(original)
        cases = [original.replace('{', '{"format":"private-test-marker",', 1),
                 original.replace('{', '{"format":' + json.dumps(recovery.FORMAT) + ',', 1),
                 original.replace('{', '{"extra":{"key":1,"key":2},', 1),
                 json.dumps(manifest).replace('"bytes":', '"bytes":0,"bytes":', 1)]
        cases.extend(original.replace('{', '{"extra":' + value + ',', 1)
                     for value in ('NaN', 'Infinity', '-Infinity'))
        for index, content in enumerate(cases):
            with self.subTest(case=index):
                path.write_text(content, encoding='utf-8')
                with self.assertRaisesRegex(ValueError, '^Invalid backup manifest JSON$'):
                    recovery.restore_backup(self.backup, self.root / 'restored')
                self.assertFalse((self.root / 'restored').exists())
        path.write_text(original, encoding='utf-8')
        recovery.verify_backup(self.backup)

    def test_cli_rejects_malformed_manifest_without_traceback_or_content(self):
        self.create()
        original = self.source.read_bytes()
        cases = ['[]', 'null', '{"private-test-marker":',
                 '{"private-test-marker":1,"private-test-marker":2}',
                 '[' * 100000 + '0' + ']' * 100000]
        for command in ('verify', 'restore'):
            for index, content in enumerate(cases):
                with self.subTest(command=command, case=index):
                    (self.backup / 'manifest.json').write_text(content, encoding='utf-8')
                    args = ['recovery.py', command, str(self.backup)]
                    if command == 'restore':
                        args.extend(['--output', str(self.root / 'restored')])
                    stderr = io.StringIO()
                    with patch.object(sys, 'argv', args), redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            recovery.main()
                    self.assertEqual(1, raised.exception.code)
                    self.assertTrue(stderr.getvalue().startswith('Recovery operation failed: '))
                    self.assertNotIn('Traceback', stderr.getvalue())
                    self.assertNotIn('private-test-marker', stderr.getvalue())
                    self.assertFalse((self.root / 'restored').exists())
        self.assertEqual(original, self.source.read_bytes())
        self.assertEqual([], list(self.root.glob('.edgeops-pending-*')))
