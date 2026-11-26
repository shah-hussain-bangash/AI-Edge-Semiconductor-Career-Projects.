# Mac gateway handoff verification — 26 November 2026


## Local recovery and handoff completion

Hosting remains deferred by owner choice. Added cold backups/verified new-folder restore, incomplete-restore launch blocking, persisted recording browsing/downloads, explicit monitoring-only retry with backoff, sensor-only office CSV/raw/provenance packages, and an opt-in per-user Mac login service that never automatically opens USB. The shutdown acknowledgment timeout is 8 s; a delayed-response test covers the prior 2 s gap. Private datasets and original source are not overwritten. Backup limits and checksum scope are documented in LOCAL_RECOVERY.md; LOCAL_READINESS.md preserves the unfulfilled physical/AI/production criteria.

Local Windows/Python 3.12: 72 unittest methods discovered, 67 passed and five POSIX-only methods skipped. Coverage includes cold-lock/no-overwrite backup, SQLite-consistent snapshots, checksum/schema/path/corruption checks, incomplete captures and failed restores, historical HTTP downloads, no-demo sensor export, milliamp/quality semantics, opt-in retry/new-attempt IDs, storage-error refusal, cancelled backoff and service-plan safety. Chromium passed source/zero/null/history, current/session/raw exports, archived packages, outage clearing, five viewport widths and contrast checks. Shell/PowerShell syntax and guide relative links were checked. A proxy-environment test now uses a separate subprocess so Windows empty Git environment values are not disturbed in the parent process.

The GitHub workflow runs the full suite on supported Python/Linux/hosted Intel macOS and Windows, validates Mac plists without requiring installation, and exercises native Windows data actions. A disposable Mac CI service lifecycle runs only when a GUI launchd domain exists; otherwise it explicitly reports loading unverified. It never opens serial. The POSIX SIGTERM test uses a pseudo-terminal fixture and checks raw-record finalization, not an ESP32 or a physical power-loss test. No owner's Mac service has been installed, and no hardware acceptance was promoted. Real calibration, motor commissioning, real-data model/operational integration and full production acceptance remain pending; data export does not complete them.

## Graceful office demo lifecycle preparation

Added read-only Status and graceful demo-only Stop to the Windows launcher, with equivalent standard-library CLI actions. A supported server reports a per-start nonce and a hash binding its checkout/data directory; these are local mismatch guards, not remote authentication. Shutdown requires Host/origin/token/nonce checks and atomically refuses USB/recording sessions or reader starts during shutdown. The client ignores proxies, refuses redirects and waits for the existing lock to release. Legacy/other-checkout/custom-directory mismatches are preserved; there is no PID kill or lock deletion fallback.

Nine local Windows Python 3.12 lifecycle tests passed against disposable loopback servers, covering token redaction/read-only status, graceful exit/history preservation, different checkout/data refusal, USB-mode preservation without opening a port, legacy refusal, ignored proxy settings, redirect refusal, HTTP auth/nonce/origin rejection a reader-start race guard and a no-reverse-DNS startup assertion. Hosted Intel macOS exposed a blocking getfqdn call in Python HTTPServer.server_bind; the home server now binds numeric loopback directly and uses a fixed localhost server name, without changing machine DNS configuration. Existing suite/browser checks remain separate. The GitHub Windows job additionally exercises the actual native wrapper in PowerShell 5.1 and 7 using only disposable CI demo processes. No current office server or Mac/ESP32 hardware was stopped or verified for this source-preparation change. The one-time legacy upgrade procedure remains documented.

## Office/daytime and home/night setup clarification

Owner clarification, 26 November 2026: the owner is at the office Windows PC and does not have the MacBook available. Fresh MacBook preflight, current ESP32 connection and physical measurements remain **PENDING**. Earlier reported upload/text-test success stays prior owner evidence; no new hardware result was obtained.

