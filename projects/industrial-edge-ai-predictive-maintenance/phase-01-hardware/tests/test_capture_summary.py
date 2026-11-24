"""Descriptive statistics from disposable offline evidence; no hardware access."""
from datetime import datetime, timedelta, timezone
import tempfile
import sys
import json
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

from test_prepare_capture import adapter, capture, load, MAPPING, ROOT, ROW

with patch.dict(sys.modules, {'prepare_capture': adapter}):
    summary = load('capture_summary', ROOT / 'scripts/summarize_capture.py')


class CaptureSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'package'

    def prepare(self, rows):
        source = self.root / 'source.csv'
        source.write_bytes(capture(rows))
        attachment = self.root / 'attachment.json'
        attachment.write_bytes(adapter.json_bytes(MAPPING))
        return adapter.prepare(source, attachment, self.package)

    def rows(self, seconds):
        start = datetime(2026, 11, 24, tzinfo=timezone.utc)
        return [dict(ROW, seq=str(index), uptime_ms=str(index * 1000),
                     gateway_utc=(start + timedelta(seconds=value)).isoformat())
                for index, value in enumerate(seconds)]

    def test_irregular_intervals_and_counts_use_accepted_receipts(self):
        rows = self.rows([0, 1, 2, 4, 8])
        rows[1].update(adxl345_valid='False', valid='False')
        rows[2].update(ds18b20_valid='False', valid='False')
        rows[3].update(ina219_valid='False', valid='False')
        self.prepare(rows)
        report = summary.summarize(self.package)
        self.assertEqual(report['sensor_groups'], {key: {'valid_rows': 4, 'invalid_rows': 1}
                                                  for key in ('adxl345', 'ds18b20', 'ina219')})
        timing = report['timing']
        self.assertEqual((timing['interval_count'], timing['receipt_span_seconds']), (4, 8))
        self.assertEqual((timing['interval_median_seconds'], timing['interval_p95_seconds'],
                          timing['interval_max_seconds'], timing['observed_receipt_rate_hz']), (1.5, 4, 4, 0.5))
        self.assertEqual(report['physical_acceptance'], 'pending')
        for flag in ('physical_source_verified', 'calibration_verified', 'hardware_connected',
                     'equipment_authorized', 'ready_for_ingestion', 'production_ready'):
            self.assertIs(report[flag], False)

    def test_valid_zero_is_counted_and_quarantined_rows_remain_separate(self):
        rows = self.rows([0, 1, 2])
        rows[0].update(current_ma='0')
        rows[1].update(current_ma='NaN')
        self.prepare(rows)
        report = summary.summarize(self.package)
        self.assertEqual((report['input_rows'], report['accepted_rows'], report['quarantined_rows']), (3, 2, 1))
        self.assertEqual(report['sensor_groups']['ina219']['valid_rows'], 2)
        self.assertEqual(report['accepted_sequence_gaps'], 1)
        self.assertTrue(report['requires_review'])
        self.assertEqual(report['timing']['interval_max_seconds'], 2)

    def test_p95_uses_nearest_rank_rather_than_maximum(self):
        self.prepare(self.rows(list(range(20)) + [40]))
        timing = summary.summarize(self.package)['timing']
        self.assertEqual(timing['interval_p95_seconds'], 1)
        self.assertEqual(timing['interval_max_seconds'], 21)

    def test_empty_single_and_equal_timestamp_streams_have_no_invented_rate(self):
        for seconds in ([], [0], [0, 0]):
            with self.subTest(seconds=seconds), tempfile.TemporaryDirectory() as directory:
                self.root = Path(directory)
                self.package = self.root / 'package'
                self.prepare(self.rows(seconds))
                timing = summary.summarize(self.package)['timing']
                self.assertIsNone(timing['observed_receipt_rate_hz'])
                self.assertFalse(timing['capture_elapsed_verified'])
                self.assertFalse(timing['sensor_sampling_rate_verified'])
                self.assertEqual(timing['zero_interval_count'], max(0, len(seconds) - 1))

    def test_utc_offsets_represent_elapsed_time_not_text_order(self):
        rows = self.rows([0, 1])
        rows[1]['gateway_utc'] = '2026-11-24T04:00:01+04:00'
        self.prepare(rows)
        self.assertEqual(summary.summarize(self.package)['timing']['receipt_span_seconds'], 1)

    def test_tampered_package_cannot_publish_summary(self):
        self.prepare(self.rows([0, 1]))
        (self.package / 'observations.jsonl').write_bytes(b'altered')
        output = self.root / 'summary.json'
        with self.assertRaises(ValueError):
            summary.write_summary(self.package, output)
        self.assertFalse(output.exists())

    def test_post_verification_change_is_rejected(self):
        self.prepare(self.rows([0, 1]))
        original = summary.evidence.verify
        def changed(*args, **kwargs):
            report = original(*args, **kwargs)
            (self.package / 'observations.jsonl').write_bytes(b'changed after verification')
            return report
        with patch.object(summary.evidence, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'Evidence changed before summary'):
                summary.write_summary(self.package, self.root / 'summary.json')
        self.assertFalse((self.root / 'summary.json').exists())

    def test_output_is_new_external_and_does_not_change_evidence(self):
        self.prepare(self.rows([0, 1]))
        before = {path.name: path.read_bytes() for path in self.package.iterdir()}
        with self.assertRaises(ValueError):
            summary.write_summary(self.package, self.package / 'summary.json')
        output = self.root / 'summary.json'
        summary.write_summary(self.package, output)
        original = output.read_bytes()
        with self.assertRaises(ValueError):
            summary.write_summary(self.package, output)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.package.iterdir()})

    def test_cli_reports_synthetic_origin_and_refuses_overwrite(self):
        self.prepare(self.rows([0, 1]))
        output = self.root / 'summary.json'
        command = [sys.executable, str(ROOT / 'scripts/summarize_capture.py'),
                   str(self.package), '--output', str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_bytes())['source_type'], 'synthetic')
        original = output.read_bytes()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(output.read_bytes(), original)

    def test_exclusive_creation_protects_a_late_output_file(self):
        self.prepare(self.rows([0, 1]))
        output = self.root / 'summary.json'
        original = summary.summarize
        def appeared(directory):
            report = original(directory)
            output.write_bytes(b'existing result')
            return report
        with patch.object(summary, 'summarize', side_effect=appeared):
            with self.assertRaises(FileExistsError):
                summary.write_summary(self.package, output)
        self.assertEqual(output.read_bytes(), b'existing result')
