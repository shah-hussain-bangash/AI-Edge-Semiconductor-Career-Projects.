# Saved comparison metric consistency — 24 November 2026

Reviewed baseline: `27d8296e0d15997d61b9bb8fd9bc136f996c2808`, draft PR #2. Scope: numerical consistency of synthetic comparison reports and the existing report-review API. No live dashboard database or hardware was used.

## Demonstrated gap

The validator checked score ranges, confusion-count types and holdout totals but did not verify that precision, recall, F1 and accuracy agreed with those counts. A result with TP=9, TN=0, FP=1 and FN=0 was accepted with a declared F1 of 0.123; the producer's binary definition gives approximately 0.9473684211.

The regression also saved altered reports under their correctly recomputed content hashes. Before the fix, all eight altered-score cases (four metrics across two models) failed the expected rejection assertion. This demonstrates a numerical-validation gap even when byte identity is internally consistent. It does not establish a source-authentication bypass or real-world model validity.

## Change

`comparison_registry.validate_result` now derives the four scores directly from TP/TN/FP/FN using the same binary definitions as [the metric producer](../ml_evaluation.py). It accepts relative/absolute floating-point differences up to `1e-12` and preserves the existing zero-denominator convention. Boolean model thresholds and boolean sample counts are rejected rather than accepted through Python's numeric equality.

The existing read/review paths use this validator: contradictory reports are excluded from the verified list, and an approval attempt returns HTTP 409 without storing a review, review event or review audit entry. The valid original report remains visible in the regression. No report file, past decision or live data was deleted or rewritten.

Mathematically valid generated reports retain the same field format. Hand-edited or rounded records whose values fall outside the tolerance may now fail verification. New comparison identifiers can differ because the existing report format fingerprints the changed implementation source. Historical evidence remains tied to its recorded source version.

## Verification

| Suite | Outcome |
| --- | --- |
| `test_comparison_review.py` | 9/9 PASS |
| `test_sklearn_comparison.py` | 7/7 PASS |
| `test_experiment_registry.py` | 7/7 PASS |
| `test_server.py` | 26/26 PASS |

Total: **49 targeted Python tests passed**. The new checks cover correctly rehashed contradictory reports, API exclusion and approval denial, no saved review side effects, zero-denominator matrices, tiny serialization differences and boolean field rejection. All test data and stores were disposable.

This checks internal arithmetic, not whether labels, predictions, source files or scientific methodology are trustworthy. Synthetic evaluation remains offline research; no production model, physical acceptance, merge or deployment is established by these results.
