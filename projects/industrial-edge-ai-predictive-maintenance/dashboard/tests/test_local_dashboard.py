"""Disposable full-server lifecycle checks; never control the operator's server."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler
import local_dashboard as manager

ROOT=Path(__file__).resolve().parents[1]
HTTP=build_opener(ProxyHandler({}))


def available_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));return listener.getsockname()[1]


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='edgeops-managed-fixture-')
        self.root=Path(self.temp.name);self.database=self.root/'fixture.sqlite3';self.runtime=self.root/'runtime'
        self.env={**os.environ,'EDGEOPS_DASHBOARD_DB':str(self.database),'EDGEOPS_ADMIN_EMAIL':'fixture@example.invalid',
            'EDGEOPS_ADMIN_PASSWORD':secrets.token_urlsafe(24),'EDGEOPS_PRIVATE_KEY_FILE':'','EDGEOPS_SMTP_HOST':'',
            'EDGEOPS_DELIVERY_SPOOL_DB':str(self.root/'spool.sqlite3'),'EDGEOPS_OFFLINE_EXPERIMENT_ROOT':str(self.root/'artifacts'),
            'EDGEOPS_SYNTHETIC_TELEMETRY_DB':str(self.root/'telemetry.sqlite3'),'PYTHONDONTWRITEBYTECODE':'1'}
        # Each disposable child records stacks if startup stalls before logging.
        # This hook is confined to the temporary fixture, never live processes.
        (self.root/'sitecustomize.py').write_text('import faulthandler\nfaulthandler.dump_traceback_later(10,repeat=True)\n',encoding='utf-8')
        self.env['PYTHONPATH']=str(self.root)+os.pathsep+self.env.get('PYTHONPATH','')
        self.addCleanup(self.cleanup)

    def command(self,action,*extra):
        return subprocess.run([sys.executable,str(ROOT/'local_dashboard.py'),action,'--database',str(self.database),
            '--runtime-dir',str(self.runtime),*extra],cwd=ROOT,env=self.env,capture_output=True,text=True,timeout=45)

    def diagnostics(self):
        parts=[]
        try:parts.append('Control: '+json.dumps(manager.control(self.runtime,'status')))
        except Exception as error:parts.append('Control: '+type(error).__name__+' '+str(error))
        for path in self.runtime.glob('server-*.log'):
            parts.append(path.name+': '+path.read_text(encoding='utf-8',errors='replace')[-4000:])
        return '\n'.join(parts)

    def cleanup(self):
        try:manager.control(self.runtime,'stop')
        except Exception:pass
        for _ in range(100):
            try:self.temp.cleanup();return
            except PermissionError:time.sleep(.05)
        self.temp.cleanup()

    def test_background_start_status_duplicate_and_graceful_stop(self):
        port=available_port();started=self.command('start','--background','--port',str(port))
        self.assertEqual(started.returncode,0,started.stderr+'\n'+self.diagnostics());result=json.loads(started.stdout)
        self.assertEqual(result['state'],'ready');self.assertNotIn('token',result)
        record=manager.read_state(self.runtime);self.assertNotIn(record['token'],started.stdout+started.stderr)
        if os.name!='nt':self.assertEqual(manager.state_path(self.runtime).stat().st_mode&0o077,0)
        with HTTP.open('http://127.0.0.1:'+str(port)+'/health/ready') as response:self.assertEqual(response.status,200)
        duplicate=self.command('start','--background','--port',str(available_port()))
        self.assertNotEqual(duplicate.returncode,0);self.assertEqual(manager.read_state(self.runtime)['instance'],record['instance'])
        other=self.root/'different-runtime'
        duplicate=self.command('start','--background','--port',str(available_port()),'--runtime-dir',str(other))
        self.assertNotEqual(duplicate.returncode,0);self.assertFalse(manager.state_path(other).exists())
        self.assertEqual(manager.control(self.runtime,'status')['state'],'ready')
        self.assertEqual(json.loads(self.command('status').stdout)['instance'],record['instance'])
        stopped=self.command('stop');self.assertEqual(stopped.returncode,0,stopped.stderr)
        self.assertEqual(json.loads(stopped.stdout)['state'],'stopped');self.assertTrue(self.database.is_file())
        self.assertFalse(manager.state_path(self.runtime).exists());self.assertNotEqual(self.command('stop').returncode,0)

    def test_occupied_port_does_not_initialize_or_migrate_database(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen()
            result=self.command('start','--port',str(listener.getsockname()[1]))
            self.assertNotEqual(result.returncode,0);self.assertFalse(self.database.exists())
            self.assertEqual(listener.getsockname()[0],'127.0.0.1')
            with closing(sqlite3.connect(self.database)) as db:
                db.execute('CREATE TABLE fixture_marker(value TEXT)');db.commit()
            result=self.command('start','--port',str(listener.getsockname()[1]));self.assertNotEqual(result.returncode,0)
            with closing(sqlite3.connect(self.database)) as db:self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[('fixture_marker',)])

    def test_control_auth_origin_identity_and_empty_body(self):
        server=SimpleNamespace(started=True,should_exit=False)
        state=dict(format=manager.FORMAT,token=secrets.token_hex(32),instance=secrets.token_hex(16),port=8877,pid=os.getpid())
        controller=manager.control_server(server,state);state['control_port']=controller.server_port
        thread=threading.Thread(target=controller.serve_forever,daemon=True);thread.start()
        try:
            manager.private_folder(self.runtime);manager.write_state(self.runtime,state)
            base='http://127.0.0.1:'+str(controller.server_port)
            headers={'Authorization':'Bearer '+state['token'],'X-Edgeops-Instance':state['instance']}
            for changes,body,expected in [({'Authorization':'Bearer wrong'},b'',403),({'Origin':'http://example.invalid'},b'',403),({'X-Edgeops-Instance':'0'*32},b'',403),({},b'not empty',400)]:
                with self.subTest(changes=tuple(changes),expected=expected),self.assertRaises(HTTPError) as refused:
                    HTTP.open(Request(base+'/stop',data=body,headers={**headers,**changes},method='POST'))
                self.assertEqual(refused.exception.code,expected);refused.exception.close();self.assertFalse(server.should_exit)
            self.assertEqual(manager.control(self.runtime,'status')['state'],'ready')
            self.assertEqual(manager.control(self.runtime,'stop')['state'],'stopping');self.assertTrue(server.should_exit)
        finally:controller.shutdown();thread.join(3);controller.server_close();manager.state_path(self.runtime).unlink(missing_ok=True)

    def test_fixed_loopback_controls_start_without_reverse_dns(self):
        state=dict(format=manager.FORMAT,token=secrets.token_hex(32),instance=secrets.token_hex(16),port=8877)
        with patch('socket.getfqdn',side_effect=AssertionError('Resolver is unavailable in this fixture')):
            controller=manager.control_server(SimpleNamespace(started=False,should_exit=False),state)
            try:self.assertEqual(controller.server_address[0],'127.0.0.1')
            finally:controller.server_close()

    def test_shutdown_drains_an_existing_write_before_exiting(self):
        port=available_port();marker=self.root/'entered';self.env['EDGEOPS_FIXTURE_MARKER']=str(marker)
        code='''import os,time,sys,faulthandler
faulthandler.dump_traceback_later(10,repeat=True)
from pathlib import Path
import server,local_dashboard
@server.app.get('/fixture-slow-write')
def slow():
 with server.database() as db:
  db.execute('BEGIN IMMEDIATE')
  db.execute("INSERT INTO audit(time_utc,actor,action,detail) VALUES('fixture','fixture','fixture_write','Fixture only')")
  Path(os.environ['EDGEOPS_FIXTURE_MARKER']).write_text('entered')
  time.sleep(1)
 return {'committed':True}
sys.argv=['local_dashboard.py','start',*sys.argv[1:]]
local_dashboard.main()
'''
        logfile=self.root/'drain-fixture.log'
        with logfile.open('wb') as stream:
            process=subprocess.Popen([sys.executable,'-c',code,'--database',str(self.database),'--runtime-dir',str(self.runtime),'--port',str(port)],cwd=ROOT,env=self.env,stdout=stream,stderr=stream,**({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
        try:
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                try:
                    if manager.control(self.runtime,'status')['state']=='ready':break
                except Exception:pass
                self.assertIsNone(process.poll(),'Fixture server exited');time.sleep(.05)
            else:self.fail('Fixture startup timed out\n'+self.diagnostics()+'\n'+logfile.read_text(encoding='utf-8',errors='replace')[-6000:])
            def request():
                with HTTP.open('http://127.0.0.1:'+str(port)+'/fixture-slow-write',timeout=10) as response:return response.status,json.load(response)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(request);deadline=time.monotonic()+5
                while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(marker.exists());stopped=self.command('stop');self.assertEqual(stopped.returncode,0,stopped.stderr)
                self.assertEqual(future.result(timeout=5),(200,{'committed':True}))
            self.assertEqual(process.wait(timeout=5),0)
            with closing(sqlite3.connect(self.database)) as db:self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='fixture_write'").fetchone()[0],1)
        finally:
            if process.poll() is None:
                try:manager.control(self.runtime,'stop')
                except Exception:pass
                process.wait(timeout=15)

    def test_stale_record_never_uses_its_pid_to_stop_a_process(self):
        manager.private_folder(self.runtime)
        manager.write_state(self.runtime,dict(format=manager.FORMAT,instance=secrets.token_hex(16),token=secrets.token_hex(32),port=8877,control_port=available_port(),pid=os.getpid()))
        self.assertNotEqual(self.command('stop').returncode,0)
        self.assertTrue(manager.state_path(self.runtime).exists());self.assertFalse(self.database.exists())
