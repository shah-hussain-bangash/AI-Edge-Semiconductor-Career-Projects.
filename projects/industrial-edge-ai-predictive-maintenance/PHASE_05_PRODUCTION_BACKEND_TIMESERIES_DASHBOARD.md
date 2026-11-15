# Phase 05 — Production Backend, Time-Series Database & Real-Time Operations Dashboard

**Project:** Industrial Edge AI Predictive Maintenance & Autonomous Operations Platform  
**Status:** Practical implementation blueprint; not a claim of implemented or tested production software.  
**Prerequisites:** Phase 01 sensors, Phase 02 MQTT telemetry, Phase 03 edge inference, Phase 04 incident and approval design.  
**Goal:** Build and validate an integrated, secure FastAPI + PostgreSQL/TimescaleDB + Next.js operations platform for equipment telemetry, alerts, maintenance approvals and auditability.

## 1. Problem statement and deliverable

Physical telemetry and edge anomaly events need durable, queryable storage and a responsive, permission-controlled operations portal. This phase builds the **application and data backbone**: authenticated ingestion, robust time-series persistence, live equipment status, incident workflows, dashboards, monitoring, backups and reproducible deployments.

**Practical end-to-end demo:** ESP32 sensors -> MQTT -> Pi edge inference -> backend ingestion -> time-series database -> live dashboard -> incident review -> human-approved work order -> immutable-intent audit trail.

**Scope note:** Production-oriented engineering practices do not make this a certified industrial safety system. The platform never directly controls or shuts down industrial equipment.

## 2. Hardware and development environment

| Hardware | Qty | Function |
|---|---:|---|
| ESP32 + ADXL345 + DS18B20 + INA219 | 1 set | Real vibration, temperature and DC electrical telemetry |
| Guarded 12V motor, rated driver/supply/fuse/disconnect | 1 set | Safe physical test bench |
| Raspberry Pi 5 with cooling/storage | 1 | MQTT edge gateway and ONNX inference |
| Laptop or office workstation (16GB RAM recommended) | 1 | Backend, frontend, containers, testing |
| Router / LAN | 1 | Isolated device-to-edge network |
| Optional Linux VM | 1 | Staging deployment and recovery testing |
| Optional UPS | 1 | Resilience experiments |

For the first version, run the API, database and dashboard on a laptop; run edge telemetry on the Pi. Separate hosts only after validating local deployment.

## 3. Technology stack

| Layer | Technology | Practical responsibility |
|---|---|---|
| Edge transport | Mosquitto, MQTT QoS 1 | Device telemetry and edge events |
| Backend | Python 3.11+, FastAPI, Pydantic v2 | API contracts, validation, business logic |
| Persistence | PostgreSQL 16+ | Assets, incidents, users, approvals, audit events |
| Time series | TimescaleDB extension where supported | Efficient telemetry time-series queries and retention |
| ORM/migrations | SQLAlchemy 2, Alembic | Schema evolution and transactions |
| Queue/outbox | PostgreSQL transactional outbox, optional Redis worker | Reliable asynchronous notifications |
| Frontend | Next.js, React, TypeScript | Asset and maintenance operations portal |
| Data visualization | Recharts or ECharts | Sensor trends, anomalies and event timelines |
| Authentication | OIDC provider, server-side sessions / validated JWT | Identity and role enforcement |
| Realtime | Server-Sent Events (SSE) initially | Push live status and alerts to browsers |
| Observability | Prometheus, Grafana, OpenTelemetry | Metrics, logs and traces |
| Deployment | Docker Compose, reverse proxy, TLS | Repeatable local/staging deployment |
| CI/CD | GitHub Actions, pytest, Playwright | Quality gates and release validation |
| Security | RBAC, least-privilege DB, secrets manager/env injection | Protect sensitive operations |

Use a **supported and compatible** PostgreSQL/TimescaleDB version pair; check extension compatibility before pinning a Docker image. If TimescaleDB cannot be installed, start with partitioned PostgreSQL tables and document the tradeoff.

## 4. Reference architecture

