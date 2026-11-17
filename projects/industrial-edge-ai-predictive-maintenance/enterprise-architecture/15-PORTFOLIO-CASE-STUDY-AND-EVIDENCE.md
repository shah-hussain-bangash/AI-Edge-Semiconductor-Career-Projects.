# EA-15 — Executive Architecture Case Study and Evidence Register

**EDGEOPS | Industrial Edge AI Predictive Maintenance**  
**Status:** Architecture and documentation portfolio with initial embedded starter materials. Physical hardware not yet purchased or validated; no production deployment claimed.

## Executive brief

Industrial maintenance workflows require trustworthy signals, attributable AI recommendations and auditable human decisions. EDGEOPS proposes a lab-scale condition monitoring system combining ESP32 sensor capture, Raspberry Pi 5 edge analytics, FastAPI/TimescaleDB, an operator dashboard and an advisory RAG copilot. Its differentiator is governed handoff from imperfect sensor evidence to a human-reviewed maintenance workflow, with explicit safety limits.

## Business value hypothesis

Potential improvement areas: time to triage, alert traceability, standardization of inspection recommendations, data-quality transparency and reduced duplicate investigation. **No savings, accuracy, ROI or deployment impact is claimed.** These must be evaluated with credible baselines.

## Architecture choices

1. Edge processing provides local context and reduces dependence on cloud availability.
2. MQTT provides asynchronous constrained-device messaging, with deduplication and a private broker.
3. PostgreSQL/TimescaleDB separates transactional maintenance records from time-series telemetry.
4. ONNX is evaluated against simpler rules before justified deployment.
5. RAG uses approved SOP versions and read-only guidance; human authorization is never delegated to an LLM.
6. Physical protection and motor isolation are independent of the platform.

## Current evidence versus future evidence

| Claim | Current status | Evidence route / missing proof |
|---|---|---|
| End-to-end target architecture documented | Documented design | EA-01 through EA-15 |
| Eight-phase engineering roadmap | Documented design | ../README.md and PHASE_01 through PHASE_08 guides |
| ESP32 starter code exists | Source present | ../phase-01-hardware/firmware/ |
| Hardware sensors operating | Not verified | purchase, photographs, I2C scan, serial logs required |
| ONNX inference on Pi 5 | Not verified | model bundle, Pi timings, repeatable run |
| MQTT secure transport | Not verified | broker ACL/TLS config and negative tests |
| Backend/dashboard integration | Not verified | API tests, DB and deployment evidence |
| RAG and agent approval controls | Proposed for EDGEOPS | policy enforcement tests and citations required |
| Real-world industrial deployment | Not claimed | site permission, qualified safety assessment and operational evidence required |

## Suggested recruiter-facing headline

**Industrial Edge AI & Governed Maintenance — Architecture Case Study**
Solution architecture | Embedded IoT | Edge inference | Agentic AI governance | Cybersecurity | Evaluation & delivery assurance.

## Portfolio presentation narrative

1. Business challenge and risk-aware system boundary.
2. Capability map and architecture context.
3. C4 container + trust zone diagram.
4. Telemetry, edge model and incident approval sequence.
5. Threat/risk register and independent physical safety boundary.
6. Evaluation methodology and design review gates.
7. Clear build roadmap and evidence status.
8. Lessons to be populated **after** implementation.

## Evidence collection rule

Evidence item format: `EVID-### | claim | provenance | environment | commit/model/firmware hashes | exact command | date | result | reviewer | artifact path`. Real physical lab data need photographs and raw measurements; synthetic demos must be visibly marked synthetic. Do not publish employer/customer data or sensitive repository contents.

## Honest positioning

This is an **architecture-first portfolio prototype**, not an industrial-certified product or proof of enterprise deployment. Strong architecture documentation creates an interview-ready design case study; measured evidence after implementation is needed to establish delivery outcomes.
