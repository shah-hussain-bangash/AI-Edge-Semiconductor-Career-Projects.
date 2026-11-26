# Mac gateway handoff verification — 26 November 2026


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