```text
[ESP32 sensors] -> [MQTT broker on Pi] -> [ONNX edge inference]
                                             |
                                 telemetry + edge-events
                                             |
                                 [Authenticated ingest]
                                             |
                        [FastAPI service + validation]
                          |             |            |
                     [PostgreSQL]  [Outbox worker] [SSE]
                       /    \          |             |
               [Telemetry] [Incidents] [Notifications] |
                      |       |                       |
                      +-------+------> [Next.js Dashboard]
                                      /      |       \
                                 Assets  Alerts  Work orders
                                            |
                                    [Approver RBAC]
                                            |
                                     [Audit log]
```

**Trust boundaries:** device identity is separate from human identity; edge-origin data is untrusted until validated; only the backend can authorize work-order state changes; frontend checks are usability features, not security controls.

## 5. Suggested monorepo layout

```text
industrial-edge-ai-platform/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/v1/
│   │   │   ├── auth/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   ├── services/
│   │   │   ├── repositories/
│   │   │   └── workers/
│   │   ├── alembic/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── web/
│       ├── app/
│       ├── components/
│       ├── lib/
│       ├── tests/
│       └── package.json
├── edge/
│   ├── mqtt/
│   └── ingestion/
├── infra/
│   ├── compose.yaml
│   ├── prometheus/
│   └── reverse-proxy/
├── docs/
│   ├── architecture.md
│   ├── api-contracts.md
│   ├── data-retention.md
│   ├── threat-model.md
│   ├── runbook.md
│   └── benchmark-report.md
├── .github/workflows/
└── README.md
```

## 6. Step-by-step practical implementation

### Step 1 — Define contracts and boundaries
1. Freeze Phase 02 telemetry schema and Phase 03 edge-event schema as versioned API contracts.
2. Define assets, devices, sensor channels, operating state, model versions, incidents, recommendations, work orders and approvals.
3. Record units, source timestamps, gateway receive timestamps, quality flags and idempotency keys.
4. Define retention, access controls and expected sample rates before creating tables.
5. Add OpenAPI contract tests and sample payloads with **synthetic** values.

### Step 2 — Create the FastAPI service
1. Initialize Python environment and pin dependency versions.
2. Build `GET /health/live`, `GET /health/ready` and `GET /metrics` (protect metrics endpoint).
3. Use Pydantic schemas with strict field validation, bounded sizes and allowed schema versions.
4. Separate route handlers, business services, repositories and database transactions.
5. Add structured logs with request IDs and redaction.
6. Add database migrations and test database fixture.
7. Write unit and integration tests before exposing any public endpoint.

Illustrative API endpoints:

```text
POST /api/v1/ingest/telemetry       (device/service identity only)
POST /api/v1/ingest/edge-events     (device/service identity only)
GET  /api/v1/assets                (viewer+)
GET  /api/v1/assets/{id}/telemetry (viewer+, bounded time range)
GET  /api/v1/assets/{id}/health    (viewer+)
GET  /api/v1/incidents             (viewer+)
GET  /api/v1/incidents/{id}        (viewer+)
POST /api/v1/incidents/{id}/ack    (operator+)
POST /api/v1/incidents/{id}/recommendations (technician+)
POST /api/v1/incidents/{id}/approvals       (approver only)
GET  /api/v1/work-orders           (viewer+)
GET  /api/v1/audit                 (auditor/admin only)
GET  /api/v1/stream/events         (authenticated SSE)
```

Use cursor pagination for long lists, bounded date ranges for time-series reads, rate limits for ingestion and explicit authorization on every asset.

### Step 3 — PostgreSQL / TimescaleDB schema
Use Alembic migrations; do not depend on manual production SQL edits. Core relational tables: `assets`, `devices`, `model_versions`, `edge_events`, `incidents`, `incident_history`, `recommendations`, `approvals`, `work_orders`, `audit_log`, `outbox`.

Illustrative telemetry DDL (verify TimescaleDB extension/version syntax in target environment):

```sql
CREATE TABLE telemetry (
  received_at TIMESTAMPTZ NOT NULL,
  observed_at TIMESTAMPTZ,
  device_id TEXT NOT NULL,
  boot_id TEXT NOT NULL,
  seq BIGINT NOT NULL,
  asset_id TEXT NOT NULL,
  vibration_rms_mps2 DOUBLE PRECISION,
  temperature_c DOUBLE PRECISION,
  bus_voltage_v DOUBLE PRECISION,
  current_ma DOUBLE PRECISION,
  sensor_valid BOOLEAN NOT NULL,
  payload JSONB NOT NULL,
  PRIMARY KEY (received_at, device_id, boot_id, seq)
);
CREATE INDEX idx_telemetry_asset_time
  ON telemetry (asset_id, received_at DESC);
```

