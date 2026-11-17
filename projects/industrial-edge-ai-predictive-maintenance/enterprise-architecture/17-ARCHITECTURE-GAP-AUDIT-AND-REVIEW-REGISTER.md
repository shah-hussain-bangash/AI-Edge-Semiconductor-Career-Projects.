# EA-17 — Enterprise Architecture Gap Audit and Review Register

**Audit date:** 2026-11-17  
**Basis reviewed:** Current EDGEOPS project README, EA architecture index and case study; existing EA-01 through EA-15 package as previously authored. **Not a code execution audit or physical test.**

## 1. What already existed

- Project problem definition and guarded low-voltage scope.
- Eight-phase implementation roadmap and initial ESP32 source directories.
- Fifteen numbered architecture documents covering business charter, architecture, system design, AI, security, operations, ADRs, review gates, traceability, contracts, data governance, risk, evaluation, RACI and evidence.
- Illustrative diagrams and a simulated 15-screen user-interface description.
- Explicit statements that hardware-to-cloud testing and factory deployment are not demonstrated.

## 2. Findings and actions

| ID | Importance | Finding | Resolution / current status |
|---|---|---|---|
| GAP-01 | High | Architecture knowledge scattered across multiple files; no concise authoritative master | **Addressed in documentation:** EA-16 master SAD with linked canonical details |
| GAP-02 | High | Implementation guides may be mistaken for verified controls/results | **Controlled by policy:** evidence labels and status gates; real verification remains pending |
| GAP-03 | High | RAG recommendation versus workflow approval/physical action boundaries must be unambiguous | **Addressed in architecture:** advisory-only agents; independent approval; no actuation |
| GAP-04 | Critical | Exact motor stall current, power, fusing and guard ratings unknown | **Open / block motor energization:** electrical review pending |
| GAP-05 | High | API and MQTT contracts not yet reconciled to real firmware/backend | **Open:** contract-to-code comparison once implementations exist |
| GAP-06 | High | Requirements and nonfunctional targets require actual stakeholder decisions | **Open:** scope, RPO/RTO, latency, sampling and retention unapproved |
| GAP-07 | High | AI evaluation, benchmark and RAG attack claims unmeasured | **Open:** execute tests, store raw evidence, no fabricated percentages |
| GAP-08 | High | Device credential provisioning/rotation and network zoning not implemented evidence | **Open:** security prototype and negative tests |
| GAP-09 | Medium | No verified operating cost or workload sizing | **Open:** actual hardware orders + cloud usage model and measurements |
| GAP-10 | Medium | Recruiter case study needs linked screenshots, measured tradeoffs and reproducible evidence | **Open:** add only after tests |
| GAP-11 | High | Architectural reviews require real owners and signoff | **Open:** author cannot imply independent approval |
| GAP-12 | Medium | Mermaid C4 and role competencies require navigable story | **Addressed in documentation:** master SAD and competency map, visual polish remains a future option |

## 3. Review gate dashboard

| Gate | Current state | Closure evidence |
|---|---|---|
| G0 business charter | OPEN | actual sponsor/owner scope signoff |
| G1 requirements | OPEN | accepted FR/NFR and test traceability |
| G2 solution architecture | OPEN | reviewed C4, trust zones, ADR alternatives |
| G3 AI/GenAI | OPEN | evaluation protocol accepted and dataset permissions |
| G4 safety/security | OPEN | threat model review + qualified electrical signoff |
| G5 implementation readiness | OPEN | delivery plan, cost, CI quality gates, release plan |
| G6 deployment | NOT STARTED | reproducible end-to-end tests, rollback, approved release |

## 4. Design consistency and change checklist

- Canonical project name: **EDGEOPS**; avoid calling the proposed architecture a deployed product.
- Canonical physical scope: **guarded 12V low-voltage lab motor**.
- Canonical sensor roles: ADXL345 vibration, DS18B20 temperature, INA219 only with verified electrical ratings.
- Canonical inference: baseline rules first, ONNX model only after held-out evaluation.
- Canonical telemetry: ESP32 -> authenticated private MQTT -> Pi edge -> validated HTTPS API -> PostgreSQL/TimescaleDB.
- Canonical GenAI: approved SOP retrieval and suggestion **only**.
- Canonical approval: server-side independent authorized human; version binding; audited decision.
- Canonical status: design/prototype materials exist; physical bench and production credentials not established.
- Canonical hardware state: Temu selected/cart items **not purchased**.
- Maintain a changeset review when modifying existing phase guides or source contracts.

## 5. Priority closure order

1. Obtain exact selected motor and sensor datasheets, define circuit safety review (do not power).
2. Confirm scope, stakeholders and business goals; accept FR/NFRs.
3. Decide identity, broker/MQTT version, cloud region, data classification and retention.
4. Reconcile firmware payload + backend routes with EA-10 contracts.
5. Review actual source, run static/test inventory, file evidence.
6. Select baseline and AI evaluation datasets; approve release criteria.
7. Simulate complete workflow with negative security tests.
8. Prepare an architecture-review packet with reviewer names, date, signatures, open issues.
9. Publish only evidence-backed portfolio diagrams, demos and test reports.

## 6. Evidence versus documentation

**Completed:** master SAD authored, audit register authored, navigation and competency mapping authored.  
**Not completed:** stakeholder signoff, electrical acceptance, measured validation, production certification, cloud deployment confirmation.  
**Important:** No GitHub commit alone proves architecture quality, real business impact, or correctness of running software.
