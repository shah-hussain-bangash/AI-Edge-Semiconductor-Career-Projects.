"""CI-only native-shell lifecycle smoke test in the disposable Windows checkout."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from home_core import ROOT
from demo_control import status

if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_OS')!='Windows':
    raise SystemExit('This harness runs only inside disposable GitHub Windows CI; it is not a user-runtime command.')

for shell in ('powershell.exe','pwsh'):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    args=[getattr(sys,'_base_executable',sys.executable),str(ROOT/'home-mode/home_server.py'),'--mode','demo','--connect','--web-port',str(port)]
    process=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and not status(port)['reachable']:time.sleep(.1)
        if not status(port)['safe_demo_stop_available']:raise RuntimeError('Disposable demo did not become controllable')
        for action in ('Status','Stop'):
            command=[shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'home.ps1'),'-Action',action,'-WebPort',str(port)]
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=20)
            if result.returncode:raise RuntimeError(shell+' '+action+' failed: '+result.stdout+result.stderr)
            if 'write_token' in result.stdout:raise RuntimeError('Control output exposed a write token')
            print(shell+' '+action+' passed')
        process.wait(timeout=3)
        if process.returncode!=0:raise RuntimeError('Graceful server exit was not successful')
    finally:
        if process.poll() is None:process.terminate()
        process.communicate(timeout=5)
print('PowerShell 5.1 and 7 lifecycle checks passed; no physical hardware used.')