Added START_HERE.md, separate OFFICE_WINDOWS.md and TONIGHT_MAC.md guides, guarded first-clone commands and a read-only home_preflight.command. The report does not open serial, execute Git/Apple's Python stub, install packages, create environments, change configuration or promote acceptance. Three targeted tests passed locally using Git Bash, simulated host metadata and an isolated actual Python version probe; they cover wrong-host refusal, missing Python and unchanged project/private files. Windows documentation command blocks passed PowerShell parsing; Mac documentation shell blocks and the helper passed Bash syntax checks. These checks are not a Monterey or ESP32 test. No running office server or private runtime was changed for this documentation/preflight handoff.

## Timed raw USB recording addition

Added a 10–600 second bounded recording action with exact serial-read bytes, offset/classification/sample index, measured host monotonic timing, explicit duration/manual/error/limit reasons, durable private files, checksums and offline parser replay verification. Recorder source digest is recorded; firmware identity, hardware authenticity, calibration and physical acceptance remain unverified. Demo mode cannot create a USB capture. The raw package is distinct from the earlier derived rolling-session package; failed/incomplete storage is never downloadable as a finalized capture.

Local Windows/Python 3.12: 35 methods discovered, 32 passed and three POSIX-only methods skipped. New tests cover fragmented input, diagnostics, invalid UTF-8, trailing partial bytes, a virtual 600-second deadline (no physical timed test), unplug, byte/chunk limits, storage failure, no-overwrite behavior, corruption/reclassification refusal, raw sensor JSON zero/null/amp semantics, oversized-line resynchronization, strict HTTP/auth/origin boundaries, stop/download lifecycle and fake serial recordings. Hosted Linux/Intel macOS additionally run a real pySerial pseudo-terminal recording over HTTP. Browser checks include demo recording refusal, failed USB-open behavior and the prior viewport/contrast/source/export checks. No received board, actual sensor, real ten-minute recording or home MacBook was used.

The actual commit's GitHub Actions results determine CI outcomes; workflow configuration alone is not evidence. H1 physical rows remain pending regardless of a successful software recording/package check.

## Bench bring-up implementation addition

Added native Windows `home.ps1` (Setup/Check/Ports/Start/Demo/Update), Mac-only launcher guards, dashboard host guidance and consistent current/most-recent session snapshot exports. No user live server, private database, hardware or hosting was changed. Session packages preserve quality/source flags, include file hashes, report rolling-retention loss and leave physical acceptance pending. They do not include raw wire bytes or malformed frames and cannot satisfy H1 by themselves.

Local Windows Python 3.12: 23 methods discovered, 21 passed and two POSIX-only methods skipped. New cases cover a 650-record package, hash/byte verification, zero/null/amp/quality preservation, retention loss/session separation, sequence gaps/duplicates/resets, stopped-session export, corruption refusal and HTTP lifecycle/query limits. Native PowerShell syntax and Check passed; port enumeration opened no device. Chromium simulation passed session summary/ZIP/host messaging plus the earlier six-card, source/history, stop/error/outage, five-width and contrast checks. The final GitHub home workflow repeats the suite on Python 3.12–3.14 on Linux and hosted Intel macOS, plus native Windows checks. Consult the actual run for its observed result; neither CI nor a package certifies physical hardware.

## Lightweight home mode addition — 26 November 2026

Source inspection used release base `597f8ca87c4813238c0653cb26e0784b6194e359`. The existing scoped USB gateway/bench portal path was already partly integrated; direct local USB display without portal credentials was missing. [HOME_MAC.md](HOME_MAC.md) describes the added standalone mode.

Local Windows/Python 3.12 checks: 15 home unittest methods discovered, 14 passed and one POSIX pseudo-terminal method skipped. Coverage includes strict V1/text parsing, invalid/duplicate/nonfinite frames, zero/null/current units, fragmented/oversized serial input, stale clearing, simulated unplug, storage failure, rolling history/hash checks, reader fencing, private configuration, process locking, unmanaged-environment preservation, dirty/wrong-branch update refusal, and real loopback HTTP controls/CSRF/Host/limits/CSV. Fresh setup, exact pySerial 3.5 verification and an idempotent second setup passed in a disposable folder. The initial sandbox-account switch blocked an isolated test directory; the successful setup used a fresh disposable folder. No user runtime folder was changed.

