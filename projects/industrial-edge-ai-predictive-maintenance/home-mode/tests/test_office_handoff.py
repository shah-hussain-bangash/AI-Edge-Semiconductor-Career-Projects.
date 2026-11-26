"""Office export fixtures; no physical data or training is produced."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import csv,hashlib,io,json,tempfile,unittest,zipfile
from home_core import parse_line
from home_recording import Recorder
from office_handoff import package
from test_home import frame


class OfficeExportTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_sensor_csv_preserves_v1_ma_flags_raw_failures_and_unverified_labels(self):
        settings=dict(mode='sensors',port='COM3',expected_device_id='motor-001')
        recorder=Recorder(self.root,'a'*32,settings,10)
        raw=frame(ina219_valid=True);recorder.write(raw);recorder.classify('accepted',parse_line(raw,'sensors','motor-001'))
        recorder.write(b'bad\n');recorder.classify('rejected');recorder.finish('manual-stop')
        with zipfile.ZipFile(io.BytesIO(package(recorder.directory))) as archive:
            report=json.loads(archive.read('handoff.json'));rows=list(csv.DictReader(io.StringIO(archive.read('source.capture.csv').decode())))
            self.assertEqual(rows[0]['current_ma'],'25');self.assertEqual(rows[0]['ax_mps2'],'0');self.assertEqual(rows[0]['adxl345_valid'],'False')
            self.assertFalse(report['training_approved']);self.assertEqual(report['raw_frame_counts']['rejected'],1)
            for name,meta in report['files'].items():self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),meta['sha256'])
            with zipfile.ZipFile(io.BytesIO(archive.read('source-capture.zip'))) as raw_zip:self.assertTrue(raw_zip.read('wire.bin').endswith(b'bad\n'))
    def test_esp32_only_test_frames_cannot_be_exported_as_sensor_training_data(self):
        settings=dict(mode='esp32-only',port='COM3',expected_device_id='motor-001');recorder=Recorder(self.root,'b'*32,settings,10)
        recorder.write(b'ESP32 is working!\n');recorder.classify('accepted',parse_line(b'ESP32 is working!','esp32-only','motor-001'));recorder.finish('manual-stop')
        with self.assertRaises(ValueError):package(recorder.directory)
    def test_no_accepted_sensor_frames_cannot_make_a_dataset(self):
        settings=dict(mode='sensors',port='COM3',expected_device_id='motor-001');recorder=Recorder(self.root,'c'*32,settings,10)
        recorder.write(b'bad\n');recorder.classify('rejected');recorder.finish('manual-stop')
        with self.assertRaises(ValueError):package(recorder.directory)

if __name__=='__main__':unittest.main()
