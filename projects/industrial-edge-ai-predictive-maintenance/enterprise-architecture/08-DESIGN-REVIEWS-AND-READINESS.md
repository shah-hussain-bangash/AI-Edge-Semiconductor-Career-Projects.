# EA-08 — Architecture Review Gates and Implementation Readiness

**Status:** Draft gates. No gate is passed by documentation creation alone.

## Gate sequence

| Gate | Scope | Required artifact | Status |
|---|---|---|---|
| G0 | Scope and business problem | approved charter, owner and MVP definition | OPEN |
| G1 | Functional/nonfunctional requirements | signed traceability and acceptance matrix | OPEN |
| G2 | Architecture and integration | C4 diagrams, data flow, protocols and ADR review | OPEN |
| G3 | AI and evaluation | dataset provenance, model/RAG tests, expected failure behavior | OPEN |
| G4 | Threat and physical safety | reviewed threat model, rated circuit schematic, guard and independent disconnect | OPEN |
| G5 | Delivery readiness | resourcing, environment, rollback, budget and test plan | OPEN |
| G6 | Implementation release | code/integration test evidence and authorized release signoff | NOT STARTED |

"Signed" can be a dated review decision in a repository issue, but should identify actual reviewer, role, comments and approved scope. Do not invent approval.

## Design review checklist

- [ ] Business requirements connect to capabilities and component interfaces.
- [ ] Explicit operating boundary (lab, not factory / safety controller) stated everywhere.
- [ ] C4 context/container/component views reviewed for completeness.
- [ ] Every component has owner, SLA/SLO candidate, data contract and failure behavior.
- [ ] Device identity, secret rotation, TLS and topic ACLs designed.
- [ ] Independent physical safety reviewer confirms wiring, fuse, current and guarding.
- [ ] Model evaluation prevents adjacent-window leakage; false alarm limitations described.
- [ ] RAG content treated as untrusted; tool grants explicitly deny actuation.
- [ ] Human approval is server-side, version-bound, auditable.
- [ ] Backup restore, offline buffering, security negative tests and rollback are planned.
- [ ] Public GitHub artifacts contain no credentials or proprietary information.
- [ ] Documentation claims align with test/deployment artifacts.

## Requirements traceability examples

| Requirement | Design sections | Planned test |
|---|---|---|
| FR-02 sensor sampling | EA-02 device + EA-03 telemetry | I2C/OneWire capture and quality-flag test |
| FR-03 secure delivery | EA-02 MQTT + EA-05 identity | invalid cert / retry / dedupe |
| FR-05 anomaly model | EA-04 model bundle | ONNX parity, holdout evaluation, stale data |
| FR-07 RAG citation | EA-04 RAG + EA-05 injection | missing source and malicious SOP |
| FR-08 approval | EA-03 state machine + EA-05 RBAC | self-approval and stale approval denied |
| FR-10 auditability | EA-03 audit + EA-06 backup | replay and restored event trace |

## Implementation staging after architectural review

1. Inventory and bench electrical safety review (no mains, no motor powering until review).
2. Sensor-only ESP32 firmware and captured logs.
3. MQTT authenticated ingestion and outage tests.
4. Pi ONNX pipeline with versioned metrics.
5. API/database workflow, auth and UI.
6. RAG advisory and audited approval workflow.
7. Evaluation, backup/restore, security tests and demonstration.

## Portfolio evidence directory specification

For each claimed milestone store: `evidence/YYYY-MM-DD/{scenario}/` containing a short README, test command, environment, firmware/software commit SHA, real/synthetic data label, redacted logs, screenshot, reviewer, pass/fail and known limitations. Do not publish personal data, passwords or proprietary SOPs.

## Signoff block

| Gate | Reviewer name/role | Decision/date | Open issues | Evidence URL |
|---|---|---|---|---|
| G0 | Not assigned | Pending | Charter validation | — |
| G1 | Not assigned | Pending | Requirements acceptance | — |
| G2 | Not assigned | Pending | Architecture review | — |
| G3 | Not assigned | Pending | Model evaluation design | — |
| G4 | Not assigned | Pending | Physical safety and security | — |
| G5 | Not assigned | Pending | Delivery readiness | — |

## Readiness decision

**NOT READY FOR MOTOR ENERGIZATION OR PRODUCTION CLAIMS.** Architecture package is a baseline proposal, not accepted engineering assurance. Sensor-only software work can be planned separately; physical testing requires component compatibility and electrical safety review.
