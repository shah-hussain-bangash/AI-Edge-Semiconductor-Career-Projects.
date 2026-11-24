"""Durability, response loss, lease fencing, identity conflicts and real HTTP delivery."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import httpx
from pydantic import ValidationError
from edge_delivery import Spool,identity,MAX_ATTEMPTS
from delivery_service import DeliveryInput
from delivery_worker import run_once
import test_acquisition_registry as fixtures
from test_acquisition_registry import binding,observation


def envelope():
    sample=observation();sample['boot_id']='synthetic-boot';sample['quality']['session_quality']='verified'
    return DeliveryInput.model_validate({'binding_revision':1,'observation':sample}).model_dump(mode='json')


class SpoolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='edgeops-spool-');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'spool.sqlite3';self.spool=Spool(self.path)

    def due(self):
        with self.spool.db() as db:db.execute('UPDATE delivery_spool SET next_at=0,lease_until=0')

    def receipt(self,claim):return {'tier':'central-committed','event_key':claim['event_key'],'content_hash':claim['content_hash'],'receipt_id':'a'*32,'committed_at':'2026-11-24T10:00:00+00:00'}

    def test_repeated_expired_leases_cannot_exceed_persisted_retry_budget(self):
        queued=self.spool.enqueue(envelope())
        with self.spool.db() as db:original=db.execute('SELECT payload FROM delivery_spool').fetchone()[0]
        for attempt in range(1,MAX_ATTEMPTS+1):
            # Reopen the persisted queue as a restarted worker would; no finish is saved.
            claim=Spool(self.path).claim()
            self.assertEqual(claim['attempt'],attempt)
            with self.spool.db() as db:db.execute('UPDATE delivery_spool SET lease_until=0')
        sent=[]
        self.assertEqual(Spool(self.path).attempt(lambda payload:sent.append(payload)),{'attempted':False})
        self.assertEqual(sent,[])
        row=self.spool.status()['records'][0]
        self.assertEqual((row['state'],row['attempts'],row['last_error']),('blocked',MAX_ATTEMPTS,'retry-budget-exhausted'))
        self.assertFalse(self.spool.finish(claim,receipt=self.receipt(claim)))
        with self.spool.db() as db:
            retained=db.execute('SELECT * FROM delivery_spool WHERE event_key=?',(queued['event_key'],)).fetchone()
            self.assertEqual(retained['payload'],original)
            self.assertIsNone(retained['lease_token']);self.assertIsNone(retained['lease_until'])
        healthy=envelope();healthy['observation']['sequence']=1
        next_event=self.spool.enqueue(healthy)
        self.assertEqual(self.spool.claim()['event_key'],next_event['event_key'])

    def test_active_final_attempt_can_still_finish_successfully(self):
        self.spool.enqueue(envelope())
        for _ in range(MAX_ATTEMPTS-1):
            claim=self.spool.claim();self.spool.finish(claim,error='transport-unavailable');self.due()
        final=self.spool.claim()
        self.assertEqual(final['attempt'],MAX_ATTEMPTS)
        self.assertIsNone(self.spool.claim())
        self.assertEqual(self.spool.status()['counts']['inflight'],1)
        self.assertTrue(self.spool.finish(final,receipt=self.receipt(final)))
        self.assertEqual(self.spool.status()['counts']['delivered'],1)

    def test_legacy_pending_records_at_or_above_budget_are_retained_without_send(self):
        for attempts in (MAX_ATTEMPTS,MAX_ATTEMPTS+1):
            with self.subTest(attempts=attempts):
                spool=Spool(Path(self.temp.name)/('exhausted-'+str(attempts)+'.sqlite3'))
                spool.enqueue(envelope())
                with spool.db() as db:db.execute('UPDATE delivery_spool SET attempts=?,next_at=0',(attempts,))
                self.assertIsNone(spool.claim())
                row=spool.status()['records'][0]
                self.assertEqual((row['state'],row['attempts'],row['last_error']),('blocked',attempts,'retry-budget-exhausted'))

    def test_corrupt_saved_payload_is_blocked_before_send_and_retained(self):
        changed=envelope();changed['observation']['measurements']['acceleration_x_mps2']=123
        wrong_identity=envelope();wrong_identity['observation']['sequence']=99
        measured=envelope();measured['observation']['source_type']='measured'
        payloads=('private-test-marker','[]','null',json.dumps(changed),json.dumps(wrong_identity),json.dumps(measured))
        for index,payload in enumerate(payloads):
            with self.subTest(case=index):
                spool=Spool(Path(self.temp.name)/('damaged-'+str(index)+'.sqlite3'))
                spool.enqueue(envelope())
                with spool.db() as db:
                    db.execute('UPDATE delivery_spool SET payload=?',(payload,))
                    original=dict(db.execute('SELECT * FROM delivery_spool').fetchone())
                sent=[]
                self.assertEqual(spool.attempt(lambda body:sent.append(body)),{'attempted':False})
                self.assertEqual(sent,[])
                row=spool.status()['records'][0]
                self.assertEqual((row['state'],row['attempts'],row['last_error']),('blocked',0,'invalid-local-observation'))
                self.assertNotIn('private-test-marker',str(row))
                with spool.db() as db:
                    retained=dict(db.execute('SELECT * FROM delivery_spool').fetchone())
                    for field in ('event_key','content_hash','payload','created_at','attempts'):
                        self.assertEqual(retained[field],original[field])
                    self.assertIsNone(retained['lease_token']);self.assertIsNone(retained['lease_until'])
                with self.assertRaisesRegex(ValueError,'Stored queued observation failed'):
                    spool.enqueue(envelope())

    def test_corrupt_hash_is_not_trusted_and_next_healthy_event_can_be_claimed(self):
        bad=self.spool.enqueue(envelope());good=envelope();good['observation']['sequence']=1
        queued=self.spool.enqueue(good)
        with self.spool.db() as db:
            db.execute('UPDATE delivery_spool SET content_hash=?,created_at=0 WHERE event_key=?',('f'*64,bad['event_key']))
        self.assertIsNone(self.spool.claim())
        claim=self.spool.claim()
        self.assertEqual(claim['event_key'],queued['event_key'])
        self.assertTrue(self.spool.finish(claim,receipt=self.receipt(claim)))
        self.assertEqual(self.spool.status()['counts'],{'pending':0,'inflight':0,'delivered':1,'blocked':1})

    def test_corrupt_expired_lease_is_blocked_and_old_worker_stays_fenced(self):
        self.spool.enqueue(envelope());old=self.spool.claim()
        with self.spool.db() as db:
            db.execute("UPDATE delivery_spool SET payload='corrupt',lease_until=0")
        self.assertIsNone(self.spool.claim())
        self.assertFalse(self.spool.finish(old,receipt=self.receipt(old)))
        row=self.spool.status()['records'][0]
        self.assertEqual((row['state'],row['attempts'],row['last_error']),('blocked',1,'invalid-local-observation'))

    def test_malformed_success_receipts_cannot_acknowledge_a_queued_observation(self):
        changes=[{'receipt_id':value} for value in (True,123,{},[],None,'','test-only','A'*32,'a'*31,'a'*33)]
        changes.extend({'committed_at':value} for value in (None,True,123,{},'','not-a-time','2026-11-24T10:00:00','x'*41))
        for index,change in enumerate(changes):
            with self.subTest(change=change):
                spool=Spool(Path(self.temp.name)/('invalid-'+str(index)+'.sqlite3'))
                queued=spool.enqueue(envelope())
                with spool.db() as db:
                    original=db.execute('SELECT payload FROM delivery_spool').fetchone()[0]
                spool.attempt(lambda payload:(200,{**self.receipt(queued),**change}))
                row=spool.status()['records'][0]
                self.assertEqual((row['state'],row['attempts'],row['last_error']),('blocked',1,'invalid-central-receipt'))
                self.assertIsNone(row['receipt'])
                with spool.db() as db:
                    self.assertEqual(db.execute('SELECT payload FROM delivery_spool').fetchone()[0],original)
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM delivery_spool').fetchone()[0],1)

    def test_valid_commit_receipt_keeps_exact_identity_and_timestamp(self):
        self.spool.enqueue(envelope());claim=self.spool.claim();receipt=self.receipt(claim)
        self.assertTrue(self.spool.finish(claim,receipt=receipt))
        row=self.spool.status()['records'][0]
        self.assertEqual(row['state'],'delivered')
        self.assertEqual(json.loads(row['receipt']),receipt)

    def test_restart_replay_and_capacity_do_not_lose_committed_event(self):
        first=self.spool.enqueue(envelope());restarted=Spool(self.path)
        self.assertFalse(restarted.enqueue(envelope())['created'])
        self.assertEqual(restarted.status()['counts']['pending'],1)
        small=Spool(self.path,max_rows=1)
        sample=envelope();sample['observation']['sequence']=1
        with self.assertRaises(OverflowError):small.enqueue(sample)
        self.assertEqual(self.spool.status()['counts']['pending'],1)
        self.assertEqual(first['tier'],'edge-committed')
        with self.assertRaises(OverflowError):Spool(Path(self.temp.name)/'tiny.sqlite3',max_bytes=10).enqueue(envelope())

    def test_abrupt_process_exit_and_backup_restore_preserve_pending_queue(self):
        script="import os,sys,json;from edge_delivery import Spool;s=Spool(sys.argv[1]);s.enqueue(json.loads(sys.argv[2]));s.claim();os._exit(0)"
        subprocess.run([sys.executable,'-c',script,str(self.path),json.dumps(envelope())],check=True,cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(Spool(self.path).status()['counts']['inflight'],1)
        self.due();self.assertIsNotNone(Spool(self.path).claim())
        from recovery import create_backup,restore_backup
        import sqlite3
        from contextlib import closing
        auth=Path(self.temp.name)/'auth.sqlite3'
        with closing(sqlite3.connect(auth)) as db:
            db.executescript('CREATE TABLE users(id INTEGER);CREATE TABLE sessions(token_hash TEXT);CREATE TABLE audit(time_utc TEXT,actor TEXT,action TEXT,detail TEXT);')
        backup=Path(self.temp.name)/'backup';restored=Path(self.temp.name)/'restored'
        create_backup(auth,backup,delivery_spool=self.path);restore_backup(backup,restored)
        self.assertEqual(Spool(restored/'delivery-spool.sqlite3').status()['counts']['inflight'],1)

    def test_semantic_hash_excludes_arrival_but_detects_content_change(self):
        self.spool.enqueue(envelope())
        sample=envelope();sample['observation']['timestamp']['gateway_received_utc']='2026-11-20T10:00:00Z'
        self.assertFalse(self.spool.enqueue(sample)['created'])
        sample['observation']['measurements']['acceleration_x_mps2']=2
        with self.assertRaises(ValueError):self.spool.enqueue(sample)
        sample=envelope();sample['observation']['source_type']='measured'
        with self.assertRaises(ValidationError):self.spool.enqueue(sample)

    def test_expired_lease_is_reclaimed_and_old_worker_cannot_finish(self):
        self.spool.enqueue(envelope());old=self.spool.claim();self.due();new=self.spool.claim()
        self.assertNotEqual(old['token'],new['token'])
        self.assertFalse(self.spool.finish(old,receipt=self.receipt(old)))
        self.assertTrue(self.spool.finish(new,receipt=self.receipt(new)))
        self.assertEqual(self.spool.status()['counts']['delivered'],1)

    def test_retry_backoff_permanent_denial_and_invalid_receipt(self):
        self.spool.enqueue(envelope())
        self.spool.attempt(lambda data:(_ for _ in ()).throw(TimeoutError('test secret must not be saved')))
        self.assertIsNone(self.spool.claim())
        self.assertNotIn('secret',str(self.spool.status()))
        self.due();self.spool.attempt(lambda data:(409,{}))
        self.assertEqual(self.spool.status()['counts']['blocked'],1)
        other=envelope();other['observation']['sequence']=2;self.spool.enqueue(other)
        self.spool.attempt(lambda data:(200,[]))
        self.assertEqual(self.spool.status()['counts']['blocked'],2)
        sample=envelope();sample['observation']['sequence']=3;self.spool.enqueue(sample)
        for _ in range(8):
            self.due();self.spool.attempt(lambda data:(503,{}))
        self.assertEqual(self.spool.status()['counts']['blocked'],3)

    def test_concurrent_claim_and_disk_error_do_not_acknowledge_uncommitted_data(self):
        self.spool.enqueue(envelope())
        with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:self.spool.claim(),range(2)))
        self.assertEqual(sum(c is not None for c in claims),1)
        # A read-only connection supplies a real SQLite write failure without filling the user's disk.
        import sqlite3
        from contextlib import contextmanager
        from unittest.mock import patch
        @contextmanager
        def readonly():
            db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
            try:yield db
            finally:db.close()
        sample=envelope();sample['observation']['sequence']=9
        with patch.object(self.spool,'db',readonly),self.assertRaises(sqlite3.OperationalError):self.spool.enqueue(sample)
        self.assertEqual(sum(self.spool.status()['counts'].values()),1)


class DeliveryApiTests(unittest.TestCase):
    login=fixtures.AcquisitionRegistryApiTests.login
    post=fixtures.AcquisitionRegistryApiTests.post
    # Reuse isolated accounts/bootstrap, not the parent's test cases.
    def setUp(self):
        fixtures.AcquisitionRegistryApiTests.setUp(self);self.assertEqual(self.post('/api/acquisition-bindings',binding()).status_code,201)

    def test_duplicate_commit_refuses_damaged_storage_without_repair_or_receipt(self):
        first=self.post('/api/acquisition/ingest',envelope());self.assertEqual(first.status_code,201)
        with self.server.database() as db:
            original=dict(db.execute('SELECT * FROM acquisition_observations').fetchone())
        changed=json.loads(original['payload'])
        changed['observation']['measurements']['acceleration_x_mps2']=123
        fields=('payload','content_hash','binding_revision','receipt_id','committed_at')
        cases=({'payload':'corrupt'},{'payload':'[]'},{'payload':json.dumps(changed)},
               {'content_hash':'f'*64},{'binding_revision':2},{'receipt_id':'invalid'},
               {'committed_at':'2026-11-24T10:00:00'},{'committed_at':'not-a-time'})
        for changes in cases:
            with self.subTest(changes=changes):
                row={**original,**changes}
                with self.server.database() as db:
                    db.execute('UPDATE acquisition_observations SET '+','.join(field+'=?' for field in fields),
                               tuple(row[field] for field in fields))
                    before=tuple(db.execute('SELECT * FROM acquisition_observations').fetchone())
                    audits=db.execute('SELECT count(*) FROM audit').fetchone()[0]
                response=self.post('/api/acquisition/ingest',envelope())
                self.assertEqual(response.status_code,503,response.text)
                self.assertNotIn('receipt_id',response.json())
                with self.server.database() as db:
                    self.assertEqual(tuple(db.execute('SELECT * FROM acquisition_observations').fetchone()),before)
                    self.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0],1)
                    self.assertEqual(db.execute('SELECT count(*) FROM audit').fetchone()[0],audits)

    def test_lost_response_retry_cannot_deliver_a_corrupted_central_copy(self):
        spool=Spool(Path(self.temp.name)/'lost-response-spool.sqlite3');spool.enqueue(envelope())
        def lost(payload):
            self.assertEqual(self.post('/api/acquisition/ingest',payload).status_code,201)
            raise TimeoutError('synthetic lost response')
        spool.attempt(lost)
        with self.server.database() as db:
            db.execute("UPDATE acquisition_observations SET payload='damaged synthetic copy'")
        with spool.db() as db:db.execute('UPDATE delivery_spool SET next_at=0')
        spool.attempt(lambda payload:(lambda response:(response.status_code,response.json()))(
            self.post('/api/acquisition/ingest',payload)))
        row=spool.status()['records'][0]
        self.assertEqual((row['state'],row['attempts'],row['last_error']),('pending',2,'http-503'))
        self.assertIsNone(row['receipt'])
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT payload FROM acquisition_observations').fetchone()[0],'damaged synthetic copy')
            self.assertEqual(db.execute('SELECT count(*) FROM acquisition_observations').fetchone()[0],1)

    def test_delivery_commit_response_loss_and_conflict(self):
        data=envelope();spool=Spool(Path(self.temp.name)/'delivery-spool.sqlite3');spool.enqueue(data)
        def lost_response(payload):
            response=self.post('/api/acquisition/ingest',payload);self.assertEqual(response.status_code,201)
            raise TimeoutError('response lost after actual commit')
        spool.attempt(lost_response)
        self.assertEqual(spool.status()['counts']['pending'],1)
        with spool.db() as db:db.execute('UPDATE delivery_spool SET next_at=0')
        spool.attempt(lambda payload:(lambda r:(r.status_code,r.json()))(self.post('/api/acquisition/ingest',payload)))
        self.assertEqual(spool.status()['counts']['delivered'],1)
        data['observation']['measurements']['acceleration_x_mps2']=3
        self.assertEqual(self.post('/api/acquisition/ingest',data).status_code,409)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM acquisition_observations').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='synthetic_ingest_conflict'").fetchone()[0],1)

    def test_queue_retirement_roles_and_ambiguous_session_denial(self):
        data={'binding_revision':1,'observation':observation()}
        self.assertEqual(self.post('/api/acquisition/queue',data).status_code,422)
        self.assertEqual(self.post('/api/acquisition/queue',envelope()).status_code,201)
        self.assertEqual(self.http.get('/api/acquisition/delivery').json()['central_records'],0)
        self.assertEqual(self.post('/api/acquisition-bindings/test-device/retire',{'expected_revision':1}).status_code,200)
        self.assertEqual(self.post('/api/acquisition/deliver-once',{}).status_code,200)
        self.assertEqual(self.http.get('/api/acquisition/delivery').json()['counts']['blocked'],1)
        self.login('auditor');self.assertEqual(self.post('/api/acquisition/deliver-once',{}).status_code,403)
        self.assertEqual(self.post('/api/acquisition/ingest',envelope()).status_code,403)

    def test_real_loopback_worker_transmits_and_commits(self):
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        env={**os.environ,'EDGEOPS_ADMIN_EMAIL':'','EDGEOPS_ADMIN_PASSWORD':''}
        service=subprocess.Popen([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port',str(port)],cwd=Path(__file__).resolve().parents[1],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    if httpx.get(f'http://127.0.0.1:{port}/health/ready',trust_env=False).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.05)
            path=Path(self.temp.name)/'remote-edge.sqlite3';Spool(path).enqueue(envelope())
            self.assertTrue(run_once(path,f'http://127.0.0.1:{port}','admin@example.invalid',self.password)['attempted'])
            self.assertEqual(Spool(path).status()['counts']['delivered'],1)
            self.assertEqual(self.http.get('/api/acquisition/delivery').json()['central_records'],1)
        finally:service.terminate();service.wait(timeout=10)
