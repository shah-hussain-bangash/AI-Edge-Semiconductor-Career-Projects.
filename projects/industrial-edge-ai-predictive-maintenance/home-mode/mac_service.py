"""Opt-in per-user Mac login service. Never auto-connects USB or trains a model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import time
from home_core import ROOT,ProcessLock


def job(root=ROOT):
    root=Path(root).resolve();logs=root/'.local/home/service'
    label='org.edgeops.home.'+hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return dict(Label=label,ProgramArguments=[str(root/'.venv-home/bin/python'),'-u',str(root/'home-mode/home_server.py'),'--web-port','8878'],
        WorkingDirectory=str(root),RunAtLoad=True,KeepAlive={'SuccessfulExit':False},ThrottleInterval=15,
        EnvironmentVariables={'PYTHONDONTWRITEBYTECODE':'1'},StandardOutPath=str(logs/'stdout.log'),
        StandardErrorPath=str(logs/'stderr.log'),LimitLoadToSessionType='Aqua')


def render(root=ROOT):return plistlib.dumps(job(root),fmt=plistlib.FMT_XML,sort_keys=True)


def location(root=ROOT,home=None):
    return (Path(home) if home else Path.home())/'Library/LaunchAgents'/(job(root)['Label']+'.plist')


def checked_file(path,root=ROOT):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:raise ValueError('No owned service configuration found')
    if plistlib.loads(path.read_bytes())!=job(root):raise ValueError('Service configuration differs; it was preserved for review')


def run_launchctl(*args):
    return subprocess.run(['/bin/launchctl',*args],capture_output=True,text=True,timeout=15)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('plan','install','start','status','stop','remove'))
    parser.add_argument('--output',type=Path,help='New plan filename; plan never loads a job')
    args=parser.parse_args(argv)
    if sys.platform!='darwin':raise ValueError('Run this only in macOS Terminal; no launch service was changed')
    if args.action!='plan' and args.output:parser.error('--output applies only to plan')
    path=location();label=job()['Label'];domain='gui/'+str(os.getuid());target=domain+'/'+label
    if args.action=='plan':
        if args.output:
            fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(render())
            print('Plan saved only; no service installed or hardware opened.')
        else:print(render().decode('utf-8'))
        return
    if args.action=='install':
        from manage import verify
        verify()
        if (ROOT/'.local/home/RESTORE_INCOMPLETE').exists():raise ValueError('Incomplete restored data must be reviewed before service installation')
        if path.exists() or path.is_symlink():raise ValueError('Service file already exists; no configuration was overwritten')
        with ProcessLock(ROOT/'.local/home/server.lock'):pass
        logs=ROOT/'.local/home/service';logs.mkdir(parents=True,exist_ok=True,mode=0o700);logs.chmod(0o700)
        path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(render())
        result=run_launchctl('bootstrap',domain,str(path))
        if result.returncode:raise ValueError('Service file prepared but registration failed; file preserved. Review the logged-in GUI session and status before retrying.')
        print('Login service registered. It starts only the local dashboard; USB remains disconnected until selected in the UI.')
    else:
        checked_file(path)
        loaded=run_launchctl('print',target).returncode==0
        if args.action=='status':print(json.dumps(dict(label=label,registered=loaded,auto_connect_usb=False,physical_acceptance='pending')));return
        if args.action=='start':
            from manage import verify
            verify()
            if loaded:print('Owned login job is already registered; no duplicate started.');return
            with ProcessLock(ROOT/'.local/home/server.lock'):pass
            if run_launchctl('bootstrap',domain,str(path)).returncode:raise ValueError('Service start not confirmed; configuration preserved')
            print('Owned login job started; USB remains disconnected until selected in the dashboard.');return
        if loaded:
            result=run_launchctl('bootout',target)
            if result.returncode:raise ValueError('Service stop was not confirmed; configuration preserved')
            deadline=time.monotonic()+10
            while True:
                try:
                    with ProcessLock(ROOT/'.local/home/server.lock'):pass
                    break
                except ValueError:
                    if time.monotonic()>=deadline:raise ValueError('Service unload requested but lock release not verified; files preserved')
                    time.sleep(.2)
        if args.action=='remove':
            checked_file(path);path.unlink();print('Owned login-service registration/file removed. Private readings and source remain intact.')
        else:print('Login job unloaded for this session; use start to reload or remove to disable future login startup. Private data preserved.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError,plistlib.InvalidFileException) as error:raise SystemExit('Mac service action stopped: '+str(error))
