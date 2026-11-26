"""Compile and execute the firmware's actual read helpers on fake register buses."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

COMPILER = shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')


class CheckedReadTests(unittest.TestCase):
    def test_native_transfer_failure_configuration_and_unit_cases(self):
        if not COMPILER:
            if os.environ.get('GITHUB_ACTIONS') == 'true' and os.name != 'nt':
                self.fail('CI requires a native C++ compiler for checked sensor fixtures')
            self.skipTest('No local C++ compiler; Linux/Intel Mac CI must execute these fixtures')
        fixture = Path(__file__).resolve().parent/'fixtures/checked_sensor_reads.cpp'
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/('checked-read.exe' if os.name == 'nt' else 'checked-read')
            build = subprocess.run([COMPILER, '-std=c++11', '-Wall', '-Wextra', '-Werror',
                                    str(fixture), '-o', str(binary)], capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stdout+build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            self.assertIn('no hardware used', run.stdout)
