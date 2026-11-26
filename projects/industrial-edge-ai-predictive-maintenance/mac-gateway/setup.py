"""Small Python-only setup. No Docker, Homebrew, sudo or automatic hardware access."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys
import venv

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--portal',action='store_true');args=parser.parse_args()
    print('System:',platform.system(),platform.machine(),platform.mac_ver()[0] or platform.release())
    print('Python:',platform.python_version())
    if not (3,11)<=sys.version_info[:2]<=(3,13):raise SystemExit('Use Python 3.11, 3.12 or 3.13. Python 3.12 is the CI reference. Do not replace the system Python.')
    if args.check:return
    target=ROOT/('.venv-portal' if args.portal else '.venv-gateway')
    python=target/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if not python.exists():venv.EnvBuilder(with_pip=True).create(target)
    result=subprocess.run([str(python),'-c','import sys; print("%s.%s"%sys.version_info[:2])'],capture_output=True,text=True,check=True)
    if result.stdout.strip() not in ('3.11','3.12','3.13'):raise SystemExit('Existing environment uses an unsupported Python; choose a fresh clone or a matching environment.')
    requirements=ROOT/('dashboard/requirements.txt' if args.portal else 'mac-gateway/requirements.txt')
    subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(requirements)],check=True)
    print('Setup complete. No serial port opened, firmware flashed, hosting created or credentials saved.')
    if args.portal:print('Next: bash start_local_portal.command')
    else:print('Next: bash configure_gateway.command after a portal URL and scoped token are available.')


if __name__=='__main__':main()
