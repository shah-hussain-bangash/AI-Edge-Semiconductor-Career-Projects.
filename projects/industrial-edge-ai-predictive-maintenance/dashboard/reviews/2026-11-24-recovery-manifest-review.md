# Recovery manifest validation — 24 November 2026

Reviewed baseline: `848bf1bd34dfedff5a4f3ec41216493abe93aee8`, draft PR #2. Scope: local backup manifest parsing. All verification uses disposable synthetic databases and temporary backup directories.

## Demonstrated behavior

An array or null manifest root raised `AttributeError` instead of the recovery tool's handled validation error. Duplicate JSON fields were silently resolved by the decoder, including a conflicting `format` field. An otherwise valid manifest with an extra `NaN` field was also accepted. These inputs do not establish a successful corrupt restore; the demonstrated problems are an unhandled failure and ambiguous/nonstandard input acceptance.

## Change

Verification requires an object root, rejects duplicate fields at every object depth and rejects the nonstandard `NaN`, `Infinity` and `-Infinity` constants. JSON decoding and excessive nesting failures become a fixed validation message that does not repeat manifest contents. This happens before a restore staging directory is created. Valid manifests produced by the existing backup command retain the same format and round-trip behavior.

No existing backup is rewritten, migrated or deleted. Previously accepted duplicate-field or nonstandard JSON manifests now fail verification and require investigation rather than automatic repair.

## Verification

- 11 recovery tests cover normal round-trip/session revocation, WAL snapshots, source preservation, corruption, path checks and new malformed-input cases.
- New regressions cover five non-object roots, conflicting and identical duplicate format fields, nested and entry-level duplicates, all three nonstandard constants, malformed syntax and deeply nested input.
- Both `verify` and `restore` command paths exit with code 1 and no traceback or test-marker disclosure for invalid input. Failed restores leave no completed destination or staging directory; source database bytes remain unchanged.
- Combined recovery, observation-to-incident and incident-to-maintenance planning suites: 30 tests passed. The existing synthetic recovery drill is also rerun against the resulting software tree, with its sanitized result retained locally.

This is a bounded software regression check, not a general security certification, live recovery rehearsal or hardware test. Physical acceptance, equipment authorization and production readiness remain pending/false. The original 30 hardware categories are unchanged; connection awaits the complete hardware set and a ready, reviewed bench. Other repository concepts remain future scope. No merge or deployment is included.
