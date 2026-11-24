"""Retained-row and serialized-payload accounting; reads never reclaim capacity."""
from concurrent.futures import ThreadPoolExecutor
import os
import hashlib
import json
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from edge_delivery import Spool,identity
from test_delivery import envelope
import test_acquisition_registry as fixtures


class DeliveryCapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='edgeops-delivery-capacity-');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'spool.sqlite3';self.spool=Spool(self.path)

    def enqueue(self,sequence):
        data=envelope();data['observation']['sequence']=sequence
        return self.spool.enqueue(data)

    def test_default_record_limit_preserves_ten_thousand_existing_events(self):
        self.assertEqual(self.spool.max_rows,10000)
        self.enqueue(0)
        with self.spool.db() as db:
            expected_bytes=len(db.execute('SELECT payload FROM delivery_spool').fetchone()[0].encode('utf-8'))
        rows=[]
        for sequence in range(1,10000):
            sample=envelope();sample['observation']['sequence']=sequence
            key,digest=identity(sample)
            payload=json.dumps(sample,sort_keys=True,separators=(',',':'),allow_nan=False)
            expected_bytes+=len(payload.encode('utf-8'))
            saved_at=1700000000+sequence/1000
            rows.append((key,digest,payload,'pending',0,0,None,None,None,None,saved_at,saved_at))
        # Bulk population isolates the real default admission boundary; this is not an ingest-rate test.
        with self.spool.db() as db:
            db.executemany('INSERT INTO delivery_spool VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',rows)
        def snapshot_hash():
            digest=hashlib.sha256()
            with self.spool.db() as db:
                for row in db.execute('SELECT * FROM delivery_spool ORDER BY event_key'):
                    digest.update((json.dumps(tuple(row),separators=(',',':'))+'\n').encode('utf-8'))
            return digest.hexdigest()
        before=snapshot_hash();status=self.spool.status()
        self.assertEqual(status['usage'],{'records':10000,'payload_bytes':expected_bytes})
        self.assertLess(expected_bytes,status['limits']['payload_bytes'])
        self.assertEqual(status['counts']['pending'],10000)
        self.assertFalse(self.spool.enqueue(envelope())['created'])
        sample=envelope();sample['observation']['sequence']=10000
        with self.assertRaises(OverflowError):self.spool.enqueue(sample)
        restarted=Spool(self.path)
        after=restarted.status()
        self.assertEqual(after['usage'],status['usage']);self.assertEqual(after['counts'],status['counts'])
        self.assertEqual(snapshot_hash(),before)
        with self.spool.db() as db:self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
        self.default_capacity_evidence={
            'configured_record_limit':status['limits']['records'],
            'configured_payload_byte_limit':status['limits']['payload_bytes'],
            'retained_records':after['usage']['records'],'retained_payload_bytes':after['usage']['payload_bytes'],
            'duplicate_retry_created_record':False,'additional_event_rejected':True,
            'all_saved_rows_unchanged':True,'restart_preserved_counts_and_usage':True,
            'sqlite_quick_check':'ok',
            'fixture_population':'One normal enqueue plus 9,999 bulk-inserted valid synthetic rows; not 10,000 API ingests or a throughput/soak test.'}

    def test_empty_capacity_and_stored_utf8_byte_accounting(self):
        self.assertEqual(self.spool.status()['usage'],{'records':0,'payload_bytes':0})
        self.enqueue(0);self.enqueue(1)
        with self.spool.db() as db:
            # Deliberate storage-only fixture: accounting measures bytes, not character count.
            db.execute('UPDATE delivery_spool SET payload=? WHERE event_key=(SELECT MIN(event_key) FROM delivery_spool)',('é温',))
            payloads=[row[0] for row in db.execute('SELECT payload FROM delivery_spool')]
        expected=sum(len(value.encode('utf-8')) for value in payloads)
        self.assertEqual(self.spool.status()['usage'],{'records':2,'payload_bytes':expected})
        self.assertNotEqual(expected,sum(len(value) for value in payloads))

    def test_delivered_and_blocked_rows_remain_in_global_usage_across_filters_and_pages(self):
        for sequence in range(3):self.enqueue(sequence)
        before=self.spool.status()['usage']
        claim=self.spool.claim()
        self.spool.finish(claim,receipt={'tier':'central-committed','event_key':claim['event_key'],'content_hash':claim['content_hash'],'receipt_id':'a'*32,'committed_at':'2026-11-24T10:00:00Z'})
        self.spool.finish(self.spool.claim(),error='http-403',permanent=True)
        for state in ('','pending','inflight','delivered','blocked'):
            data=self.spool.status(state=state,limit=1)
            self.assertEqual(data['usage'],before);self.assertEqual(sum(data['counts'].values()),3)
        first=self.spool.status(limit=1)
        self.assertEqual(self.spool.status(before=first['page']['next_before'],limit=1)['usage'],before)

    def test_identical_retry_and_capacity_rejection_do_not_increase_usage(self):
        self.enqueue(0);before=self.spool.status()['usage']
        capped=Spool(self.path,max_rows=1)
        self.assertFalse(capped.enqueue(envelope())['created'])
        sample=envelope();sample['observation']['sequence']=1
        with self.assertRaises(OverflowError):capped.enqueue(sample)
        self.assertEqual(capped.status()['usage'],before)
        self.assertEqual(capped.status()['limits']['records'],1)

    def test_exact_payload_limit_and_reduced_profile_preserve_reported_usage(self):
        self.enqueue(0);before=self.spool.status()['usage']
        exact=Spool(self.path,max_bytes=before['payload_bytes'])
        self.assertFalse(exact.enqueue(envelope())['created'])
        sample=envelope();sample['observation']['sequence']=1
        with self.assertRaises(OverflowError):exact.enqueue(sample)
        self.assertEqual(exact.status()['usage'],before)
        reduced=Spool(self.path,max_bytes=1)
        self.assertGreater(reduced.status()['usage']['payload_bytes'],reduced.status()['limits']['payload_bytes'])
        self.assertEqual(reduced.status()['usage'],before)


