from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import unittest
import json
import httpx
import test_acquisition_registry as fixture
from test_bench_ingress import frame, gateway


class OperationalTests(unittest.TestCase):
    login=fixture.AcquisitionRegistryApiTests.login
    post=fixture.AcquisitionRegistryApiTests.post

    def setUp(self):
        fixture.AcquisitionRegistryApiTests.setUp(self)
        self.http.base_url=httpx.URL('https://testserver')
        self.timestamp=datetime.now(timezone.utc).isoformat(timespec='microseconds')
        with self.server.database() as db:
            db.execute('INSERT INTO users(email,password_hash,role) VALUES(?,?,?)',('reviewer@example.invalid',self.server.password_hash(self.password),'admin'))
            self.technician=db.execute("SELECT id FROM users WHERE role='operator'").fetchone()[0]
        credential=self.post('/api/bench/credentials',dict(label='Isolated operational fixture',device_id='motor-001',lifetime_minutes=60,current_password=self.password,reason='Configure an isolated software fixture with no hardware.'))
        self.assertEqual(credential.status_code,201,credential.text);self.token=credential.json()['token']
        self.authorization=dict(current_password=self.password,reason='Create an explicit isolated observation review policy.')
        response=self.post('/api/operational/assets',dict(site_id='test-site',asset_id='test-asset',device_id='motor-001',label='Isolated fixture motor',source_type='software-fixture',**self.authorization))
        self.assertEqual(response.status_code,201,response.text);self.asset=response.json()['asset']

    def rule(self,**changes):
        body=dict(asset=self.asset['id'],expected_asset_revision=1,channel='temperature_c',comparison='above',threshold=25.0,window_frames=60,max_age_seconds=30,enabled=True,**self.authorization)
        body.update(changes);response=self.post('/api/operational/rules',body)
        self.assertEqual(response.status_code,201,response.text);return response.json()['rule']

    def ingest(self,index=0,source='software-fixture',**changes):
        fields=frame();fields.update(changes)
        body=gateway.sample(fields,'a'*32,index,source)
        body['gateway_received_at']=self.timestamp
        return self.http.post('/api/bench/readings',json=body,headers={'authorization':'Bearer '+self.token})

    def summary(self):return self.http.get('/api/operational/summary').json()

    def action(self,kind,row,action,**changes):
        body=dict(expected_revision=row['revision'],action=action,note='Explicit isolated review decision for software testing.',evidence_refs='')
        body.update(changes);return self.post('/api/operational/'+kind+'/'+row['id']+'/action',body)

    def order(self,case):
        return self.post('/api/operational/orders',dict(case_id=case['id'],expected_case_revision=case['revision'],request_key='d'*32,title='Inspect fixture evidence',procedure='Review the captured software evidence without any equipment action.',technician_id=self.technician))

    def test_opt_in_atomic_dedup_conflict_and_source_isolation(self):
        self.assertEqual(self.ingest(temp_c=40).status_code,201);self.assertEqual(self.summary()['cases'],[])
        self.rule()
        self.assertEqual(self.ingest(temp_c=40).status_code,200);self.assertEqual(self.summary()['cases'],[],'No retroactive evaluation')
        self.assertEqual(self.ingest(1,temp_c=40).status_code,201)
        self.assertEqual(self.ingest(1,temp_c=40).status_code,200)
        self.assertEqual(self.ingest(1,temp_c=41).status_code,409)
        case=self.summary()['cases'][0]
        self.assertEqual(case['matched_records'],1);self.assertEqual(case['source_type'],'software-fixture')
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM synthetic_incidents').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM operational_evaluations').fetchone()[0],1)
        self.assertFalse(self.summary()['equipment_authorized'])

    def test_null_invalid_zero_and_partitioned_sources(self):
        self.rule(threshold=-1.0)
        self.assertEqual(self.ingest(ds18b20_valid=False,valid=False,temp_c=0).status_code,201)
        self.assertEqual(self.summary()['cases'],[])
        self.assertEqual(self.ingest(1,temp_c=0).status_code,201)
        self.assertEqual(self.summary()['cases'][0]['last_snapshot']['value'],0)
        body=gateway.sample(frame(),'b'*32,0,'measured-unverified')
        body['frame']['temp_c']=40
        self.assertEqual(self.http.post('/api/bench/readings',json=body,headers={'authorization':'Bearer '+self.token}).status_code,201)
        self.assertEqual(len(self.summary()['cases']),1,'Fixture rule cannot consume measured-unverified source')

    def test_concurrent_retries_and_frame_buckets(self):
        self.rule()
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda _:self.ingest(temp_c=40).status_code,range(2)))
        self.assertEqual(sorted(codes),[200,201])
        self.assertEqual(self.ingest(1,temp_c=40).status_code,201)
        self.assertEqual(self.ingest(60,temp_c=40).status_code,201)
        cases=self.summary()['cases'];self.assertEqual(len(cases),2);self.assertEqual(sum(c['matched_records'] for c in cases),3)

    def test_independent_order_lifecycle_and_physical_boundaries(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        case=self.summary()['cases'][0]
        response=self.post('/api/operational/cases/'+case['id']+'/assign',dict(expected_revision=1,assignee_id=self.technician,**self.authorization))
        self.assertEqual(response.status_code,200,response.text);case=response.json()['record']
        order=self.order(case);self.assertEqual(order.status_code,201,order.text);order=order.json()['record']
        self.assertEqual(self.order(case).status_code,200)
        response=self.action('orders',order,'submit');self.assertEqual(response.status_code,200,response.text);order=response.json()['record']
        self.assertEqual(self.action('orders',order,'approve').status_code,403)
        self.login('reviewer');response=self.action('orders',order,'approve');self.assertEqual(response.status_code,200,response.text);order=response.json()['record']
        self.assertEqual(self.action('orders',order,'start').status_code,403)
        self.login('operator');response=self.action('orders',order,'start');self.assertEqual(response.status_code,200,response.text);order=response.json()['record']
        self.assertEqual(self.action('orders',order,'complete').status_code,422)
        response=self.action('orders',order,'complete',evidence_refs='fixture evidence only');self.assertEqual(response.status_code,200,response.text);order=response.json()['record']
        self.login('admin');self.assertEqual(self.action('orders',order,'verify',evidence_refs='reviewed fixture').status_code,403)
        self.login('reviewer');response=self.action('orders',order,'verify',evidence_refs='reviewed fixture');self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['record']['state'],'closed');self.assertFalse(response.json()['physical_work_verified'])
        history=self.http.get('/api/operational/order/'+order['id']+'/history').json()['events'];self.assertEqual(len(history),6)

    def test_roles_csrf_revisions_retire_and_revoked_policy(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        case=self.summary()['cases'][0]
        self.assertEqual(self.action('cases',case,'acknowledge',expected_revision=99).status_code,409)
        self.assertEqual(self.post('/api/operational/cases/'+case['id']+'/action',dict(action='acknowledge',expected_revision=1,note='Missing CSRF should refuse this change.'),False).status_code,403)
        self.login('operator');self.assertEqual(self.summary()['cases'],[])
        self.login('auditor');self.assertEqual(self.action('cases',case,'acknowledge').status_code,403)
        self.login('admin')
        with self.server.database() as db:db.execute('UPDATE operational_rules SET issuer_revision=999')
        self.assertEqual(self.ingest(1,temp_c=40).status_code,201);self.assertEqual(self.summary()['cases'][0]['matched_records'],1)
        response=self.post('/api/operational/assets/'+self.asset['id']+'/retire',dict(expected_revision=1,**self.authorization))
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(self.summary()['rules'][0]['enabled'],0)

    def test_capacity_failure_rolls_back_reading_for_gateway_retry(self):
        self.rule()
        from unittest.mock import patch
        import operational_workflow
        def broken(*args,**kwargs):raise RuntimeError('fixture history unavailable')
        with patch.object(operational_workflow,'event',side_effect=broken):
            with self.assertRaises(RuntimeError):self.ingest(temp_c=40)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM bench_samples').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM operational_cases').fetchone()[0],0)
        self.assertEqual(self.ingest(temp_c=40).status_code,201)

    def test_work_context_is_frozen_while_case_receives_more_readings(self):
        self.rule();self.ingest(temp_c=40)
        case=self.summary()['cases'][0];response=self.order(case)
        self.assertEqual(response.status_code,201,response.text);order=response.json()['record']
        self.assertEqual(json.loads(order['case_snapshot']['last_snapshot'])['value'],40)
        self.assertEqual(self.ingest(1,temp_c=70).status_code,201)
        summary=self.summary()
        self.assertEqual(summary['cases'][0]['last_snapshot']['value'],70)
        frozen=summary['orders'][0]
        self.assertEqual(json.loads(frozen['case_snapshot']['last_snapshot'])['value'],40)
        self.assertEqual(frozen['case_snapshot_sha256'],order['case_snapshot_sha256'])
        with self.server.database() as db:db.execute("UPDATE operational_orders SET case_snapshot='{}'")
        self.assertEqual(self.http.get('/api/operational/summary').status_code,503)
