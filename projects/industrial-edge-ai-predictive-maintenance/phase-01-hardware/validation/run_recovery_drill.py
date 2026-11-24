"""Disposable synthetic backup/restore drill; never reads the running dashboard DB.

Requires the existing dashboard test dependencies and a new output filename.
Private temporary databases/backups are deleted; only an allowlisted result is saved.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT/'dashboard'), str(PROJECT/'dashboard/tests')]
import recovery
from test_observation_incidents import ObservationIncidentTests


def run():
    case = ObservationIncidentTests()
    try:
        case.setUp()
        created = case.create()
        case.assertEqual(created.status_code, 200)
        incident = created.json()
        prepared = case.post('/api/incidents/'+incident['incident']['id']+'/maintenance-plan', {
            'expected_revision':1,
            'proposal':'Review synthetic provenance after an isolated recovery exercise; no equipment work is authorized.'})
        case.assertEqual(prepared.status_code, 200)
        plan = prepared.json()
        case.assertEqual(plan['request']['status'], 'draft')
        source_path = case.server.DB_PATH
        source_digest = recovery.digest(source_path)
        directory = Path(case.temp.name)
        backup, restored = directory/'backup', directory/'restored'
        saved = recovery.create_backup(source_path, backup)
        case.assertTrue(saved['verified'])
        manifest = recovery.verify_backup(backup)
        case.assertEqual(len(manifest['files']), 1)
        report = recovery.restore_backup(backup, restored)
        case.assertTrue(report['verified'])
        case.assertEqual(report['sessions_revoked'], 1)
        case.assertFalse(report['production_ready'])
        with closing(sqlite3.connect(restored/'dashboard.sqlite3')) as db:
            case.assertEqual(db.execute('PRAGMA quick_check').fetchall(), [('ok',)])
            case.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            case.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
            counts = {table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                      for table in ('acquisition_observations','synthetic_incidents',
                                    'maintenance_requests','incident_plan_links','incident_observation_sources')}
            case.assertTrue(all(count == 1 for count in counts.values()))
        # The original browser token must not authenticate the restored database.
        with patch.object(case.server, 'DB_PATH', restored/'dashboard.sqlite3'):
            case.assertEqual(case.http.get('/api/me').status_code, 401)
            case.login('admin')
            loaded_incident = case.http.get('/api/incidents/'+incident['incident']['id'])
            case.assertEqual(loaded_incident.status_code, 200)
            case.assertEqual(loaded_incident.json()['source_observation'], incident['source_observation'])
            loaded_plan = case.http.get('/api/maintenance-requests/'+plan['request']['id'])
            case.assertEqual(loaded_plan.status_code, 200)
            loaded = loaded_plan.json()
            case.assertEqual(loaded['request']['status'], 'draft')
            case.assertEqual(loaded['source_incident'], plan['source_incident'])
            case.assertEqual(loaded['source_incident']['snapshot']['source_observation'], incident['source_observation'])
            case.assertFalse(loaded['execution_enabled'])
        # Alter a separate backup copy, never the source or valid recovery result.
        corrupt = directory/'corrupt-backup'
        shutil.copytree(backup, corrupt)
        (corrupt/'dashboard.sqlite3').write_bytes(b'intentionally altered synthetic drill copy')
        rejected = directory/'rejected-restore'
        with case.assertRaises(ValueError):
            recovery.restore_backup(corrupt, rejected)
        case.assertFalse(rejected.exists())
        case.assertEqual(recovery.digest(source_path), source_digest)
        repo = PROJECT.parents[1]
        tree = subprocess.check_output(['git','-c','safe.directory='+repo.as_posix(),
                                        'rev-parse','HEAD^{tree}'], cwd=PROJECT, text=True).strip()
        return {'schema':'edgeops.synthetic-recovery-drill.v1',
                'executed_at_utc':datetime.now(timezone.utc).isoformat(), 'software_tree':tree,
                'scope':'One disposable dashboard database; no live data, serial port, deployment or hardware.',
                'backup_verified':True, 'restored_database_integrity':'ok',
                'restored_foreign_key_violations':0, 'restored_domain_counts_before_login':counts,
                'sessions_revoked':report['sessions_revoked'], 'old_session_rejected':True,
                'new_login_succeeded':True, 'observation_snapshot_preserved':True,
                'incident_to_plan_snapshot_preserved':True, 'maintenance_status':'draft',
                'corrupt_backup_rejected_without_published_restore':True,
                'original_database_bytes_unchanged':True,
                'equipment_authorized':False, 'hardware_connected':False,
                'physical_acceptance_verified':False, 'production_ready':False,
                'limitations':'No coordinated multi-store recovery, live cutover, offsite/encrypted backup, measured RPO/RTO or physical maintenance is established.',
                'sanitization':'Allowlisted assertions and synthetic counts only; private databases, backups, identities, credentials and session tokens are not exported.'}
    finally:
        case.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run()
    content = json.dumps(result, indent=2, allow_nan=False)+'\n'
    with args.output.open('x', encoding='utf-8', newline='\n') as output:
        output.write(content)
    print('PASS: synthetic backup/restore, retained evidence, revoked session and corrupt-copy rejection.')
    print('Result SHA256: '+hashlib.sha256(content.encode()).hexdigest())
