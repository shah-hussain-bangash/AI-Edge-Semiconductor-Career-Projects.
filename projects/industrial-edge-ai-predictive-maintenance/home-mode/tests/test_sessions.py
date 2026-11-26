"""Software-only session packaging and launcher boundaries."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contextlib import closing
import csv, hashlib, io, json, os, sqlite3, subprocess, tempfile, unittest, zipfile
from urllib.error import HTTPError
from home_core import Controller, ROOT, Store, canonical, parse_line
from session_export import build_package, summarize
import test_home
from test_home import frame, wait_for


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
        self.store=Store(self.directory/'history.sqlite3',limit=1000)
        self.controller=Controller(self.store,dict(mode='esp32-only',port='COM3',expected_device_id='motor-001'),self.directory)
        self.controller.session_id='a'*32
    def tearDown(self):self.controller.stop();self.tmp.cleanup()
    def accept(self, raw=None, mode='esp32-only'):
        sample=parse_line(raw or b'ESP32 is working!','esp32-only' if mode=='esp32-only' else 'sensors','motor-001')
        self.controller.settings['mode']=mode
        self.controller._accept(sample,0,self.controller.stop_event,self.controller.session_id)
    def test_full_650_record_package_is_not_last_60_or_hardware_acceptance(self):
        self.accept()
        # Seed a large retained fixture in one transaction; this tests export
        # bounds rather than timing hundreds of synchronous disk commits.
        with closing(self.store.connect()) as db,db:
            db.executemany('INSERT INTO home_samples(session_id,received_at,source,payload_json,content_hash) SELECT session_id,received_at,source,payload_json,content_hash FROM home_samples WHERE id=1', [()] * 649)
        self.controller.accepted=650
        snapshot=self.controller.session_snapshot();payload=build_package(snapshot)
        with zipfile.ZipFile(io.BytesIO(payload)) as package:
            manifest=json.loads(package.read('manifest.json'))
            rows=package.read('samples.jsonl').splitlines()
            self.assertEqual(len(rows),650);self.assertEqual(manifest['accepted_at_snapshot'],650)
            self.assertTrue(manifest['all_accepted_records_retained'])
            self.assertEqual(manifest['source_counts'],{'simulated':650})
            self.assertEqual(manifest['physical_acceptance'],'pending');self.assertFalse(manifest['production_ready'])
            self.assertFalse(manifest['raw_serial_capture_included']);self.assertFalse(manifest['receipt_span_is_run_duration'])
            for name,meta in manifest['files'].items():
                raw=package.read(name);self.assertEqual(len(raw),meta['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),meta['sha256'])
            self.assertTrue(all(v==0 for v in manifest['available_value_counts'].values()))
    def test_retention_loss_is_explicit_and_old_sessions_excluded(self):
        self.store.limit=2
        other=parse_line(b'ESP32 is working!','esp32-only','motor-001')
        self.store.append(dict(other,session_id='b'*32,received_at='2026-11-26T00:00:00+00:00',production_ready=False,hardware_verified=False,calibration_verified=False,equipment_authorized=False))
        for _ in range(5):self.accept()
        summary=summarize(self.controller.session_snapshot())
        self.assertFalse(summary['all_accepted_records_retained']);self.assertEqual(summary['missing_accepted_records'],3)
        self.assertEqual(summary['retained_records'],2);self.assertEqual(summary['physical_acceptance'],'pending')
    def test_sensor_csv_preserves_zero_null_amps_quality_and_unverified_source(self):
        self.accept(frame(adxl345_valid=True,ina219_valid=True),mode='sensors')
        with zipfile.ZipFile(io.BytesIO(build_package(self.controller.session_snapshot()))) as package:
            rows=list(csv.DictReader(io.StringIO(package.read('samples.csv').decode('utf-8'))))
        self.assertEqual(rows[0]['source'],'serial-unverified');self.assertEqual(rows[0]['acceleration_x_mps2'],'0')
        self.assertEqual(rows[0]['temperature_c'],'');self.assertEqual(rows[0]['current_a'],'0.025')
        self.assertEqual(rows[0]['temperature_c_quality'],'unavailable');self.assertEqual(rows[0]['hardware_verified'],'False')
    def test_sequence_summary_reports_gaps_duplicates_and_reset_without_pass(self):
        for seq,uptime in [(1,1000),(3,3000),(3,3000),(0,0)]:self.accept(frame(seq=seq,uptime_ms=uptime))
        summary=summarize(self.controller.session_snapshot())
        self.assertEqual(summary['device_sequence_gaps'],1);self.assertEqual(summary['device_duplicate_sequences'],1)
        self.assertEqual(summary['device_sequence_or_uptime_resets'],1);self.assertEqual(summary['physical_acceptance'],'pending')
    def test_stopped_session_remains_exportable_and_new_process_cannot_invent_session(self):
        self.accept();self.controller.stop()
        self.assertEqual(summarize(self.controller.session_snapshot())['reader_state_at_snapshot'],'disconnected')
        fresh=Controller(self.store,self.controller.settings,self.directory)
        with self.assertRaises(ValueError):fresh.session_snapshot()
    def test_corrupted_or_relabelled_rows_refused(self):
        self.accept()
        with closing(sqlite3.connect(self.store.path)) as db,db:db.execute("UPDATE home_samples SET source='verified-hardware'")
        with self.assertRaises(ValueError):self.controller.session_snapshot()
        with closing(sqlite3.connect(self.store.path)) as db,db:db.execute("UPDATE home_samples SET source='simulated',payload_json='{}'")
        with self.assertRaises(ValueError):self.controller.session_snapshot()
    @unittest.skipIf(os.name=='nt','POSIX shell guard; Windows has its own native launcher')
    def test_mac_launchers_refuse_other_hosts_before_touching_environment(self):
        fake=self.directory/'uname';fake.write_text('#!/bin/sh\necho Linux\n',encoding='utf-8');fake.chmod(0o700)
        env=dict(os.environ,PATH=str(self.directory)+os.pathsep+os.environ['PATH'])
        for name in ['home_setup.command','home_start.command','home_update.command','home_data.command','home_service.command']:
            result=subprocess.run(['bash',str(ROOT/name)],capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,1);self.assertIn('macOS Terminal',result.stdout);self.assertIn('home.ps1',result.stdout)


class SessionHttpTests(test_home.HttpTests):
    def test_session_package_lifecycle_and_query_boundaries(self):
        with self.assertRaises(HTTPError) as error:self.request('/api/session.zip')
        self.assertEqual(error.exception.code,422)
        with self.request('/api/connect',dict(self.settings,mode='demo')):pass
        wait_for(lambda:self.controller.status()['accepted']>0)
        with self.request('/api/disconnect',{}):pass
        with self.request('/api/session') as response:summary=json.load(response)
        self.assertTrue(summary['all_accepted_records_retained']);self.assertEqual(summary['physical_acceptance'],'pending')
        with self.request('/api/session.zip') as response:
            self.assertEqual(response.headers['Content-Type'],'application/zip')
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertEqual(json.loads(archive.read('manifest.json'))['session_id'],summary['session_id'])
        with self.assertRaises(HTTPError) as error:self.request('/api/session?session_id=other')
        self.assertEqual(error.exception.code,422)

# The base HTTP suite is discovered in test_home; keep only the new HTTP case.
for name in dir(test_home.HttpTests):
    if name.startswith('test_') and name not in SessionHttpTests.__dict__:setattr(SessionHttpTests,name,None)
if __name__=='__main__':unittest.main()
