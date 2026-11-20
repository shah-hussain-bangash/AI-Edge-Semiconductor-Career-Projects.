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

Administrators can read and act on all local incident exercises. Operators can create incidents and read/act on incidents they created or that are currently assigned to them. Only the incident creator or an administrator controls assignment. Auditors can read/export all local records and cannot create or change them. Each write requires authentication and CSRF, then rechecks the current session/account role inside the write transaction. The service has one local workspace; this is not production multi-tenant authorization.

Input is bounded and unknown fields are rejected. Only `source_type: synthetic` is accepted; measured/replayed claims, equipment commands and unknown assets are rejected. Maximum 1,000 incident exercises and 200 revisions per incident. Capacity limits reject new writes and retain existing records; no automatic deletion is enabled. List pages are bounded to 50 entries. History is bounded by the revision limit. Notes and evidence are displayed as escaped text, not executable HTML or active links.

## API

- `GET /api/incidents?state=all&q=&offset=0&limit=25`
- `GET /api/incidents/{id}` — current record and history
- `POST /api/incidents` — explicit synthetic exercise creation
- `POST /api/incidents/{id}/actions` — `expected_revision`, `action`, `note`, `evidence_refs`

All responses declare the synthetic scope, `hardware_connected: false`, `equipment_authorized: false`, `production_ready: false`, `automatic_detection: false` and `external_notifications_sent: false`. Resolving an exercise is a local record transition; it does not establish a repaired or safe machine. Evidence references are declarations, not independently verified files or calibration evidence.

## Accountable ownership and handoff

The creator or an administrator can explicitly assign an open/acknowledged synthetic incident to an enabled local Administrator or Operator account, reassign it or remove the assignment. The scoped candidate picker returns bounded eligible local account metadata only; auditors, disabled users and unknown ids cannot be selected. Auditors and assigned operators who did not create the incident cannot browse the candidate roster or forward ownership. Resolved or history-limited incidents do not expose assignment controls.

Assignment shares the incident with the selected operator. Its creator remains able to access it; creator identity and original observation never change. Assigned operators can acknowledge/resolve/reopen and prepare their own linked planning drafts under existing rules. Reassignment/removal ends the former assignee's current incident access immediately on subsequent requests, unless they are also the creator or have a wider administrative/audit read role. Their own planning records retain the source context captured while access was authorized, but current source metadata/links are withheld when no longer accessible. Another operator's private planning records are not revealed through incident assignment.

The Alert center can filter accessible records by assigned-to-me, created-by-me or unassigned. Counts respect the selected ownership view. Assignment changes consume an incident revision and record the actor, reason, timestamp and selected ownership in the same event/audit transaction. Stale/concurrent requests are rejected and failures roll back assignment, revision and history together. Existing incident states/assignments are not seeded or changed during installation. Earlier history without assignment data is labelled not recorded; it is not rewritten to invent ownership.

If an assigned account is disabled or changes to an ineligible role, its declared assignment remains visible as unavailable, with no silent reassignment. Its current account permissions/session revocation still apply. Creator/admin action is required to hand it off. Assignment does not send email/messages, dispatch a technician, establish identity/qualification, create an external work order or authorize equipment. Automatic escalation and operational SLA enforcement remain pending.

`GET /api/incidents/{id}/assignment-candidates` is restricted to creators/admins who can assign the current incident. `POST /api/incidents/{id}/assignment` accepts exactly `expected_revision`, `assignee_id` (or null to remove it) and `note`; authentication, CSRF, enabled target/role, session, revision and capacity are checked inside the serialized write transaction. The additive assignment table is included in diagnostics and backup/restore. Existing physical and production flags remain false.

Eleven API checks cover scoped visibility/planning, delegation restrictions, handoff revocation, disabled/auditor/unknown targets, concurrency, audit rollback, strict input/roles/CSRF, unavailable owners, truthful legacy history, actual backup/restore and session revocation. Chromium covers an explicit operator-to-operator handoff, ownership filters, stale-note preservation, source-context privacy after reassignment, auditor controls, roster outage/retry, contrast and five widths.

## Linked maintenance planning

An authorized writer can now prepare a maintenance draft directly from an open or acknowledged incident exercise. The writer supplies the proposed inspection explicitly. Creation binds the current incident revision, title, original observation, asset, severity, initial evidence references and timestamps in an immutable context snapshot. A synthetic draft is created in the existing maintenance workflow, with its ordinary creator ownership and independent review requirements.

