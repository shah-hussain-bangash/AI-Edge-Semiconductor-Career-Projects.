from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx
import bench_ingress as bench
import test_acquisition_registry as fixture

spec=importlib.util.spec_from_file_location('mac_gateway',Path(__file__).resolve().parents[2]/'mac-gateway/gateway.py')
gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(gateway)


def frame(**changes):
    return dict(schema_version=1,device_id='motor-001',seq=1,uptime_ms=1000,ax_mps2=0,ay_mps2=0,az_mps2=9.8,
        temp_c=23.0,bus_v=0,current_ma=0,adxl345_valid=True,ds18b20_valid=True,ina219_valid=True,valid=True,**changes)


class BenchTests(unittest.TestCase):
    login=fixture.AcquisitionRegistryApiTests.login
    post=fixture.AcquisitionRegistryApiTests.post
    def setUp(self):
        fixture.AcquisitionRegistryApiTests.setUp(self)
        self.http.base_url=httpx.URL('https://testserver')
        self.body=gateway.sample(frame(),'1'*32,0,'software-fixture')
        response=self.post('/api/bench/credentials',dict(label='Disposable Mac gateway',device_id='motor-001',lifetime_minutes=60,current_password=self.password,reason='Authorize a disposable sensor-only software integration rehearsal.'))
        self.assertEqual(response.status_code,201,response.text)
        self.token=response.json()['token'];self.credential=response.json()['credential']

    def ingest(self,body=None,token=None):
        return self.http.post('/api/bench/readings',json=body or self.body,headers={'authorization':'Bearer '+(token or self.token)})

    def test_retry_dedup_zero_values_source_and_no_synthetic_effect(self):
        self.assertEqual(self.ingest().status_code,201);self.assertEqual(self.ingest().status_code,200)
        data=self.http.get('/api/bench/readings').json();self.assertEqual(data['total_in_run'],1)
        item=data['items'][0];self.assertEqual(item['values']['current_a'],0);self.assertEqual(item['values']['acceleration_x_mps2'],0)
        self.assertEqual(item['source_type'],'software-fixture');self.assertFalse(item['production_ready']);self.assertIsNone(item['device_boot_id'])
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM synthetic_incidents').fetchone()[0],0)

    def test_concurrent_retries_commit_one_record(self):
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda _:self.ingest().status_code,range(2)))
        self.assertEqual(sorted(codes),[200,201])

    def test_remote_plain_http_is_refused_and_https_is_accepted(self):
        from fastapi.testclient import TestClient
        headers={'authorization':'Bearer '+self.token}
        with TestClient(self.server.app,base_url='http://portal.invalid',client=('203.0.113.1',1234)) as client:
            self.assertEqual(client.post('/api/bench/readings',json=self.body,headers=headers).status_code,403)
        with TestClient(self.server.app,base_url='https://portal.invalid',client=('203.0.113.1',1234)) as client:
            self.assertEqual(client.post('/api/bench/readings',json=self.body,headers=headers).status_code,201)

    def test_modified_identity_preserves_original(self):
        self.ingest();changed=json.loads(json.dumps(self.body));changed['frame']['temp_c']=40
        self.assertEqual(self.ingest(changed).status_code,409)
        self.assertEqual(self.http.get('/api/bench/readings').json()['items'][0]['values']['temperature_c'],23)

    def test_invalid_sensor_groups_are_null_and_milliamps_convert_once(self):
        body=json.loads(json.dumps(self.body));body['frame'].update(ds18b20_valid=False,valid=False,current_ma=250,temp_c=0)
        self.assertEqual(self.ingest(body).status_code,201)
        values=self.http.get('/api/bench/readings').json()['items'][0]['values']
        self.assertIsNone(values['temperature_c']);self.assertEqual(values['current_a'],0.25)

    def test_device_and_bearer_scope_and_no_cookie_fallback(self):
        self.assertEqual(self.http.post('/api/bench/readings',json=self.body).status_code,401)
        self.assertEqual(self.ingest(token='edgeops_svc_'+'a'*64).status_code,401)
        self.body['frame']['device_id']='other-board';self.assertEqual(self.ingest().status_code,403)

    def test_revocation_account_revision_and_metadata_redaction(self):
        self.assertNotIn(self.token,self.http.get('/api/bench/credentials').text)
        body=dict(expected_revision=1,current_password=self.password,reason='Revoke the disposable scoped gateway credential.')
        self.assertEqual(self.post('/api/bench/credentials/'+self.credential['id']+'/revoke',body).status_code,200)
        self.assertEqual(self.ingest().status_code,401)

    def test_issuer_revision_and_expiry(self):
        with self.server.database() as db:db.execute('UPDATE bench_credentials SET issuer_revision=99')
        self.assertEqual(self.ingest().status_code,401)
        with self.server.database() as db:db.execute('UPDATE bench_credentials SET issuer_revision=1,expires_at=1')
        self.assertEqual(self.ingest().status_code,401)

    def test_issue_role_password_csrf_and_read_access(self):
        payload=dict(label='Refused gateway',device_id='motor-001',lifetime_minutes=60,current_password=self.password,reason='Check protected issuance for this disposable gateway.')
        self.assertEqual(self.post('/api/bench/credentials',payload,False).status_code,403)
        payload['current_password']='wrong';self.assertEqual(self.post('/api/bench/credentials',payload).status_code,403)
        self.login('operator');self.assertEqual(self.post('/api/bench/credentials',payload).status_code,403)
        self.assertEqual(self.http.get('/api/bench/readings').status_code,200)
        self.assertEqual(self.http.get('/api/bench/credentials').status_code,403)

    def test_bad_frames_times_and_capacity(self):
        invalid=json.loads(json.dumps(self.body));invalid['frame']['valid']='true'
        self.assertEqual(self.ingest(invalid).status_code,422)
        invalid=json.loads(json.dumps(self.body));invalid['gateway_received_at']='2026-01-01T00:00:00'
        self.assertEqual(self.ingest(invalid).status_code,422)
        with patch.object(bench,'MAX_RECORDS',0):self.assertEqual(self.ingest().status_code,429)
        self.assertEqual(self.http.get('/api/bench/readings').json()['total_in_run'],0)

    def test_stored_payload_integrity_and_restore_revocation(self):
        self.ingest()
        import recovery
        root=Path(self.temp.name);recovery.create_backup(self.server.DB_PATH,root/'backup')
        report=recovery.restore_backup(root/'backup',root/'restored')
        self.assertEqual(report['bench_credentials_revoked'],1)
        with self.server.database() as db:db.execute("UPDATE bench_samples SET payload_json='{}'")
        self.assertEqual(self.http.get('/api/bench/readings').status_code,503)


