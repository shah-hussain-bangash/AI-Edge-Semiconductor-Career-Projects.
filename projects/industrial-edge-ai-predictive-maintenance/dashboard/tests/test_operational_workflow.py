from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
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
        if kind=='cases':body['expected_last_frame']=row['last_frame']
        if kind=='orders' and action=='approve':body['expected_last_frame']=row.get('source_review',{}).get('last_frame',row['case_snapshot']['last_frame'])
        body.update(changes);return self.post('/api/operational/'+kind+'/'+row['id']+'/action',body)

    def order(self,case):
        return self.post('/api/operational/orders',dict(case_id=case['id'],expected_case_revision=case['revision'],expected_last_frame=case['last_frame'],request_key='d'*32,title='Inspect fixture evidence',procedure='Review the captured software evidence without any equipment action.',technician_id=self.technician))

    def prepared_order(self, stage='draft'):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        case=self.summary()['cases'][0];order=self.order(case).json()['record']
        if stage!='draft':order=self.action('orders',order,'submit').json()['record']
        if stage in ('approved','in-progress'):
            self.login('reviewer');order=self.action('orders',order,'approve').json()['record']
        if stage=='in-progress':
            self.login('operator');order=self.action('orders',order,'start').json()['record']
        return case,order

    def note(self,kind,row,text='Append an isolated fixture clarification without a state change.',key='1'*32,**changes):
        body=dict(request_key=key,expected_revision=row['revision'],note=text)
        if kind=='case':body['expected_last_frame']=row['last_frame']
        body.update(changes);return self.post('/api/operational/'+kind+'/'+row['id']+'/notes',body)

    def test_review_note_concurrent_retries_append_once_without_changing_case(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        with ThreadPoolExecutor(max_workers=2) as pool:replies=list(pool.map(lambda _:self.note('case',case),range(2)))
        self.assertEqual(sorted(r.status_code for r in replies),[200,201]);self.assertEqual(len({r.json()['note_id'] for r in replies}),1)
        self.assertEqual(self.summary()['cases'][0],case)
        events=self.http.get('/api/operational/case/'+case['id']+'/history').json()['events'];self.assertEqual(sum(e['action']=='review_note_added' for e in events),1)
        notices=self.http.get('/api/operational/notifications').json()['items'];self.assertEqual(sum('review note added' in n['subject'] for n in notices),1)
        self.assertFalse(replies[0].json()['physical_work_verified'])

    def test_clarifications_preserve_terminal_states_and_upload_freeze(self):
        case,order=self.prepared_order('approved');self.login('admin');order=self.action('orders',order,'cancel').json()['record'];frozen=order['case_snapshot_sha256']
        reply=self.note('order',order);self.assertEqual(reply.status_code,201,reply.text);current=self.summary()['orders'][0]
        self.assertEqual((current['state'],current['revision'],current['case_snapshot_sha256']),('cancelled',order['revision'],frozen))
        path='/api/operational/evidence/order/'+order['id'];self.assertEqual(self.http.post(path,params={'filename':'blocked.txt'},content=b'No upload unlock',headers={'content-type':'text/plain','x-edgeops-csrf':self.http.cookies.get('edgeops_csrf')}).status_code,409)
        case=self.action('cases',case,'acknowledge').json()['record'];case=self.action('cases',case,'resolve',evidence_refs='Fixture resolution evidence').json()['record']
        self.assertEqual(self.note('case',case).status_code,201);current=self.summary()['cases'][0];self.assertEqual((current['state'],current['revision']),('resolved',case['revision']))
        report=self.http.get('/api/operational/order/'+order['id']+'/review-export').json()['report'];self.assertEqual(report['history']['events'][0]['action'],'review_note_added')

    def test_review_notes_recheck_write_access_csrf_and_context(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        body=dict(request_key='1'*32,expected_revision=case['revision'],expected_last_frame=case['last_frame'],note='A case clarification requires current write access.')
        self.assertEqual(self.post('/api/operational/case/'+case['id']+'/notes',body,False).status_code,403)
        self.login('auditor');self.assertEqual(self.note('case',case).status_code,403)
        self.login('operator');self.assertEqual(self.note('case',case).status_code,404)
        self.login('admin');self.assertEqual(self.note('case',case,expected_revision=99).status_code,409)
        self.assertEqual(self.note('case',case,expected_last_frame=None).status_code,422)
        self.assertEqual(self.ingest(1,temp_c=60).status_code,201);self.assertEqual(self.note('case',case).status_code,409)
        current=self.summary()['cases'][0];self.assertEqual(self.note('case',current).status_code,201)
        self.assertEqual(self.note('case',current,text='Different content with the same saved key must fail.').status_code,409)

    def test_saved_note_retry_remains_idempotent_after_record_changes(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        original=self.note('case',case);self.assertEqual(original.status_code,201)
        self.assertEqual(self.action('cases',case,'acknowledge').status_code,200)
        self.assertEqual(self.ingest(1,temp_c=60).status_code,201)
        reply=self.note('case',case);self.assertEqual(reply.status_code,200,reply.text);self.assertEqual(reply.json()['note_id'],original.json()['note_id'])
        self.assertEqual(self.summary()['cases'][0]['state'],'acknowledged')

    def test_corrupt_saved_note_receipt_refuses_duplicate_inference(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        reply=self.note('case',case);self.assertEqual(reply.status_code,201)
        with self.server.database() as db:
            saved=db.execute('SELECT snapshot_json FROM operational_events WHERE id=?',(reply.json()['note_id'],)).fetchone()
            snapshot=json.loads(saved['snapshot_json']);snapshot.pop('note_request')
            db.execute('UPDATE operational_events SET snapshot_json=? WHERE id=?',(json.dumps(snapshot),reply.json()['note_id']))
        self.assertEqual(self.note('case',case).status_code,503)
        events=self.http.get('/api/operational/case/'+case['id']+'/history').json()['events'];self.assertEqual(sum(e['action']=='review_note_added' for e in events),1)

    def test_review_note_notification_failure_rolls_back_event_for_retry(self):
        from unittest.mock import patch
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        with patch('operational_notifications.enqueue',side_effect=RuntimeError('Fixture inbox unavailable')):
            with self.assertRaises(RuntimeError):self.note('case',case)
        events=self.http.get('/api/operational/case/'+case['id']+'/history').json()['events'];self.assertFalse(any(e['action']=='review_note_added' for e in events))
        self.assertEqual(self.note('case',case).status_code,201)

    def test_approval_requires_latest_displayed_source_and_retains_review_context(self):
        case,order=self.prepared_order('submitted');frozen=order['case_snapshot_sha256'];self.assertEqual(self.ingest(1,temp_c=60).status_code,201);self.login('reviewer')
        self.assertEqual(self.action('orders',order,'approve').status_code,409);current=self.summary()['orders'][0]
        self.assertEqual(current['state'],'submitted');self.assertEqual(current['source_review']['last_frame'],1);self.assertEqual(current['source_review']['value'],60)
        self.assertEqual(current['case_snapshot']['last_frame'],0);self.assertEqual(current['case_snapshot_sha256'],frozen)
        reply=self.action('orders',current,'approve');self.assertEqual(reply.status_code,200,reply.text)
        event=self.http.get('/api/operational/order/'+order['id']+'/history').json()['events'][0]
        self.assertEqual(event['approval_review']['last_frame'],1);self.assertEqual(event['approval_review']['value'],60)
        self.assertEqual(self.ingest(2,temp_c=70).status_code,201)
        retained=self.http.get('/api/operational/order/'+order['id']+'/history').json()['events'][0]
        self.assertEqual(retained,event);self.assertEqual(self.summary()['orders'][0]['case_snapshot_sha256'],frozen)
        report=self.http.get('/api/operational/order/'+order['id']+'/review-export').json()['report'];self.assertEqual(report['history']['events'][0]['approval_review']['last_frame'],1)

    def test_live_source_preview_respects_current_case_scope(self):
        case,order=self.prepared_order('submitted');self.assertEqual(self.ingest(1,temp_c=60).status_code,201);self.login('operator')
        self.assertEqual(self.summary()['orders'][0]['source_review'],{'available':False})
        self.assertEqual(self.http.get('/api/operational/order/'+order['id']+'/record').json()['record']['source_review'],{'available':False})
        with self.server.database() as db:db.execute('UPDATE operational_cases SET assignee_id=? WHERE id=?',(self.technician,case['id']))
        self.assertEqual(self.summary()['orders'][0]['source_review']['value'],60)
        with self.server.database() as db:db.execute('UPDATE operational_cases SET assignee_id=NULL WHERE id=?',(case['id'],))
        self.assertEqual(self.summary()['orders'][0]['source_review'],{'available':False})
        self.login('auditor');self.assertEqual(self.summary()['orders'][0]['source_review']['last_frame'],1)

    def test_approval_requires_valid_frame_without_affecting_other_actions(self):
        case,order=self.prepared_order('submitted');self.login('reviewer')
        self.assertEqual(self.action('orders',order,'approve',expected_last_frame=None).status_code,422)
        self.assertEqual(self.action('orders',order,'approve',expected_last_frame=True).status_code,422)
        self.assertEqual(self.summary()['orders'][0]['state'],'submitted')
        self.assertEqual(self.action('orders',order,'reject').status_code,200)

    def test_concurrent_approval_and_new_frame_never_records_unseen_source(self):
        case,order=self.prepared_order('submitted');self.login('reviewer')
        with ThreadPoolExecutor(max_workers=2) as pool:
            incoming=pool.submit(lambda:self.ingest(1,temp_c=60).status_code);decision=pool.submit(lambda:self.action('orders',order,'approve'))
            self.assertEqual(incoming.result(),201);reply=decision.result();self.assertIn(reply.status_code,(200,409))
        if reply.status_code==200:
            event=self.http.get('/api/operational/order/'+order['id']+'/history').json()['events'][0];self.assertEqual(event['approval_review']['last_frame'],0)
        else:self.assertEqual(self.summary()['orders'][0]['state'],'submitted')

    def test_legacy_approval_history_does_not_invent_reviewed_source(self):
        case,order=self.prepared_order('approved')
        with self.server.database() as db:
            saved=db.execute("SELECT * FROM operational_events WHERE kind='order' AND record_id=? AND action='approve'",(order['id'],)).fetchone()
            snapshot=json.loads(saved['snapshot_json']);snapshot.pop('approval_review')
            db.execute('UPDATE operational_events SET snapshot_json=? WHERE id=?',(json.dumps(snapshot),saved['id']))
        history=self.http.get('/api/operational/order/'+order['id']+'/history').json()['events']
        self.assertNotIn('approval_review',history[0]);self.assertEqual(history[0]['action'],'approve')

    def test_saved_case_search_reaches_older_records_and_pages_without_duplicates(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        with self.server.database() as db:
            columns=[x[1] for x in db.execute('PRAGMA table_info(operational_cases)')];original=dict(db.execute('SELECT * FROM operational_cases WHERE id=?',(case['id'],)).fetchone())
            for index in range(205):
                copy=dict(original,id=format(index+1,'032x'),bucket=index+1,created_at='2099-01-01T00:00:00+00:00',updated_at='2099-01-01T00:00:00+00:00')
                db.execute('INSERT INTO operational_cases VALUES('+','.join('?' for _ in columns)+')',tuple(copy[k] for k in columns))
        self.assertNotIn(case['id'],[r['id'] for r in self.summary()['cases']])
        found=self.http.get('/api/operational/case/records',params={'q':case['id']});self.assertEqual(found.status_code,200,found.text);self.assertEqual(found.headers['cache-control'],'no-store');self.assertEqual([x['id'] for x in found.json()['items']],[case['id']])
        seen=[];params={'limit':61}
        for _ in range(10):
            data=self.http.get('/api/operational/case/records',params=params).json();seen += [x['id'] for x in data['items']];self.assertEqual(data['matching_total'],206)
            cursor=data['page']['next_cursor']
            if cursor is None:break
            params.update(before_created=cursor['created_at'],before_id=cursor['id'])
        self.assertEqual(len(seen),206);self.assertEqual(len(set(seen)),206)
        self.assertEqual(self.http.get('/api/operational/case/records',params={'q':'%'}).json()['items'],[])
        self.assertEqual(self.http.get('/api/operational/case/records',params={'source_type':'measured-unverified'}).json()['matching_total'],0)

    def test_saved_case_search_rechecks_operator_assignment_before_filtering(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0];path='/api/operational/case/records'
        self.login('operator');self.assertEqual(self.http.get(path).json()['matching_total'],0)
        self.login('admin');self.assertEqual(self.post('/api/operational/cases/'+case['id']+'/assign',dict(expected_revision=case['revision'],assignee_id=self.technician,**self.authorization)).status_code,200)
        self.login('operator');data=self.http.get(path,params={'q':'Isolated fixture motor','state':'open','source_type':'software-fixture'}).json();self.assertEqual(data['matching_total'],1);self.assertNotIn('first_snapshot',data['items'][0])
        with self.server.database() as db:db.execute('UPDATE operational_cases SET assignee_id=NULL WHERE id=?',(case['id'],))
        self.assertEqual(self.http.get(path,params={'q':case['id'],'before_created':'2099-01-01T00:00:00+00:00','before_id':'f'*32}).json()['matching_total'],0)
        self.login('auditor');self.assertEqual(self.http.get(path,params={'q':case['id']}).json()['matching_total'],1)

    def test_saved_work_search_state_source_and_current_assignment(self):
        case,order=self.prepared_order('approved');self.login('admin');self.assertEqual(self.action('orders',order,'cancel').status_code,200);path='/api/operational/order/records';params={'q':'Inspect fixture','state':'cancelled','source_type':'software-fixture'}
        self.login('operator');reply=self.http.get(path,params=params);self.assertEqual(reply.status_code,200,reply.text);self.assertEqual([x['id'] for x in reply.json()['items']],[order['id']]);self.assertNotIn('procedure',reply.text);self.assertNotIn('request_hash',reply.text)
        with self.server.database() as db:db.execute('UPDATE operational_orders SET technician_id=creator_id WHERE id=?',(order['id'],))
        self.assertEqual(self.http.get(path,params=params).json()['items'],[])
        self.login('auditor');self.assertEqual(self.http.get(path,params=params).json()['matching_total'],1)
        self.http.cookies.clear();self.assertEqual(self.http.get(path).status_code,401)

    def test_saved_record_search_rejects_bad_filters_and_cursor_pairs(self):
        path='/api/operational/case/records'
        for params in [{'state':'draft'},{'source_type':'unverified'},{'limit':0},{'limit':101},{'q':'x'*101},{'before_created':'2099-01-01T00:00:00+00:00'},{'before_id':'a'*32},{'before_created':'2099-01-01T00:00:00','before_id':'a'*32}]:self.assertEqual(self.http.get(path,params=params).status_code,422)
        self.assertEqual(self.http.get('/api/operational/order/records',params={'state':'acknowledged'}).status_code,422)

    def test_new_work_refuses_unseen_matching_frame_and_accepts_reviewed_frame(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        self.assertEqual(self.ingest(1,temp_c=60).status_code,201);self.assertEqual(self.order(case).status_code,409);self.assertEqual(self.summary()['orders'],[])
        reply=self.order(self.summary()['cases'][0]);self.assertEqual(reply.status_code,201,reply.text);self.assertEqual(reply.json()['record']['case_snapshot']['last_frame'],1)

    def test_saved_work_retry_retains_original_context_after_new_frame(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        original=self.order(case).json()['record'];self.assertEqual(self.ingest(1,temp_c=60).status_code,201)
        reply=self.order(case);self.assertEqual(reply.status_code,200,reply.text);self.assertFalse(reply.json()['created'])
        self.assertEqual(reply.json()['record']['id'],original['id']);self.assertEqual(reply.json()['record']['case_snapshot_sha256'],original['case_snapshot_sha256']);self.assertEqual(reply.json()['record']['case_snapshot']['last_frame'],0)
        self.assertEqual(self.order(self.summary()['cases'][0]).status_code,409,'A saved request key cannot silently capture newer content')

    def test_legacy_saved_request_replay_remains_valid_but_new_legacy_create_fails(self):
        import hashlib
        from operational_workflow import canonical
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0];original=self.order(case).json()['record']
        legacy=dict(case_id=case['id'],expected_case_revision=case['revision'],request_key='d'*32,title='Inspect fixture evidence',procedure='Review the captured software evidence without any equipment action.',technician_id=self.technician)
        # A prior-version record used the same body hash without a frame expectation.
        with self.server.database() as db:db.execute('UPDATE operational_orders SET request_hash=? WHERE id=?',(hashlib.sha256(canonical(legacy).encode()).hexdigest(),original['id']))
        self.assertEqual(self.ingest(1,temp_c=60).status_code,201)
        reply=self.post('/api/operational/orders',legacy);self.assertEqual(reply.status_code,200,reply.text);self.assertEqual(reply.json()['record']['id'],original['id'])
        legacy['request_key']='e'*32;self.assertEqual(self.post('/api/operational/orders',legacy).status_code,422)

    def test_concurrent_work_creation_never_captures_an_unseen_new_frame(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            incoming=pool.submit(lambda:self.ingest(1,temp_c=60).status_code);draft=pool.submit(lambda:self.order(case))
            self.assertEqual(incoming.result(),201);reply=draft.result();self.assertIn(reply.status_code,(201,409))
        if reply.status_code==201:self.assertEqual(reply.json()['record']['case_snapshot']['last_frame'],0)
        else:self.assertEqual(self.summary()['orders'],[])

    def test_new_matching_frame_blocks_stale_acknowledgement(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        self.assertEqual(self.ingest(1,temp_c=50).status_code,201)
        self.assertEqual(self.action('cases',case,'acknowledge').status_code,409)
        current=self.summary()['cases'][0];self.assertEqual(current['state'],'open');self.assertEqual(current['revision'],case['revision'])
        self.assertEqual(self.action('cases',current,'acknowledge').status_code,200)

    def test_new_matching_frame_blocks_stale_resolution_and_retains_ack_context(self):
        self.rule();self.assertEqual(self.ingest(10,temp_c=40).status_code,201);case=self.summary()['cases'][0]
        case=self.action('cases',case,'acknowledge').json()['record'];self.assertEqual(self.ingest(11,temp_c=60).status_code,201)
        self.assertEqual(self.action('cases',case,'resolve',evidence_refs='Outdated fixture review').status_code,409)
        current=self.summary()['cases'][0];self.assertEqual(current['state'],'acknowledged');self.assertEqual(current['revision'],case['revision'])
        self.assertEqual(self.action('cases',current,'resolve',evidence_refs='Reviewed latest fixture crossing').status_code,200)
        events=self.http.get('/api/operational/case/'+case['id']+'/history').json()['events']
        self.assertEqual(events[0]['captured_last_frame'],11);self.assertEqual(events[1]['captured_last_frame'],10)

    def test_retries_and_older_frames_do_not_invalidate_latest_frame_decision(self):
        self.rule();self.assertEqual(self.ingest(10,temp_c=40).status_code,201);case=self.summary()['cases'][0]
        case=self.action('cases',case,'acknowledge').json()['record']
        self.assertEqual(self.ingest(10,temp_c=40).status_code,200);self.assertEqual(self.ingest(5,temp_c=50).status_code,201)
        reply=self.action('cases',case,'resolve',evidence_refs='Review of unchanged latest matched frame');self.assertEqual(reply.status_code,200,reply.text)
        self.assertEqual(reply.json()['record']['last_frame'],10);self.assertEqual(reply.json()['record']['first_frame'],5)

    def test_concurrent_new_reading_and_resolution_cannot_leave_case_resolved(self):
        self.rule();self.assertEqual(self.ingest(10,temp_c=40).status_code,201);case=self.summary()['cases'][0];case=self.action('cases',case,'acknowledge').json()['record']
        def resolve():return self.action('cases',case,'resolve',evidence_refs='Concurrent fixture decision review').status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            incoming=pool.submit(lambda:self.ingest(11,temp_c=60).status_code);decision=pool.submit(resolve)
            self.assertEqual(incoming.result(),201);self.assertIn(decision.result(),(200,409))
        current=self.summary()['cases'][0];self.assertIn(current['state'],('open','acknowledged'));self.assertEqual(current['last_frame'],11)

    def test_case_decisions_require_a_valid_displayed_frame(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        for value in (None,True,-1,2**64):
            self.assertEqual(self.action('cases',case,'acknowledge',expected_last_frame=value).status_code,422)
        body=dict(expected_revision=case['revision'],action='acknowledge',note='A legacy client missing its displayed frame must refresh.')
        self.assertEqual(self.post('/api/operational/cases/'+case['id']+'/action',body).status_code,422)
        self.assertEqual(self.summary()['cases'][0]['state'],'open')

    def seeded_history(self,count=226):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        with self.server.database() as db:
            event=dict(db.execute("SELECT * FROM operational_events WHERE kind='case' AND record_id=?",(case['id'],)).fetchone())
            for _ in range(count-1):db.execute('INSERT INTO operational_events(kind,record_id,revision,actor_id,action,note,snapshot_json,time_utc) VALUES(?,?,?,?,?,?,?,?)',tuple(event[k] for k in ('kind','record_id','revision','actor_id','action','note','snapshot_json','time_utc')))
        return case

    def test_history_pages_reach_earlier_decisions_beyond_200(self):
        case=self.seeded_history();path='/api/operational/case/'+case['id']+'/history';seen=[];before=None
        while True:
            params={'limit':61}
            if before:params['before_event']=before
            reply=self.http.get(path,params=params);self.assertEqual(reply.status_code,200,reply.text);self.assertEqual(reply.headers['cache-control'],'no-store')
            data=reply.json();self.assertEqual(data['history_total'],226);self.assertLessEqual(len(data['events']),61)
            seen += [x['id'] for x in data['events']];before=data['page']['next_before_event']
            for event in data['events']:self.assertEqual(event['captured_value'],40)
            if not before:break
        self.assertEqual(len(seen),226);self.assertEqual(len(set(seen)),226);self.assertEqual(seen,sorted(seen,reverse=True))
        report=self.http.get('/api/operational/case/'+case['id']+'/review-export').json()['report'];self.assertEqual(report['history']['returned'],200);self.assertFalse(report['history']['complete'])

    def test_history_page_rechecks_access_after_assignment_revoked(self):
        case=self.seeded_history(4)
        case=self.post('/api/operational/cases/'+case['id']+'/assign',dict(expected_revision=case['revision'],assignee_id=self.technician,**self.authorization)).json()['record']
        self.login('operator');path='/api/operational/case/'+case['id']+'/history';reply=self.http.get(path,params={'limit':1});self.assertEqual(reply.status_code,200);cursor=reply.json()['page']['next_before_event']
        with self.server.database() as db:db.execute('UPDATE operational_cases SET assignee_id=NULL WHERE id=?',(case['id'],))
        self.assertEqual(self.http.get(path,params={'before_event':cursor}).status_code,404)
        self.login('auditor');self.assertEqual(self.http.get(path,params={'before_event':cursor}).status_code,200)
        self.http.cookies.clear();self.assertEqual(self.http.get(path,params={'before_event':cursor}).status_code,401)

    def test_history_page_reports_current_revision_after_new_decision(self):
        case=self.seeded_history(4);path='/api/operational/case/'+case['id']+'/history';first=self.http.get(path,params={'limit':1}).json()
        changed=self.action('cases',case,'acknowledge');self.assertEqual(changed.status_code,200)
        second=self.http.get(path,params={'before_event':first['page']['next_before_event']}).json()
        self.assertEqual(second['record']['revision'],case['revision']+1);self.assertEqual(second['record']['state'],'acknowledged')
        self.assertTrue(all(e['id']<first['events'][-1]['id'] for e in second['events']))
        self.assertEqual(second['history_total'],5)

    def test_history_page_bounds_and_frozen_order_integrity(self):
        case,order=self.prepared_order('approved');path='/api/operational/order/'+order['id']+'/history'
        for params in [{'limit':0},{'limit':201},{'before_event':0},{'before_event':-1},{'before_event':2**64}]:self.assertEqual(self.http.get(path,params=params).status_code,422)
        self.login('operator');reply=self.http.get(path,params={'limit':1});self.assertEqual(reply.status_code,200)
        with self.server.database() as db:db.execute("UPDATE operational_orders SET case_snapshot='{}' WHERE id=?",(order['id'],))
        self.assertEqual(self.http.get(path,params={'before_event':reply.json()['page']['next_before_event']}).status_code,503)

    def test_exact_lookup_opens_case_outside_recent_summary_without_mutation(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        with self.server.database() as db:
            columns=[x[1] for x in db.execute('PRAGMA table_info(operational_cases)')]
            original=dict(db.execute('SELECT * FROM operational_cases WHERE id=?',(case['id'],)).fetchone())
            for index in range(201):
                copy=dict(original,id=format(index+1,'032x'),bucket=index+1,updated_at='2099-01-01T00:00:00+00:00')
                db.execute('INSERT INTO operational_cases VALUES('+','.join('?' for _ in columns)+')',tuple(copy[k] for k in columns))
        self.assertNotIn(case['id'],[r['id'] for r in self.summary()['cases']])
        inbox=self.http.get('/api/operational/notifications').json()['items']
        reply=self.http.get('/api/operational/case/'+case['id']+'/record');self.assertEqual(reply.status_code,200,reply.text)
        self.assertEqual(reply.headers['cache-control'],'no-store');self.assertEqual(reply.json()['record']['revision'],case['revision'])
        self.assertEqual(reply.json()['record']['last_snapshot']['value'],40)
        self.assertEqual(self.http.get('/api/operational/notifications').json()['items'],inbox)

    def test_exact_lookup_rechecks_current_access_and_account_status(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        path='/api/operational/case/'+case['id']+'/record'
        self.login('operator');self.assertEqual(self.http.get(path).status_code,404)
        self.login('admin');case=self.post('/api/operational/cases/'+case['id']+'/assign',dict(expected_revision=case['revision'],assignee_id=self.technician,**self.authorization)).json()['record']
        self.login('operator');self.assertEqual(self.http.get(path).status_code,200)
        with self.server.database() as db:db.execute('UPDATE operational_cases SET assignee_id=NULL WHERE id=?',(case['id'],))
        self.assertEqual(self.http.get(path).status_code,404)
        with self.server.database() as db:db.execute('UPDATE users SET disabled=1 WHERE id=?',(self.technician,))
        self.assertIn(self.http.get(path).status_code,(401,403))
        self.http.cookies.clear();self.assertEqual(self.http.get(path).status_code,401)

    def test_exact_work_lookup_keeps_frozen_context_and_current_start_review(self):
        case,order=self.prepared_order('approved');path='/api/operational/order/'+order['id']+'/record'
        self.login('operator');reply=self.http.get(path);self.assertEqual(reply.status_code,200,reply.text)
        self.assertEqual(reply.json()['record']['case_snapshot_sha256'],order['case_snapshot_sha256'])
        self.assertEqual(reply.json()['record']['start_review']['state'],'ready')
        with self.server.database() as db:db.execute('UPDATE operational_cases SET revision=revision+1 WHERE id=?',(case['id'],))
        self.assertEqual(self.http.get(path).json()['record']['start_review']['state'],'source-case-changed')
        with self.server.database() as db:db.execute("UPDATE operational_orders SET case_snapshot='{}' WHERE id=?",(order['id'],))
        self.assertEqual(self.http.get(path).status_code,503)

    def test_review_export_hash_evidence_metadata_and_no_workflow_mutation(self):
        import hashlib
        from operational_workflow import canonical
        self.rule(threshold=-1);self.assertEqual(self.ingest(temp_c=0).status_code,201);case=self.summary()['cases'][0]
        upload=self.http.post('/api/operational/evidence/case/'+case['id'],params={'filename':'private.txt'},content=b'Private fixture payload',headers={'content-type':'text/plain','x-edgeops-csrf':self.http.cookies.get('edgeops_csrf')})
        self.assertEqual(upload.status_code,201)
        before=self.summary()['cases'];inbox=self.http.get('/api/operational/notifications').json()['items']
        reply=self.http.get('/api/operational/case/'+case['id']+'/review-export');self.assertEqual(reply.status_code,200,reply.text)
        self.assertIn('attachment;',reply.headers['content-disposition']);self.assertEqual(reply.headers['cache-control'],'no-store')
        envelope=reply.json();report=envelope['report'];self.assertEqual(envelope['report_sha256'],hashlib.sha256(canonical(report).encode()).hexdigest())
        self.assertFalse(envelope['digitally_signed']);self.assertFalse(report['production_ready']);self.assertFalse(report['physical_work_verified'])
        self.assertEqual(report['record']['last_snapshot']['value'],0);self.assertTrue(report['history']['complete'])
        self.assertEqual(report['evidence']['files'][0]['sha256'],upload.json()['file']['sha256']);self.assertFalse(report['evidence']['file_payloads_included'])
        self.assertNotIn('Private fixture payload',reply.text);self.assertNotIn(self.token,reply.text);self.assertNotIn(self.password,reply.text)
        self.assertEqual(self.summary()['cases'],before);self.assertEqual(self.http.get('/api/operational/notifications').json()['items'],inbox)

    def test_review_export_current_access_and_frozen_order_context(self):
        case,order=self.prepared_order('approved');case_path='/api/operational/case/'+case['id']+'/review-export';order_path='/api/operational/order/'+order['id']+'/review-export'
        self.login('operator');self.assertEqual(self.http.get(case_path).status_code,404)
        reply=self.http.get(order_path);self.assertEqual(reply.status_code,200,reply.text)
        record=reply.json()['report']['record'];self.assertEqual(record['case_snapshot_sha256'],order['case_snapshot_sha256']);self.assertNotIn('request_hash',record)
        self.login('auditor');self.assertEqual(self.http.get(case_path).status_code,200);self.assertEqual(self.http.get(order_path).status_code,200)
        self.login('operator')
        with self.server.database() as db:db.execute('UPDATE users SET disabled=1 WHERE id=?',(self.technician,))
        self.assertIn(self.http.get(order_path).status_code,(401,403))
        self.http.cookies.clear();self.assertEqual(self.http.get(order_path).status_code,401)

    def test_review_export_declares_truncated_history_and_refuses_corrupt_context(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0];path='/api/operational/case/'+case['id']+'/review-export'
        with self.server.database() as db:
            event=dict(db.execute("SELECT * FROM operational_events WHERE kind='case' AND record_id=?",(case['id'],)).fetchone())
            for _ in range(201):db.execute('INSERT INTO operational_events(kind,record_id,revision,actor_id,action,note,snapshot_json,time_utc) VALUES(?,?,?,?,?,?,?,?)',tuple(event[k] for k in ('kind','record_id','revision','actor_id','action','note','snapshot_json','time_utc')))
        report=self.http.get(path).json()['report'];self.assertFalse(report['history']['complete']);self.assertEqual(report['history']['total'],202);self.assertEqual(report['history']['returned'],200)
        self.assertEqual(len(report['history']['events']),200)
        with self.server.database() as db:db.execute("UPDATE operational_events SET snapshot_json='{}' WHERE kind='case' AND record_id=?",(case['id'],))
        self.assertEqual(self.http.get(path).status_code,503)

    def test_review_export_cancelled_order_keeps_context_and_refuses_tampering(self):
        case,order=self.prepared_order('approved');self.login('admin');self.assertEqual(self.action('orders',order,'cancel').status_code,200)
        path='/api/operational/order/'+order['id']+'/review-export';report=self.http.get(path).json()['report']
        self.assertEqual(report['record']['state'],'cancelled');self.assertEqual(report['record']['case_snapshot_sha256'],order['case_snapshot_sha256'])
        self.assertEqual(report['history']['events'][0]['action'],'cancel');self.assertIsNotNone(report['history']['events'][0]['actor_id'])
        with self.server.database() as db:db.execute("UPDATE operational_orders SET case_snapshot='{}' WHERE id=?",(order['id'],))
        self.assertEqual(self.http.get(path).status_code,503)

    def test_start_review_reports_current_approval_without_authorizing_equipment(self):
        case,order=self.prepared_order('approved');review=self.summary()['orders'][0]['start_review']
        self.assertEqual(review['state'],'ready');self.assertFalse(review['equipment_authorized'])
        self.login('operator');self.assertEqual(self.summary()['orders'][0]['start_review']['state'],'ready')
        current=self.action('orders',order,'start').json()['record']
        self.assertEqual(current['state'],'in-progress');self.assertEqual(self.summary()['orders'][0]['start_review']['state'],'not-approved')

    def test_start_review_detects_changed_approval_authority_and_blocks_start(self):
        case,order=self.prepared_order('approved')
        with self.server.database() as db:
            db.execute('INSERT INTO account_controls VALUES(?,2,?) ON CONFLICT(user_id) DO UPDATE SET revision=2',(order['approver_id'],self.timestamp))
        self.login('operator');review=self.summary()['orders'][0]['start_review']
        self.assertEqual(review['state'],'approval-authority-changed');self.assertNotIn('approver_revision',review)
        self.assertEqual(self.action('orders',order,'start').status_code,409)
        self.assertEqual(self.summary()['orders'][0]['state'],'approved')

    def test_start_review_detects_unavailable_technician(self):
        case,order=self.prepared_order('approved');self.login('admin')
        with self.server.database() as db:db.execute('UPDATE users SET disabled=1 WHERE id=?',(self.technician,))
        self.assertEqual(self.summary()['orders'][0]['start_review']['state'],'technician-unavailable')
        self.assertEqual(self.action('orders',order,'cancel').status_code,200)

    def test_approval_requires_assignee_to_remain_eligible(self):
        case,order=self.prepared_order('submitted');self.login('reviewer')
        for role,disabled in [('operator',1),('auditor',0)]:
            with self.server.database() as db:db.execute('UPDATE users SET role=?,disabled=? WHERE id=?',(role,disabled,self.technician))
            self.assertEqual(self.action('orders',order,'approve').status_code,422)
            self.assertEqual(self.summary()['orders'][0]['state'],'submitted')
        with self.server.database() as db:db.execute("UPDATE users SET role='operator',disabled=0 WHERE id=?",(self.technician,))
        self.assertEqual(self.action('orders',order,'approve').status_code,200)

    def test_start_review_detects_source_change_without_exposing_hidden_case(self):
        case,order=self.prepared_order('approved');self.login('admin')
        self.assertEqual(self.action('cases',case,'acknowledge').status_code,200)
        self.login('operator');summary=self.summary();self.assertEqual(summary['cases'],[])
        self.assertEqual(summary['orders'][0]['start_review']['state'],'source-case-changed')
        self.assertEqual(self.action('orders',order,'start').status_code,409)

    def test_cancel_unstarted_work_preserves_source_context_and_is_terminal(self):
        case,order=self.prepared_order('approved');context=order['case_snapshot_sha256']
        self.login('admin');reply=self.action('orders',order,'cancel')
        self.assertEqual(reply.status_code,200,reply.text);cancelled=reply.json()['record']
        self.assertEqual(cancelled['state'],'cancelled');self.assertEqual(cancelled['revision'],order['revision']+1)
        self.assertEqual(cancelled['case_snapshot_sha256'],context);self.assertEqual(cancelled['approver_id'],order['approver_id'])
        self.assertEqual(self.summary()['cases'][0]['revision'],case['revision'])
        self.assertEqual(self.summary()['cases'][0]['state'],case['state']);self.assertFalse(reply.json()['physical_work_verified'])
        self.assertEqual(self.action('orders',cancelled,'cancel').status_code,409)
        self.login('operator');self.assertEqual(self.action('orders',cancelled,'start').status_code,409)
        self.login('admin');history=self.http.get('/api/operational/order/'+order['id']+'/history').json()['events']
        self.assertEqual([x['action'] for x in history],['cancel','approve','submit','order_created'])
        self.assertIn('Explicit isolated review decision',history[0]['note'])

    def test_cancel_requires_reason_csrf_current_revision_and_authorized_actor(self):
        case,order=self.prepared_order()
        self.assertEqual(self.action('orders',order,'cancel',note='').status_code,422)
        self.assertEqual(self.action('orders',order,'cancel',expected_revision=99).status_code,409)
        body=dict(expected_revision=order['revision'],action='cancel',note='Cancellation must require the existing CSRF protection.')
        self.assertEqual(self.post('/api/operational/orders/'+order['id']+'/action',body,False).status_code,403)
        self.login('operator');self.assertEqual(self.action('orders',order,'cancel').status_code,403)
        self.login('auditor');self.assertEqual(self.action('orders',order,'cancel').status_code,403)
        self.login('reviewer');self.assertEqual(self.action('orders',order,'cancel').status_code,200)

    def test_creator_can_cancel_submitted_work_but_started_work_cannot_be_cancelled(self):
        case,order=self.prepared_order('submitted')
        self.assertEqual(self.action('orders',order,'cancel').status_code,200)
        # A separate request key keeps the first cancelled record immutable.
        self.login('admin')
        created=self.post('/api/operational/orders',dict(case_id=case['id'],expected_case_revision=case['revision'],expected_last_frame=case['last_frame'],request_key='e'*32,title='Separate started fixture',procedure='Record an independent software-only workflow for cancellation boundaries.',technician_id=self.technician))
        order=created.json()['record'];order=self.action('orders',order,'submit').json()['record']
        self.login('reviewer');order=self.action('orders',order,'approve').json()['record']
        self.login('operator');order=self.action('orders',order,'start').json()['record']
        self.login('admin');self.assertEqual(self.action('orders',order,'cancel').status_code,409)
        self.assertEqual(self.summary()['orders'][0]['state'],'in-progress')

    def test_cancel_freezes_evidence_and_keeps_retained_file_downloadable(self):
        case,order=self.prepared_order();path='/api/operational/evidence/order/'+order['id']
        reply=self.http.post(path,params={'filename':'retained.txt'},content=b'Fixture cancellation evidence',headers={'content-type':'text/plain','x-edgeops-csrf':self.http.cookies.get('edgeops_csrf')})
        self.assertEqual(reply.status_code,201,reply.text);file=reply.json()['file']
        self.assertEqual(self.action('orders',order,'cancel').status_code,200)
        reply=self.http.post(path,params={'filename':'later.txt'},content=b'New fixture upload',headers={'content-type':'text/plain','x-edgeops-csrf':self.http.cookies.get('edgeops_csrf')})
        self.assertEqual(reply.status_code,409)
        self.assertEqual(self.http.get('/api/operational/evidence/files/'+file['id']+'/download').content,b'Fixture cancellation evidence')
        self.assertEqual(len(self.http.get(path).json()['files']),1)

    def test_concurrent_start_and_cancel_only_one_revision_wins(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201);case=self.summary()['cases'][0]
        case=self.post('/api/operational/cases/'+case['id']+'/assign',dict(expected_revision=case['revision'],assignee_id=self.technician,**self.authorization)).json()['record']
        self.login('operator');order=self.order(case).json()['record'];order=self.action('orders',order,'submit').json()['record']
        self.login('reviewer');order=self.action('orders',order,'approve').json()['record'];self.login('operator')
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda action:self.action('orders',order,action).status_code,['start','cancel']))
        self.assertEqual(sorted(codes),[200,409]);current=self.summary()['orders'][0]
        self.assertIn(current['state'],('in-progress','cancelled'));self.assertEqual(current['revision'],order['revision']+1)
        events=self.http.get('/api/operational/order/'+order['id']+'/history').json()['events']
        self.assertEqual(sum(e['action'] in ('start','cancel') for e in events),1)

    def test_cancel_event_failure_rolls_back_state_and_notification(self):
        from unittest.mock import patch
        import operational_workflow
        case,order=self.prepared_order();before=self.http.get('/api/operational/order/'+order['id']+'/history').json()['events']
        with patch.object(operational_workflow,'event',side_effect=RuntimeError('fixture history unavailable')):
            with self.assertRaises(RuntimeError):self.action('orders',order,'cancel')
        current=self.summary()['orders'][0];self.assertEqual(current['state'],'draft');self.assertEqual(current['revision'],order['revision'])
        self.assertEqual(self.http.get('/api/operational/order/'+order['id']+'/history').json()['events'],before)
        self.assertEqual(self.action('orders',order,'cancel').status_code,200)

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

    def test_assignment_choices_are_minimal_current_and_revalidated(self):
        people=self.summary()['assignees']
        self.assertTrue(any(person['id']==self.technician for person in people))
        self.assertTrue(all(set(person)=={'id','email','role'} for person in people))
        self.assertFalse(any(person['role']=='auditor' for person in people))
        self.rule();self.ingest(temp_c=40);case=self.summary()['cases'][0]
        with self.server.database() as db:db.execute('UPDATE users SET disabled=1 WHERE id=?',(self.technician,))
        self.assertFalse(any(person['id']==self.technician for person in self.summary()['assignees']))
        response=self.post('/api/operational/cases/'+case['id']+'/assign',dict(expected_revision=case['revision'],assignee_id=self.technician,**self.authorization))
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.order(case).status_code,422)
        self.login('auditor');self.assertEqual(self.summary()['assignees'],[])
        with self.server.database() as db:db.execute('UPDATE users SET disabled=0 WHERE id=?',(self.technician,))
        self.login('operator');self.assertTrue(self.summary()['assignees'])

    def test_signin_preserves_only_the_enumerated_local_view(self):
        for view in ('registered','demonstration'):
            response=self.http.get('/signin?view='+view,follow_redirects=False)
            self.assertEqual(response.headers['location'],'/app?view='+view)
        self.http.cookies.clear()
        for view in ('registered','demonstration'):
            response=self.http.get('/app?view='+view,follow_redirects=False)
            self.assertEqual(response.headers['location'],'/signin?view='+view)
        for value in ('https://example.invalid','//example.invalid','registered%26next%3Dhttps://example.invalid'):
            response=self.http.get('/app?view='+value,follow_redirects=False)
            self.assertEqual(response.headers['location'],'/signin')
        self.assertEqual(self.http.get('/app?next=https://example.invalid',follow_redirects=False).headers['location'],'/signin')

    def test_out_of_order_matches_preserve_frame_extrema_and_frozen_work_context(self):
        self.rule()
        for index,value in [(30,50),(10,40),(20,45)]:self.assertEqual(self.ingest(index,temp_c=value).status_code,201)
        case=self.summary()['cases'][0]
        self.assertEqual((case['first_frame'],case['last_frame'],case['matched_records']),(10,30,3))
        self.assertEqual(case['first_snapshot']['value'],40);self.assertEqual(case['last_snapshot']['value'],50)
        saved=self.order(case);self.assertEqual(saved.status_code,201,saved.text);context_hash=saved.json()['record']['case_snapshot_sha256']
        for index,value in [(50,70),(40,60)]:self.assertEqual(self.ingest(index,temp_c=value).status_code,201)
        self.assertEqual(self.ingest(40,temp_c=60).status_code,200)
        data=self.summary();case=data['cases'][0]
        self.assertEqual((case['first_frame'],case['last_frame'],case['matched_records']),(10,50,5))
        self.assertEqual(case['last_snapshot']['value'],70)
        self.assertEqual(case['first_snapshot']['frame_index'],10);self.assertEqual(case['last_snapshot']['frame_index'],50)
        self.assertEqual(data['orders'][0]['case_snapshot_sha256'],context_hash)
        self.assertEqual(data['orders'][0]['case_snapshot']['last_frame'],30)

    def test_receipt_display_boundaries_and_unknown_clocks(self):
        from operational_workflow import receipt_timing
        reference=datetime(2026,11,27,tzinfo=timezone.utc)
        for age,delay,expected in [(0,0,'recent-receipt'),(15,15,'recent-receipt'),(15.001,0,'stale-receipt'),(0,15.001,'delayed-receipt'),(-6,0,'clock-difference'),(0,-6,'clock-difference')]:
            server=reference-timedelta(seconds=age)
            reading=dict(server_received_at=server.isoformat(),gateway_received_at=(server-timedelta(seconds=delay)).isoformat())
            with self.subTest(age=age,delay=delay):
                result=receipt_timing(reading,reference.isoformat());self.assertEqual(result['state'],expected);self.assertFalse(result['acquisition_time_verified'])
        self.assertEqual(receipt_timing(None,reference.isoformat())['state'],'no-readings')
        self.assertEqual(receipt_timing(dict(server_received_at='invalid',gateway_received_at='invalid'),reference.isoformat())['state'],'timing-unavailable')
        self.assertEqual(receipt_timing(dict(server_received_at='2026-11-27T00:00:00',gateway_received_at=reference.isoformat()),reference.isoformat())['state'],'timing-unavailable')

    def test_server_referenced_receipt_age_never_promotes_unavailable_channels(self):
        from unittest.mock import patch
        self.assertEqual(self.summary()['assets'][0]['receipt']['state'],'no-readings')
        self.assertEqual(self.ingest(temp_c=0,ds18b20_valid=False,valid=False).status_code,201)
        asset=self.summary()['assets'][0];self.assertEqual(asset['receipt']['state'],'recent-receipt')
        self.assertIsNone(asset['latest']['values']['temperature_c']);self.assertEqual(asset['latest']['values']['current_a'],0)
        received=datetime.fromisoformat(asset['latest']['server_received_at'])
        with patch('operational_workflow.now',return_value=(received+timedelta(seconds=16)).isoformat()):
            stale=self.summary()['assets'][0];self.assertEqual(stale['receipt']['state'],'stale-receipt');self.assertIsNone(stale['latest']['values']['temperature_c'])
        with patch('operational_workflow.now',return_value=(received-timedelta(seconds=6)).isoformat()):
            self.assertEqual(self.summary()['assets'][0]['receipt']['state'],'clock-difference')

    def test_recent_server_receipt_can_still_be_delayed_gateway_data(self):
        self.timestamp=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        self.assertEqual(self.ingest(temp_c=0).status_code,201)
        asset=self.summary()['assets'][0];self.assertEqual(asset['receipt']['state'],'delayed-receipt')
        self.assertEqual(asset['latest']['values']['temperature_c'],0);self.assertEqual(asset['source_type'],'software-fixture')
        self.assertFalse(asset['receipt']['acquisition_time_verified'])

    def resolved_case(self,index=10):
        self.rule();self.assertEqual(self.ingest(index,temp_c=40).status_code,201)
        case=self.summary()['cases'][0]
        case=self.action('cases',case,'acknowledge').json()['record']
        reply=self.action('cases',case,'resolve',evidence_refs='Reviewed fixture record; physical work remains unverified.')
        self.assertEqual(reply.status_code,200,reply.text);return reply.json()['record']

    def test_newer_match_reopens_review_and_preserves_original_resolution(self):
        case=self.resolved_case();route='/api/operational/case/'+case['id']+'/history'
        previous=self.http.get(route).json()['events'];resolution=next(event for event in previous if event['action']=='resolve')
        self.assertEqual(resolution['captured_state'],'resolved');self.assertEqual(resolution['captured_last_frame'],10)
        self.assertEqual(self.ingest(11,temp_c=60).status_code,201)
        reopened=self.summary()['cases'][0]
        self.assertEqual(reopened['id'],case['id']);self.assertEqual(reopened['state'],'open');self.assertEqual(reopened['revision'],case['revision']+1)
        events=self.http.get(route).json()['events'];self.assertEqual(events[0]['action'],'threshold_reobserved');self.assertEqual(events[0]['captured_value'],60)
        self.assertEqual(next(event for event in events if event['action']=='resolve'),resolution)
        notices=self.http.get('/api/operational/notifications').json()['items']
        recurrence=[item for item in notices if 'review reopened' in item['subject']]
        self.assertEqual(len(recurrence),1);self.assertEqual(recurrence[0]['email_state'],'local-only-fixture')

    def test_concurrent_newer_matches_and_retries_reopen_only_once(self):
        case=self.resolved_case()
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda index:self.ingest(index,temp_c=50).status_code,(11,12)))
        self.assertEqual(codes,[201,201]);self.assertEqual(self.ingest(11,temp_c=50).status_code,200)
        reopened=self.summary()['cases'][0]
        self.assertEqual((reopened['revision'],reopened['matched_records'],reopened['last_frame']),(case['revision']+1,3,12))
        events=self.http.get('/api/operational/case/'+case['id']+'/history').json()['events']
        self.assertEqual(sum(event['action']=='threshold_reobserved' for event in events),1)

    def test_late_nonmatching_invalid_delayed_and_disabled_inputs_do_not_reopen(self):
        case=self.resolved_case()
        self.assertEqual(self.ingest(5,temp_c=50).status_code,201)
        self.assertEqual(self.ingest(11,temp_c=0).status_code,201)
        self.assertEqual(self.ingest(12,temp_c=50,ds18b20_valid=False,valid=False).status_code,201)
        self.timestamp=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat();self.assertEqual(self.ingest(13,temp_c=50).status_code,201)
        self.timestamp=(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat();self.assertEqual(self.ingest(14,temp_c=50).status_code,201)
        self.timestamp=datetime.now(timezone.utc).isoformat()
        rule=self.summary()['rules'][0]
        self.assertEqual(self.post('/api/operational/rules/'+rule['id']+'/disable',dict(expected_revision=rule['revision'],**self.authorization)).status_code,200)
        self.assertEqual(self.ingest(15,temp_c=50).status_code,201)
        row=self.summary()['cases'][0];self.assertEqual((row['state'],row['revision'],row['matched_records']),('resolved',case['revision'],2))

    def test_reopened_source_blocks_start_of_an_old_approved_work_record(self):
        self.rule();self.ingest(temp_c=40);case=self.summary()['cases'][0]
        order=self.order(case).json()['record'];context_hash=order['case_snapshot_sha256']
        order=self.action('orders',order,'submit').json()['record'];self.login('reviewer');order=self.action('orders',order,'approve').json()['record']
        self.login('admin');case=self.action('cases',case,'acknowledge').json()['record'];self.action('cases',case,'resolve',evidence_refs='Fixture resolution only')
        self.ingest(1,temp_c=50);self.login('operator')
        response=self.action('orders',order,'start');self.assertEqual(response.status_code,409,response.text);self.assertIn('Source case changed',response.text)
        current=self.summary()['orders'][0];self.assertEqual(current['state'],'approved');self.assertEqual(current['case_snapshot_sha256'],context_hash)

    def test_in_progress_work_can_be_documented_without_closing_reopened_case(self):
        self.rule();self.ingest(temp_c=40);case=self.summary()['cases'][0]
        order=self.order(case).json()['record'];context_hash=order['case_snapshot_sha256']
        order=self.action('orders',order,'submit').json()['record'];self.login('reviewer');order=self.action('orders',order,'approve').json()['record']
        self.login('operator');order=self.action('orders',order,'start').json()['record']
        self.login('admin');case=self.action('cases',case,'acknowledge').json()['record'];self.action('cases',case,'resolve',evidence_refs='Fixture resolution only');self.ingest(1,temp_c=50)
        self.login('operator');reply=self.action('orders',order,'complete',evidence_refs='Existing fixture execution evidence');self.assertEqual(reply.status_code,200,reply.text);order=reply.json()['record']
        self.login('reviewer');reply=self.action('orders',order,'verify',evidence_refs='Independent fixture closure evidence');self.assertEqual(reply.status_code,200,reply.text)
        self.assertEqual(reply.json()['record']['case_snapshot_sha256'],context_hash);self.assertEqual(self.summary()['cases'][0]['state'],'open');self.assertFalse(reply.json()['physical_work_verified'])

    def test_reopen_event_failure_rolls_back_reading_and_case_until_retry(self):
        from unittest.mock import patch
        case=self.resolved_case()
        with patch('operational_workflow.event',side_effect=RuntimeError('Fixture event storage unavailable')):
            with self.assertRaises(RuntimeError):self.ingest(11,temp_c=50)
        row=self.summary()['cases'][0];self.assertEqual((row['state'],row['revision'],row['matched_records']),('resolved',case['revision'],1))
        with self.server.database() as db:self.assertEqual(db.execute('SELECT count(*) FROM bench_samples').fetchone()[0],1)
        self.assertEqual(self.ingest(11,temp_c=50).status_code,201);self.assertEqual(self.summary()['cases'][0]['state'],'open')