The incident and plan show links in both directions. Planning details show the captured revision and whether the current incident has changed. The plan continues to refer to the captured context; later incident actions do not silently rewrite it or approve a new context. Review/approval is bound to the planning revision and captured incident context, not to future incident changes. Opening current source context is an explicit action. Approval does not resolve an incident, verify repair, authorize field work or deploy anything.

Only one linked plan per incident per creator is allowed, with at most 20 links per incident. An exact creation retry returns the existing draft/current plan, even after the incident changes; changed request content is rejected and the user must revise the existing plan through its normal revision flow. Stale incident revisions and new plans for resolved incidents are rejected. Reopen the exercise before preparing a new plan. A linked plan's asset cannot be reassigned. Other planning edits still clear earlier approval under existing rules.

`POST /api/incidents/{id}/maintenance-plan` accepts exactly `expected_revision` and `proposal`, requires CSRF, and rechecks current session/role inside the write transaction. Draft creation, link snapshot, initial plan history and both audit entries commit together or roll back together. Source incident state/revision is unchanged by creating a draft. Operator visibility respects both domains: another account's linked plan is not exposed merely because the operator can see the incident. Administrators/auditors retain their existing read scopes; auditors cannot create links. All links and captured context are retained by backup/restore and counted in diagnostics.

Nine additional API checks cover creation, concurrency/retry, stale/resolved input, role/CSRF/visibility, snapshot preservation and asset locking, independent review, audit rollback, backup/restore and strict input/capacity. Chromium verifies draft creation, navigation both ways, captured context, changed-source warnings and auditor controls as part of the incident workflow suite.

## Remaining operational work

Automatic correlation with real observations, deduplication of detected fault episodes, verified technician dispatch, operational SLA enforcement/escalations, notification delivery, maintenance execution/verification, authorized operational closure, real device/asset identity and deployed multi-tenant policy remain pending. This slice does not implement those capabilities or mark their readiness criteria complete.

## Verification

