"""Retry fixtures: explicit opt-in, no raw recording splices or disk-error loops."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile,time,unittest
from unittest.mock import patch
from home_core import Controller,Store
import test_home
from test_home import wait_for


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name);self.settings=dict(mode='esp32-only',port='COM3',expected_device_id='motor-001')
        self.fake=test_home.FakeSerial();self.calls=0
        def factory(*a,**kw):
            self.calls+=1
            if self.calls==1:raise OSError('fixture disconnected')
            return self.fake
        self.controller=Controller(Store(self.directory/'history.sqlite3'),self.settings,self.directory,serial_factory=factory,retry_base_seconds=.02)
    def tearDown(self):self.controller.stop();self.tmp.cleanup()
    def test_opt_in_retry_starts_new_attempt_and_never_fabricates_values(self):
        self.controller.start(self.settings,auto_reconnect=True);original=self.controller.session_id
        wait_for(lambda:self.calls==2)
        self.assertNotEqual(self.controller.session_id,original);self.assertFalse(self.controller.status()['fresh'])
        self.fake.items.put(b'ESP32 is working!\n');wait_for(lambda:self.controller.accepted==1)
        state=self.controller.status();self.assertTrue(state['fresh']);self.assertEqual(state['reconnect']['attempts'],1)
        self.assertTrue(all(v is None for v in state['live_values'].values()))
    def test_default_does_not_retry(self):
        self.controller.start(self.settings);wait_for(lambda:self.controller.status()['state']=='error')
        time.sleep(.08);self.assertEqual(self.calls,1)
    def test_manual_stop_cancels_backoff(self):
        self.controller.retry_base_seconds=.5;self.controller.start(self.settings,auto_reconnect=True)
        wait_for(lambda:self.controller.status()['state']=='retry-wait');self.controller.stop();time.sleep(.05)
        self.assertEqual(self.calls,1);self.assertEqual(self.controller.status()['state'],'disconnected')
    def test_storage_failure_is_not_retried_as_a_transport_problem(self):
        self.calls=1
        with patch.object(self.controller.store,'append',side_effect=OSError('fixture disk full')):
            self.controller.start(self.settings,auto_reconnect=True);self.fake.items.put(b'ESP32 is working!\n')
            wait_for(lambda:self.controller.status()['state']=='error');time.sleep(.08)
        self.assertEqual(self.calls,2);self.assertFalse(self.controller.status()['fresh'])
    def test_demo_recording_and_nonboolean_retry_options_refused(self):
        with self.assertRaises(ValueError):self.controller.start(self.settings,record_seconds=600,auto_reconnect=True)
        with self.assertRaises(ValueError):self.controller.start(dict(self.settings,mode='demo'),auto_reconnect=True)
        with self.assertRaises(ValueError):self.controller.start(self.settings,auto_reconnect=1)

if __name__=='__main__':unittest.main()
