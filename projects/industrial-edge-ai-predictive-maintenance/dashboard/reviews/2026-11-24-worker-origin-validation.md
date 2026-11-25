# Worker origin and redirect checks — 24 November 2026

Reviewed baseline: `4e64eb674d5ce45036de3a26d9bc7bb99dcf3e85`, draft PR #2. Scope: the existing one-pass development HTTP delivery worker. New connection-boundary tests use a mock HTTP transport; no external server or equipment is contacted. The existing integration suite also uses an isolated loopback test server.

## Demonstrated defect and change

A nonnumeric configured port passed the worker's origin checks, then raised `httpx.InvalidURL`, which the command-line error handler did not catch. Validation now parses and bounds the optional port before constructing a client. It also refuses control/whitespace characters and any user-info component, including empty user-info, to avoid ambiguous origin settings. Invalid settings produce the existing sanitized command-line failure without creating a queue file.

The worker retains its existing HTTP loopback-only scope, supporting `127.0.0.1`, `localhost` and `::1`. Redirect following and environment proxy use were already disabled; this change adds explicit regression evidence for those protections rather than claiming they were newly implemented.

## Verification

Five new tests cover invalid origins before client/file creation, valid IPv4/hostname/IPv6 loopback origins, login redirects, ingest redirects and sanitized CLI errors. They assert that a redirect target receives no request, redirected ingest remains pending without a receipt, and logout uses the original origin. Client options explicitly keep `follow_redirects=false` and `trust_env=false`. The CLI regression checks exit code 1, no traceback, no synthetic credential-marker disclosure and no queue file. The new suite is included explicitly in Dashboard Checks.

All 44 tests passed across `test_delivery.py`, `test_delivery_worker.py`, `test_delivery_history.py`, `test_delivery_capacity.py` and `test_delivery_timing.py`. Existing test-client deprecation warnings did not block execution.

These checks establish local development-worker behavior, not secure remote transport, DNS authenticity, TLS, hardware enrollment or a production device identity. Credentials remain dedicated local test-account inputs. No dashboard scope, new hardware, merge or deployment is included. The original 30-product selection is unchanged; physical acceptance and equipment authorization remain pending/false.
