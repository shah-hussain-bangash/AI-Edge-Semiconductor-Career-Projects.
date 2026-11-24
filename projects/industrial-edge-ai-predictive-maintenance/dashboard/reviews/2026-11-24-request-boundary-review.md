# Bounded software review: authentication and evidence boundaries

Reviewed 24 November 2026 against draft PR #2, branch `ui/production-workspace-20261119`, baseline commit `9f8831f257c490a0b8febf701628bae2ecc63c2d` (application tree `190dd2bc4a804785d5fb340f498ac51a1ed56c7c`). The PR targets `dashboard-live-edit`; no merge, deployment, live database change or hardware work was performed.

## Demonstrated finding and fix

An authenticated request with non-ASCII bytes in the anti-forgery header or cookie reached `hmac.compare_digest` with non-ASCII strings. Python raises `TypeError` for those arguments. The request therefore failed as an unhandled server error rather than an ordinary access denial. This review did not demonstrate an authentication bypass, unauthorized state change or equipment effect.

The regression test failed before the fix with four subtest errors: `TypeError: comparing strings with non-ASCII characters is not supported`. Cases covered a Latin-1 header byte, a UTF-8 byte sequence, a malformed cookie with the original valid header, and matching malformed header/cookie text.

`server.require_csrf` now rejects non-ASCII token text before calling the existing constant-time comparison. Issued tokens are ASCII, so valid token behavior is unchanged. Invalid requests return HTTP 403 with the existing denial message and response security headers. The regression also verifies that no session or audit record is changed, that the original session remains authenticated, and that a subsequent valid logout succeeds and revokes access.

Reference: [Python `hmac.compare_digest` documentation](https://docs.python.org/3/library/hmac.html#hmac.compare_digest), which specifies ASCII-only string arguments or bytes-like arguments. No authentication package or new application feature was introduced.

## Verification

All runs used existing test dependencies and disposable local data.

| Check | Outcome after fix |
| --- | --- |
| `test_server.py` (including four malformed-token subcases in the new regression) | 26/26 PASS |
| `test_team_accounts.py` | 11/11 PASS |
| `test_password_rotation.py` | 9/9 PASS |
| `test_observation_incidents.py` | 10/10 PASS |
| `test_observation_queries.py` | 5/5 PASS |
| `test_operations.py` (request limits and service checks) | 7/7 PASS |
| `tests/browser_passwords.cjs` | PASS; reauthentication, password confirmation, session revocation, sign-in, outage handling, contrast and five widths |
| `git diff --check` | PASS |

Total: **68 targeted Python regression tests passed**, plus the existing Chromium password workflow suite. The browser test starts and stops its own isolated service; it does not use the running user dashboard. GitHub CI outcomes for the resulting commit should be inspected in PR #2; the local results above do not assert that a later CI run has already passed.

## Limits and current hardware status

This was a focused source review and regression exercise, not a comprehensive penetration test, security certification or production acceptance. Existing authentication, request-size and source-snapshot checks were exercised in the listed scope; no broader absence-of-vulnerabilities claim is made.

The owner reports partial hardware receipt. Connection is deferred until the original ordered set is complete and the relevant bench review is ready. All physical acceptance remains pending. Previously published profile evidence stays pinned to its historical source commit; it must not be interpreted as evidence of a deployed fix or real acquisition. The other six repository concepts remain future scope.
