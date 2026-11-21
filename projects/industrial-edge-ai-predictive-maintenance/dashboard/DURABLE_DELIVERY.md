# Durable synthetic delivery - 20 November 2026

This slice adds a bounded SQLite delivery spool, conflict-aware local central ingestion and explicit durable receipts. It is tested with synthetic observations only. It is not hardware enrollment, MQTT broker integration, measured ingestion, production identity, factory availability, or deployment acceptance.

## Device workspace

After creating an active synthetic test binding, use **Load synthetic delivery example**. This fills the existing observation editor with a declared synthetic boot identity; it does not verify a physical boot. **Save editor observation to queue** returns edge-committed only after the spool transaction commits. It does not claim central commitment. **Run local delivery attempt** claims one due entry and invokes the same central commit function within the local service. Its outcome and receipt are then read from durable state. **Refresh delivery state** does not attempt transmission.

The local relay is explicitly in-process, not a network test. A separate loopback HTTP worker is provided below and exercised by automated tests. Queue state survives browser reload and process exit. The existing preflight-only path still accepts ambiguous boot identity for validation, but delivery requires a declared verified synthetic boot/session to make its dedupe key unambiguous. None of these synthetic declarations establish actual device trust, calibration or freshness.

## Commit boundaries and identity

- Edge committed: the independent spool database has committed an immutable source envelope. The web process can restart without losing this entry.
- Central committed: a central observation and stable receipt have committed in the dashboard database. Retries return the original receipt, not a second observation.
- Broker receipt: unavailable. No broker acknowledgment is fabricated.

The source key is device/boot/event-type/sequence within this single local project. The canonical content hash includes binding revision and the normalized observation, excluding the per-arrival gateway receipt timestamp. Changed content under an existing key returns conflict and never overwrites the original. Site/asset/source/transport bindings remain immutable and must be active at the exact revision. Retired bindings and revoked/unauthorized accounts fail closed even when a retry refers to prior data.

This is not multi-tenant scoping or cryptographic device authentication. Browser-style local account sessions and CSRF authorize the test APIs. The central commit timestamp is generated server-side; client observation/receipt timestamps are not assumed trustworthy or used to make a stale asset healthy. Central acceptance has no incident, maintenance, model, inference or equipment effect.

## Storage, retries and failure behavior

The spool defaults to delivery-spool.sqlite3 beside the configured dashboard database. EDGEOPS_DELIVERY_SPOOL_DB can explicitly select another private path. It uses SQLite WAL, synchronous FULL transactions, a 10,000-row limit and 32 MiB of serialized envelope payloads. These are application limits, not a guaranteed physical file/disk budget; indexes, SQLite pages and WAL require additional space. Central storage is independently capped at 10,000 observations for this local slice.

Delivered entries remain retained and count toward capacity. No automatic deletion, key expiration, retention reset or hidden replay is implemented. At capacity, new observations fail explicitly with no edge acceptance. Existing identical retries remain idempotent. Capacity must be reviewed and storage provisioned before sustained operation.

Each claim holds a random lease token for 45 seconds. Expired leases can be reclaimed; a previous worker cannot complete a claim owned by a newer worker. Transient transport/5xx/408/429 outcomes schedule exponential backoff capped at 300 seconds. Eight failed attempts result in a visible blocked entry; other 4xx denials and invalid/mismatched receipts block immediately. Arbitrary exception text and credentials are never stored as last_error. Blocked entries are retained for investigation; there is no automatic requeue or source-identity rewriting.

The UI relay makes one attempt per explicit action. The HTTP worker makes one attempt per invocation. Backoff is persisted, but retries require another invocation from an operator or separately managed supervisor; no unattended process or scheduler is automatically installed. After an abrupt crash, lease expiry allows a later worker invocation to recover the entry. A lost response after central commit produces an idempotent retry with the original receipt.

Edge and central stores are separate transactions. A response can be lost after an edge/central commit; retries reconcile by key/hash. Project audit writes are not a distributed transaction with the edge file. A SQLite/disk failure cannot return a successful new commit, but it may leave a durable entry whose HTTP acknowledgment was lost. The source must retry/reconcile; do not treat an unavailable response as proof the data was never committed.

## HTTP worker

Run from the dashboard folder against an explicitly configured local test server:

```powershell
.\.venv\Scripts\python.exe delivery_worker.py --spool .local/delivery-spool.sqlite3 --server http://127.0.0.1:8877
```

Supply EDGEOPS_DELIVERY_EMAIL and EDGEOPS_DELIVERY_PASSWORD through a private local environment using a suitable test account; do not save them in source, reports, screenshots or the spool. The worker creates a short-lived authenticated session, sends a due envelope with CSRF and attempts logout afterward. It accepts only explicit loopback HTTP origins, disables environmental proxies and redirects, and has a request timeout. Failed authentication leaves the queue untouched. This is a local development worker; production requires separate scoped device/service credentials, TLS transport, secret rotation, supervision and network policy. No worker is started against the user's live installation automatically.

## API surface

| Route | Meaning |
| --- | --- |
| POST /api/acquisition/queue | Admin/operator, CSRF, current role and active binding; edge-committed after spool persistence |
| POST /api/acquisition/ingest | Admin/operator, CSRF, current role and binding; 201 new central commit, 200 identical retry, 409 conflicting content |
| POST /api/acquisition/deliver-once | Authorized local in-process test attempt; no network/hardware claim |
| GET /api/acquisition/delivery | Supported authenticated roles; bounded paged queue outcomes (default 20, limit 1-100), queue counts and central record count |