**Important idempotency caveat:** A composite primary key containing `received_at` does **not** deduplicate retries if the same event is received at a different time. Enforce `(device_id, boot_id, seq)` uniqueness via a separate ingestion-key table or a deterministic upstream event ID, and transactionally insert the telemetry row only for a new key. TimescaleDB unique constraints generally must include the partitioning time column; design idempotency outside the hypertable when needed.

If using TimescaleDB, enable extension and convert to hypertable only after compatibility verification; configure compression/columnstore and retention according to the installed version and measured needs. Use continuous aggregates only for suitable dashboards, and keep raw data for the defined retention period.

### Step 4 — Implement reliable MQTT ingestion
1. Run an authenticated MQTT subscriber as a supervised service, not a fragile API startup background thread.
2. Validate topic-to-device identity and payload schema.
3. Deduplicate with stable ingestion keys before writing time-series data.
4. Use bounded batches, backpressure, retry with jitter and dead-letter handling for poison messages.
5. Distinguish telemetry from model-derived edge events.
6. Persist events and incident-outbox messages in one transaction where required.
7. Track broker reconnects, ingestion lag, duplicates, invalid payloads and storage failures.
8. Replay recorded data through the same ingestion path in test mode.

### Step 5 — Build query services and health summaries
1. Add asset list and latest-seen status.
2. Create time-bounded raw telemetry queries with downsampling for long ranges.
3. Calculate sensor-quality percentages, offline/stale states and event counts.
4. Expose model version, feature schema and anomaly threshold with each alert.
5. Never turn missing sensor data into a zero/healthy value.
6. Add indexes and use `EXPLAIN ANALYZE` to optimize real queries.
7. Test pagination, timezone handling and cross-asset authorization.

### Step 6 — Integrate Phase 04 incident workflows
1. Consume validated edge events through deterministic correlation rules.
2. Apply hysteresis and deduplication to avoid alert storms.
3. Enforce explicit incident state-machine transitions.
4. Persist append-only incident history.
5. Generate recommendation **drafts** with SOP citations and uncertainty.
6. Require approver role, reason and audit record before creating work orders.
7. Ensure approval and work-order creation are idempotent and transactional.
8. Prohibit direct remote motor commands in the application.

### Step 7 — Implement real-time updates
Use **SSE** for one-way dashboard events initially:
- Authenticated browser connection to `/api/v1/stream/events`.
- Push asset-status, incident-created and work-order-updated notifications.
- Reconnect with event IDs or perform an authoritative refetch after reconnection.
- Do not assume SSE delivery is durable; PostgreSQL remains the source of truth.
- Use bounded per-client queues and heartbeat events.
- Test reverse proxy timeouts and multiple concurrent viewers.

WebSockets are optional only if genuinely needed for bidirectional collaboration.

### Step 8 — Build Next.js dashboard
Implement these screens:
1. **Fleet overview:** total assets, healthy, anomaly, sensor fault, offline.
2. **Asset details:** sensor trends, quality flags, model version, anomaly score.
3. **Incident center:** severity, duration, evidence, acknowledgement and assignment.
4. **Maintenance review:** SOP-backed recommendation and approval controls.
5. **Work orders:** requested, approved, in progress, verified, closed.
6. **Device diagnostics:** firmware, last-seen, queue depth and connectivity.
7. **Audit viewer:** actor, action, timestamp and reason.
8. **Admin settings:** authorized asset/device mapping and alert policies.

UI requirements: responsive, accessible labels, loading/empty/error states, UTC-aware display, downsampled charts and explicit stale-data indicators. Never imply live equipment status when data is old.

### Step 9 — Authentication and authorization
1. Integrate an OIDC identity provider; validate tokens server-side (issuer, audience, expiry and signature).
2. Roles: viewer, operator, technician, approver, auditor, administrator.
3. Add asset-level authorization where needed; do not rely on UI-hidden buttons.
4. Separate device service credentials from human login.
5. Protect state-changing endpoints against CSRF if cookie-based sessions are used.
6. Store secrets outside Git; rotate and revoke credentials.
7. Test privilege escalation, unauthorized approvals, cross-asset access and token expiry.

