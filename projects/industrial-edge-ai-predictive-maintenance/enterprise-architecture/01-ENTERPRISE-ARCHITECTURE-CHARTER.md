# EA-01 — Enterprise Architecture Charter and Business Requirements

**Status:** Draft for stakeholder validation. **Intended domain:** synthetic/laboratory industrial maintenance.

## 1. Business problem and measurable objective

The proposed system addresses fragmented condition telemetry, reactive maintenance, slow triage, lack of evidence provenance and opaque AI advice. Desired outcomes: earlier detection of relevant anomalies; fewer unreviewed recommendations; more reproducible diagnostic histories; demonstrable operator oversight. These are **hypotheses**, not proven savings.

Business KPIs to negotiate: mean time to acknowledge incidents; alert precision and false-alarm rate; time from event to approved work order; proportion of recommendations citing approved SOPs; data completeness; audit completeness; service recovery. No numerical target is asserted before baseline data exists.

## 2. Stakeholders and responsibility

| Stakeholder | Primary decision | Evidence |
|---|---|---|
| Business sponsor | Approves outcomes, funding and pilot scope | Charter and business-case signoff |
| Enterprise architect | System boundaries, interoperability, architectural exceptions | Architecture decision records |
| AI solutions architect | Data/model design, quality gates | AI design and evaluation plan |
| OT/electrical safety reviewer | Motor wiring, power, guarding and safe operations | Independent safety review |
| Security architect | Device trust, identity, secrets, threat model | Control mapping and penetration-test plan |
| Data owner | Retention, classification, data sharing | Data register and approval |
| Maintenance engineer | Fault taxonomy and SOP applicability | Reviewed maintenance playbooks |
| Technical lead | Implementation sequencing, code and CI policy | Delivery plan and test evidence |
| Human approver | Authorizes work order, not equipment actuation | Signed decision and audit trail |

For a single-person portfolio, role assignments can be proposed, but **do not claim an independent review actually occurred**.

## 3. Capabilities

1. Device onboarding and asset registration.
2. Sensor collection and signal-quality validation.
3. Local telemetry buffering and transport.
4. Condition analytics and anomaly inference.
5. Incident correlation, deduplication and escalation.
6. Document-grounded diagnostic guidance.
7. Human work-order review, authorization and audit.
8. Fleet views, simulation and reporting.
9. Identity, security, monitoring, backup and recovery.
10. Data/model lifecycle and repeatable validation.

## 4. Scope

**In scope for prototype:** one guarded 12V DC motor; ESP32; ADXL345, DS18B20 and appropriately rated electrical measurements; Raspberry Pi 5; authenticated MQTT; ONNX anomaly detector; FastAPI; PostgreSQL/TimescaleDB; Next.js dashboard; synthetic or approved example maintenance documents; human-approved workflow.

**Out of scope:** PLC or SCADA actuation, production machinery control, safety integrity functions, medical devices, financial transactions, autonomous repair execution, claims of factory acceptance testing, certification, field MTBF reliability or unapproved proprietary industrial data.

## 5. Functional requirements (candidate identifiers)

| ID | Requirement | Acceptance evidence |
|---|---|---|
| FR-01 | Register asset and uniquely identifiable device | Valid/invalid registration test |
| FR-02 | Capture timestamped calibrated-or-unverified sensor samples with quality flags | Raw telemetry + schema validation |
| FR-03 | Authenticated transport to edge node with bounded reconnect behavior | Broker ACL and outage replay test |
| FR-04 | Persist telemetry with source/model/firmware provenance | DB query and trace example |
| FR-05 | Produce explainable anomaly scores and low-quality-data abstentions | Evaluation fixtures and model card |
| FR-06 | Deduplicate and correlate incidents | Deterministic integration tests |
| FR-07 | Restrict SOP-grounded RAG to advisory answers | Retrieval and prompt-injection test |
| FR-08 | Require authorized human approval for work orders | Unauthorized/dual-role tests |
| FR-09 | Display synthetic vs measured data visibly | UI test and screenshot |
| FR-10 | Preserve auditable state changes and recovery | Tamper/retry/restore evidence |

## 6. Constraints and architectural principles

- Explicit least privilege, defense in depth, data minimization and zero implicit trust between devices/services.
- Physical safety is independent of software and AI output.
- Edge may continue bounded collection when cloud/backend unavailable; missing data must not be presented as healthy.
- Avoid unbounded data retention and uncontrolled token/tool use.
- Architectural decisions must document alternatives, tradeoffs and reversal triggers.

## 7. Business case template (unmeasured)

Cost: hardware + engineering hours + hosting + support + model/API usage + maintenance + security. Benefit hypotheses: faster triage, reduced investigation effort, transparent decision trail. Record baseline, measurement method and uncertainty; never invent ROI or downtime savings.

## 8. Open questions

Asset criticality? Required sample rate and sensor bandwidth? Actual motor stall current? Site network? Data residency obligations? Person responsible for approving work orders? Offline duration? Retention period? False-alarm tolerance? Approval segregation? These are **open design inputs**, not assumed facts.
