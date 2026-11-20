# Saved synthetic incident workflow

Alert center now includes authenticated, persisted incident exercises. No records are seeded into an existing installation. Users create an exercise explicitly for one of the existing synthetic workspace assets. The original alert examples remain browser-session demonstrations and do not become saved incidents automatically.

## Implemented behavior

- Create an immutable initial observation with severity and optional evidence-reference text. Repeating the same creation key and payload returns the same record; conflicting reuse is rejected.
- Open → acknowledge → acknowledged → resolve → resolved. Reopening returns a resolved exercise to open, requiring acknowledgement again. Resolution requires an evidence reference and every step requires an explanation.
- Save each step, revision, actor, time, reference text and snapshot in an append-only application history, together with an audit entry in one transaction. No API deletes or rewrites past history. A database administrator still controls the local SQLite file; this is not a tamper-proof audit service.
- Reject stale revisions and simultaneous conflicting actions. The UI preserves a rejected action note so the operator can copy it before reopening the current record.
- Filter by state, search title/asset with literal wildcard characters, page through results, reopen records after reload and export a record with its complete bounded history.
- Include the two incident tables in service diagnostics and the existing verified backup/restore tool. Restoration preserves incident/history records and revokes sessions.

## Permissions and limits

Administrators can read and act on all local incident exercises. Operators can create, read and act on their own records. Auditors can read/export all local records and cannot create or change them. Each write requires authentication and CSRF, then rechecks the current session/account role inside the write transaction. The service has one local workspace; this is not production multi-tenant authorization.

Input is bounded and unknown fields are rejected. Only `source_type: synthetic` is accepted; measured/replayed claims, equipment commands and unknown assets are rejected. Maximum 1,000 incident exercises and 200 revisions per incident. Capacity limits reject new writes and retain existing records; no automatic deletion is enabled. List pages are bounded to 50 entries. History is bounded by the revision limit. Notes and evidence are displayed as escaped text, not executable HTML or active links.

## API

- `GET /api/incidents?state=all&q=&offset=0&limit=25`
- `GET /api/incidents/{id}` — current record and history
- `POST /api/incidents` — explicit synthetic exercise creation
- `POST /api/incidents/{id}/actions` — `expected_revision`, `action`, `note`, `evidence_refs`

All responses declare the synthetic scope, `hardware_connected: false`, `equipment_authorized: false`, `production_ready: false`, `automatic_detection: false` and `external_notifications_sent: false`. Resolving an exercise is a local record transition; it does not establish a repaired or safe machine. Evidence references are declarations, not independently verified files or calibration evidence.

## Remaining operational work

Automatic correlation with real observations, deduplication of detected fault episodes, assignment to other technicians, deadlines/escalations, notification delivery, maintenance execution/verification, authorized operational closure, real device/asset identity and deployed multi-tenant policy remain pending. This slice does not implement those capabilities or mark their readiness criteria complete.

## Verification

Ten API checks use disposable databases, including lifecycle persistence, role/CSRF/session enforcement, idempotency, concurrent/stale actions, strict input, capacity boundaries, rollback on audit failure and backup/restore. The separate Chromium suite covers reload persistence, escaped observation text, conflict-note preservation, resolution evidence, reopening/history/export, auditor controls, outage recovery, contrast and five widths.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_incidents.py -v
```

GitHub runs these checks and `tests/browser_incidents.cjs` against disposable stores. Consult actual current-head results; no hardware is connected or tested by these checks.
