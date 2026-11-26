# EDGEOPS: office development, lightweight home bench

Prepared 26 November 2026 for the reported Early 2015 Intel MacBook Air, 4 GB RAM, macOS Monterey 12.7.6. This is a **local USB bench tool**, not an accepted production deployment. Original 30-product selections and blocked part reviews are preserved; receiving 16 categories does not complete the system.

## What source inspection found

Inspected release base `597f8ca87c4813238c0653cb26e0784b6194e359`. Use this release branch; the default branch may differ.

| Area | Existing implementation and remaining boundary |
|---|---|
| Full dashboard | Synthetic operational workflow remains available. Its simulated health/maintenance screens are not live physical acceptance. |
| USB sensor firmware | `phase-01-hardware/firmware/src/main.cpp` emits JSON V1 at 115200 baud. Invalid groups include numeric placeholders; home mode converts these to unavailable, not zero measurements. |
| USB to full portal | Already partly integrated: `mac-gateway/gateway.py` posts to the scoped bench-ingest backend and a separate Devices bench view. A portal URL and credential are required. This was not wholly missing. |
| Direct home USB dashboard | Added `home-mode`: standard-library HTTP/SQLite plus pySerial, no portal credential or full backend required. |
| Wi-Fi / MQTT | Lab MQTT and API code exist. Supplied ESP32 firmware has **no Wi-Fi/MQTT network transmission**. Direct ESP32 Wi-Fi integration remains pending. |
| Online portal | Separate gateway supports configurable HTTPS delivery and a private durable queue. Hosting, public URL, credential provisioning and real remote operation are **pending**. Home mode does not upload remotely. |
| Physical hardware | Owner reports successful ESP32 upload and repeated `ESP32 is working!` on `/dev/cu.usbserial-0001`. This change did not independently repeat that test. ADXL345 headers still require soldering; wiring, exact probe/driver identification and calibration remain pending. |

## Requirements and first setup

Use a current patched **Python 3.12, 3.13 or 3.14** from python.org. For a new installation, the current Python 3.14 macOS universal installer supports macOS 10.15+, including Monterey's OS version: [official Python 3.14.10 release](https://www.python.org/downloads/release/python-31410/). This is an OS requirement check, not verification on your particular Mac. Do not replace Apple's system Python. Open a new Terminal after installation.

Home runtime has one external dependency: **`pyserial==3.5`**. Everything else uses Python's standard library. Setup creates a dedicated `.venv-home`; it does not install Docker, FastAPI, model training, Node, PlatformIO or the enterprise stack. Internet is needed for cloning and initial dependency installation, not subsequent local USB display.

In Mac Terminal, in a directory where `edgeops-home` does not already exist:

```bash
git clone --branch release/mac-bench-20261126 --single-branch https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects..git edgeops-home
cd edgeops-home/projects/industrial-edge-ai-predictive-maintenance
bash home_setup.command --check
bash home_setup.command
open -a "Visual Studio Code" .
```

If Git asks for Apple Command Line Tools, complete that installation and retry. If you already cloned this branch, do not clone over it: stop running services, enter the existing project folder, review `git status`, and use `git pull --ff-only origin release/mac-bench-20261126` only when clean, followed by `bash home_setup.command`. Never discard local work to make these instructions succeed. Setup refuses an existing unmanaged `.venv-home` rather than replacing it.

## ESP32-only communication test

Keep the motor, motor driver and 12 V supply disconnected. Connect the board through the USB data cable. Close Arduino Serial Monitor and all other serial readers first. Opening USB serial may reset the ESP32. No equipment-control commands are sent.

Your existing sketch printing `ESP32 is working!` at **115200 baud** is supported without a new upload. Check the actual current port:

```bash
ls /dev/cu.*
bash home_start.command --mode esp32-only --port /dev/cu.usbserial-0001 --connect
```

Keep that Terminal open. In a second Terminal:

```bash
open http://127.0.0.1:8878/app
```

This is the portal link **on the Mac running home mode**. `127.0.0.1` on the office PC points to the office PC, not your Mac. There is currently no hosted online portal URL.

The page should show accepted communication records labelled **SIMULATED / TEST**, with all six sensor values **Unavailable**. The text sketch supplies no verified device identity, sequence, boot ID or device clock; these are not invented. The frame's host receipt UTC is the computer's receipt time, not synchronized device time.

An optional Arduino-only sketch at `phase-01-hardware/esp32_only/esp32_only.ino` emits JSON V1 with **all sensor-valid flags false**. Open it in Arduino IDE, choose the reported classic **ESP32 Dev Module**, confirm the actual USB port, and upload manually only if you choose to replace the current sketch. No sensor libraries, Wi-Fi password or motor wiring are needed. Its software compile check is not a board upload test.

For a demo without any USB hardware:

```bash
bash home_start.command --mode demo --connect
```

All numeric examples in this mode are simulated. They do not prove that a sensor is connected.

## Sensor readings later

Only after soldering and reviewing exact module pinouts, voltage and wiring, upload the existing JSON V1 sensor firmware using its documented board/library configuration. Keep motor power disconnected during sensor-only bring-up. Then:

```bash
bash home_start.command --mode sensors --port /dev/cu.usbserial-0001 --device-id motor-001 --connect
```