### Step 10 — Docker and deployment
1. Define `compose.yaml` for API, web, PostgreSQL, optional TimescaleDB, worker and observability.
2. Add health checks, resource limits, persistent volumes and restart policies.
3. Use a reverse proxy with TLS; expose only intended web/API ports.
4. Keep PostgreSQL and broker ports on private networks.
5. Run migrations as an explicit deployment step, with rollback plan.
6. Pin container images and scan dependencies.
7. Validate backups and restore before calling deployment production-ready.

### Step 11 — Observability and incident response
Track:
- MQTT messages/sec, invalid payloads, duplicate rate and ingestion lag.
- API p50/p95 latency, error rate and authorization failures.
- Database storage, slow queries, connections and retention job health.
- SSE connected clients, reconnects and queue overflows.
- Asset last-seen, missing telemetry, edge model version and alert counts.
- Approval workflow latency and outbox backlog.

Use structured logs and distributed trace IDs. Alert on stale telemetry and failed backups, not only HTTP errors.

### Step 12 — CI/CD and release quality
1. Run Python lint/type checks and pytest.
2. Run frontend lint, TypeScript checks and unit tests.
3. Execute database migration and API integration tests in CI.
4. Run Playwright E2E tests for alert review and approval flow.
5. Scan dependencies and check for committed secrets.
6. Build versioned containers.
7. Deploy to staging, run smoke tests, then promote manually.
8. Document rollback and restore procedures.

## 7. Performance and reliability test matrix

| Scenario | Expected evidence |
|---|---|
| Continuous telemetry | Measured messages/sec, storage growth and data completeness |
| MQTT duplicates | One persisted logical event per stable idempotency key |
| MQTT/broker outage | Reconnect, bounded buffering and documented loss policy |
| DB restart | No corrupted incident state; recovery time recorded |
| Large chart time range | Bounded query time and downsampled output |
| 20 simulated viewers | SSE connections and API performance measured |
| Unauthorized user | Access denied at backend for restricted asset/actions |
| Approval retry | Exactly one approved work order created |
| Model event with invalid sensor quality | Sensor fault, not false healthy state |
| Backup/restore | Restored data and migrations verified |
| Deployment rollback | Documented, tested procedure |
| 24-hour soak | Memory, CPU, storage, errors and dropped events recorded |

These are **test scenarios**, not claims that any performance threshold has already been met. Set numeric service-level targets only after baseline measurements.

## 8. Data retention, privacy and governance

- Define raw telemetry retention and longer-lived aggregates separately.
- Keep incident, work-order and audit retention according to organizational policy.
- Restrict access to device identity, user identity and operational data.
- Record consent/authorization for any real industrial deployment.
- Preserve provenance of AI-generated recommendations and their cited SOP versions.
- Never use an LLM to authorize maintenance actions.
- Document failure modes, safety boundaries and escalation to human operators.

## 9. GitHub deliverables and definition of done

- [ ] API source code with OpenAPI contract and validation tests
- [ ] Versioned Alembic migrations and reproducible DB setup
- [ ] Idempotent MQTT ingestion with replay tests
- [ ] Time-series retention and query benchmark report
- [ ] Authenticated SSE updates with reconnect behavior
- [ ] Next.js fleet, asset, incident and work-order dashboards
- [ ] RBAC and human approval E2E tests
- [ ] Docker Compose staging environment
- [ ] Metrics, logs, traces and operational runbook
- [ ] Backup/restore and rollback evidence
- [ ] Security/threat-model documentation
- [ ] Video: physical sensor -> edge event -> dashboard -> approved work order
- [ ] Clear distinction between synthetic and real sensor test evidence

**Phase 05 is complete only when** the backend, database, dashboard and workflow can be deployed reproducibly, handle real sensor-origin events, enforce permissions, recover from tested failures and demonstrate audited human-approved maintenance actions.

## 10. Next phase

**Phase 06 — Agentic AI Maintenance Assistant, RAG Knowledge Base & Controlled Automation.** Build a versioned maintenance-document ingestion pipeline, evidence-grounded recommendations, tool permission boundaries, evaluation sets and human review workflows.

> This guide is a plan for implementation. No code deployment, benchmark, security certification or hardware validation is asserted.
