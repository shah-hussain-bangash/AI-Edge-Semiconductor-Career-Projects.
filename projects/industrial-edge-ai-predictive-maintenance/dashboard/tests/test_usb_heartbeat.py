import sys
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from usb_heartbeat import UsbHeartbeat, valid_port


class UsbHeartbeatTests(unittest.TestCase):
    def test_only_local_usb_paths_allowed(self):
        for port in ('/dev/cu.usbserial-0001', '/dev/cu.usbmodem123', 'COM3', '/dev/ttyUSB0'):
            self.assertTrue(valid_port(port))
        for port in ('socket://example.com:23', '/tmp/file', '/dev/cu.Bluetooth-Incoming-Port', 'COM0'):
            with self.assertRaises(ValueError):
                UsbHeartbeat(port)

    def test_default_disabled_does_not_open_device(self):
        reader = UsbHeartbeat(factory=lambda **kw: self.fail('must not open'))
        reader.start()
        self.assertIsNone(reader.thread)
        self.assertEqual(reader.snapshot()['state'], 'disabled')

    def test_freshness_expiry_and_raw_data_not_exposed(self):
        clock = [100.0]
        reader = UsbHeartbeat('/dev/cu.usbserial-0001', clock=lambda: clock[0])
        reader.state = 'open'
        self.assertEqual(reader.snapshot()['state'], 'waiting')
        self.assertFalse(reader.observe(b'private unexpected serial content\n'))
        self.assertFalse(reader.observe(b'x' * 300))
        reader.observe(b'ESP32 is working!\r\n')
        self.assertTrue(reader.snapshot()['heartbeat_fresh'])
        self.assertFalse(reader.snapshot()['sensor_telemetry_verified'])
        self.assertNotIn('private', str(reader.snapshot()))
        clock[0] = 105.0
        self.assertEqual(reader.snapshot()['state'], 'stale')
        self.assertIsNone(reader.snapshot()['message'])

    def test_reader_fragments_limits_and_closes_without_writes(self):
        reader = None
        class Device:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.chunks = iter([b'ESP32 is ', b'working!\n', b'x' * 257, b'ESP32 is working!\n', b'ESP32 is working!\n'])
                self.closed = False
            def open(self):
                self_test.assertFalse(self.dtr)
                self_test.assertFalse(self.rts)
            def read_until(self, delimiter, size):
                try:
                    return next(self.chunks)
                except StopIteration:
                    reader.stop_event.set()
                    return b''
            def close(self):
                self.closed = True
        self_test = self
        devices = []
        def factory(**kwargs):
            devices.append(Device(**kwargs))
            return devices[-1]
        reader = UsbHeartbeat('/dev/cu.usbserial-0001', factory=factory)
        reader.start()
        reader.thread.join(timeout=2)
        self.assertFalse(reader.thread.is_alive())
        self.assertEqual(reader.snapshot()['heartbeat_count'], 2)
        self.assertEqual(reader.snapshot()['ignored_line_count'], 1)
        self.assertTrue(devices[0].closed)
        self.assertTrue(devices[0].kwargs['exclusive'])
        self.assertFalse(reader.snapshot()['heartbeat_fresh'])

    def test_disconnect_clears_fresh_status_and_can_stop_retry(self):
        def unavailable(**kwargs):
            raise OSError('private OS details')
        reader = UsbHeartbeat('/dev/cu.usbserial-0001', factory=unavailable)
        reader.observe(b'ESP32 is working!\n')
        reader.start()
        deadline = time.monotonic() + 1
        while reader.snapshot()['state'] != 'disconnected' and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertEqual(reader.snapshot()['state'], 'disconnected')
        self.assertIsNone(reader.snapshot()['last_received_utc'])
        self.assertNotIn('private OS', str(reader.snapshot()))
        reader.stop()
        self.assertFalse(reader.thread.is_alive())

    def test_authenticated_status_and_revocation(self):
        import server
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as folder:
            email, password = 'usb-test@example.invalid', secrets.token_urlsafe(24)
            with patch.multiple(server, DB_PATH=Path(folder) / 'test.sqlite3',
                                BOOTSTRAP_EMAIL=email, BOOTSTRAP_PASSWORD=password,
                                usb_reader=UsbHeartbeat()):
                with TestClient(server.app) as http:
                    self.assertEqual(http.get('/api/usb/status').status_code, 401)
                    response = http.post('/api/auth/login', json={'email': email, 'password': password})
                    self.assertEqual(response.status_code, 200)
                    response = http.get('/api/usb/status')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()['state'], 'disabled')
                    self.assertEqual(response.headers['cache-control'], 'no-store')
                    self.assertEqual(http.get('/static/usb_heartbeat.py').status_code, 404)
                    csrf = http.cookies.get('edgeops_csrf')
                    self.assertEqual(http.post('/api/auth/logout', headers={'x-edgeops-csrf': csrf}).status_code, 200)
                    self.assertEqual(http.get('/api/usb/status').status_code, 401)



if __name__ == '__main__':
    unittest.main()
