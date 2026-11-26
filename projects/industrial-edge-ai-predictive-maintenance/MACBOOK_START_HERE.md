# EDGEOPS home MacBook handoff

Prepared 26 November 2026. **Source and software tests only. Hosting is intentionally deferred.**
The original 30-product selection remains intact. Your 16 arriving items are a partial receipt,
not an accepted complete production system. This handoff adds a USB gateway and a separate
unverified bench-reading portal view; it does not operate a motor.

## 1. Get the complete branch

In Terminal on the Mac:

```bash
git clone --branch release/mac-bench-20261126 --single-branch https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects..git edgeops-home
cd edgeops-home/projects/industrial-edge-ai-predictive-maintenance
bash setup_mac.command
```

Git may first offer Apple's Command Line Tools. Complete that installation and retry the clone.
The setup uses an isolated `.venv-gateway`, installs only HTTPX and pySerial, and does not require
Docker, Homebrew or administrator privileges. It does not open ports, flash a board or start hosting.

Use Python 3.11–3.13; Python 3.12 is the CI reference. Install a supported, patched Python from
[python.org](https://www.python.org/downloads/macos/) if needed. Do not replace macOS's system Python.
The Python 3.12.10 universal installer documents macOS 10.13 or newer, but that historical release
has been superseded: see its [official release notes](https://www.python.org/downloads/release/python-31210/).
This is not proof that current dependencies or your USB adapter work on every old macOS version.
Your MacBook year, macOS version, USB chip and exact ESP32 model remain unconfirmed.

For a read-only environment report before installing anything:

```bash
bash setup_mac.command --check
```

## 2. Decide what can be connected when the package arrives

Read [the arrival guide](HARDWARE_ARRIVAL_16.md) before powering or flashing anything. Keep the motor,
driver and 12 V motor supply disconnected during the sensor-only milestone. Do not connect 12 V
to the ESP32, sensor supply or breadboard rails. Confirm the exact ESP32 and probe pinouts first.

## 3. Prepare the firmware only after identifying the board

The existing firmware target is **classic ESP32 `esp32dev`** with GPIO21/22 I²C and GPIO4 for a
confirmed DS18B20. It is not a universal target for ESP32-C3/S2/S3 boards. Stop if the ordered board
does not match; a different chip needs a reviewed board target and pin map, not a guessed substitution.

After verifying that target and its sensor-only wiring:

```bash
.venv-gateway/bin/python -m venv .local/firmware-venv
.local/firmware-venv/bin/python -m pip install -r phase-01-hardware/requirements-build.txt
.local/firmware-venv/bin/python -m platformio run --project-dir phase-01-hardware/firmware --environment esp32dev
.venv-gateway/bin/python mac-gateway/gateway.py --list-ports
```

Compilation does not upload anything. To upload to your verified classic board, replace the
placeholder with the exact port you observed:

```bash
.local/firmware-venv/bin/python -m platformio run --project-dir phase-01-hardware/firmware --environment esp32dev --target upload --upload-port /dev/cu.YOUR_CONFIRMED_PORT
```

Do not use that placeholder literally. Close other serial monitors. Flashing changes the board's
firmware; the repository does not automatically execute it. First builds need internet access.
If a port does not appear, verify the cable is a data cable and identify the USB-UART chip before
installing a driver. Do not install an arbitrary driver package.

## 4. Portal address: configurable, not deployed yet

**No public portal URL is provisioned by this handoff.** We will review hosting and deployment later.
The Mac can be prepared now; uploading to a nonexistent URL cannot work.

An optional local rehearsal is available without exposing a server to your home network:

```bash
bash start_local_portal.command
```

On first use, this installs the separate portal environment and asks you to create your own
administrator account. No password is preconfigured, committed or printed. Keep this Terminal open.
Visit `http://127.0.0.1:8877/app`, sign in, then open **Devices → USB bench readings**.
Your local database is `.local/portal/dashboard.sqlite3`. It is separate from a future hosted portal.
Local accounts/data will not automatically transfer to hosting. Do not open a router port or use
plain HTTP for a remote portal. The local page can be used for software rehearsal before hardware.

When the future portal is deployed, sign in there instead. In **Devices → USB bench readings**,
expand **Administrator: prepare a Mac gateway credential**, choose the exact firmware device ID
(`motor-001` in the existing firmware), enter a reason and your password, and create a scoped token.
Its lifetime is 5 minutes to 7 days. The raw token is shown once. Keep it private; it is separate
from the synthetic test-service credentials and cannot control equipment or create incidents.

## 5. Configure the Mac gateway privately

In a second Terminal in the project folder:

```bash
bash configure_gateway.command
```

Enter the future HTTPS portal root URL, the scoped bench token and the exact firmware device ID.
For a local rehearsal on the same Mac, use `http://127.0.0.1:8877` instead. The script prompts for
the token with hidden input and stores configuration in `.local/gateway.json` with private permissions.
The [example configuration](mac-gateway/config.example.json) contains placeholders only. Do not put
real tokens in examples, Git, screenshots, chat, shell arguments or committed `.env` files.

Hosting later requires a persistent database, HTTPS, trusted proxy configuration, private bootstrap
secrets and a supervised application process. The configurable gateway alone does not supply these.

## 6. Capture a verified sensor-only bench

After board, voltages and pinouts have been checked, with motor power disconnected:

```bash
bash connect_sensors.command
```

Select the observed `/dev/cu.*` port and confirm the sensor-only review. The default session is
600 seconds at the firmware's existing 115200 baud and approximately one report per second.
It does not generate a high-frequency vibration waveform or a validated predictive-maintenance model.

In the portal, refresh **Devices → USB bench readings**, or enable its visible-page 5-second refresh.
All six channels, valid zero, invalid/unavailable groups, declared source, current in amperes and
server receipt freshness are separated. No measured values replace synthetic charts or trigger
automatic incident/maintenance workflows. Source is **measured-unverified**, not authenticated
physical identity, accepted calibration, fault detection or production readiness.

To capture for up to an hour instead:

```bash
.venv-gateway/bin/python mac-gateway/gateway.py --port /dev/cu.YOUR_CONFIRMED_PORT --confirm-sensor-only --seconds 3600
```

Ctrl+C stops capture. Disconnect USB only after stopping. Do not run the capture recorder, serial
monitor and gateway against the same port simultaneously. The gateway requests exclusive serial
access on macOS and locks its pending-data spool against a second gateway process.

## 7. If the portal or network fails

The gateway saves validated frames into `.local/gateway-spool.sqlite3` before sending them.
Only a matching stored receipt removes a pending row. Network failures use bounded backoff;
authentication, identity-conflict and invalid-receipt failures stop delivery with pending data retained.
Retry without opening a USB port:

```bash
.venv-gateway/bin/python mac-gateway/gateway.py --retry-only
```

Do not delete the spool to silence an error. The local queue holds at most 10,000 pending frames;
at capacity capture stops. The portal retains at most 100,000 frames and 1,000 runs, without automatic
deletion. Retention/archive operations and long-running service acceptance remain future work.
Delivered rows are removed only from the local pending queue; server records remain retained.
Back up the private `.local` folder on the Mac while the gateway is stopped. Use the existing
dashboard backup/verify/restore tooling for the portal; it now includes bench records and revokes
restored bench credentials. Protect backups because they contain private identities and data.

Keep the same valid credential when retrying an existing run. While readings are pending, the gateway refuses changes to their portal,
credential or declared device; configuration replacement is checked before overwriting the private
configuration. A drained queue may be configured for a new destination. The spool stores only the
credential fingerprint, never the raw token. Expiry/revocation can leave a run
requiring administrator reconciliation before rotating credentials; the gateway does not silently
reassign prior data to a new token, device or source. A restart creates a new gateway run ID, not
a verified device boot ID. Deduplication covers HTTP retries of an identical gateway frame, not
physical sensor identity or every USB retransmission.

## Implementation and remaining checks

Implemented: existing dashboard and firmware sources; recent synthetic credentials/runner/MQTT,
correlation, local inbox, automatic delivery and follow-up reminders; separate scoped bench ingestion,
read-only portal view, bounded durable Mac USB gateway, private configuration and setup commands.
The release branch also retains newer GitHub security/integrity fixes instead of replacing them
with this computer's older files.

Software checks use disposable databases, fixtures, mock networks and browser rehearsals. Hosted
Intel-macOS CI can check Python setup/contracts; it cannot validate your older Mac, USB chip,
received ESP32, wiring, calibration or real motor path. No physical board was connected, no firmware
uploaded and no online portal deployed during this preparation. Your first real sensor session,
network interruption/retry, power-cycle handling, exact driver/motor/supply suitability, physical
acceptance and complete end-to-end production validation still need testing.
