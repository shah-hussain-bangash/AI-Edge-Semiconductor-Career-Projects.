# EA-07 — Architecture Decision Record (ADR) Register

All decisions below are **proposed**; they have not been formally approved.

## ADR-001 — Raspberry Pi 5 as first edge gateway

**Context:** Need low-cost Linux inference and MQTT validation.
**Options:** Raspberry Pi 5, cloud-only, Jetson.
**Decision proposed:** Pi 5 for first prototype; upgrade only if measured throughput/latency requires.
**Consequences:** simple setup and low cost; limited compute and single-node resilience.
**Revisit trigger:** sustained inference SLO misses or memory/thermal constraints.

## ADR-002 — MQTT for field-to-edge telemetry

**Options:** MQTT, HTTPS polling, direct serial.
**Decision proposed:** private authenticated MQTT with per-device topics, QoS1 and deduplication.
**Consequences:** retries and asynchronous flow; duplicate/out-of-order processing requires design.
**Revisit trigger:** need for hard real-time control (not supported in current scope).

## ADR-003 — ONNX first for local anomaly inference

**Options:** threshold rules, scikit-learn pipeline, ONNX model, hosted LLM.
**Decision proposed:** rules as baseline, ONNX only after measured benefit.
**Consequences:** portable inference; model-feature bundling and parity tests needed.
**Revisit trigger:** ONNX adds no demonstrated benefit.

## ADR-004 — PostgreSQL plus TimescaleDB

**Options:** PostgreSQL only, TimescaleDB, cloud time-series database.
**Decision proposed:** PostgreSQL for business workflow records; TimescaleDB extension for telemetry where deployment environment supports it.
**Consequences:** one persistence family; time-series tuning/retention are operational responsibilities.
**Revisit trigger:** extension incompatibility or retention/volume limits.

## ADR-005 — Advisory-only generative AI

**Options:** AI direct execution, human-in-loop proposals, no LLM.
**Decision proposed:** RAG provides read-only SOP-grounded suggestions, never direct equipment actuation.
**Consequences:** explicit human effort but reduced blast radius and improved accountability.
**Revisit trigger:** any actuation request requires separate safety engineering; not a routine feature toggle.

## ADR-006 — Separate physical safety from cloud controls

**Decision proposed:** independent rated motor switch, fuse, guard and electrical review. No safety assurance may depend on Wi-Fi, broker, dashboard or agent.
**Consequences:** more deliberate bench setup; prevents architecture from treating software controls as an emergency stop.
**Revisit trigger:** none within this prototype.

## ADR-007 — Version-bound independent human approval

**Decision proposed:** all work orders require server-side permissions and approval of an immutable version; deny self-approval when policy requires segregation.
**Consequences:** auditability and concurrency control; additional service complexity.
**Revisit trigger:** proven workflow changes with documented risk review.

## ADR-008 — Strict provenance for portfolio evidence

**Decision proposed:** clearly distinguish measured, synthetic, replayed, implemented, tested and aspirational systems.
**Consequences:** narrower claims but high technical credibility and reproducibility.
**Revisit trigger:** evidence allows advancing status with concrete commit/test/deployment records.

## ADR template for additions

ID; status; owner; date; decision context; driving requirements; options with costs/risks; selected approach; alternatives rejected; consequences; acceptance tests; reversal trigger; links to evidence. A change to an accepted decision needs a superseding ADR instead of silently rewriting history.
