# EA-20 — Serial V1 to Enterprise Telemetry V2 Migration and Verification Plan

**Status:** Design proposal. No firmware, broker, API or migration changes performed yet.

## 1. Architecture decision

Use an **anti-corruption adapter** at the Pi gateway to read **existing flat serial V1** and construct a versioned, explicit-quality canonical V2 event. Do not rename or silently reinterpret existing fields in-place. Keep the existing serial capture utility reproducible until the adapter has automated tests and observed runs.

### Current V1 (source-verified)
```json
{"schema_version":1,"device_id":"motor-001","seq":1,"uptime_ms":1000,"ax_mps2":0.1,"ay_mps2":0.2,"az_mps2":9.8,"temp_c":25.0,"bus_v":12.0,"current_ma":100.0,"adxl345_valid":true,"ds18b20_valid":true,"ina219_valid":true,"valid":true}
```
The numbers shown are **illustrative test fixture values**, not real measurements.

## 2. Proposed canonical V2 envelope

```json
{
  "schema_version": "2.0",
  "event_type": "telemetry.sample",
  "source_type": "measured",
  "site_id": "lab",
  "asset_id": "motor-001",
  "device_id": "esp32-001",
  "boot_id": "UNASSIGNED_UNTIL_IMPLEMENTED",
  "sequence": 1,
  "timestamp": {
    "device_uptime_ms": 1000,
    "device_time_utc": null,
    "gateway_received_utc": "2026-11-17T06:00:00Z",
    "clock_quality": "gateway_receipt_only"
  },
  "measurements": {
    "acceleration_x_mps2": 0.1,
    "acceleration_y_mps2": 0.2,
    "acceleration_z_mps2": 9.8,
    "motor_case_temperature_c": 25.0,
    "bus_voltage_v": 12.0,
    "current_a": 0.1
  },
  "quality": {
    "adxl345": "valid",
    "ds18b20": "valid",
    "ina219": "valid",
    "calibration": "not_verified"
  }
}
```

All values above are **illustrative**. `gateway_received_utc` must come from a real authenticated gateway clock when implemented. `source_type` must distinguish real measured, synthetic and replayed fixtures. Never fabricate `boot_id`; a tested V1 adapter must either derive a reliable session ID from actual serial session boundaries or set a transitional `session_quality: "inferred"` and document its ambiguity.

## 3. Field mapping contract

| Raw serial V1 | Canonical V2 | Rule |
|---|---|---|
| schema_version=1 | schema_version="2.0" | Explicit transform only |
| device_id="motor-001" | device_id | Bind actual authenticated board identity; do not assume motor ID is device identity |
| device_id / gateway mapping | asset_id | Bind approved hardware-to-asset registry |
| seq | sequence | Include gateway session context |
| uptime_ms | timestamp.device_uptime_ms | Unsynchronized monotonic uptime, not UTC |
| ax_mps2 | measurements.acceleration_x_mps2 | Preserve SI units |
| ay_mps2 | measurements.acceleration_y_mps2 | Preserve SI units |
| az_mps2 | measurements.acceleration_z_mps2 | Preserve SI units |
| temp_c | measurements.motor_case_temperature_c | Set null if DS18B20 invalid |
| bus_v | measurements.bus_voltage_v | Set null if INA219 invalid |
| current_ma | measurements.current_a | Divide by 1000 only if INA219 valid |
| adxl345_valid | quality.adxl345 | false => invalid + all three acceleration components null |
| ds18b20_valid | quality.ds18b20 | false => invalid + temperature null |
| ina219_valid | quality.ina219 | false => invalid + voltage/current null |
| valid | quality.legacy_all_valid | Optional migration metadata, never primary health state |

## 4. JSON and operational contract conditions

- Use real `null` for invalid sensor fields; reject nonfinite JSON numbers.
- Validate `seq` integer range and handle overflow/reset; sequence by authenticated device and real boot/session identity.
- Assert expected units, schema major version, device binding and source_type.
- Prevent redaction of the difference between synthetic fixtures and real measured data.
- Define whether model output can evaluate partial features; otherwise abstain and signal degraded state.
- Make IDs and topic names site-scoped with broker ACL; a payload site ID is never a sufficient authorization check.
- Deduplicate QoS1 traffic with an explicit unique event key.
- Capture original V1 payload hash and V2 mapping version for auditability where retention is authorized.
- Reconcile this V2 with earlier EA-10 and EA-03 illustrative schema before implementing; do not claim both are simultaneous canonical contracts.

## 5. Required automated test suite (planned)

| Test ID | Input | Expected result |
|---|---|---|
| CT-01A | valid V1 line | V2 transform with identical numeric meaning |
| CT-01B | INA219 valid=false and zero numeric fallback | V2 current/voltage null, not actual 0 |
| CT-01C | DS18B20 invalid | V2 temperature null |
| CT-01D | ADXL345 invalid | V2 acceleration axes null |
| CT-02A | current_ma=1000 | current_a=1.0 |
| CT-02B | acceleration 9.81 m/s² | unchanged 9.81 m/s² |
| CT-02C | unsupported schema | reject with countable error |
| CT-03A | device restarts with seq=1 | new verified boot/session identity or explicit ambiguity |
| CT-03B | repeated packet | deduped without second incident |
| CT-03C | identity topic/payload mismatch | reject and audit |
| CT-04A | gaps and clock drift | loss and timing metrics visible |
| CT-05A | unauthorized MQTT topic | denied |
| CT-05B | invalid TLS credentials | denied |
| CT-06A | synthetic source fixture | visibly synthetic in UI/export |
| CT-06B | stale data | health state = unknown/degraded, not healthy |

**No results provided or implied.**

## 6. Transition and release gates

1. Agree on V2 schema and units with data/AI/security architecture owners.
2. Add JSON Schema + versioned fixtures in repo; validate schema across languages.
3. Implement gateway V1->V2 adapter with stable identity/session handling.
4. Test source reader and gateway adapter locally using synthetic fixtures.
5. Run on actual hardware **sensor-only**, motor disconnected, when parts arrive and safe voltage check completed.
6. Add private authenticated MQTT publish/subscribe tests and ACL negatives.
7. Add backend ingest contract tests and idempotency/replay invariants.
8. Capture measured data only with provenance evidence; compare observed timing and quality.
9. Update EA-10 canonical contract, then retire legacy V1 only after compatibility evidence.
10. Record reviewers, changes, test logs, known limitations, rollback conditions.

## 7. Safety and scope

This plan does not approve hardware assembly, mains exposure or motor operation. No external tool or agent gets motor power control. Physical safety signoff remains a separate gate.

## 8. Decision record template

`Decision ID | Topic | Alternatives | Proposed choice | Cost/complexity | Risk | Reviewer | Status | Change trigger`.
