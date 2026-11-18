# EDGEOPS — Industrial Intelligence Platform

**Status: production-oriented development foundation, NOT production-ready.** This directory now includes a responsive sign-in page, authenticated Python API, industrial dashboard UI, a proposed 30-slot hardware catalog, local audit records, and a safe optional Git sync workflow.

**Previous verification:** The enterprise-architecture laboratory phases EA-23 through EA-31 have 132 tests reported passed on the user's Windows computer. Dashboard backend tests and visual browser tests are **new and have not yet been executed in that environment**.

## High-level system

- Frontend: HTML5, responsive custom CSS, vanilla JavaScript, SVG telemetry charts.
- Backend: FastAPI with PBKDF2-HMAC-SHA256 credential hashing, an eight-hour server-side opaque session stored by SHA-256 hash, same-site cookies, per-session double-submit CSRF validation and basic security headers.
- Development database: SQLite stores users, session metadata and local audit records. Existing EA-30 SQLite telemetry data is **not automatically linked**.
- Hardware planning: read-only inventory with 30 catalog slots; 14 known names, 16 unconfirmed. No real physical device is marked connected or purchased.
- Application controls: no equipment actuator commands, no live production telemetry, no model training/inference, no critical control path.
- Authentication: a single explicit local bootstrap admin, never a default password; this starter is not enterprise SSO/OIDC.

## Screens

1. Attractive responsive **Sign In** screen: branded industrial artwork, account authentication and visible local-development scope.
2. **Overview**: 12 synthetic demonstration asset cards, performance counters, health distribution and alerts.
3. **Live telemetry**: clearly labeled synthetic vibration, temperature, current and voltage trends.
4. **Assets**: sample asset table and synthetic health status.
5. **Alerts**: browser-local demonstration alert acknowledgment. A separate authenticated backend endpoint can audit *demo* acknowledgments; it does not change real alarm state.
6. **AI insights**: illustrative human-readable cards, explicitly NOT trained AI model output.
7. **Hardware inventory**: all 30 planning slots, with 14 named items and 16 unconfirmed; secure read-only same-origin API.
8. **Security & audit**: status/gates summary; protected API audit endpoint available to admin/auditor, not yet a complete audit UI.
9. **Account session**: authenticated session details, sign-out with CSRF protection.

## Run from Cursor / VS Code on Windows

Open the existing Git checkout in Cursor or VS Code, then run **PowerShell** in the integrated terminal:

~~~powershell
cd "C:\Users\Gaming PC i9 3080\edgeops-workspace\projects\industrial-edge-ai-predictive-maintenance\dashboard"
git pull --ff-only origin main
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

Create a strong local development password (do **not** save it in source code, screenshots or Git). The following prompt reads the password securely without displaying it in your terminal:

~~~powershell
$env:EDGEOPS_ADMIN_EMAIL = "admin@example.invalid"
$secure = Read-Host "New EDGEOPS local admin password (14+ chars)" -AsSecureString
$handle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $env:EDGEOPS_ADMIN_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($handle)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($handle)
  Remove-Variable secure
}
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8765
~~~

**Open:** http://127.0.0.1:8765/signin

The first run creates the local admin and development database in the ignored `.local/` directory. Restarting the same database will not change the original admin password merely by changing the environment variables. Setting `EDGEOPS_HTTPS_ONLY=1` requires HTTPS (typically at an authenticated reverse proxy) or cookies will not work over HTTP. This setup is strictly localhost-only; do not bind 0.0.0.0 or expose the development server to the internet.

**Verification from another terminal:**

~~~powershell
cd "C:\Users\Gaming PC i9 3080\edgeops-workspace\projects\industrial-edge-ai-predictive-maintenance\dashboard"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_server.py" -v
~~~

This suite has **12 authored API tests**: redirects, login rejection, session, catalog, no static server-source access, CSRF, logout, audit, safe state and synthetic-only acknowledgment.

**Static checks:** The Phase 1 static structure test has been updated for the authenticated server asset routes. Both source structure and API tests are configured in GitHub Actions but remain unverified until their actual run results are inspected.

