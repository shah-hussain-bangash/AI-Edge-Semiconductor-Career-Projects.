# EA-13 — Edge AI, RAG and Agent Evaluation Protocol

**Status:** Prespecified evaluation **plan**; no performance results asserted.

## 1. Evaluation questions

1. Can the acquisition pipeline detect missing, malformed and stale sensor values?
2. Does a simple statistical baseline perform as well as or better than an ONNX detector?
3. Does the model detect controlled, **non-hazardous** changes without unacceptable false alerts?
4. Does Pi 5 inference fit actual latency and resource budgets?
5. Can RAG return correct approved SOP citations and safely abstain?
6. Can any prompt, SOP or agent tool bypass human approval or physical safety boundaries?

## 2. Dataset provenance

Provenance classes: `real_measured_lab`, `synthetic`, `replayed`. Store recording ID, time/session, device and firmware ID, sensor placement, motor/mount configuration, calibration status, consent/permission, feature schema and SHA-256. A synthetic perturbation is **not** a demonstrated actual motor fault.

## 3. Split strategy

Partition by independent recording session or physical setup before feature-window generation, preventing adjacent-window leakage. Keep a held-out test set unseen during tuning. Report label definitions, class distribution, uncertain labels and the number of independent sessions. No numerical accuracy claim is acceptable absent ground truth and confusion-matrix evidence.

## 4. Baselines and candidate models

- Baseline A: sensor quality and simple threshold rules.
- Baseline B: rolling median/MAD or isolation forest.
- Candidate C: small ONNX-exportable anomaly detector, chosen only if it improves measured trade-offs.

Measure precision/recall/F1 or PR-AUC where labels are defensible; false alerts per hour, detection delay, calibration effects, and missingness behavior. Report uncertainty and per-session breakdown; avoid presenting near-duplicate windows as independent experiments.

## 5. Edge benchmark protocol

Record actual Pi board revision, OS, CPU governor, cooling, model and preprocessor hashes, batch/window size, CPU/RAM/temperature, idle and loaded timings (median/p95/p99), warm vs cold startup, MQTT-to-incident processing delay, wattage if accurately metered. Report replication count and raw measurement logs.

## 6. RAG evaluation

Build independent question sets about approved SOP content, unsupported questions, stale revisions, conflicting procedures and embedded malicious instructions. Metrics: citation correctness, groundedness, retrieval recall@k where labeled, abstention correctness, dangerous action rejection, ACL enforcement, token cost and latency. Review failure cases manually; do not use only model self-grading.

## 7. Agent/tool security evaluation

Test forbidden equipment control tool requests, unauthorized tenant reads, data exfiltration prompts, poisoned retrieval results, double approvals, stale work order revisions and tool invocation retries. Confirm that policy engine, not LLM text, makes authorization decisions. Maintain an immutable test record per scenario.

## 8. Release gate

Candidate -> tested -> security reviewed -> staged -> independent authorized release. Bundle ONNX + preprocessing + feature schema + threshold + evaluation manifest. Failure to meet any Must safety/security requirement blocks promotion. Measured targets must be agreed before interpreting tests.

## 9. Evaluation record schema

`case_id, dataset_hash, provenance, model_hash, firmware_hash, test_time, environment, expected_behavior, actual_behavior, metric, pass_fail, reviewer, evidence_url, limitations`.
