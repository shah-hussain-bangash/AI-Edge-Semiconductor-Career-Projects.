"""Offline, fair-split comparison of EDGEOPS synthetic demonstration baselines.

scikit-learn is optional and installed only for offline experiment work.
Same chronological partitions and holdout event IDs are used for both models.
All labels are invented synthetic demo labels; this is not industrial validity.
No pickle, joblib, network, API inference or equipment connection.
"""
from __future__ import annotations

from dataclasses import asdict
from math import sqrt
from statistics import mean, pstdev

from ml_evaluation import evaluate_scores
from offline_baseline import Baseline, FEATURES, _features, _label, _split


def _select_threshold(labels, scores):
    candidates = (0.3, 0.45, 0.6, 0.75, 0.9)
    return max(candidates, key=lambda t: (
        evaluate_scores(labels, scores, threshold=t).f1, t))


def compare_same_holdout(rows, *, train_fraction=0.60, validation_fraction=0.20):
    """Use the same held-out events for two distinct offline approaches."""
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError(
            "Offline ML comparison needs scikit-learn and numpy; "
            "install requirements-ml.txt into the development environment"
        ) from exc

    train, validation, test = _split(rows, train_fraction, validation_fraction)
    x_train = [_features(row) for row in train]
    x_val = [_features(row) for row in validation]
    x_test = [_features(row) for row in test]
    y_train = [_label(row) for row in train]
    y_val = [_label(row) for row in validation]
    y_test = [_label(row) for row in test]
    if len(set(y_train)) != 2:
        raise ValueError("Both demo label classes are required in the training split")

    centers = tuple(mean(col) for col in zip(*x_train))
    scales = tuple(max(pstdev(col), 1e-6) for col in zip(*x_train))
    # Existing transparent deviation baseline, fit only on training features.
    deviation = Baseline(centers, scales, threshold=0.5)
    deviation_val_scores = [deviation.score(row) for row in validation]
    deviation_threshold = _select_threshold(y_val, deviation_val_scores)
    deviation_test_scores = [deviation.score(row) for row in test]

    # Separate supervised sklearn comparison: no holdout fit or threshold tuning.
    supervised = make_pipeline(
        StandardScaler(),
        LogisticRegression(random_state=17, max_iter=1000, class_weight="balanced")
    )
    supervised.fit(np.asarray(x_train), np.asarray(y_train))
    sklearn_val_scores = supervised.predict_proba(np.asarray(x_val))[:, 1].tolist()
    sklearn_threshold = _select_threshold(y_val, sklearn_val_scores)
    sklearn_test_scores = supervised.predict_proba(np.asarray(x_test))[:, 1].tolist()

    return {
        "provenance": "synthetic-demo",
        "label_kind": "synthetic-demonstration-only",
        "evaluation_scope": "offline-research-only",
        "hardware_connected": False,
        "model_deployed": False,
        "real_world_accuracy": "not-established",
        "split": {
            "method": "global-chronological",
            "train_count": len(train),
            "validation_count": len(validation),
            "test_count": len(test),
            "holdout_event_ids": [row["event_id"] for row in test],
        },
        "models": [
            {
                "name": "standardized-deviation",
                "type": "unsupervised-deviation-baseline",
                "threshold": deviation_threshold,
                "test_metrics": evaluate_scores(y_test, deviation_test_scores,
                                                 threshold=deviation_threshold).as_dict(),
            },
            {
                "name": "sklearn-logistic-regression",
                "type": "supervised-synthetic-classifier",
                "threshold": sklearn_threshold,
                "test_metrics": evaluate_scores(y_test, sklearn_test_scores,
                                                 threshold=sklearn_threshold).as_dict(),
            }
        ],
        "warning": "Synthetic labels and tiny holdouts do not establish failure prediction performance."
    }
