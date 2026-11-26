"""Private-data recovery and historical recording fixtures, no real hardware."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contextlib import closing
import io,json,os,sqlite3,tempfile,unittest,zipfile
from unittest.mock import patch
from urllib.error import HTTPError
from home_core import Controller,Store,ProcessLock,parse_line,save_settings
from home_recording import Recorder
import home_backup as backup
import recording_library as library
import test_home


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.data=self.root/'home';self.data.mkdir()
        self.settings=dict(mode='esp32-only',port='COM3',expected_device_id='motor-001')
        save_settings(self.data,self.settings)
        self.store=Store(self.data/'history.sqlite3')
        controller=Controller(self.store,self.settings,self.data)
        controller._accept(parse_line(b'ESP32 is working!','esp32-only','motor-001'),0,controller.stop_event,'a'*32)
    def tearDown(self):self.tmp.cleanup()
    def recording(self,identity='b'*32,finish=True):
        recorder=Recorder(self.data/'captures',identity,self.settings,10)
        recorder.write(b'ESP32 is working!\n');recorder.classify('accepted',parse_line(b'ESP32 is working!','esp32-only','motor-001'))
        if finish:recorder.finish('manual-stop')
        return recorder
    def test_backup_restore_preserves_history_config_and_raw_files(self):
        recording=self.recording();(self.data/'notes.txt').write_text('private',encoding='utf-8')
        result=backup.create(self.data,self.root/'backup');self.assertEqual(result['rows'],1)
        destination=self.root/'restored';restored=backup.restore(self.root/'backup',destination)
        self.assertEqual(restored['rows'],1);self.assertEqual((destination/'notes.txt').read_text(encoding='utf-8'),'private')
        self.assertEqual(Store(destination/'history.sqlite3').history()['total'],1)
        self.assertEqual((destination/'captures'/recording.session_id/'wire.bin').read_bytes(),b'ESP32 is working!\n')
        self.assertFalse((destination/'server.lock').exists());self.assertFalse((destination/'RESTORE_INCOMPLETE').exists())
        self.assertFalse(restored['production_ready'])
    def test_active_server_lock_and_existing_destinations_preserved(self):
        with ProcessLock(self.data/'server.lock'):
            with self.assertRaises(ValueError):backup.create(self.data,self.root/'backup')
        self.assertFalse((self.root/'backup').exists())
        backup.create(self.data,self.root/'backup')
        with self.assertRaises(ValueError):backup.create(self.data,self.root/'backup')
        with self.assertRaises(ValueError):backup.restore(self.root/'backup',self.data)
        self.assertEqual(self.store.history()['total'],1)
    def test_recursive_backup_and_checksum_tampering_refused(self):
        with self.assertRaises(ValueError):backup.create(self.data,self.data/'recursive')
        backup.create(self.data,self.root/'backup')
        (self.root/'backup/data/config.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):backup.restore(self.root/'backup',self.root/'restored')
        self.assertFalse((self.root/'restored').exists())
    def test_manifest_traversal_inventory_and_bad_database_refused(self):
        backup.create(self.data,self.root/'backup')
        path=self.root/'backup/backup-manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'))
        manifest['files']['../outside']=manifest['files']['config.json'];path.write_text(json.dumps(manifest),encoding='utf-8')
        with self.assertRaises(ValueError):backup.verify(self.root/'backup')
        with closing(sqlite3.connect(self.store.path)) as db,db:db.execute("UPDATE home_samples SET payload_json='{}'")
        with self.assertRaises(ValueError):backup.create(self.data,self.root/'bad-backup')
        self.assertFalse((self.root/'bad-backup').exists())
    def test_copy_failure_leaves_new_restore_blocked_without_touching_original(self):
        backup.create(self.data,self.root/'backup')
        with patch('home_backup.copy_private',side_effect=OSError('fixture full disk')):
            with self.assertRaises(OSError):backup.restore(self.root/'backup',self.root/'failed-restore')
        self.assertTrue((self.root/'failed-restore/RESTORE_INCOMPLETE').exists())
        self.assertEqual(self.store.history()['total'],1)
    def test_incomplete_recording_preserved_but_not_listed_as_downloadable(self):
        recorder=self.recording(finish=False)
        # Simulate a crash: close file handles without inventing a final manifest.
        for stream in recorder.files.values():stream.close()
        backup.create(self.data,self.root/'backup');backup.restore(self.root/'backup',self.root/'restored')
        items=library.listing(self.root/'restored')['items'];self.assertEqual(items[0]['state'],'incomplete');self.assertFalse(items[0]['downloadable'])
        with self.assertRaises(ValueError):library.download(self.root/'restored',recorder.session_id)
    def test_historical_library_after_restart_and_invalid_id(self):
        recorder=self.recording();page=library.listing(self.data)
        self.assertEqual(page['total'],1);self.assertTrue(page['items'][0]['downloadable'])
        with zipfile.ZipFile(io.BytesIO(library.download(self.data,recorder.session_id))) as archive:self.assertEqual(archive.read('wire.bin'),b'ESP32 is working!\n')
        for value in ['../home','b'*31,'/etc/passwd']:
            with self.assertRaises(ValueError):library.download(self.data,value)
        with self.assertRaises(ValueError):library.download(self.data,recorder.session_id,active_id=recorder.session_id)
    def test_invalid_manifest_and_raw_tamper_never_download_as_verified(self):
        recorder=self.recording();(recorder.directory/'wire.bin').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):library.download(self.data,recorder.session_id)
        (recorder.directory/'manifest.json').write_text('{}',encoding='utf-8')
        self.assertEqual(library.listing(self.data)['items'][0]['state'],'invalid')
    def test_incomplete_restore_cannot_launch_a_server(self):
        import socket,subprocess
        target=self.root/'incomplete';target.mkdir();(target/'RESTORE_INCOMPLETE').write_bytes(b'')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        executable=getattr(sys,'_base_executable',sys.executable) if os.name=='nt' else sys.executable
        script=Path(__file__).resolve().parents[1]/'home_server.py'
        result=subprocess.run([executable,str(script),'--data-dir',str(target),'--web-port',str(port)],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertIn('incomplete restore',result.stderr)
        self.assertFalse((target/'history.sqlite3').exists())
    @unittest.skipIf(os.name=='nt','POSIX symlink fixture; Windows privilege is not assumed')
    def test_linked_source_is_refused_before_copying_outside_data(self):
        outside=self.root/'private.txt';outside.write_text('preserve',encoding='utf-8')
        (self.data/'linked').symlink_to(outside)
        with self.assertRaises(ValueError):backup.create(self.data,self.root/'linked-backup')
        self.assertFalse((self.root/'linked-backup').exists());self.assertEqual(outside.read_text(encoding='utf-8'),'preserve')
    def test_page_and_path_bounds(self):
        for value in ['../escape','C:/path','a\\b','NUL','dir/../file','file.']:
            with self.assertRaises(ValueError):backup.relative_name(value)
        with self.assertRaises(ValueError):library.listing(self.data,limit=101)
        with self.assertRaises(ValueError):library.listing(self.data,offset=-1)


class LibraryHttpTests(test_home.HttpTests):
    def test_saved_library_and_zip_do_not_require_current_session(self):
        settings=dict(self.settings,mode='esp32-only');recorder=Recorder(self.directory/'captures','c'*32,settings,10)
        raw=b'ESP32 is working!\n';recorder.write(raw);recorder.classify('accepted',parse_line(raw,'esp32-only','motor-001'));recorder.finish('manual-stop')
        self.assertIsNone(self.controller.session_id)
        with self.request('/api/captures') as response:page=json.load(response)
        self.assertEqual(page['total'],1)
        with self.request('/api/captures/'+recorder.session_id+'.zip') as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:self.assertEqual(archive.read('wire.bin'),raw)
        with self.assertRaises(HTTPError) as error:self.request('/api/captures?limit=101')
        self.assertEqual(error.exception.code,422)

for name in dir(test_home.HttpTests):
    if name.startswith('test_') and name not in LibraryHttpTests.__dict__:setattr(LibraryHttpTests,name,None)
if __name__=='__main__':unittest.main()
