# Hardware Requirements — Industrial Edge AI Predictive Maintenance Platform

**Status:** Proposed purchasing and implementation plan, not evidence of purchased or tested hardware.

## Objective
Build a low-voltage DC motor condition-monitoring demonstrator: sensors -> ESP32 -> Raspberry Pi / optional Jetson -> AI anomaly detection -> backend -> dashboard -> human-approved maintenance workflow.

## Core controllers and computers

| Hardware | Qty | Purpose / function | Priority |
|---|---:|---|---|
| ESP32 DevKit | 1–2 | Sample I2C/GPIO sensors, timestamp and transmit measurements over Wi-Fi | Essential |
| Raspberry Pi 5 (4GB or 8GB) | 1 | Edge telemetry receiver, signal processing, ONNX inference, local buffering and alerts | Recommended |
| NVIDIA Jetson Orin Nano Super Developer Kit | 1 | Optional GPU-accelerated inference and chip-performance comparisons | Later |

## Condition-monitoring sensors

| Hardware | Qty | Purpose / function | Notes |
|---|---:|---|---|
| ADXL345 3-axis accelerometer | 1–2 | Measure vibration changes for introductory anomaly detection | Not a calibrated high-bandwidth industrial vibration analyzer |
| DS18B20 temperature probe | 1–2 | Track motor housing temperature and thermal trends | Use suitable mounting and required pull-up resistor |
| INA219 current/voltage monitor | 1 | Measure low-voltage DC motor load and power | Verify motor start/stall current and shunt ratings |
| BME280 environmental sensor | 1 | Optional ambient temperature/humidity context | Later |
| Hall-effect RPM sensor | 1 | Optional motor speed measurement | Later |
| INA226 module | 1 | Optional alternative electrical monitoring | Verify operating limits |

## Physical test equipment

| Hardware | Qty | Purpose / function |
|---|---:|---|
| 12V low-voltage DC motor | 1 | Produces measurable mechanical and electrical signals |
| Appropriately rated motor driver (e.g. TB6612FNG for a compatible small motor) | 1 | Controlled motor-speed experiments; match continuous and startup currents |
| Secure motor mount/base | 1 | Repeatable, stable sensor measurements |
| Protective rotating-parts guard | 1 | Reduce contact with moving parts |
| Regulated 12V motor power supply | 1 | Power the motor within rated limits |
| Inline fuse and manual emergency power disconnect | 1 each | Circuit protection and quick motor power removal |

## Prototyping, power and measurement accessories

| Hardware | Qty | Purpose |
|---|---:|---|
| Breadboard | 1–2 | Initial sensor prototyping, not final motor-current wiring |
| Jumper wires and hookup wire | 1 set | Connect low-power modules |
| USB data cables | 2 | Flash and debug ESP32, connect devices |
| Suitable USB supply for ESP32 | 1 | Controller power |
| Compatible Raspberry Pi 5 power supply | 1 | Stable edge-computer power |
| microSD card or SSD | 1 | Edge OS and storage |
| Raspberry Pi case and cooling | 1 | Protect and cool processor |
| Digital multimeter | 1 | Verify voltage, polarity and continuity |
| 4.7 kOhm resistors | Several | DS18B20 pull-up when required |
| Terminal blocks/connectors | 1 set | Secure connections |
| Nonconductive electronics enclosure | 1 | Protect controller and wiring |
| Wi-Fi router / local network | 1 | ESP32-to-edge communications |

## Optional industrial expansion
- Industrial vibration sensor: higher-quality condition-monitoring data.
- Industrial temperature probe/interface: more robust thermal measurements.
- Appropriately rated isolated current transducer: larger electrical equipment.
- Isolated RS485/Modbus interface: connect compatible industrial devices.
- Industrial IoT gateway: rugged edge communications and device management.
- UPS: resilience to brief power loss.
- Ethernet switch and cabling: wired networking.
- FPGA development board: separate RTL/AI accelerator learning project.

## Practical architecture

```text
Low-voltage DC motor
   |-- ADXL345 vibration
   |-- DS18B20 temperature
   '-- INA219 current/voltage
             |
             v
      ESP32 sensor firmware
             |
        Wi-Fi / MQTT
             |
             v
   Raspberry Pi 5 (or Jetson)
   - telemetry and signal processing
   - ONNX anomaly detection
   - local alarms and buffering
             |
         secure API
             |
             v
   FastAPI + PostgreSQL/TimescaleDB
             |
   dashboard + RAG maintenance assistant
             |
     human-approved work order
```

This is a functional architecture, **not** an electrical wiring schematic. Design and review wiring, grounds, power distribution and protection separately.

## Purchase order
1. **Sensors first:** ESP32, ADXL345, DS18B20, INA219, breadboard, USB cables, resistor and multimeter. Verify sensor data on a laptop.
2. **Motor test bench:** DC motor, correctly rated driver, power supply, mounting base, guard, fuse and disconnect. Record healthy baseline data.
3. **Edge inference:** Raspberry Pi 5, storage, cooling and power supply. Run signal processing and a small ONNX model.
4. **Advanced optimization:** Jetson and industrial-grade sensors only after the baseline prototype works.

## Acceptance tests
- [ ] Record sensor module model numbers, voltage ratings and wiring diagram.
- [ ] Read all three sensors reliably and validate values with a reference measurement where possible.
- [ ] Record at least 10 minutes of timestamped baseline data.
- [ ] Measure sampling rate, packet loss and recovery after Wi-Fi disconnection.
- [ ] Train and evaluate an anomaly model with held-out recordings.
- [ ] Deploy local inference and record latency, accuracy and memory usage.
- [ ] Demonstrate a maintenance alert and human approval workflow.
- [ ] Document safety limits, failure cases and reproducible setup.

## Safety
Use only a guarded low-voltage test rig. Never wire mains equipment directly to hobby sensor boards. Confirm motor stall current, driver rating, power supply rating, sensor voltage levels and protection before energizing. Do not allow an AI agent to control safety-critical equipment without appropriate independent safety engineering.

## Estimated budget
A basic prototype with Raspberry Pi may be approximately **AED 800–1,600**; with a Jetson upgrade, approximately **AED 2,000–4,000+**. These are illustrative planning estimates, not verified retailer quotations. Check UAE supplier availability and compatible part numbers before purchasing.
