# Bounded local login protection — 25 November 2026

Reviewed baseline: `e5c046c0b6a5929ea72c80711fc29ba1fc7bf701`, draft PR #2. The scoped backend review demonstrated that rotating the email bypassed an aggregate client limit and expired identity keys remained in an unbounded process-local dictionary. A new API regression failed before this change: the 31st distinct invalid identity returned 401 and reached the password checker instead of returning 429 before that work.

## Change

`LoginThrottle` replaces the old dictionary. A lock atomically reserves admission before database/password work, so simultaneous requests count against the same fixed-window budgets. Defaults are five failed/in-flight attempts per client/email and thirty across emails per client in 900 seconds, measured with a monotonic clock. Successful completion removes only its reservation from the source bucket and clears completed failures for the matching identity while retaining other in-flight work. Denied credentials and aborted admitted requests retain their reservation until expiry.

The table holds at most 4,096 hashed source/identity buckets. Every admission/completion prunes expired entries globally. Capacity refusal does not add a key or evict a live limit. Empty buckets are removed. Late completion of an expired reservation does not recreate it. Both quota and capacity refusal return the existing generic 429 response before another password check. Password/role revalidation, session issuance, audit and cookies retain their existing transaction behavior. The diagnostic source fingerprint includes the new backend module.

## Verification

All **80 targeted test methods passed**: login protection 12, server/API 26, local team administration 11, password rotation 9, service operations 7 and static structure 15. The login suite covers identity/source isolation, identity rotation, bounded capacity with expiry recovery, success without clearing source failures or other in-flight reservations, expired completion, hashed tracking keys, actual-credential recovery and concurrent admission. One API case holds five password checks in flight and verifies that the sixth same-identity request is denied before the checker; a separate concurrent unit case admits exactly thirty of sixty requests from the same source within the window. These are finite fixtures, not throughput or soak measurements.

The tests use disposable stores, synthetic identities and controlled clocks. Invalid-credential probes mock the password-check result to avoid turning the regression into a load test; expiry recovery also verifies a real configured fixture password. Existing in-flight password-rotation and account protections passed. No real account, running dashboard or hardware is used. Existing dependency deprecation warnings were non-blocking. The Dashboard Checks workflow now explicitly runs the new suite.

From `dashboard` with test dependencies installed:

```powershell
python -m unittest discover -s tests -p test_login_protection.py -v
python -m unittest discover -s tests -p test_server.py -v
python -m unittest discover -s tests -p test_team_accounts.py -v
python -m unittest discover -s tests -p test_password_rotation.py -v
python -m unittest discover -s tests -p test_operations.py -v
python -m unittest discover -s tests -p test_structure.py -v
```

## Remaining boundary

This closes the reviewed gap in bounded local state, expiry and aggregate client admission. It does not close the production requirement for shared/gateway enforcement, trusted proxy attribution, enterprise identity or security qualification. State resets on restart and is independent across workers. A shared/NAT/proxy address shares the source budget; global capacity saturation can deny new legitimate identities until expiry. Long-running reservations expire with their admission window, so this is not a lifetime concurrency semaphore. Thresholds and deployment behavior need qualification for the accepted pilot.

Hardware connection remains deferred, the original 30 products are unchanged, and physical acceptance, equipment authorization and production readiness remain pending. No merge, deployment or live installation is included. Banner readability and other UI findings are separate follow-up work.
