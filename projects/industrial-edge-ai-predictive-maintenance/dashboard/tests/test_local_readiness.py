import os
import unittest
from unittest.mock import patch
import test_operational_workflow as fixture
from test_bench_ingress import frame,gateway


class LocalReadinessTests(unittest.TestCase):
    setUp=fixture.OperationalTests.setUp
    login=fixture.OperationalTests.login
    post=fixture.OperationalTests.post
    rule=fixture.OperationalTests.rule
    ingest=fixture.OperationalTests.ingest

    def snapshot(self):return self.http.get('/api/production-readiness/local-capabilities')

    def test_all_fourteen_are_read_only_observations_not_acceptance(self):
        def counts():
            with self.server.database() as db:return {name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('audit','readiness_records','readiness_events','readiness_release_scope','readiness_scope_events','operational_cases','platform_backup_jobs')}
        before=counts();reply=self.snapshot();self.assertEqual(reply.status_code,200,reply.text)
        data=reply.json();self.assertEqual(len(data['items']),14);self.assertEqual(len({item['id'] for item in data['items']}),14)
        self.assertEqual(data['scope'],'local-capability-observations');self.assertFalse(data['production_ready']);self.assertFalse(data['physical_acceptance_verified']);self.assertFalse(data['acceptance_records_changed'])
        self.assertTrue(all(item['production_accepted'] is False for item in data['items']))
        self.assertEqual(reply.headers['cache-control'],'no-store');self.assertEqual(before,counts())

    def test_source_lanes_and_case_visibility_stay_distinct(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        body=gateway.sample(frame(),'b'*32,0,'measured-unverified')
        reply=self.http.post('/api/bench/readings',json=body,headers={'authorization':'Bearer '+self.token});self.assertEqual(reply.status_code,201,reply.text)
        admin={item['id']:item for item in self.snapshot().json()['items']}
        self.assertIn('1 fixture runs; 1 gateway-declared measurement runs (unverified)',admin['registered-data']['observation'])
        self.assertIn('1 cases',admin['threshold-cases']['observation']);self.assertEqual(admin['threshold-cases']['state'],'review_required')
        self.login('operator');operator={item['id']:item for item in self.snapshot().json()['items']}
        self.assertIn('0 cases',operator['threshold-cases']['observation']);self.assertFalse(operator['registered-data']['production_accepted'])

    def test_role_private_configuration_and_secrets_are_not_exported(self):
        private=dict(EDGEOPS_SMTP_HOST='private-fixture.smtp.invalid',EDGEOPS_SMTP_USERNAME='private-fixture-user',EDGEOPS_SMTP_PASSWORD='private-fixture-password',EDGEOPS_SMTP_FROM='private-sender@example.invalid')
        with patch.dict(os.environ,private),patch('platform_operations.backup_ready',return_value=dict(private_key_ready=True,output_directory_ready=True)):
            admin=self.snapshot();self.assertEqual(admin.status_code,200,admin.text)
            for value in private.values():self.assertNotIn(value,admin.text)
            self.login('operator');reply=self.snapshot();self.assertEqual(reply.status_code,200,reply.text)
            areas={item['id']:item for item in reply.json()['items']}
            for identity in ('observability','recovery','governance'):self.assertEqual(areas[identity]['state'],'access_restricted')
            for value in private.values():self.assertNotIn(value,reply.text)
            self.assertNotIn('completed jobs:',areas['recovery']['observation']);self.assertNotIn(self.password,reply.text)
        self.login('auditor');self.assertEqual(self.snapshot().status_code,200)

    def test_authenticator_observation_is_for_current_account_only(self):
        with self.server.database() as db:
            identity=db.execute("SELECT id FROM users WHERE email='admin@example.invalid'").fetchone()[0]
            db.execute('INSERT INTO account_mfa(user_id,enabled,last_counter,revision) VALUES(?,1,-1,1)',(identity,))
        areas={item['id']:item for item in self.snapshot().json()['items']}
        self.assertEqual(areas['identity']['state'],'available_locally')
        self.login('operator');areas={item['id']:item for item in self.snapshot().json()['items']}
        self.assertEqual(areas['identity']['state'],'optional_setup');self.assertIn('not enabled',areas['identity']['observation'])

    def test_no_session_cannot_obtain_observations(self):
        self.http.cookies.clear();self.assertEqual(self.snapshot().status_code,401)
