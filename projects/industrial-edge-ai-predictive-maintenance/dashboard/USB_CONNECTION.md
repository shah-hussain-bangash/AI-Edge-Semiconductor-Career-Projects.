# ESP32 USB heartbeat connection

This optional local connection displays the existing Arduino test message
`ESP32 is working!` in the portal. It confirms recent reception of that fixed
message through the configured serial device; it does not identify the chip
cryptographically, measure sensors, flash firmware or operate a motor.

## MacBook setup with an existing portal account

Keep the ESP32 on USB power only and the motor/12V circuit disconnected.
Close Arduino Serial Monitor and any other serial reader. Stop the existing
portal with Ctrl+C in its terminal. From this dashboard directory:

```bash
git status --short --branch
git pull --ff-only origin main
.venv/bin/python -m pip install -r requirements-usb.txt
.venv/bin/python start_local.py --serial-port /dev/cu.usbserial-0001
```

Stop if Git reports conflicting/local edits or divergence; preserve them rather
than resetting or force-pulling. Use `python` (the user's confirmed Conda Python
3.11.5), not the older system `python3`, when creating a new virtual environment.
The `.venv` already created for this portal can be reused. Dependencies do not
include an LLM or model weights.

Open http://127.0.0.1:8765/app and sign in with the existing account. There is no
need to enter a new bootstrap password. The **ESP32 USB connection** panel should
show **Receiving ESP32 heartbeat** and the known message after fresh reception.
The endpoint requires the same authenticated portal session as other APIs.

For a first-ever account only, add `--bootstrap` to the launcher. It prompts
without echoing the password. Existing database accounts are not reset. Private
SQLite state remains in `.local/`, excluded from Git; never delete it to fix a
login problem. The launcher binds to loopback with one worker. Do not enable
multiple workers/reload processes competing for one serial port.

To run without opening a serial port:

```bash
.venv/bin/python start_local.py
```

## Interpret the panel

| State | Meaning / next check |
| --- | --- |
| Disabled | The portal was started without an explicit serial port. |
| Waiting | The port opened, but no matching complete heartbeat has arrived. Verify sketch and 115200 baud. |
| Receiving | A matching heartbeat was received less than five seconds ago. |
| Stale / observation expired | No recent verified heartbeat, or the browser observation has expired. This is not current connectivity. |
| Disconnected / unavailable | Opening or reading failed. Check cable, port, competing programs and `ls /dev/cu.*`. |
| Dependency missing | Install `requirements-usb.txt` in the portal's environment and restart. |

The reader retries a failed port every three seconds. Closing the server stops
the worker and releases the port. Unix opens request exclusive access, but this
is not a guarantee that every other program honors the same lock. The reader
sets DTR/RTS inactive before opening; some boards/drivers may still reset on open.
If necessary press the board's EN/RESET button once after the reader starts;
do not press BOOT or upload new firmware for this test.

Only a fixed heartbeat is displayed. Unexpected content, boot noise and overlong
lines are ignored; raw serial content and OS exception details are not exported.
Lines are bounded to 256 bytes, reads time out after one second and counters are
bounded/process-local. The panel polls every two seconds, clears on errors/sign-out
and expires a fresh observation after its remaining freshness window. A hidden
page clears its observation. No historical capture, durable queue, sensor data,
online deployment, remote forwarding or automatic hardware provisioning is added.

The catalog and system-health `hardware_connected: false` fields retain their
original unverified physical-sensor scope. `/api/usb/status` separately reports
`heartbeat_fresh`; it never changes the sample assets, sensor charts or model
claims. A fixed message could be emitted by another device; this is a connection
test, not authenticated device identity or electrical validation.

## Verification and remaining work

On 28 November 2026, the Linux development workspace ran the dashboard unittest
suite: **28 passed**, including six new heartbeat tests. Checks cover disabled
mode, permitted local ports, byte-fragment handling, overlong-line rejection,
staleness, disconnect cleanup, authenticated access and sign-out revocation.
JavaScript syntax was checked with Node. Fake serial transports are fixtures;
the user's physical ESP32 and MacBook were not accessed by these tests.

A headless browser check could not launch because this workspace lacks a working
Chromium binary. Desktop/mobile visual verification is pending. Existing framework
deprecation warnings remain; no claim of production qualification is made.

Next hardware acceptance: on the user's Mac confirm live message reception,
unplug/stale/reconnect behavior and sign-out. Then verify soldered sensor headers
and low-voltage wiring before implementing a separate validated sensor-telemetry
ingestion path. The existing text test must never be converted into invented
vibration, temperature, current or voltage readings.
