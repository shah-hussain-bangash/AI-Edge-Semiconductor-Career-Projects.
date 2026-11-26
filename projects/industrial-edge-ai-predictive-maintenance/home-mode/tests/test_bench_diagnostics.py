import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError

import bench_diagnostics
from home_core import Controller, Store
from home_server import HomeServer
from test_home import FakeSerial, frame, wait_for


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.clock = [10.0]
        self.serial = FakeSerial()
        self.settings = dict(mode='esp32-only', port='COM999', expected_device_id='motor-001')
        self.controller = Controller(Store(self.directory/'history.sqlite3'), self.settings,
                                     self.directory, serial_factory=lambda *a, **k: self.serial,
                                     monotonic=lambda: self.clock[0])

    def tearDown(self):
        self.controller.stop()
        self.temp.cleanup()

    def test_text_demo_stale_and_partial_sensor_states_never_certify_hardware(self):
        self.controller.start(self.settings)
        self.serial.items.put(b'ESP32 is working!\n')
        wait_for(lambda: self.controller.status()['accepted'] == 1)
        report = bench_diagnostics.report(self.controller)
        self.assertEqual(report['reader']['communication'], 'fresh-parser-accepted-input')
        self.assertEqual(set(report['reader']['sensor_groups'].values()), {'unavailable'})
        self.clock[0] = 16
        self.assertEqual(bench_diagnostics.report(self.controller)['reader']['communication'], 'not-demonstrated')
        self.controller.start(dict(self.settings, mode='demo'))
        wait_for(lambda: self.controller.status()['fresh'])
        self.assertEqual(bench_diagnostics.report(self.controller)['reader']['communication'], 'not-demonstrated')
        self.controller.stop()
        self.serial = FakeSerial()
        self.controller.start(dict(self.settings, mode='sensors'))
        self.serial.items.put(frame(adxl345_valid=True))
        wait_for(lambda: self.controller.status()['accepted'] == 1)
        report = bench_diagnostics.report(self.controller)
        self.assertEqual(report['reader']['sensor_groups'], {'ADXL345':'declared-valid-unverified', 'DS18B20':'unavailable', 'INA219':'unavailable'})
        self.assertFalse(report['hardware_verified'])
        self.assertFalse(report['production_ready'])

    def test_missing_dependency_disk_and_no_secrets_or_enumeration(self):
        with patch.object(bench_diagnostics, 'version', side_effect=bench_diagnostics.PackageNotFoundError), patch.object(bench_diagnostics.shutil, 'disk_usage', side_effect=OSError):
            report = bench_diagnostics.report(self.controller)
        self.assertFalse(report['host']['dependency_matches'])
        self.assertIsNone(report['host']['free_bytes'])
        self.assertEqual(report['host']['recording_space_advisory'], 'unknown')
        text = json.dumps(report)
        for private in ('write_token', 'instance_id', str(self.directory), 'payload_json', 'error'):
            self.assertNotIn(private, text)
        self.assertEqual(self.controller.status()['state'], 'disconnected')

    def test_http_report_and_fixed_guide_allowlist(self):
        server = HomeServer(0, self.controller)
        worker = threading.Thread(target=server.serve_forever, daemon=True);worker.start()
        base = 'http://127.0.0.1:'+str(server.server_port)
        try:
            with urlopen(base+'/api/diagnostics') as response:
                data = json.load(response)
                self.assertEqual(data['reader']['state'], 'disconnected')
            for route in ('mac', 'windows', 'wiring', 'recovery'):
                with urlopen(base+'/guide/'+route) as response:
                    self.assertEqual(response.headers.get_content_type(), 'text/plain')
                    self.assertGreater(len(response.read()), 100)
            for route in ('/guide/../.local/home/config.json', '/guide/mac?path=.local', '/api/diagnostics?token=x'):
                with self.assertRaises(HTTPError):urlopen(base+route)
        finally:
            server.shutdown();server.server_close();worker.join()
