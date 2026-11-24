# Synthetic model-evaluation review — 24 November 2026

Scope: the shared offline train/validation/test splitter, saved experiment/comparison ordering, preprocessing and threshold-selection boundaries. Reviewed baseline: GitHub commit `eec5fa1647163531030e76ed2864d941c55d6d52`, draft PR #2. No real equipment data, deployment or model approval was introduced.

## Demonstrated chronology defect and fix

The splitter sorted the `captured_at` strings directly. Re-expressing the same synthetic event instants using alternating UTC+09:00 and UTC-08:00 offsets changed the holdout from events `demo-exp-038` through `demo-exp-047` to events `029, 031, 033, 035, 037, 039, 041, 043, 045, 047`. No event time, feature or label had actually changed. Invalid and timezone-free timestamp strings were also accepted as if they defined a chronological evaluation.

The common ordering key now parses timestamps through the existing offset-aware time parser and compares actual UTC instants, using event ID as a deterministic tie-breaker. The same key orders the evaluation partitions and newly saved experiment/comparison datasets. Original timestamp text remains in the saved input snapshot. Invalid or timezone-free values fail before artifact creation. See [Python aware timestamp semantics](https://docs.python.org/3/library/datetime.html#aware-and-naive-objects).

New comparison reports include the timestamp-parser source file in their implementation fingerprints. Existing artifacts are not rewritten or migrated. Different declared timestamp representations can still have different dataset hashes because their original input text differs; the evaluated holdout and metrics now remain equivalent for the same instants.

## Training and threshold boundaries

Source inspection confirms that deviation centers/scales and the scikit-learn scaler/classifier are fitted on training rows. Thresholds are chosen on validation scores/labels from a fixed candidate list. Both approaches use the same held-out event IDs. The supervised pipeline uses `StandardScaler` followed by logistic regression; the deviation score is not a failure probability.

A regression changes every holdout label and strongly perturbs its features, then checks that the labels and scores supplied to both threshold-selection calls remain unchanged. This supports the tested training/validation boundary; it is not a general proof that any future dataset or feature generator is leakage-free. The methodology follows the [scikit-learn guidance on fitting preprocessing only on training data](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).

## Recorded demonstration result

[Machine-readable review result](../../phase-01-hardware/validation/model-evaluation-review-result.json)

| Partition | Rows | Synthetic label 0 | Synthetic label 1 |
| --- | --- | --- | --- |
| Training | 27 | 23 | 4 |
| Validation | 9 | 8 | 1 |
| Holdout | 10 | 1 | 9 |

| Approach | Selected threshold | TP / TN / FP / FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- |
| Standardized deviation | 0.45 | 9 / 0 / 1 / 0 | 0.90 | 1.00 | 0.9474 |
| Logistic regression | 0.90 | 3 / 1 / 0 / 6 | 1.00 | 0.3333 | 0.50 |

The deviation baseline predicts every holdout row positive. Its high F1 on this tiny, heavily positive synthetic holdout does not demonstrate useful real-world fault discrimination. Logistic regression misses six of the nine invented positive labels. This review selects no production model and establishes no industrial predictive-maintenance accuracy, calibrated failure probability or operating benefit.

The result records NumPy/scikit-learn versions and normalized source-file SHA-256 fingerprints. Its SHA-256 is `753387f5fe7a2f9ca15a07ef1c3bcfd0f1bbdf12ba2599d6b6471f50f048ae45` for the original LF JSON bytes. It describes the reviewed working implementation, versioned with this note after the baseline commit; it does not claim that the baseline already contained the fix.

## Verification

| Suite | Outcome |
| --- | --- |
| `test_sklearn_comparison.py` | 7/7 PASS |
| `test_experiment_registry.py` | 7/7 PASS |
| `test_comparison_review.py` | 6/6 PASS |
| `test_server.py` | 26/26 PASS |

Total: **46 targeted Python tests passed**. New regressions cover offset-equivalent holdouts/metrics, invalid/naive times, unchanged selection inputs after holdout perturbation, UTC ordering in saved experiment/comparison datasets, parser provenance and rejection before experiment-file writes. Existing content-addressing, review and API checks passed. These runs used disposable data and the separate installed test environment.

Hardware connection and physical acceptance remain pending. Real labeled datasets, appropriate temporal evaluation design, calibration/reference evidence and qualified operating acceptance remain separate dependencies. No dashboard feature, live data change, merge or deployment is part of this review.