## GitHub + Cursor/VS Code automatic synchronization

**Git principle:** Editing and saving a file locally does *not* automatically update GitHub. Saving, staging, committing and pushing are separate operations. Automatically pushing every keystroke to `main` would risk publishing untested code and secrets.

Recommended human-review workflow:

~~~powershell
git status
git diff -- projects/industrial-edge-ai-predictive-maintenance/dashboard
git add projects/industrial-edge-ai-predictive-maintenance/dashboard
git commit -m "feat(edgeops): improve dashboard"
git push origin main
~~~

These commands are written for running from the **repository root**. For simple day-to-day work from this dashboard folder use `git add index.html styles.css app.js signin.html signin.css signin.js server.py` with only the files you actually reviewed; do not stage local `.env` or `.local/` data.

**Optional continuous auto-commit and push:** Only if you explicitly enable it, `sync-dashboard.ps1` can watch for edits every 20 seconds, commit an allowlist of dashboard source files and push to a **separate `dashboard-live-edit` branch** (never directly to `main`). Before starting:

~~~powershell
git fetch origin
git switch -c dashboard-live-edit
git push -u origin dashboard-live-edit
.\sync-dashboard.ps1 -Watch -IntervalSeconds 20
~~~

This is a convenience workflow, not CI. Stop with Ctrl+C. It refuses unrelated staged files and aborts when push fails. **Review the diff and run tests before merging that branch into main.** Do not save tokens or secrets in source files, since even a temporary commit can expose them remotely. The monitor uses the existing Git credentials configured in Cursor or VS Code; do not paste GitHub personal access tokens into scripts.

## What remains before a truthful production claim

| Area | Current implementation | Required before production |
|---|---|---|
| Sign-in | Local bootstrap admin and session cookies | Enterprise identity (OIDC/SSO), MFA, provisioning, recovery and account policies |
| Authorization | Fixed local roles for read-only/audit endpoints | Tenant/site/asset authorization and policy integration |
| UI | Responsive code committed | Actual multi-browser visual QA, accessibility audit and UX acceptance |
| Data | Synthetic fixtures and isolated SQLite auth/audit | PostgreSQL/TimescaleDB, migrations, retention, recovery, integrations |
| MQTT | EA-31 localhost mTLS lab separate from dashboard | Durable retries/queue, proven delivery semantics, hardening, certificate lifecycle |
| Analytics | Synthetic static charts | Live read-only API with provenance, pagination and error states |
| Predictive AI | Illustrative cards only | Trained/evaluated models, drift monitoring, calibrated explanations and human review |
| Device operations | Proposed 30-slot catalog | Bill of materials approval, physical provisioning, certificates and calibration |
| Security | Local CSRF, session and headers starter | Independent pen test, OIDC, distributed rate limiting, secure deployment, secrets manager, SIEM |
| Safety | No actuator UI, G4b BLOCKING | Independent electrical safety/guard/E-stop approval before physical testing |
| Reliability | Some EA-30/31 lab evidence | EA-32 spool/retry/dead-letter design and failure-injection proof |
| Governance | Architecture and test documents | Change control, runbooks, disaster recovery tests, threat model sign-off |

**Do not deploy this local starter as an internet-facing production identity service or connect real industrial equipment.**

## Source

- `signin.html`, `signin.css`, `signin.js`: login experience.
- `index.html`, `styles.css`, `app.js`: existing multi-page dashboard.
- `dashboard-auth.js`: authenticated inventory loading and logout.
- `server.py`: local API, session storage, auth and audit.
- `tests/test_server.py`: authored security/API tests; local execution pending.
- `sync-dashboard.ps1`: opt-in Git sync for dedicated development branch.


## Approved visual redesign — sign-in and executive command center

**Design status:** Source implemented on `dashboard-live-edit`, awaiting browser screenshot/visual QA and an updated local test run. Not yet merged to `main` and not a production deployment.

