# Retry budget after expired worker leases — 24 November 2026

Reviewed baseline: `fe0b19aa500dfbc1c6cc3d41a2150cbc66e3522f`, draft PR #2. Scope: the existing synthetic delivery spool. New verification reopens disposable SQLite queues and deterministically expires leases; it does not perform repeated physical crashes, power cuts or equipment work.

## Demonstrated gap

Failed attempts saved through `finish()` became blocked after attempt eight. A worker that stopped before saving an outcome instead left an in-flight lease. Repeatedly expiring and reclaiming that lease produced claim nine and could continue beyond the intended budget.

## Change and retained behavior

One shared eight-attempt constant now governs both failure completion and new claims. When an eligible pending or expired in-flight record has already consumed its budget, claiming marks it blocked with `retry-budget-exhausted`, clears lease fields and returns no claim. Its payload, identity, original count and queue entry remain retained. No sender is called and no ninth attempt is counted. A subsequent invocation can claim healthy work.

The guard applies only when a record is eligible for claiming. It does not revoke an active eighth lease: that worker can still save a valid successful receipt. Once an expired record is blocked, its stale worker token cannot finish it. Legacy eligible records already above the budget are retained with their existing count rather than reset or deleted. There is no automatic unblock or repair.

Counts represent durable claims, not proven network transmissions. An exhausted record can have an uncertain central outcome if an earlier response was lost; blocked state does not prove the central service never committed it. Investigation/reconciliation remains necessary. This change does not add an operator replay workflow or change the one-pass worker model.

## Verification

All 47 tests passed across `test_delivery.py`, `test_delivery_worker.py`, `test_delivery_history.py`, `test_delivery_capacity.py` and `test_delivery_timing.py`.

New regressions cover eight reopened claims with expired leases and no saved result, refusal of a ninth send, preserved payload/count, stale-worker fencing, healthy work after exhaustion, successful completion of an active final attempt, and eligible legacy counts at/above the budget. Existing failure backoff, restart, lost-response, corruption, capacity and worker-boundary checks also passed. Existing test-client deprecation warnings did not block execution.

No new dashboard scope, hardware, merge or deployment is included. The original 30-product selection remains unchanged; physical acceptance and equipment authorization remain pending/false.
