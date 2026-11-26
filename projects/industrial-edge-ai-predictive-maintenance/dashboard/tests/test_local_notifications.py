"""Disposable-store tests for atomic local routing, delivery and current authorization."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import local_notifications as notifications
import recovery
import test_incidents as fixture
import test_correlation as correlation_fixture


class LocalNotificationTests(unittest.TestCase):
    login=fixture.IncidentApiTests.login
    post=fixture.IncidentApiTests.post
    create=fixture.IncidentApiTests.create
    action=fixture.IncidentApiTests.action
    def setUp(self):fixture.IncidentApiTests.setUp(self)

    def inbox(self,**params):
        response=self.http.get('/api/local-notifications',params=params)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def subscribe(self,enabled=True,severities=None):
        previous=self.inbox()['preference']
        response=self.post('/api/local-notifications/preference',dict(expected_revision=previous['revision'],enabled=enabled,severities=severities or ['watch']))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def deliver(self):
        response=self.post('/api/local-notifications/deliver',None)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def count(self):
        with self.server.database() as db:return db.execute('SELECT count(*) FROM local_notification_outbox').fetchone()[0]

    def test_opt_in_future_only_and_exact_severity(self):
        self.create();self.assertEqual(self.count(),0)
        self.subscribe(severities=['critical']);self.create();self.assertEqual(self.count(),0)
        body=fixture.payload();body['severity']='critical'
        self.assertEqual(self.post('/api/incidents',body).status_code,200)
        self.assertEqual(self.inbox()['total'],0);self.assertEqual(self.inbox()['own_outbox_counts'],{'pending':1})
        self.assertEqual(self.deliver()['delivered'],1)
        data=self.inbox();self.assertEqual(data['unread'],1);self.assertFalse(data['production_ready']);self.assertFalse(data['external_notifications_sent'])

    def test_concurrent_response_loss_retries_deduplicate_event_and_delivery(self):
        self.subscribe();body=fixture.payload()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.post('/api/incidents',body),range(2)))
        self.assertEqual([r.status_code for r in results],[200,200]);self.assertEqual(self.count(),1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            delivered=list(pool.map(lambda _:self.post('/api/local-notifications/deliver',None),range(2)))
        self.assertEqual(sum(r.json()['delivered'] for r in delivered),1)
        self.assertEqual(self.inbox()['total'],1)
        self.server.init_db();self.assertEqual(self.inbox()['total'],1)

    def test_read_is_idempotent_and_does_not_acknowledge_incident(self):
        self.subscribe();incident=self.create();self.deliver();item=self.inbox()['items'][0]
        for _ in range(2):self.assertEqual(self.post('/api/local-notifications/'+item['id']+'/read',None).status_code,200)
        self.assertEqual(self.inbox()['unread'],0)
        self.assertEqual(self.http.get('/api/incidents/'+incident['id']).json()['incident']['state'],'open')

    def test_operator_visibility_and_recipient_isolation(self):
        self.subscribe();self.login('operator');self.subscribe();own=self.create()
        self.login('admin');foreign=self.create();self.deliver();admin_item=self.inbox()['items'][0]
        self.login('operator');self.assertEqual(self.deliver()['delivered'],1)
        self.assertEqual([x['incident_id'] for x in self.inbox()['items']],[own['id']])
        self.assertEqual(self.post('/api/local-notifications/'+admin_item['id']+'/read',None).status_code,404)
        self.assertNotIn(foreign['id'],str(self.inbox()))

    def test_access_removed_between_queue_and_delivery_is_suppressed(self):
        self.login('operator');self.subscribe();incident=self.create()
        with self.server.database() as db:
            admin=db.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
            db.execute('UPDATE synthetic_incidents SET creator_id=? WHERE id=?',(admin,incident['id']))
        self.assertEqual(self.deliver()['suppressed'],1);self.assertEqual(self.inbox()['total'],0)

    def test_account_revision_invalidates_route_queue_and_delivered_access(self):
        self.subscribe();self.create();self.deliver();self.create()
        with self.server.database() as db:
            uid=db.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
            db.execute("INSERT INTO account_controls VALUES(?,2,'test') ON CONFLICT(user_id) DO UPDATE SET revision=revision+1",(uid,))
        self.assertTrue(self.inbox()['preference']['requires_reconfirmation']);self.assertEqual(self.inbox()['total'],0)
        self.assertEqual(self.deliver()['suppressed'],1)
        self.subscribe();self.create();self.assertEqual(self.deliver()['delivered'],1)

    def test_disable_or_change_cancels_pending_and_never_replays(self):
        self.subscribe();self.create();self.subscribe(False)
        self.assertEqual(self.inbox()['own_outbox_counts'],{'suppressed':1})
        self.subscribe();self.assertEqual(self.deliver()['delivered'],0)
        self.create();self.subscribe(severities=['critical']);self.assertEqual(self.deliver()['delivered'],0)

    def test_capacity_failure_rolls_back_incident_and_history(self):
        self.subscribe()
        with patch.object(notifications,'MAX_RECORDS',0):
            self.assertEqual(self.post('/api/incidents',fixture.payload()).status_code,429)
        self.assertEqual(self.count(),0)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM synthetic_incidents').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM synthetic_incident_events').fetchone()[0],0)

    def test_csrf_auth_validation_stale_preference_and_auditor_self_subscription(self):
        self.assertEqual(self.post('/api/local-notifications/deliver',None,False).status_code,403)
        for changes in ({'enabled':True,'severities':[]},{'enabled':True,'severities':['watch','watch']},{'enabled':1,'severities':['watch']},{'enabled':True,'severities':['email']}):
            self.assertEqual(self.post('/api/local-notifications/preference',dict(expected_revision=0,**changes)).status_code,422)
        self.subscribe()
        self.assertEqual(self.post('/api/local-notifications/preference',dict(expected_revision=0,enabled=False,severities=[])).status_code,409)
        self.login('auditor');self.subscribe();self.assertEqual(self.inbox()['preference']['revision'],1)
        self.http.cookies.clear();self.assertEqual(self.http.get('/api/local-notifications').status_code,401)

    def test_paging_and_multiple_incident_revisions(self):
        self.subscribe();incident=self.create();self.action(incident,'acknowledge');self.deliver()
        first=self.inbox(limit=1);second=self.inbox(limit=1,offset=1)
        self.assertEqual(first['total'],2);self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
        self.assertEqual({first['items'][0]['incident_revision'],second['items'][0]['incident_revision']},{1,2})

    def test_concurrent_preference_changes_use_revision_guard(self):
        body=dict(expected_revision=0,enabled=True,severities=['watch'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes=list(pool.map(lambda _:self.post('/api/local-notifications/preference',body).status_code,range(2)))
        self.assertEqual(sorted(codes),[200,409]);self.assertEqual(self.inbox()['preference']['revision'],1)

    def test_disabled_recipient_is_not_queued_and_delivery_failure_rolls_back(self):
        self.login('auditor');self.subscribe();self.login('admin')
        with self.server.database() as db:db.execute("UPDATE users SET disabled=1 WHERE role='auditor'")
        self.create();self.assertEqual(self.count(),0)
        self.subscribe();self.create()
        # Simulated transaction interruption after delivery updates: no partial delivery survives.
        with self.server.database() as db:
            actor=db.execute("SELECT * FROM users WHERE role='admin'").fetchone()
            db.execute('BEGIN IMMEDIATE');self.assertEqual(notifications.deliver(db,actor)['delivered'],1);db.rollback()
        self.assertEqual(self.inbox()['own_outbox_counts'],{'pending':1})
        self.assertEqual(self.deliver()['delivered'],1)

    def test_restore_retains_history_disables_routes_and_cancels_pending(self):
        self.subscribe();self.create();self.deliver();self.create();root=Path(self.temp.name)
        recovery.create_backup(self.server.DB_PATH,root/'backup')
        report=recovery.restore_backup(root/'backup',root/'restored')
        self.assertEqual(report['notification_routes_disabled'],1);self.assertEqual(report['pending_notifications_suppressed'],1)
        with closing(sqlite3.connect(root/'restored/dashboard.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT enabled FROM local_notification_preferences').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM local_notification_outbox').fetchone()[0],2)

    def test_correlation_handoff_routes_once_with_human_incident_author(self):
        self.subscribe(severities=['critical'])
        fixture_body=correlation_fixture.fixture.binding('corr-device');fixture_body.update(site_id='corr-site',asset_id='MTR-001')
        self.assertEqual(self.post('/api/acquisition-bindings',fixture_body).status_code,201)
        policy=correlation_fixture.CorrelationTests.policy_body(self)
        self.assertEqual(self.post('/api/correlation/policies',policy).status_code,201)
        obs=correlation_fixture.CorrelationTests.envelope(self)
        self.assertEqual(self.post('/api/acquisition/ingest',obs).status_code,201);self.assertEqual(self.count(),0)
        case=self.http.get('/api/correlation/cases').json()['cases'][0]
        body=dict(expected_revision=case['revision'],note='Reviewed synthetic evidence before local governed incident handoff.')
        for _ in range(2):self.assertEqual(self.post('/api/correlation/cases/'+case['id']+'/handoff',body).status_code,200)
        self.assertEqual(self.count(),1);self.assertEqual(self.deliver()['delivered'],1)
        self.assertEqual(self.inbox()['items'][0]['severity'],'critical')


if __name__=='__main__':unittest.main()
