# EA-06 — Nonfunctional Requirements, Operations and FinOps

**Status:** Proposed thresholds and measurement methods; no benchmark measured yet.

## Quality attributes and acceptance

| Quality attribute | Proposed requirement / method | Evidence |
|---|---|---|
| Reliability | detect missing device heartbeat, broker and edge downtime | disconnect and reboot tests |
| Telemetry correctness | valid units, timestamps, schema, dedupe and quality flags | golden packets and property tests |
| Latency | define sample-to-alert p95 target from observed baseline | correlated timestamp traces |
| Security | per-device MQTT ACL, authenticated APIs, role enforcement | negative authorization tests |
| Privacy | documented classification, retention and deletion workflow | data mapping and test |
| Maintainability | versioned schemas, interfaces and ADRs | CI and change-review records |
| Scalability | define devices/site and ingest volume; test plausible sizes | staged load test |
| AI quality | declared dataset splits and error analysis | evaluation report |
| Explainability | link event to source window/model and SOP citations | incident trace |
| Accessibility | keyboard navigation, contrast and error feedback | WCAG-oriented UI checks |
| Recoverability | define RPO/RTO with sponsor then measure clean restore | signed restore drill |
| Observability | metrics, logs, traces and alert ownership | monitoring dashboard + runbook |

Targets should be **proposed**, not recorded as achieved. Do not invent availability percentages or p95 milliseconds.

## Operational telemetry

Device: uptime, last-seen, firmware, boot ID, missed sequences. Edge: buffer fill, dropped windows, inference latency, CPU, temperature, model hash. Application: API p95, 4xx/5xx, work-order transition failures, approvals, data lag. AI: anomaly rate, drift/quality indicators, RAG citation/abstention, denied tools. Security: auth failures, ACL denials, credential expiry.

## Failure and disaster recovery design

- Wi-Fi loss: edge or device buffer within bounded limits, visible stale status.
- Pi restart: local durable queue if feasible, service restart, detect missing model.
- Broker outage: alarm and store counters; reconnect with backoff.
- Database outage: queue ingestion with bounded retention; replay idempotently on return.
- Model rollback: bundle model+scaler+feature schema and verify signatures.
- SOP update: rebuild index with version references; invalidate stale citations.
- Backup: encrypt Postgres/config/model metadata, keep off-host copy, restore to clean environment.
- Security incident: revoke compromised identity and review broker/API activity.

## Environment and release plan

| Environment | Data | Access | Purpose |
|---|---|---|---|
| Development | synthetic and approved lab samples | engineers | iteration and unit tests |
| Staging | sanitized test fixtures | limited testers | integration, vulnerability and load tests |
| Pilot (future) | authorized measured data | business-authorized | controlled operation after reviews |

CI gates: lint/type checks -> unit tests -> integration -> model parity -> safety/security tests -> secret and dependency scan -> container build / SBOM -> staging -> manual approval -> controlled release -> rollback readiness.

## Costs and sizing

Separate upfront prototype hardware from monthly operations. Cost categories: Pi/ESP32/sensors/power protection; replacement components; storage and compute; IoT network connectivity; LLM request tokens; vector search; monitoring; engineer hours; backups; vulnerability scanning. Build low/base/high estimates from actual invoices and measured traffic. GPU/Jetson is optional and unjustified until workload needs documented.

```text
Monthly run cost =
  compute + managed database + storage + backups + network egress
  + model/API tokens + monitoring + certificate/domain charges
  + human support/operations
```

**Cost control:** token budgets, caching where appropriate, request quotas, retention tiers, edge-first deterministic anomaly detection. Record actual invoices separately from estimates.

## Sustainability of operations

Define runbooks for broker loss, sensor failure, stale inference, high false-alarm rates, data corruption, leaked credentials, unsafe AI response, failed approval gate, out-of-disk and restore. Every runbook needs trigger, severity, owner, mitigation, verification and postmortem template.
