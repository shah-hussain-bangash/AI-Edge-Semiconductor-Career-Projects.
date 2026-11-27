# Local operational dashboard

This release adds working local workflows to the existing full dashboard. It preserves the original 30-product catalog and the lightweight home USB application. It does not certify a complete industrial production deployment. Hosting remains deferred; physical verification remains pending.

Open the full dashboard at `http://127.0.0.1:8877/app?view=registered` after the full server has been updated and started. In Overview, choose **Registered observation records** to see retained gateway records instead of the demonstration fleet. The registered-data link keeps that selection through email/password sign-in. An empty registry stays empty. Select **Demonstration** to return to the existing exercises. A source-view preference never changes permissions or promotes a fixture into a measurement.

## Coverage of the 14 remaining areas

| Area | Working local capability and location | Remaining acceptance or external work |
| --- | --- | --- |
| 1. Unified data views | Overview, Assets and Telemetry use exact registered device/source mappings, latest retained runs, SI units, zero values and unavailable-channel gaps. | Device identity, calibration, clock quality and sustained real input need independent evidence. Existing historical exercise services retain their synthetic provenance. |
| 2. Asset/device lifecycle | Assets registers site/asset/device mappings; retirement disables associated policies and preserves history. Devices offers explicit review policies. | Provisioning, inventory reconciliation and managed fleet identity are not connected. |
| 3. Automatic review cases | Opt-in threshold policies consume only new matching-source inserts, deduplicate by host-frame bucket and retain first/last inputs. Alerts supports assignment, acknowledgement and resolution. | Thresholds need engineering review. These are threshold reviews, not diagnoses or equipment commands. |
| 4. Maintenance workflow | Maintenance saves case-linked work records with frozen, hashed case context, submission, independent approval, assigned start/completion and independent closure. Revision checks prevent stale decisions. Assignment forms list active local administrators/operators by email and role; account eligibility is checked again when saving. | No CMMS dispatch, equipment authorization or physical-work certification. |
| 5. Notifications | Settings provides a per-user durable inbox. Optional TLS SMTP has bounded retries, persistent leases, access rechecks and a separate worker. | SMTP is unconfigured and disabled by default. No email provider has been selected or tested. Fixtures never send external email. SMTP is at least once; a lost response may produce duplicates. |
| 6. Baseline studies | Models fits a bounded single-channel statistical baseline from 3–10 distinct retained runs, with chronological training, validation and untouched holdout partitions. Reports retain input hashes and deviations. | Distinct host runs do not prove independent physical sessions. No labelled fault accuracy, RUL, drift acceptance or qualified predictive-maintenance model is claimed. |
| 7. Runtime scoring | A different administrator activates an exact hash-bound baseline. New matching-source inputs produce retained scalar scores or unavailable outcomes. Retirement and independently reviewed rollback are available. | This standard-library statistical baseline is not a deployed ONNX/deep-learning model. No automatic maintenance or equipment action follows a score. |
| 8. Governed guidance | Knowledge offers role-scoped source drafts, declared content rights, immutable revisions, independent approval, replacement and retirement. Insights searches approved accessible text, cites revision/hash and abstains without matches. | This is extractive local search, without an LLM, external tools or autonomous advice. Source rights still require human verification. |
| 9. Account protection | Existing email/password sign-in remains. Settings optionally enrolls encrypted TOTP, confirms a fresh code and displays one-use recovery codes. Persistent replay and attempt guards apply. | SSO, identity-provider integration, distributed abuse protection and managed key custody are not connected. MFA remains opt-in; no existing user is enrolled automatically. |
| 10. Evidence and persistence | Cases/work records accept bounded private evidence files with hashes, authenticated downloads, source context and frozen completion stages. A schema journal checks the new local component. | SQLite remains a single-node store. Files are not malware scanned; there is no object-storage/HA migration or file-safety certification. |
| 11. Observability | Settings shows database checks, schema fingerprint, bounded request metrics, record counts, worker heartbeat and jobs. Authenticated metrics export uses fixed labels without account/device identifiers. | No external metrics collector, uptime service, SLO, paging route or managed service is installed. |
| 12. Reviewed releases | Settings exports a clean committed source bundle. CLI verifies hashes/inventory and unpacks into a new folder only. Payload comes from the recorded Git commit, independent of checkout line endings. | Packaging is not deployment. Dependencies, migrations, canary acceptance and cutover remain explicit operator work. Hashes detect mismatch; they are not a release-signing trust system. |
| 13. Protected recovery | Settings queues encrypted SQLite backup jobs and an opt-in interval policy. The worker creates verified snapshots. CLI authenticates/decrypts and restores to a new directory. | A running worker and private key/output directory are required. There is no managed OS service, off-machine key escrow or accepted RPO/RTO. Home USB data is separate. |
| 14. Retention and governance | Settings previews exact hashed targets for old read terminal notifications or baseline scores. A different administrator applies the reviewed deletion. Knowledge retains immutable document revisions and declared rights. | Broader evidence/raw-record deletion, legal holds, organization retention approval and deletion of external backup copies remain separate procedures. |

