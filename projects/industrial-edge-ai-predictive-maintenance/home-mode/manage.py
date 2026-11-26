"""Create/verify a dedicated home environment; preserve user files and existing environments."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import venv

from home_core import ProcessLock, ROOT, serial_ports

SUPPORTED = {(3, 12), (3, 13), (3, 14)}
VENV = ROOT / '.venv-home'
MARKER = VENV / '.edgeops-home-environment.json'


def verify(python=None):
    python = python or VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not MARKER.is_file(): raise ValueError('This is not a managed home environment. Run ' + (r'.\home.ps1 -Action Setup' if os.name == 'nt' else 'bash home_setup.command') + ' first.')
    metadata = json.loads(MARKER.read_text(encoding='utf-8'))
    if metadata != {'format': 'edgeops-home-environment-v1'}: raise ValueError('Unexpected environment marker; no files were replaced')
    result = subprocess.run([str(python), '-c',
        'import json,sys,serial; print(json.dumps({"python":list(sys.version_info[:2]),"serial":serial.VERSION,"prefix":sys.prefix}))'],
        check=True, capture_output=True, text=True)
    state = json.loads(result.stdout)
    if tuple(state['python']) not in SUPPORTED or state['serial'] != '3.5' or Path(state['prefix']).resolve() != VENV.resolve():
        raise ValueError('Home environment does not match supported Python / pySerial 3.5. Run setup after stopping home mode.')


def setup():
    if sys.version_info[:2] not in SUPPORTED: raise ValueError('Use Python 3.12, 3.13 or 3.14. A current Python 3.14 installer supports Monterey.')
    with ProcessLock(ROOT / '.local/home/server.lock'):
        if VENV.exists() and not MARKER.exists():
            raise ValueError('.venv-home already exists without an EDGEOPS marker. Preserve it and use a fresh clone or rename it manually; setup will not overwrite it.')
        if not VENV.exists():
            venv.EnvBuilder(with_pip=True).create(VENV)
            MARKER.write_text(json.dumps({'format': 'edgeops-home-environment-v1'}) + '\n', encoding='utf-8')
        if json.loads(MARKER.read_text(encoding='utf-8')) != {'format': 'edgeops-home-environment-v1'}:
            raise ValueError('Unexpected environment marker; no packages were changed')
        python = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        version = subprocess.run([str(python), '-c', 'import sys;print("%s.%s"%sys.version_info[:2])'], check=True, capture_output=True, text=True).stdout.strip()
        if version not in {'3.12', '3.13', '3.14'}: raise ValueError('Existing environment uses an unsupported Python; it was preserved')
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(ROOT / 'home-mode/requirements.txt')], check=True)
        verify(python)
    print('Home setup complete: Python standard library + pyserial==3.5 only.')
    print('No serial port opened, firmware uploaded, cloud configured or model training installed.')
    if os.name == 'nt': print(r'Windows launch: .\home.ps1 -Action Start. Software-only demo: .\home.ps1 -Action Demo')
    else: print('Mac launch: bash home_start.command. Software-only demo: bash home_start.command --mode demo --connect')


def check_clean_update(repo=ROOT):
    repo = Path(repo)
    branch = subprocess.run(['git', '-C', str(repo), 'branch', '--show-current'], check=True, capture_output=True, text=True).stdout.strip()
    if branch != 'release/mac-bench-20261126': raise ValueError('Update expects release/mac-bench-20261126. Your current branch was preserved: ' + branch)
    changes = subprocess.run(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=normal'], check=True, capture_output=True, text=True).stdout
    if changes.strip(): raise ValueError('Local changes or non-ignored files exist. Review/commit them yourself before updating. No stash, reset, clean or overwrite was performed.')


def update():
    with ProcessLock(ROOT / '.local/home/server.lock'):
        check_clean_update()
        subprocess.run(['git', '-C', str(ROOT), 'pull', '--ff-only', 'origin', 'release/mac-bench-20261126'], check=True)
    print('Source updated by fast-forward only. Run ' + (r'.\home.ps1 -Action Setup' if os.name=='nt' else 'bash home_setup.command') + ', then launch home mode.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'setup', 'verify', 'update', 'ports', 'status', 'stop-demo', 'backup', 'verify-backup', 'restore'))
    parser.add_argument('--web-port',type=int,default=8878,help='Loopback port for status/stop-demo')
    parser.add_argument('--data-dir',type=Path,help='Expected data directory for status/stop-demo')
    parser.add_argument('--output',type=Path,help='New private backup directory')
    parser.add_argument('--backup',type=Path,help='Existing verified backup folder')
    parser.add_argument('--destination',type=Path,help='New restore directory; never overwritten')
    args = parser.parse_args(argv)
    if args.action in ('backup','verify-backup','restore'):
        import home_backup
        if args.web_port!=8878:parser.error('Backup commands do not select a web port')
        if args.action=='backup':
            if args.backup or args.destination:parser.error('backup accepts --data-dir and --output only')
            result=home_backup.create(args.data_dir or ROOT/'.local/home',args.output)
        else:
            if not args.backup or args.output or args.data_dir:parser.error('Use --backup and, for restore, --destination')
            if args.action=='restore':
                if not args.destination:parser.error('restore needs a NEW --destination')
                result=home_backup.restore(args.backup,args.destination)
            else:
                if args.destination:parser.error('verify-backup does not use a destination')
                result=home_backup.verify(args.backup)
        print(json.dumps(result,sort_keys=True));return
    if args.output or args.backup or args.destination:parser.error('Backup arguments apply only to backup commands')
    if args.action in ('status','stop-demo'):
        from demo_control import status, stop_demo
        result=(status if args.action=='status' else stop_demo)(args.web_port,args.data_dir)
        print(json.dumps(result,sort_keys=True))
        return
    if args.data_dir is not None or args.web_port!=8878: parser.error('Port/data directory options apply only to status/stop-demo')
    if args.action == 'check':
        print('System:', platform.system(), platform.machine(), platform.mac_ver()[0] or platform.release())
        print('Python:', platform.python_version())
        if sys.version_info[:2] not in SUPPORTED: raise ValueError('Supported Python: 3.12, 3.13 and 3.14')
    elif args.action == 'ports':
        ports = serial_ports()
        print('Detected serial ports (none opened):')
        for port in ports: print(port['port'] + ' | ' + port['description'])
        if not ports: print('No serial ports detected.')
    elif args.action == 'setup': setup()
    elif args.action == 'verify': verify(); print('Managed home environment verified.')
    else: update()


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print('Home setup stopped: ' + str(error), file=sys.stderr); raise SystemExit(1)
