"""Deterministic offline evaluation foundation for synthetic EDGEOPS data.

No deployed ML model, training pipeline or real failure labels are implied.
This utility evaluates supplied binary scores/labels and keeps threshold
selection separate from holdout evaluation to avoid test-data leakage.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationResult:
    sample_count: int
    threshold: float
    tp: int
    tn: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    accuracy: float

    def as_dict(self):
        return vars(self).copy()


def evaluate_scores(labels, scores, *, threshold):
    """Evaluate previously computed scores, without fitting on test labels."""
    labels = list(labels)
    scores = list(scores)
    if len(labels) != len(scores) or not labels:
        raise ValueError("Labels and scores must have equal nonzero lengths")
    if not isinstance(threshold, (int, float)) or not math.isfinite(threshold):
        raise ValueError("Threshold must be finite")
    if any(type(label) is not int or label not in (0, 1) for label in labels):
        raise ValueError("Labels must be binary integers")
    if any(not isinstance(score, (int, float)) or not math.isfinite(score)
           or score < 0 or score > 1 for score in scores):
        raise ValueError("Scores must be finite values in [0, 1]")
    positives = [int(score >= threshold) for score in scores]
    tp = sum(a == 1 and b == 1 for a,b in zip(labels, positives))
    tn = sum(a == 0 and b == 0 for a,b in zip(labels, positives))
    fp = sum(a == 0 and b == 1 for a,b in zip(labels, positives))
    fn = sum(a == 1 and b == 0 for a,b in zip(labels, positives))
    precision = tp / (tp+fp) if tp+fp else 0.0
    recall = tp / (tp+fn) if tp+fn else 0.0
    f1 = (2*precision*recall / (precision+recall)) if precision+recall else 0.0
    return EvaluationResult(len(labels), float(threshold), tp, tn, fp, fn,
                            precision, recall, f1, (tp+tn)/len(labels))


def chronological_holdout(rows, holdout_fraction=0.25):
    """Split rows by strictly ordered UTC event timestamp, not at random.

    Rows are (timestamp, label, score). The caller must provide actual
    labels/scores; synthetic telemetry alone has no ground-truth failures.
    """
    if not 0 < holdout_fraction < 1:
        raise ValueError("Holdout fraction must be between 0 and 1")
    ordered = sorted(rows, key=lambda row: row[0])
    if len(ordered) < 4:
        raise ValueError("At least four labeled examples are required")
    n_holdout = max(1, math.ceil(len(ordered)*holdout_fraction))
    return ordered[:-n_holdout], ordered[-n_holdout:]