class GatewayTests(unittest.TestCase):
    def test_config_rejects_remote_http_credentials_and_redirect_shapes(self):
        token='edgeops_bench_'+'1'*64
        for url in ['http://example.com','https://user:pw@example.com','https://example.com/path','https://example.com?token=private']:
            with self.assertRaises(ValueError):gateway.validate_config(dict(portal_url=url,token=token,expected_device_id='motor-001'))
        self.assertEqual(gateway.validate_config(dict(portal_url='https://example.com/',token=token,expected_device_id='motor-001'))['portal_url'],'https://example.com')

    def test_failed_or_invalid_receipts_retain_data_and_matching_retry_drains(self):
        with tempfile.TemporaryDirectory() as directory:
            spool=gateway.Spool(Path(directory)/'spool.sqlite3')
            try:
                body=gateway.sample(frame(),'1'*32,0,'software-fixture');spool.add(body)
                for payload in [None,{},dict(stored=True,scope='unverified-bench-readings',production_ready=False,run_id='1'*32,frame_index=True,content_hash=gateway.digest(body))]:
                    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(201,json=payload)),base_url='https://example.com') as client:self.assertEqual(spool.drain(client)[1],'invalid-portal-receipt')
                    self.assertEqual(spool.db.execute('SELECT count(*) FROM pending').fetchone()[0],1)
                receipt=dict(stored=True,scope='unverified-bench-readings',production_ready=False,run_id=body['run_id'],frame_index=0,content_hash=gateway.digest(body))
                with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(201,json=receipt)),base_url='https://example.com') as client:self.assertEqual(spool.drain(client),(1,'ok'))
                self.assertEqual(spool.db.execute('SELECT count(*) FROM pending').fetchone()[0],0)
            finally:spool.close()

    def test_spool_conflict_capacity_lock_and_restart_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'spool.sqlite3';spool=gateway.Spool(path)
            body=gateway.sample(frame(),'1'*32,0,'software-fixture');spool.add(body);spool.add(body)
            with self.assertRaises(ValueError):gateway.Spool(path)
            altered={**body,'source_type':'measured-unverified'}
            with self.assertRaises(ValueError):spool.add(altered)
            with patch.object(gateway,'MAX_PENDING',1),self.assertRaises(ValueError):spool.add({**body,'frame_index':1})
            spool.close();spool=gateway.Spool(path)
            self.assertEqual(spool.db.execute('SELECT count(*) FROM pending').fetchone()[0],1);spool.close()

    def test_dry_cli_does_not_open_serial(self):
        with self.assertRaises(SystemExit):gateway.main(['--port','not-a-real-port'])

    def test_pending_readings_cannot_be_retargeted_by_configuration_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            spool=gateway.Spool(Path(directory)/'spool.sqlite3')
            config=dict(portal_url='https://original.example',token='edgeops_bench_'+'1'*64,expected_device_id='motor-001')
            try:
                spool.bind(config);spool.add(gateway.sample(frame(),'1'*32,0,'software-fixture'))
                for changed in ({**config,'portal_url':'https://other.example'},{**config,'token':'edgeops_bench_'+'2'*64},{**config,'expected_device_id':'other-device'}):
                    with self.assertRaises(ValueError):spool.bind(changed)
                spool.bind(config)
                self.assertEqual(spool.db.execute('SELECT count(*) FROM pending').fetchone()[0],1)
                self.assertNotIn(config['token'],str(spool.db.execute('SELECT * FROM destination').fetchall()))
            finally:spool.close()


if __name__=='__main__':unittest.main()
