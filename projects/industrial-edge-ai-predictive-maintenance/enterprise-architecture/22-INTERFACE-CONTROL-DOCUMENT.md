# EA-22 — EDGEOPS Interface Control Document (ICD)

> **ICD version:** 0.1 proposed contract (candidate Telemetry V2)  
> **Date:** 2026-11-17  
> **Approval status:** DRAFT — no owner or independent reviewer has approved it.  
> **Change boundary:** Documentation/contract artifacts only; existing firmware and capture tooling unchanged.  
> **Safety boundary:** No motor/control commands, PLC or safety actuation interfaces.

## 1. Purpose and system-of-record boundaries

This ICD identifies the interfaces among sensor-only ESP32 firmware, a proposed Pi gateway/V1 adapter, private MQTT, future FastAPI ingestion and downstream data/AI/maintenance services. It describes the source-to-target transition without claiming the V2 envelope already exists.

**Current source contract (implemented in code):**
- `../phase-01-hardware/firmware/src/main.cpp` emits line-delimited flat JSON over **USB serial**, with integer `schema_version=1`.
- `../phase-01-hardware/scripts/capture_serial.py` checks the V1 record and writes CSV with a gateway receipt timestamp.
- **No MQTT TLS, device certificate, broker, Pi adapter, FastAPI interface or production authorization has been verified.**

**Target contract (proposed only):** `contracts/telemetry-v2.schema.json`, draft 2020-12 JSON Schema with two synthetic fixtures:
- `contracts/examples/telemetry-v2.synthetic-valid.json`
- `contracts/examples/telemetry-v2.synthetic-partial.json`

This candidate refines the earlier, incompatible illustrative `EA-10` V1.0 schema and `EA-20` V2 example. **EA-22 is the latest proposed format, not yet an accepted replacement.** If ratified, update EA-03/EA-10/EA-20 and actual source together with a tracked ADR.

## 2. Interface boundary register

| ID | Producer → consumer | Protocol / status | Trust binding | Data / failure policy |
|---|---|---|---|---|
| ICD-01 | ESP32 → laptop serial capture | USB serial, **source present** | physically connected serial port; no cryptographic identity | V1 flat JSON, invalid lines rejected; missing sensors currently numeric zero plus flags |
| ICD-02 | Serial V1 reader → gateway normalizer | proposed in-process adapter | trusted local attachment and provisioned registry | V1→V2 with unit conversion, provenance and quality; reject unknown schema |
| ICD-03 | ESP32 or gateway → edge broker | future private MQTT, TLS candidate | per-device/service credential and topic ACL | QoS1 candidate; bounded retry and dedupe |
| ICD-04 | Pi gateway → FastAPI ingestion | future HTTPS | scoped service principal bound to site/device | idempotent V2 ingest, explicit status codes |
| ICD-05 | FastAPI → PostgreSQL/TimescaleDB | future DB protocol | service DB principal | source event, quality and origin retained |
| ICD-06 | Browser → domain APIs | future HTTPS/OIDC | server-side RBAC and asset/site scope | authorization denial audited |
| ICD-07 | RAG → SOP repository | future read-only retrieval | document ACL bound to requester | cited guidance or abstain |
| ICD-08 | Approver → work-order API | future HTTPS/OIDC | reviewer role + current version | audit approval/rejection; never physical actuation |

Do not expose serial ports or private broker publicly. Never infer identity solely from payload text.

## 3. Canonical event and field constraints (V2 design candidate)

Required top-level keys: `schema_version` = `"2.0"`, `event_type` = `"telemetry.sample"`, `source_type` in `measured|synthetic|replayed`, `site_id`, `asset_id`, `device_id`, nullable `boot_id`, unsigned 32-bit `sequence`, `timestamp`, `measurements` and `quality`. Unspecified extra keys are rejected by schema.

**Time object:** `device_uptime_ms` in [0, 4294967295], optional `device_time_utc` as nullable date-time, `gateway_received_utc` as date-time, and `clock_quality` distinguishing verified device time from gateway receipt only. Format annotations such as `date-time` must be enabled in the chosen JSON Schema validator.

