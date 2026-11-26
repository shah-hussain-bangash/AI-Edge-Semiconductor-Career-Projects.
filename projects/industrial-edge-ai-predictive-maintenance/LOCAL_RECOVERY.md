# Local recovery, recordings and optional login startup

These are local software features. Hosting stays deferred at the owner's request. Physical MacBook/ESP32/sensor/motor verification and real-data AI acceptance remain pending.

## Back up before changing or updating data

A backup is a **cold snapshot**: stop the intended server first. Closing a browser or only disconnecting a reader is not enough. An updated Windows demo can use `home.ps1 -Action Stop`; an older server follows the one-time legacy procedure in [OFFICE_WINDOWS.md](OFFICE_WINDOWS.md). A Mac login service uses its own stop command below. Active process locks cause backup refusal; no running session is force-killed.

Windows PowerShell, from the project folder:

```powershell
.\home.ps1 -Action Backup
```

Mac Terminal, after stopping the intended server:

```bash
bash home_data.command backup
```

The command prints the new private backup folder under `.local/backups/`. `-OutputDirectory` (Windows) or `--output` (Mac) can select a **new** private folder. Existing destinations and destinations inside the source data folder are refused. Backups include home configuration, a consistent SQLite database snapshot, recordings, incomplete recording files and other home files/logs. The process lock and SQLite WAL/SHM files are excluded; committed WAL data is incorporated through SQLite's backup API. Completed backup databases are self-contained and validated. This is the home data folder only, not the separate portal/gateway credential queues or the entire repository.

Limits: 512 MiB total, 256 MiB per file and 5,000 files. Oversized datasets fail explicitly rather than being truncated. Symbolic links/junctions, unsafe/nonportable paths and corrupt history checksums are refused. Config and history labels are validated without promoting hardware/calibration/production flags. Backups can contain private diagnostic text; keep them outside Git and share only after review. Final checksums detect inconsistency, not authenticity or malicious rewriting.

## Verify and restore without replacing the original

Use actual private paths printed by Backup; the following are examples to adapt. A new restore directory must not already exist.

Windows PowerShell:

```powershell
.\home.ps1 -Action VerifyBackup -BackupDirectory '.local/backups/YOUR_BACKUP'
.\home.ps1 -Action Restore -BackupDirectory '.local/backups/YOUR_BACKUP' -RestoreDirectory '.local/home-recovered-NEW'
```

Mac Terminal:

```bash
bash home_data.command verify-backup --backup .local/backups/YOUR_BACKUP
bash home_data.command restore --backup .local/backups/YOUR_BACKUP --destination .local/home-recovered-NEW
```

Restore verifies the package before creating a destination, then validates the copied data. It never overwrites `.local/home` or changes the active data location. `RESTORE_INCOMPLETE` blocks server startup if a new restore fails part-way; the partial folder is preserved for inspection. Do not remove that marker to force startup. Original data and the verified backup remain intact.

After successful restore, inspect the new folder before choosing it explicitly with the server's `--data-dir` option. Merely restoring files does not launch a reader, install a service or certify measurements. Back up to a separate trusted disk/location when actual disaster protection is needed; a second folder on the same disk is only a local recovery copy. No automatic off-site backup or retention deletion is configured.

## Saved recordings after restart

The dashboard's **Saved recordings** panel lists private recording folders with paging. **Refresh recordings** reloads the index. A missing final manifest is incomplete, an invalid manifest is unavailable, and an active run is not downloadable as finalized. Finalized rows are marked **unchecked** until a download verifies file hashes and repeats parsing from the wire bytes. Corruption is refused, never repaired silently.

A sensor-mode row offers **Office CSV package**. It contains `source.capture.csv` in the existing V1 capture schema, the complete raw capture ZIP and a checksum/provenance report. Rejected/partial/diagnostic records remain in the raw ZIP and are counted. Current stays in **mA** in this V1 CSV; the existing offline adapter converts once to A. Acceleration stays in m/s²; do not merge it into the historical synthetic mm/s research ledger or claim vibration spectra from 1 Hz summaries.

Office export refuses ESP32-only/demo recordings and recordings without accepted structured sensor records. It still marks sensor records **serial-unverified**, `training_approved=false`, calibration/production false and physical acceptance pending. Transfer privately rather than committing the data to GitHub. Follow [the existing offline capture handoff](phase-01-hardware/docs/OFFLINE_CAPTURE_HANDOFF.md) to add actual board/firmware/configuration references, review quarantined data and curate an office dataset. Export is not an evaluated predictive model or permission to create real maintenance actions.

## Optional reconnect for ordinary monitoring

The UI checkbox **Retry ordinary USB monitoring** is off by default. It retries only open/read transport errors on the exact selected port, with exponential delay capped at 30 seconds. Current values clear immediately during an error; a successful open without usable frames does not become fresh data. Each retry gets a new unverified attempt ID. No port is auto-discovered, no device authentication is inferred, and manual Disconnect/Stop cancels retries.

Storage errors, missing dependencies, invalid frames and stale-but-open streams do not trigger automatic reopen loops. Timed recordings never retry or splice two acquisitions. The option is not persisted into login startup or a later server restart. CLI monitoring can opt in using `--connect --reconnect` with a confirmed USB mode/port. Opening a port can reset the ESP32; retain that behavior in the test record.

## Optional Mac startup at login

This uses a per-user [Apple launchd agent](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html). It does not run as root. Installation is optional and must be performed on the actual Mac after normal setup and communication checks. No service is installed on the owner's Mac by preparing this repository.

Mac Terminal only, after stopping an existing server:

```bash
bash home_service.command plan
bash home_service.command install
bash home_service.command status
```

The plan shows exact paths before installation. The installed job starts **only the local dashboard**, without `--connect` or `--reconnect`; no USB port is opened, no demo data generated and no model training started at login. Use the page to select a reader yourself. A crash may restart the dashboard after a throttle interval, but acquisition does not resume automatically. RunAtLoad applies while your GUI user is logged in; this is not an always-on hosted portal or a closed-lid uptime guarantee.

```bash
bash home_service.command stop
bash home_service.command start
bash home_service.command remove
```

Stop unloads the job for this login session. Start reloads the owned configuration. Remove disables future login startup by removing only the exact owned plist after unloading; private readings and source remain. A modified/existing unexpected plist is preserved for review. The server handles SIGTERM by closing its reader and finalizing a recording when possible. Actual forced power loss can still leave incomplete files; physical recovery testing remains pending.

Logs are private under `.local/home/service/`. The label is distinct per checkout. Remove the service before moving a checkout. Default service port/data are 8878 and `.local/home`; custom data folders are not silently switched. Do not enable two launchers for the same data directory. Windows office startup remains manual; the home Mac is the intended login-service host.
