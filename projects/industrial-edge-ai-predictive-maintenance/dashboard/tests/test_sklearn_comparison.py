"""Offline scikit-learn comparison regression: equal holdout, no deployment."""
import sys
import json
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from run_offline_experiment import synthetic_fixture
from sklearn_comparison import compare_same_holdout
from sklearn_comparison import _select_threshold


class SklearnComparisonTests(unittest.TestCase):
    def test_01_same_holdout_for_distinct_models(self):
        rows=synthetic_fixture()
        result=compare_same_holdout(rows)
        self.assertEqual(result["evaluation_scope"],"offline-research-only")
        self.assertFalse(result["model_deployed"])
        self.assertFalse(result["hardware_connected"])
        self.assertEqual(len(result["models"]),2)
        self.assertEqual(result["split"]["test_count"],len(result["split"]["holdout_event_ids"]))
        self.assertEqual(result["split"]["holdout_event_ids"],
                         [x["event_id"] for x in rows[-result["split"]["test_count"]:] ])
        for model in result["models"]:
            self.assertEqual(model["test_metrics"]["sample_count"],result["split"]["test_count"])
            self.assertTrue(0 <= model["test_metrics"]["f1"] <= 1)

    def test_02_comparison_is_deterministic_and_rejects_missing_labels(self):
        rows=synthetic_fixture()
        a=compare_same_holdout(rows)
        b=compare_same_holdout(list(reversed(rows)))
        self.assertEqual(a,b)
        rows[0].pop("label")
        with self.assertRaisesRegex(ValueError,"label"):
            compare_same_holdout(rows)

    def test_03_comparison_requires_both_training_classes(self):
        rows=synthetic_fixture()
        for row in rows:
            row["label"]=0
        with self.assertRaises(ValueError):
            compare_same_holdout(rows)

    def test_04_equivalent_offset_times_keep_the_same_holdout_and_metrics(self):
        rows=synthetic_fixture()
        expected=compare_same_holdout(rows)
        for i,row in enumerate(rows):
            parsed=datetime.fromisoformat(row['captured_at'])
            row['captured_at']=parsed.astimezone(timezone(timedelta(hours=9 if i%2 else -8))).isoformat()
        self.assertEqual(compare_same_holdout(list(reversed(rows))),expected)

    def test_05_invalid_or_naive_times_cannot_claim_chronological_evaluation(self):
        for timestamp in ('not-a-time','2026-01-01T00:00:00','2026-99-01T00:00:00Z'):
            with self.subTest(timestamp=timestamp):
                rows=synthetic_fixture();rows[0]['captured_at']=timestamp
                with self.assertRaisesRegex(ValueError,'captured_at'):
                    compare_same_holdout(rows)

    def test_06_holdout_changes_do_not_change_threshold_selection_inputs(self):
        rows=synthetic_fixture()
        with patch('sklearn_comparison._select_threshold',wraps=_select_threshold) as select:
            original=compare_same_holdout(rows)
            calls=[deepcopy(call.args) for call in select.call_args_list]
        holdout=set(original['split']['holdout_event_ids'])
        for row in rows:
            if row['event_id'] in holdout:
                row['label']=1-row['label']
                row['features']={k:v+1000 for k,v in row['features'].items()}
        with patch('sklearn_comparison._select_threshold',wraps=_select_threshold) as select:
            changed=compare_same_holdout(rows)
            self.assertEqual(select.call_count,2)
            self.assertEqual([call.args for call in select.call_args_list],calls)
        self.assertEqual(changed['split'],original['split'])
        self.assertEqual([m['threshold'] for m in changed['models']],
                         [m['threshold'] for m in original['models']])

    def test_07_saved_comparison_rows_follow_actual_time_and_record_parser_source(self):
        from comparison_registry import save_comparison, verify_comparison
        rows=synthetic_fixture();expected=[row['event_id'] for row in rows]
        for i,row in enumerate(rows):
            parsed=datetime.fromisoformat(row['captured_at'])
            row['captured_at']=parsed.astimezone(timezone(timedelta(hours=9 if i%2 else -8))).isoformat()
        with tempfile.TemporaryDirectory(prefix='edgeops-comparison-time-') as directory:
            saved=save_comparison(list(reversed(rows)),directory)
            report=verify_comparison(directory,saved['comparison_id'])
            data=json.loads((Path(directory)/'comparison-datasets'/(report['dataset_sha256']+'.json')).read_text())
            self.assertEqual([row['event_id'] for row in data['rows']],expected)
            self.assertEqual(report['result']['split']['holdout_event_ids'],expected[-report['result']['split']['test_count']:])
            self.assertIn('time_series_features.py',report['source_sha256'])


if __name__=="__main__":
    unittest.main()
