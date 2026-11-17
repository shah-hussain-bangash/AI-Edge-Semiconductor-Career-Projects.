# Industrial Edge AI - 30 Hardware Product Register

Planning edition: 17 November 2026. AED prices are estimates, not current quotations. Cart entries are not confirmed purchases.

| No. | Hardware | Purpose | Estimate (AED) | Project use |
|---:|---|---|---:|---|
| 1 | Raspberry Pi 5 (4GB) | Edge AI computer | 350-590 | MQTT ingestion, ONNX inference, local edge services |
| 2 | ESP32-WROOM-32 development board | IoT controller | 20-45 | Read sensor data and publish via Wi-Fi |
| 3 | ADXL345 accelerometer | Vibration sensing | 12-30 | Sample motor housing vibration in 3 axes |
| 4 | DS18B20 temperature sensor | Thermal sensing | 10-25 | Record motor casing temperature |
| 5 | INA219 current/voltage sensor | DC electrical monitoring | 12-35 | Read suitable low-voltage current and voltage within sensor limits |
| 6 | 12V DC motor | Rotating machine mock-up | 35-100 | Test healthy and abnormal running scenarios |
| 7 | 12V 5A regulated DC adapter | Motor power | 35-90 | Supply protected motor circuit only after verifying ratings |
| 8 | Official Raspberry Pi 5 USB-C supply | Pi power | 45-80 | Power Pi independently |
| 9 | Raspberry Pi 5 case | Board protection | 15-40 | Enclose SBC |
| 10 | Raspberry Pi 5 active cooler | Thermal management | 20-45 | Cool Pi during inference |
| 11 | 64GB microSD card | Storage | 25-55 | Raspberry Pi OS, logs and models |
| 12 | Breadboard | Prototyping | 8-20 | Low-current sensor circuits only |
| 13 | Dupont jumper wires | Signals | 8-20 | Sensor and ESP32 interconnects |
| 14 | ESP32 USB data cable | Firmware tools | 8-20 | Flash and debug ESP32 |
| 15 | Digital multimeter | Electrical testing | 30-100 | Verify polarity, voltage and continuity |
| 16 | 4.7k-ohm resistor assortment | Pull-up circuits | 5-15 | DS18B20 data pull-up |
| 17 | 5.5 x 2.1mm DC connectors (male/female) | Power connections | 4-12 | Connect compatible adapter and DC wiring |
| 18 | Inline DC fuse holder and fuse | Overcurrent safety | 8-25 | Protect DC supply near source |
| 19 | DC isolation switch | Manual shutdown | 8-25 | Cut motor power before adjustments |
| 20 | Motor shaft safety guard | Rotating-part protection | 20-60 | Shield rotating shaft |
| 21 | 12V motor driver or MOSFET module | Motor switching | 15-45 | Switch motor at appropriate electrical rating |
| 22 | Flyback diode / TVS | Transient suppression | 5-20 | Suppress motor-induced spikes |
| 23 | Hook-up wires and ferrules | Wiring | 10-30 | Secure DC wiring terminations |
| 24 | DC terminal distribution blocks | Power routing | 10-30 | Organize DC distribution |
| 25 | Motor mounting bracket/base | Mechanical stability | 20-60 | Secure motor for repeatable measurements |
| 26 | 12V-to-5V buck converter | Voltage conversion | 10-30 | Feed appropriate 5V peripheral circuits |
| 27 | I2C logic-level shifter | Signal compatibility | 5-15 | Adapt different I2C voltage levels if necessary |
| 28 | USB-to-TTL serial adapter | UART diagnostics | 10-30 | Debug 3.3V serial output |
| 29 | USB/DC inline power meter | Power consumption | 20-60 | Measure compatible input current/voltage |
| 30 | Spare ESP32 and sensor kit | Replacement/testing | 40-100 | Spare boards and comparison testing |

**Estimated total: AED 823-1,852**, excluding delivery, taxes and quantities above one.

## Architecture

12V motor -> vibration/temperature/electrical sensors -> ESP32 -> MQTT/Wi-Fi -> Raspberry Pi 5 -> ONNX edge anomaly detection -> backend/database -> dashboard alerts -> human-approved maintenance decisions.

## Procurement status

Earlier screenshots show **11 Temu cart entries**, and the **1 male + 1 female 5.5 x 2.1mm DC connector** variant was explicitly selected. No verified checkout, purchase or delivery records were provided. Therefore the number of purchased categories and the exact number remaining are **unknown**. Cart entries need reconciliation against this list.

## Safety notes

- Check adapter voltage, continuous and startup current, certification, connector dimensions and polarity.
- Do not feed 12V into 3.3V ESP32 GPIO.
- Use a fused, enclosed motor circuit and a suitable motor driver; never carry motor current through a breadboard.
- Mount the motor securely and guard the shaft. Disconnect power before changing wiring.
- Keep mains AC wiring fully enclosed; use certified ready-made external supplies.
- Record order links, test results and actual prices separately.
