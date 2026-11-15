# Phase 08 — Security Hardening, MLOps, Production Deployment & Professional Portfolio Demonstration

**Project:** Industrial Edge AI Predictive Maintenance & Autonomous Operations Platform  
**Status:** Implementation blueprint; not evidence of deployed software, completed hardware experiments, certified safety, or measured performance.  
**Prerequisites:** Phases 01–07.  
**Objective:** Turn the prototype into a reproducible, monitored, security-reviewed, recoverable **production-oriented pilot**, with a transparent, technically credible GitHub portfolio.

## 1. Final system architecture

```text
Guarded 12V motor + sensors
          |
         ESP32 (firmware, device identity, bounded queue)
          |
      TLS MQTT / LAN
          |
  Raspberry Pi 5 edge node
  - ONNX Runtime inference
  - local buffering and health
          |
  authenticated ingestion
          |
 FastAPI + PostgreSQL/TimescaleDB
   |        |          |
 incidents  audit      model registry
   |        |          |
 Next.js operations dashboard
   |                 |
 human approvals   RAG assistant (read-only evidence + drafts)
   |
 approved inspection work order

Operational plane:
GitHub Actions -> signed/versioned artifacts -> staging -> manual promotion
Prometheus/Grafana + logs/traces + backups + recovery exercises
```

**Safety boundary:** No autonomous motor actuation, no PLC writes, no bypass of interlocks. Human review is mandatory for maintenance workflow approvals. The physical emergency disconnect must operate independently of software.

## 2. Scope and definition of production-ready

A hobby demonstration is not equivalent to a production-certified industrial system. This phase targets **production-oriented engineering quality**: least privilege, documented threat model, reproducible builds, tested backup restoration, staged releases, audit trails, model rollback, and measured service reliability. Any real industrial deployment additionally requires site-specific safety engineering, applicable standards, qualified reviews, and operational approval.

## 3. Hardware and environment checklist

| Component | Purpose |
|---|---|
| ESP32 + validated sensors | Authenticated telemetry source |
| Guarded low-voltage DC motor test rig | Physical demonstration |
| Raspberry Pi 5 with cooling and reliable storage | Edge inference and buffering |
| Laptop / Linux server or VM | API, DB, dashboard, staging |
| Isolated LAN / router | Segmented device network |
| UPS (optional) | Resilience to short power loss |
| External backup target | Restore testing and retention |
| Power meter (optional) | Measured energy benchmarks |

Separate **development**, **staging**, and **production pilot** configurations. Use synthetic telemetry only with visible provenance labels.

## 4. Implementation workstreams

### Workstream A — Threat modeling and security boundaries
1. Inventory assets: devices, MQTT broker, API, database, documents, model files, identities and secrets.
2. Map trust boundaries: device -> broker -> edge -> backend -> browser -> AI tools.
3. Analyze spoofing, tampering, replay, denial of service, privilege escalation, data leakage, malicious SOP content and model artifact compromise.
4. Assign mitigations, owners, residual risks and verification tests.
5. Require human review for any risk that could affect physical equipment.

**Deliverables:** `docs/threat-model.md`, network/data-flow diagram, risk register and test evidence.

### Workstream B — Device and MQTT hardening
1. Give each ESP32 a unique identity and revocable credentials.
2. Use authenticated MQTT over TLS with certificate validation and per-device topic ACLs.
3. Keep broker private; never expose development MQTT port publicly.
4. Enforce payload size limits, schema versions, sequence/boot IDs and deduplication.
5. Use bounded offline queues and explicit dropped-record counters.
6. Pin firmware versions; document signed firmware and secure boot feasibility for the exact ESP32 hardware.
7. Verify disconnect, reconnect, credential rotation, revoked identity and invalid certificate behavior.

**Important:** Secure boot, flash encryption and OTA capabilities depend on the exact ESP32 variant, bootloader and provisioning workflow. Do not claim these controls until configured and tested on the chosen board.

