"""Fixed-parts scope and truthful physical state; no bench operation is performed."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fastapi import HTTPException
import physical_build
import test_acquisition_registry as fixtures

ROOT=Path(__file__).resolve().parents[1]


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
