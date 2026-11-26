import hashlib
import json
import unittest
import test_operational_workflow as fixture
from test_bench_ingress import frame,gateway


class BaselineTests(unittest.TestCase):
    setUp=fixture.OperationalTests.setUp
    login=fixture.OperationalTests.login
    post=fixture.OperationalTests.post

    def runs(self,holdout=50):
        identities=['1'*32,'2'*32,'3'*32]
        for number,identity in enumerate(identities):
            for index in range(5):
                fields=frame();fields['temp_c']=20+index*.1 if number<2 else holdout+index
                body=gateway.sample(fields,identity,index,'software-fixture')
                response=self.http.post('/api/bench/readings',json=body,headers={'authorization':'Bearer '+self.token})
                self.assertEqual(response.status_code,201,response.text)
        return identities

    def fit(self,identities,**changes):
        body=dict(request_key='c'*32,asset=self.asset['id'],expected_asset_revision=1,channel='temperature_c',run_ids=identities,
                  qualification_note='Isolated software fixture baseline study; no physical qualification.',minimum_score_threshold=3.0)
        body.update(changes);return self.post('/api/operational/models',body)

    def catalog(self):return self.http.get('/api/operational/models')

    def activate(self,row,action='activate'):
        return self.post('/api/operational/models/'+row['id']+'/'+action,dict(expected_revision=row['revision'],artifact_sha256=row['artifact_sha256'],**self.authorization))

    def test_session_split_holdout_not_fit_and_independent_activation(self):
        identities=self.runs();response=self.fit(list(reversed(identities)));self.assertEqual(response.status_code,200,response.text)
        result=response.json();self.assertEqual(result['report']['training_runs'],identities[:1]);self.assertEqual(result['report']['holdout_runs'],identities[-1:])
        self.assertAlmostEqual(result['artifact']['center'],20.2)
        self.assertIsNone(result['report']['accuracy']);self.assertFalse(result['report']['physical_session_independence_verified'])
        row=self.catalog().json()['models'][0]
        self.assertEqual(self.activate(row).status_code,403)
        self.login('reviewer');response=self.activate(row);self.assertEqual(response.status_code,200,response.text)
        fields=frame();fields['temp_c']=50
        body=gateway.sample(fields,'4'*32,0,'software-fixture')
        for code in (201,200):self.assertEqual(self.http.post('/api/bench/readings',json=body,headers={'authorization':'Bearer '+self.token}).status_code,code)
        catalog=self.catalog().json();self.assertEqual(len(catalog['scores']),1);self.assertEqual(catalog['scores'][0]['decision'],'baseline-deviation')
        self.assertFalse(catalog['failure_prediction_validated']);self.assertFalse(catalog['equipment_authorized'])
        with self.server.database() as db:self.assertEqual(db.execute('SELECT count(*) FROM operational_orders').fetchone()[0],0)
        row=catalog['models'][0];self.assertEqual(self.activate(row,'retire').status_code,200)

    def test_training_identity_validation_and_no_mixed_source(self):
        identities=self.runs()
        result=self.fit(identities);self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(self.fit(identities).json()['created'])
        self.assertEqual(self.fit(identities,channel='current_a').status_code,409)
        self.assertEqual(self.fit(identities,request_key='d'*32,run_ids=[identities[0]]*3).status_code,422)
        with self.server.database() as db:db.execute("UPDATE bench_runs SET source_type='measured-unverified' WHERE id=?",(identities[1],))
        self.assertEqual(self.fit(identities,request_key='e'*32).status_code,422)
        self.login('auditor');self.assertEqual(self.fit(identities,request_key='f'*32).status_code,403)

    def test_revoked_release_abstains_and_corrupted_report_blocks(self):
        identities=self.runs();self.assertEqual(self.fit(identities).status_code,200)
        self.login('reviewer');row=self.catalog().json()['models'][0];self.assertEqual(self.activate(row).status_code,200)
        with self.server.database() as db:db.execute('UPDATE operational_models SET reviewer_revision=999')
        fields=frame();body=gateway.sample(fields,'5'*32,0,'software-fixture')
        self.assertEqual(self.http.post('/api/bench/readings',json=body,headers={'authorization':'Bearer '+self.token}).status_code,201)
        self.assertEqual(self.catalog().json()['scores'],[])
        with self.server.database() as db:db.execute("UPDATE operational_models SET report='{}'")
        self.assertEqual(self.catalog().status_code,503)

    def test_inactive_candidate_does_not_score_and_invalid_group_abstains(self):
        identities=self.runs();self.fit(identities)
        fields=frame();body=gateway.sample(fields,'6'*32,0,'software-fixture')
        self.assertEqual(self.http.post('/api/bench/readings',json=body,headers={'authorization':'Bearer '+self.token}).status_code,201)
        self.assertEqual(self.catalog().json()['scores'],[])
        self.login('reviewer');self.activate(self.catalog().json()['models'][0])
        fields.update(temp_c=0,ds18b20_valid=False,valid=False);body=gateway.sample(fields,'7'*32,0,'software-fixture')
        self.assertEqual(self.http.post('/api/bench/readings',json=body,headers={'authorization':'Bearer '+self.token}).status_code,201)
        score=self.catalog().json()['scores'][0];self.assertIsNone(score['score']);self.assertEqual(score['decision'],'unavailable')

    def test_rollback_reactivates_only_reviewed_retired_hash(self):
        self.fit(self.runs());self.login('reviewer');row=self.catalog().json()['models'][0]
        self.assertEqual(self.activate(row).status_code,200)
        active=self.catalog().json()['models'][0];self.assertEqual(self.activate(active,'retire').status_code,200)
        retired=self.catalog().json()['models'][0]
        self.assertEqual(self.activate(active,'rollback').status_code,409)
        self.login('admin');self.assertEqual(self.activate(retired,'rollback').status_code,403)
        self.login('reviewer');self.assertEqual(self.activate(retired,'rollback').status_code,200)
        self.assertEqual(self.catalog().json()['models'][0]['state'],'active')