The preparation/readiness register remains an evidence register. These new capabilities do not automatically mark its criteria accepted. Installation enables no threshold policy, model, email route, MFA enrollment, backup schedule or retention deletion.

## Live local capability checks

Production readiness now includes a **Local capability checks** panel covering all 14 software areas. It reads the current local database and configuration presence, shows the next review for each area, and links to the related workspace. Use the filter to find configuration, missing records, review work or optional account protection. Labels describe local next steps; they are not acceptance grades or an implementation percentage.

Refresh after making changes and check the observation timestamp. Fixture runs and gateway-declared measurement runs remain separate; the latter remain unverified. Model artifacts are integrity-checked; current scoring releases and approved guidance use their existing authority checks. Study counts also include retained candidates and retired versions. The panel never contacts an email provider, tests a physical device, builds a release or runs a worker.

Case/work/evidence counts follow the signed-in account's existing visibility. Authenticator status is for the current account only. Detailed service, recovery and retention observations are restricted to administrators/auditors. Export includes these same account-scoped observations, without passwords, private paths, provider settings, source text or control secrets. Treat the JSON as local operational information.

**Export local observations** is separate from the existing 53-criterion register export. The new read-only endpoint is `GET /api/production-readiness/local-capabilities`; it saves no acceptance records. If checks fail, old cards and their export are cleared while the independent acceptance register remains available. No status is promoted to production acceptance automatically.

## Full-dashboard setup and update

The [local process manager](LOCAL_DASHBOARD_CONTROL.md) adds background/foreground startup, status and graceful shutdown for the full dashboard. It avoids PID-based stopping and checks port ownership before initializing the application.

Use Python **3.12–3.14**, with 3.12 as the reference. The full runtime is pinned in `requirements-runtime.txt` and `requirements-security.txt`; optional laboratory ML/MQTT requirements remain separate. No Docker, local training, serial connection or external email is needed to use these screens. The 4 GB Mac should continue using [lightweight home mode](../HOME_MAC.md) unless the full local dashboard is explicitly desired. The full dashboard and home mode have separate servers and databases.

For an existing installation: inspect `git status --short`; preserve local edits before updating. Stop only the identified server you intend to update. Record the configured database, artifact and spool locations, then use [the existing backup runbook](RECOVERY.md). Verify the backup before first startup of this version, which adds tables in a transaction. Retain the prior source and environment for rollback. Do not run two server versions against one database. Changing bootstrap environment variables does not reset existing credentials.

From the project’s `dashboard` directory on Windows PowerShell:

```powershell
py -3.12 -m venv .venv-operations
.\.venv-operations\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-operations\Scripts\python.exe -m pip check
.\.venv-operations\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8877
```

For a new full-dashboard installation on macOS Terminal:

```bash
python3.12 -m venv .venv-operations
./.venv-operations/bin/python -m pip install -r requirements.txt
./.venv-operations/bin/python -m pip check
./.venv-operations/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8877
```

For independent reviews, an administrator must create a separate reviewer account through Settings → Local team accounts; the creator cannot approve their own work. No extra accounts or passwords are generated automatically. Local operators can see the minimal active assignment directory (email, role and identifier); auditors receive no assignment directory. Disabled accounts disappear on refresh.

