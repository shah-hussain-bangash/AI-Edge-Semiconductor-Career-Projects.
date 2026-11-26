# Local software completion and remaining acceptance

Handoff status: 26 November 2026. The owner is at the office Windows PC; home Mac/ESP32 verification is pending. Hosting is explicitly deferred. This is a scope ledger, not a production acceptance certificate.

| Item from the remaining-work review | Local implementation | What still requires evidence/input |
|---|---|---|
| Shutdown timeout | Graceful shutdown acknowledgment now allows 8 s; a delayed acknowledgment regression test is included. | Verify behavior on the actual home setup; no forced PID kill fallback. |
| Backup/restore | Cold, checksummed snapshots; bounded streaming; SQLite-consistent copy; restore to new folders only; incomplete restore launch guard. | Select a separate trusted storage location and exercise a real recovery drill. |
| Previous recordings in UI | Paged saved-recording index, checked raw downloads, incomplete/corrupt handling after restart. | Inspect actual home recordings; checksums do not authenticate hardware. |
| Reconnect | Explicit opt-in monitoring retry with backoff, cleared live values and new attempt IDs; no retry for storage failures or timed recordings. | Actual cable/driver unplug/replug measurements. |
| Startup at login | Optional per-user Mac agent, plan/install/status/start/stop/remove; no automatic acquisition; graceful SIGTERM handling. | Actual owner Mac installation/login/logout verification; current machine remains untouched. |
| Office real-data handoff | Sensor-only V1 CSV + original raw ZIP + provenance/quality report; refuses communication-test data as sensor export. | Real received-part identity, firmware/build/configuration references, calibrated data and reviewed labels. |
| Home environment/USB bring-up | Minimal setup, read-only preflight, ESP32-only parser, timed raw capture, on-page connection checklist, fixed local guide links and a read-only troubleshooting snapshot/download are implemented. Demo input never passes the USB check; stale/unavailable groups stay unavailable. | Tonight's actual OS/Python/port output, successful reader test and measured baseline. |
| Sensor wiring/calibration | Firmware/quality mapping and recording tools exist. | Exact probe/driver variants, ADXL345 soldering, reviewed pinouts/supply/shunt ratings and reference measurements. |
| Motor commissioning | No automatic actuation added; original ordered parts and blocked reviews preserved. | Driver/motor/current/fuse compatibility and guarded physical commissioning. |
| Predictive AI/real operational workflow | Existing research/lab and offline handoff remain available; local exports preserve units/source. No synthetic observation is promoted to verified physical data or a real work order. | Real datasets, validation/holdouts, accepted policies, approved model release/inference and real alert-to-maintenance integration. This has not been completed by a CSV export. |
| Reliability/production acceptance | Software fault fixtures, bounded capture/history, recovery and lifecycle tools are available. | Actual long-duration, restart, power-loss, resource/latency and recovery measurements, then independent acceptance. |
| Online portal/ESP32 Wi-Fi | Existing configurable HTTPS gateway remains separate. | Deferred by owner: hosting/public URL, production identity/TLS/storage/supervision and native ESP32 networking. |

The local preparation features above do not make the complete production system accepted. Remaining physical/AI/operational criteria cannot be closed from office simulations or invented measurements. See [tonight's checklist](TONIGHT_MAC.md), [recovery/operations instructions](LOCAL_RECOVERY.md), [H1 physical acceptance](phase-01-hardware/validation/FIRST-HARDWARE-ACCEPTANCE.md) and [the full production acceptance plan](production-design/04-IMPLEMENTATION-AND-ACCEPTANCE.md).