class DeliveryCapacityApiTests(unittest.TestCase):
    login=fixtures.AcquisitionRegistryApiTests.login
    post=fixtures.AcquisitionRegistryApiTests.post
    def setUp(self):
        fixtures.AcquisitionRegistryApiTests.setUp(self)
        self.path=Path(self.temp.name)/'capacity-spool.sqlite3'
        env=patch.dict(os.environ,{'EDGEOPS_DELIVERY_SPOOL_DB':str(self.path)});env.start();self.addCleanup(env.stop)
        self.spool=Spool(self.path)
        for sequence in range(2):
            data=envelope();data['observation']['sequence']=sequence;self.spool.enqueue(data)

    def populate_central(self,count):
        self.assertEqual(self.post('/api/acquisition-bindings',fixtures.binding()).status_code,201)
        first=self.post('/api/acquisition/ingest',envelope())
        self.assertEqual(first.status_code,201);original_receipt=first.json()
        prefix='0' if original_receipt['receipt_id'][0]!='0' else '1'
        rows=[]
        for sequence in range(1,count):
            sample=envelope();sample['observation']['sequence']=sequence
            key,digest=identity(sample)
            rows.append((key,digest,sample['observation']['device_id'],sample['binding_revision'],
                         json.dumps(sample,sort_keys=True),prefix+f'{sequence:031x}',
                         '2026-11-24T10:00:00+00:00','bulk-fixture@example.invalid'))
        with self.server.database() as db:
            db.executemany('INSERT INTO acquisition_observations VALUES(?,?,?,?,?,?,?,?)',rows)
        return original_receipt

    def central_snapshot_hash(self,exclude=None):
        digest=hashlib.sha256()
        query='SELECT * FROM acquisition_observations'+(' WHERE event_key<>?' if exclude else '')+' ORDER BY event_key'
        with self.server.database() as db:
            for row in db.execute(query,(exclude,) if exclude else ()):
                digest.update((json.dumps(tuple(row),separators=(',',':'))+'\n').encode('utf-8'))
        return digest.hexdigest()

    def test_full_central_store_preserves_duplicate_receipt_and_edge_backpressure(self):
        original_receipt=self.populate_central(10000)
        with self.server.database() as db:original_audit_count=db.execute('SELECT count(*) FROM audit').fetchone()[0]
        before=self.central_snapshot_hash()
        duplicate=self.post('/api/acquisition/ingest',envelope())
        self.assertEqual(duplicate.status_code,200);self.assertEqual(duplicate.json(),original_receipt)
        sample=envelope();sample['observation']['sequence']=10000
        rejected=self.post('/api/acquisition/ingest',sample)
        self.assertEqual(rejected.status_code,429);self.assertNotIn('receipt_id',rejected.json())
        edge=Spool(Path(self.temp.name)/'full-central-edge.sqlite3');edge.enqueue(sample)
        statuses=[]
        def sender(payload):
            response=self.post('/api/acquisition/ingest',payload);statuses.append(response.status_code)
            return response.status_code,response.json()
        edge.attempt(sender)
        self.assertEqual(statuses,[429])
        pending=edge.status()['records'][0]
        self.assertEqual((pending['state'],pending['attempts'],pending['last_error']),('pending',1,'http-429'))
        self.assertIsNone(pending['receipt'])
        self.assertEqual(self.central_snapshot_hash(),before)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0],10000)
            self.assertEqual(db.execute('SELECT count(*) FROM audit').fetchone()[0],original_audit_count)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='synthetic_central_commit'").fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
            self.central_capacity_evidence={
                'central_records':10000,'exact_retry_http_status':duplicate.status_code,
                'original_receipt_preserved':True,'additional_event_http_status':rejected.status_code,
                'additional_event_received_receipt':False,'edge_delivery_http_status':statuses[0],
                'edge_state':pending['state'],'edge_attempts':pending['attempts'],'edge_receipt':pending['receipt'],
                'all_central_rows_and_audit_count_unchanged':True,
                'api_central_commit_audit_events':1,'sqlite_quick_check':'ok',
                'fixture_population':'One authenticated API commit plus 9,999 direct synthetic inserts; not 10,000 API ingests or sustained load.'}

    def test_concurrent_requests_for_last_central_slot_cannot_exceed_limit(self):
        self.populate_central(9999)
        before=self.central_snapshot_hash()
        with self.server.database() as db:audit_before=db.execute('SELECT count(*) FROM audit').fetchone()[0]
        payloads=[]
        for sequence in (9999,10000):
            sample=envelope();sample['observation']['sequence']=sequence;payloads.append(sample)
        gate=Barrier(2)
        def submit(payload):
            gate.wait(timeout=10)
            return self.post('/api/acquisition/ingest',payload)
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(submit,payloads))
        self.assertEqual(sorted(response.status_code for response in responses),[201,429])
        winner=next(index for index,response in enumerate(responses) if response.status_code==201)
        receipt=responses[winner].json();denied=responses[1-winner]
        self.assertNotIn('receipt_id',denied.json())
        expected_key,expected_hash=identity(payloads[winner]);denied_key,_=identity(payloads[1-winner])
        self.assertEqual((receipt['event_key'],receipt['content_hash']),(expected_key,expected_hash))
        retried=self.post('/api/acquisition/ingest',payloads[winner])
        self.assertEqual(retried.status_code,200);self.assertEqual(retried.json(),receipt)
        self.assertEqual(self.central_snapshot_hash(exclude=expected_key),before)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0],10000)
            self.assertIsNone(db.execute('SELECT 1 FROM acquisition_observations WHERE event_key=?',(denied_key,)).fetchone())
            self.assertEqual(db.execute('SELECT receipt_id FROM acquisition_observations WHERE event_key=?',(expected_key,)).fetchone()[0],receipt['receipt_id'])
            self.assertEqual(db.execute('SELECT count(*) FROM audit').fetchone()[0],audit_before+1)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='synthetic_central_commit'").fetchone()[0],2)
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.concurrent_capacity_evidence={
                'initial_central_records':9999,'concurrent_requests':2,
                'observed_http_statuses':sorted(response.status_code for response in responses),
                'final_central_records':10000,'rejected_request_received_receipt':False,
                'successful_retry_http_status':retried.status_code,'successful_receipt_preserved':True,
                'preexisting_rows_unchanged':True,'new_audit_events':1,
                'api_central_commit_audit_events':2,'sqlite_quick_check':'ok','foreign_key_violations':0,
                'fixture_population':'One API commit plus 9,998 direct synthetic inserts, then two barrier-started in-process API requests; not a load/soak benchmark.'}

    def test_supported_readers_receive_global_usage_without_mutating_queue(self):
        with self.spool.db() as db:before=[tuple(row) for row in db.execute('SELECT * FROM delivery_spool ORDER BY event_key')]
        expected=self.spool.status()['usage']
        for role in ('admin','operator','auditor'):
            self.login(role)
            for state in ('','pending','blocked'):
                response=self.http.get('/api/acquisition/delivery',params={'state':state,'limit':1})
                self.assertEqual(response.status_code,200);data=response.json()
                self.assertEqual(data['usage'],expected);self.assertEqual(set(data['usage']),{'records','payload_bytes'})
                for flag in ('hardware_connected','equipment_authorized','production_ready','model_deployed'):self.assertIs(data[flag],False)
        self.http.cookies.clear();self.assertEqual(self.http.get('/api/acquisition/delivery').status_code,401)
        with self.spool.db() as db:self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM delivery_spool ORDER BY event_key')],before)
