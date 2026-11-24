"""Disposable synthetic observation-to-plan rollback and retry evidence.

Uses existing authenticated test fixtures; never contacts equipment or a live server.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT / 'dashboard'), str(PROJECT / 'dashboard' / 'tests')]
from test_observation_incidents import ObservationIncidentTests


def run():
    case = ObservationIncidentTests()
    try:
        case.setUp()
        created = case.create()
        case.assertEqual(created.status_code, 200)
        incident = created.json()['incident']
        source = created.json()['source_observation']
        route = '/api/incidents/' + incident['id'] + '/maintenance-plan'
        body = {'expected_revision': incident['revision'],
                'proposal': 'Inspect the synthetic provenance and declared quality; no equipment action is authorized.'}
        tables = ('acquisition_observations', 'synthetic_incidents', 'incident_plan_links',
                  'maintenance_requests', 'maintenance_request_events', 'audit')

        def counts():
            with case.server.database() as db:
                return {name: db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                        for name in tables}

        before = counts()
        with case.server.database() as db:
            incident_before = tuple(db.execute('SELECT * FROM synthetic_incidents').fetchone())
            db.execute("""CREATE TRIGGER deny_integrity_drill_audit BEFORE INSERT ON audit
                WHEN NEW.action='synthetic_incident_plan_linked'
                BEGIN SELECT RAISE(ABORT,'synthetic drill failure'); END""")
        with case.assertRaises(sqlite3.IntegrityError):
            case.post(route, body)
        case.assertEqual(before, counts())
        retained = case.http.get('/api/incidents/' + incident['id'])
        case.assertEqual(retained.status_code, 200)
        with case.server.database() as db:
            case.assertEqual(tuple(db.execute('SELECT * FROM synthetic_incidents').fetchone()), incident_before)
        case.assertEqual(retained.json()['source_observation'], source)
        with case.server.database() as db:
            db.execute('DROP TRIGGER deny_integrity_drill_audit')

        prepared = case.post(route, body)
        case.assertEqual(prepared.status_code, 200)
        plan = prepared.json()
        case.assertTrue(plan['created'])
        case.assertEqual(plan['request']['status'], 'draft')
        case.assertFalse(plan['execution_enabled'])
        snapshot = plan['source_incident']['snapshot']
        case.assertEqual(snapshot['source_observation'], source)
        saved = counts()
        case.assertEqual(saved['acquisition_observations'], 1)
        case.assertEqual(saved['synthetic_incidents'], 1)
        for table in ('incident_plan_links', 'maintenance_requests', 'maintenance_request_events'):
            case.assertEqual(saved[table], 1)

        retry = case.post(route, body)
        case.assertEqual(retry.status_code, 200)
        case.assertFalse(retry.json()['created'])
        case.assertEqual(retry.json()['request']['id'], plan['request']['id'])
        case.assertEqual(saved, counts())
        conflict = case.post(route, {**body, 'proposal': 'A changed proposal must not silently replace the saved draft.'})
        case.assertEqual(conflict.status_code, 409)
        case.assertEqual(saved, counts())

        changed = case.post('/api/incidents/' + incident['id'] + '/actions', {
            'expected_revision': incident['revision'], 'action': 'acknowledge',
            'note': 'Acknowledge the synthetic review without authorizing equipment work.'})
        case.assertEqual(changed.status_code, 200)
        case.assertEqual(changed.json()['incident']['revision'], incident['revision'] + 1)
        after_change = counts()
        retained_plan = case.post(route, body)
        case.assertEqual(retained_plan.status_code, 200)
        data = retained_plan.json()
        case.assertFalse(data['created'])
        case.assertEqual(data['request'], plan['request'])
        case.assertTrue(data['source_incident']['changed_since_capture'])
        case.assertEqual(data['source_incident']['snapshot'], snapshot)
        case.assertEqual(after_change, counts())
        for flag in ('hardware_connected', 'equipment_authorized', 'execution_enabled'):
            case.assertFalse(data[flag])
        case.assertFalse(created.json()['production_ready'])

        repo = PROJECT.parents[1]
        tree = subprocess.check_output(['git', '-c', 'safe.directory=' + repo.as_posix(),
                                        'rev-parse', 'HEAD^{tree}'], cwd=PROJECT, text=True).strip()
        return {
            'schema': 'edgeops.synthetic-workflow-integrity.v1',
            'executed_at_utc': datetime.now(timezone.utc).isoformat(), 'software_tree': tree,
            'scope': 'In-process authenticated API and disposable database; no live service or hardware.',
            'observation_count': 1, 'incident_count': 1, 'linked_maintenance_draft_count': 1,
            'checks': {'injected_audit_failure_rolled_back_plan_link_events_and_audit': True,
                       'source_incident_and_observation_unchanged_after_failure': True,
                       'retry_after_failure_succeeded': True,
                       'exact_retry_returned_existing_draft_without_writes': True,
                       'changed_retry_rejected_without_writes': True,
                       'later_incident_revision_flagged_without_changing_plan_snapshot': True},
            'maintenance_status': 'draft', 'execution_enabled': False,
            'hardware_connected': False, 'equipment_authorized': False,
            'physical_acceptance_verified': False, 'production_ready': False,
            'limitations': 'Deterministic local transaction failure and sequential retries only; not a power-loss, distributed delivery, browser or physical acceptance test.',
            'sanitization': 'Allowlisted assertions and counts; no credentials, identities, record IDs, database files or local paths exported.'}
    finally:
        case.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    content = json.dumps(run(), indent=2, allow_nan=False) + '\n'
    with args.output.open('x', encoding='utf-8', newline='\n') as output:
        output.write(content)
    print('PASS: synthetic rollback, safe retry and frozen source evidence.')
    print('Result SHA256: ' + hashlib.sha256(content.encode()).hexdigest())
