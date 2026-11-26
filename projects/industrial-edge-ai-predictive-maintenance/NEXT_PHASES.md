# Guided completion: office development and home hardware

Updated 26 November 2026. Software preparation is implemented; actual MacBook, sensor, motor and production acceptance are not certified. Hosting remains deferred by the owner. This guide orders the work and identifies the next evidence needed; it is not a promise that untested hardware will work on first connection.

## Your next action: confirm the home computer and port

On the home MacBook, in macOS Terminal, run:

```bash
uname -s
sw_vers -productVersion
ls /dev/cu.*
```

Send the exact output to the project chat. These commands do not open a serial port or upload firmware. Do not paste Mac commands into office PowerShell. Then follow [tonight's setup](TONIGHT_MAC.md), which covers first-time dependencies and preserves existing clones/local changes.

## Work order and responsibilities

| Phase | Implemented preparation | Next evidence/action needed from the owner | What follows that evidence |
|---|---|---|---|
| 1. Home installation | Supported Python 3.12–3.14, pySerial 3.5, Mac/Windows launchers, host/port diagnostics, local guides and graceful lifecycle | Actual three-command output above, setup result and any exact error | Resolve the actual machine-specific issue, then start the local dashboard; no Docker or local training |
| 2. ESP32 USB | Existing text sketch/JSON test, explicit Start/Stop, stale clearing, timed raw capture and quality review | ESP32 USB only; close Serial Monitor; confirm increasing accepted count and six unavailable sensors; collect a 10-second communication recording | Review raw timing/counts and actual unplug/reconnect behavior; no sensor or production pass from test messages |
| 3. Sensor baseline | V1 sensor firmware, per-group validity, units, raw recording, first-window baseline review and office export | Exact received module identities, soldered headers, reviewed pinouts/ratings, firmware/build configuration, reference capability; after qualified wiring review collect sensor-only data | Review sensors one at a time, measured references and a pre-agreed 600-second baseline; retain failures and partial groups |
| 4. Motor commissioning | Original hardware selection and blocked compatibility reviews retained; local software sends no actuation commands | Exact driver variant, motor/supply ratings including current requirements, protection/mounting/guard/disconnect design and qualified physical review | Prepare and review the actual guarded procedure; energize only under that separate accepted procedure |
| 5. Measured intelligence | Raw-to-office sensor CSV with units/provenance, offline research/evaluation code; 1 Hz data is not converted into invented vibration velocity/spectra | Qualified baseline sessions, actual acquisition bandwidth, reviewed labels and intended prediction task | Define suitable features, session-independent train/validation/holdout splits, compare baselines, select and validate an inference release; no accuracy/RUL claim before results |
| 6. Real maintenance workflow | Existing local synthetic planning/rehearsal stays separate from measured bench data | Accepted asset/device mapping, alert policy, responsible people and independent review/closure rules | Integrate qualified observations with explicit domain policy, audit, duplicate handling and role-bound review; report approval does not deploy a model or authorize equipment |
| 7. Online access | Configurable HTTPS gateway and durable delivery software already exist | Deferred: no hosting account, public URL or production credentials requested now | When hosting is explicitly resumed, review deployment/identity/TLS/storage/supervision and test remote delivery; native ESP32 Wi-Fi remains separate work |
| 8. Production acceptance | Fault/lifecycle fixtures, checksummed backups, new-folder restore, bounded history/raw capture, review/export tools | Real Mac/board long-duration, resource/latency, restart/power-loss, reference, recovery and independent acceptance evidence; production scope/targets agreed in advance | Resolve observed failures and evaluate the full requirements matrix; issue a production acceptance record only after its criteria are actually satisfied |

The immediate dependency is phase 1, followed by the ESP32-only communication test. Do not assemble all modules at once to accelerate the checklist. Board/driver/probe photos and measurements will be requested when their corresponding phase is reached; never send credentials.

## Review a saved recording in the dashboard

1. Finish a timed recording. In **Saved recordings**, click **Refresh recordings**, then **Review baseline quality** for that run.
2. The report rechecks raw hashes and parser classifications. It lists the recording stop reason, observed host-monotonic duration, first `[0, 600)` second counts, per-group declared-valid counts, receipt interval median/p95/max, sequence gaps, duplicates and sequence/uptime decreases. An event at or after 600 seconds stays in total/raw counts but is excluded from the first window.
3. ESP32-only data is explicitly communication-test data. Invalid/disconnected sensor groups remain unavailable. The proposed 594 valid records per group and 3-second interval figures come from [H1](phase-01-hardware/validation/FIRST-HARDWARE-ACCEPTANCE.md); they require agreement before acceptance measurements. First/last-receipt warnings are descriptive coverage advisories. Counts and firmware flags do not prove calibration or source authenticity.
4. Download the review if needed. A report with no listed count/timing issues still says **review-required / physical acceptance pending**. It does not approve motor operation, AI training or production use. Raw evidence and independent reference comparisons are still needed.

Offline review without opening USB is also available after setup. Replace `CAPTURE_FOLDER` with the actual private capture folder path. On Mac:

```bash
.venv-home/bin/python home-mode/home_recording.py review "CAPTURE_FOLDER"
```

On Windows PowerShell:

```powershell
.\.venv-home\Scripts\python.exe home-mode\home_recording.py review "CAPTURE_FOLDER"
```

An optional `--output NEW.json` saves privately to a new filename outside the capture folder; existing files are refused. Keep the capture's original 32-character folder name: it is checked against the manifest identity. A recording is not accepted if its host-monotonic event times move backwards. Copies of old incomplete/corrupt recordings are preserved for investigation rather than silently repaired.

See [local implementation status](LOCAL_READINESS.md), [recovery operations](LOCAL_RECOVERY.md) and the full [implementation and acceptance plan](production-design/04-IMPLEMENTATION-AND-ACCEPTANCE.md). Documentation coverage and software CI never close physical acceptance by themselves.
