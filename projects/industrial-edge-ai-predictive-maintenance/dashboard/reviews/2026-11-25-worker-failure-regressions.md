# Worker authentication and timeout regressions — 25 November 2026

Baseline: `131954031b202358b214a1dc5d6a7b4b172af53e`, draft PR #2. The existing worker passed an isolated six-scenario CLI rehearsal. This follow-up makes the core state-preservation checks permanent in `tests/test_delivery_worker.py`, which the existing Dashboard Checks workflow already executes. Runtime code and dashboard behavior are unchanged.

Three new regression methods cover six mock-transport cases:

- Four login failures: HTTP 401, HTTP 503, read timeout and missing CSRF cookie. No ingest request occurs; the complete saved queue row is unchanged and no delivery attempt is consumed.
- Ingest read timeout: the observation, identity, hash and creation time remain intact; state is pending with one attempt, a future retry time, no receipt and the sanitized `transport-unavailable` error. Logout is attempted.
- Logout read timeout after a valid mock commit response: the exact receipt remains saved, the source row remains intact and state remains delivered with one attempt and no delivery error. A failed logout does not establish server-side session revocation; this test only checks the retained delivery outcome.

All cases use disposable SQLite stores and `httpx.MockTransport`. No network, actual central database, real server session or hardware is exercised. Marker strings in simulated timeout exceptions are absent from saved queue records. CLI output sanitization is separately covered by the existing invalid-port CLI test; these three methods exercise `run_once` directly.

The worker suite passed **9/9 methods**, including the earlier origin, redirect and malformed-receipt tests. The six new cases are contained in three methods and are not an additional six-method total. Existing dependency deprecation warnings were non-blocking. Run from `dashboard`:

```powershell
python -m unittest discover -s tests -p test_delivery_worker.py -v
```

No software blocker required another runtime fix. This is finite fault-handling coverage, not a load/soak test or production transport qualification. The original 30-product selection remains unchanged, hardware connection is deferred and physical acceptance and production readiness remain pending. No merge, deployment or live installation is included.
