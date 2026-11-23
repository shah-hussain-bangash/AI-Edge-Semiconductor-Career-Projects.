"""Offline synthetic fixtures only; no serial ports or hardware are accessed."""
import csv
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load('prepare_capture', ROOT / 'scripts/prepare_capture.py')
serial_capture = load('serial_capture', ROOT / 'scripts/capture_serial.py')
contract = load('v2_contract', ROOT.parent / 'enterprise-architecture/contracts/tests/test_telemetry_v2_contract.py')
MAPPING = dict(profile='edgeops.serial-attachment.v1', site_id='synthetic-lab', asset_id='fixture-motor',
               device_id='fixture-esp32', v1_device_id='motor-001', serial_port='NOT-CONNECTED',
               board_reference='synthetic-fixture', configuration_ref='fixture-only', source_type='synthetic',
               physical_verification='unverified', calibration='not_verified', transport='usb-serial')
ROW = dict(zip(adapter.FIELDS, ['2026-11-20T10:00:00+00:00', 'motor-001', '1', '1000',
                              '0', '-0.2', '9.8', '25', '12', '125', 'True', 'True', 'True', 'True']))


def capture(rows, fields=adapter.FIELDS):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


class PrepareCaptureTests(unittest.TestCase):
    def test_fragmented_capture_to_evidence_handoff(self):
        import contextlib
        values = {key: value for key, value in ROW.items() if key != 'gateway_utc'}
        for key in ('seq', 'uptime_ms'): values[key] = int(values[key])
        for key in serial_capture.NUMERIC: values[key] = float(values[key])
        for key in ('adxl345_valid', 'ds18b20_valid', 'ina219_valid', 'valid'): values[key] = values[key] == 'True'
        values['schema_version'] = 1
        raw = (json.dumps(values) + '\n').encode()
        chunks = [raw[:20], b'', raw[20:]]
        class Port:
            def readline(self, size): return chunks.pop(0)
        ticks = iter([0, 0, 0, 0, 99])
        stream = io.StringIO(newline='')
        with contextlib.redirect_stdout(io.StringIO()):
            serial_capture.capture_stream(Port(), stream, 1, monotonic=lambda: next(ticks), receipt=lambda: ROW['gateway_utc'])
        records, rejected, _, _ = adapter.normalize(stream.getvalue().encode(), MAPPING)
        self.assertEqual(rejected, [])
        self.assertEqual(contract.failures(records[0]), [])
        self.assertEqual(records[0]['measurements']['current_a'], 0.125)

    def test_units_zero_and_provenance_match_contract(self):
        result, _ = adapter.convert(ROW, MAPPING)
        self.assertEqual(result['measurements']['current_a'], 0.125)
        self.assertEqual(result['measurements']['acceleration_x_mps2'], 0)
        self.assertIsNone(result['boot_id'])
        self.assertIsNone(result['timestamp']['device_time_utc'])
        self.assertEqual(contract.failures(result), [])

    def test_invalid_groups_are_null_and_valid_zero_survives(self):
        for sensor in ('adxl345', 'ds18b20', 'ina219'):
            row = dict(ROW, **{sensor + '_valid': 'False', 'valid': 'False'})
            result, _ = adapter.convert(row, MAPPING)
            self.assertEqual(contract.failures(result), [])
            for field in contract.CHANNELS[sensor]:
                self.assertIsNone(result['measurements'][field])
        result, _ = adapter.convert(dict(ROW, current_ma='0'), MAPPING)
        self.assertEqual(result['measurements']['current_a'], 0)

    def test_malformed_values_are_quarantined(self):
        for key, value in [('current_ma', 'NaN'), ('current_ma', '1_000'), ('current_ma', '1e999'),
                           ('seq', '-1'), ('seq', '4294967296'), ('uptime_ms', '1.0'),
                           ('valid', 'false'), ('valid', 'False'), ('device_id', 'unknown'),
                           ('gateway_utc', '2026-11-20T10:00:00')]:
            with self.subTest(key=key, value=value):
                accepted, rejected, _, count = adapter.normalize(capture([dict(ROW, **{key: value})]), MAPPING)
                self.assertEqual((accepted, len(rejected), count), ([], 1, 1))

    def test_reset_duplicate_and_clock_regression_latch_quarantine(self):
        for changes in ({'seq': '1'}, {'seq': '2', 'uptime_ms': '999'},
                        {'seq': '2', 'gateway_utc': '2026-11-20T09:59:59Z'}):
            rows = [ROW, dict(ROW, **changes), dict(ROW, seq='3', uptime_ms='3000')]
            accepted, rejected, _, _ = adapter.normalize(capture(rows), MAPPING)
            self.assertEqual((len(accepted), len(rejected)), (1, 2))
            self.assertTrue(all('discontinuity' in item['reason'] for item in rejected))

    def test_gaps_are_counted_without_inventing_boot_identity(self):
        accepted, rejected, gaps, _ = adapter.normalize(capture([ROW, dict(ROW, seq='4', uptime_ms='4000')]), MAPPING)
        self.assertEqual((len(accepted), rejected, gaps), (2, [], 2))
        self.assertTrue(all(item['boot_id'] is None for item in accepted))

    def test_exact_header_and_row_shape(self):
        for raw in (b'bad,header\n1,2\n', capture([ROW]).replace(b'gateway_utc,', b'seq,', 1)):
            with self.assertRaises(ValueError):
                adapter.normalize(raw, MAPPING)
        accepted, rejected, _, _ = adapter.normalize(capture([ROW]).rstrip() + b',extra\n', MAPPING)
        self.assertEqual((accepted, len(rejected)), ([], 1))

    def test_attachment_cannot_assert_physical_or_calibration_verification(self):
        for changes in ({'physical_verification': 'verified'}, {'calibration': 'verified'},
                        {'source_type': 'automatic'}, {'extra': 'field'}):
            with self.assertRaises(ValueError):
                adapter.attachment(dict(MAPPING, **changes))
        for declared in ('measured', 'replayed'):
            item, _ = adapter.convert(ROW, adapter.attachment(dict(MAPPING, source_type=declared)))
            self.assertEqual(contract.failures(item), [])
            self.assertEqual(item['quality']['session_quality'], 'unavailable')

    def package(self, root, rows):
        source = root / 'capture.csv'; source.write_bytes(capture(rows))
        mapping = root / 'mapping.json'; mapping.write_bytes(adapter.json_bytes(MAPPING))
        destination = root / 'evidence'
        manifest = adapter.prepare(source, mapping, destination)
        return source, mapping, destination, manifest

    def test_package_reconciles_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            source, mapping, destination, manifest = self.package(Path(temp), [ROW])
            self.assertEqual(adapter.verify(destination), manifest)
            self.assertFalse(manifest['production_ready'])
            before = (destination / 'manifest.json').read_bytes()
            with self.assertRaises(ValueError):
                adapter.prepare(source, mapping, destination)
            self.assertEqual((destination / 'manifest.json').read_bytes(), before)

    def test_tamper_and_rehashed_transformation_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, destination, manifest = self.package(Path(temp), [ROW])
            file = destination / 'observations.jsonl'
            record = json.loads(file.read_bytes()); record['measurements']['current_a'] = 999
            file.write_bytes(adapter.json_bytes(record))
            with self.assertRaises(ValueError): adapter.verify(destination)
            manifest['files'][file.name] = {'bytes': file.stat().st_size, 'sha256': adapter.sha(file.read_bytes())}
            (destination / 'manifest.json').write_bytes(adapter.json_bytes(manifest))
            with self.assertRaises(ValueError): adapter.verify(destination)

    def test_empty_input_requires_review(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, _, manifest = self.package(Path(temp), [])
            self.assertTrue(manifest['requires_review'])
            self.assertEqual(manifest['accepted_rows'], 0)

    def rehash(self, destination, manifest, name, raw):
        (destination / name).write_bytes(raw)
        manifest['files'][name] = {'bytes': len(raw), 'sha256': adapter.sha(raw)}
        (destination / 'manifest.json').write_bytes(adapter.json_bytes(manifest))

    def test_manifest_rejects_boolean_float_and_unsupported_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, destination, original = self.package(Path(temp), [ROW])
            for key, value in [('input_rows', True), ('input_rows', 1.0), ('accepted_rows', True),
                               ('quarantined_rows', False), ('accepted_sequence_gaps', False),
                               ('accepted_sequence_gaps', -1), ('accepted_sequence_gaps', 4294967296),
                               ('requires_review', 0), ('files', []), ('files', None),
                               ('created_at', '2026-02-31T00:00:00Z'),
                               ('created_at', '2026-11-20T10:00:00+01:00'),
                               ('extra', 'unsupported')]:
                with self.subTest(key=key, value=value):
                    changed = dict(original, **{key: value})
                    (destination / 'manifest.json').write_bytes(adapter.json_bytes(changed))
                    with self.assertRaises(ValueError): adapter.verify(destination)
            for reference in ({'bytes': False, 'sha256': original['files']['quarantine.jsonl']['sha256']},
                              {'bytes': 0.0, 'sha256': original['files']['quarantine.jsonl']['sha256']},
                              {'bytes': 0, 'sha256': 'A' * 64}, {'bytes': 0, 'sha256': 'bad'},
                              {'bytes': 0, 'sha256': original['files']['quarantine.jsonl']['sha256'], 'extra': False}):
                changed = json.loads(json.dumps(original)); changed['files']['quarantine.jsonl'] = reference
                (destination / 'manifest.json').write_bytes(adapter.json_bytes(changed))
                with self.assertRaises(ValueError): adapter.verify(destination)

    def test_rehashed_boolean_observations_cannot_equal_numbers(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, destination, manifest = self.package(Path(temp), [ROW])
            original = (destination / 'observations.jsonl').read_bytes()
            for field in ('sequence', 'acceleration_x_mps2'):
                record = json.loads(original)
                if field == 'sequence': record[field] = True
                else: record['measurements'][field] = False
                self.rehash(destination, manifest, 'observations.jsonl', adapter.json_bytes(record))
                with self.assertRaises(ValueError): adapter.verify(destination)
            # Equivalent JSON numbers remain numbers; spelling 0 versus 0.0 is not a boolean.
            record = json.loads(original); record['measurements']['acceleration_x_mps2'] = 0
            self.rehash(destination, manifest, 'observations.jsonl', adapter.json_bytes(record))
            self.assertEqual(adapter.verify(destination), manifest)

    def test_duplicate_fields_rejected_even_with_rehashed_files(self):
        with tempfile.TemporaryDirectory() as temp:
            _, mapping, destination, manifest = self.package(Path(temp), [dict(ROW, valid='False'), ROW])
            raw_manifest = (destination / 'manifest.json').read_bytes()
            for raw in (raw_manifest.replace(b'"format":', b'"format":"ignored","format":', 1),
                        raw_manifest.replace(b'"format":', b'"\\u0066ormat":"ignored","format":', 1),
                        raw_manifest.replace(b'"bytes":', b'"bytes":0,"bytes":', 1)):
                (destination / 'manifest.json').write_bytes(raw)
                with self.assertRaises(ValueError): adapter.verify(destination)
            (destination / 'manifest.json').write_bytes(raw_manifest)
            for name, key in [('attachment.json', 'site_id'), ('observations.jsonl', 'sequence'), ('quarantine.jsonl', 'reason')]:
                original = (destination / name).read_bytes()
                modified = original.replace(('"'+key+'":').encode(), ('"'+key+'":null,"'+key+'":').encode(), 1)
                self.rehash(destination, manifest, name, modified)
                with self.assertRaises(ValueError): adapter.verify(destination)
                self.rehash(destination, manifest, name, original)
            duplicate_mapping = mapping.read_bytes().replace(b'"site_id":', b'"site_id":"ignored","site_id":', 1)
            mapping.write_bytes(duplicate_mapping)
            with self.assertRaises(ValueError): adapter.prepare(Path(temp) / 'capture.csv', mapping, Path(temp) / 'new-evidence')
            self.assertFalse((Path(temp) / 'new-evidence').exists())

    def test_json_encoding_nonfinite_nesting_and_record_limits(self):
        for raw in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'\xff',
                    b'[' * 2000 + b']' * 2000, b'[0,' + b'0,' * 512 + b'0]'):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError): adapter.evidence_json(raw)
        with self.assertRaises(ValueError): adapter.evidence_lines(b'{}\n' * (adapter.MAX_ROWS + 1), 256)
        with self.assertRaises(ValueError): adapter.evidence_lines(b' ' * 257, 256)
        with self.assertRaises(ValueError): adapter.evidence_lines(b'{}\n\n', 256)
        with self.assertRaises(ValueError): adapter.evidence_lines(b' ' * 16385, 16384)

    def test_file_specific_limits_and_snapshot_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, destination, manifest = self.package(Path(temp), [ROW])
            original_read = adapter.read_file; reads = []
            def checked_read(path, limit):
                reads.append((Path(path).name, limit))
                return original_read(path, limit)
            with mock.patch.object(adapter, 'read_file', side_effect=checked_read):
                self.assertEqual(adapter.verify(destination), manifest)
            self.assertEqual(reads, [('manifest.json', 65536), *adapter.EVIDENCE_LIMITS.items()])
            for name, limit in [('source.capture.csv', adapter.MAX_INPUT), ('attachment.json', 8192)]:
                original = (destination / name).read_bytes()
                with (destination / name).open('wb') as stream: stream.truncate(limit + 1)
                with self.assertRaises(ValueError): adapter.verify(destination)
                (destination / name).write_bytes(original)

    def test_cli_malformed_evidence_fails_without_traceback_or_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, destination, manifest = self.package(Path(temp), [ROW])
            manifest['accepted_rows'] = True
            (destination / 'manifest.json').write_bytes(adapter.json_bytes(manifest))
            before = {p.name: p.read_bytes() for p in destination.iterdir()}
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_capture.py'), 'verify', str(destination)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, before)

    def test_cli_exit_status_separates_preparation_from_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'capture.csv'; source.write_bytes(capture([dict(ROW, valid='False')]))
            mapping = root / 'mapping.json'; mapping.write_bytes(adapter.json_bytes(MAPPING))
            output = root / 'review'
            command = [sys.executable, str(ROOT / 'scripts/prepare_capture.py')]
            prepared = subprocess.run(command + ['prepare', '--input', str(source), '--attachment', str(mapping), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(prepared.returncode, 2, prepared.stderr)
            verified = subprocess.run(command + ['verify', str(output)], capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertTrue(json.loads(verified.stdout)['requires_review'])

    def test_verification_report_matches_snapshots_without_physical_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            _,_,destination,manifest=self.package(root,[dict(ROW,valid='False')])
            before={p.name:p.read_bytes() for p in destination.iterdir()}
            output=root/'verification.json'
            self.assertEqual(adapter.write_verification_report(destination,output),manifest)
            report=adapter.evidence_json(output.read_bytes())
            self.assertEqual(report['manifest'],manifest)
            self.assertEqual(report['manifest_sha256'],adapter.sha(before['manifest.json']))
            self.assertEqual(report['manifest_bytes'],len(before['manifest.json']))
            self.assertTrue(report['package_consistency_checked'])
            self.assertTrue(report['source_transformation_recomputed'])
            self.assertTrue(report['manifest']['requires_review'])
            for key in ('report_authenticated','source_authenticated','atomic_folder_snapshot','ongoing_freshness_verified',
                        'physical_source_verified','calibration_verified','hardware_connected','ready_for_ingestion','equipment_authorized','production_ready'):
                self.assertIs(report[key],False,key)
            self.assertEqual({p.name:p.read_bytes() for p in destination.iterdir()},before)
            saved=output.read_bytes()
            with self.assertRaises(ValueError):adapter.write_verification_report(destination,output)
            self.assertEqual(output.read_bytes(),saved)
            with self.assertRaises(ValueError):adapter.write_verification_report(destination,destination/'report.json')
            self.assertFalse((destination/'report.json').exists())

    def test_report_cli_success_and_failure_preserve_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,_,destination,_=self.package(root,[ROW]);output=root/'report.json'
            command=[sys.executable,str(ROOT/'scripts/prepare_capture.py'),'verify',str(destination),'--report',str(output)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(json.loads(result.stdout)['requires_review'])
            saved=output.read_bytes();result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertEqual(output.read_bytes(),saved)
            output.unlink();(destination/'observations.jsonl').write_bytes(b'altered')
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertFalse(output.exists())
            self.assertNotIn('Traceback',result.stderr)

    def test_report_exclusive_creation_rechecks_late_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,_,destination,_=self.package(root,[ROW]);output=root/'report.json'
            verify=adapter.verify
            def competing_write(*args,**kwargs):
                report=verify(*args,**kwargs);output.write_bytes(b'other local file');return report
            with mock.patch.object(adapter,'verify',side_effect=competing_write):
                with self.assertRaises(FileExistsError):adapter.write_verification_report(destination,output)
            self.assertEqual(output.read_bytes(),b'other local file')


if __name__ == '__main__':
    unittest.main()