The expected device ID must match the firmware. Text-test messages are rejected in sensor mode. Per-sensor validity flags determine availability: a valid numeric **0 stays 0**, an invalid channel stays **Unavailable**, and INA219 milliamps are converted to amps once. All readings remain **USB SENSOR DATA · UNVERIFIED** until physically checked. The firmware's validity flag alone is not calibration or provenance proof.

After 5 seconds without a usable frame, current values clear. On a detected serial/storage error or reader stop they clear immediately. Retained history remains separate. Reconnect explicitly after cable/port problems; there is no automatic reconnect loop. This mode does not generate health predictions or train a model.

## Start, stop and future office updates

Without arguments, `bash home_start.command` opens the dashboard with the last saved selection, but does not start a reader automatically. Choose a mode and click **Start selected session**. **Disconnect reader** closes the serial reader while keeping the web page service running. **Ctrl+C in the server Terminal** stops both. To close VS Code, use its normal Quit command.

For future office changes: develop/test on Windows and push reviewed source to `release/mac-bench-20261126`. On the Mac, first stop home mode with Ctrl+C, then from the project folder:

```bash
bash home_update.command
bash home_start.command --mode esp32-only --port /dev/cu.usbserial-0001 --connect
```

The update script refuses a different branch, any tracked changes or non-ignored new files, a running default home session, and non-fast-forward history. It never stashes, resets, cleans or overwrites local work. It then reruns setup for pinned dependencies. If it stops, review/commit your own changes before retrying; do not put secrets in a commit. When using a custom `--data-dir`, stop that session yourself too.

Office model training stays in the separate development/training environment. Exported home CSV includes source, mode and verification flags; keep simulated and unverified observations distinguishable when curating training datasets. No office-trained model is automatically activated in home mode.

## Private local files and limits

Selection settings, process lock and SQLite history are in **`.local/home/`**, ignored by Git. There are no required credentials for home mode. `.venv-home/`, `.vscode/`, existing environment/credential paths and local databases are ignored. Keep future portal tokens, Wi-Fi passwords and API keys in private local configuration/environment files, never source or firmware commits. Existing remote-gateway credentials/queues stay separate and are not read by home mode.

History retains the **most recent 10,000 records** across sessions (about 2.8 hours at 1 Hz). Older rows are removed automatically. The UI shows/exports the last 60; API history/CSV accepts `limit=1` through `200`. Export required records before they roll out. These limits favor a small home installation; this is not an archival or backup service. Hash checks detect retained payload corruption, not malicious tampering. A complete baseline session still needs a separate capture/retention plan.

The service listens only on **127.0.0.1:8878**, with same-origin write checks and a per-process anti-forgery token. It is a personal local bench tool, without enterprise authentication or remote-device control. Do not expose/forward the port to a network. No remote upload, credentials, firmware flashing or motor control occurs during setup or launch.

## Troubleshooting

| Symptom | Action |
|---|---|
| Python not found / unsupported | Install a supported patched Python from python.org, reopen Terminal, run `bash home_setup.command --check`. Apple's bundled Python may be unsuitable. |
| `.venv-home` already exists unmanaged | Preserve it; use a fresh clone or deliberately rename your own environment before setup. Nothing is overwritten automatically. |
| No USB port | Reconnect the data cable and board; compare `ls /dev/cu.*` before/after. Office Windows cannot see USB hardware connected at home. Investigate the actual USB chip/driver if still absent. |
| Port busy / reset | Close Arduino Serial Monitor, existing capture/gateway programs and other home sessions. One program owns USB serial. Do not run the HTTPS gateway and home reader simultaneously on the same port. |
| Accepted count remains zero | Match 115200 baud, selected port, expected JSON device ID and mode. Existing text sketch needs `esp32-only`; structured sensor frames with valid sensor flags need `sensors`. Boot diagnostics and malformed/oversized frames are not measurements. |
| Sensors unavailable | Expected for ESP32-only. In sensor mode inspect exact wiring/validity flags; no replacement readings are fabricated. ADXL345 unsoldered headers are not verified electrical connections. |
| Stale/error after unplug | Values clear; fix the cable/port and press Start selected session again. History is not a live status indicator. Also check free disk space/private directory access if storage fails. |
| Port 8878 busy | Stop the existing home Terminal, or use `bash home_start.command --web-port 8879` and open `http://127.0.0.1:8879/app`. No process is killed automatically. |
| Invalid saved configuration | Original file is preserved. Review `.local/home/config.json` against `home-mode/config.example.json`; no secrets belong in this file. |
| `code` command absent | Use `open -a "Visual Studio Code" .`; adding VS Code's command to PATH is optional. |
| Update refuses changes | Run `git status` and review your work. Commit appropriate source or keep working in your branch; do not discard changes to force an update. |

## Verification boundary

See [handoff test status](HANDOFF_TEST_STATUS.md) and the actual GitHub Actions results for this commit. Software tests use fake serial streams and POSIX pseudo-terminals, not your board. Hosted Intel macOS is newer than Monterey. Your 2015 Mac, Safari/Arduino/USB driver, actual sensor wiring, measured accuracy, long-duration capture, power-loss recovery and complete end-to-end production acceptance still need home measurements.