### Workstream C — API, database and identity security
1. Validate OIDC issuer, audience, signature, expiry and role claims server-side.
2. Enforce RBAC and asset-level authorization on every endpoint and agent tool.
3. Separate human identities, device identities and service accounts.
4. Protect cookies against CSRF where applicable; configure CORS narrowly.
5. Apply request limits, timeouts, strict schema validation and rate limiting.
6. Use least-privilege DB roles and parameterized queries.
7. Protect backups, audit data and SOP documents with encryption and access policies.
8. Test unauthorized approvals, cross-asset access, duplicate requests and replay attacks.

### Workstream D — Secrets and software supply chain
1. Keep credentials, private keys, production data and proprietary manuals out of Git.
2. Use a secret manager or protected deployment-time environment injection.
3. Pin dependencies and container image digests.
4. Run dependency, secret and container vulnerability scanning in CI.
5. Generate an SBOM and document provenance of firmware, models and containers.
6. Use signed release artifacts where supported and verify signatures before promotion.
7. Establish a vulnerability triage and patching process.

### Workstream E — MLOps and model registry
1. Version dataset snapshots and record their hashes, origin and consent/usage rights.
2. Version feature extraction, preprocessing, scaler, anomaly threshold, model weights and ONNX file **as one release bundle**.
3. Record training seed, train/validation/test split, metrics, hardware and package versions.
4. Validate ONNX parity and model quality against the approved reference.
5. Maintain model states: `candidate -> validated -> staged -> approved -> active -> retired`.
6. Restrict model promotion to authorized reviewers; require documented approval.
7. Implement rollback to a known-good model with compatible feature schema.
8. Track sensor quality, distribution drift, false alarms (when labels exist), inference latency and model version by device.
9. Never auto-promote a drift-triggered retrain into safety-adjacent operations.

Example model manifest:

```yaml
model_id: motor-anomaly-ae
version: 0.1.0
format: onnx
artifact_sha256: REPLACE_WITH_COMPUTED_HASH
feature_schema_version: 1
preprocessor_version: 1
threshold_config_version: 1
dataset_manifest: datasets/healthy-motor-v1.yaml
validation_report: reports/model-validation-v0.1.0.md
status: candidate
```

This is an example, not a registered or validated model.

### Workstream F — Reproducible deployment
1. Maintain separate Docker Compose development and staging configurations.
2. Use private networks for database, broker and worker.
3. Expose only the reverse proxy over TLS.
4. Add health/readiness probes, resource limits, log rotation and restart policies.
5. Apply Alembic migrations as an explicit controlled step.
6. Require backup verification before irreversible migrations.
7. Document a staging smoke-test checklist and manual promotion gate.
8. Pin Pi OS, Python, ONNX Runtime, PostgreSQL/TimescaleDB, Node and container versions in an environment manifest.

Example service inventory:

```text
reverse-proxy
web-nextjs
api-fastapi
worker-outbox
postgres-timescaledb
mqtt-broker
metrics-prometheus
dashboard-grafana
edge-inference-pi
```

This is a logical inventory; place services on hosts according to resource and network constraints.

### Workstream G — CI/CD quality gates
A GitHub Actions workflow should:
1. Check Markdown links and repository structure.
2. Lint and type-check Python and TypeScript.
3. Run unit tests for feature extraction, payload validation, incident correlation and approval permissions.
4. Run integration tests with ephemeral PostgreSQL/MQTT services.
5. Run ONNX parity tests and deterministic evaluation cases.
6. Test RAG citations, abstention and prompt-injection defenses.
7. Scan secrets, dependencies and containers.
8. Build versioned artifacts and record hashes/SBOM.
9. Deploy to staging after automated gates pass.
10. Require manual approval for pilot promotion.

Never place production secrets in public GitHub Actions logs or workflow files.