A fresh database requires `EDGEOPS_ADMIN_EMAIL` and a unique `EDGEOPS_ADMIN_PASSWORD` of at least 14 characters in the private process environment, as described in [README](README.md). Existing databases preserve their accounts. Neither the example environment file nor real secrets are automatically loaded from Git. Keep the server on loopback; remote HTTPS, proxy trust, identity and shared rate limits require a separately reviewed deployment. Stop with **Ctrl+C** in that server’s terminal. If a port is occupied, identify its process and existing URL before starting another server.

## Private key, optional MFA and backup configuration

Keep the encryption key outside the checkout and outside backup archives. Create an existing owner-controlled private directory first. From `dashboard`, this creates a new key file without printing its content:

```text
python private_crypto.py generate --output <absolute-private-key-file>
```

Use the virtual environment’s Python executable in place of `python`. Set `EDGEOPS_PRIVATE_KEY_FILE` privately for both server and worker. POSIX key permissions must be owner-only; Windows ACLs must be restricted by the administrator and are not independently checked by this tool. Back up the key through a separate controlled channel: losing it prevents seed decryption and backup recovery; disclosure exposes both. Key rotation, escrow and custody acceptance are not automated. MFA recovery codes work independently of seed decryption and must be stored privately.

In Settings → Account protection, use your own password to begin enrollment, add the displayed secret/URI to an authenticator, then confirm a fresh code. Store the displayed recovery codes once. Enrollment/disable requires HTTPS or actual loopback and revokes other browser sessions. Never paste secrets or recovery codes into this chat, Git or issue reports.

For encrypted backups, also set `EDGEOPS_PROTECTED_BACKUP_DIR` to an existing protected directory outside Git. Optional `EDGEOPS_OFFLINE_EXPERIMENT_ROOT` and `EDGEOPS_BACKUP_DELIVERY_SPOOL` include those explicitly configured stores. Home-mode data is never implicitly included. Additional stores are verified individually; no coordinated cross-store snapshot is promised. Each protected payload is bounded to **64 MiB**; reaching the bound fails visibly instead of silently omitting data.

Queue a job or enable the interval policy in Settings only after storage/key readiness is shown. A pending job can be cancelled before a worker claims it. To execute configured jobs and email, run a separate foreground worker with the same private environment and database path:

```text
python platform_worker.py --once
python platform_worker.py --loop --interval-seconds 60
```

Use one worker per local installation. Stop the loop with Ctrl+C. Installation does not register or start a background service. Schedules run only while the worker is running. A lease expires after an interrupted pass; an existing encrypted output blocks a retry for reconciliation instead of being overwritten. Inspect Settings for `completed`, `failed` or `blocked`; a queued job is not a successful backup.

Offline recovery, into new private directories only:

```text
python protected_recovery.py unseal --source <encrypted-file> --key <private-key-file> --output <new-decrypted-directory>
python recovery.py verify <new-decrypted-directory>/backup
python recovery.py restore <new-decrypted-directory>/backup --output <another-new-runtime-directory>
```

Restore revokes browser/service/bench credentials and disables active review policies, models, outbound email, reminders and backup schedules/jobs in the restored copy. Reconcile source, data and roles before deliberately re-enabling anything. Do not replace a running live database. Protect/delete decrypted staging data through the local retention procedure; it contains private account and evidence information.

## Optional email

Choose a service separately; do not enter SMTP passwords into dashboard forms. Configure `EDGEOPS_SMTP_HOST`, `EDGEOPS_SMTP_PORT`, `EDGEOPS_SMTP_TLS` (`starttls` or `ssl`), `EDGEOPS_SMTP_USERNAME`, `EDGEOPS_SMTP_PASSWORD` and `EDGEOPS_SMTP_FROM` through the private process environment. The server must see configuration to enable the policy; the worker needs it to send. TLS certificate validation and authentication are required. Delivery sends a minimal notice ID, source and recorded event time, not private evidence files or raw notes. Delayed delivery is labelled. Review recipients and queued records before enabling an external route. No provider delivery is certified by software mocks.

