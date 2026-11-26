from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import notification_worker as worker
import test_local_notifications as fixture
import recovery


class NotificationWorkerTests(unittest.TestCase):
    login=fixture.LocalNotificationTests.login
    post=fixture.LocalNotificationTests.post
    create=fixture.LocalNotificationTests.create
    inbox=fixture.LocalNotificationTests.inbox
    subscribe=fixture.LocalNotificationTests.subscribe
    def setUp(self):fixture.LocalNotificationTests.setUp(self)

    def configure(self,**changes):
        previous=self.http.get('/api/local-notification-worker').json()
        body=dict(expected_revision=previous['revision'],enabled=True,interval_seconds=5,current_password=self.password,reason='Enable automatic local delivery for disposable test subscriptions.')
        body.update(changes)
        return self.post('/api/local-notification-worker',body)

    def tick(self,identity='first',epoch=1000):return worker.tick(self.server.database,self.server.record_audit,identity,epoch)

    def test_default_disabled_then_automatic_delivery_without_session(self):
        self.subscribe();self.create();self.assertEqual(self.tick(),'disabled');self.assertEqual(self.inbox()['total'],0)
        self.assertEqual(self.configure().status_code,200);self.http.cookies.clear()
        self.assertEqual(self.tick(),'completed');self.login('admin');self.assertEqual(self.inbox()['total'],1)

    def test_concurrent_workers_lease_and_manual_retry_do_not_duplicate(self):
        self.subscribe();self.create();self.configure()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda identity:self.tick(identity),['first','second']))
        self.assertEqual(sorted(results),['completed','lease-held']);self.assertEqual(self.inbox()['total'],1)
        self.assertEqual(self.post('/api/local-notifications/deliver',None).json()['delivered'],0)

    def test_interval_and_dead_owner_takeover(self):
        self.configure();self.assertEqual(self.tick(),'completed')
        self.assertEqual(self.tick(epoch=1001),'not-due');self.assertEqual(self.tick('second',1006),'lease-held')
        self.assertEqual(self.tick('second',1031),'completed')

    def test_pause_and_resume_retains_pending_until_new_pass(self):
        self.subscribe();self.configure();self.create();self.configure(enabled=False)
        self.assertEqual(self.tick(),'disabled');self.assertEqual(self.inbox()['own_outbox_counts'],{'pending':1})
        self.configure();self.tick();self.assertEqual(self.inbox()['total'],1)

    def test_recipient_disabled_or_changed_is_suppressed(self):
        self.login('operator');self.subscribe();self.create();self.login('admin');self.configure()
        with self.server.database() as db:db.execute("UPDATE users SET disabled=1 WHERE role='operator'")
        self.tick()
        with self.server.database() as db:self.assertEqual(db.execute('SELECT state FROM local_notification_outbox').fetchone()[0],'suppressed')

    def test_issuer_account_change_stops_automatic_authority(self):
        self.configure()
        with self.server.database() as db:
            uid=db.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
            db.execute("INSERT INTO account_controls VALUES(?,2,'changed')",(uid,))
        self.assertEqual(self.tick(),'disabled')
        self.assertEqual(self.http.get('/api/local-notification-worker').json()['state'],'authorization-changed')

    def test_password_role_csrf_revision_and_bounds(self):
        self.assertEqual(self.configure(current_password='wrong-password').status_code,403)
        self.assertEqual(self.configure(interval_seconds=4).status_code,422)
        self.assertEqual(self.configure().status_code,200)
        self.assertEqual(self.configure(expected_revision=0).status_code,409)
        self.assertEqual(self.post('/api/local-notification-worker',dict(expected_revision=1,enabled=False,interval_seconds=5,current_password=self.password,reason='Pause test notification delivery.'),False).status_code,403)
        self.login('operator');self.assertEqual(self.configure().status_code,403)
        self.http.cookies.clear();self.assertEqual(self.http.get('/api/local-notification-worker').status_code,401)

    def test_status_is_recent_stale_or_error_without_process_health_claim(self):
        self.configure();self.tick()
        with self.server.database() as db:
            self.assertEqual(worker.status(db,1001)['state'],'recent-pass')
            self.assertEqual(worker.status(db,1040)['state'],'pass-stale')
            db.execute("UPDATE local_notification_worker_status SET last_error='delivery-pass-failed'")
            self.assertEqual(worker.status(db,1040)['state'],'delivery-error')

    def test_failed_delivery_transaction_preserves_pending(self):
        self.subscribe();self.create();self.configure()
        with patch.object(worker.inbox,'deliver',side_effect=RuntimeError('private details must not escape')):
            with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.inbox()['own_outbox_counts'],{'pending':1});self.tick();self.assertEqual(self.inbox()['total'],1)

    def test_shutdown_releases_own_lease(self):
        self.configure();instance=worker.Worker(self.server.database,self.server.record_audit)
        self.tick(instance.id);instance.stop();self.assertEqual(self.tick('new-process',1001),'not-due')
        self.assertEqual(self.tick('new-process',1006),'completed')

    def test_supervisor_records_sanitized_first_pass_error(self):
        self.configure();instance=worker.Worker(self.server.database,self.server.record_audit)
        def finish(_):instance.stop_event.set()
        with patch.object(worker,'tick',side_effect=RuntimeError('private exception details')),patch.object(instance.stop_event,'wait',side_effect=finish):instance.run()
        report=self.http.get('/api/local-notification-worker').json()
        self.assertEqual(report['state'],'delivery-error');self.assertEqual(report['last_error'],'delivery-pass-failed')
        self.assertNotIn('private exception details',str(report))

    def test_restore_disables_worker_without_deleting_status(self):
        self.configure();self.tick();root=Path(self.temp.name)
        recovery.create_backup(self.server.DB_PATH,root/'backup');report=recovery.restore_backup(root/'backup',root/'restored')
        self.assertEqual(report['notification_worker_disabled'],1)
        with closing(sqlite3.connect(root/'restored/dashboard.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT enabled FROM local_notification_worker_config').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT lease_until FROM local_notification_worker_status').fetchone()[0],0)

    def test_batch_is_bounded_across_multiple_recipients(self):
        self.subscribe();self.login('auditor');self.subscribe();self.login('admin');self.configure()
        # 51 incidents route to two enabled recipients: 102 pending notifications.
        for _ in range(51):self.create()
        self.tick()
        with self.server.database() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM local_notification_outbox WHERE state='delivered'").fetchone()[0],100)
            self.assertEqual(db.execute("SELECT count(*) FROM local_notification_outbox WHERE state='pending'").fetchone()[0],2)
        self.tick(epoch=1006)
        with self.server.database() as db:self.assertEqual(db.execute("SELECT count(*) FROM local_notification_outbox WHERE state='pending'").fetchone()[0],0)


if __name__=='__main__':unittest.main()
