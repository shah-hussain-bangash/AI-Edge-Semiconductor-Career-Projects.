import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import threading
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError

from baseline_review import review
from home_core import Controller, ROOT, Store, canonical, parse_line
from home_recording import Recorder
from home_server import HomeServer
from recording_library import baseline_report
from test_home import frame


class BaselineReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.clock = [0.0]
        self.settings = dict(mode='sensors', port='COM999', expected_device_id='motor-001')
        self.recorder = Recorder(self.directory/'captures', 'b'*32, self.settings, 600, monotonic=lambda:self.clock[0])

    def tearDown(self):
        if not self.recorder.finished:self.recorder.finish('manual-stop')
        self.temp.cleanup()

    def put(self, tick, sequence, **changes):
        self.clock[0] = tick
        fields=dict(seq=sequence, uptime_ms=int(tick*1000), adxl345_valid=True,
                    ds18b20_valid=True, ina219_valid=True, valid=True)
        fields.update(changes)
        data = frame(**fields)
        self.recorder.write(data)
        self.recorder.classify('accepted', parse_line(data,'sensors','motor-001'))

    def finish(self, seconds=600, reason='duration-elapsed'):
        self.clock[0] = seconds
        self.recorder.finish(reason)
        return review(self.recorder.directory)

    def test_600_good_fixture_records_still_cannot_pass_physical_or_ai_gates(self):
        for tick in range(600):self.put(tick,tick)
        result = self.finish()
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['window']['sensor_groups']['ina219']['declared_valid'],600)
        self.assertEqual(result['window']['interval_p95_seconds'],1)
        self.assertEqual(result['window']['observed_receipt_rate_hz'],1)
        self.assertEqual(result['outcome'],'review-required')
        self.assertEqual(result['physical_acceptance'],'pending')
        self.assertFalse(result['checks_are_acceptance'])
        self.assertFalse(result['equipment_authorized'])
        self.assertFalse(result['production_ready'])

    def test_counts_first_window_separately_from_late_read(self):
        self.put(1,0);self.put(599,1);self.put(600,2);self.put(600.2,3)
        result = self.finish(600.3)
        self.assertEqual(result['window']['frame_counts']['accepted'],2)
        self.assertEqual(result['observed']['total_frame_counts']['accepted'],4)
        self.assertEqual(result['window']['end_exclusive_seconds'],600)

    def test_gaps_duplicates_reset_and_long_interval(self):
        for tick,sequence in [(0,0),(1,3),(5,3),(6,1)]:self.put(tick,sequence)
        result = self.finish(10,'manual-stop')
        window=result['window']
        self.assertEqual((window['sequence_gaps'],window['duplicate_sequences'],window['sequence_or_uptime_resets']),(2,1,1))
        self.assertEqual(window['interval_max_seconds'],4)
        self.assertIn('full-600-second-window-not-recorded',result['issues'])
        self.assertIn('sequence-discontinuity-needs-review',result['issues'])

    def test_partial_sensor_flags_and_valid_zero_stay_distinct(self):
        self.put(1,0,ds18b20_valid=False,valid=False)
        result=self.finish(10,'manual-stop')
        groups=result['window']['sensor_groups']
        self.assertEqual(groups['adxl345']['declared_valid'],1)
        self.assertEqual(groups['ds18b20']['declared_valid'],0)
        self.assertEqual(groups['ina219']['declared_valid'],1)
        self.assertEqual(groups['ds18b20']['unavailable'],1)

    def test_rejected_partial_and_capacity_loss_preserved(self):
        self.clock[0]=1
        self.recorder.write(b'not-json\n');self.recorder.classify('rejected')
        self.recorder.write(b'partial')
        self.recorder.withheld=10
        result=self.finish(10,'byte-limit')
        self.assertEqual(result['window']['frame_counts']['rejected'],1)
        self.assertEqual(result['window']['frame_counts']['partial'],1)
        self.assertIn('raw-bytes-withheld-at-capacity-limit',result['issues'])
        self.assertIsNone(result['window']['interval_p95_seconds'])

    def test_communication_recording_has_no_valid_sensors_or_invented_sequences(self):
        self.recorder.finish('manual-stop')
        self.settings['mode']='esp32-only'
        self.recorder=Recorder(self.directory/'captures','c'*32,self.settings,10,monotonic=lambda:self.clock[0])
        self.recorder.write(b'ESP32 is working!\n')
        self.recorder.classify('accepted',parse_line(b'ESP32 is working!\n','esp32-only','motor-001'))
        result=self.finish(10)
        self.assertEqual(result['source'],'simulated')
        self.assertEqual(result['window']['sensor_groups']['adxl345']['declared_valid'],0)
        self.assertIn('communication-test-only-no-sensor-baseline',result['issues'])

    def test_tampered_raw_and_backwards_host_ticks_rejected(self):
        self.put(1,0);self.put(2,1);self.finish(10,'manual-stop')
        folder=self.recorder.directory
        index=folder/'frames.jsonl'
        events=[json.loads(line) for line in index.read_text(encoding='utf-8').splitlines()]
        events[1]['elapsed_seconds']=0.5
        index.write_text(''.join(canonical(event)+'\n' for event in events),encoding='utf-8')
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        raw=index.read_bytes();manifest['files']['frames.jsonl']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        (folder/'manifest.json').write_text(canonical(manifest),encoding='utf-8')
        with self.assertRaises(ValueError):review(folder)
        (folder/'wire.bin').write_bytes(b'tampered')
        with self.assertRaises(ValueError):review(folder)

    def test_active_and_folder_identity_mismatch_refused(self):
        identity=self.recorder.session_id
        with self.assertRaises(ValueError):baseline_report(self.directory,identity,identity)
        self.finish(10,'manual-stop')
        path=self.recorder.directory/'manifest.json'
        manifest=json.loads(path.read_text(encoding='utf-8'));manifest['session_id']='d'*32
        path.write_text(canonical(manifest),encoding='utf-8')
        with self.assertRaises(ValueError):review(self.recorder.directory)

    def test_read_only_http_report_and_cli_preserve_existing_outputs(self):
        self.put(1,0);self.finish(10,'manual-stop')
        controller=Controller(Store(self.directory/'history.sqlite3'),self.settings,self.directory)
        server=HomeServer(0,controller);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            route='/api/captures/'+self.recorder.session_id+'/review.json'
            with urlopen(base+route) as response:self.assertEqual(json.load(response)['physical_acceptance'],'pending')
            with self.assertRaises(HTTPError):urlopen(base+route+'?threshold=0')
            self.assertEqual(controller.status()['state'],'disconnected')
            output=self.directory/'review.json'
            command=[sys.executable,str(ROOT/'home-mode/home_recording.py'),'review',str(self.recorder.directory),'--output',str(output)]
            subprocess.run(command,check=True,capture_output=True)
            original=output.read_bytes()
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(output.read_bytes(),original)
            command[-1]=str(self.recorder.directory/'unexpected.json')
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertFalse((self.recorder.directory/'unexpected.json').exists())
        finally:
            server.shutdown();server.server_close();worker.join();controller.stop()
