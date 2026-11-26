"""Opt-in atomic synthetic correlation and governed human handoff in disposable stores."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
from contextlib import closing
import json
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import correlation
import recovery
import test_acquisition_registry as fixture


class CorrelationTests(unittest.TestCase):
    login=fixture.AcquisitionRegistryApiTests.login
    post=fixture.AcquisitionRegistryApiTests.post

    def setUp(self):
        fixture.AcquisitionRegistryApiTests.setUp(self)
        binding=fixture.binding('corr-device');binding.update(site_id='corr-site',asset_id='MTR-001')
        self.assertEqual(self.post('/api/acquisition-bindings',binding).status_code,201)

    def policy_body(self,**changes):
        return {'label':'Synthetic acceleration threshold','device_id':'corr-device','expected_binding_revision':1,
            'channel':'acceleration_x_mps2','comparison':'above','threshold':5.0,'window_size':10,
            'max_age_seconds':3600,'severity':'critical',
            'calibration_policy':'allow_declared_unverified_for_synthetic',
            'current_password':self.password,'reason':'Activate a reviewed disposable synthetic threshold policy.',**changes}

    def create_policy(self,**changes):
        response=self.post('/api/correlation/policies',self.policy_body(**changes))
        self.assertEqual(response.status_code,201,response.text)
        return response.json()['policy']

    def envelope(self,sequence=0,value=10,**changes):
        obs=fixture.observation('corr-device')
        obs.update(site_id='corr-site',asset_id='MTR-001',boot_id='corr-boot',sequence=sequence)
        obs['quality']['session_quality']='verified'
        obs['measurements']['acceleration_x_mps2']=value
        obs['timestamp']['clock_quality']='device_clock_verified'
        obs['timestamp']['device_time_utc']=(datetime.now(timezone.utc)-timedelta(seconds=5)).isoformat()
        obs.update(changes)
        return {'binding_revision':1,'observation':obs}

    def ingest(self,body):return self.post('/api/acquisition/ingest',body)
    def cases(self):return self.http.get('/api/correlation/cases').json()['cases']
    def count(self,table):
        with self.server.database() as db:return db.execute('SELECT count(*) FROM '+table).fetchone()[0]

    def test_no_policy_means_no_automatic_effect_and_activation_never_replays_history(self):
        body=self.envelope();self.assertEqual(self.ingest(body).status_code,201)
        self.assertEqual(self.cases(),[]);self.create_policy()
        self.assertEqual(self.ingest(body).status_code,200);self.assertEqual(self.cases(),[])
        self.assertEqual(self.ingest(self.envelope(1)).status_code,201);self.assertEqual(len(self.cases()),1)

    def test_duplicate_conflict_and_out_of_order_events_have_one_case_per_sequence_window(self):
        self.create_policy();first=self.envelope(2)
        self.assertEqual(self.ingest(first).status_code,201);self.assertEqual(self.ingest(first).status_code,200)
        second=self.envelope(1);self.assertEqual(self.ingest(second).status_code,201)
        row=self.cases()[0];self.assertEqual(row['matched_events'],2)
        self.assertEqual((row['min_sequence'],row['max_sequence']),(1,2))
        changed=json.loads(json.dumps(first));changed['observation']['measurements']['acceleration_x_mps2']=12
        self.assertEqual(self.ingest(changed).status_code,409);self.assertEqual(self.cases()[0]['matched_events'],2)
        self.assertEqual(self.ingest(self.envelope(10)).status_code,201);self.assertEqual(len(self.cases()),2)
        self.assertEqual(self.ingest(self.envelope(0,boot_id='another-boot')).status_code,201)
        self.assertEqual(len(self.cases()),3);self.assertEqual(self.count('synthetic_incidents'),0)

    def test_same_source_concurrent_delivery_creates_one_evaluation_and_case(self):
        self.create_policy();body=self.envelope()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.ingest(body).status_code,range(2)))
        self.assertEqual(sorted(results),[200,201]);self.assertEqual(self.count('correlation_evaluations'),1)
        self.assertEqual(self.cases()[0]['matched_events'],1)

    def test_quality_calibration_clock_and_age_abstention_are_recorded(self):
        self.create_policy(calibration_policy='verified_only')
        bodies=[self.envelope(i) for i in range(6)]
        for item in bodies:item['observation']['quality']['calibration']='verified'
        bodies[0]['observation']['quality']['calibration']='unknown'
        bodies[1]['observation']['quality']['adxl345']='invalid'
        for key in ('acceleration_x_mps2','acceleration_y_mps2','acceleration_z_mps2'):
            bodies[1]['observation']['measurements'][key]=None
        bodies[2]['observation']['timestamp'].update(clock_quality='gateway_receipt_only',device_time_utc=None)
        bodies[3]['observation']['timestamp']['device_time_utc']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        bodies[4]['observation']['timestamp']['device_time_utc']=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
        bodies[5]['observation']['measurements']['acceleration_x_mps2']=5
        for body in bodies:self.assertEqual(self.ingest(body).status_code,201)
        self.assertEqual(self.cases(),[])
        with self.server.database() as db:
            decisions=[x[0] for x in db.execute('SELECT decision FROM correlation_evaluations')]
        self.assertCountEqual(decisions,['calibration-unverified','quality-unusable','clock-unverified',
                                        'stale-or-future','stale-or-future','not-matched'])

    def test_legitimate_zero_and_policy_disable_replacement_preserve_history(self):
        policy=self.create_policy(comparison='below',threshold=1.0)
        self.assertEqual(self.ingest(self.envelope(value=0)).status_code,201);first=self.cases()[0]
        disable={'expected_revision':1,'current_password':self.password,'reason':'Disable the disposable policy before replacement.'}
        self.assertEqual(self.post('/api/correlation/policies/'+policy['id']+'/disable',disable).status_code,200)
        self.assertEqual(self.ingest(self.envelope(1,value=0)).status_code,201);self.assertEqual(self.cases()[0]['matched_events'],1)
        replacement=self.create_policy(comparison='below',threshold=-1.0)
        self.assertNotEqual(policy['id'],replacement['id']);self.ingest(self.envelope(2,value=0))
        self.assertEqual(len(self.cases()),1);self.assertEqual(self.cases()[0]['id'],first['id'])

    def test_current_authority_binding_and_policy_integrity_are_enforced(self):
        self.create_policy()
        with self.server.database() as db:
            owner=db.execute('SELECT issuer_id FROM correlation_policies').fetchone()[0]
            db.execute("INSERT INTO account_controls VALUES(?,2,'test')",(owner,))
        self.assertEqual(self.ingest(self.envelope()).status_code,201);self.assertEqual(self.cases(),[])
        self.assertEqual(self.http.get('/api/correlation/policies').json()['policies'][0]['status'],'issuer-changed')

    def test_capacity_and_corrupt_policy_roll_back_the_entire_new_observation(self):
        self.create_policy()
        with patch.object(correlation,'MAX_CASES',0):
            self.assertEqual(self.ingest(self.envelope()).status_code,429)
        self.assertEqual(self.count('acquisition_observations'),0);self.assertEqual(self.count('correlation_evaluations'),0)
        with self.server.database() as db:db.execute("UPDATE correlation_policies SET config_hash=?",('0'*64,))
        self.assertEqual(self.ingest(self.envelope()).status_code,503)
        self.assertEqual(self.count('acquisition_observations'),0)

    def test_partial_multi_policy_evaluation_cannot_commit_half_an_effect(self):
        self.create_policy();self.create_policy(channel='motor_case_temperature_c')
        body=self.envelope();body['observation']['measurements']['motor_case_temperature_c']=10
        body['observation']['quality']['ds18b20']='valid'
        with patch.object(correlation,'MAX_EVALUATIONS',1):self.assertEqual(self.ingest(body).status_code,429)
        self.assertEqual(self.count('acquisition_observations'),0);self.assertEqual(self.count('correlation_cases'),0)
        self.assertEqual(self.count('correlation_evaluations'),0)

    def test_policy_roles_reauthentication_csrf_and_duplicate_activation(self):
        self.assertEqual(self.post('/api/correlation/policies',self.policy_body(),csrf=False).status_code,403)
        self.assertEqual(self.post('/api/correlation/policies',self.policy_body(current_password='wrong')).status_code,403)
        self.assertEqual(self.post('/api/correlation/policies',self.policy_body(threshold=True)).status_code,422)
        self.create_policy();self.assertEqual(self.post('/api/correlation/policies',self.policy_body()).status_code,409)
        for role in ('operator','auditor'):
            self.login(role);self.assertEqual(self.post('/api/correlation/policies',self.policy_body()).status_code,403)
            self.assertEqual(self.http.get('/api/correlation/cases').status_code,200)
        self.http.cookies.clear();self.assertEqual(self.http.get('/api/correlation/cases').status_code,401)

    def test_human_handoff_is_revision_bound_idempotent_and_uses_existing_workflow(self):
        self.create_policy();self.ingest(self.envelope());original=self.cases()[0]
        self.ingest(self.envelope(1));case=self.cases()[0]
        note='Human review of the synthetic threshold evidence before investigation.'
        self.assertEqual(self.post('/api/correlation/cases/'+case['id']+'/handoff',{
            'expected_revision':original['revision'],'note':note}).status_code,409)
        body={'expected_revision':case['revision'],'note':note}
        first=self.post('/api/correlation/cases/'+case['id']+'/handoff',body)
        self.assertEqual(first.status_code,200,first.text);self.assertTrue(first.json()['created'])
        second=self.post('/api/correlation/cases/'+case['id']+'/handoff',body)
        self.assertEqual(second.status_code,200);self.assertFalse(second.json()['created'])
        incident=first.json()['incident_detail']['incident'];self.assertEqual(self.count('synthetic_incidents'),1)
        self.assertIn(case['id'],incident['observation'])
        self.ingest(self.envelope(2));updated=self.cases()[0]
        self.assertTrue(updated['new_evidence_since_handoff']);self.assertEqual(updated['incident_id'],incident['id'])
        self.assertEqual(self.http.get('/api/incidents/'+incident['id']).json()['incident']['revision'],1)
        context=self.http.get('/api/incidents/'+incident['id']).json()['correlation_source']
        self.assertTrue(context['changed_since_handoff']);self.assertEqual(context['captured_case_revision'],2)
        self.login('operator');self.assertIsNone(self.cases()[0]['incident_id'])
        self.assertTrue(self.cases()[0]['handoff_recorded'])

    def test_evidence_paging_integrity_and_frozen_first_source(self):
        self.create_policy(window_size=100)
        for sequence in range(25):self.assertEqual(self.ingest(self.envelope(sequence)).status_code,201)
        case=self.cases()[0]
        result=self.http.get('/api/correlation/cases/'+case['id']+'?limit=10').json()
        self.assertEqual(len(result['evidence']),10);self.assertEqual(result['total_evidence'],25)
        self.assertEqual(result['first_accepted_source']['observation']['sequence'],0)
        self.assertEqual(len(self.http.get('/api/correlation/cases/'+case['id']+'?offset=20&limit=10').json()['evidence']),5)
        with self.server.database() as db:db.execute('UPDATE acquisition_observations SET payload=? WHERE event_key=?',('{}',case['first_event_key']))
        self.assertEqual(self.http.get('/api/correlation/cases/'+case['id']).status_code,503)

    def test_restore_retains_evidence_but_disables_automatic_policy_authority(self):
        self.create_policy();self.ingest(self.envelope())
        root=Path(self.temp.name)
        recovery.create_backup(self.server.DB_PATH,root/'backup')
        result=recovery.restore_backup(root/'backup',root/'restored')
        self.assertEqual(result['correlation_policies_disabled'],1)
        with closing(sqlite3.connect(root/'restored'/'dashboard.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM correlation_cases').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT disabled FROM correlation_policies').fetchone()[0],1)

    def test_evidence_paging_refuses_changed_case_revision(self):
        self.create_policy();self.ingest(self.envelope());case=self.cases()[0]
        self.ingest(self.envelope(1))
        self.assertEqual(self.http.get('/api/correlation/cases/'+case['id']+'?case_revision='+str(case['revision'])).status_code,409)


if __name__=='__main__':unittest.main()
