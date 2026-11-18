# EDGEOPS Industrial Intelligence Console — Dashboard Phase 1

**Status:** UI foundation authored and committed to GitHub; browser execution, accessibility review, and visual QA **NOT YET VERIFIED ON THE USER'S COMPUTER**.

**Scope:** Read-only and browser-local visual prototype. No backend API call, no MQTT subscription, no saved login, no physical sensor, no real trained AI model, and no motor/actuator controls. Every chart, health score, alert and telemetry display is **synthetic**.

## Purpose

Create a visually strong, portfolio-ready industrial operations interface aligned with the EDGEOPS EA-01 through EA-31 architecture and previously committed verification evidence. Dashboard Phase 1 intentionally does not claim the production system exists.

## Files

| File | Contents |
|---|---|
| [index.html](index.html) | Semantic HTML5 application shell, accessible navigation, screens, alert view, SVG chart placeholders |
| [styles.css](styles.css) | Responsive dark industrial visual system, cards, tables, mobile sidebar, status treatments |
| [app.js](app.js) | Browser-local demo dataset, safe text rendering, chart rendering, navigation, session-only alert acknowledgment, JSON export |

## Screens

1. **Overview:** asset count, simulated fleet health, alert summary, synthetic ingestion rate, telemetry trend and recent alarms.
2. **Live telemetry:** expressly marked simulated sensor readings (vibration, motor-case temperature, current and voltage) with selectable charts.
3. **Assets & devices:** a 12-item fixture asset registry, health bars and severity classification.
4. **Alerts:** synthetic incidents; acknowledge button only mutates in-memory browser UI, not backend.
5. **AI insights:** illustrative narrative cards labeled *not model output*.
6. **Security & audit:** previously reported EA test evidence count and unapproved security/physical gates.

The dashboard makes **zero network requests**, avoiding accidental calls to existing NAWA, Finagent, EDGEOPS test, or other running services.

## Run locally — Windows PowerShell

Open your existing checkout and pull changes:

~~~powershell
cd "C:\Users\Gaming PC i9 3080\edgeops-workspace\projects\industrial-edge-ai-predictive-maintenance\enterprise-architecture"
git pull --ff-only origin main
Start-Process "..\dashboard\index.html"
~~~

This opens a static page in the default browser. It requires **no Docker, Node.js, npm, Python packages or server**.

Optional repository structural verification:

~~~powershell
python ..\dashboard\tests\test_structure.py
~~~

That script only checks source-file structure; it does not prove responsive browser rendering or API compatibility. Review in Chrome/Edge at desktop and mobile widths and verify menu navigation, chart selector, local alert acknowledgment, export, keyboard focus and simulated-data warnings.

## Visual and UX intent

- Dark navy industrial surfaces, mint-green telemetry accents, muted blue analytics, amber watch conditions, red critical alerts.
- Responsive desktop/compact navigation; a mobile menu with keyboard-accessible controls and labeled sections.
- Monitoring **only**: no remotely operable start/stop button or other unsafe actuation.
- Visible simulated-data disclosure at the top and in export contents.
- Client-only export of demo metrics, asset list and telemetry fixture as a JSON file. Export is not evidence of real sensor events or server-side logging.

## Known limitations and future phases

- No real API integration, authentication, role-based application session, persistent alert state or timestamped live stream.
- The labels *Live telemetry* and *AI insights* are navigation taxonomy only: both are prominent demo placeholders.
- User-facing charts show fixed samples, not sensor readings or inferred failure predictions.
- UI security panel summarizes previous code/test evidence; it is **not** a compliance dashboard or security accreditation.
- **Dashboard Phase 2 proposal:** integrate read-only API endpoints for device and aggregate telemetry, use event provenance badges, schema validation, loading/error/offline states and accessible chart descriptions; do not expose any motor controls.
- **Dashboard Phase 3 proposal:** real alert acknowledgment service with authorization, audit logging and persistent state, plus supervised model-evaluation readout after valid model evidence exists.
- **EA-32 reliability project** can proceed separately from dashboard UI development.

## Safety and truthfulness

- G4a independent cybersecurity approval: **OPEN**.
- G4b physical/electrical motor safety: **BLOCKING**.
- All example sensor values and alerts are synthetic.
- Do not call the dashboard production-ready or connect it to live industrial equipment.