The new GitHub home workflow runs these software tests across Python 3.12–3.14 on Linux and modern hosted Intel macOS (including a real pySerial pseudo-terminal fixture), plus Windows 3.13, browser checks and a compile-only ESP32 test sketch. Workflow configuration is not itself a passed result: consult the commit's actual Actions runs. Local Chromium browser checks passed for demo/source labels, sensor unavailability after stop/error, valid zero display, history/CSV labels, service-outage clearing, five viewport widths and solid-surface text contrast. The three new Mac shell scripts passed `bash -n`; Python/JavaScript syntax and Git whitespace checks passed. These are software-only results.

No physical ESP32, sensor, MacBook, motor or hosted portal was accessed. The owner's reported ESP32 text test is separate prior evidence. No production status or physical acceptance was promoted. The older verification records below refer to their stated prior gateway/full-dashboard scope.

Scope: source preparation and GitHub handoff. Hosting/deployment is deferred at the owner's request.
No received hardware, USB device, motor, live portal or private Windows dashboard data was used.

## Observed local software checks

| Check | Observed result and limits |
|---|---|
| Gateway setup | Created an isolated environment and installed only HTTPX/pySerial using Python 3.12.14 on Windows. No port access or configuration secrets. This does not establish old-macOS compatibility. |
| Optional portal setup | Created its separate Python 3.12 environment and installed core dependencies. No real administrator account was seeded. |
| Merged backend regression run | 148 methods passed using the existing Python 3.14 environment, including the new bench path and retained delivery/security checks. |
| Clean Python 3.12 backend run | 126 methods passed for bench, scoped credentials/runner, correlation, local notifications/worker/reminders, recovery and server surfaces. |
| Final bench/gateway run | 16 methods passed on Python 3.12, including remote-HTTP refusal / HTTPS acceptance and pending-destination binding. Includes zero/null/current units, exact retry, modified-identity refusal, token revocation, role/CSRF scope, private queue retention/locking/capacity and malformed-receipt refusal. This overlaps the larger runs; do not add totals. |
| Hardware-side offline contracts | 61 methods passed on Python 3.12. Dummy build records, fixtures and offline transformations are not actual firmware-upload or physical measurement evidence. |
| Full browser rehearsal | Existing synthetic MQTT → spool → central ledger → correlation → governed incident → inbox/reminder flows retained. A real fixture gateway process then sent two explicitly labelled software frames through HTTP into the bench ledger and rendered the six-channel portal view. Retry, revoke, zero/null/current-unit distinctions, outage clearing, all 18 pages and five viewport widths/contrast passed. No physical USB device was used. |
| Shell/static checks | All five `.command` files passed `bash -n`; the new browser module passed Node syntax checking; staged Git whitespace checks passed. |

GitHub CI is configured for Python 3.12 on Linux and hosted Intel macOS plus a Linux browser/broker
rehearsal. A workflow definition alone is not a passed run. Consult the branch's actual GitHub
Actions results. Hosted modern Intel macOS cannot validate the owner's older MacBook or USB chip.

## Still required before claiming real end-to-end operation

- Confirm MacBook year/macOS, supported Python/browser and the actual USB device/driver/cable.
- Inspect the received ESP32 and every module/probe, identify exact pinouts/ratings and record receipt.
- Confirm the supplied classic-ESP32 target applies; compile/upload on the identified board and retain evidence.
- Perform reviewed sensor-only wiring, voltage/polarity/reference checks and a real 600-second session.
- Compare actual measurements against references; verify invalid sensors, disconnects, power cycles and gaps.
- Review hosting, HTTPS/proxy trust, persistent storage, private identity/bootstrap, supervision and recovery.
- Configure the future portal URL and a scoped bench token privately; exercise a real Mac-to-hosted-portal session and network outage/retry.
- Obtain motor startup/stall-current and exact driver/shunt/supply/fuse/wire/thermal suitability before any motor circuit or actuation work.
- Implement/accept physical identity, calibration, real fault policies, retention, alert escalation and production service targets.

`production_ready`, verified hardware/calibration and equipment authorization remain false. Bench
readings do not enter synthetic model/incident pipelines or automatically drive equipment. Original
30-product choices remain unchanged; unconfirmed/incompatible components stay blocked for review.
