from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
import io
import os
from unittest.mock import patch
import release_bundle


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        # Disposable local-only repositories: avoid inherited tool Git config and
        # Windows patch.dict restoration of empty native environment values.
        environment=patch.dict(os.environ,{"GIT_CONFIG_COUNT":"0"});environment.start();self.addCleanup(environment.stop)

    def fixture(self,root):
        subprocess.run(['git','init','-q',str(root)],check=True,capture_output=True)
        for name,data in [('app.py',b'print("fixture only")\n'),('.env',b'PRIVATE=not-for-release'),('private.key',b'not-a-real-key'),('.env.example',b'PRIVATE=\n'),('.gitignore',b'.local/\n'),('data.sqlite3',b'not-a-real-db')]:
            (root/name).write_bytes(data)
        subprocess.run(['git','-C',str(root),'add','--','.'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Disposable release fixture'],check=True,capture_output=True)

    def test_deterministic_source_only_package_and_new_folder_unpack(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'repo';root.mkdir();self.fixture(root)
            raw,manifest=release_bundle.build(root);again,_=release_bundle.build(root);self.assertEqual(raw,again)
            files=set(manifest['files']);self.assertIn('project/.env.example',files);self.assertIn('project/.gitignore',files)
            self.assertNotIn('project/.env',files);self.assertNotIn('project/private.key',files);self.assertNotIn('project/data.sqlite3',files)
            release_bundle.verify(raw)
            subprocess.run(['git','-C',str(root),'config','core.autocrlf','true'],check=True,capture_output=True)
            (root/'app.py').write_bytes(b'print("fixture only")\r\n')
            subprocess.run(['git','-C',str(root),'add','--','app.py'],check=True,capture_output=True)
            canonical,_=release_bundle.build(root);self.assertEqual(canonical,raw,'Archive uses committed bytes, not platform checkout newlines')
            out=Path(temporary)/'install';result=release_bundle.unpack(raw,out);self.assertFalse(result['deployment_performed']);self.assertTrue((out/'project/app.py').is_file())
            with self.assertRaises(FileExistsError):release_bundle.unpack(raw,out)
            (root/'app.py').write_bytes(b'local edits preserved')
            with self.assertRaises(ValueError):release_bundle.build(root)
            self.assertEqual((root/'app.py').read_bytes(),b'local edits preserved')

    def test_rehashed_or_unknown_members_require_exact_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.fixture(root);raw,_=release_bundle.build(root)
            stream=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(raw)) as original,zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as changed:
                for item in original.infolist():changed.writestr(item,original.read(item))
                changed.writestr('../outside.txt',b'not allowed')
            with self.assertRaises(ValueError):release_bundle.verify(stream.getvalue())
