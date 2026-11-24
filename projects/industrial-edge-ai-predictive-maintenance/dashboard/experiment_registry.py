"""Content-addressed, read-only-by-default offline experiment artifacts.

No pickle, executable model loading, cloud uploads or equipment connections.
A run records a snapshot of explicitly labeled synthetic feature rows,
a transparent JSON baseline specification, and holdout metrics. Historical
artifacts are immutable and integrity-checked when read.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from offline_baseline import _chronological_key, evaluate_offline_baseline

SCHEMA_VERSION = "edgeops-offline-experiment-v1"


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _save_once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError("Existing artifact differs from its content address: " + path.name)


def _read_verified(path, expected_sha):
    if not path.is_file():
        raise ValueError("Missing experiment artifact: " + path.name)
    data = path.read_bytes()
    if _digest(data) != expected_sha:
        raise ValueError("Experiment artifact integrity mismatch: " + path.name)
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Experiment artifact is not valid JSON") from exc


def register_experiment(rows, artifact_root, *, train_fraction=0.6,
                        validation_fraction=0.2):
    """Store an immutable snapshot/model/manifest under a chosen local folder.

    This function never touches the dashboard's database. Identical input and
    parameters yield the same run ID and bytes. A run ID is a fingerprint,
    not proof of accuracy or real-world readiness.
    """
    rows = list(rows)
    # Evaluation validates all rows, labels and provenance before filesystem I/O.
    outcome = evaluate_offline_baseline(
        rows, train_fraction=train_fraction, validation_fraction=validation_fraction)
    ordered = sorted(rows, key=_chronological_key)
    dataset = {
        "schema": SCHEMA_VERSION, "provenance": "synthetic-demo",
        "rows": ordered, "label_kind": "synthetic-demonstration-only",
    }
    dataset_bytes = _json_bytes(dataset)
    dataset_sha = _digest(dataset_bytes)
    model = outcome["model"]
    model_doc = {
        "schema": SCHEMA_VERSION,
        "model_kind": "standardized-deviation-baseline",
        "provenance": "synthetic-demo",
        "feature_names": list(model.feature_names),
        "centers": list(model.centers),
        "scales": list(model.scales),
        "threshold": model.threshold,
        "score_interpretation": "unitless deviation, not failure probability",
        "deployment_status": "not-deployed",
    }
    model_bytes = _json_bytes(model_doc)
    model_sha = _digest(model_bytes)
    report = {
        "schema": SCHEMA_VERSION,
        "provenance": "synthetic-demo",
        "dataset_sha256": dataset_sha,
        "model_sha256": model_sha,
        "training_config": {
            "train_fraction": train_fraction,
            "validation_fraction": validation_fraction,
            "split_method": "global-chronological",
            "threshold_selection": "validation-f1",
            "evaluation_method": "chronological-holdout",
        },
        "counts": {
            "train": outcome["train_count"],
            "validation": outcome["validation_count"],
            "test": outcome["test_count"],
        },
        "holdout_event_ids": outcome["holdout_event_ids"],
        "test_metrics": outcome["test_metrics"],
        "evaluation_scope": "synthetic-labeled-offline-only",
        "failure_prediction_accuracy": "not-established",
        "deployment_status": "not-deployed",
    }
    report_bytes = _json_bytes(report)
    run_id = _digest(report_bytes)
    root = Path(artifact_root).expanduser().resolve()
    _save_once(root / "datasets" / (dataset_sha + ".json"), dataset_bytes)
    _save_once(root / "models" / (model_sha + ".json"), model_bytes)
    _save_once(root / "runs" / (run_id + ".json"), report_bytes)
    return {"run_id": run_id, "dataset_sha256": dataset_sha,
            "model_sha256": model_sha, "report": report}


def verify_experiment(artifact_root, run_id):
    """Read and verify a run and its exact referenced JSON artifacts."""
    if not isinstance(run_id, str) or len(run_id) != 64 or any(
            character not in "0123456789abcdef" for character in run_id):
        raise ValueError("run_id must be a lowercase SHA-256 digest")
    root = Path(artifact_root).expanduser().resolve()
    report = _read_verified(root / "runs" / (run_id + ".json"), run_id)
    if report.get("schema") != SCHEMA_VERSION or report.get("provenance") != "synthetic-demo":
        raise ValueError("Invalid offline experiment manifest")
    dataset_sha = report.get("dataset_sha256")
    model_sha = report.get("model_sha256")
    for value in (dataset_sha, model_sha):
        if not isinstance(value, str) or len(value) != 64 or any(
                letter not in "0123456789abcdef" for letter in value):
            raise ValueError("Invalid artifact hash in manifest")
    dataset = _read_verified(root / "datasets" / (dataset_sha + ".json"), dataset_sha)
    model = _read_verified(root / "models" / (model_sha + ".json"), model_sha)
    if dataset.get("provenance") != "synthetic-demo" or model.get("provenance") != "synthetic-demo":
        raise ValueError("Non-synthetic experiment artifact")
    if model.get("deployment_status") != "not-deployed":
        raise ValueError("Experiment model incorrectly marked deployed")
    return {"run_id": run_id, "report": report, "dataset": dataset, "model": model}


def compare_experiments(artifact_root, run_ids):
    """Grounded comparison of stored holdout metrics, not a model leaderboard."""
    if not run_ids:
        raise ValueError("Provide at least one run ID")
    result = []
    for run_id in run_ids:
        report = verify_experiment(artifact_root, run_id)["report"]
        result.append({
            "run_id": run_id, "dataset_sha256": report["dataset_sha256"],
            "test_count": report["counts"]["test"],
            "precision": report["test_metrics"]["precision"],
            "recall": report["test_metrics"]["recall"],
            "f1": report["test_metrics"]["f1"],
            "evaluation_scope": report["evaluation_scope"],
        })
    return result
