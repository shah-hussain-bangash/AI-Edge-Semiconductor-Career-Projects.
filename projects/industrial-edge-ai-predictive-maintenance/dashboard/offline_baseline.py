"""Offline synthetic feature baseline; never deployed to industrial equipment.

Fits standardized deviation scores on TRAIN only. The validation set selects
a fixed alarm threshold from predefined quantiles; TEST is never consulted
during fitting or threshold selection. Labels must be explicitly supplied and
are demo labels, not measured failures or equipment RUL.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import mean, pstdev

from ml_evaluation import evaluate_scores
from time_series_features import _time

FEATURES = (
    "vibration_mm_s_mean", "vibration_mm_s_std", "vibration_mm_s_delta",
    "temperature_c_mean", "temperature_c_std", "temperature_c_delta",
    "current_a_mean", "current_a_std", "current_a_delta",
)


def _features(row):
    values = row.get("features")
    if not isinstance(values, dict):
        raise ValueError("feature map required")
    result = []
    for feature in FEATURES:
        value = values.get(feature)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
            raise ValueError("missing or invalid feature: " + feature)
        result.append(float(value))
    return result


def _label(row):
    value = row.get("label")
    if type(value) is not int or value not in (0, 1):
        raise ValueError("explicit synthetic binary label required")
    return value


def _chronological_key(row):
    """Order by actual UTC instant; retain the original timestamp in saved rows."""
    return _time(row['captured_at']), row['event_id']


def _split(rows, train_fraction=0.6, validation_fraction=0.2):
    rows = list(rows)
    if len(rows) < 10:
        raise ValueError("at least ten explicitly labeled feature rows required")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("invalid train/validation proportions")
    ids = set()
    last_by_asset = {}
    clean = []
    for row in rows:
        if row.get("provenance") != "synthetic-demo":
            raise ValueError("non-synthetic record rejected")
        eid = row.get("event_id")
        asset = row.get("asset_id")
        timestamp = row.get("captured_at")
        if not isinstance(eid, str) or not eid or eid in ids:
            raise ValueError("event_id must be unique")
        if not isinstance(asset, str) or not asset or not isinstance(timestamp, str) or not timestamp:
            raise ValueError("asset and captured_at required")
        ids.add(eid)
        _features(row)
        _label(row)
        clean.append(row)
    # Explicit global chronology, including when assets are interleaved.
    clean.sort(key=_chronological_key)
    train_end = int(len(clean) * train_fraction)
    val_end = int(len(clean) * (train_fraction + validation_fraction))
    if not (2 <= train_end < val_end < len(clean)):
        raise ValueError("empty train, validation or test partition")
    return clean[:train_end], clean[train_end:val_end], clean[val_end:]


@dataclass(frozen=True)
class Baseline:
    centers: tuple[float, ...]
    scales: tuple[float, ...]
    threshold: float
    feature_names: tuple[str, ...] = FEATURES

    def score(self, row):
        features = _features(row)
        z = [(x - center) / scale for x, center, scale in zip(features, self.centers, self.scales)]
        # Map monotonic Euclidean deviation to 0..1, without probability claims.
        distance = sqrt(sum(value * value for value in z) / len(z))
        return distance / (1 + distance)


def evaluate_offline_baseline(rows, *, train_fraction=0.6, validation_fraction=0.2):
    """Return demo metrics with distinct train/validation/test and provenance."""
    train, validation, holdout = _split(rows, train_fraction, validation_fraction)
    matrix = [_features(row) for row in train]
    centers = tuple(mean(column) for column in zip(*matrix))
    scales = tuple(max(pstdev(column), 1e-6) for column in zip(*matrix))
    initial = Baseline(centers, scales, threshold=0.5)
    validation_scores = [initial.score(row) for row in validation]
    validation_labels = [_label(row) for row in validation]
    candidate_thresholds = (0.3, 0.45, 0.6, 0.75, 0.9)
    # Deterministic tie-breaking prefers a higher threshold to avoid excess alerts.
    selected = max(candidate_thresholds,
                   key=lambda t: (evaluate_scores(validation_labels, validation_scores, threshold=t).f1, t))
    model = Baseline(centers, scales, selected)
    holdout_labels = [_label(row) for row in holdout]
    holdout_scores = [model.score(row) for row in holdout]
    result = evaluate_scores(holdout_labels, holdout_scores, threshold=selected)
    return {
        "model": model,
        "train_count": len(train),
        "validation_count": len(validation),
        "test_count": len(holdout),
        "holdout_event_ids": [r["event_id"] for r in holdout],
        "test_metrics": result.as_dict(),
        "evaluation_scope": "synthetic-labeled-offline-only",
        "deployment_status": "not-deployed",
        "failure_prediction_accuracy": "not-established",
    }
