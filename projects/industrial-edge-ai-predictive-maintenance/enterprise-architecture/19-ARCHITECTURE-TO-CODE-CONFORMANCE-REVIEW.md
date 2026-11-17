# EA-19 — Architecture-to-Code Conformance Review

**Review date:** 2026-11-17  
**Scope:** The GitHub source files named below, compared with EA-10 and EA-16.  
**Method:** Static code reading only, no firmware build, automated test execution, physical wiring or hardware validation.  
**Review state:** Design findings recorded; no claim of independent approval.

## Reviewed code and design

- `../phase-01-hardware/firmware/platformio.ini`
- `../phase-01-hardware/firmware/src/main.cpp`
- `../phase-01-hardware/scripts/capture_serial.py`
- `../phase-01-hardware/tests/test_capture.py`
- `../phase-01-hardware/docs/WIRING_AND_SAFETY.md`
- `10-API-EVENT-AND-CONTRACT-CATALOG.md`
- `16-MASTER-ENTERPRISE-SOLUTION-ARCHITECTURE.md`

## Existing technical facts verified by source inspection

- Firmware targets `esp32dev` on Arduino/PlatformIO and uses Adafruit ADXL345, INA219, DallasTemperature, OneWire, ArduinoJson libraries.
- `main.cpp` initializes I2C on GPIO21 (SDA) and GPIO22 (SCL) at 100 kHz; DS18B20 on GPIO4; 115200 baud serial; intended one JSON emission per 1000 ms.
- ADXL345 produces acceleration in **m/s²**, INA219 bus voltage in **volts** and current in **milliamperes**. DS18B20 reports Celsius.
- Current firmware schema is **flat** and uses integer `schema_version: 1`, `device_id: "motor-001"`, `seq`, `uptime_ms`, six numeric fields plus four boolean validity fields.
- `capture_serial.py` parses that flat schema, validates finite numbers/booleans, adds `gateway_utc` and writes CSV; only one prior sequence value is tracked **per device ID**.
- The test file contains four `unittest` tests for valid record, wrong schema, nonfinite values and inconsistent flags. These were not executed during this review.
- Firmware does not implement MQTT, TLS, per-device credentials, boot ID, external wall-clock sync, or site/asset separation; those belong to later planned phases.
- Wiring document explicitly says **motor disconnected** during sensor-only bring-up and is not a reviewed electrical schematic.

## Findings and disposition

| ID | Severity | Grounded observation | Architecture conflict / consequence | Remediation |
|---|---|---|---|---|
| C-01 | High | Invalid sensor readings emitted as **0.0** with a separate validity flag | A downstream consumer ignoring flags could interpret missing sensor as a real zero | New canonical V2 envelope must use nullable values plus validity/quality; preserve flags for migration |
| C-02 | High | Source emits integer `schema_version = 1` and flat fields; EA-10 proposes string `"1.0"` and nested envelope | Incompatible producers and consumers | Introduce explicit `raw_serial_v1` adapter and `telemetry_v2` schema; migrate with contracts/tests |
| C-03 | High | Firmware `device_id = "motor-001"` conflates device and asset | Site/tenant scoping and device replacement ambiguous | Separate authenticated `device_id`, `asset_id`, `site_id` in gateway mapping |
| C-04 | Medium | Acceleration in `m/s²`, future proposal in `g`; current mA vs proposed A | Unit conversion errors produce wrong anomaly features | Fix canonical unit choice, convert precisely, record units in manifest |
| C-05 | High | `seq` increments but has no `boot_id`; capture tracks last sequence by device only | Restart resets sequence, causing dedupe ambiguity and missed gap/restart classification | Add boot/session identity at gateway/firmware, test restart and wraparound |
| C-06 | Medium | `lastReport += 1000` and blocking DS18B20 conversion | Emission jitter can increase; actual measurement time and cadence unknown | Measure timing, preserve sensor timestamps, assess non-blocking conversion and queue behavior |
| C-07 | Medium | `valid` requires **all three** sensors | A disconnected INA219 invalidates useful vibration and temperature data | Define per-channel quality and per-model required feature sets; avoid global health conflation |
| C-08 | High | Flat serial lacks cryptographic sender auth; MQTT and TLS absent | Designed network trust boundary is not yet implemented | Keep USB-only as Phase 1, build authenticated MQTT in Phase 2 and test ACL, reconnect, replay |
| C-09 | Medium | Capture script catches `(OSError, Exception)` broadly | Broad exception suppression can hide exact defect class and complicate incident resolution | Narrow anticipated errors, include structured error reason and safe termination |
| C-10 | Medium | Serial capture writes and flushes CSV every record | Throughput/backpressure and filesystem behavior unmeasured | Benchmark sustained capture and log buffering, ensure flush/close/recovery policy |
| C-11 | High | Only four parser unit test functions; no restart, sequence regression, malformed types, range or sensor-outage cases shown | Requirement traceability incomplete | Add negative and boundary test matrix; run and retain actual results |
| C-12 | High | No physical assembly or hardware purchase evidence | Documentation cannot prove measured sensors or safe motor rig | Keep motor power blocked pending rated schematic, protection, mount and review |
| C-13 | Medium | `currentValid` tests finiteness but not module voltage/current operating limits or calibration state | May admit physically untrustworthy readings | Add explicit shunt/module rating and plausibility policy, mark calibration uncertain |
| C-14 | Medium | Current serial CSV does not persist schema version or sensor calibration/device provenance | Dataset reproducibility, model audit and contract migration weak | Include source schema, firmware hash, boot ID, acquisition mode, session manifest |

## Traceability and acceptance

| Finding | Design owner | Planned test ID | Acceptance criterion | Current result |
|---|---|---|---|---|
| C-01 / C-07 | Firmware + data | CT-01 | Missing sensor represented null/invalid; unaffected channels remain usable | NOT RUN |
| C-02 / C-04 | Integration | CT-02 | Raw serial adapter maps every unit correctly to approved V2 schema | NOT RUN |
| C-03 / C-05 | Security + integration | CT-03 | Restart/replay and cross-device messages cannot be confused | NOT RUN |
| C-06 / C-10 | Embedded lead | CT-04 | Timestamp, effective sampling rate, jitter and loss measured | NOT RUN |
| C-08 | Security architect | CT-05 | Unauthorized MQTT topic publish and invalid identity denied | NOT IMPLEMENTED |
| C-11 / C-14 | QA + MLOps | CT-06 | Negative tests and provenance manifest stored with run | NOT RUN |
| C-12 / C-13 | Qualified electrical reviewer | CT-07 | Approved motor/shunt/driver/fuse/guard diagram before motor power | BLOCKED |

## Explicit decisions required before code change

1. Canonical V2 numeric units and nullability.
2. Where the source serial adapter lives (Pi gateway recommended).
3. Boot ID generation and monotonic versus wall-clock timestamps.
4. Authenticated device identity and site/asset binding.
5. MQTT protocol version, TLS certificate provisioning, QoS and ACL.
6. Sensor-required feature policy and partial-quality semantics.
7. Sensor and electrical ratings required for test hardware.
8. Actual package/board version pinning and test environments.

## Conclusion

This is a **static architecture-to-code review**, not a passed test report. Phase 1 starter code is a useful basis but does not yet satisfy enterprise telemetry, identity, quality and security contracts. Preserve the existing serial schema as legacy V1 until a tested migration is available. Do **not** energize a motor or claim enterprise deployment from documentation alone.
