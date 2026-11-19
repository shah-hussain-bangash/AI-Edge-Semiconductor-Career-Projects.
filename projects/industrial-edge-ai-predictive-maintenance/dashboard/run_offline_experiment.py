"""Run a deterministic synthetic EDGEOPS experiment from the command line.

This produces *demonstration* model artifacts. Labels are invented on purpose:
they are not recorded equipment failures and metrics are not operational evidence.
No network calls, device access, or writes to the dashboard session database.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from experiment_registry import register_experiment, compare_experiments
from time_series_features import trailing_features


def synthetic_fixture():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = []
    for index in range(48):
        events.append({
            "event_id": f"demo-exp-{index:03d}",
            "asset_id": "MTR-001",
            "captured_at": (start + timedelta(minutes=index)).isoformat(),
            "vibration_mm_s": 2.2 + 0.09 * (index % 9) + (2.4 if index >= 36 else 0),
            "temperature_c": 37 + index * 0.11,
            "current_a": 1.1 + (index % 5) * 0.035,
            "provenance": "synthetic-demo",
        })
    rows = trailing_features(events, window=3)
    for index, row in enumerate(rows):
        row["label"] = int(index % 8 == 0 or index >= 37)
    return rows


def run(root):
    rows = synthetic_fixture()
    a = register_experiment(rows, root, train_fraction=0.60, validation_fraction=0.20)
    b = register_experiment(rows, root, train_fraction=0.65, validation_fraction=0.20)
    return {
        "message": "Synthetic-only experiment. No real failure prediction or deployed ML.",
        "artifact_root": str(Path(root).resolve()),
        "run_ids": [a["run_id"], b["run_id"]],
        "comparison": compare_experiments(root, [a["run_id"], b["run_id"]]),
        "hardware_connected": False,
        "model_deployed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent / ".local" / "experiments"),
                        help="Local output directory for immutable JSON artifacts")
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