**Measurement fields / units:**
- `acceleration_x_mps2`, `acceleration_y_mps2`, `acceleration_z_mps2`: SI m/s²; no conversion from current V1.
- `motor_case_temperature_c`: Celsius; V1 `temp_c`.
- `bus_voltage_v`: volts; V1 `bus_v`.
- `current_a`: amperes; **V1 `current_ma / 1000`**.
- All measurements are `number|null`; nonfinite numbers are invalid JSON.
- When `quality.adxl345 != valid`, **all three acceleration axes must be null**; similarly invalid DS18B20 → temperature null and invalid INA219 → voltage and current null.
- A `valid` quality flag means only a present numeric sensor read; it **does not** independently prove accuracy, calibration, physical rating or safety.
- Schema cannot enforce every positive invariant (e.g., valid → all channels non-null, clock freshness, sensor plausibility, identity authorization or monotonicity). Semantic validator and security gateway tests are required.

**Origin, security and session semantics:**
- Source type must reflect true provenance. Illustrative fixtures are `synthetic`; a replay of real measurements is labeled `replayed` with source manifest.
- `device_id` must be an authenticated registered physical endpoint, **not** the hard-coded V1 `motor-001` asset identifier.
- `boot_id` is nullable while identity is not verifiably established. `session_quality` = verified/inferred/unavailable makes the limitation explicit; **never invent a globally unique boot ID**.
- `sequence` repeats after firmware restart; therefore, do not assert exactly-once deduplication across resets without verified boot/session identity.
- Receiver must obtain server-side site/asset mapping from trusted registry; mismatch or unauthorized identity → reject and audit.

## 4. V1-to-V2 transformation (proposed)

| V1 flat field | V2 field | Conversion |
|---|---|---|
| `schema_version=1` | `schema_version="2.0"` | explicit adapter, never silent parsing |
| `device_id="motor-001"` | `asset_id` | provisional mapping ONLY if site asset registry confirms |
| trusted USB port / provisioning | `device_id` | actual board identity from trusted registry, never guessed |
| `seq` | `sequence` | integer value; handle restart and wrap |
| `uptime_ms` | `timestamp.device_uptime_ms` | monotonic boot-relative time, not UTC |
| `ax_mps2/ay_mps2/az_mps2` | `measurements.acceleration_*_mps2` | preserve units when ADXL345 valid |
| `temp_c` | `measurements.motor_case_temperature_c` | null if DS18B20 invalid |
| `bus_v` | `measurements.bus_voltage_v` | null if INA219 invalid |
| `current_ma` | `measurements.current_a` | divide 1000; null if INA219 invalid |
| `adxl345_valid` | `quality.adxl345` | true→valid, false→invalid/not_connected based on evidence |
| `ds18b20_valid` | `quality.ds18b20` | likewise |
| `ina219_valid` | `quality.ina219` | likewise |
| serial host timestamp | `timestamp.gateway_received_utc` | actual trusted gateway receipt timestamp |
| unknown firmware calibration | `quality.calibration` | `not_verified` / `unknown` |

**Legacy V1 limitation:** numeric zero fallback must be replaced by null only when the corresponding validity bit is false; a true valid sensor can legitimately read zero.

## 5. Events, retries and status behavior

- MQTT topic candidate: `edgeops/v1/{site_id}/{device_id}/telemetry`; distinguish topic convention version from **payload** V2 contract version.
- For QoS1, duplicate delivery is possible. Proposed idempotency key = authenticated device ID + verified boot/session identity + sequence + event type. If session identity is inferred/unavailable, quarantine or use collision-safe bounded session handling; do not claim global deduplication.
- Reject malformed payloads and identity mismatches; capture reason codes, metrics and safe redacted trace.
- Gateway queue must be bounded with explicit dropped-record counters, storage/quota limits and reconnect backoff.
- Failed broker/API/DB must surface stale/degraded/unknown condition, never healthy.
- Backend successful ingest should acknowledge only when documented durable acceptance criterion is met. Define 2xx/4xx/5xx and idempotent replay behavior in OpenAPI after the review.
- Firmware sensor-only serial V1 remains supported until V2 adapter is tested and release/rollback is authorized.

