"""CI-only per-user service lifecycle; never connects a serial reader."""
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from home_core import ROOT
from demo_control import status
from mac_service import job,location

if os.environ.get('GITHUB_ACTIONS')!='true' or sys.platform!='darwin':raise SystemExit('This harness runs only in disposable Mac CI')
domain='gui/'+str(os.getuid())
if subprocess.run(['/bin/launchctl','print',domain],capture_output=True).returncode:
    print('No logged-in GUI domain on this runner. Plan lint passed; actual service loading remains unverified here.')
    raise SystemExit(0)
path=location()
if path.exists():raise SystemExit('Existing service file preserved; smoke test refused')
command=[sys.executable,str(ROOT/'home-mode/mac_service.py')]
created=False
try:
    for action in ('install','status','stop','start','remove'):
        result=subprocess.run(command+[action],capture_output=True,text=True,timeout=30)
        created=path.exists() or created
        if result.returncode:raise RuntimeError(action+' failed: '+result.stdout+result.stderr)
        print(action+' passed')
        if action in ('install','start'):
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                state=status()
                if state.get('reachable') and state.get('matches_checkout_and_data'):break
                time.sleep(.1)
            else:raise RuntimeError('Owned login service did not respond')
            if state['reader_state']!='disconnected' or state['fresh']:raise RuntimeError('Login service unexpectedly started acquisition')
    if path.exists():raise RuntimeError('Owned service file was not removed')
finally:
    if created and path.exists():
        cleanup=subprocess.run(command+['remove'],capture_output=True,text=True,timeout=30)
        if cleanup.returncode:print('CI cleanup needs review: '+cleanup.stderr)
print('Disposable Mac service lifecycle passed; USB remained disconnected. This is not the owner MacBook test.')
