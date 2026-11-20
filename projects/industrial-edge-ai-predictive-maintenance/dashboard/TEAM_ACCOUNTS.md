# Administrator-managed local accounts

Settings now includes **Accounts for independent review**, visible only to an authenticated administrator. This allows separate local accounts for the existing review workflows without database edits. No account, password, invitation or approval is created by installing this feature.

## Supported workflow

An administrator can create a local account with an email-form username, a selected role, an initial password of 14–256 characters (not entirely whitespace), a reason and their own current password. The browser asks for the initial password twice. Passwords are not trimmed, returned, displayed in history or stored in plaintext. The existing salted password-hashing function is used. Creation does not send email or establish that the named person or email owner was verified. Administrators must manage initial credential handover outside this application.

The supported local roles are:

| Role | Local capabilities |
| --- | --- |
| Administrator | Manage local account access, read local domain records and independently review another creator's submissions |
| Operator | Create and manage own incident, planning and documentation-exercise records within their existing scopes |
| Auditor | Read/export existing domain records under the existing read scopes; no writes and no team-management access |

No role enables physical equipment operation, real device enrollment or production acceptance.

Administrators can change role or enable/disable an account. Each action requires their current password, a substantive reason, CSRF and the expected account revision. All target-account sessions are revoked when access changes; self-changes end the current session. Disabling an account prevents sign-in and preserves its authored records and review history. There is no account-delete endpoint. At least one enabled administrator must remain; serialized transactions protect the last active administrator from disable/demotion.

## Credential and transaction boundaries

Current session, revocation and administrator role are checked again inside each write transaction. Administrator password failures are recorded without the attempted secret and limited to five failures per administrator in a 15-minute window. Denial records and their sanitized audit event persist even when the request is refused. A successfully committed account action clears that administrator's failure count. A rate-limited administrator must wait for the window to expire.

Role/access change, metadata history, session revocation and audit commit together. An audit failure rolls the account change back. Duplicate usernames are rejected without changing an existing password; a response-loss retry never silently resets credentials. If creation's result is uncertain, refresh the list and inspect the account before retrying.

The browser clears password fields after requests, on refresh and when the document becomes hidden. It does not save them in browser storage. Reason text is retained for rejected changes where possible; keep secrets out of reasons and other free-text fields. Existing hashes cannot be read through this API. A session or role error clears the displayed account controls on refresh. Changes are revision-checked; concurrent updates are rejected.

## History and recovery

New accounts start at metadata revision 1 with a creation event. Existing accounts are presented with baseline revision 1 and no invented creation date/history; their first managed change records revision 2. No existing password, role or access flag is rewritten during installation. Account metadata/history and reauthentication-denial tables are included in service diagnostics and the existing verified database backup/restore workflow. Restoring revokes sessions as before.

Limits are 100 local accounts and 200 managed revisions per account; capacity limits retain existing records and reject further creation/changes. Disabled accounts count toward the local account limit. Lists are paginated (maximum 50 per page). SQLite administrators can still alter local data; application history is not a tamper-proof identity service.

## API and remaining identity work

- `GET /api/team?q=&offset=0&limit=25`: administrator-only bounded metadata list.
- `GET /api/team/{id}`: administrator-only metadata and management history.
- `POST /api/team`: explicit local account creation.
- `POST /api/team/{id}`: role/access change with revision, reason and current administrator password.

Every response declares local scope and false invitation, identity-verification, hardware, equipment-authorization and production-readiness flags. Password recovery/reset/rotation, verified invitations, enterprise identity/MFA, identity lifecycle integration, distributed abuse protection, approved TLS deployment and emergency recovery remain pending. Changing a role does not retroactively rewrite earlier authorship or prove a reviewer's professional qualification. A demoted administrator retains captured context in their own plans, but source links hide current incident metadata outside their new operator scope.

Eleven API checks cover hashing/no secret responses, login, roles/CSRF/session revocation, password-denial persistence/rate limiting, last-admin protection, concurrent edits, demotion-safe source links, duplicate usernames, self-demotion, retained authorship, capacity, audit rollback and actual disposable backup/restore. Chromium covers explicit creation/sign-in, cleared password fields, last-admin protection, role-change revocation, history, non-admin visibility, outage/retry, contrast and five widths. Tests use disposable accounts only.
