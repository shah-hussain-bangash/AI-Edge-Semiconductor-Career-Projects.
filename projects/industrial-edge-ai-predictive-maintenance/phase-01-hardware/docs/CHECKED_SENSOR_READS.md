# Checked sensor reads: software behavior, not calibration

Prepared 26 November 2026. No board was uploaded or physically measured for this change. Keep the existing ESP32 communication-test sketch for the first home connection test. Sensor firmware is a later, manually reviewed upload after actual parts and wiring are confirmed.

## Problem and resulting behavior

The previous sensor loop checked presence only at startup and used finite converted numbers as its validity test. A failed register read could still yield a finite value. The sensor-only firmware now checks complete I2C reads and the expected runtime configuration before setting each group's V1 validity flag.

- ADXL345 at the existing default 0x53 address: check device identity, full-resolution/right-justified +/-16 g configuration and awake measurement mode; read all six axis bytes in one transfer. Any failed/short transfer or configuration mismatch leaves the entire acceleration group invalid. Nominal full-resolution conversion remains 0.004 g/LSB, expressed in m/s² with 9.80665 m/s² as the declared standard-gravity conversion constant.
- INA219 at the existing default 0x40 address: require the prior library preset's config 0x399f and calibration 0x1000, conversion-ready status, no math-overflow flag, complete voltage/current reads, and matching calibration on a second read. A failure invalidates both voltage and current. Current remains signed mA in V1; the home adapter still converts it to A once.
- The INA219 conversion preserves the existing **nominal 0.1-ohm shunt assumption** and 0.1 mA/LSB scale. The library preset's name is not an electrical rating or approval of an actual MCU-219 board, shunt, wiring, supply or motor. Exact shunt identity and reference measurements are still mandatory. A different actual shunt/configuration needs a separately reviewed conversion; this change does not authorize substitutions or automatic recalibration.
- The Wire adapter requires a successful register-pointer write, successful repeated-start transaction, exact byte count and available bytes, and successful byte reads. The ESP32 Wire timeout is set to 50 ms. Timeout, sampling rate and recovery still need measurements on the received board. No bus power cycling, equipment commands or automatic reinitialization is added.
- Invalid groups retain V1 numeric placeholders with false validity flags, so the dashboard shows **Unavailable**, not measured zero. A genuine valid zero remains zero. DS18B20 handling, the 115200 baud V1 schema, pin assignments and nominal 1 Hz summary schedule remain unchanged.

If a sensor was absent at boot, or loses configuration, it stays unavailable until the actual issue is reviewed and the board is restarted under the approved setup. Do not unplug powered sensor wiring to test this change. These checks do not authenticate a device or prove fresh internal sensor conversion, bus atomicity across multiple registers, sensor calibration, electrical compatibility, vibration bandwidth or predictive accuracy. Register agreement alone cannot identify a physical board manufacturer.

## Build, package and software checks

Keep `firmware/include/checked_sensors.h` alongside `firmware/src/main.cpp`; the PlatformIO project automatically supplies its include directory. Do not copy only main.cpp into an Arduino sketch and omit the header. Build instructions and pinned dependencies remain in [FIRMWARE_BUILD.md](FIRMWARE_BUILD.md). The compile-only workflow records hashes for the header as well as the original source/configuration/artifacts. Nothing here flashes the board automatically.

Native C++ fake-bus fixtures execute the actual helper header. They cover successful signed values and valid zeros; each read failure; missing devices; wrong ADXL identity/range/power mode; short transfers; INA configuration/calibration mismatch, conversion-not-ready, overflow, calibration loss between reads; partial group availability; and Wire pointer-write/NACK/count/byte failures. They run through `tests/test_checked_sensor_reads.py` on Linux/Intel Mac CI with a C++ compiler. A machine with no compiler skips that local check explicitly; an expected Linux/Mac CI compiler failure is an error. Compiling the actual ESP32 target is a separate check. Neither test substitutes for physical measurements.

New arrival exports use **edgeops-arrival-pack-v3**, including this document, the helper header and native fixtures. The verifier retains exact v1/v2 inventory support for old unchanged archives. Existing saved archives are not rewritten; a newly generated v3 archive missing the header is rejected even if its manifest is rehashed. File consistency is not physical acceptance.

## Primary technical references

- [Analog Devices ADXL345 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ADXL345.pdf): register map, full-resolution data formatting and axis register reads.
- [Texas Instruments INA219 datasheet](https://www.ti.com/lit/ds/symlink/ina219.pdf): current/bus register formats, calibration, conversion-ready and overflow semantics.
- [Pinned Adafruit ADXL345 1.3.4 implementation](https://github.com/adafruit/Adafruit_ADXL345/blob/1.3.4/Adafruit_ADXL345_U.cpp) and [header](https://github.com/adafruit/Adafruit_ADXL345/blob/1.3.4/Adafruit_ADXL345_U.h).
- [Pinned Adafruit INA219 1.2.3 implementation](https://github.com/adafruit/Adafruit_INA219/blob/1.2.3/Adafruit_INA219.cpp): prior preset and nominal scaling assumptions.

All physical acceptance remains pending. Use [the guided phase sequence](../../NEXT_PHASES.md) before sensor work.
