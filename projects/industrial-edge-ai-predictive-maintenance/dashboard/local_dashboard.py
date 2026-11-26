"""Manage one loopback dashboard with a private control channel and graceful shutdown.

No process killing, dependency installation, hardware connection or cloud service.
Only instances launched with this manager can be controlled by it.
"""
import argparse
from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parent
FORMAT='edgeops-local-dashboard-v1'


class ManagedStateError(Exception):
    """Only fixed, nonsecret messages safe to show in the local CLI."""


def private_folder(path):
    if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('Linked runtime directory')
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not path.is_dir() or (os.name!='nt' and path.stat().st_mode&0o077):raise ValueError('Runtime directory must be owner-only')


@contextmanager
def instance_lock(database):
    path=database.with_name(database.name+'.manager.lock')
    if path.is_symlink():raise ValueError('Linked instance lock')
    descriptor=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    locked=False
    try:
        if os.fstat(descriptor).st_size==0:os.write(descriptor,b'0')
        os.lseek(descriptor,0,os.SEEK_SET)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(descriptor,msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        locked=True
        yield
    finally:
        if locked:
            if os.name=='nt':
                os.lseek(descriptor,0,os.SEEK_SET);msvcrt.locking(descriptor,msvcrt.LK_UNLCK,1)
            else:fcntl.flock(descriptor,fcntl.LOCK_UN)
        os.close(descriptor)


def state_path(runtime):return runtime/'instance.json'


def read_state(runtime):
    path=state_path(runtime)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>4096:raise ValueError('No managed instance record')
    if os.name!='nt' and path.stat().st_mode&0o077:raise ValueError('Instance record must be owner-only')
    value=json.loads(path.read_text(encoding='utf-8'))
    if (value.get('format')!=FORMAT or not re.fullmatch('[a-f0-9]{64}',value.get('token',''))
        or not re.fullmatch('[a-f0-9]{32}',value.get('instance',''))
        or any(type(value.get(key)) is not int or not 1<=value[key]<=65535 for key in ('control_port','port'))):raise ValueError('Invalid instance record')
    return value


def write_state(runtime,state):
    path=state_path(runtime)
    if path.is_symlink():raise ValueError('Linked instance record')
    staging=runtime/('instance-'+secrets.token_hex(8)+'.tmp')
    descriptor=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(state,stream);stream.flush();os.fsync(stream.fileno())
        os.replace(staging,path)
    finally:
        if staging.exists():staging.unlink()


def control(runtime,action):
    state=read_state(runtime)
    request=Request('http://127.0.0.1:'+str(state['control_port'])+'/'+action,
        data=b'' if action=='stop' else None,
        headers={'Authorization':'Bearer '+state['token'],'X-Edgeops-Instance':state['instance']},
        method='POST' if action=='stop' else 'GET')
    # Never send the private local control token through a configured proxy.
    with build_opener(ProxyHandler({})).open(request,timeout=2) as response:
        raw=response.read(8193)
    if len(raw)>8192:raise ValueError('Invalid control response')
    result=json.loads(raw)
    if result.get('instance')!=state['instance'] or result.get('format')!=FORMAT:raise ValueError('Different instance answered')
    return result


def control_server(server,state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body):
            raw=json.dumps(body).encode();self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('Connection','close');self.end_headers()
            self.close_connection=True;self.wfile.write(raw)

        def dispatch(self,stop=False):
            valid=(self.headers.get('Host')=='127.0.0.1:'+str(self.server.server_port)
                and self.headers.get('Origin') is None
                and hmac.compare_digest(self.headers.get('Authorization','').encode(),'Bearer '.encode()+state['token'].encode())
                and hmac.compare_digest(self.headers.get('X-Edgeops-Instance','').encode(),state['instance'].encode()))
            if not valid:return self.reply(403,{'error':'Control request refused'})
            lengths=self.headers.get_all('Content-Length',[])
            if self.headers.get('Transfer-Encoding') or lengths not in ([],['0']):return self.reply(400,{'error':'Empty control body required'})
            if self.path!=('/stop' if stop else '/status'):return self.reply(404,{'error':'Unknown control action'})
            if stop:server.should_exit=True
            self.reply(202 if stop else 200,dict(format=FORMAT,instance=state['instance'],
                state='stopping' if server.should_exit else 'ready' if server.started else 'starting',port=state['port'],
                url='http://127.0.0.1:'+str(state['port'])+'/app?view=registered'))

        def do_GET(self):self.dispatch()
        def do_POST(self):self.dispatch(True)

    class LocalControl(ThreadingHTTPServer):
        daemon_threads=True
        slots=threading.BoundedSemaphore(8)
        def process_request(self,request,address):
            if not self.slots.acquire(blocking=False):return self.shutdown_request(request)
            try:super().process_request(request,address)
            except Exception:self.slots.release();raise
        def process_request_thread(self,request,address):
            try:super().process_request_thread(request,address)
            finally:self.slots.release()
        def get_request(self):
            connection,address=super().get_request();connection.settimeout(2);return connection,address
    return LocalControl(('127.0.0.1',0),Handler)


def serve(database,runtime,port,instance):
    # Claim the application port before importing/starting the app. A conflicting
    # listener must not trigger schema/bootstrap writes in another installation.
    import uvicorn
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    if os.name=='nt':listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    else:listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    controller=None;thread=None
    try:
        listener.bind(('127.0.0.1',port));listener.listen(2048)
        database.parent.mkdir(mode=0o700,parents=True,exist_ok=True);private_folder(runtime)
        with instance_lock(database):
            os.environ['EDGEOPS_DASHBOARD_DB']=str(database)
            server=uvicorn.Server(uvicorn.Config('server:app',host='127.0.0.1',port=port,log_level='info'))
            state=dict(format=FORMAT,instance=instance,token=secrets.token_hex(32),port=port,pid=os.getpid())
            controller=control_server(server,state);state['control_port']=controller.server_port
            write_state(runtime,state)
            thread=threading.Thread(target=controller.serve_forever,daemon=True);thread.start()
            try:server.run(sockets=[listener])
            finally:
                try:
                    if read_state(runtime)['instance']==instance:state_path(runtime).unlink()
                except (ValueError,OSError):pass
            if not server.started:raise ValueError('Dashboard startup did not complete')
    finally:
        if controller:
            if thread:controller.shutdown();thread.join(timeout=3)
            controller.server_close()
        listener.close()


def start_background(database,runtime,port,timeout):
    private_folder(runtime)
    # Do not launch against an already controlled instance, even on a new port.
    try:control(runtime,'status')
    except Exception:pass
    else:raise ManagedStateError('A managed instance is already running. Use status before starting another.')
    identity=secrets.token_hex(16)
    log=runtime/('server-'+identity+'.log')
    descriptor=os.open(log,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    kwargs=dict(cwd=ROOT,stdin=subprocess.DEVNULL)
    if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP
    else:kwargs['start_new_session']=True
    with os.fdopen(descriptor,'wb') as stream:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'_serve','--database',str(database),
            '--runtime-dir',str(runtime),'--port',str(port),'--instance',identity],stdout=stream,stderr=stream,**kwargs)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if process.poll() is not None:raise ManagedStateError('Dashboard did not start. Inspect the selected runtime directory and its private server log.')
        try:
            state=control(runtime,'status')
            if state['instance']==identity and state['state']=='ready':return state
        except Exception:pass
        time.sleep(.1)
    raise ManagedStateError('Startup is unconfirmed. Use status before retrying. No process was force-stopped.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','status','stop','_serve'])
    parser.add_argument('--database',type=Path,default=Path(os.environ.get('EDGEOPS_DASHBOARD_DB',ROOT/'.local/dashboard.sqlite3')))
    parser.add_argument('--runtime-dir',type=Path)
    parser.add_argument('--port',type=int,default=8877)
    parser.add_argument('--background',action='store_true')
    parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--instance',default='')
    args=parser.parse_args()
    if not 1<=args.port<=65535 or not 1<=args.timeout<=60:parser.error('Use port 1–65535 and timeout 1–60 seconds')
    database=args.database.resolve();runtime=(args.runtime_dir or database.parent/(database.stem+'-runtime')).absolute()
    try:
        if args.action in ('start','_serve'):
            if args.action=='start' and args.background:result=start_background(database,runtime,args.port,args.timeout)
            else:
                identity=args.instance if args.action=='_serve' else secrets.token_hex(16)
                if not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('Invalid instance identity')
                serve(database,runtime,args.port,identity);result=dict(state='stopped')
        else:
            result=control(runtime,args.action)
            if args.action=='stop':
                deadline=time.monotonic()+args.timeout
                while time.monotonic()<deadline:
                    if not state_path(runtime).exists():result['state']='stopped';break
                    try:
                        if read_state(runtime)['instance']!=result['instance']:raise ValueError('A new instance replaced the stopped instance')
                    except FileNotFoundError:result['state']='stopped';break
                    time.sleep(.1)
                else:raise ManagedStateError('Graceful shutdown was requested and is still draining. Check status again. No process was force-stopped.')
        print(json.dumps(result,sort_keys=True))
    except ManagedStateError as error:parser.exit(1,str(error)+'\n')
    except Exception:
        # Paths, tokens, environment and arbitrary exception text stay private.
        parser.exit(1,'Local dashboard operation refused or unconfirmed. Check the selected database/runtime, private log and existing listener. No unrelated process was stopped.\n')


if __name__=='__main__':main()
