# Phase 06 — Agentic AI Maintenance Assistant, RAG Knowledge Base & Controlled Automation

**Project:** Industrial Edge AI Predictive Maintenance & Autonomous Operations Platform  
**Status:** Practical engineering blueprint; no deployed agent, validated RAG system, or completed tests are claimed.  
**Prerequisites:** Phase 01 sensor acquisition, Phase 02 MQTT, Phase 03 ONNX edge inference, Phase 04 incident workflows, Phase 05 backend/database/dashboard.  
**Goal:** Create a maintenance copilot that reads authorized asset evidence, retrieves versioned maintenance procedures, drafts grounded inspection recommendations, and proposes—but never autonomously authorizes—work orders.

## 1. Practical problem and scope

Technicians must correlate time-series data, anomaly events, maintenance history and equipment-specific procedures. A generic chatbot may hallucinate fault causes, cite the wrong manual, or suggest unsafe actions. Phase 06 builds a **retrieval-grounded, tool-restricted assistant** with verifiable citations, deterministic approval boundaries and a measured evaluation suite.

**Allowed:** Summarize incidents; explain observed measurements; retrieve approved SOPs; draft inspection checklists; propose a work order for human review; compare before/after measurements.

**Not allowed:** Operate motors, change PLC settings, bypass safety controls, approve its own work order, silently modify maintenance records, or assert a root cause unsupported by evidence.

## 2. End-to-end architecture

```text
ESP32 sensors -> MQTT -> Raspberry Pi ONNX anomaly events
                                 |
                    FastAPI + PostgreSQL/TimescaleDB
                       |                   |
                  Incident API       Asset telemetry API
                       |                   |
                       +--------+----------+
                                |
                      LangGraph agent runtime
                       |         |         |
                  Read-only   RAG search  Draft proposal
                  tools       approved    (no execution)
                              SOPs
                       |         |         |
                       +---- Evidence check-+
                                |
                   Structured recommendation
                                |
                       Human review UI
                                |
                     Approver authorization
                                |
               Deterministic work-order service
                                |
                         Append-only audit
```

The agent uses **server-side tool adapters** with explicit per-user permissions; it never receives raw database credentials or direct network access to industrial control devices.

## 3. Hardware and software

| Component | Purpose | Requirement |
|---|---|---|
| ESP32 + Phase 01 sensors | Real-world asset observations | Existing test rig |
| Raspberry Pi 5 | Edge inference and local event production | Existing edge node |
| Development workstation | RAG indexing, API and evaluation | Required |
| PostgreSQL + pgvector | SOP chunks, embeddings and metadata | Recommended |
| FastAPI + SQLAlchemy | Authenticated read-only evidence tools and proposal APIs | Required |
| LangGraph | Explicit agent workflow, state and guarded tool transitions | Recommended |
| Embedding model | Index and query SOP passages | Required for vector retrieval |
| LLM provider or local model | Draft evidence-based explanations | Select based on privacy, latency and cost |
| Next.js | Human review and approval UI | Existing Phase 05 dashboard |
| Optional GPU/Jetson | Local language model acceleration | Later; not needed for first version |

**Offline behavior:** The Pi anomaly detector can continue independently; the maintenance copilot may be unavailable when its LLM or document index is unavailable. Clearly show this state rather than implying full offline AI.

## 4. Repository layout

```text
phase-06-agentic-maintenance/
├── README.md
├── api/
│   ├── app/agent/graph.py
│   ├── app/agent/state.py
│   ├── app/agent/policies.py
│   ├── app/tools/asset_read.py
│   ├── app/tools/incident_read.py
│   ├── app/tools/sop_search.py
│   ├── app/services/recommendations.py
│   └── app/schemas/recommendation.py
├── rag/
│   ├── ingest.py
│   ├── chunk.py
│   ├── index.py
│   ├── retrieve.py
│   └── manifests/
├── eval/
│   ├── cases.jsonl
│   ├── run_eval.py
│   └── rubric.md
├── tests/
│   ├── test_authorization.py
│   ├── test_prompt_injection.py
│   ├── test_citation_grounding.py
│   ├── test_work_order_approval.py
│   └── test_agent_fail_closed.py
├── docs/
│   ├── threat-model.md
│   ├── document-provenance.md
│   ├── evaluation-report.md
│   └── demo-script.md
└── infra/
    └── compose.yaml
```

## 5. Step-by-step implementation

### Step 1 — Define use cases and trust boundaries
1. Write five initial user stories: explain an alert, compare trends, find the relevant SOP, draft an inspection checklist, propose a work order.
2. Define operator, technician, approver and auditor permissions.
3. Classify data as measured telemetry, model output, maintenance history, approved SOP, or AI-generated suggestion.
4. Ensure user/asset authorization is checked **in every tool**, not only in the chat interface.
5. Record prohibited actions and require a deterministic policy gate for every write operation.

