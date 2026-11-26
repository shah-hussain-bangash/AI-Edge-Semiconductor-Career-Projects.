# Tonight: home MacBook checklist

**Use this only on the MacBook, in macOS Terminal.** If the prompt starts `PS C:\...`, use [OFFICE_WINDOWS.md](OFFICE_WINDOWS.md) instead. Current MacBook/ESP32 verification is **PENDING**. No hardware connection was checked while the owner was at work.

## 1. Confirm the computer before setup

Run one command and retain its actual output:

```bash
uname -s
```

Expected OS type: `Darwin`. This does not display the macOS version or prove hardware readiness. Then collect the OS version and current device names:

```bash
sw_vers -productVersion
ls /dev/cu.*
```

The previously reported ESP32 port was `/dev/cu.usbserial-0001`; use tonight's actual result. Listing ports does not open the board. An office Windows computer cannot see a USB board connected at home.

## 2. Get the release without overwriting work

If no clone exists yet, use this first-time block in Mac Terminal. It selects your home directory, refuses an existing destination, and stops on clone/setup failure:

```bash
(
set -e
cd "$HOME"
if [ -e edgeops-home ]; then
  printf '%s\n' 'edgeops-home already exists. Preserve it and use the existing-clone instructions below.'
  exit 1
fi
git clone --branch release/mac-bench-20261126 --single-branch https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects..git edgeops-home
cd edgeops-home/projects/industrial-edge-ai-predictive-maintenance
bash home_preflight.command
bash home_setup.command
open -a "Visual Studio Code" .
)
```

The preflight prints host details, candidate Python versions and port names; it makes no configuration/environment/database changes, opens no serial port and does not execute Git or Apple's system Python stub. Exit 0 means the report ran, **not** that setup or hardware passed. It can report that supported Python is missing. Setup then needs Python 3.12, 3.13 or 3.14; see [requirements](HOME_MAC.md#requirements-and-first-setup). Initial cloning/package installation needs internet. macOS may ask for Command Line Tools when you first invoke Git; that is separate from preflight and requires completing Apple's own installation flow.

If the project already exists, open its actual folder, stop its dashboard first, and inspect `git status` and `git branch --show-current`. Use the release branch and preserve all local work. An existing prepared environment can run `bash home_update.command`, which refuses dirty/different-branch/non-fast-forward updates. If the checkout predates that helper, or no environment is ready, follow [the complete existing-clone instructions](HOME_MAC.md#requirements-and-first-setup) before running setup. Do not run the first-time clone block inside an existing project.

## 3. Confirm ESP32-only communication

Keep motor, driver and 12 V power disconnected. Connect the board with its USB data cable. Close Arduino Serial Monitor and every other serial reader. The existing `ESP32 is working!` sketch at 115200 baud needs no replacement for this test.

In the home project folder, after successful setup:

```bash
bash home_start.command
```

Keep that Terminal open. In a second Terminal:

```bash
open http://127.0.0.1:8878/app
```

The page now includes **Connect your home hardware**, a live connection checklist, local setup/wiring/recovery guides and **Check setup snapshot**. The downloadable troubleshooting report contains software versions, free disk space, selected port, reader counts and sensor-group availability. It excludes passwords, anti-forgery tokens, raw samples and local database paths. Review the report before sharing; port names and host details are still personal machine information. It never certifies wiring or hardware.

Choose **ESP32-only communication test**, enter the confirmed current port and click **Start selected session**. Expected communication evidence: accepted count increases, source is **SIMULATED / TEST**, and all six sensor values remain **Unavailable**. No real sensor readings are fabricated. If no frames are accepted, stop and review port/baud/firmware rather than changing wiring or powering the motor.

## 4. Optional timed recording after communication works

For a short communication recording, choose 10 seconds in **Timed raw USB recording** and start it. The reader restarts and may reset the ESP32. At the end, download the raw recording and review its stop reason/counters. A 600-second recording can be collected later under the reviewed sensor-only procedure. A duration or accepted count alone never passes H1. See [timed recording details](HOME_MAC.md#record-a-timed-usb-test).

Ctrl+C in the original server Terminal stops both server and reader. The dashboard's **Disconnect reader** stops the reader while keeping the page service available. Export required packages before closing/changing sessions; private finalized capture folders stay under `.local/home/captures`.

## What to bring back to this chat

Paste the **actual** `uname -s`, macOS version and port-list output; supported Python/preflight result; and any exact setup/reader error. If the communication test runs, report mode, accepted/rejected counts and the six-channel unavailable state. Keep raw archives private until reviewed; firmware diagnostic text can contain sensitive information. Do not send Wi-Fi passwords, portal tokens or API keys.

Still pending: exact sensor/probe/driver identification, ADXL345 soldering, reviewed wiring/ratings, reference measurements, firmware provenance, motor commissioning, real-data AI validation, Wi-Fi and online hosting. Do not connect all modules or energize the motor as part of this checklist.
