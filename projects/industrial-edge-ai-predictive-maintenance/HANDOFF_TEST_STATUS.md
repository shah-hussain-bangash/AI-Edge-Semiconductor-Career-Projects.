# Mac gateway handoff verification — 26 November 2026

Scope: source preparation and GitHub handoff. Hosting/deployment is deferred at the owner's request.
No received hardware, USB device, motor, live portal or private Windows dashboard data was used.

## Observed local software checks

| Check | Observed result and limits |
|---|---|
| Gateway setup | Created an isolated environment and installed only HTTPX/pySerial using Python 3.12.14 on Windows. No port access or configuration secrets. This does not establish old-macOS compatibility. |
| Optional portal setup | Created its separate Python 3.12 environment and installed core dependencies. No real administrator account was seeded. |
| Merged backend regression run | 148 methods passed using the existing Python 3.14 environment, including the new bench path and retained delivery/security checks. |
| Clean Python 3.12 backend run | 126 methods passed for bench, scoped credentials/runner, correlation, local notifications/worker/reminders, recovery and server surfaces. |
| Final bench/gateway run | 15 methods passed on Python 3.12 after adding a remote-HTTP refusal / HTTPS acceptance test. Includes zero/null/current units, exact retry, modified-identity refusal, token revocation, role/CSRF scope, private queue retention/locking/capacity and malformed-receipt refusal. This overlaps the larger runs; do not add totals. |
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
