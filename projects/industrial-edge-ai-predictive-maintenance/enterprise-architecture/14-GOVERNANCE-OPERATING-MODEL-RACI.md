# EA-14 — Architecture Governance, Technical Leadership and Operating Model

**Status:** Proposed RACI for a future team or supervised project. Does not imply that named people reviewed or approved the architecture.

## Architecture review board

Review the business charter, C4 diagrams, integration contracts, threat model, model card, NFRs and budget before irreversible technical choices. Record decision outcomes: approved / approved with conditions / revise / rejected. Track explicit reviewers and dates. Authoring and approval are separate roles when required.

| Activity | Architect | Tech lead | Security | OT safety | Data owner | Business sponsor |
|---|---|---|---|---|---|---|
| Business scope and outcomes | C | C | I | I | C | A |
| Solution design and ADR | A/R | R | C | C | C | I |
| Electrical protection and guarding | C | R | C | A | I | I |
| Data classification/retention | C | R | C | I | A | I |
| AI evaluation and model release | A | R | C | C | C | I |
| Approval policies and identities | R | C | A | C | C | I |
| Release change management | C | A/R | C | C | I | I |
| Production pilot authorization | R | C | C | C | C | A |

R=Responsible, A=Accountable, C=Consulted, I=Informed. This is a **candidate organization model**, not actual staffing. Avoid duplicate accountability on a single deliverable; adapt it to the employer's governance.

## Engineering lifecycle

Intake -> discovery -> requirements -> ADRs -> design review -> proof-of-concept -> implementation -> automated quality gates -> staging -> human approval -> monitored release -> lessons learned. Use small vertical slices and revise ADRs after evidence; documentation-first is not documentation-only.

## Minimum meeting/review artifacts

- Architecture review agenda and minutes with open questions.
- Proposed ADR with alternative comparison, consequences and reversibility.
- Threat model review and independent electrical assessment.
- Design-to-test traceability matrix.
- Deployment checklist, rollback procedure and post-release observations.
- Decision log, owners and evidence links.

## Repository change policies

- No production secrets, proprietary manuals or personal records in public GitHub.
- Use branches and PR review for code/design updates when collaborators are available.
- Docs-only changes: Markdown/link lint and diagram render validation.
- Contract changes: schema compatibility and migration tests.
- AI changes: evaluation manifest and approval evidence.
- No status upgrade from planned to tested without reproducible output.
- No invented benchmark, approval, employment outcome or customer impact.

## Role-positioning evidence

**Enterprise AI Architect:** capability-to-system traceability and technology governance.
**AI Solutions Architect:** interfaces, ADRs, NFR, cost/deployment constraints.
**Agentic AI Architect:** tool policies, approval state machines and prompt-injection defenses.
**Senior Generative AI Architect:** RAG evaluation, grounding, model lifecycle.
**AI Technical Lead:** delivery gates, ownership, tests, incident learning.
**Security/Governance:** threat model, audit, least privilege and risk treatment.

This document is supporting architecture evidence, not itself proof of having held each role.
