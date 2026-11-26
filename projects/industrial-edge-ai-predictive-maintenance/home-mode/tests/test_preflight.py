"""Shell preflight fixtures; simulated host metadata, never Mac acceptance."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]


def bash_path(value):
    path=Path(value).resolve().as_posix()
    if os.name=='nt':return '/'+path[0].lower()+path[2:]
    return path


class PreflightTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            bash=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git/bin/bash.exe'
            if not bash.is_file():self.skipTest('Git Bash unavailable; POSIX CI covers the shell')
            self.bash=str(bash)
        else:
            self.bash=shutil.which('bash')
            if not self.bash:self.skipTest('Bash unavailable')
        self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
        self.project=self.directory/'project';self.project.mkdir()
        shutil.copy2(ROOT/'home_preflight.command',self.project/'home_preflight.command')
        self.tools=self.directory/'tools';self.tools.mkdir()
        self.write_tool('uname','case "$1" in -s) echo Darwin ;; *) echo x86_64 ;; esac')
        self.write_tool('sw_vers','echo 12.7.6-fixture')
        self.write_tool('sysctl','case "$2" in hw.model) echo MacBookAir7,2-fixture ;; *) echo 4294967296 ;; esac')
        self.write_tool('git','echo executed > git-executed.txt; echo "Git must not be executed by preflight" >&2; exit 97')
    def tearDown(self):
        if hasattr(self,'tmp'):self.tmp.cleanup()
    def write_tool(self,name,body):
        file=self.tools/name;file.write_text('#!/bin/bash\n'+body+'\n',encoding='utf-8');file.chmod(0o700)
    def snapshot(self):
        return {p.relative_to(self.project).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.project.rglob('*') if p.is_file()}
    def run_report(self):
        env=dict(os.environ);env.pop('BASH_ENV',None);env.pop('ENV',None)
        args=[self.bash,'-c','export PATH="$1:/usr/bin:/bin"; exec /bin/bash "$2"','preflight-fixture',bash_path(self.tools),bash_path(self.project/'home_preflight.command')]
        return subprocess.run(args,env=env,cwd=self.directory,capture_output=True,text=True)
    def test_report_is_read_only_and_python_probe_uses_isolated_interpreter(self):
        python=bash_path(sys.executable)
        self.write_tool('python3.14','[ "$1 $2 $3" = "-I -S -B" ] || exit 98\nexec "'+python+'" "$@"')
        private=self.project/'.local';private.mkdir();(private/'preserve.txt').write_text('keep',encoding='utf-8')
        before=self.snapshot();result=self.run_report()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('12.7.6-fixture',result.stdout);self.assertIn('4096 MiB',result.stdout)
        self.assertIn('Supported interpreter found: '+sys.version.split()[0],result.stdout)
        self.assertIn('Physical verification remains PENDING',result.stdout)
        self.assertNotIn('Git must not be executed',result.stderr);self.assertEqual(self.snapshot(),before)
    def test_missing_python_is_reported_without_installing_or_creating_environment(self):
        before=self.snapshot();result=self.run_report()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Supported interpreter not found',result.stdout)
        self.assertIn('Home environment not prepared',result.stdout)
        self.assertEqual(self.snapshot(),before);self.assertFalse((self.project/'.venv-home').exists())
    def test_other_hosts_refused_before_system_checks(self):
        self.write_tool('uname','echo Linux')
        self.write_tool('sw_vers','echo "Should not execute" >&2; exit 99')
        before=self.snapshot();result=self.run_report()
        self.assertEqual(result.returncode,1);self.assertIn('Office Windows',result.stdout)
        self.assertNotIn('Should not execute',result.stderr);self.assertEqual(self.snapshot(),before)


if __name__=='__main__':unittest.main()
