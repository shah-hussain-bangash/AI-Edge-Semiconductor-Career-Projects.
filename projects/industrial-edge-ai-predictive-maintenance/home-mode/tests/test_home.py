import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json, os, queue, sqlite3, subprocess, tempfile, threading, time, unittest
from contextlib import closing
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import home_core as core
from home_server import HomeServer
import manage


def frame(**changes):
    value=dict(schema_version=1,device_id='motor-001',seq=0,uptime_ms=0,
        ax_mps2=0,ay_mps2=0,az_mps2=0,temp_c=0,bus_v=0,current_ma=25,
        adxl345_valid=False,ds18b20_valid=False,ina219_valid=False,valid=False)
    value.update(changes)
    return json.dumps(value).encode()+b'\n'


def wait_for(predicate):
    end=time.monotonic()+4
    while time.monotonic()<end:
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for fixture')


class FakeSerial:
    def __init__(self): self.items=queue.Queue(); self.closed=False
    def readline(self, size):
        try: value=self.items.get(timeout=.03)
        except queue.Empty: return b''
        if isinstance(value, Exception): raise value
        return value
    def close(self): self.closed=True


class HomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.directory=Path(self.tmp.name)
        self.settings=dict(mode='esp32-only',port='COM3' if os.name=='nt' else '/dev/cu.fixture',expected_device_id='motor-001')
        self.store=core.Store(self.directory/'history.sqlite3',limit=3)
        self.fake=FakeSerial(); self.clock=[10.]
        self.controller=core.Controller(self.store,self.settings,self.directory,serial_factory=lambda *a,**k:self.fake,monotonic=lambda:self.clock[0])
    def tearDown(self): self.controller.stop(); self.tmp.cleanup()
    def test_text_test_has_no_invented_sensor_or_device_values(self):
        value=core.parse_line(b'ESP32 is working!\n','esp32-only','motor-001')
        self.assertEqual(value['source'],'simulated');self.assertIsNone(value['device_id'])
        self.assertTrue(all(v is None for v in value['values'].values()))
        with self.assertRaises(ValueError): core.parse_line(b'ESP32 is working!','sensors','motor-001')
    def test_zero_is_valid_and_current_converted_once(self):
        value=core.parse_line(frame(adxl345_valid=True,ina219_valid=True),'sensors','motor-001')
        self.assertEqual(value['values']['acceleration_x_mps2'],0)
        self.assertEqual(value['values']['current_a'],.025)
        self.assertIsNone(value['values']['temperature_c'])
        self.assertEqual(value['source'],'serial-unverified')
    def test_invalid_contracts_rejected(self):
        for value in [frame(device_id='other'),frame(valid=True),frame(seq=True),frame(schema_version=2),frame(temp_c=float('nan')),b'{"x":1,"x":2}',b'x'*4097]:
            with self.subTest(value=value[:60]), self.assertRaises((ValueError,UnicodeError)):
                core.parse_line(value,'esp32-only','motor-001')
        with self.assertRaises(ValueError):core.parse_line(frame(adxl345_valid=True),'esp32-only','motor-001')
    def test_invalid_settings_and_private_roundtrip(self):
        core.save_settings(self.directory,self.settings)
        self.assertEqual(core.load_settings(self.directory),self.settings)
        if os.name!='nt':self.assertEqual((self.directory/'config.json').stat().st_mode&0o777,0o600)
        for value in [dict(self.settings,port='/etc/passwd'),dict(self.settings,token='secret'),dict(self.settings,mode='cloud')]:
            with self.assertRaises(ValueError):core.validate_settings(value)
    def test_fragmented_serial_stale_disconnect_and_history(self):
        self.controller.start(self.settings)
        for part in [b'ESP32 is ',b'working!\n',b'x'*4097,b'discard\n',b'ESP32 is working!\n']:self.fake.items.put(part)
        wait_for(lambda:self.controller.status()['accepted']==2)
        self.assertTrue(self.controller.status()['fresh']);self.assertEqual(self.controller.status()['rejected'],1)
        self.clock[0]=16
        self.assertFalse(self.controller.status()['fresh'])
        self.assertTrue(all(v is None for v in self.controller.status()['live_values'].values()))
        self.controller.stop();self.assertTrue(self.fake.closed)
        self.assertIsNone(self.controller.status()['last_sample']);self.assertEqual(self.store.history()['total'],2)
    def test_unplug_clears_live_values(self):
        self.controller.start(self.settings);self.fake.items.put(b'ESP32 is working!\n')
        wait_for(lambda:self.controller.status()['accepted']==1)
        self.fake.items.put(OSError('fixture unplug'))
        wait_for(lambda:self.controller.status()['state']=='error')
        self.assertIsNone(self.controller.status()['last_sample'])
    def test_storage_error_is_not_a_bad_sensor_frame(self):
        with patch.object(self.store,'append',side_effect=ValueError('fixture storage fault')):
            self.controller.start(self.settings);self.fake.items.put(b'ESP32 is working!\n')
            wait_for(lambda:self.controller.status()['state']=='error')
        self.assertEqual(self.controller.status()['rejected'],0)
    def test_rolling_retention_integrity_and_generation_fencing(self):
        sample=core.parse_line(b'ESP32 is working!','esp32-only','motor-001')
        for _ in range(5):self.controller._accept(sample,0,self.controller.stop_event,'fixture')
        self.assertEqual(self.store.history()['total'],3)
        self.controller._accept(sample,99,self.controller.stop_event,'stale')
        self.assertEqual(self.controller.status()['accepted'],5)
        with closing(sqlite3.connect(self.store.path)) as db, db:db.execute("UPDATE home_samples SET payload_json='{}'")
        with self.assertRaises(ValueError):self.store.history()
    def test_process_lock_rejects_duplicate_and_releases(self):
        path=self.directory/'lock'
        with core.ProcessLock(path):
            with self.assertRaises(ValueError):
                with core.ProcessLock(path):pass
        with core.ProcessLock(path):pass
    def test_invalid_configuration_preserved(self):
        path=self.directory/'config.json';path.write_text('{broken',encoding='utf-8')
        with self.assertRaises(ValueError):core.load_settings(self.directory)
        self.assertEqual(path.read_text(encoding='utf-8'),'{broken')
    def test_unmanaged_environment_not_overwritten(self):
        root=self.directory/'project';root.mkdir();env=root/'.venv-home';env.mkdir()
        sentinel=env/'keep';sentinel.write_text('preserve',encoding='utf-8')
        with patch.object(manage,'ROOT',root),patch.object(manage,'VENV',env),patch.object(manage,'MARKER',env/'marker'):
            with self.assertRaisesRegex(ValueError,'will not overwrite'):manage.setup()
        self.assertEqual(sentinel.read_text(encoding='utf-8'),'preserve')
    def test_update_refuses_dirty_and_wrong_branch(self):
        repo=self.directory/'repo';repo.mkdir()
        result=subprocess.run(['git','init','--initial-branch=release/mac-bench-20261126',str(repo)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        manage.check_clean_update(repo)
        (repo/'user-work.txt').write_text('preserve',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Local changes'):manage.check_clean_update(repo)
        subprocess.run(['git','-C',str(repo),'checkout','-b','my-work'],check=True,capture_output=True)
        with self.assertRaisesRegex(ValueError,'current branch was preserved'):manage.check_clean_update(repo)
        self.assertEqual((repo/'user-work.txt').read_text(encoding='utf-8'),'preserve')


class HttpTests(HomeTests):
    # Reuse fixtures; run only HTTP-specific tests here.
    def setUp(self):
        super().setUp();self.server=HomeServer(0,self.controller)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()
    def request(self,path,body=None,headers=None):
        merged={'Content-Type':'application/json','Origin':self.url,'X-Edgeops-Home-Token':self.server.write_token}
        merged.update(headers or {})
        request=Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=merged)
        return urlopen(request,timeout=5)
    def test_http_demo_stop_and_csv_source(self):
        with self.request('/api/connect',dict(self.settings,mode='demo')) as r:self.assertEqual(r.status,200)
        wait_for(lambda:self.controller.status()['accepted']>0)
        with self.request('/api/status') as r:data=json.load(r)
        self.assertEqual(data['live_values']['acceleration_y_mps2'],0);self.assertFalse(data['production_ready'])
        with self.request('/api/history.csv') as r:
            csv=r.read().decode();self.assertIn('simulated,demo,software-demo',csv);self.assertIn('False,False,False',csv)
        with self.request('/api/disconnect',{}) as r:self.assertFalse(json.load(r)['fresh'])
        with self.request('/app') as r:self.assertIn("default-src 'none'",r.headers['Content-Security-Policy'])
    def test_http_rejects_remote_host_csrf_bad_body_and_limits(self):
        for path,body,headers,code in [('/api/status',None,{'Host':'evil.invalid'},403),('/api/connect',self.settings,{'Origin':'https://evil.invalid'},403),('/api/disconnect',{}, {'X-Edgeops-Home-Token':'bad'},403),('/api/history?limit=201',None,{},422),('/api/connect',dict(self.settings,token='not-supported'),{},422),('/api/connect',{'x':'a'*5000},{},413)]:
            with self.subTest(path=path,headers=headers),self.assertRaises(HTTPError) as ctx:self.request(path,body,headers)
            self.assertEqual(ctx.exception.code,code)
    @unittest.skipIf(os.name=='nt','POSIX pseudo-terminal fixture; not physical hardware')
    def test_real_pyserial_pty_to_http(self):
        import pty
        master,slave=pty.openpty()
        try:
            self.controller.serial_factory=None
            settings=dict(self.settings,port=os.ttyname(slave))
            with self.request('/api/connect',settings):pass
            wait_for(lambda:self.controller.status()['state']=='port-open')
            os.write(master,b'ESP32 is working!\n')
            wait_for(lambda:self.controller.status()['accepted']==1)
            with self.request('/api/status') as r:data=json.load(r)
            self.assertTrue(data['fresh']);self.assertEqual(data['last_sample']['source'],'simulated')
            self.assertTrue(all(v is None for v in data['live_values'].values()))
        finally:self.controller.stop();os.close(master);os.close(slave)

# Avoid duplicated inherited tests while sharing fixture helpers.
for name in list(HomeTests.__dict__):
    if name.startswith('test_') and name not in HttpTests.__dict__:setattr(HttpTests,name,None)
if __name__=='__main__':unittest.main()
