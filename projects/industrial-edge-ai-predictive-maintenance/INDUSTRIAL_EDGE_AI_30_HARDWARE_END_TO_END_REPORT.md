# Industrial Edge AI — 30-Product End-to-End Hardware Report

**Date:** 2026-11-17. **Project:** Industrial Edge AI Predictive Maintenance & Autonomous Operations Platform.

> Planning document only. No physical testing or completed purchases have been confirmed.

## Overview and shopping status

- **Total planned:** 30 hardware product categories (25 core and 5 expansion).
- **Temu screenshots:** cart counter showed **11 entries**, but they were not reconciled to distinct products or paid orders.
- **Explicit item selected:** 5.5×2.1mm DC connectors, **1 male + 1 female**.
- **Verified paid or delivered:** no proof provided. **Remaining to buy:** unknown pending cart/invoice reconciliation, not automatically 30−11.
- **Power-supply warnings:** one advertised 12V/5A product had a review reporting only approximately 3A; a 12V/10A listing had a one-star mismatch review. Prefer seller-confirmed, electrically rated and independently tested supply.
- An earlier guide estimated AED 930–1,370 for its smaller initial bill of materials; **this is not a verified price for all 30 categories**.

## End-to-end topology

```text
ADXL345 vibration ----+
DS18B20 temperature --+--> ESP32 firmware --> authenticated MQTT --> Raspberry Pi 5
INA219 DC monitoring -+                                           |
                                                            ONNX edge inference
                                                                  |
                                                FastAPI + PostgreSQL/TimescaleDB
                                                                  |
                                               Next.js alerts & digital twins
                                                                  |
                                         RAG advice -> human-approved work orders
```

**Separate supply paths:** Pi 5 needs its own compatible USB-C PSU, ESP32 receives USB/regulated logic supply, and guarded 12V motor uses a separate protected 12V DC circuit. Never apply 12V to ESP32 GPIO or Pi power input.

## All 30 hardware products, roles, usage and acceptance tests

### 1. Raspberry Pi 5 4GB — Core
**Role:** Edge MQTT gateway and ONNX inference.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Boot, broker and ONNX timing.

### 2. ESP32-WROOM-32 DevKit — Core
**Role:** Sample 3.3V sensors and publish MQTT.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Flash, serial log and packet sequencing.

### 3. ADXL345 accelerometer — Core
**Role:** Measure three-axis motor vibration.
**Use:** Connect to ESP32 3.3V-safe I2C SDA GPIO21 / SCL GPIO22 and secure to motor housing.
**Verify:** I2C scan, stationary baseline and vibration.

### 4. DS18B20 waterproof probe — Core
**Role:** Measure motor casing temperature.
**Use:** Connect OneWire DATA to GPIO4 with a 4.7k resistor to 3.3V.
**Verify:** Known temperature comparison.

### 5. INA219 current-voltage sensor — Core
**Role:** Measure safe rated DC current and voltage.
**Use:** Use ESP32 I2C GPIO21/GPIO22 only with rated shunt, motor startup-current check and safe common-mode voltage.
**Verify:** Compare safe reading to multimeter.

### 6. 12V DC motor — Core
**Role:** Create guarded rotating-equipment test rig.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Guarded baseline at rated current.

### 7. 12V 5A regulated motor adapter — Core
**Role:** Provide separate fused motor power.
**Use:** Verify exact 12V DC output, barrel dimensions and polarity; purchase only from reliable certified seller.
**Verify:** 12V verified under actual load.

### 8. Official Raspberry Pi 5 USB-C PSU — Core
**Role:** Power Pi 5 safely; never use 12V.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Pi undervoltage diagnostic check.

### 9. Raspberry Pi 5 case — Core
**Role:** Shield Pi electronics.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Mechanical fit and cable clearance.

### 10. Pi 5 active cooler — Core
**Role:** Prevent Pi thermal throttling.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Thermal stress check.

### 11. 64GB microSD — Core
**Role:** Store Raspberry Pi OS and local data.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Successful flash and filesystem integrity.

### 12. Breadboard — Core
**Role:** Build 3.3V sensor-only prototypes.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** No mains or motor-current routing.

### 13. Dupont jumper wires — Core
**Role:** Connect I2C/OneWire low-current wires.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Continuity and stable bus.

### 14. ESP32 USB data cable — Core
**Role:** Flash ESP32 and capture serial logs.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Firmware flashing and serial output.

### 15. Digital multimeter — Core
**Role:** Check voltage polarity and continuity.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Reference measurement.

