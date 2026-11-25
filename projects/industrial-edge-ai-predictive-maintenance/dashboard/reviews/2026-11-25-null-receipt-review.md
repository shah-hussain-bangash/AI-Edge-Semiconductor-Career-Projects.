# Null success-receipt handling — 25 November 2026

Reviewed baseline: `2b7274ddeaf48cc9518446fb26a814cc87b92395`, draft PR #2. Scope: the existing synthetic delivery worker and durable spool. All HTTP responses in the new regression use an in-memory mock transport; no server, hardware, live database or external endpoint is contacted.

## Demonstrated defect

A 200 or 201 ingest response containing JSON `null` reached `Spool.finish(receipt=None)`. That value also represents the internal no-receipt outcome. The queued observation therefore returned to `pending` after one attempt with no `last_error`, instead of being blocked with `invalid-central-receipt` like other malformed success receipts. The source remained retained and was never marked delivered; the defect was ambiguous retry/error classification, not a demonstrated data-loss or false-commit case.

Before the fix, the new worker regression failed for both HTTP statuses with observed state `(pending, 1, None)` rather than `(blocked, 1, invalid-central-receipt)`. Other tested non-object JSON values already failed receipt validation.

## Correction and verification

The success-response path now requires a receipt object before calling `finish`. Null and all other non-object responses enter the existing invalid-receipt path. Transient transport and retry behavior is unchanged. The internal no-receipt outcome remains available for ordinary failure handling.

The regression covers both 200 and 201 with null, list, boolean, numeric and string bodies: ten mock response cases. It checks blocked state, one attempt, no receipt, cleared lease, one retained row, unchanged event key/content hash/payload/creation time, sanitized error and a logout attempt at the original loopback origin. Valid receipt behavior remains covered by the existing worker tests.

All **55 related tests passed** after the fix: delivery 22, worker 6, history 12, capacity 9 and timing 6. The ten new response cases are subcases of one worker test, not ten additional test methods. Existing FastAPI/Starlette deprecation warnings were non-blocking.

Run the related suites from `dashboard` with its test dependencies:

```powershell
python -m unittest discover -s tests -p test_delivery.py -v
python -m unittest discover -s tests -p test_delivery_worker.py -v
python -m unittest discover -s tests -p test_delivery_history.py -v
python -m unittest discover -s tests -p test_delivery_capacity.py -v
python -m unittest discover -s tests -p test_delivery_timing.py -v
```

This change does not enroll hardware, expand dashboard scope, implement production transport or authorize equipment. The original 30-product selection is unchanged. Physical acceptance and production qualification remain pending. No merge, deployment or live installation is performed by this work.
