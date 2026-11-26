import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import private_crypto
import platform_worker
import test_operational_workflow as fixture


class PlatformTests(unittest.TestCase):
    setUp=fixture.OperationalTests.setUp
    login=fixture.OperationalTests.login
    post=fixture.OperationalTests.post
    rule=fixture.OperationalTests.rule
    ingest=fixture.OperationalTests.ingest

    def status(self):return self.http.get('/api/platform/status')

    def test_metrics_schema_health_and_role_access(self):
        response=self.status();self.assertEqual(response.status_code,200,response.text)
        data=response.json();self.assertEqual(data['schema'][0]['version'],1);self.assertFalse(data['hosting_deployed'])
        metrics=self.http.get('/api/platform/metrics');self.assertEqual(metrics.status_code,200)
        self.assertIn('edgeops_http_requests_total',metrics.text);self.assertNotIn(str(self.server.DB_PATH),metrics.text)
        self.assertNotIn(self.password,response.text)
        self.login('operator');self.assertEqual(self.status().status_code,403)
        self.login('auditor');self.assertEqual(self.status().status_code,200)
        with self.server.database() as db:db.execute('ALTER TABLE operational_assets ADD COLUMN unexpected TEXT')
        with self.assertRaises(RuntimeError):self.server.init_db()

    def test_reviewed_retention_is_bound_to_preview_and_independent(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        notice=self.http.get('/api/operational/notifications').json()['items'][0]
        self.post('/api/operational/notifications/'+notice['id']+'/read',{})
        with self.server.database() as db:db.execute("UPDATE operational_notifications SET created_at='2020-01-01T00:00:00+00:00'")
        body=dict(request_key='e'*32,domain='read-notifications',keep_days=30,**self.authorization)
        response=self.post('/api/platform/retention',body);self.assertEqual(response.status_code,200,response.text)
        plan=response.json();self.assertEqual(plan['target_count'],1)
        apply=dict(expected_revision=1,target_sha256=plan['target_sha256'],**self.authorization)
        self.assertEqual(self.post('/api/platform/retention/'+plan['id']+'/apply',apply).status_code,403)
        self.login('reviewer');response=self.post('/api/platform/retention/'+plan['id']+'/apply',apply);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['deleted_records'],1)
        self.assertTrue(self.post('/api/platform/retention/'+plan['id']+'/apply',apply).json()['already_applied'])
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM bench_samples').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM operational_cases').fetchone()[0],1)
        self.assertEqual(self.post('/api/platform/retention',dict(body,domain='raw-readings')).status_code,422)

    def test_mutated_preview_does_not_delete_current_records(self):
        self.rule();self.ingest(temp_c=40)
        with self.server.database() as db:db.execute("UPDATE operational_notifications SET created_at='2020-01-01',read_at='2020-01-02'")
        plan=self.post('/api/platform/retention',dict(request_key='f'*32,domain='read-notifications',keep_days=30,**self.authorization)).json()
        with self.server.database() as db:db.execute("UPDATE operational_notifications SET subject='changed after preview'")
        self.login('reviewer');response=self.post('/api/platform/retention/'+plan['id']+'/apply',dict(expected_revision=1,target_sha256=plan['target_sha256'],**self.authorization))
        self.assertEqual(response.status_code,409)
        with self.server.database() as db:self.assertEqual(db.execute('SELECT count(*) FROM operational_notifications').fetchone()[0],1)

    def test_encrypted_backup_queue_worker_and_schedule_are_opt_in(self):
        with patch.dict(os.environ,{'EDGEOPS_PRIVATE_KEY_FILE':'','EDGEOPS_PROTECTED_BACKUP_DIR':''}):
            self.assertEqual(self.post('/api/platform/backup-jobs',dict(request_key='a'*32,**self.authorization)).status_code,422)
        root=Path(self.temp.name);key=root/'key';private_crypto.generate(key);output=root/'encrypted';output.mkdir()
        settings={'EDGEOPS_PRIVATE_KEY_FILE':str(key),'EDGEOPS_PROTECTED_BACKUP_DIR':str(output),'EDGEOPS_SMTP_HOST':'',
                  'EDGEOPS_OFFLINE_EXPERIMENT_ROOT':'','EDGEOPS_BACKUP_DELIVERY_SPOOL':''}
        with patch.dict(os.environ,settings):
            job=self.post('/api/platform/backup-jobs',dict(request_key='a'*32,**self.authorization));self.assertEqual(job.status_code,200,job.text)
            self.assertFalse(self.post('/api/platform/backup-jobs',dict(request_key='a'*32,**self.authorization)).json()['created'])
            result=platform_worker.run_once(self.server.database,self.server.DB_PATH);self.assertEqual(result['backup']['state'],'completed')
            self.assertEqual(len(list(output.glob('*.enc'))),1)
            data=self.status().json();self.assertEqual(data['jobs'][0]['state'],'completed');self.assertIsNotNone(data['worker']['last_pass'])
            schedule=self.post('/api/platform/backup-policy',dict(expected_revision=0,enabled=True,interval_hours=24,**self.authorization));self.assertEqual(schedule.status_code,200,schedule.text)
            first=platform_worker.run_once(self.server.database,self.server.DB_PATH);self.assertEqual(first['backup']['state'],'completed')
            second=platform_worker.run_once(self.server.database,self.server.DB_PATH);self.assertEqual(second['backup']['state'],'idle')
            self.assertEqual(len(list(output.glob('*.enc'))),2)

    def test_restored_or_revoked_job_does_not_run(self):
        root=Path(self.temp.name);key=root/'key';private_crypto.generate(key);folder=root/'output';folder.mkdir()
        with patch.dict(os.environ,{'EDGEOPS_PRIVATE_KEY_FILE':str(key),'EDGEOPS_PROTECTED_BACKUP_DIR':str(folder),'EDGEOPS_SMTP_HOST':''}):
            self.post('/api/platform/backup-jobs',dict(request_key='b'*32,**self.authorization))
            with self.server.database() as db:db.execute('UPDATE platform_backup_jobs SET creator_revision=999')
            result=platform_worker.run_once(self.server.database,self.server.DB_PATH);self.assertEqual(result['backup']['state'],'cancelled');self.assertEqual(list(folder.iterdir()),[])

    def test_pending_backup_cancellation_does_not_run_a_job(self):
        root=Path(self.temp.name);key=root/'cancel.key';private_crypto.generate(key)
        with patch.dict(os.environ,dict(EDGEOPS_PRIVATE_KEY_FILE=str(key),EDGEOPS_PROTECTED_BACKUP_DIR=str(root))):
            queued=self.post('/api/platform/backup-jobs',dict(request_key='c'*32,**self.authorization));self.assertEqual(queued.status_code,200,queued.text)
            identity=queued.json()['id'];route='/api/platform/backup-jobs/'+identity+'/cancel'
            self.login('operator');self.assertEqual(self.post(route,self.authorization).status_code,403)
            self.login('admin');self.assertEqual(self.post(route,self.authorization).status_code,200)
            self.assertEqual(self.post(route,self.authorization).status_code,409)
            self.assertEqual(platform_worker.backup_pass(self.server.database,self.server.DB_PATH)['state'],'idle')
            self.assertFalse(list(root.glob('*.enc')))