### 16. 4.7k ohm resistor assortment — Core
**Role:** DS18B20 OneWire pull-up DATA to 3.3V.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Measure 4.7k resistance and stable sensor data.

### 17. 5.5x2.1mm male/female DC terminal connectors — Core
**Role:** Connect low-voltage DC leads; match exact barrel size.
**Use:** Choose one male plus one female 5.5x2.1mm terminal connector; verify adapter plug is not 5.5x2.5mm.
**Verify:** Polarity, diameter and screw terminal pull-test.

### 18. DC inline fuse and fuse — Core
**Role:** Protect motor low-voltage circuit against faults.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Fuse match and DC continuity.

### 19. Rated DC isolation switch — Core
**Role:** Allow manual motor disconnect independent of software.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Independently halt motor.

### 20. Motor shaft guard — Core
**Role:** Prevent contact with rotating parts.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Inspect full shaft coverage.

### 21. 12V motor driver MOSFET — Core
**Role:** Switch motor using correctly rated driver.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Driver derating and load test.

### 22. Flyback diode or transient suppressor — Core
**Role:** Suppress motor switching inductive kick.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Verify module installation and suppression.

### 23. Hook-up wire and ferrules — Core
**Role:** Make securely sized low-voltage connections.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Pull-test and temperature check.

### 24. Low-voltage terminal distribution blocks — Core
**Role:** Protect and label DC power distribution.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Covered terminal and polarity check.

### 25. Motor mounting bracket/base — Core
**Role:** Fix motor securely for repeatable sensing.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Verify structural stability.

### 26. 12V to 5V buck converter — Expansion
**Role:** Power optional 5V peripherals from 12V.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** 5V set before connecting devices.

### 27. I2C logic level shifter accessories — Expansion
**Role:** Translate I2C levels only when datasheets require.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** 3.3V logic on I2C.

### 28. USB serial debugging adapter — Expansion
**Role:** Debug UART at 3.3V logic levels.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** UART logs with common GND.

### 29. USB/DC inline power meter — Expansion
**Role:** Measure suitable DC/USB power draw.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** Meter compared with reference.

### 30. Spare ESP32 and sensor kit — Expansion
**Role:** Enable repairs and reproducibility tests.
**Use:** Integrate according to the exact manufacturer's rated voltage, wiring diagram and current limits.
**Verify:** A/B baseline replication.

## Integration phases

1. Inventory, photograph and confirm ratings, pinouts, purchase receipts and return terms.
2. Bring up ESP32 with **motor disconnected**; verify ADXL345 and INA219 I2C addresses and 3.3V-safe modules.
3. Wire DS18B20 with pull-up, capture sensor-valid telemetry, save actual baseline CSV.
4. Assemble guarded motor base with independent switch, suitably sized fuse, driver and separately rated adapter; verify startup/stall current and wiring before powering.
5. Install Raspberry Pi OS, MQTT broker and authenticated ESP32 telemetry ingestion.
6. Train/evaluate anomaly baseline, export ONNX and benchmark on Raspberry Pi.
7. Connect ingestion to FastAPI, PostgreSQL/TimescaleDB and Next.js dashboards; label real vs synthetic data.
8. Add human-reviewed RAG recommendations, audit logs, rollback/security tests and portfolio demonstration.

## Essential safety

**No exposed mains AC modules** on a breadboard. Use an enclosed certified AC adapter, rated UK mains lead and independent low-voltage fuse/disconnect. Check 5.5x2.1 versus 5.5x2.5mm barrel compatibility and output polarity. Never power a rotating motor without a rigid mount and shaft guard. Do not put an unverified INA219 board in the motor's high-current path. Never deliberately stall the motor. AI outputs must not autonomously operate safety-critical machines.

## Evidence checklist

- [ ] Confirm exact manufacturer models, quantities, pricing and receipts for each of 30 categories
- [ ] Measure supply voltage, polarity, current limits and continuity
- [ ] Verify sensor wiring, I2C scan and 10-minute real serial CSV
- [ ] Prove guarded motor tests and baseline vibration/temperature
- [ ] Run MQTT reconnect test and Pi ONNX latency evaluation
- [ ] Show real FastAPI/database/UI and approval audit trail
- [ ] Upload photos, logs, risk review, failure notes and project demo

Related: [hardware buying guide](./HARDWARE_BUYING_INTEGRATION_AND_CAREER_GUIDE.md), [Phase 01](./PHASE_01_HARDWARE_IMPLEMENTATION.md), [Phase 08](./PHASE_08_SECURITY_MLOPS_DEPLOYMENT_PORTFOLIO.md).
