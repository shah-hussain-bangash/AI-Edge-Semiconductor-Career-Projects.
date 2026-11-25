# Local queued payload integrity — 24 November 2026

Reviewed baseline: `705a787b5a9ffa5ee5254627146e16cb7d5394b5`, draft PR #2. Scope: the existing synthetic delivery spool. Verification uses disposable queue databases and synthetic input; it does not connect equipment or change the running user dashboard.

## Demonstrated defects

A fixture altered a saved measurement without updating the queue's content-hash column. The queue sent that altered payload to its sender callback. A second fixture replaced the payload with malformed JSON; claiming it committed an in-flight state and then raised `JSONDecodeError`. Neither path verified the stored payload against its saved identity before dispatch.

## Change and operating behavior

The queue now validates stored payloads against the existing synthetic delivery contract and recomputes their event/content identities before claiming them. The same check prevents duplicate enqueue requests from returning an edge-commit acknowledgment for an inconsistent saved copy. Valid receipt-time differences retain the existing identity semantics.

An invalid claim candidate becomes `blocked` with the fixed `invalid-local-observation` reason, while its saved payload, identity/hash, creation time and attempt count are retained. Lease fields are cleared. No sender callback is invoked and no delivery attempt is counted. There is no automatic repair, deletion or unblock.

This call returns `attempted=false` because no transmission occurred; queue status shows the blocked record. A subsequent invocation can claim the next healthy record. This remains the existing one-attempt worker model, not a new continuous worker. An expired worker cannot finish the blocked record because state/token fencing still applies. Existing delivered history is not retroactively revalidated or rewritten.

## Verification

All 61 tests passed across `test_delivery.py`, `test_delivery_history.py`, `test_delivery_capacity.py`, `test_delivery_timing.py`, `test_acquisition_registry.py`, `test_observation_queries.py` and `test_observation_incidents.py`.

New regressions cover malformed/non-object payloads, changed measurements, changed source identity, an invalid measured-source claim, contradictory stored hash, healthy work after a damaged first record and corruption of an expired lease. Assertions verify no send, retained evidence, sanitized reason, duplicate-enqueue refusal and old-worker fencing. Existing restart, lost-response, capacity, central integrity and incident evidence checks also pass. Existing test-client deprecation warnings did not block execution.

This is software consistency evidence, not proof of sensor authenticity or resistance to a privileged actor changing both data and hashes. No new dashboard scope, hardware, merge or deployment is included. The original 30-product selection remains unchanged; physical acceptance and equipment authorization remain pending/false.
