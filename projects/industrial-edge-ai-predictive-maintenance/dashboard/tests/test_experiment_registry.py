"""Offline EDGEOPS experiment registry regression tests (synthetic fixtures only)."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiment_registry import register_experiment, verify_experiment, compare_experiments
from time_series_features import trailing_features


def demo_rows():
    events = [
        {
            "event_id": f"exp-{index:03d}",
            "asset_id": "MTR-001",
            "captured_at": (datetime(2026, 1, 1, tzinfo=timezone.utc)
                            + timedelta(minutes=index)).isoformat(),
            "vibration_mm_s": 2.0 + (index % 4) * 0.4 + (3 if index > 25 else 0),
            "temperature_c": 35.0 + index * 0.08,
            "current_a": 1.0 + (index % 3) * 0.1,
            "provenance": "synthetic-demo",
        }
        for index in range(36)
    ]
    result = trailing_features(events, window=3)
    for i, row in enumerate(result):
        row["label"] = int(i % 7 == 0)
    return result


class ExperimentRegistryTests(unittest.TestCase):
    def test_01_repeat_registration_is_content_addressed_and_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="edgeops-registry-") as directory:
            rows = demo_rows()
            first = register_experiment(rows, directory)
            second = register_experiment(list(reversed(rows)), directory)
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["dataset_sha256"], second["dataset_sha256"])
            self.assertEqual(len(list((Path(directory) / "runs").glob("*.json"))), 1)
            saved = verify_experiment(directory, first["run_id"])
            self.assertEqual(saved["report"]["evaluation_scope"], "synthetic-labeled-offline-only")
            self.assertEqual(saved["model"]["deployment_status"], "not-deployed")
            self.assertEqual(saved["dataset"]["label_kind"], "synthetic-demonstration-only")

    def test_02_change_in_configuration_produces_distinct_run(self):
        with tempfile.TemporaryDirectory(prefix="edgeops-registry-") as directory:
            rows = demo_rows()
            a = register_experiment(rows, directory, train_fraction=0.6)
            b = register_experiment(rows, directory, train_fraction=0.65)
            self.assertNotEqual(a["run_id"], b["run_id"])
            comparison = compare_experiments(directory, [a["run_id"], b["run_id"]])
            self.assertEqual(len(comparison), 2)
            self.assertEqual(comparison[0]["dataset_sha256"], comparison[1]["dataset_sha256"])
            self.assertEqual(comparison[0]["evaluation_scope"], "synthetic-labeled-offline-only")

    def test_03_tampered_model_or_report_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="edgeops-registry-") as directory:
            run = register_experiment(demo_rows(), directory)
            model_path = Path(directory) / "models" / (run["model_sha256"] + ".json")
            model_path.write_text('{"deployment_status":"deployed"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity"):
                verify_experiment(directory, run["run_id"])
            with self.assertRaises(ValueError):
                register_experiment(demo_rows(), directory)

    def test_04_invalid_data_rejected_without_writing_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="edgeops-registry-") as directory:
            rows = demo_rows()
            rows[0]["provenance"] = "hardware-live"
            with self.assertRaisesRegex(ValueError, "non-synthetic"):
                register_experiment(rows, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
            with self.assertRaises(ValueError):
                verify_experiment(directory, "../invalid")
            with self.assertRaises(ValueError):
                compare_experiments(directory, [])


    def test_05_cli_fixture_runs_and_compares_two_synthetic_experiments(self):
        from run_offline_experiment import run
        with tempfile.TemporaryDirectory(prefix="edgeops-demo-cli-") as directory:
            result = run(directory)
            self.assertEqual(len(result["run_ids"]), 2)
            self.assertNotEqual(*result["run_ids"])
            self.assertEqual(len(result["comparison"]), 2)
            self.assertFalse(result["model_deployed"])
            self.assertFalse(result["hardware_connected"])
            for run_id in result["run_ids"]:
                self.assertEqual(verify_experiment(directory, run_id)["report"]["deployment_status"], "not-deployed")



    def test_06_saved_experiment_uses_actual_utc_order_for_mixed_offsets(self):
        rows=demo_rows();expected=[row['event_id'] for row in rows]
        for i,row in enumerate(rows):
            parsed=datetime.fromisoformat(row['captured_at'])
            row['captured_at']=parsed.astimezone(timezone(timedelta(hours=9 if i%2 else -8))).isoformat()
        with tempfile.TemporaryDirectory(prefix='edgeops-experiment-time-') as directory:
            saved=register_experiment(list(reversed(rows)),directory)
            result=verify_experiment(directory,saved['run_id'])
            self.assertEqual([row['event_id'] for row in result['dataset']['rows']],expected)
            self.assertEqual(result['report']['holdout_event_ids'],expected[-result['report']['counts']['test']:])

    def test_07_invalid_or_naive_times_are_rejected_before_artifact_writes(self):
        for timestamp in ('not-a-time','2026-01-01T00:00:00','2026-99-01T00:00:00Z'):
            with self.subTest(timestamp=timestamp),tempfile.TemporaryDirectory() as directory:
                rows=demo_rows();rows[0]['captured_at']=timestamp
                with self.assertRaisesRegex(ValueError,'captured_at'):
                    register_experiment(rows,directory)
                self.assertEqual(list(Path(directory).iterdir()),[])


if __name__ == "__main__":
    unittest.main()