## 6. Acceptance-test catalog

| ID | Input / scenario | Expected outcome | Status |
|---|---|---|---|
| ICD-T01 | Synthetic fully valid V2 fixture | Schema accepts | NOT EXECUTED |
| ICD-T02 | Synthetic INA219-not-connected fixture | Schema accepts with voltage/current null | NOT EXECUTED |
| ICD-T03 | INA219 invalid but current = 0.0 | Schema rejects (must be null) | NOT EXECUTED |
| ICD-T04 | ADXL345 invalid but one acceleration numeric | Schema rejects | NOT EXECUTED |
| ICD-T05 | DS18B20 invalid but temperature 0 | Schema rejects | NOT EXECUTED |
| ICD-T06 | V1 valid current_ma=1000 | V2 current_a=1.0 | NOT IMPLEMENTED |
| ICD-T07 | V1 invalid current_ma=0, flag=false | V2 current_a=null | NOT IMPLEMENTED |
| ICD-T08 | V1 acceleration 9.81 m/s² | V2 9.81 m/s² unchanged | NOT IMPLEMENTED |
| ICD-T09 | Schema 3.0, missing site_id, additional field | Reject incompatible event | NOT EXECUTED |
| ICD-T10 | Verified clock_quality without device_time_utc | Schema rejects | NOT EXECUTED |
| ICD-T11 | Verified session_quality with null boot_id | Schema rejects | NOT EXECUTED |
| ICD-T12 | Duplicate/restart sequence | Idempotency preserves unique event or flags ambiguity | NOT IMPLEMENTED |
| ICD-T13 | Device publishes another site's topic | ACL denies and records audit | NOT IMPLEMENTED |
| ICD-T14 | Invalid/revoked MQTT TLS credential | Broker rejects | NOT IMPLEMENTED |
| ICD-T15 | Stale sample or disconnected edge | UI shows unknown/degraded | NOT IMPLEMENTED |
| ICD-T16 | Agent attempts to execute physical control | Tool/authorization layer rejects | NOT IMPLEMENTED |

**Pass policy:** Store validator version, command, fixture hash, source commit SHA, environment, expected/observed outcome and reviewer in a dated evidence record. A design fixture in GitHub is not proof its validation passed.

## 7. Architecture ownership and ratification

| Decision | Review role | Status |
|---|---|---|
| Canonical V2 structure, values, units | Solution/data architect | Proposed |
| Device, site, asset, boot/session identity and binding | Security/embedded architect | Proposed |
| MQTT 3.1.1 vs 5, QoS, client identities, TLS/ACL | Security/integration lead | Proposed |
| Version compatibility and retirement | Technical lead | Proposed |
| Latency, retention, queue limits, availability | Sponsor/SRE | Pending business inputs |
| Electrical circuit and sensor accuracy | Qualified electrical reviewer | Pending safety review |

Ratification requires an actual design review, approved ADR, compatible schema validation, negative contract tests and roll-back plan. Before approval, these files are **candidate interface-control documentation only**.

## 8. Relationship to companion architecture

- [EA-19 source-code conformance](19-ARCHITECTURE-TO-CODE-CONFORMANCE-REVIEW.md)
- [EA-20 V1→V2 migration](20-TELEMETRY-CONTRACT-MIGRATION-AND-TEST-PLAN.md)
- [EA-21 architecture readiness](21-IMPLEMENTATION-READINESS-ARCHITECTURE-REVIEW.md)
- [EA-10 early API/event catalog](10-API-EVENT-AND-CONTRACT-CATALOG.md)
- [EA-16 master architecture](16-MASTER-ENTERPRISE-SOLUTION-ARCHITECTURE.md)

**Current disposition:** NO-GO for motor energization and production claims. Contract review can proceed without hardware purchase.
