"""Graceful demo lifecycle with disposable loopback servers, never user hardware."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import demo_control
from home_core import ROOT,Store
import test_home
from test_home import wait_for


class DemoControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name);self.process=None
        self.addCleanup(self.tmp.cleanup);self.addCleanup(self.cleanup_process)
        self.launch()
    def launch(self,mode='demo'):
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        # Bypass Windows venv redirectors so failed-test cleanup owns one real PID.
        python=getattr(sys,'_base_executable',sys.executable) if os.name=='nt' else sys.executable
        args=[python,str(ROOT/'home-mode/tests/run_control_server.py'),'--data-dir',str(self.directory),'--web-port',str(self.port),'--mode',mode]
        if mode=='demo':args.append('--connect')
        self.process=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if self.process.poll() is not None:
                out,err=self.process.communicate()
                self.fail('Fixture exited before readiness: '+out+err)
            if demo_control.status(self.port,self.directory)['reachable']:return
            time.sleep(.1)
        self.cleanup_process()
        self.fail('Fixture startup timed out: '+self.fixture_output)
    def cleanup_process(self):
        if self.process is not None:
            if self.process.poll() is None:self.process.terminate()
            out,err=self.process.communicate(timeout=5)
            self.fixture_output=out+err
    def test_status_is_read_only_redacts_tokens_and_stop_releases_lock(self):
        state=demo_control.status(self.port,self.directory)
        self.assertTrue(state['safe_demo_stop_available']);self.assertNotIn('write_token',state);self.assertNotIn('instance_id',state)
        before=Store(self.directory/'history.sqlite3').history()['total']
        result=demo_control.stop_demo(self.port,self.directory)
        self.assertTrue(result['stopped']);self.process.wait(timeout=3);self.assertEqual(self.process.returncode,0)
        self.assertGreaterEqual(Store(self.directory/'history.sqlite3').history()['total'],before)
        self.assertFalse(demo_control.status(self.port,self.directory)['reachable'])
    def test_different_data_or_checkout_identity_cannot_stop_server(self):
        other=self.directory/'other'
        with self.assertRaisesRegex(ValueError,'different data directory'):demo_control.stop_demo(self.port,other)
        self.assertFalse(other.exists());self.assertIsNone(self.process.poll())
        with patch('demo_control.instance_identity',return_value='0'*64):
            self.assertFalse(demo_control.status(self.port,self.directory)['matches_checkout_and_data'])
            with self.assertRaises(ValueError):demo_control.stop_demo(self.port,self.directory)
        self.assertIsNone(self.process.poll())
    def test_usb_mode_is_preserved_without_opening_a_port(self):
        demo_control.stop_demo(self.port,self.directory);self.process.communicate(timeout=3)
        self.launch(mode='sensors')  # No --connect: a serial port is never opened.
        state=demo_control.status(self.port,self.directory)
        self.assertEqual(state['mode'],'sensors');self.assertFalse(state['safe_demo_stop_available'])
        with self.assertRaisesRegex(ValueError,'preserved'):demo_control.stop_demo(self.port,self.directory)
        self.assertIsNone(self.process.poll())
    def test_legacy_status_refuses_shutdown(self):
        old=dict(scope='edgeops-lightweight-home',production_ready=False,settings=dict(mode='demo'))
        with patch('demo_control.request',return_value=old) as request:
            with self.assertRaisesRegex(ValueError,'Legacy server'):demo_control.stop_demo(self.port,self.directory)
            self.assertEqual(request.call_count,1);self.assertEqual(request.call_args.args[1],'/api/status')
        self.assertIsNone(self.process.poll())
    def test_proxy_environment_ignored_and_redirect_not_followed(self):
        with patch.dict(os.environ,{'HTTP_PROXY':'http://127.0.0.1:1','http_proxy':'http://127.0.0.1:1','NO_PROXY':'','no_proxy':''}):
            self.assertTrue(demo_control.status(self.port,self.directory)['reachable'])
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):self.send_response(302);self.send_header('Location','http://192.0.2.1/never-follow');self.end_headers()
            def log_message(self,*_):pass
        server=HTTPServer(('127.0.0.1',0),Redirect);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with self.assertRaises(HTTPError) as error:demo_control.request(server.server_port,'/api/status')
            self.assertEqual(error.exception.code,302)
        finally:server.shutdown();server.server_close();thread.join()


class ShutdownHttpTests(test_home.HttpTests):
    def test_shutdown_rejects_missing_token_origin_wrong_nonce_and_shape(self):
        body=dict(instance_id=self.server.instance_id)
        for payload,headers,code in [(body,{'X-Edgeops-Home-Token':'bad'},403),(body,{'Origin':'https://other.invalid'},403),({}, {},422),(dict(instance_id='0'*32),{},422)]:
            with self.assertRaises(HTTPError) as error:self.request('/api/shutdown',payload,headers)
            self.assertEqual(error.exception.code,code)
        self.assertFalse(self.controller.shutting_down)
    def test_current_usb_mode_is_rechecked_when_shutdown_arrives(self):
        with self.request('/api/connect',dict(self.settings,mode='sensors')):pass
        with self.assertRaises(HTTPError) as error:self.request('/api/shutdown',dict(instance_id=self.server.instance_id))
        self.assertEqual(error.exception.code,422);self.assertFalse(self.controller.shutting_down)
        self.assertFalse(self.fake.closed)
    def test_shutdown_fence_prevents_new_readers_after_demo_check(self):
        self.controller.start(dict(self.settings,mode='demo'));wait_for(lambda:self.controller.accepted>0)
        self.controller.prepare_demo_shutdown()
        self.assertTrue(self.controller.shutting_down)
        with self.assertRaisesRegex(ValueError,'shutting down'):self.controller.start(self.settings)
        self.assertEqual(self.controller.settings['mode'],'demo');self.assertFalse(self.controller.status()['fresh'])

for name in dir(test_home.HttpTests):
    if name.startswith('test_') and name not in ShutdownHttpTests.__dict__:setattr(ShutdownHttpTests,name,None)
if __name__=='__main__':unittest.main()
