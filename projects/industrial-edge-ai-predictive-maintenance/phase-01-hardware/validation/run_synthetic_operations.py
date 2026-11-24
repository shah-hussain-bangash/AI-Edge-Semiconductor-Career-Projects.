"""One isolated API walkthrough; never contacts equipment or the running dashboard.

Uses existing test fixtures, ephemeral credentials and a disposable database.
Run with the dashboard test dependencies installed; output is sanitized JSON.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT / 'dashboard'), str(PROJECT / 'dashboard' / 'tests')]
from test_observation_incidents import ObservationIncidentTests
from test_delivery import envelope


def run():
    case = ObservationIncidentTests()
    try:
        case.setUp()  # Creates exactly one synthetic observation in a temporary DB.
        response = case.http.get('/api/acquisition/observations?device_id=test-device')
        case.assertEqual(response.status_code, 200)
        history = response.json()
        case.assertEqual(len(history['records']), 1)
        record = history['records'][0]
        case.assertEqual(record['content_hash'], case.source['content_hash'])
        case.assertEqual(record['event_key'], case.source['event_key'])
        case.assertEqual(record['observation']['measurements']['acceleration_x_mps2'], 0)
        case.assertIsNone(record['observation']['measurements']['current_a'])
        case.assertEqual(record['freshness']['state'], 'clock-unverified')
        case.assertFalse(history['hardware_connected'])
        created = case.create()
        case.assertEqual(created.status_code, 200)
        incident = created.json()
        source = incident['source_observation']
        case.assertEqual(source['observation'], record['observation'])
        case.assertEqual(source['content_hash'], record['content_hash'])
        case.assertEqual(source['receipt_id'], case.source['receipt_id'])
        case.assertEqual(source['channels']['current_a']['unit'], 'A')
        for flag in ('automatic_detection', 'equipment_authorized', 'hardware_connected'):
            case.assertFalse(incident[flag])
        prepared = case.post('/api/incidents/' + incident['incident']['id'] + '/maintenance-plan', {
            'expected_revision': 1,
            'proposal': 'Review synthetic source quality and clock limitations. Prepare sensor-only acceptance; no equipment action is authorized.'})
        case.assertEqual(prepared.status_code, 200)
        plan = prepared.json()
        case.assertEqual(plan['source_incident']['snapshot']['source_observation'], source)
        retained = case.http.get('/api/incidents/' + incident['incident']['id'])
        case.assertEqual(retained.status_code, 200)
        case.assertEqual(retained.json()['source_observation'], source)
        with case.server.database() as db:
            case.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0], 1)
            statuses = [row[0] for row in db.execute('SELECT status FROM maintenance_requests')]
            case.assertEqual(statuses, ['draft'])
        return {
            'schema': 'edgeops.synthetic-operations-walkthrough.v1',
            'executed_at_utc': datetime.now(timezone.utc).isoformat(),
            'software_tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=PROJECT, text=True).strip(),
            'scope': 'In-process authenticated API inspection, incident and maintenance-draft preparation; not a browser or hardware test.',
            'input': {**envelope(), 'observation': record['observation']},
            'inspection': {'event_key': record['event_key'], 'content_hash': record['content_hash'],
                           'freshness_state': record['freshness']['state'], 'unit_current': source['channels']['current_a']['unit'],
                           'zero_preserved': True, 'missing_current_preserved_as_null': True,
                           'source_matches_history_and_commit_receipt': True},
            'incident': {'state': incident['incident']['state'], 'severity': 'watch',
                         'interpretation': 'Human-created synthetic review; no equipment fault established.'},
            'maintenance': {'prepared': True, 'status': statuses[0], 'source_snapshot_matches': True,
                            'execution_authorized': False, 'approval_performed': False},
            'checks': {'exactly_one_observation': True, 'retained_incident_source_matches': True,
                       'automatic_detection': False, 'hardware_connected': False, 'equipment_authorized': False},
            'physical_acceptance': 'pending',
            'sanitization': 'Allowlisted fields only; no credentials, cookies, user IDs, database files, local paths or live data.'}
    finally:
        case.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run()
    content = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    with args.output.open('x', encoding='utf-8', newline='\n') as output:
        output.write(content)
    print('PASS: one synthetic observation inspected; incident and maintenance draft prepared.')
    print('Result SHA256: ' + hashlib.sha256(content.encode('utf-8')).hexdigest())
