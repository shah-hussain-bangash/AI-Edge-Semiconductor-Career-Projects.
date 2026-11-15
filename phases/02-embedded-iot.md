# Phase 2: Embedded Systems and IoT

**Status:** Planned — implement and validate before marking complete.

## Purpose
Develop practical competency in embedded systems and iot through a verifiable build.

## Hardware
ESP32, Raspberry Pi, same sensors, Wi-Fi router

## Implementation steps
1. Prepare hardware, drivers, versions, and a wiring or system diagram.
2. Implement timestamped telemetry, MQTT publish, reconnection, local buffering, signed device identity, and simulated OTA rollback.
3. Add unit/integration tests and capture baseline measurements.
4. Repeat the experiment, log failures and limitations, and document exact reproduction commands.
5. Publish a short demonstration only after validating the results.

## Software stack and tools
FreeRTOS, ESP-IDF, MQTT, Mosquitto, Python, TLS

## Required deliverables
Firmware, message schema, broker config, packet-loss/recovery test, 24-hour soak test

## Safety and accuracy
Never expose MQTT broker or device credentials.

## Completion checklist
- [ ] Hardware or simulation environment documented
- [ ] Source code and setup commands committed
- [ ] Automated tests pass
- [ ] Quantitative evidence attached
- [ ] Security and safety constraints reviewed
- [ ] README and demonstration updated
