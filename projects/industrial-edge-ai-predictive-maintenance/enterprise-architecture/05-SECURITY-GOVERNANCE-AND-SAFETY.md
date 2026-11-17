# EA-05 — Security, Governance, Privacy and Physical Safety

**Status:** Threat model proposal, not an independent audit or certification.

## Asset classification

- Device identity, MQTT credentials, service secrets, API signing keys: **restricted**.
- Personnel/approver identities and detailed audit history: **confidential**.
- Device IDs, maintenance SOPs and equipment configuration: **internal**, unless license/classification indicates more restrictive.
- Synthetic sample telemetry: **public-demo eligible only when free of sensitive metadata**.
- Real industrial data: **not public without owner authorization**.

## Trust boundaries and principal types

Distinct device, edge-service, backend-service, end-user and administrator identities. Device may publish only its own allowed topics. Operator may view authorized asset data but cannot approve without assigned reviewer privilege. Independent approver must be a distinct authorized identity when required by policy; never silently substitute a demo user.

## STRIDE-oriented threat table

| Threat | Target | Planned mitigation | Verification |
|---|---|---|---|
| Spoofed sensor | MQTT | unique device cert/credential, per-topic ACL, broker private | revoked ID publish denied |
| Replay/duplicate | ingest | boot/sequence dedupe, idempotency, TTL | duplicate test |
| Tampered telemetry | message path | TLS, origin mapping, schema + range checks | mutation rejection |
| Service compromise | API | scoped tokens, network segmentation, least privilege | cross-role access tests |
| Cross-tenant leakage | DB/API/RAG | server enforced site/asset ACL and row security where used | cross-tenant denial tests |
| Untrusted SOP prompt injection | RAG/agent | source treated as data, tool allowlist, human review | adversarial SOP test |
| Unauthorized work order | workflow | RBAC, approval separation, version binding, auditable transitions | self-approval denied |
| Model poisoning | training/release | hashed datasets, approvals, signed/pinned artifacts | checksum failure |
| Device DoS | broker/gateway | limits, quotas, backpressure, bounded queue | load/disconnect test |
| Sensor false healthy | dashboard | stale/invalid-data state and freshness bound | missing telemetry test |
| Secrets leak | repos/logs | secret scanning and redaction | staged leak test |
| Backup compromise | storage | encryption, restricted restore identity | recovery test |

## Physical and operational safety case

- Low-voltage guarded lab motor only. No uncovered mains wiring and no mains on breadboards.
- Verify motor startup/stall current, driver ratings, fuse coordination, cable gauge, polarity and cooling before energizing.
- Guard all rotating shafts and secure the mount.
- Physical disconnect must be accessible and independent of Wi-Fi, MQTT, backend and AI.
- The motor cannot be commanded by an AI agent, dashboard or cloud service without a separately engineered safety case and competent review; this prototype deliberately excludes that use.
- Motor stall, electrical fault injection or unsafe load tests are not acceptable demo methods.

## Governance system

| Control domain | Owner candidate | Required artifact |
|---|---|---|
| Architecture review | enterprise/solutions architect | design signoff and ADRs |
| Product risk | project sponsor | risk register and exception decisions |
| Device/electrical safety | qualified reviewer | schematic and guard review |
| IAM | security engineer | matrix of principals, claims and entitlements |
| Data privacy | owner/compliance reviewer | data flow and retention assessment |
| AI risk | AI architect + reviewer | model card, evaluation, fallback plan |
| Release authorization | technical lead + approver | release gate and deployment record |
| Incident handling | operations owner | response and escalation runbook |

## Security acceptance tests

Test invalid MQTT cert, topic ACL denial, replay, oversized message, unauthorized asset view, cross-tenant SOP retrieval, stale work-order approval, duplicate submission, malicious SOP prompt injection, unsigned model rejection, loss of network and audit tamper evidence.

## Framework mapping (guidance, not certification)

Use NIST AI RMF for governing, mapping, measuring and managing AI risk; NIST CSF for broader cybersecurity; OWASP LLM application risks for RAG/agents; IEC 62443 concepts for industrial network segmentation and device identity **only as design guidance**. Applicability, current versions and organizational control owners require validation. Evaluate UAE data protection and contractual data residency requirements with qualified counsel before real deployments.

## Residual risks

Commodity ADXL345 is not industrial-certified; INA219 has board-specific shunt limits; motor drivers may be undersized; network authentication does not prove physical safety; LLM guidance may hallucinate; a single Pi or broker may fail. Record owners, severity, acceptance and scheduled retesting. Open risks must not be silently closed.