### Workstream H — Observability and operational SLOs
Collect metrics for:
- Device last-seen, sensor validity, packet gaps and reconnects.
- MQTT ingress rate, duplicate count and invalid payloads.
- API latency p50/p95/p99, 4xx/5xx, authentication failures.
- Database storage, ingestion lag, slow queries and outbox backlog.
- Edge inference latency, dropped windows, model version and drift.
- Incident creation delay, duplicate incidents and human approval integrity.
- RAG citation failures, abstentions, tool-policy denials and cost/latency.
- Backup age, restore test results, disk space and certificate expiry.

Set SLO targets only after measuring a realistic baseline. Keep an alert runbook with owner, escalation and recovery steps.

### Workstream I — Backups, disaster recovery and rollback
1. Define recovery point objective (RPO) and recovery time objective (RTO) based on actual pilot needs.
2. Back up PostgreSQL, configuration, SOP manifests, model registry and encryption-key recovery procedures.
3. Encrypt backups, restrict access and store a copy outside the primary host.
4. Perform a **restore drill** into a clean environment and verify row counts, incidents, model references and application login.
5. Test Pi reboot, broker outage, database restart, corrupted model rejection and deployment rollback.
6. Record measured recovery time and data loss rather than claiming zero loss.
7. Ensure local inference degradation is visible and never silently classified as healthy.

### Workstream J — Security and reliability validation
Minimum adversarial tests:
- Invalid MQTT certificate / revoked device identity.
- Unauthorized topic publish and cross-device impersonation.
- Duplicate/replayed event IDs.
- Malformed and oversized telemetry.
- Unauthorized asset access and work-order approval.
- Prompt injection embedded in an SOP PDF.
- Model artifact checksum mismatch.
- Database outage and outbox replay.
- Network partition between edge and backend.
- Stale sensor measurements and missing windows.
- Secrets accidentally included in logs or commits.
- Failed backup restoration.

Record pass/fail, evidence, severity, owner and remediation. Do not present untested controls as implemented.

## 5. Professional GitHub portfolio structure

```text
industrial-edge-ai-predictive-maintenance/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── hardware-bom.md
│   ├── wiring-and-safety.md
│   ├── threat-model.md
│   ├── data-contracts.md
│   ├── model-card.md
│   ├── evaluation-report.md
│   ├── operations-runbook.md
│   └── demo-script.md
├── hardware/
│   ├── esp32-firmware/
│   └── schematics/
├── edge/
│   ├── inference/
│   └── model-bundles/
├── backend/
│   ├── app/
│   ├── migrations/
│   └── tests/
├── frontend/
│   ├── app/
│   └── tests/
├── ai/
│   ├── training/
│   ├── rag/
│   └── evaluations/
├── simulation/
│   ├── twin/
│   └── scenarios/
├── infra/
│   ├── compose/
│   ├── monitoring/
│   └── ci/
├── assets/
│   ├── architecture-diagram.png
│   ├── dashboard-screenshot.png
│   └── demo-thumbnail.png
└── .github/workflows/
```

The diagram and screenshot filenames above are **future deliverables**, not existing assets. Do not fabricate screenshots or benchmark tables.

## 6. README template requirements

The project landing page should explain:
1. **Problem:** Industrial motor condition monitoring and accountable maintenance workflows.
2. **Solution:** Physical sensors, edge anomaly detection, backend, dashboard, RAG and human approval.
3. **Architecture:** One accurate diagram with hardware and trust boundaries.
4. **Hardware:** Exact purchased part numbers, photos and safe wiring notes.
5. **Quick start:** Tested local deployment commands and prerequisites.
6. **Data provenance:** Real vs synthetic vs replayed recordings.
7. **Model evaluation:** Measured quality, false alarms, latency and limitations.
8. **Security:** RBAC, MQTT auth/TLS, approval boundary and known residual risks.
9. **Demo:** Short video showing sensor -> MQTT -> edge alert -> dashboard -> approved work order.
10. **Status:** Clearly distinguish planned, implemented, tested and validated features.
11. **License and contributions:** License only material you own or can redistribute.
12. **Next steps:** Honest engineering roadmap and issues.

