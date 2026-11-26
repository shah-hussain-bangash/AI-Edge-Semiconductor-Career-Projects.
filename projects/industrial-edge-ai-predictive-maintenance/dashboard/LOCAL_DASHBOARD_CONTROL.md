# Start, check and stop the full local dashboard

`local_dashboard.py` gives the full dashboard its own local process controls. It can request a graceful shutdown, allowing existing HTTP requests to finish and database transactions to commit. It never kills a PID, stops unrelated Python processes, flashes hardware or configures hosting. The lightweight home application keeps its existing separate controls.

Install the [pinned full-dashboard dependencies](LOCAL_OPERATIONAL_PLATFORM.md#full-dashboard-setup-and-update) first, using Python 3.12–3.14. From `dashboard`, use that environment's Python for every command below. Examples show Windows PowerShell; on macOS replace `.\.venv-operations\Scripts\python.exe` with `./.venv-operations/bin/python`.

## New managed instance

For a new default installation, configure the private bootstrap email/password as described in [README](README.md). Existing accounts are retained; changing bootstrap values does not reset an existing password. The default database is `dashboard/.local/dashboard.sqlite3`, or the existing `EDGEOPS_DASHBOARD_DB` environment value. Keep any configured artifact, telemetry and delivery-spool environment paths identical across restarts.

```powershell
.\.venv-operations\Scripts\python.exe local_dashboard.py start --background --port 8877
.\.venv-operations\Scripts\python.exe local_dashboard.py status
Start-Process 'http://127.0.0.1:8877/app?view=registered'
.\.venv-operations\Scripts\python.exe local_dashboard.py stop
```

On macOS, open the URL with `open 'http://127.0.0.1:8877/app?view=registered'`. Omit `--background` to run visibly in the current terminal and stop with Ctrl+C. Background start waits for application startup and reports `ready`; this means local server readiness, not hardware or production acceptance. Logs remain in the private runtime directory.

## Existing custom data

Select the same explicit database when starting, checking and stopping:

```text
python local_dashboard.py start --background --database <existing-private-database> --port 8890
python local_dashboard.py status --database <existing-private-database>
python local_dashboard.py stop --database <existing-private-database>
```

These are command templates; replace `python` with the environment's executable and each angle-bracket placeholder with the actual path, quoting paths containing spaces. Optional `--runtime-dir <private-directory>` must also match on all commands. By default the runtime is `<database-parent>/<database-stem>-runtime`. The manager does not guess or move data stores, copy credentials or create extra accounts.

An instance started directly with `uvicorn` has no managed control channel and cannot be adopted or stopped by this tool. Preserve its settings, make a verified backup and stop it in its original terminal before switching the same database to the manager. Do not run managed and unmanaged servers against the same database. An occupied application port is rejected **before application initialization**, so a failed bind does not migrate or bootstrap a database. A database-side lock prevents two managed instances from owning the same resolved database, even on different ports or runtime directories.

## Update safely

1. Create and verify a [backup](RECOVERY.md), including explicitly configured additional stores.
2. Request `stop` with the same database/runtime selection. Wait for `stopped` before updating source or dependencies. If shutdown is still draining at the timeout, it remains a graceful request; the manager does not force termination. Check status again and resolve the outstanding request or worker activity.
3. Inspect `git status --short`. Preserve local changes before a fast-forward-only update. The manager performs no Git reset, stash or dependency installation.
4. Update the pinned dependencies in the dedicated environment, then start with the same database, private environment and port. Check readiness before opening the dashboard.

`--timeout` accepts 1–60 seconds and defaults to 30. If startup times out, inspect status/private logs before retrying; an unconfirmed process is never automatically killed. If the log reports a port conflict, identify the existing listener instead of killing Python processes. A stale record is not authority to terminate its recorded PID.

## Private controls and scope

The manager stores a random control secret in an owner-only local instance file. Do not share it, include it in diagnostics or commit it. It is not the dashboard password, a device token or an API credential. POSIX directory/file permissions are checked; Windows ACLs must be restricted locally and are not independently inspected. Protect the runtime directory like the database.

The separate control listener binds only to IPv4 loopback on an automatically selected port, without a hostname lookup. It requires the secret and exact instance identity, rejects browser-origin requests and nonempty bodies, bounds concurrent connections, and uses short connection timeouts. Control requests bypass configured web proxies. Normal CLI output omits the secret. No shutdown endpoint is added to the public dashboard API.

Process management is local only: no automatic boot service, restart supervisor, online portal, multi-host management or production availability guarantee is installed. Automated tests use disposable servers and cover startup/status, duplicate ownership, occupied ports, unauthorized controls, stale PID records and a graceful stop while an HTTP request commits a database write.