Ten API checks use disposable databases, including lifecycle persistence, role/CSRF/session enforcement, idempotency, concurrent/stale actions, strict input, capacity boundaries, rollback on audit failure and backup/restore. The separate Chromium suite covers reload persistence, escaped observation text, conflict-note preservation, resolution evidence, reopening/history/export, auditor controls, outage recovery, contrast and five widths.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_incidents.py -v
```

GitHub runs these checks and `tests/browser_incidents.cjs` against disposable stores. Consult actual current-head results; no hardware is connected or tested by these checks.

## Declared incident follow-up dates

Alerts now shows each incident's follow-up date and filters for overdue, upcoming or undated records. Open a record and choose Change follow-up date. The date editor explicitly uses UTC; leave it blank to remove the date. Past dates support synthetic overdue exercises. A reason is required for setting, changing or clearing a date. Creator, current assignee and administrator writers can change dates on unresolved records; auditors remain read-only.

Dates are normalized to UTC with an explicit offset required by the API. Status is calculated against the local service clock when read; refresh to update it. This clock is not verified device time. Resolved incidents retain their date but leave the overdue/upcoming filters; reopening may make an old date overdue again. No background scheduler, reminder, notification, escalation, dispatch, equipment operation or production SLA is implemented.

`POST /api/incidents/{id}/follow-up` accepts only `expected_revision`, `due_at` (ISO timestamp with offset, or null) and `note`. Dates range from 2000 through 2100. Authentication, CSRF, current session/role, scoped incident visibility, revision and history capacity are checked in the serialized transaction. Date, incident revision, event and audit commit atomically. No-op and stale writes are rejected; failed saves preserve browser input. Read operations never advance revisions. History and frozen planning context capture the declared date without a misleading live overdue status; older events explicitly identify unrecorded follow-up context. The additive table participates in diagnostics and private backup/restore. No existing incident is assigned a date during installation.

Ten API checks cover frozen planning dates, normalization, strict dates, filters and scope, clearing, resolved/reopened behavior, assignee/auditor permissions, CSRF/session/capacity, concurrent/no-op writes, rollback, truthful legacy history, read-only status evaluation and actual backup/restore. Chromium checks date persistence, overdue/undated views, clearing, stale edits and outage input preservation, auditor access, contrast and five widths. All fixtures are disposable synthetic data.

## Investigation log

Open an unresolved incident and select Add investigation update. Choose Progress update, Analysis note or Evidence reference, then supply the note and optional reference text. Evidence-reference entries require a reference. Saving adds an immutable application-history entry and advances the incident revision without changing its lifecycle state, initial observation, ownership or follow-up date. The UI retains notes/references on failures and stale writes. Earlier entries remain in Recorded history and in the record export; corrections require a new entry. Files are not uploaded, links are not activated and reference text is not independently verified. A local database administrator still controls the database; application history is not tamper-proof.

Creators, currently assigned operators and administrators can add updates. Auditors can read/export them. Resolved incidents require reopening before a new update; the shared 200-revision capacity applies. Current role/session, CSRF and scoped access are checked again under the write lock. No real investigation, diagnosis, repair, external communication or equipment action is performed by saving notes.

`POST /api/incidents/{id}/investigation` accepts exactly `request_key` (32 hex characters), `expected_revision`, `kind` (`update`, `analysis`, `evidence`), `note` (10–800 characters) and optional `evidence_refs` (up to 1,000 characters). Revision, history, audit and an actor-scoped retry identity commit together or roll back together. Exact retries return `created=false` and the original `update_revision`, plus the currently visible incident. Changed reuse of a key is rejected, including after a lost response. Access is rechecked before retry lookup; losing an assignment also removes retry access. No new notes are accepted for stale revisions or resolved/history-limited records. Exact retries of already committed notes remain readable under current write access without adding another entry.

The additive retry table is included in diagnostics and verified backup/restore. Existing records/history are not rewritten or seeded during installation. Captured planning context remains at its source revision and flags later investigation updates as changes. Ten API checks cover persistence, all update types, exact/concurrent retries and conflicting content, evidence/strict inputs, scoped roles, reassignment, CSRF/session/state/capacity, audit/key-write rollback, actual backup/restore and retained planning snapshots. Chromium checks persistence, escaped notes/references, missing evidence, a response lost after a successful commit, conflict-input preservation, history/export, auditor controls, contrast and five widths.


## Saved observation to incident

Telemetry now offers Create incident on each committed observation when the current administrator/operator can write and the binding's asset ID exactly matches a dashboard asset. The Device setup asset field suggests the existing dashboard IDs; arbitrary test-binding IDs remain supported, but are not silently mapped. Auditors see Read only. Unknown assets show Asset not in dashboard. No observation, threshold or model automatically creates an incident.

Select a row, review all six channels with units and declared quality, then supply a title, interpretation and severity. Saving revalidates the original source envelope, event identity, content hash, receipt, device/binding revision and immutable site/asset/device relationship inside the write transaction. It also validates the saved binding definition. Unknown, changed or corrupt sources fail without a partial case. A retired binding can supply historical context; its status/revision at capture remain explicit and do not imply a live device.

The new incident receives the source asset directly; callers cannot select a different asset or submit replacement readings. The capture retains all readings (including zero and null), source clock/gateway time/quality/calibration/session declarations, binding metadata, SI channel definitions, content hash and central receipt/commit identity. It excludes live age/freshness calculations. The source is frozen at capture, persists across reload, appears in the incident's export and is copied into later frozen maintenance-planning context. Open device history navigates to that device's current history rather than claiming to replay the old page. New readings do not rewrite the capture. If live source storage later fails verification, the previously saved capture remains historical declared context; it is not a fresh verification of that storage or physical evidence. A local database administrator can still change the database.

`POST /api/incidents/from-observation` accepts exactly `request_key`, `event_key`, `content_hash`, `title`, `observation` (the user's interpretation) and `severity`. Account/session/role and CSRF are rechecked under the write lock. Creation, source link/capture, initial incident history and both audit records commit atomically or roll back. One source-based incident per observation per creating account is allowed; subsequent work uses investigation updates. Exact creation retries return the existing incident even after later source/history changes; changed request-key reuse and duplicate creation with a new key are rejected. Each creator's ordinary incident visibility still applies; project-wide synthetic history access does not grant access to another operator's incident.

The additive source table participates in diagnostics and actual backup/restore. Existing incidents, source observations, bindings and credentials are not rewritten or seeded during installation. This is a manual synthetic investigation bridge, not automatic correlation/deduplication of detected fault episodes, physical diagnosis, notification delivery or equipment authorization. All hardware/production boundaries remain false and the same original 30 products remain planned.

Ten API checks cover all-channel/time/quality/identity capture, exact/concurrent retries and per-creator uniqueness, unknown/changed/corrupt sources, exact asset matching and binding-definition checks, retired context, roles/CSRF/current sessions, strict input/capacity, audit/link rollback, preserved captures and planning context, and actual backup/restore. Separate Chromium checks cover explicit creation, no automatic cases, lost-response retry, escaped interpretation, zero/null/clock provenance, reload/export, history navigation and cancel focus, stale-editor clearing, duplicate rejection, unmapped assets, auditor controls, contrast and five widths.
