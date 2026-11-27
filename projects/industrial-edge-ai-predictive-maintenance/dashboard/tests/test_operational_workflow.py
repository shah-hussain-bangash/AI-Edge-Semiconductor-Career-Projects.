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
        body.update(changes);return self.post('/api/operational/'+kind+'/'+row['id']+'/action',body)

    def order(self,case):
        return self.post('/api/operational/orders',dict(case_id=case['id'],expected_case_revision=case['revision'],request_key='d'*32,title='Inspect fixture evidence',procedure='Review the captured software evidence without any equipment action.',technician_id=self.technician))

    def prepared_order(self, stage='draft'):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        case=self.summary()['cases'][0];order=self.order(case).json()['record']
        if stage!='draft':order=self.action('orders',order,'submit').json()['record']
        if stage in ('approved','in-progress'):
            self.login('reviewer');order=self.action('orders',order,'approve').json()['record']
        if stage=='in-progress':
            self.login('operator');order=self.action('orders',order,'start').json()['record']
        return case,order

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
        created=self.post('/api/operational/orders',dict(case_id=case['id'],expected_case_revision=case['revision'],request_key='e'*32,title='Separate started fixture',procedure='Record an independent software-only workflow for cancellation boundaries.',technician_id=self.technician))
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