## 7. Demo sequence for employers and technical reviewers

**Target duration: 5–8 minutes.**
1. Show the guarded low-voltage motor, sensors and ESP32.
2. Show live telemetry flowing through MQTT.
3. Display Raspberry Pi ONNX model version and measured inference timing.
4. Show a real healthy operating baseline.
5. Introduce a safe operating-state change or replay a clearly labeled synthetic anomaly.
6. Show incident correlation, sensor evidence and dashboard update.
7. Ask the RAG assistant for an inspection procedure and verify source citations.
8. Demonstrate a draft work order requiring a separate human approver.
9. Show audit history and unauthorized approval denial.
10. Show model registry, rollback plan and a recovery test report.

Never represent simulated faults as verified physical bearing failures or measured RUL.

## 8. Final acceptance and release gates

| Gate | Evidence required |
|---|---|
| G1 Hardware | Actual wiring schematic, safe bench photos, validated sensor data |
| G2 Connectivity | Authenticated MQTT, outage/reconnect logs, deduplication tests |
| G3 Edge AI | Session-disjoint evaluation, ONNX parity, Pi benchmark |
| G4 Backend | API integration tests, DB migration and telemetry query benchmarks |
| G5 Workflow | RBAC, incident correlation, human approval and audit E2E tests |
| G6 RAG | Approved SOP provenance, citation checks, injection tests |
| G7 Fleet | Synthetic/real provenance, replay and drift reports |
| G8 Security | Threat model, secret scanning, access tests and remediation |
| G9 Operations | Monitoring, backup restore, rollback and incident runbooks |
| G10 Portfolio | Accurate README, demo video, diagrams, limitations and license |

**Release rule:** A gate remains `NOT VERIFIED` until the exact evidence exists. Failed tests must be documented and fixed or explicitly accepted by a responsible reviewer.

## 9. Suggested implementation schedule (planning estimate)

| Sprint | Focus | Exit evidence |
|---|---|---|
| 1 | Threat model, access policy, secret handling | Risk register and negative tests |
| 2 | Device/MQTT hardening and schema validation | Auth, TLS and replay tests |
| 3 | Model registry, parity and rollback | Versioned model bundle and rollback demo |
| 4 | CI/CD and staging deployment | Green pipelines and staging smoke tests |
| 5 | Observability and backup restore | Dashboards, alerts and restore report |
| 6 | End-to-end security, reliability and demo | Release gate report and portfolio assets |

Actual duration depends on hardware availability and implementation progress.

## 10. Definition of done

Phase 08 is complete when:
- [ ] A reproducible staging deployment works end-to-end with real sensor-origin telemetry.
- [ ] Device, service and human identities are separated and authenticated.
- [ ] Sensitive workflows enforce backend RBAC and human approvals.
- [ ] Models, features, datasets and thresholds are versioned and rollback-tested.
- [ ] Monitoring, backup restoration and disaster recovery are exercised.
- [ ] CI runs automated tests and security checks.
- [ ] Synthetic and measured evidence are clearly distinguished.
- [ ] A concise, truthful professional portfolio demonstrates the system and its limits.
- [ ] All G1–G10 gates have documented evidence or explicitly disclosed gaps.

## 11. After Phase 08

Once the flagship prototype has genuine evidence, extend your portfolio to:
- AI chip inference optimization and energy benchmarking.
- FPGA neural network accelerator with RTL verification.
- Industrial vision inspection.
- Semiconductor wafer defect detection.
- AI-assisted RTL verification and EDA.

These are **separate engineering projects**, not features automatically delivered by this maintenance platform.

> This guide is a detailed implementation plan. It does not assert industrial certification, measured performance, physical hardware testing, or successful production deployment.
