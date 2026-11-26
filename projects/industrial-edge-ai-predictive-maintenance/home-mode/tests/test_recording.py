"""Raw capture fixtures. No actual board or 600-second physical test."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hashlib,io,json,os,subprocess,tempfile,unittest,zipfile
from unittest.mock import patch
from urllib.error import HTTPError
import test_home
from test_home import wait_for
from home_core import Controller,Store,canonical
from home_recording import Recorder,CaptureLimit,package,verify


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
        self.clock=[0.];self.settings=dict(mode='esp32-only',port='COM3' if os.name=='nt' else '/dev/cu.fixture',expected_device_id='motor-001')
        self.fake=test_home.FakeSerial();self.controller=Controller(Store(self.directory/'history.sqlite3'),self.settings,self.directory,serial_factory=lambda *a,**k:self.fake,monotonic=lambda:self.clock[0])
    def tearDown(self):self.controller.stop();self.tmp.cleanup()
    def test_fragmented_raw_bytes_invalid_utf8_diagnostics_and_partial_preserved(self):
        self.controller.start(self.settings,record_seconds=600)
        pieces=[b'# boot\n',b'ESP32 is ',b'working!\n',b'\xff\n',b'partial']
        for piece in pieces:self.fake.items.put(piece)
        wait_for(lambda:self.controller.recording and self.controller.recording.total==len(b''.join(pieces)))
        self.controller.stop()
        recording=self.controller.recording;manifest,files=verify(recording.directory)
        self.assertEqual(files['wire.bin'],b''.join(pieces));self.assertEqual(manifest['frame_counts'],dict(accepted=1,rejected=1,diagnostic=1,partial=1))
        self.assertEqual(manifest['stop_reason'],'manual-stop');self.assertFalse(manifest['deadline_reached'])
        self.assertEqual(manifest['source'],'simulated');self.assertEqual(manifest['physical_acceptance'],'pending')
        self.assertFalse(manifest['production_ready'])
    def test_600_second_deadline_uses_injected_clock_not_waiting_or_physical_measurement(self):
        self.controller.start(self.settings,record_seconds=600);self.fake.items.put(b'ESP32 is working!\n')
        wait_for(lambda:self.controller.accepted==1)
        self.clock[0]=601.
        wait_for(lambda:self.controller.status()['state']=='disconnected')
        manifest,_=verify(self.controller.recording.directory)
        self.assertEqual(manifest['stop_reason'],'duration-elapsed');self.assertTrue(manifest['deadline_reached'])
        self.assertFalse(self.controller.status()['fresh']);self.assertEqual(manifest['physical_acceptance'],'pending')
    def test_unplug_finalizes_failure_and_keeps_partial(self):
        self.controller.start(self.settings,record_seconds=600)
        self.fake.items.put(b'ESP32 is working!\n');self.fake.items.put(b'tail');self.fake.items.put(OSError('fixture unplug'))
        wait_for(lambda:self.controller.recording and self.controller.recording.finished)
        manifest,files=verify(self.controller.recording.directory)
        self.assertEqual(manifest['stop_reason'],'serial-or-storage-error');self.assertEqual(manifest['frame_counts']['partial'],1)
        self.assertTrue(files['wire.bin'].endswith(b'tail'));self.assertFalse(self.controller.status()['fresh'])
    def test_sensor_json_raw_and_normalized_quality_survive_replay(self):
        self.controller.start(dict(self.settings,mode='sensors'),record_seconds=600)
        raw=test_home.frame(adxl345_valid=True,ina219_valid=True)
        self.fake.items.put(raw);wait_for(lambda:self.controller.accepted==1);self.controller.stop()
        manifest,files=verify(self.controller.recording.directory)
        event=json.loads(files['frames.jsonl'])
        self.assertEqual(files['wire.bin'],raw);self.assertEqual(manifest['source'],'serial-unverified')
        self.assertEqual(event['sample']['values']['acceleration_x_mps2'],0)
        self.assertEqual(event['sample']['values']['current_a'],.025)
        self.assertIsNone(event['sample']['values']['temperature_c'])
    def test_oversized_frame_is_preserved_and_next_frame_resynchronizes(self):
        self.controller.start(self.settings,record_seconds=600)
        pieces=[b'x'*4097,b'\n',b'ESP32 is working!\n']
        for piece in pieces:self.fake.items.put(piece)
        wait_for(lambda:self.controller.accepted==1);self.controller.stop()
        manifest,files=verify(self.controller.recording.directory)
        self.assertEqual(files['wire.bin'],b''.join(pieces));self.assertEqual(manifest['frame_counts']['rejected'],1)
        self.assertEqual(manifest['frame_counts']['accepted'],1)
    def test_modes_durations_and_reused_folders_refused(self):
        for seconds in [True,0,9,601,10.5]:
            with self.assertRaises(ValueError):self.controller.start(self.settings,record_seconds=seconds)
        with self.assertRaises(ValueError):self.controller.start(dict(self.settings,mode='demo'),record_seconds=600)
        recording=Recorder(self.directory,'a'*32,self.settings,10)
        try:
            with self.assertRaises(FileExistsError):Recorder(self.directory,'a'*32,self.settings,10)
        finally:recording.finish('manual-stop')
    def test_byte_and_chunk_limits_are_reported_with_withheld_bytes(self):
        for suffix,kw,reason in [('b',dict(max_bytes=4),'byte-limit'),('c',dict(max_chunks=1),'chunk-limit')]:
            recording=Recorder(self.directory,suffix*32,self.settings,10,**kw)
            recording.write(b'#x\n');recording.classify('diagnostic')
            with self.assertRaises(CaptureLimit) as error:recording.write(b'#y\n')
            self.assertEqual(str(error.exception),reason);recording.finish(reason)
            manifest,_=verify(recording.directory)
            self.assertEqual(manifest['raw_bytes'],3);self.assertEqual(manifest['withheld_read_bytes'],3)
            self.assertEqual(manifest['physical_acceptance'],'pending')
    def test_storage_failure_never_creates_final_manifest_or_download(self):
        recording=Recorder(self.directory,'d'*32,self.settings,10);recording.write(b'partial')
        with patch('home_recording.os.fsync',side_effect=OSError('fixture disk failure')):
            with self.assertRaises(OSError):recording.finish('serial-or-storage-error')
        self.assertFalse(recording.finished);self.assertFalse(recording.status()['active'])
        with self.assertRaises(ValueError):package(recording.directory)
    def test_verifier_recomputes_parser_not_only_hashes_and_pack_refuses_overwrite(self):
        recording=Recorder(self.directory,'e'*32,self.settings,10);recording.write(b'#diag\n');recording.classify('diagnostic');recording.finish('manual-stop')
        with zipfile.ZipFile(io.BytesIO(package(recording.directory))) as archive:self.assertEqual(set(archive.namelist()),{'wire.bin','frames.jsonl','manifest.json'})
        output=self.directory/'existing.zip';output.write_bytes(b'preserve')
        result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'home_recording.py'),'pack',str(recording.directory),'--output',str(output)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(output.read_bytes(),b'preserve')
        index=recording.directory/'frames.jsonl';event=json.loads(index.read_text(encoding='utf-8'));event['kind']='accepted'
        raw=(canonical(event)+'\n').encode();index.write_bytes(raw)
        manifest=json.loads((recording.directory/'manifest.json').read_text(encoding='utf-8'))
        manifest['files']['frames.jsonl']=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        manifest['frame_counts']=dict(accepted=1,rejected=0,diagnostic=0,partial=0)
        (recording.directory/'manifest.json').write_text(canonical(manifest),encoding='utf-8')
        with self.assertRaises(ValueError):verify(recording.directory)


class RecordingHttpTests(test_home.HttpTests):
    def test_recording_requires_origin_token_usb_mode_and_strict_shape(self):
        for body in [dict(settings=dict(self.settings,mode='demo'),seconds=600),dict(settings=self.settings,seconds=True),dict(settings=self.settings,seconds=600,extra='no')]:
            with self.assertRaises(HTTPError) as error:self.request('/api/record',body)
            self.assertEqual(error.exception.code,422)
        with self.assertRaises(HTTPError) as error:self.request('/api/record',dict(settings=self.settings,seconds=600),headers={'Origin':'https://other.invalid'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:self.request('/api/capture.zip')
        self.assertEqual(error.exception.code,422)
    @unittest.skipIf(os.name=='nt','POSIX pseudo-terminal fixture, not physical ESP32 hardware')
    def test_pyserial_pty_recording_preserves_exact_bytes_over_http(self):
        import pty
        master,slave=pty.openpty()
        try:
            self.controller.serial_factory=None
            settings=dict(self.settings,port=os.ttyname(slave))
            with self.request('/api/record',dict(settings=settings,seconds=600)):pass
            wait_for(lambda:self.controller.recording is not None)
            raw=b'ESP32 is working!\n'
            os.write(master,raw)
            wait_for(lambda:self.controller.accepted==1)
            with self.request('/api/disconnect',{}):pass
            with self.request('/api/capture.zip') as response:
                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                    self.assertEqual(archive.read('wire.bin'),raw)
                    manifest=json.loads(archive.read('manifest.json'))
                    self.assertFalse(manifest['hardware_verified']);self.assertEqual(manifest['physical_acceptance'],'pending')
        finally:self.controller.stop();os.close(master);os.close(slave)
    def test_fake_serial_http_record_stop_and_raw_download(self):
        with self.request('/api/record',dict(settings=self.settings,seconds=600)):pass
        self.fake.items.put(b'ESP32 is working!\n')
        wait_for(lambda:self.controller.accepted==1)
        with self.assertRaises(HTTPError):self.request('/api/capture.zip')
        with self.request('/api/disconnect',{}):pass
        with self.request('/api/capture.zip') as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertEqual(archive.read('wire.bin'),b'ESP32 is working!\n')
                self.assertEqual(json.loads(archive.read('manifest.json'))['physical_acceptance'],'pending')

for name in dir(test_home.HttpTests):
    if name.startswith('test_') and name not in RecordingHttpTests.__dict__:setattr(RecordingHttpTests,name,None)
if __name__=='__main__':unittest.main()
