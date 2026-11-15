# Phase 01 — Practical Hardware Implementation: ESP32 Sensor Acquisition

**Project:** Industrial Edge AI Predictive Maintenance & Autonomous Operations Platform  
**Status:** Implementation guide; hardware tests are **not yet performed**.  
**Goal:** Produce timestamped, validated vibration, temperature, and DC current/voltage measurements from a guarded low-voltage motor test rig.

## 1. What you will build

```text
ADXL345 accelerometer ---- I2C ----+
INA219 DC monitor --------- I2C ----+--> ESP32 --> USB serial --> laptop CSV
DS18B20 temperature ------- GPIO ---+
12V motor -- protected supply / driver -- separate power circuit
```

**Milestone A:** Verify sensors with motor disconnected.  
**Milestone B:** Run a safely guarded low-voltage motor, collect baseline telemetry.  
**Milestone C:** Save reproducible datasets and validation evidence.

## 2. Hardware bill of materials

| Item | Qty | Role |
|---|---:|---|
| ESP32 DevKit (3.3V GPIO) | 1 | Samples and reports sensor data |
| ADXL345 breakout, 3.3V compatible | 1 | Three-axis acceleration |
| INA219 breakout, 3.3V I2C compatible | 1 | Low-voltage DC current and bus voltage |
| DS18B20 temperature sensor | 1 | Temperature near motor housing |
| 4.7 kOhm resistor | 1 | DS18B20 data-line pull-up |
| Breadboard and jumper wires | 1 set | **Sensor-side** prototyping only |
| USB data cable and laptop | 1 each | ESP32 programming and serial capture |
| Digital multimeter | 1 | Voltage, continuity and polarity checks |
| 12V DC motor and appropriately rated motor driver | 1 each | Controlled physical test load |
| 12V regulated motor supply, fuse, disconnect | 1 each | Protected motor power |
| Motor mount and rotating-parts guard | 1 each | Secure and safer experiments |

**Do not purchase or energize a motor until its rated voltage, startup/stall current, driver limits, power supply, fuse, and guarding are checked.** The INA219's module shunt and wiring must be rated for the actual motor current, including transients. If not, measure a separate low-current load or use a correctly rated current transducer.

## 3. Development environment

Install **VS Code + PlatformIO** (or Espressif ESP-IDF) and Python 3.11+. Select the actual ESP32 board definition and serial port. Use a USB data cable rather than a charge-only cable.

Example project structure:

```text
phase-01-hardware/
├── firmware/
│   ├── platformio.ini
│   └── src/main.cpp
├── scripts/
│   └── capture_serial.py
├── data/
│   └── .gitkeep
├── docs/
│   ├── wiring.md
│   ├── calibration.md
│   └── test-report.md
└── README.md
```

Do not commit private credentials, personal data or large raw datasets to the repository.

## 4. Sensor wiring (example ESP32 DevKit pinout)

**Disconnect power before wiring.** Verify the exact breakout board labels and voltage compatibility from the manufacturer. These pin assignments are *illustrative*, not a substitute for the module datasheets.

| ESP32 | ADXL345 breakout | INA219 breakout | DS18B20 |
|---|---|---|---|
| 3V3 | VCC/VIN only if breakout supports 3.3V | VCC if supported | VDD |
| GND | GND | GND | GND |
| GPIO21 (SDA) | SDA | SDA | — |
| GPIO22 (SCL) | SCL | SCL | — |
| GPIO4 | — | — | DATA |

- Put a **4.7 kOhm resistor between DS18B20 DATA and 3.3V**.
- For ADXL345 I2C mode, verify **CS** and **SDO/ALT ADDRESS** strapping required by your specific breakout. Typical 7-bit address is **0x53 or 0x1D**.
- INA219 commonly uses **0x40**, but address depends on configuration.
- The motor power path is **not** routed through the ESP32, GPIO pins or breadboard. The INA219 is placed in a suitably rated DC measurement path according to its datasheet.
- Avoid connecting 5V signals directly to 3.3V-only ESP32 GPIO.
- Power and signal grounds require a reviewed circuit design; do not assume every external supply can simply be joined.

## 5. Firmware implementation tasks

1. Create PlatformIO project for your exact ESP32 board.
2. Initialize serial output at 115200 baud.
3. Initialize I2C on GPIO21/GPIO22 and run an I2C address scanner.
4. Initialize ADXL345; configure range and sample rate appropriate to the experiment.
5. Initialize INA219; confirm shunt calibration and expected current range.
6. Initialize DS18B20 on GPIO4; verify valid conversions and reject disconnected-probe sentinel values.
7. Sample sensors at defined rates; **do not claim high-frequency vibration sampling** if the implementation is a slow polling loop.
8. Emit a structured record containing timestamp, sensor values, validity flags, and sequence number.
9. Include error counters and serial diagnostic messages.
10. Run a continuous 10-minute test before attaching the motor.

