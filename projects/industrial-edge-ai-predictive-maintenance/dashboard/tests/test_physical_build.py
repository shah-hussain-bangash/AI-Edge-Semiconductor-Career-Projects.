"""Fixed-parts scope and truthful physical state; no bench operation is performed."""
import csv
import hashlib
import io
import json
import copy
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from fastapi import HTTPException
import physical_build
import hardware_handover
import test_acquisition_registry as fixtures

ROOT=Path(__file__).resolve().parents[1]


def preparation_fixture(base):
    project=base/'project';root=project/'dashboard';root.mkdir(parents=True)
    for source,destination in [(ROOT/'physical-build-plan.json',root/'physical-build-plan.json'),
                               (ROOT/'physical-sensor-map.svg',root/'physical-sensor-map.svg'),
                               (ROOT.parent/physical_build.MATRIX_NAME,project/physical_build.MATRIX_NAME),
                               (ROOT.parent/physical_build.MAP_NAME,project/physical_build.MAP_NAME)]:
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(source.read_bytes())
    return root


class PreparationSourceConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='edgeops-preparation-source-');self.addCleanup(self.temp.cleanup)
        self.root=preparation_fixture(Path(self.temp.name))
        self.plan=json.loads((self.root/'physical-build-plan.json').read_bytes())

    def write(self,plan):
        (self.root/'physical-build-plan.json').write_text(json.dumps(plan),encoding='utf-8')

    def refused(self):
        with self.assertRaises(HTTPException) as result:physical_build.read_plan(self.root)
        self.assertEqual(result.exception.status_code,503)
        self.assertEqual(result.exception.detail,'Physical preparation plan is unavailable; no connection instructions returned')

    def test_all_five_row_fields_must_equal_matrix_even_with_valid_shape_and_hash(self):
        for field in physical_build.ROW_FIELDS:
            with self.subTest(field=field):
                plan=copy.deepcopy(self.plan);plan['rows'][0][field]='A structurally valid but inconsistent note';self.write(plan);self.refused()

    def test_unsupported_shapes_blank_fields_scope_hashes_and_declarations_are_sanitized(self):
        variants=[None,[],{'rows':None},dict(self.plan,rows=[None]*30),dict(self.plan,rows='invalid'),
                  dict(self.plan,scope='production'),dict(self.plan,source_csv_sha256='bad'),
                  dict(self.plan,sensor_map_sha256=1),dict(self.plan,order_reported_on='2026-99-99'),
                  dict(self.plan,source_hash_basis='unknown')]
        for field in physical_build.ROW_FIELDS:
            for value in ('   ',None,[],200):
                plan=copy.deepcopy(self.plan);plan['rows'][0][field]=value;variants.append(plan)
        for plan in variants:
            with self.subTest(plan=plan):self.write(plan);self.refused()
        for raw in (b'{"rows":[],"rows":[]}',b'\xff',b'{',b'['*1100+b']'*1100):
            (self.root/'physical-build-plan.json').write_bytes(raw);self.refused()

    def test_matrix_change_and_reordered_or_mismatched_rows_are_refused(self):
        matrix=self.root.parent/physical_build.MATRIX_NAME;original=matrix.read_bytes()
        matrix.write_bytes(original.replace(b'Edge computer',b'Changed role'));self.refused()
        # A matching digest alone cannot legitimize disagreement with the exact plan rows.
        plan=copy.deepcopy(self.plan);plan['source_csv_sha256']=hashlib.sha256(matrix.read_bytes().replace(b'\r\n',b'\n')).hexdigest();self.write(plan);self.refused()
        matrix.write_bytes(original);plan=copy.deepcopy(self.plan);plan['rows'].reverse();self.write(plan);self.refused()

    def test_map_must_match_hash_and_independent_source_copy(self):
        local=self.root/'physical-sensor-map.svg';original=local.read_bytes()
        local.write_bytes(original+b' changed');self.refused()
        plan=copy.deepcopy(self.plan);plan['sensor_map_sha256']=hashlib.sha256(local.read_bytes()).hexdigest();self.write(plan);self.refused()
        local.write_bytes(original);self.write(self.plan)
        (self.root.parent/physical_build.MAP_NAME).write_bytes(original+b' changed');self.refused()

    def test_missing_oversized_linked_and_outside_sources_are_refused(self):
        for limit in ('MAX_PLAN_BYTES','MAX_MATRIX_BYTES','MAX_MAP_BYTES'):
            with self.subTest(limit=limit),patch.object(physical_build,limit,8):self.refused()
        with patch.object(Path,'is_symlink',return_value=True):self.refused()
        with self.assertRaises(ValueError):physical_build._read_source(Path(self.temp.name)/'outside',self.root.parent,100)
        (self.root.parent/physical_build.MATRIX_NAME).unlink();self.refused()

    def test_crlf_matrix_and_exact_map_bytes_preserve_successful_read(self):
        matrix=self.root.parent/physical_build.MATRIX_NAME
        matrix.write_bytes(matrix.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        plan,sensor_map=physical_build.read_preparation(self.root)
        self.assertEqual(plan['rows'],self.plan['rows'])
        self.assertEqual(sensor_map,(self.root/'physical-sensor-map.svg').read_bytes())
        self.assertEqual(plan['plan_sha256'],hashlib.sha256((self.root/'physical-build-plan.json').read_bytes()).hexdigest())


class PhysicalPlanTests(unittest.TestCase):
    def test_same_30_parts_and_firmware_map_match_source(self):
        data=physical_build.read_plan(ROOT)
        source=ROOT/'../phase-01-hardware/docs/physical-connection-pack/all-30-connection-matrix.csv'
        with source.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        self.assertEqual([row['selected_family'] for row in data['rows']],[row['GitHub part/family'] for row in rows])
        self.assertEqual(data['source_csv_sha256'],hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest())
        self.assertEqual(data['sensor_map_sha256'],hashlib.sha256((ROOT/'physical-sensor-map.svg').read_bytes()).hexdigest())
        self.assertFalse(data['additional_hardware_allowed']);self.assertFalse(data['substitution_allowed'])
        self.assertFalse(data['order_verified']);self.assertFalse(data['hardware_connected'])

    def test_invalid_or_expanded_plan_is_not_presented_as_connection_guidance(self):
        with tempfile.TemporaryDirectory(prefix='edgeops-build-plan-') as temp:
            path=Path(temp)
            for change in ('extra','connected','replacement'):
                data=physical_build.read_plan(ROOT)
                if change=='extra':data['rows'].append(data['rows'][0])
                if change=='connected':data['hardware_connected']=True
                if change=='replacement':data['substitution_allowed']=True
                (path/'physical-build-plan.json').write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(HTTPException) as context:physical_build.read_plan(path)
                self.assertEqual(context.exception.status_code,503)


class PhysicalPlanApiTests(unittest.TestCase):
    login=fixtures.AcquisitionRegistryApiTests.login
    post=fixtures.AcquisitionRegistryApiTests.post
    def setUp(self):fixtures.AcquisitionRegistryApiTests.setUp(self)

    def test_all_read_routes_refuse_real_inconsistent_sources_without_partial_content(self):
        with tempfile.TemporaryDirectory(prefix='edgeops-source-api-') as temp:
            root=preparation_fixture(Path(temp));plan=json.loads((root/'physical-build-plan.json').read_bytes())
            plan['rows'][0]['connection']='Inconsistent private note must not be returned'
            (root/'physical-build-plan.json').write_text(json.dumps(plan),encoding='utf-8')
            original=physical_build.read_preparation
            with patch.object(physical_build,'read_preparation',side_effect=lambda _:original(root)):
                for suffix in ('','/sensor-map','/arrival-pack'):
                    response=self.http.get('/api/hardware/physical-plan'+suffix)
                    self.assertEqual(response.status_code,503)
                    self.assertIn('application/json',response.headers['content-type'])
                    self.assertNotIn('Inconsistent private note',response.text)
                    self.assertNotIn('<svg',response.text)

    def test_plan_and_map_are_uncached_and_map_returns_exact_checked_snapshot(self):
        plan,sensor_map=physical_build.read_preparation(ROOT)
        response=self.http.get('/api/hardware/physical-plan')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json(),plan)
        self.assertEqual(response.headers['cache-control'],'no-store')
        with patch.object(physical_build,'read_preparation',return_value=(plan,sensor_map)) as checked:
            with patch.object(physical_build,'_read_source',side_effect=AssertionError('Must not reopen checked file')):
                response=self.http.get('/api/hardware/physical-plan/sensor-map')
        checked.assert_called_once()
        self.assertEqual(response.status_code,200);self.assertEqual(response.content,sensor_map)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(response.headers['x-content-type-options'],'nosniff')

    def test_arrival_pack_is_authenticated_fixed_scope_and_contains_no_runtime_data(self):
        for role in ('admin','operator','auditor'):
            self.login(role)
            response=self.http.get('/api/hardware/physical-plan/arrival-pack')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertIn('edgeops-hardware-arrival-pack.zip',response.headers['content-disposition'])
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                expected=set(hardware_handover.SOURCE_FILES)|{'receipt-worksheet.csv','physical-plan.json','START-HERE.md','manifest.json'}
                self.assertEqual(set(archive.namelist()),expected)
                manifest=json.loads(archive.read('manifest.json'))
                self.assertFalse(manifest['hardware_connected']);self.assertFalse(manifest['production_ready'])
                self.assertEqual(manifest['received_count_verified'],0)
                for name,entry in manifest['files'].items():
                    content=archive.read(name)
                    self.assertEqual(entry,{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
                rows=list(csv.DictReader(io.StringIO(archive.read('receipt-worksheet.csv').decode('utf-8-sig'))))
                self.assertEqual([row['Product ID'] for row in rows],[f'P{i:02}' for i in range(1,31)])
                self.assertTrue(all(row['Actual received model / board revision']=='' and row['Record status']=='awaiting-delivery-unverified' for row in rows))
                self.assertEqual(archive.read('phase-01-hardware/scripts/capture_serial.py'),(ROOT/'../phase-01-hardware/scripts/capture_serial.py').read_bytes())
        self.http.cookies.clear()
        self.assertEqual(self.http.get('/api/hardware/physical-plan/arrival-pack').status_code,401)

    def test_pack_failure_never_returns_a_partial_archive(self):
        with patch.object(hardware_handover,'SOURCE_FILES',('phase-01-hardware/nonexistent-source',)):
            response=self.http.get('/api/hardware/physical-plan/arrival-pack')
            self.assertEqual(response.status_code,503)
            self.assertIn('application/json',response.headers['content-type'])

    def test_order_report_is_separate_from_physical_verification_and_plan_is_read_only(self):
        for role in ('admin','operator','auditor'):
            self.login(role)
            catalog=self.http.get('/api/hardware').json()
            self.assertEqual(catalog['ordered_count_user_reported'],30)
            self.assertTrue(all(row['lifecycle']=='ordered-user-reported' and not row['connected'] and not row['purchase_verified'] for row in catalog['devices']))
            plan=self.http.get('/api/hardware/physical-plan').json()
            self.assertEqual(len(plan['rows']),30);self.assertFalse(plan['production_ready'])
            self.assertEqual(self.http.get('/api/hardware/physical-plan/sensor-map').status_code,200)
            self.assertEqual(self.post('/api/hardware/physical-plan',{'hardware_connected':True}).status_code,405)
        self.http.cookies.clear()
        self.assertEqual(self.http.get('/api/hardware/physical-plan').status_code,401)
        self.assertEqual(self.http.get('/api/hardware/physical-plan/sensor-map').status_code,401)


class ArrivalPackIntegrityTests(unittest.TestCase):
    def test_map_changed_after_initial_plan_check_cannot_enter_pack(self):
        original=Path.open;count=0;source_map=(ROOT.parent/physical_build.MAP_NAME).resolve()
        def read(path,*args,**kwargs):
            nonlocal count
            if path.resolve()==source_map:
                count+=1
                if count>1:return io.BytesIO(b'<svg>Changed after validation</svg>')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',read),self.assertRaises(HTTPException) as result:hardware_handover.build_pack(ROOT)
        self.assertEqual(result.exception.status_code,503)

    def test_changed_matrix_and_source_outside_project_are_refused(self):
        with patch.object(hardware_handover,'read_plan',return_value=dict(physical_build.read_plan(ROOT),source_csv_sha256='0'*64)):
            with self.assertRaises(HTTPException) as result:hardware_handover.build_pack(ROOT)
            self.assertEqual(result.exception.status_code,503)
        with patch.object(hardware_handover,'SOURCE_FILES',('../outside.txt',)):
            with self.assertRaises(HTTPException) as result:hardware_handover.build_pack(ROOT)
            self.assertEqual(result.exception.status_code,503)