### Step 2 — Build an approved maintenance knowledge base
1. Obtain rights to use applicable motor, sensor and test-bench manuals.
2. Maintain a manifest for each document: document ID, title, manufacturer, asset applicability, revision, approval status, effective date, source URL/path and checksum.
3. Parse PDFs and documents while preserving section/page references, tables and safety warnings.
4. Remove duplicates and superseded revisions from the active retrieval set, while preserving audit history.
5. Separate unapproved web content and user comments from authoritative SOPs.
6. Never upload proprietary industrial manuals to public GitHub without permission.

Example metadata:

```json
{
  "document_id": "sop-motor-inspection-001",
  "revision": "1.0",
  "status": "approved",
  "asset_type": "low-voltage-dc-motor",
  "section": "3.2",
  "page": 7,
  "checksum_sha256": "<calculated-at-ingestion>"
}
```

### Step 3 — Chunk, embed and index
1. Chunk by headings and procedure boundaries, keeping warnings with related steps.
2. Store original passage text and provenance separately from embeddings.
3. Generate embeddings with a pinned model/version.
4. Use pgvector for semantic search plus PostgreSQL full-text search for exact terms and part numbers.
5. Filter retrieval by asset type, document approval status, effective revision and user access.
6. Reindex changed documents and verify old revisions no longer appear in active results.
7. Benchmark retrieval before connecting an LLM.

Suggested tables: `maintenance_documents`, `document_chunks`, `document_embeddings`, `document_access_policies`, `ingestion_runs`. Keep an auditable relationship between chunk, source document and revision.

### Step 4 — Implement least-privilege evidence tools
Create narrow, typed tools:
- `get_asset_health(asset_id, time_range)` — returns validated summaries and freshness.
- `get_incident(incident_id)` — returns authorized incident history and model version.
- `get_telemetry_summary(asset_id, start, end)` — returns bounded, downsampled measurements.
- `search_approved_sops(asset_id, query)` — returns citations and relevant approved passages.
- `get_maintenance_history(asset_id)` — returns permitted previous inspections.
- `draft_work_order(incident_id, recommendation)` — **proposal only**, no approval or execution.

Enforce time-range caps, result limits, query budgets, per-asset authorization, logging and rate limits. Return explicit stale/missing-data flags. No generic SQL, shell, browser, or unrestricted HTTP tool is given to the agent.

### Step 5 — Build a deterministic LangGraph workflow

```text
START
  |
  v
Authenticate + authorize
  |
  v
Classify user intent
  |
  v
Fetch incident + validated telemetry
  |
  v
Retrieve approved SOPs
  |
  v
Evidence sufficiency check
  |                         |
sufficient                insufficient
  |                         |
  v                         v
Draft structured answer    Ask for data / abstain
  |
  v
Citation + safety policy checks
  |
  v
Display recommendation / draft proposal
  |
  v
END (human approval handled outside agent)
```

Agent state should contain `request_id`, `user_id`, `authorized_asset_ids`, `incident_id`, evidence references, retrieved document revisions, policy flags and structured output. Avoid exposing hidden credentials in prompts or tool results.

### Step 6 — Structured recommendation contract

```json
{
  "incident_id": "inc-demo-001",
  "classification": "inspection_recommended",
  "observations": ["Vibration feature increased relative to recorded baseline"],
  "possible_explanations": ["Sensor mounting changed", "Operating state differs"],
  "recommended_checks": ["Verify sensor attachment", "Review motor speed and current"],
  "citations": [
    {"document_id": "sop-motor-inspection-001", "revision": "1.0", "section": "3.2"}
  ],
  "uncertainty": "No verified fault label or teardown evidence is available",
  "requires_human_approval": true
}
```

**Illustrative output only.** Validate against a strict Pydantic schema. Reject uncited safety-critical claims and references to documents not actually retrieved. Do not equate an anomaly score with a mechanical fault diagnosis.

### Step 7 — Prompt-injection and hallucination defenses
1. Treat all retrieved text, telemetry fields and incident comments as **untrusted data**.
2. Clearly separate instructions from quoted source passages.
3. Do not let document text request new tools, permissions, hidden prompts or credential disclosure.
4. Enforce tool permissions in code; prompts are not an authorization boundary.
5. Use allowlisted proposal types and deterministic schema checks.
6. Reject unsafe instructions, unsupported fault assertions and invented citations.
7. Record adversarial test cases: “ignore previous instructions,” fake SOP revisions, malicious document metadata and cross-asset data requests.
8. Fail closed on unavailable policy checks or document-index errors.

### Step 8 — Human review and work-order integration
1. Agent creates a **draft recommendation** with citations and evidence IDs.
2. Next.js UI shows source excerpts, timestamps, data quality and model version.
3. Authorized technician may edit or reject the draft.
4. Separate authorized approver explicitly approves a proposed inspection.
5. FastAPI work-order service validates role, incident state and idempotency key.
6. Persist approval decision, actor, time, reason, final recommendation and source versions.
7. Do not expose a direct actuator command or safety bypass API.