The approved dark command-center direction has been rebuilt with brighter text, electric cyan outlines, industrial midnight-blue surfaces and amber status/actions. Industrial machinery imagery is shipped as two original local SVG assets, `industrial-motor.svg` and `industrial-plant.svg`, both served through an explicit static allowlist. The source illustrations are stylized vector art, not photorealistic images or actual photographs of purchased hardware.

### Sign-in layout

- Full-width industrial illustration with overlaid synthetic sensor readouts and a distinct access card.
- Local account login, show/hide password, optional remembered **email only** (not password), and explicit feedback for unconfigured SSO, recovery and public demo access.
- Mobile responsive layout with keyboard focus treatments.
- Corporate safety notice, demo provenance and readable accessible contrast.

### Executive dashboard

- Compact eleven-section navigation: Overview, Assets, Telemetry, AI Copilot, Inventory, Alerts, Maintenance, Security, Governance, Reports and Settings.
- Five executive KPI fixtures (health, 30 planned hardware slots, alerts, model readiness and illustrative uptime).
- Machine + sensor hero display, selectable sensor signal chart, alerts, activity, demonstration work queue and review-only quick actions.
- Synthetic fleet distribution; equipment criticality; maintenance queue; pictorial hardware preview; governance/safety panel.
- Functional read-only inventory API, alert browsing/ephemeral acknowledge, snapshot JSON export, session sign-out, section navigation and client-only asset/alert search.
- No deceptive "30 connected devices", "deployed model" or production-risk statistics. The 30 component positions are **planning slots**, and only 14 component names are confirmed from the user's earlier requested inventory.

### Preview on your Windows machine

Because you have an opt-in auto-sync watcher on the development branch, press **Ctrl+C in the sync terminal before pulling** to avoid local/remote divergence during updates.

```powershell
cd "C:\Users\Gaming PC i9 3080\edgeops-workspace\projects\industrial-edge-ai-predictive-maintenance\dashboard"
git status
git pull --ff-only origin dashboard-live-edit
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_structure.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_server.py" -v
```

Keep the preexisting Uvicorn development server running on localhost port 8877. Open:

- http://127.0.0.1:8877/signin
- http://127.0.0.1:8877/app (after authenticated sign-in)

With `--reload`, the server may restart due to Python source changes. **Use Ctrl+F5 to hard-refresh** CSS, JS and SVG assets as needed. In a separate terminal restart the opt-in watcher with `.\sync-dashboard.ps1 -Watch -IntervalSeconds 20` once the branch has been pulled and tested.

### Verification scope

The dashboard is not pixel-identical to generated mockup images: the approved composition, contrast, features and colors have been translated into maintainable HTML/CSS/JS, with local vector machinery artwork rather than the mockup's photorealistic pixels. Source changes are committed to the GitHub branch, but no actual browser screenshot or new test output has been verified yet. Do not count new checks as passed until the test log and UI are inspected.


## Approved reference photographs (November 18)

The dashboard and login now reference two JPG images extracted/cropped from the user-approved EDGEOPS mockup:
- `edgeops-motor-photo.jpg`: photographed industrial motor with existing cyan sensor overlays.
- `edgeops-factory-backdrop.jpg`: wider factory environment used behind the sign-in showcase.

**The binary JPGs must be copied into this directory locally**, then added and pushed from the user's checkout. They are not bundled in this branch by GitHub's text-file connector. Until installed, an error handler falls back to the original vector SVG illustrations. The backend serves both JPGs only through its static allowlist. This is intentional and avoids a broken image or a silent claim that the image was uploaded.

Copy both files into `dashboard/` and in PowerShell:
```powershell
git add -- edgeops-motor-photo.jpg edgeops-factory-backdrop.jpg
git commit -m "assets(edgeops): add approved industrial photographic artwork"
git push origin dashboard-live-edit
```

Run `python -m unittest discover -s tests -p "test_server.py" -v`, reload the page and check the browser's Network panel for 200 responses on both image URLs. Do not publish the entire reference screenshot as a user background with the simulated login form duplicated on top.
