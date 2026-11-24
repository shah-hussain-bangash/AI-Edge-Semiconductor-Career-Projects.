"""Worker connection boundaries using a mock HTTP transport, never external hosts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
import delivery_worker
from edge_delivery import Spool, identity
from test_delivery import envelope


class DeliveryWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='edgeops-worker-')
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'spool.sqlite3'

    def client(self,handler,options):
        actual=httpx.Client
        def factory(**kwargs):
            options.append(kwargs.copy())
            return actual(**kwargs,transport=httpx.MockTransport(handler))
        return patch.object(delivery_worker.httpx,'Client',side_effect=factory)

    def test_invalid_origins_fail_before_client_or_spool_creation(self):
        targets=('http://example.invalid','https://127.0.0.1','http://user:pass@localhost',
                 'http://@localhost','http://localhost/path','http://localhost?query=1',
                 'http://localhost#fragment','http://127.0.0.1:not-a-port',
                 'http://localhost:0','http://localhost:65536','http://[::1',
                 ' http://localhost','http://local\nhost','',None)
        for target in targets:
            with self.subTest(target=target),patch.object(delivery_worker.httpx,'Client') as client:
                with self.assertRaisesRegex(ValueError,'explicit loopback HTTP origin'):
                    delivery_worker.run_once(self.path,target,'test@example.invalid','test-only')
                client.assert_not_called()
                self.assertFalse(self.path.exists())

    def test_valid_loopback_origins_keep_redirect_and_proxy_protection(self):
        for index,origin in enumerate(('http://127.0.0.1:8877','http://localhost:8877','http://[::1]:8877')):
            with self.subTest(origin=origin):
                path=Path(self.temp.name)/(str(index)+'.sqlite3');Spool(path).enqueue(envelope())
                calls=[];options=[]
                def handler(request):
                    calls.append(request)
                    if request.url.path=='/api/auth/login':
                        return httpx.Response(200,headers={'set-cookie':'edgeops_csrf=test-csrf; Path=/'},json={})
                    if request.url.path=='/api/acquisition/ingest':
                        key,digest=identity(json.loads(request.content))
                        self.assertEqual(request.headers['x-edgeops-csrf'],'test-csrf')
                        return httpx.Response(201,json={'tier':'central-committed','event_key':key,
                            'content_hash':digest,'receipt_id':'a'*32,'committed_at':'2026-11-24T10:00:00Z'})
                    return httpx.Response(200,json={})
                with self.client(handler,options):
                    self.assertTrue(delivery_worker.run_once(path,origin,'test@example.invalid','test-only')['attempted'])
                self.assertEqual(Spool(path).status()['counts']['delivered'],1)
                self.assertEqual([request.url.path for request in calls],
                                 ['/api/auth/login','/api/acquisition/ingest','/api/auth/logout'])
                self.assertFalse(options[0]['follow_redirects']);self.assertFalse(options[0]['trust_env'])

    def test_login_redirect_never_contacts_redirect_target(self):
        calls=[];options=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(307,headers={'location':'https://external.invalid/collect'})
        with self.client(handler,options):
            with self.assertRaises(httpx.HTTPStatusError):
                delivery_worker.run_once(self.path,'http://127.0.0.1:8877','test@example.invalid','test-only')
        self.assertEqual(len(calls),1);self.assertEqual(calls[0].url.host,'127.0.0.1')
        self.assertFalse(self.path.exists())

    def test_ingest_redirect_retains_queue_and_logs_out_at_original_origin(self):
        Spool(self.path).enqueue(envelope());calls=[];options=[]
        def handler(request):
            calls.append(request)
            if request.url.path=='/api/auth/login':
                return httpx.Response(200,headers={'set-cookie':'edgeops_csrf=test-csrf; Path=/'},json={})
            if request.url.path=='/api/acquisition/ingest':
                return httpx.Response(307,headers={'location':'https://external.invalid/collect'})
            return httpx.Response(200,json={})
        with self.client(handler,options):
            delivery_worker.run_once(self.path,'http://127.0.0.1:8877','test@example.invalid','test-only')
        self.assertEqual([request.url.host for request in calls],['127.0.0.1']*3)
        self.assertEqual(calls[-1].url.path,'/api/auth/logout')
        row=Spool(self.path).status()['records'][0]
        self.assertEqual((row['state'],row['last_error']),('pending','http-307'))
        self.assertIsNone(row['receipt'])

    def test_cli_invalid_port_has_no_traceback_or_credential_disclosure(self):
        result=subprocess.run([sys.executable,str(Path(delivery_worker.__file__)),
            '--spool',str(self.path),'--server','http://127.0.0.1:not-a-port'],capture_output=True,text=True,
            env={**os.environ,'EDGEOPS_DELIVERY_EMAIL':'private-test-marker@example.invalid',
                 'EDGEOPS_DELIVERY_PASSWORD':'private-test-marker-password'})
        self.assertEqual(result.returncode,1)
        self.assertIn('Delivery worker unavailable',result.stderr)
        self.assertNotIn('Traceback',result.stderr)
        self.assertNotIn('private-test-marker',result.stdout+result.stderr)
        self.assertFalse(self.path.exists())
