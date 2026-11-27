"""Application resource ownership on startup, failed startup and shutdown."""
import importlib
import os
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
import warnings
from unittest.mock import patch
from fastapi.testclient import TestClient


class ApplicationLifespanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='edgeops-lifespan-');self.addCleanup(self.temp.cleanup)
        self.database=Path(self.temp.name)/'fixture.sqlite3'
        environment=patch.dict(os.environ,{'EDGEOPS_DASHBOARD_DB':str(self.database),'EDGEOPS_ADMIN_EMAIL':'fixture@example.invalid','EDGEOPS_ADMIN_PASSWORD':secrets.token_urlsafe(24)})
        environment.start();self.addCleanup(environment.stop)
        import server
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always',DeprecationWarning)
            self.server=importlib.reload(server)
        self.import_warnings=observed

    def test_import_has_no_event_deprecation_or_running_worker(self):
        self.assertFalse(self.database.exists())
        self.assertIsNone(self.server.notification_delivery_worker.thread)
        self.assertFalse([str(item.message) for item in self.import_warnings if 'on_event' in str(item.message)])

    def test_normal_and_repeated_lifespans_stop_the_actual_worker(self):
        worker=self.server.notification_delivery_worker
        for _ in range(2):
            with TestClient(self.server.app) as client:
                self.assertTrue(worker.thread.is_alive());self.assertEqual(client.get('/health/ready').status_code,200)
            self.assertTrue(worker.stop_event.is_set());self.assertFalse(worker.thread.is_alive())

    def test_failed_database_initialization_never_starts_worker(self):
        worker=self.server.notification_delivery_worker
        with patch.object(self.server,'init_db',side_effect=RuntimeError('Fixture schema unavailable')),patch.object(worker,'start') as start,patch.object(worker,'stop') as stop:
            with self.assertRaisesRegex(RuntimeError,'Fixture schema unavailable'):
                with TestClient(self.server.app):pass
            start.assert_not_called();stop.assert_not_called()
        self.assertFalse(self.database.exists())

    def test_partially_started_worker_is_cleaned_up_when_startup_raises(self):
        class PartialWorker:
            def __init__(self):self.event=threading.Event();self.thread=None
            def start(self):
                self.thread=threading.Thread(target=self.event.wait,daemon=True);self.thread.start()
                raise RuntimeError('Fixture partial worker startup')
            def stop(self):
                self.event.set()
                if self.thread:self.thread.join(timeout=2)
        partial=PartialWorker();self.addCleanup(partial.stop)
        with patch.object(self.server,'notification_delivery_worker',partial):
            with self.assertRaisesRegex(RuntimeError,'Fixture partial worker startup'):
                with TestClient(self.server.app):pass
        self.assertIsNotNone(partial.thread);self.assertFalse(partial.thread.is_alive())

    def test_worker_stops_when_the_application_context_exits_with_an_error(self):
        worker=self.server.notification_delivery_worker
        with self.assertRaisesRegex(RuntimeError,'Fixture context failure'):
            with TestClient(self.server.app):
                self.assertTrue(worker.thread.is_alive())
                raise RuntimeError('Fixture context failure')
        self.assertFalse(worker.thread.is_alive());self.assertTrue(worker.stop_event.is_set())
