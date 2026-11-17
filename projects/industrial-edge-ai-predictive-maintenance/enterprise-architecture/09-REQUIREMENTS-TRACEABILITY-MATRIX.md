# EA-09 — Requirements Traceability and Verification Matrix

**Status:** Architecture proposal. Requirements need sponsor and engineering review; verification results not yet available.

## Traceability rules

Each requirement has a unique ID, source, owner, risk priority, architectural owner, test ID, acceptance criterion and evidence location. A document being written is not a test pass. Keep one canonical source of IDs across the project.

| ID | Priority | Stakeholder and need | Owner system | Design reference | Verification protocol / acceptance |
|---|---|---|---|---|---|
| FR-01 | Must | Operator registers controlled asset/device | Asset API | EA-01, EA-03 | VT-01: valid asset saved; unauthorized site refused |
| FR-02 | Must | Maintenance gets traceable measured readings | ESP32/edge | EA-03, EA-04 | VT-02: timestamp, unit, quality, device/firmware ID present |
| FR-03 | Must | Platform resists intermittent connectivity | Broker/gateway | EA-02, EA-03 | VT-03: disconnect, bounded queue, documented losses, duplicates deduped |
| FR-04 | Must | Analyst can distinguish measured, replayed and simulated data | Ingest/UI | EA-03 | VT-04: provenance immutable and visible on API, charts and exports |
| FR-05 | Must | Analyst understands detector score and limits | ONNX pipeline | EA-04 | VT-05: baseline and held-out evaluation with versioned artifacts |
| FR-06 | Must | Operator sees actionable, nonduplicated incidents | Incident API | EA-03 | VT-06: replay does not create duplicate incidents |
| FR-07 | Should | Technician sees SOP-cited advisory guidance | RAG service | EA-04, EA-05 | VT-07: missing citation -> abstain; injected SOP cannot invoke tools |
| FR-08 | Must | Approver authorizes a versioned work order | Workflow API | EA-03, EA-05 | VT-08: rejected self-approval and stale approvals |
| FR-09 | Must | Security team can reconstruct decisions | Audit | EA-05, EA-11 | VT-09: immutable sequence + actor + source and version |
| FR-10 | Must | Technician can stop the lab motor independently | Physical circuit | EA-05, hardware guide | VT-10: qualified electrical review and disconnect verification BEFORE energization |
| NFR-01 | Must | Least-privilege device transport | MQTT | EA-05 | VT-11: unrelated topic publish rejected |
| NFR-02 | Must | Data loss is detectable | Gateway | EA-03, EA-06 | VT-12: dropped-window counters, stale-state displayed |
| NFR-03 | Should | Recover records and model deployment | Ops | EA-06 | VT-13: documented clean-environment restore drill |
| NFR-04 | Must | User and asset permissions enforced | API | EA-05 | VT-14: cross-site and cross-tenant access denied |
| NFR-05 | Must | Model change is reversible | MLOps | EA-04, EA-06 | VT-15: rollback of compatible model/scaler/threshold bundle |
| NFR-06 | Should | Usable operator interface | UI | EA-06 | VT-16: keyboard, contrast, error and stale-status checks |

## Acceptance format

`Requirement ID | Test ID | Environment | Date | Commit SHA | Dataset provenance | Expected | Observed | Reviewer | Decision | Evidence URL`

**Coverage policy:** no Must requirement can be marked accepted without at least one tested acceptance case; safety and security Must requirements also need negative tests. A failed test stays visible with issue owner and corrective action.

## Open assumptions

Sample frequency, acceptable latency, fleet size, log retention, pilot site, uptime target, response times and operating budgets need stakeholder baselines; avoid numeric targets fabricated before measurement.