Suggested JSON Lines record (example schema, not real measurements):

```json
{"seq":1,"uptime_ms":1000,"ax_mps2":0.01,"ay_mps2":0.03,"az_mps2":9.79,"temp_c":25.2,"bus_v":12.0,"current_ma":120.0,"valid":true}
```

For actual vibration analysis, sample accelerometer readings into a fixed-size buffer with known sampling intervals, then compute RMS, peak-to-peak and frequency features. Use separate slower sampling for temperature and current. ESP32 uptime is **not** wall-clock time; synchronize and record UTC timestamps at the gateway when available.

## 6. Laptop capture and dataset format

Capture newline-delimited JSON from serial, validate fields, and append to a timestamped CSV. Suggested columns:

```text
gateway_utc,device_id,seq,uptime_ms,ax_mps2,ay_mps2,az_mps2,temp_c,bus_v,current_ma,valid,experiment_label
```

Suggested labels: `motor_off`, `healthy_low_speed`, `healthy_high_speed`, and `controlled_load_change`. Record the conditions for each experiment. Do **not** intentionally damage bearings, unbalance rotating parts, obstruct a motor, or stall it to manufacture faults.

## 7. Practical experiment sequence

### Experiment 1 — Power and communication
- Inspect all wiring with power off; verify continuity and polarity with multimeter.
- Connect ESP32 by USB and confirm firmware upload and serial logs.
- Run I2C scanner; record detected addresses.
- Verify DS18B20 values change plausibly with ambient temperature.

**Pass:** All three sensors respond; no repeated disconnects or invalid data.

### Experiment 2 — Sensor baseline
- Keep motor disconnected.
- Capture 10 minutes of telemetry.
- Calculate missing-data rate, sensor range, mean and standard deviation.
- Record sensor positions and ambient conditions.

**Pass:** Timestamped data is parseable, with a documented effective sample rate and missing-data count.

### Experiment 3 — Guarded motor run
- Secure motor and guard all rotating components.
- Use rated supply/driver, fuse and manual disconnect.
- Run short, supervised tests at supported speeds.
- Compare vibration, temperature and electrical readings against motor-off baseline.

**Pass:** Motor runs without unsafe heating or unstable wiring, and telemetry shows reproducible operating-state differences.

### Experiment 4 — Data quality
- Repeat baseline and running conditions across multiple sessions.
- Check dropped sequence numbers, duplicate timestamps and out-of-range readings.
- Compare bus voltage to multimeter measurements and record discrepancies.

**Pass:** Data quality and calibration limitations are documented.

## 8. Validation metrics

| Metric | How to measure |
|---|---|
| Effective vibration sample rate | Actual timestamps per sample / buffered acquisition timing |
| Telemetry completeness | Received valid records / expected records |
| I2C communication errors | Count read failures and retries |
| Temperature plausibility | Compare with ambient and probe placement |
| Voltage accuracy | Compare INA219 reading with multimeter |
| Repeatability | Compare feature distributions across repeated conditions |
| Safety | Confirm protection, guarding and manual disconnect |

Do not invent benchmark numbers. Save measured values and hardware revision information.

## 9. Troubleshooting

- **I2C device missing:** Verify 3.3V, ground, SDA/SCL, address pins, pull-ups and board-specific wiring.
- **DS18B20 reads invalid values:** Verify pull-up, pinout, wiring length and conversion completion.
- **INA219 readings are unexpected:** Confirm current path orientation, shunt value, calibration and module current limits.
- **ESP32 resets when motor starts:** Check supply separation, wiring, transient noise and grounding design; stop testing until fixed.
- **Vibration looks flat:** Confirm sensor mounting, data-ready/sample configuration, units and actual sample rate.
- **No serial data:** Check USB data cable, port permissions, baud rate and firmware flash status.

## 10. Deliverables to commit

- [ ] Bill of materials with exact part numbers and ratings
- [ ] Reviewed wiring schematic and clear photos of the actual setup
- [ ] Firmware source and dependency versions
- [ ] Serial-to-CSV capture script
- [ ] Sensor baseline dataset (small anonymized sample)
- [ ] Sampling-rate and data-quality report
- [ ] Controlled motor experiment notes
- [ ] Safety checklist and known limitations
- [ ] Short reproducible demo video

## 11. Next phase

**Phase 02 — Embedded IoT & MQTT:** Replace laptop-only serial capture with robust ESP32-to-edge telemetry, device identity, reconnect behavior, local buffering, MQTT schema and long-duration soak tests.

> This document describes a proposed experiment. It does not assert that any hardware has been assembled, purchased or tested.
