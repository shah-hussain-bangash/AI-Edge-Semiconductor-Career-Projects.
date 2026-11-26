"""Disposable continuous runner, locking and authenticated report tests."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import httpx
from edge_delivery import Spool
import service_delivery_runner as runner
import recovery
import test_service_credentials as fixture


class NoWait:
    def is_set(self):return False
    def wait(self, seconds):return False


class ServiceRunnerTests(unittest.TestCase):
    login = fixture.ServiceCredentialTests.login
    post = fixture.ServiceCredentialTests.post
    issue = fixture.ServiceCredentialTests.issue
    revoke = fixture.ServiceCredentialTests.revoke
    envelope = fixture.ServiceCredentialTests.envelope

    def setUp(self):
        fixture.ServiceCredentialTests.setUp(self)
        self.issued = self.issue().json();self.token = self.issued['token']

    def body(self, **changes):
        return {'run_id':'a'*32,'sequence':0,'state':'running','interval_seconds':1,
                'passes':0,'attempts':0,'pass_errors':0,'last_outcome':'not-attempted',**changes}

    def heartbeat(self, body):
        return self.edge.post('/api/edge/heartbeat', json=body,
                              headers={'Authorization':'Bearer '+self.token})

    def test_report_retries_are_idempotent_and_no_observation_is_created(self):
        first = self.heartbeat(self.body());self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json(),self.heartbeat(self.body()).json())
        self.assertEqual(self.heartbeat(self.body(last_outcome='idle')).status_code,409)
        self.assertEqual(self.heartbeat(self.body(sequence=1,passes=1,last_outcome='idle')).status_code,200)
        self.assertEqual(self.heartbeat(self.body(sequence=2,passes=0)).status_code,409)
        report=self.http.get('/api/service-runners').json()
        self.assertEqual(report['runners'][0]['observation'],'recent-heartbeat')
        self.assertFalse(report['production_ready']);self.assertNotIn(self.token,json.dumps(report))
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM service_runner_reports').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0],0)

    def test_competing_run_lease_stopped_restart_and_expired_lease(self):
        self.assertEqual(self.heartbeat(self.body()).status_code,200)
        self.assertEqual(self.heartbeat(self.body(run_id='b'*32)).status_code,409)
        stopped=self.body(sequence=1,state='stopped')
        self.assertEqual(self.heartbeat(stopped).status_code,200)
        self.assertEqual(self.heartbeat(stopped).status_code,200)
        self.assertEqual(self.heartbeat(self.body(sequence=2)).status_code,409)
        self.assertEqual(self.heartbeat(self.body(run_id='b'*32)).status_code,200)
        with self.server.database() as db:db.execute('UPDATE service_runner_reports SET lease_until=0')
        self.assertEqual(self.http.get('/api/service-runners').json()['runners'][0]['observation'],'heartbeat-stale')
        self.assertEqual(self.heartbeat(self.body(run_id='c'*32)).status_code,200)

    def test_revocation_contract_and_reader_authentication(self):
        self.assertEqual(self.heartbeat(self.body(attempts=1)).status_code,422)
        self.assertEqual(self.heartbeat(self.body(credential_id='invented')).status_code,422)
        self.assertEqual(self.edge.post('/api/edge/heartbeat',json=self.body()).status_code,401)
        self.heartbeat(self.body());self.revoke(self.issued['credential'])
        self.assertEqual(self.heartbeat(self.body(sequence=1)).status_code,401)
        self.assertEqual(self.http.get('/api/service-runners').json()['runners'][0]['observation'],'credential-inactive')
        for role in ('operator','auditor'):
            self.login(role);self.assertEqual(self.http.get('/api/service-runners').status_code,200)
        self.http.cookies.clear();self.assertEqual(self.http.get('/api/service-runners').status_code,401)

    def test_os_lock_rejects_duplicate_and_releases_after_abrupt_exit(self):
        path=Path(self.temp.name)/'lock-test.sqlite3'
        with runner.RunnerLock(path):
            with self.assertRaises(RuntimeError):
                with runner.RunnerLock(path):pass
        command='import os,sys;from service_delivery_runner import RunnerLock;lock=RunnerLock(sys.argv[1]);lock.__enter__();os._exit(0)'
        subprocess.run([sys.executable,'-c',command,str(path)],check=True,cwd=Path(__file__).resolve().parents[1])
        with runner.RunnerLock(path):pass

    def client_factory(self, handler=None):
        original=httpx.Client
        def dispatch(request):
            if handler:
                response=handler(request)
                if response is not None:return response
            return self.edge.post(request.url.path,content=request.content,
                headers={'Authorization':request.headers['authorization'],'content-type':'application/json'})
        return lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(dispatch))

    def test_finite_runner_delivers_two_events_and_reports_stop(self):
        path=Path(self.temp.name)/'runner.sqlite3';spool=Spool(path)
        for sequence in (0,1):
            body=self.envelope();body['observation']['sequence']=sequence;spool.enqueue(body)
        with patch.object(runner.httpx,'Client',side_effect=self.client_factory()):
            result=runner.run(path,'http://127.0.0.1:8877',self.token,max_passes=2,interval=1,stop=NoWait())
        self.assertEqual(result['passes'],2);self.assertEqual(result['attempts'],2)
        self.assertEqual(result['stop_reason'],'pass-limit');self.assertEqual(spool.status()['counts']['delivered'],2)
        row=self.http.get('/api/service-runners').json()['runners'][0]
        self.assertEqual(row['observation'],'reported-stopped');self.assertEqual(row['attempts'],2)

    def test_lost_heartbeat_response_reconciles_without_duplicate_work(self):
        path=Path(self.temp.name)/'lost-report.sqlite3';Spool(path).enqueue(self.envelope())
        lost=[False]
        def handler(request):
            if request.url.path=='/api/edge/heartbeat' and not lost[0]:
                lost[0]=True
                self.edge.post(request.url.path,content=request.content,headers={
                    'Authorization':request.headers['authorization'],'content-type':'application/json'})
                raise httpx.ReadTimeout('simulated response loss')
        with patch.object(runner.httpx,'Client',side_effect=self.client_factory(handler)):
            result=runner.run(path,'http://127.0.0.1:8877',self.token,max_passes=1,interval=1,stop=NoWait())
        self.assertEqual(result['attempts'],1);self.assertEqual(result['stop_reason'],'pass-limit')
        self.assertEqual(Spool(path).status()['counts']['delivered'],1)

    def test_unavailable_reports_never_claim_queue_and_stop_at_budget(self):
        path=Path(self.temp.name)/'unavailable.sqlite3';spool=Spool(path);spool.enqueue(self.envelope())
        def unavailable(request):return httpx.Response(503,json={'detail':'test outage'})
        with patch.object(runner.httpx,'Client',side_effect=self.client_factory(unavailable)):
            result=runner.run(path,'http://127.0.0.1:8877',self.token,max_passes=1,interval=1,
                              failure_budget=2,stop=NoWait())
        self.assertEqual(result['passes'],0);self.assertEqual(result['stop_reason'],'heartbeat-failure-budget')
        self.assertEqual(spool.status()['records'][0]['attempts'],0)

    def test_local_pass_failures_are_bounded_and_sanitized(self):
        path=Path(self.temp.name)/'pass-error.sqlite3'
        with patch.object(runner.httpx,'Client',side_effect=self.client_factory()),patch.object(
                runner,'run_once',side_effect=RuntimeError('private:'+self.token)):
            result=runner.run(path,'http://127.0.0.1:8877',self.token,max_passes=10,
                              interval=1,failure_budget=2,stop=NoWait())
        self.assertEqual(result['passes'],2);self.assertEqual(result['pass_errors'],2)
        self.assertEqual(result['stop_reason'],'pass-error-budget');self.assertNotIn(self.token,json.dumps(result))

    def test_malformed_success_report_never_authorizes_a_queue_claim(self):
        path=Path(self.temp.name)/'bad-report.sqlite3';spool=Spool(path);spool.enqueue(self.envelope())
        def bad_receipt(request):return httpx.Response(200,json={
            'scope':'local-synthetic-runner-status','production_ready':False})
        with patch.object(runner.httpx,'Client',side_effect=self.client_factory(bad_receipt)):
            result=runner.run(path,'http://127.0.0.1:8877',self.token,max_passes=1,interval=1,
                              failure_budget=2,stop=NoWait())
        self.assertEqual(result['passes'],0);self.assertEqual(spool.status()['records'][0]['attempts'],0)

    def test_revocation_between_passes_stops_without_claiming_more_work(self):
        path=Path(self.temp.name)/'revoked.sqlite3';spool=Spool(path)
        for sequence in (0,1):
            body=self.envelope();body['observation']['sequence']=sequence;spool.enqueue(body)
        def revoke_after_commit(request):
            if request.url.path=='/api/edge/observations':
                response=self.edge.post(request.url.path,content=request.content,headers={
                    'Authorization':request.headers['authorization'],'content-type':'application/json'})
                self.revoke(self.issued['credential']);return response
        with patch.object(runner.httpx,'Client',side_effect=self.client_factory(revoke_after_commit)):
            result=runner.run(path,'http://127.0.0.1:8877',self.token,max_passes=10,interval=1,stop=NoWait())
        self.assertEqual(result['attempts'],1);self.assertEqual(result['stop_reason'],'credential-or-runner-lease-denied')
        self.assertEqual(spool.status()['counts']['pending'],1)


    def test_restore_preserves_reports_but_revokes_report_credentials(self):
        self.heartbeat(self.body())
        root=Path(self.temp.name)
        recovery.create_backup(self.server.DB_PATH,root/'backup')
        result=recovery.restore_backup(root/'backup',root/'restored')
        self.assertEqual(result['service_credentials_revoked'],1)
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(root/'restored'/'dashboard.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM service_runner_reports').fetchone()[0],1)
            self.assertIsNotNone(db.execute('SELECT revoked_at FROM service_credentials').fetchone()[0])


if __name__=='__main__':unittest.main()
