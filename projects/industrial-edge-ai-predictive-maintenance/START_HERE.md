# EDGEOPS: choose the computer first

Current handoff, 26 November 2026: development is on the office Windows PC. The home MacBook is unavailable during the day. **MacBook preflight, current ESP32 connection, sensor measurements and physical acceptance are pending.** Earlier reported upload/text-test success is prior owner evidence, not verification of tonight's setup.

| Where you are | Open this guide | What you can do |
|---|---|---|
| Office Windows; prompt starts `PS C:\...` | [Office Windows guide](OFFICE_WINDOWS.md) | Develop, run/check/gracefully stop the simulated demo, review GitHub changes and train models separately. |
| Home MacBook; macOS Terminal | [Tonight's checklist](TONIGHT_MAC.md), then [complete Mac guide](HOME_MAC.md) | Inspect the host and USB port, prepare the minimal environment, then test the physically attached ESP32. |
| Future online portal | [Existing advanced gateway handoff](MACBOOK_START_HERE.md) | Hosting and ESP32 Wi-Fi remain deferred; no public portal URL is provisioned. |

GitHub release: **`release/mac-bench-20261126`**. The default branch is not the home handoff. Clone URL (the two dots before `git` are intentional):

```text
https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects..git
```

Choose a new top-level folder under your user directory. Never clone inside another project, clone over an existing directory, discard local edits or commit private `.local/` data.

The dashboard URL is **http://127.0.0.1:8878/app on the computer running it**. Opening that address on the Mac does not connect to the office server. GitHub supplies source code; it does not host this portal or bridge USB devices between computers.

The home runtime requires supported Python 3.12–3.14 and installs **pyserial==3.5 only**. Setup/configuration must be completed after cloning. No Docker, local training, cloud account or enterprise stack is needed for the local USB bench.

Use the [test status](HANDOFF_TEST_STATUS.md) and actual GitHub Actions runs as software evidence. Physical status cannot be promoted by CI, preflight, a sample count or a successful archive checksum. The original 30-product selection and blocked part reviews remain unchanged.