All responses retain synthetic scope, production_ready=false, hardware_connected=false, equipment_authorized=false and model_deployed=false. The separate preflight response continues to report observation_persisted=false; queue/ingest use their own explicit receipt tier instead.

## Backup and verification

The recovery tool now accepts **--delivery-spool** when that file exists. Include both the configured dashboard database and spool plus required offline reports. Restoring preserves queue states and source keys; inflight entries wait for lease expiry before another attempt. Per-store snapshots are not an atomic cross-store recovery point. Stop writers for a coordinated snapshot and reconcile pending/committed identities after a real cutover. Existing authentication/session-revocation rules still apply. See RECOVERY.md.

Tests cover restart, abrupt process exit, WAL recovery, backup/restore of an inflight entry, lost response after central commit, canonical retry hashing, conflicts, concurrent claims, stale-worker fencing, bounded capacity, read-only write failure, retry exhaustion, malformed receipts, role/retirement denial and a separate real HTTP server/worker. These are local synthetic tests, not real network outage duration, physical disk-full, power-loss hardware or industrial reliability acceptance. Next work includes supervised edge/service identity and broker integration, operational telemetry queries/freshness and qualified measured-device integration.


## Read-only saved outcome inspection

Each loaded delivery-history row now offers Inspect outcome for every supported reader, including auditors. It opens the exact loaded queue row without another service read or a delivery action. The full event key, attempt count, saved failure code and any central receipt remain separate from the browser response-load time. Pending, inflight and blocked descriptions do not invent retry times, running workers or absence from central storage after a lost response. A delivered entry shows the saved receipt tier, ID, content hash, commit timestamp and matching event key; it is not a new verification of central storage or hardware health.

Inspection requires the expected synthetic scope and false hardware/equipment/production/model flags. A delivered row requires a parseable, matching central-committed receipt with supported identities, timezone-qualified commit time and unchanged boundary flags. Inconsistent/non-delivered receipts or malformed state refuse inspection/export. This is consistency checking of a loaded status record; the API does not expose the source envelope or binding here, so the browser cannot independently recompute a content hash or infer device/asset identity. No broker receipt is created.

Export this saved outcome retains the exact status row, original receipt string, parsed receipt, reported counts/limits/retention/relay mode and distinct browser load/generation times. The service does not provide an as_of timestamp on this endpoint; the browser does not invent one. Queue counts cover all retained entries while only the selected page is returned; central count is obtained separately and is not an atomic cross-store snapshot. Payload limits do not include SQLite/index/WAL overhead. Export is read-only, synthetic, false equipment/hardware/production/model authority, with live_requery_performed=false. No observation payload, actor or credentials are included.

Refresh, a failed request and newer page loads close old inspection content and export authority. Close/Escape clears immediately and restores focus; old queued close events do not clear a reopened dialog. An unsaved observation editor remains unchanged by inspection. The change adds no route/schema, retry/requeue command, hardware product or acceptance decision. Disposable browser checks cover real pending/delivered/blocked records and saved receipts, a claimed inflight entry, lost-response-safe wording, exact export, role access, malformed/mismatched fixtures, escaped codes, loading/outage/concurrent-response clearing, new arrivals, draft retention, keyboard/focus, contrast and five widths.


## Browsing older retained queue entries

Device → Saved queue & commit receipts now has Older entries and Newest entries. Refresh and successful explicit queue/attempt actions return to the newest page. Each page contains at most 20 entries in the dashboard; global queue counts still cover every retained entry. A historical page does not become the current queue or a historical reconstruction of its states: each read shows saved states when that read ran. New arrivals do not silently replace the currently loaded page or its receipt export.

GET /api/acquisition/delivery accepts an optional opaque before cursor and a limit from 1 to 100 (default 20). The response page object contains limit, the requested before position, next_before and order=created-desc-event-asc. Ordering preserves the previous newest-created-first/event-identity-ascending tie break. Cursors encode version, creation time and event identity, are bounded and validated, and represent navigation positions rather than authorization or signed evidence. Queue counts and the selected rows share one read transaction in the spool. Central count is read separately, so this is not a cross-store atomic snapshot.

Keyset paging excludes already traversed positions when new newer entries arrive, including deterministic behavior for tied creation times. It is not a frozen multi-page snapshot: independently added older-position entries and state changes may appear in later reads. No automatic deletion or retention change is introduced. A new delivery_history index supports the traversal without altering existing rows. Receipt export includes the exact reported history page metadata and original browser load time; page context does not create a server snapshot timestamp.

Paging and refresh immediately clear old rows, close old receipt inspection/export content and disable stale page controls until a request succeeds. Outage clears old results; Refresh retries from the newest page. Late responses cannot overwrite a newer request. Observation editor drafts stay intact. Auditors retain the same read access and receive no write controls. Backend checks cover ties/new arrivals, mutable outcomes and global counts, empty/terminal/reopened pages, malformed/bounded cursors/limits, supported reader roles and denial without authentication. Browser checks cover browsing beyond 20, exact older-row inspection/export, new arrivals, draft preservation, outage/retry/loading/stale-response clearing, keyboard, contrast and five widths. No worker, retry, command, new hardware product or acceptance decision is added.
