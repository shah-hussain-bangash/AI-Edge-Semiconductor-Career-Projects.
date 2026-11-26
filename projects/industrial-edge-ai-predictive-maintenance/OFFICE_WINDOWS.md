# Office Windows development and simulated dashboard

Use **Windows PowerShell** here. The home MacBook and ESP32 are unavailable for verification during the workday; their checks remain **PENDING**. Run Mac commands tonight using [TONIGHT_MAC.md](TONIGHT_MAC.md). `bash` on Windows is not a connection to the home Mac, and `/dev/cu.*` is not a Windows serial port.

## Existing office checkout

From the project folder, these commands inspect the environment and list local ports without opening hardware:

```powershell
.\home.ps1 -Action Check
```

To start a software-only demo:

```powershell
.\home.ps1 -Action Demo
```

If a home server already responds, the launcher reports its URL without starting another copy or changing its reader. Open or refresh it with:

```powershell
Start-Process "http://127.0.0.1:8878/app"
```

Demo numbers are simulated. They do not show readings from the board at home. The demo cannot start a raw USB recording. Model training belongs in the separate office development environment; the home environment stays minimal.

## First-time office checkout only

Use this only when `edgeops-office` does not already exist in your user directory. Leave previous folders intact; never clone inside another project.

```powershell
Set-Location $env:USERPROFILE
if (Test-Path -LiteralPath 'edgeops-office') { throw 'Existing folder preserved. Use its project folder and review git status.' }
git -c core.longpaths=true clone --branch release/mac-bench-20261126 --single-branch https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects..git edgeops-office
if ($LASTEXITCODE -ne 0) { throw 'Clone failed; stop here.' }
Set-Location 'edgeops-office/projects/industrial-edge-ai-predictive-maintenance'
pymanager exec -V:3.13 home-mode/manage.py setup
if ($LASTEXITCODE -ne 0) { throw 'Setup failed; stop here.' }
.\home.ps1 -Action Demo
```

The `pymanager` example uses the owner's already installed Python 3.13. It is not a requirement to install another global Python. With an installed Python 3.12–3.14 `python` command, `.\home.ps1 -Action Setup` is available; `-PythonPath` accepts an explicit installed executable. Runtime installs only `pyserial==3.5`. Scripts preserve unmanaged existing environments and do not change global execution policy.

## Inspect or stop an updated demo

After this release is installed **and its server restarted**, use:

```powershell
.\home.ps1 -Action Status
.\home.ps1 -Action Stop
```

`Status` is read-only and redacts anti-forgery tokens. `Stop` sends a graceful loopback shutdown only when the server identifies this exact checkout and expected data directory, reports the supported control protocol and is currently in demo mode. The server rechecks the mode and prevents a new USB reader from starting during shutdown. The helper waits for the process lock to release. It does not look up or kill a PID, delete locks, stop USB/recording sessions, follow HTTP redirects or use environment proxies. This identity is an accidental-mismatch guard for a personal local tool, not authentication for an online portal.

For a different web port, pass `-WebPort 8879` to both commands. The Windows launcher expects the default `.local/home` data folder. An explicitly configured custom folder can use the environment Python with `home-mode/manage.py status --web-port 8879 --data-dir YOUR_PRIVATE_FOLDER` or `stop-demo` with the same options. Use your actual private path. A different data directory is refused unless explicitly selected. No custom-folder update is automated.

A running pre-upgrade server has no supported instance identity; `Stop` deliberately refuses it. Use Ctrl+C or the one-time legacy procedure below, then update and restart. Installing new source does not update code already loaded in an older running process.

## Stop before updating

For an updated demo, use `.\home.ps1 -Action Stop`. For a USB/recording session or an older server, use Ctrl+C in the Terminal originally running the server. **Disconnect reader** closes USB reading, but the server still holds its process lock. Closing only the browser does not stop the server. Repeating Start/Update cannot release that lock.

A pre-upgrade demo started by the assistant may run in the background. If its original Terminal is unavailable, the one-time legacy block below stops **only a responding demo owned by this exact project**. It checks the live port owner and command line, gracefully disconnects the reader, and then stops the verified process. It refuses a different project, a non-demo session or an unknown service. It does not use a PID copied from an older chat.

Run this only from the intended project folder when you want to stop its office demo:

```powershell
$ErrorActionPreference = 'Stop'
$expectedPython = (Resolve-Path '.venv-home/Scripts/python.exe').Path.Replace('\','/')
$baseUrl = 'http://127.0.0.1:8878'
$state = Invoke-RestMethod -Uri "$baseUrl/api/status" -TimeoutSec 5
if ($state.scope -ne 'edgeops-lightweight-home' -or $state.settings.mode -ne 'demo') { throw 'Not the expected demo; nothing stopped.' }
$listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8878 -State Listen
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
if (-not $processInfo.CommandLine) { throw 'Cannot identify process; nothing stopped.' }
$command = $processInfo.CommandLine.Replace('\','/')
if ($command -notlike "*$expectedPython*home-mode/home_server.py*--mode demo*") { throw 'Process belongs to another project or launch mode; nothing stopped.' }
Invoke-RestMethod -Uri "$baseUrl/api/disconnect" -Method Post -ContentType 'application/json' -Headers @{ Origin=$baseUrl; 'X-Edgeops-Home-Token'=$state.write_token } -Body '{}' -TimeoutSec 8 | Out-Null
Stop-Process -Id $listener.OwningProcess
```

If process lookup is unavailable or the block refuses, preserve the running service and use its original Terminal or ask for help identifying it. Do not kill all Python processes or delete a lock file to force an update.

After stopping the intended home server (for an updated demo, `-Action Stop`), update and launch:

```powershell
.\home.ps1 -Action Update
if ($LASTEXITCODE -eq 0) { .\home.ps1 -Action Demo }
```

If either command reports an error, stop and review it before continuing. Update refuses running default sessions, tracked edits, non-ignored new files, a different branch and non-fast-forward history. It never stashes, resets, cleans or discards work. `.local/`, `.venv-home/` and capture downloads remain private/ignored. Stop custom-data-directory sessions yourself before updating too.

For an old prepared checkout without `home.ps1`, after stopping its server:

```powershell
.\.venv-home\Scripts\python.exe home-mode/manage.py update
if ($LASTEXITCODE -eq 0) { .\home.ps1 -Action Demo }
```

Use the release **`release/mac-bench-20261126`**. Office source changes should be reviewed/tested and pushed to that branch for the home handoff. Read [test status](HANDOFF_TEST_STATUS.md) for the difference between CI fixtures and physical verification. Online hosting/ESP32 Wi-Fi and all remaining physical acceptance work are pending.
