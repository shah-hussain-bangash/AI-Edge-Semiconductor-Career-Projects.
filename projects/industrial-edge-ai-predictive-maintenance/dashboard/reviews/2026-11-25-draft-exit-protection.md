# Browser exit warnings for unsaved drafts — 25 November 2026

Baseline: `10c747328ca1a696e721c6145aed5fef4806e984`, draft PR #2. Existing in-app discard dialogs protected tracked incident and planning editors, but browser reload/tab close could discard those drafts. The new Chromium regression first failed because a dirty incident reload produced no exit dialog.

The existing dirty-state functions now register independent `beforeunload` handlers only while their tracked forms are dirty. The browser owns the warning and its wording. Cancelling leaves the page and typed values intact; accepting leaves without saving those values. Reverting, successful save or explicit discard clears the applicable handler. Clearing a maintenance draft does not remove a retained incident warning. Read-only filters do not count as drafts. No new draft storage, autosave, backend mutation or equipment authority is introduced.

Verification passed in four disposable Chromium suites: the new native-exit exercise, existing incident-draft suite, existing planning/exercise-draft suite and the 18-page workspace suite at five widths. All 15 structure checks also passed. The new exercise covers clean/read-only reload, cancelled incident reload and tab close, accepted reload, concurrent incident/planning dirty state, independent guard cleanup, cancelled planning close and accepted close. It verifies unchanged incident revision, no created maintenance request and no draft marker in browser storage. Explicit browser contexts are used so tab-close tests do not force-close a convenience-owned context. The existing suites retain their in-app save, discard, conflict and exercise-baseline coverage.

Replay the new check with the repository's Playwright/Python test dependencies:

```text
node tests/browser_draft_exit.cjs
```

The browser workflow now runs this check explicitly. Native-exit behavior was observed in Chromium, not certified across all browsers or mobile operating systems. Warnings require browser support and prior user interaction. Forced termination, crashes, mobile process shutdown and arbitrary programmatic replacement can bypass them. This feature is not draft recovery or autosave and does not change authentication enforcement, account permissions, record approval or in-flight server operations. Hardware remains deferred; the original 30 products and pending physical/production acceptance are unchanged. No merge, deployment or live installation is included.
