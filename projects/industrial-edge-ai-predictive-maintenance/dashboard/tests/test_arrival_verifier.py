"""Disposable unopened-pack corruption checks; no extraction, service or hardware."""
import csv
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from unittest.mock import patch

import hardware_handover
import verify_arrival_pack as verifier

ROOT=Path(__file__).resolve().parents[1]


class ArrivalVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=hardware_handover.build_pack(ROOT)
        with zipfile.ZipFile(io.BytesIO(cls.raw)) as archive:cls.files={name:archive.read(name) for name in archive.namelist()}

    def repack(self,changes=None,rehash=False,extra=None):
        files=dict(self.files);files.update(changes or {})
        if rehash:
            manifest=json.loads(files['manifest.json'])
            manifest['files']={name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in files.items() if name!='manifest.json'}
            files['manifest.json']=json.dumps(manifest).encode()
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in files.items():archive.writestr(name,data)
            if extra:archive.writestr(*extra)
        return output.getvalue()

    def test_real_generated_pack_passes_with_all_physical_authority_false(self):
        report=verifier.verify_bytes(self.raw)
        self.assertEqual(report['file_consistency'],'passed')
        self.assertEqual(report['files_checked'],len(verifier.EXPECTED_FILES)-1)
        self.assertEqual(report['archive_sha256'],hashlib.sha256(self.raw).hexdigest())
        for key in ('signature_verified','source_authenticity_verified','physical_acceptance_verified','hardware_connected','equipment_authorized','production_ready'):self.assertIs(report[key],False)
        self.assertEqual(self.files['dashboard/verify_arrival_pack.py'],(ROOT/'verify_arrival_pack.py').read_bytes())

    def test_changed_file_and_forged_manifest_size_or_hash_are_rejected(self):
        with self.assertRaises(verifier.PackError):verifier.verify_bytes(self.repack({'START-HERE.md':b'changed'}))
        for key,value in [('bytes',True),('bytes',123),('sha256','0'*64),('sha256','bad')]:
            manifest=json.loads(self.files['manifest.json']);manifest['files']['START-HERE.md'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(verifier.PackError):verifier.verify_bytes(self.repack({'manifest.json':json.dumps(manifest).encode()}))

    def test_missing_duplicate_extra_and_traversal_entries_are_rejected(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            for name,data in self.files.items():
                if name!='START-HERE.md':archive.writestr(name,data)
        with self.assertRaises(verifier.PackError):verifier.verify_bytes(output.getvalue())
        for name in ('START-HERE.md','unexpected.txt','../outside.txt','/absolute.txt','C:\\outside.txt'):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                raw=self.repack(extra=(name,b'unexpected'))
            with self.subTest(name=name),self.assertRaises(verifier.PackError):verifier.verify_bytes(raw)

    def test_symbolic_link_entry_is_rejected_without_extraction(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            for name,data in self.files.items():
                info=zipfile.ZipInfo(name)
                if name=='START-HERE.md':info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
                archive.writestr(info,data)
        with self.assertRaises(verifier.PackError):verifier.verify_bytes(output.getvalue())

    def test_archive_member_manifest_and_expanded_limits_are_enforced(self):
        for limit in ('MAX_ARCHIVE','MAX_FILE','MAX_MANIFEST','MAX_TOTAL'):
            with self.subTest(limit=limit),patch.object(verifier,limit,8),self.assertRaises(verifier.PackError):verifier.verify_bytes(self.raw)

    def test_malformed_duplicate_and_deep_json_are_sanitized(self):
        for raw in (b'{',b'null',b'[]',b'{"format":"a","format":"b"}',b'['*1100+b']'*1100,b'\xff'):
            with self.subTest(raw=raw[:25]),self.assertRaises(verifier.PackError):verifier.verify_bytes(self.repack({'manifest.json':raw}))

    def test_manifest_authority_and_membership_cannot_be_upgraded(self):
        for key,value in [('hardware_connected',True),('production_ready',True),('received_count_verified',1),('received_count_verified',False),('ordered_count_user_reported',31),('format','other'),('files',[])]:
            manifest=json.loads(self.files['manifest.json']);manifest[key]=value
            with self.subTest(key=key),self.assertRaises(verifier.PackError):verifier.verify_bytes(self.repack({'manifest.json':json.dumps(manifest).encode()}))

    def test_rehashed_plan_still_must_match_all_matrix_fields_and_scope(self):
        for key in ('selected_family','quantity_basis','role','connection','pending'):
            plan=json.loads(self.files['physical-plan.json']);plan['rows'][0][key]='Changed but rehashed'
            with self.subTest(key=key),self.assertRaises(verifier.PackError):verifier.verify_bytes(self.repack({'physical-plan.json':json.dumps(plan).encode()},True))
        for key,value in [('scope','production'),('hardware_connected',True),('rows',[]),('pins',{}),('order_reported_on','invalid')]:
            plan=json.loads(self.files['physical-plan.json']);plan[key]=value
            with self.subTest(key=key),self.assertRaises(verifier.PackError):verifier.verify_bytes(self.repack({'physical-plan.json':json.dumps(plan).encode()},True))

    def test_rehashed_matrix_or_map_cannot_bypass_plan_references(self):
        for name in ('phase-01-hardware/docs/physical-connection-pack/all-30-connection-matrix.csv','phase-01-hardware/docs/physical-connection-pack/sensor-only-reference.svg'):
            with self.subTest(name=name),self.assertRaises(verifier.PackError):verifier.verify_bytes(self.repack({name:self.files[name]+b' changed'},True))

    def test_modified_or_reordered_worksheet_is_not_an_unopened_template(self):
        rows=list(csv.reader(io.StringIO(self.files['receipt-worksheet.csv'].decode('utf-8-sig'))))
        for kind in ('model','reordered','scope'):
            changed=[list(row) for row in rows]
            if kind=='model':changed[1][5]='Owner note in edited worksheet'
            elif kind=='reordered':changed[1],changed[2]=changed[2],changed[1]
            else:changed.pop()
            output=io.StringIO(newline='');csv.writer(output).writerows(changed)
            with self.subTest(kind=kind),self.assertRaises(verifier.PackError):verifier.verify_bytes(self.repack({'receipt-worksheet.csv':output.getvalue().encode('utf-8-sig')},True))

    def test_corrupt_or_truncated_zip_is_refused(self):
        for raw in (b'',b'not a zip',self.raw[:40],self.raw[:-40]):
            with self.subTest(size=len(raw)),self.assertRaises(verifier.PackError):verifier.verify_bytes(raw)

    def test_cli_runs_standalone_and_never_extracts_or_changes_input(self):
        with tempfile.TemporaryDirectory(prefix='edgeops-arrival-verifier-') as temp:
            folder=Path(temp);archive=folder/'arrival.zip';archive.write_bytes(self.raw)
            command=[sys.executable,'-I',str(ROOT/'verify_arrival_pack.py')]
            result=subprocess.run([*command,str(archive)],cwd=folder,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['file_consistency'],'passed')
            self.assertEqual(archive.read_bytes(),self.raw);self.assertEqual(list(folder.iterdir()),[archive])
            archive.write_bytes(b'corrupt')
            for path in (archive,folder/'missing.zip'):
                result=subprocess.run([*command,str(path)],cwd=folder,capture_output=True,text=True)
                self.assertEqual(result.returncode,2,result.stderr)
                self.assertEqual(json.loads(result.stdout)['file_consistency'],'failed')
                self.assertNotIn(str(folder),result.stdout)
            self.assertEqual(archive.read_bytes(),b'corrupt');self.assertEqual(list(folder.iterdir()),[archive])
