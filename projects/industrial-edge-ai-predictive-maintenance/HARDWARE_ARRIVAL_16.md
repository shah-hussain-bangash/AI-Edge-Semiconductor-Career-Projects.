# Your 16 arriving items: first-bench decisions

These are the items you reported on 26 November 2026. They do not replace the original 30-product
register. Receipt and exact variants remain unverified until you inspect the package.

| # | Ordered item | First arrival check and scope |
|---|---|---|
| 1 | ESP32 development board | Read chip/module markings and USB connector/UART chip. The supplied firmware/pin map is conditional on a classic ESP32 `esp32dev`; do not flash C3/S2/S3 variants with that target. |
| 2 | ADXL345 accelerometer | Confirm module voltage and pin labels, I²C mode/address, CS/SDO configuration and 3.3 V compatibility. Initial readings are bench observations, not calibrated vibration/fault measurements. |
| 3 | INA219 / MCU-219 | Confirm it is an INA219-compatible module, shunt value/rating and permitted voltages. Logic-only sensor bring-up is separate from connecting a current-carrying load. No motor measurement circuit is authorized by this guide. |
| 4 | Likely DS18B20 probes | Confirm the actual sensor and wire/package pinout. Colour is not proof of pin assignment. If it is a thermistor or another sensor, stop and review; the supplied firmware expects DS18B20. |
| 5 | Likely TB6612FNG modules | Read the actual chip/carrier ratings and thermal limits. Keep disconnected. Motor startup/stall current and exact carrier suitability have not been established. |
| 6 | GA25-370, 12 V, 170 RPM | Keep disconnected and securely stored. Obtain the exact motor's startup/stall-current data and mechanical mounting/guard plan. Do not intentionally stall it to obtain data. |
| 7 | TEKLO TL-AC12-2A, 12 V/2 A | Confirm output label, DC polarity and connector using the multimeter before any approved load circuit. Keep it off the ESP32/sensor/breadboard supplies. It is not an ESP32 supply. |
| 8 | MB-102 breadboard | Use only the reviewed low-current sensor circuit. Inspect split power rails; never carry motor current through it. |
| 9 | Dupont jumpers | Inspect insulation/contact fit. Use for low-current signals only; check continuity when disconnected. |
| 10 | USB-A to USB-C data cable | Confirm both the received ESP32 connector and the MacBook's port match. Verify a data port appears; a power-only cable will not carry readings. An unconfirmed adapter or different cable is not silently substituted. |
| 11 | UNI-T UT33B+ multimeter | Inspect leads, rating and manual. Check DC polarity/voltage in the correct voltage mode; never put the current-input setting directly across a supply. Do not inspect inside the mains adapter. |
| 12 | 4.7 kΩ resistors | Verify value. A confirmed DS18B20 uses a DATA-to-3.3 V pull-up in the conditional sensor map. |
| 13 | DC screw-terminal connectors | Check polarity, insulation and wire/current ratings. Reserve motor-power connections for a reviewed design. |
| 14 | Inline DC ON/OFF switch cable | Check DC/current ratings and polarity. It is not proof of a safety-rated emergency stop. Keep out of the initial sensor-only circuit. |
| 15 | Inline blade fuse-holder kit | Verify DC voltage/current ratings, wire size and the protection design. No fuse value is assigned without the actual load/wire/driver data. |
| 16 | BLF enclosure 200 × 120 × 75 mm | Check fit, mounting, strain relief, ventilation and access. Leave final enclosure/powered motor assembly until the circuit is reviewed. |

## Conditional sensor-only map

Use the existing [wiring and safety guide](phase-01-hardware/docs/WIRING_AND_SAFETY.md) only after
confirming the board and modules. For a matching classic ESP32: 3.3 V/GND supply for verified
3.3 V-compatible modules, GPIO21 SDA, GPIO22 SCL, GPIO4 for a confirmed DS18B20 DATA line with
4.7 kΩ pull-up to 3.3 V. Sensor package/module pin order must come from its actual documentation.
Do not power a module just because the connector fits or wire colours look familiar.

The Toshiba TB6612FNG has specific operating/current limits, not a blanket motor compatibility
guarantee: [official product information](https://toshiba.semicon-storage.com/eu/semiconductor/product/general-purpose-logic-ics/detail.TB6612FNG.html).
The 12 V motor label alone does not establish driver, supply, shunt, fuse, wiring or thermal suitability.
Incompatible or unconfirmed parts stay blocked for review; no substitution is authorized here.

Before the first session, retain photos/markings, the reviewed sensor map, multimeter voltage/polarity
checks, detected port/address results, firmware build result and environmental/reference notes.
Then follow [the MacBook guide](MACBOOK_START_HERE.md). Do not record a physical acceptance as
passed just because compilation, a fixture or a portal page works.
