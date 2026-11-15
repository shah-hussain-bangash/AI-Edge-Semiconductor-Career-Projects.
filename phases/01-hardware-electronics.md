# Phase 1: Hardware and Electronics

**Status:** Planned — implement and validate before marking complete.

## Purpose
Develop practical competency in hardware and electronics through a verifiable build.

## Hardware
ESP32, breadboard, 3.3V temperature sensor, I2C accelerometer, multimeter, USB power

## Implementation steps
1. Prepare hardware, drivers, versions, and a wiring or system diagram.
2. Wire and read sensors; verify voltage, I2C addresses, sampling frequency and noise; log CSV.
3. Add unit/integration tests and capture baseline measurements.
4. Repeat the experiment, log failures and limitations, and document exact reproduction commands.
5. Publish a short demonstration only after validating the results.

## Software stack and tools
ESP-IDF/PlatformIO, C++, Python, serial monitor

## Required deliverables
Wiring diagram, bill of materials, sample CSV, calibration notes, 10-minute recording

## Safety and accuracy
No mains wiring; use low-voltage bench hardware.

## Completion checklist
- [ ] Hardware or simulation environment documented
- [ ] Source code and setup commands committed
- [ ] Automated tests pass
- [ ] Quantitative evidence attached
- [ ] Security and safety constraints reviewed
- [ ] README and demonstration updated