## Receipt timing and historical case evidence

Assets shows receipt timing calculated against the server's observation timestamp at the last refresh, rather than the browser's wall clock. The 15-second window is a display convention, not an accepted sampling rate, alarm target or production service level. A recent server receipt can still be labelled delayed when the gateway-declared receipt time is more than 15 seconds earlier. Future-dated times beyond a five-second tolerance, invalid timing and absent data are labelled separately. Gateway and sensor acquisition clocks remain unverified.

Refresh operational records, or enable the visible 5-second refresh option, to obtain a new snapshot. A static page does not prove ongoing freshness. Valid numeric zero remains zero; channels marked invalid remain unavailable even if the server receipt is recent. No receipt label establishes cable connectivity, calibration or equipment health.

Alerts labels captured threshold crossings as historical evidence and shows the run, saved host-frame endpoints and capture receipt timestamp. **Review retained telemetry** switches to registered data and selects the associated available mapping; it clears the selection if that mapping is unavailable. New matched updates keep first/last captures in host-frame order even when HTTP arrivals are out of order. Duplicate retries still do not increment matched-record counts. Host-frame order is not a verified device clock or sampling frequency.

This forward-processing fix does not replay or bulk-repair older case histories. Retained raw readings remain available for a separate historical review. Existing work records retain their original captured case context and hash. New readings neither automatically resolve cases nor verify physical work.

## Evidence, studies, retention and release procedure

Evidence is stored inside SQLite: at most 2 MiB per supported file, 256 files and 32 MiB total. Type/signature/text validation does not establish safety. Downloads are forced attachments with `nosniff`; do not open untrusted files without a separate scanning procedure. Upload retries with the same record, name, media type and content are deduplicated. Resolution or work completion freezes additional uploads; retained files remain available to currently authorized users. No public file links are issued.

Before fitting a study, register the exact source lane and collect distinct retained runs. Check validity flags and session provenance. Fit uses only training runs for mean/scale, validation for threshold choice, then reports holdout deviations without tuning on holdout. The baseline artifact binds the study-report hash. Another active administrator must approve the exact artifact hash. Retiring a mapping or changing the approving account invalidates scoring authority. Software fixtures stay explicitly labelled throughout.

Retention preview never deletes data. A separate administrator must reauthenticate and confirm the exact plan hash. Targets changed after preview cause a conflict. Backup copies, raw readings, case/work histories and evidence files are not deleted by this feature.

Source packaging requires Git and a clean tracked checkout. Settings → Platform operations downloads a verified source ZIP. Alternatively:

```text
python release_bundle.py build --output <new-source-zip>
python release_bundle.py verify --source <source-zip>
python release_bundle.py unpack --source <source-zip> --output <new-install-directory>
```

Unpacking installs no dependencies and changes no live service or database. Inspect the manifest, compare its commit with the reviewed GitHub commit, create a separate environment, verify a restored private data copy, then plan a stopped-service cutover. Roll back with the prior environment/source and the verified pre-update backup; do not assume older code accepts a newer schema.

## Verification boundaries

New unit tests exercise policies, atomic deduplication, source/role isolation, frozen work context, independent review, guided search/abstention, mocked TLS SMTP, statistical splits/integrity/rollback, encrypted MFA/replay/recovery, protected backups, schema drift, retention and source bundles. Evidence tests cover permissions, deduplication, freeze, malformed formats, tampering and actual byte limits including chunked uploads. Browser fixtures exercise real forms with separate administrator/reviewer/operator accounts, evidence upload/download, workflow closure, baseline activation/scoring, registered telemetry, outages and five viewport widths. All use disposable data; no live credentials, physical board, external email or hosting are used.

The `EDGEOPS local operational platform` workflow runs focused contracts on Windows, Intel macOS and Linux with Python 3.12/3.14, plus a Linux browser check. Existing home and dashboard workflows remain applicable. See the release’s Actions results for the tested commit. Automated checks do not certify macOS Monterey hardware behavior, production scale, safety or industrial acceptance.