### Step 9 — Build a practical evaluation set
Create at least 30–50 curated cases spanning:
- Normal and anomalous motor observations.
- Sensor disconnect and stale telemetry.
- Missing or contradictory SOPs.
- Wrong asset/manual revision.
- Unsupported root-cause claims.
- Permission and cross-asset access attempts.
- Prompt injection in retrieved documents.
- Approval bypass attempts.
- Long incident timelines and conflicting measurements.
- Model output changes across versions.

Use **synthetic** cases for controlled failure scenarios, and clearly distinguish them from real motor recordings.

### Step 10 — Measure RAG and agent quality

| Metric | Meaning |
|---|---|
| Retrieval recall@k | Correct SOP passage appears in top-k for labeled queries |
| Citation precision | Returned citations actually support stated claims |
| Groundedness | Assertions trace to retrieved evidence or measured telemetry |
| Abstention quality | Assistant declines unsupported diagnoses |
| Unauthorized tool calls | Must be blocked by server-side policy |
| Approval bypass success | Must remain zero in tested cases |
| Task completion | Correctly drafts permitted recommendations |
| p50/p95 latency | End-to-end response time |
| Cost per request | Token and infrastructure cost |
| Document freshness | Active revisions used rather than superseded documents |

Publish the test cases, evaluation rubric, actual results and known failure modes. Do not invent accuracy or safety metrics.

### Step 11 — Observability and operations
- Log request ID, agent graph version, tool names, latency, source IDs and outcome.
- Redact credentials and sensitive document content from traces.
- Track tool errors, retrieval misses, schema validation failures, abstentions and approval requests.
- Version prompts, embedding model, LLM model, SOP index and policy rules.
- Apply budgets and timeouts to limit runaway agent loops.
- Require review before enabling any new tool capability.
- Test restart/recovery and document the behavior when LLM provider or vector index is offline.

### Step 12 — End-to-end demo
1. Run a guarded low-voltage motor and collect real sensor measurements.
2. Generate a valid edge anomaly event or replay a **clearly labeled synthetic** scenario.
3. Open the incident in the dashboard.
4. Ask the assistant: “What measurements changed and which inspection procedure applies?”
5. Show the exact source passages and uncertainty statement.
6. Generate an inspection work-order **draft**.
7. Log in as a separate approver and approve/reject it.
8. Show the audit trail and demonstrate that the agent cannot approve or actuate anything.
9. Inject a malicious document instruction and verify policy enforcement.
10. Export the evaluation and demo logs.

## 6. Suggested API endpoints

```text
POST /api/v1/assistant/ask              (authorized user)
POST /api/v1/assistant/recommendations  (draft only)
GET  /api/v1/knowledge/documents        (authorized reader)
POST /api/v1/knowledge/ingest           (knowledge admin only)
GET  /api/v1/recommendations/{id}       (authorized user)
POST /api/v1/recommendations/{id}/review (technician+)
POST /api/v1/work-orders/{id}/approve   (approver only, deterministic backend)
GET  /api/v1/audit/assistant            (auditor/admin only)
```

Do not allow the agent to call the approval endpoint with service privileges. The backend must authenticate the **actual human approver**.

## 7. Tests and release gates

| Test | Expected result |
|---|---|
| Correct SOP revision | Only applicable approved version cited |
| Missing source | Assistant abstains or asks for evidence |
| Invalid citation | Recommendation rejected or marked unsupported |
| Cross-asset request | Tool denies unauthorized access |
| Prompt injection in PDF | No new privileges or forbidden tool execution |
| Fake “approve now” instruction | No work order approval without human action |
| Model score without ground truth | No definitive fault diagnosis |
| Document index outage | Graceful degraded response, no fabricated sources |
| Duplicate proposal submission | One logical draft/work order |
| User role change | Permissions rechecked at action time |
| Source revision change | Recommendation provenance remains auditable |
| LLM timeout | Safe error, bounded retry, no hidden side effect |

## 8. Security, privacy and safety checklist

- [ ] Maintenance manuals licensed/authorized and not publicly exposed
- [ ] Approved document manifest with revisions and checksums
- [ ] User and asset permissions checked inside every tool
- [ ] No unrestricted SQL, shell, internet or industrial control tools
- [ ] Strict structured-output validation
- [ ] Citation support checked before display
- [ ] Prompt-injection test suite and policy enforcement
- [ ] Human approval separated from agent execution
- [ ] Complete audit of drafts, edits, approvals and source versions
- [ ] No autonomous safety-critical actuation
- [ ] Measured evaluation with limitations and abstentions
- [ ] Secure secret storage, logging and retention policies

## 9. Definition of done

Phase 06 is complete when an authenticated user can ask about a real or clearly labeled synthetic incident, the assistant retrieves the **correct authorized SOP revision**, explains observed evidence with verifiable citations, drafts an inspection proposal, and a separate human approval workflow can approve or reject it. Security tests must show that document instructions and agent output cannot bypass backend permissions.

**Next: Phase 07 — Industrial Digital Twin, Fleet Analytics & Predictive Maintenance Evaluation.** Build simulation-backed scenarios, multi-asset comparisons, drift monitoring and a rigorous benchmark/evaluation package.

> The content above is a design and implementation guide, not proof of a deployed or certified system.
