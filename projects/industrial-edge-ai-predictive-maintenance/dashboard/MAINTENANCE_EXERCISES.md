# Synthetic maintenance documentation exercises

An independently approved maintenance plan can now lead to a saved documentation exercise. This prepares notes, evidence-reference handling and independent review before hardware commissioning. It does not implement technician dispatch, physical execution, machine isolation, permits, repair verification or operational closure.

## Workflow

1. The plan creator explicitly selects **Prepare documentation exercise** from the current approved plan. No records are seeded and no field job is issued. Only one exercise can be created for each approved plan revision; exact retries return the existing record.
2. The exercise retains an immutable snapshot of the approved plan, its approval references and any captured source incident context. The initial record is a draft and makes no physical-work claim.
3. The creator records synthetic work notes, a synthetic outcome and declared evidence-reference text. An outcome and nonblank references are required before submission.
4. A different local administrator reviews the submitted exercise and accepts or rejects the documentation, with a reason. The creator cannot review their own exercise, including when their account is an administrator. The state named `verified` means the synthetic documentation exercise was reviewed; it never establishes verified physical work.
5. The creator can withdraw a submitted exercise. Editing a rejected or reviewed exercise returns it to draft, clears its previous reviewer/decision and retains earlier notes/references in history. Submission freezes editing until withdrawal or review.

Exercise and plan states remain separate. Reviewing an exercise does not resolve the source incident, approve a changed plan, authorize equipment work or qualify a production release.

## Plan revisions and visibility

Creating, editing, submitting and reviewing an exercise require the captured approved plan revision to remain current and approved. A later plan edit makes the earlier exercise historical, even if it was reviewed. Its frozen snapshot and history are retained; no evidence is silently moved to another revision. Withdrawal remains available to the creator for a stale submitted record. After the revised plan is independently approved, its creator may prepare a new exercise for that new approved revision.

Incident context remains the context already captured in the plan. Later incident changes do not rewrite that snapshot. Exercise review concerns only the submitted synthetic documentation and its captured planning context.

Operators can view their own exercises, create them only for their own approved plans and edit/submit/withdraw their own records. Administrators can read all local records and independently review another creator's submitted exercise, but cannot rewrite another creator's notes. Auditors can read/export all local records and have no write permission. Authentication, CSRF, role and session revocation are checked inside serialized write transactions. This is the existing single local workspace, not production multi-tenant authorization.

## Evidence, history and recovery

Notes and reference strings are recorded as declarations; no file upload, independent document authentication, calibration acceptance or physical inspection is implemented. Text is escaped when displayed. Each event records the actor, time, explanation and a snapshot of notes/outcome/references. Earlier contents can be inspected in history and are included in export. Database administrators still control SQLite; the journal is not tamper-proof.

State change, history and audit share one transaction. Audit failure rolls back the change. Expected revisions reject stale/concurrent writes. Limits are 50 exercises per plan and 100 revisions per exercise, with no automatic deletion. Plan details return compact exercise summaries; full bounded notes/history are loaded explicitly. Diagnostics count the two new tables, and the existing verified backup/restore tool preserves them while revoking restored sessions.

## API and permanent boundaries

- `POST /api/maintenance-requests/{id}/exercises`: `expected_plan_revision` only.
- `GET /api/maintenance-exercises/{id}`: current record, captured approved plan and history.
- `PUT /api/maintenance-exercises/{id}`: `expected_revision`, `work_note`, `outcome`, `evidence_refs`.
- `POST /api/maintenance-exercises/{id}/actions`: `expected_revision`, `action` (`submit`, `withdraw`, `verify`, `reject`) and `note`.

Unknown fields and physical-work claims are rejected. Every exercise response declares the synthetic scope and `hardware_connected: false`, `equipment_authorized: false`, `execution_enabled: false`, `physical_work_verified: false` and `production_ready: false`, including after documentation review.

Ten API checks cover approved-plan/creator gates, duplicate creation, independent review, source-plan invalidation, edit invalidation, input/evidence/CSRF/session permissions, bounded history, audit rollback and real disposable backup/restore. Chromium checks cover the complete documentation flow, escaped notes, concurrent conflicts with preserved explanations, export, auditor controls, plan-change guards, outage behavior, contrast and five widths. All checks use disposable synthetic stores and no physical device.

The same 30 selected products and existing firmware pins remain unchanged. Exact received-part inspection, real acquisition, measured ingestion, qualified work execution and independent physical acceptance remain pending.
