from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import followup_reminders as reminders
import notification_worker
import recovery
import test_notification_worker as fixture
import test_incident_followups as dates


class FollowupReminderTests(unittest.TestCase):
    login=fixture.NotificationWorkerTests.login
    post=fixture.NotificationWorkerTests.post
    create=fixture.NotificationWorkerTests.create
    inbox=fixture.NotificationWorkerTests.inbox
    subscribe=fixture.NotificationWorkerTests.subscribe
    configure=fixture.NotificationWorkerTests.configure
    save_due=dates.IncidentFollowupTests.save
    action=dates.IncidentFollowupTests.action
    def setUp(self):fixture.NotificationWorkerTests.setUp(self)

    def view(self):
        response=self.http.get('/api/follow-up-reminders');self.assertEqual(response.status_code,200,response.text);return response.json()

    def opt_in(self,enabled=True):
        revision=self.view()['preference']['revision']
        return self.post('/api/follow-up-reminders/preference',dict(expected_revision=revision,enabled=enabled))

    def tick(self,identity='first',advance=0):
        return notification_worker.tick(self.server.database,self.server.record_audit,identity,datetime.now(timezone.utc).timestamp()+advance)

    def prepare(self):
        self.subscribe();self.assertEqual(self.opt_in().status_code,200);self.configure()
        return self.save_due(self.create(),'2001-01-01T00:00:00Z').json()['incident']

    def test_explicit_opt_in_required_even_when_notification_worker_enabled(self):
        self.subscribe();self.configure();self.save_due(self.create(),'2001-01-01T00:00:00Z');self.tick()
        self.assertEqual(self.view()['total'],0)
        self.opt_in();self.tick(advance=6);self.assertEqual(self.view()['total'],1)

    def test_one_reminder_per_saved_due_date_and_idempotent_read(self):
        incident=self.prepare();self.tick();item=self.view()['items'][0]
        self.tick(advance=6);self.assertEqual(self.view()['total'],1)
        for _ in range(2):self.assertEqual(self.post('/api/follow-up-reminders/'+item['id']+'/read',None).status_code,200)
        self.assertEqual(self.view()['unread'],0)
        data=self.http.get('/api/incidents/'+incident['id']).json()['incident']
        self.assertEqual(data['state'],'open');self.assertEqual(data['revision'],2)

    def test_future_dates_wait_until_due_and_null_dates_never_trigger(self):
        self.subscribe();self.opt_in();self.configure();self.create()
        self.save_due(self.create(),'2099-01-01T00:00:00Z');self.tick();self.assertEqual(self.view()['total'],0)

    def test_schedule_change_hides_old_reminder_and_new_due_date_gets_new_reminder(self):
        incident=self.prepare();self.tick();old=self.view()['items'][0]
        self.save_due(incident,'2002-01-01T00:00:00Z')
        self.assertEqual(self.view()['total'],0)
        self.assertEqual(self.post('/api/follow-up-reminders/'+old['id']+'/read',None).status_code,404)
        self.tick(advance=6);self.assertEqual(self.view()['total'],1);self.assertNotEqual(self.view()['items'][0]['id'],old['id'])

    def test_resolution_cancels_reminder_and_reopen_does_not_repeat_old_schedule(self):
        incident=self.prepare();self.tick()
        incident=self.action(incident,'acknowledge').json()['incident'];incident=self.action(incident,'resolve').json()['incident']
        self.assertEqual(self.view()['total'],0);self.tick(advance=6)
        self.action(incident,'reopen');self.tick(advance=12);self.assertEqual(self.view()['total'],0)

    def test_disable_resubscribe_does_not_repeat_same_saved_due_date(self):
        self.prepare();self.tick();self.opt_in(False);self.assertEqual(self.view()['total'],0)
        self.opt_in();self.tick(advance=6);self.assertEqual(self.view()['total'],0)

    def test_recipient_scope_and_mark_read_isolation(self):
        self.prepare();self.tick();admin_item=self.view()['items'][0]
        self.login('operator');self.subscribe();self.opt_in();self.tick(advance=6)
        self.assertEqual(self.view()['total'],0)
        self.assertEqual(self.post('/api/follow-up-reminders/'+admin_item['id']+'/read',None).status_code,404)
        self.save_due(self.create(),'2001-01-01T00:00:00Z');self.tick(advance=12);self.assertEqual(self.view()['total'],1)

    def test_revoked_account_and_subscription_revision_hide_reminders(self):
        self.prepare();self.tick();self.subscribe(False);self.assertEqual(self.view()['total'],0)
        self.tick(advance=6)
        with self.server.database() as db:self.assertEqual(db.execute('SELECT state FROM followup_reminders').fetchone()[0],'cancelled')

    def test_exact_selected_severity(self):
        self.subscribe(severities=['critical']);self.opt_in();self.configure()
        incident=self.save_due(self.create(),'2001-01-01T00:00:00Z').json()['incident'];self.tick();self.assertEqual(self.view()['total'],0)
        self.post('/api/incidents/'+incident['id']+'/severity',dict(expected_revision=2,severity='critical',note='Review synthetic severity before reminder delivery.'))
        self.tick(advance=6);self.assertEqual(self.view()['items'][0]['severity'],'critical')

    def test_concurrent_passes_and_failure_rollback(self):
        self.prepare()
        with patch.object(notification_worker.inbox,'deliver',side_effect=RuntimeError('forced transaction interruption')):
            with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.view()['total'],0)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda name:self.tick(name),['a','b']))
        self.assertEqual(self.view()['total'],1)

    def test_capacity_does_not_stop_ordinary_notification_delivery(self):
        self.prepare()
        with patch.object(reminders,'MAX_RECORDS',0):
            self.tick();self.assertTrue(self.view()['capacity_reached'])
        self.assertEqual(self.view()['total'],0);self.assertGreater(self.inbox()['total'],0)

    def test_auth_csrf_revision_and_subscription_prerequisite(self):
        self.assertEqual(self.opt_in().status_code,409)
        self.subscribe();self.assertEqual(self.opt_in().status_code,200)
        self.assertEqual(self.post('/api/follow-up-reminders/preference',dict(expected_revision=0,enabled=False)).status_code,409)
        self.assertEqual(self.post('/api/follow-up-reminders/preference',dict(expected_revision=1,enabled=False),False).status_code,403)
        self.assertEqual(self.post('/api/follow-up-reminders/preference',dict(expected_revision=True,enabled=True)).status_code,422)
        self.http.cookies.clear();self.assertEqual(self.http.get('/api/follow-up-reminders').status_code,401)

    def test_restore_disables_reminder_preferences_and_cancels_history(self):
        self.prepare();self.tick();root=Path(self.temp.name)
        recovery.create_backup(self.server.DB_PATH,root/'backup');report=recovery.restore_backup(root/'backup',root/'restored')
        self.assertEqual(report['reminder_preferences_disabled'],1);self.assertEqual(report['followup_reminders_cancelled'],1)
        with closing(sqlite3.connect(root/'restored/dashboard.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM followup_reminders').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT state FROM followup_reminders').fetchone()[0],'cancelled')

    def test_global_worker_budget_includes_reminders_and_event_notifications(self):
        self.subscribe();self.opt_in();self.configure()
        for _ in range(40):self.save_due(self.create(),'2001-01-01T00:00:00Z')
        self.tick()
        with self.server.database() as db:
            ordinary=db.execute("SELECT count(*) FROM local_notification_outbox WHERE state='delivered'").fetchone()[0]
            reminders_count=db.execute('SELECT count(*) FROM followup_reminders').fetchone()[0]
            self.assertEqual(ordinary+reminders_count,100);self.assertEqual(reminders_count,40)


if __name__=='__main__':unittest.main()
