# Local incident notifications

Alerts → My incident inbox is a working local integration for synthetic governed incidents.
Each signed-in administrator, operator or auditor can opt into exact severities for their own account.
No subscriptions are seeded. Saving a subscription applies only to future incident events.
Automatic threshold cases need their explicit human incident handoff before this route applies.

Incident events and notification outbox rows commit in one SQLite transaction. A unique recipient /
incident / revision key prevents duplicates. Every incident event action is eligible, including
creation, assignment, severity review and investigation changes. Current severity determines routing.
Only recipients who can currently view the incident are queued. This is an event history feed,
not on-call escalation, an external message transport or fault validation.

Select **Deliver queued notifications** for an explicit delivery pass of at most 100 items for
your own account. An administrator can also enable the dashboard-process worker below. Each pass rechecks subscription revision,
account-control revision, enabled account, current role and incident visibility. Invalid pending
items become suppressed, without being delivered. Retry is safe. Disabling or changing a
subscription cancels all its pending items. Delivered items remain subject to current access;
account-control revision changes invalidate old routes and hide old items until retained offline
review. Reconfirming a route creates a new generation, not a replay of older notifications.

Refresh is read-only. Pages contain up to 100 currently accessible delivered records. Per-account
outbox counts include suppressed rows but do not expose another recipient's information.
**Mark notification read** is idempotent and never acknowledges an incident. Opening an incident
uses its existing permission and unsaved-work guards. All writes require a current session and CSRF.
Subscription changes, nonempty delivery passes and first read marks are audited.

The global retention limit is 20,000 notification records. Nothing is automatically deleted.
If a routed incident change would exceed this limit, the entire incident transaction is refused
with 429; no partial incident or notification is saved. Retention/archive operations need a later
implementation before long-running deployment. Backups include the tables; restore disables
enabled subscriptions and suppresses pending deliveries while preserving history.

External SMTP, SMS, webhook providers, provider receipts,
escalation rosters and production acceptance remain pending. No local inbox delivery is evidence
that a person saw a message or that a real machine fault was detected.

## Automatic local delivery

Alerts → Automatic local inbox delivery shows saved pass status and administrator controls.
Automatic delivery is disabled by default. Enabling or pausing requires the current administrator
password, a reason and the latest configuration revision. Enabled settings survive normal restarts.
Changing the authorizing administrator's account-control revision, disabling them or removing
their admin role stops the worker until a newly authorized configuration is saved.

The supervised worker runs inside each dashboard process. A SQLite lease selects one current
owner; a write transaction serializes delivery with manual passes and incident/subscription
changes. Each pass processes at most 100 queued records across all recipients, at a configured
interval of 5–300 seconds. There is no external transport or installed operating-system service.
The dashboard must remain running. A fresh process can take over an expired lease after a crash;
graceful shutdown releases its own lease. Pause retains pending rows; manual delivery still works.

Status reports saved passes, cumulative delivery/cancellation counts and sanitized failures.
Refresh status explicitly; a recent pass is activity evidence, not proof of future uptime or human
receipt. A failed transaction rolls back all its delivery changes and retries through the supervisor.
If storage is unavailable, the last report becomes stale. Restoring a backup disables automatic
delivery and releases leases as well as disabling subscriptions and suppressing pending items.

## Overdue follow-up reminders

Alerts → Overdue follow-up reminders is a separate opt-in per local user. Enable an incident
subscription with exact severities first. The administrator-controlled automatic delivery worker
must be active to evaluate overdue dates. No reminder preferences or records are seeded.
Opting in includes currently overdue synthetic incidents that the recipient can currently access.
The local service clock determines whether the saved, normalized due date has passed.

The worker delivers one reminder per recipient and saved follow-up generation (incident ID,
due date and schedule-update timestamp). Unrelated incident edits do not create new reminders.
Reopening or resubscribing does not repeat the same saved schedule. Saving a different due date
creates a new generation, including when changing back to an earlier date. No recurring escalation,
on-call reassignment, external sends or human receipt is implied.

Every evaluation checks enabled accounts, current role/access, account-control revisions,
reminder preference and incident subscription generations, severity matching and incident state.
Resolved, cleared, rescheduled or inaccessible reminders are immediately excluded from the UI and
read actions. The worker later records their cancellation. Disabling reminder preferences cancels
their currently delivered rows. Read tracking never acknowledges incidents or changes due dates.
Reminder snapshots retain the source incident revision and severity at delivery; opening the
incident loads its current authorized state.

Reminder creation/cancellation and normal inbox delivery share the same atomic worker transaction
and global 100-change pass budget. Reminder changes are processed first. SQLite uniqueness prevents
duplicate reminders across concurrent/retried passes. Saved worker totals include both types of
delivery and cancellation; individual reminder rows retain their own due-date source.

All 10,000 reminder records are retained, including cancellations. At capacity, new reminders wait,
the dashboard displays a capacity warning and ordinary notification delivery continues. Archive
operations remain future work. Backup restoration disables reminder preferences and cancels
reminders while preserving their history. This remains a synthetic local integration requiring
production clock, uptime, retention, hardware and fault-policy acceptance.
