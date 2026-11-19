"""Offline scikit-learn comparison regression: equal holdout, no deployment."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from run_offline_experiment import synthetic_fixture
from sklearn_comparison import compare_same_holdout


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


if __name__=="__main__":
    unittest.main()
