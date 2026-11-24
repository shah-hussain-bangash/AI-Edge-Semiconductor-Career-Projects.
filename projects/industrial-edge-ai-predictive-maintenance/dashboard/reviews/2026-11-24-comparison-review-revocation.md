# Comparison-review access revocation — 24 November 2026

Reviewed baseline: `229bb543a3040381bfb48a0b76f9eb75fc2bd241`, draft PR #2. Scope: the existing administrator-only offline comparison-review write path. All accounts, sessions and reports used for verification were disposable synthetic fixtures.

## Demonstrated race

The endpoint authenticated the session and checked the administrator role before reading and verifying comparison files. It then opened the review write transaction without refreshing those access facts. A concurrent access change committed during file verification could therefore leave an in-flight request using the earlier authorization state.

Deterministic regressions simulate the committed change after successful report verification and before the review write. Before the fix, all five negative cases still returned HTTP 200 with a saved review: demotion to operator, demotion to auditor, account disabling, session deletion and session expiry. A second enabled administrator was retained in the fixture so the scenario did not rely on removing the final administrator.

This concerns offline report decisions; the response still declared `model_deployed=false` and `hardware_connected=false`. It is not evidence of equipment control or deployment.

## Change

After acquiring the existing `BEGIN IMMEDIATE` write transaction, the endpoint now calls the existing [session/identity refresh helper](../maintenance_requests.py) and checks the fresh role before reading the decision revision or writing the decision, event and audit record. The helper binds the check to the original session's user ID and CSRF hash, verifies that the account remains enabled and checks session expiry.

Demoted accounts receive HTTP 403; disabled accounts and revoked/expired sessions receive HTTP 401. The negative regressions verify that no review row, review-history event or review audit entry is created. A positive control revokes a different session for the same administrator and confirms that the current authorized session can still save the offline review.

The change uses the application's existing transaction and authorization helpers. It adds no identity provider, account, dashboard feature, equipment permission or production deployment. Historical review decisions are not rewritten.

## Verification

| Suite | Outcome |
| --- | --- |
| `test_comparison_review.py` | 12/12 PASS |
| `test_team_accounts.py` | 11/11 PASS |
| `test_password_rotation.py` | 9/9 PASS |
| `test_server.py` | 26/26 PASS |

Total: **58 targeted Python tests passed**. The new regressions cover five access-change interleavings and the other-session positive control. Existing numerical-consistency, review/revision, authentication, account and password checks passed. No real user's access or live dashboard database was changed.

This is a bounded write-boundary regression review, not a comprehensive concurrency audit or security certification. Physical hardware validation remains pending; no merge or deployment is part of this change.
