# Duplicate central commit integrity — 24 November 2026

Reviewed baseline: `1c10b0af299a20044d16a2d1bc5984ab03ddd493`, draft PR #2. Scope: retrying the existing synthetic observation ingest endpoint against disposable test storage. No hardware, live dashboard database or deployed service is used.

## Demonstrated inconsistency

After an initial HTTP 201 commit, a synthetic fixture changed the stored measurement payload without changing its content-hash column. History inspection correctly returned HTTP 503, but retrying the original ingest returned HTTP 200 with a central-commit receipt. The duplicate path trusted the stored hash column without validating the stored content. A worker recovering from a lost response could therefore mark delivery successful despite an inconsistent central copy.

## Change

Inside the existing serialized transaction, the duplicate path now runs the same stored-observation integrity and contract checks used by history inspection. They validate the stored payload against its event/content identities, device and binding metadata, receipt identity and aware commit timestamp before a duplicate receipt or normal content-conflict decision is returned.

Damaged storage returns HTTP 503 without a receipt. The endpoint does not repair, overwrite, remove or add an observation, and does not add a misleading successful-commit/conflict audit entry. An intact duplicate retains the existing idempotent behavior; a legitimate changed-content request still returns the existing conflict response.

The delivery worker handles this 503 through its existing bounded backoff/retry policy. It retains the queued payload and does not mark it delivered; exhausted retries remain blocked for investigation. Previously saved history is not retroactively checked or rewritten by this change.

## Regression evidence

Eight corruption cases cover malformed/non-object payloads, altered measurements, a contradictory hash column, mismatched stored binding revision, invalid receipt identity and invalid/timezone-free commit timestamps. Each asserts 503, no receipt, unchanged damaged row, one retained central record and unchanged audit count.

A separate lost-response scenario commits through the actual in-process test API, loses that response, damages the central fixture and retries delivery. It asserts retained pending state after the second attempt, `http-503`, null receipt and an unchanged central copy. The related existing suites also cover successful response-loss recovery, duplicate suppression, conflicts, access, lease fencing, history inspection and frozen incident evidence.

All 58 tests passed across `test_delivery.py`, `test_delivery_history.py`, `test_delivery_capacity.py`, `test_delivery_timing.py`, `test_acquisition_registry.py`, `test_observation_queries.py` and `test_observation_incidents.py`. Existing test-client deprecation warnings did not block execution.

These are bounded synthetic software checks. Hash consistency does not authenticate a physical sensor or prevent a privileged actor from changing both data and its identities. No dashboard feature, merge, deployment or equipment operation is included. The original 30-product selection is unchanged; physical acceptance and equipment authorization remain pending/false.
