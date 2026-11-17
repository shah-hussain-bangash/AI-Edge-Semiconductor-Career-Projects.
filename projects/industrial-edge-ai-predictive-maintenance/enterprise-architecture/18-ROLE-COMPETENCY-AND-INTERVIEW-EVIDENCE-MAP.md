# EA-18 — EDGEOPS Role Competency and Interview Evidence Map

**Goal:** Show how a **single EDGEOPS project** is relevant to six target professional capabilities without exaggerating the engineer's actual job title or delivery evidence.

| Target competency | Architecture deliverables | Interview explanation | Future empirical proof |
|---|---|---|---|
| Enterprise AI Architect | EA-01 capability map, EA-16 boundaries, EA-07 choices, EA-14 governance | Connect business value stream to independently governed domains and ownership | sponsor review and changed architectural decision evidence |
| AI Solutions Architect | EA-02 C4, EA-03 / EA-10 contracts, EA-11 data, EA-06 NFRs | Defend edge/cloud split, QoS1 dedupe, provider-neutral deployment and capacity | component demo, contract tests, latency and cost |
| Agentic AI Architect | EA-04 approval sequence, EA-05/12 threats, EA-16 agent permissions | Explain why LLM is advisory, policy engine owns authorization and tools are read-only | prompt injection tests and denied tool calls |
| Senior Generative AI Architect | EA-04 retrieval, EA-13 evaluation, EA-11 SOP revisions | Defend chunking, retrieval ACL, evidence coverage, citations and abstention | golden-set evaluation and reviewed hallucination cases |
| AI Technical Lead | EA-09 verification, EA-14 RACI, EA-08 gates, phase plan | Explain delivery sequencing, release/rollback and how to handle failed tests | PR review, CI failures fixed, restore evidence |
| Security & AI Governance | EA-05 controls, EA-12 risk, EA-14 operating model | Demonstrate device identity, least privilege, physical safety separation and approved action lifecycle | negative tests, actual review and remediation |

## Ten-minute interviewer walkthrough

1. (1 min) Business problem and explicit lab limitations.
2. (1 min) Asset/telemetry/maintenance capability breakdown.
3. (2 min) Context + container diagrams and physical/cloud trust boundaries.
4. (1 min) MQTT duplicate/replay and offline behavior.
5. (1 min) Model baseline, data provenance, session holdout and expected uncertainty.
6. (1 min) RAG SOP permissions, prompt injection and cited abstention.
7. (1 min) Human approval and no-actuation invariant.
8. (1 min) Reliability, disaster recovery, cost and threat register.
9. (1 min) What is actually implemented, measured and still open.

## Recruiter-ready professional summary

**EDGEOPS — Industrial Edge AI Predictive Maintenance (Architecture Case Study)**

Designed a proposed enterprise reference architecture for guarded IoT condition monitoring, edge anomaly inference, audit-ready maintenance workflows and governed generative AI assistance. Produced business, C4, data, API/MQTT, risk, evaluation, operating-model and implementation-gate artifacts. Hardware tests and integrated deployment remain future milestones.

Do **not** revise "designed proposed architecture" to "deployed enterprise system" until verified evidence exists.

## What moves this from credible documentation to stronger senior-role evidence?

- Annotated tradeoff comparisons with real throughput/cost inputs.
- Independent stakeholders reviewing design decisions.
- Actual unit/integration/negative security tests and recorded artifacts.
- Bench-verified sensor inputs and model evaluation on hardware.
- A reproducible incident-to-human-approved-work-order run.
- Clear ownership, incident learning and an operational release.
