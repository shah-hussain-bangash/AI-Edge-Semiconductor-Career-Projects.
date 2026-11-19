"""Compare two offline EDGEOPS baselines on identical synthetic holdout rows.

This command does not load production data, update the dashboard database,
write model binaries, connect hardware or deploy a classifier.
"""
import json
from run_offline_experiment import synthetic_fixture
from sklearn_comparison import compare_same_holdout

if __name__ == "__main__":
    result = compare_same_holdout(synthetic_fixture())
    print(json.dumps(result, indent=2, sort_keys=True))
