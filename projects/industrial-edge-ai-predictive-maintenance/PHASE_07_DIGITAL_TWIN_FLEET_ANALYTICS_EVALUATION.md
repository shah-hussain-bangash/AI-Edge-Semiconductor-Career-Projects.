# Phase 07 — Industrial Digital Twin, Fleet Analytics & Predictive Maintenance Evaluation

**Project:** Industrial Edge AI Predictive Maintenance & Autonomous Operations Platform  
**Status:** Implementation blueprint, not completed experiments.  
**Prerequisites:** Phases 01–06 (hardware, MQTT, edge AI, incidents, production backend, RAG assistant).  
**Objective:** Create a simulation-backed multi-asset testing environment, fleet analytics, data/model drift monitoring, and a reproducible evaluation framework for reliability, safety and operational usefulness.

## 1. Real-world problem

A single guarded DC motor proves basic connectivity, not fleet readiness. Industrial systems must cope with different operating conditions, multiple assets, missing measurements, network partitions, sensor drift, changed equipment behavior and maintenance workflow load. This phase creates a **digital twin as an explicitly simplified software model**, not a physics-validated replica of a real factory.

**Primary outputs:** reproducible simulator, asset registry, fleet dashboards, scenario library, drift detector, evaluation harness, and signed-off benchmark report.

## 2. System architecture

```text
Real guarded motor test rig (ESP32 + sensors)
                |
           MQTT telemetry
                |
                +-----------------------------+
                                              |
Synthetic fleet simulator -> MQTT namespace -> validated ingest
  |                                           |
  +-> scenario labels and ground truth        v
                                    PostgreSQL / TimescaleDB
                                              |
                                  Edge inference + incident rules
                                              |
                                 Fleet analytics and drift monitor
                                              |
                                 Next.js dashboard + RAG copilot
                                              |
                                  Human-approved maintenance
                                              |
                                  Evaluation and audit reports
```

**Keep real and synthetic data distinguishable at every layer.** Synthetic telemetry must never be silently represented as measured industrial evidence.

## 3. Hardware and software requirements

| Component | Purpose | Needed |
|---|---|---|
| Phase 01 guarded low-voltage motor + ESP32/sensors | Physical reference data | Existing |
| Raspberry Pi 5 | Real edge telemetry and inference | Existing or equivalent |
| Development workstation (16GB+ RAM preferred) | Simulate assets and run evaluation | Yes |
| Local network / MQTT broker | Device and simulator transport | Yes |
| PostgreSQL + TimescaleDB | Time-series storage and analytics | Existing |
| FastAPI + Next.js | Fleet APIs and dashboards | Existing |
| Python, NumPy, SciPy, pandas | Simulation and feature computation | Yes |
| pytest + Locust or k6 | Automated correctness/load testing | Yes |
| Prometheus + Grafana | Operational and drift monitoring | Recommended |
| Optional Jetson | Compare hardware inference deployments | Later |

A GPU is not required for the initial simulator. Use a laptop instead of extra physical motors.

## 4. Define the digital twin correctly

A **digital twin** in this project is a versioned, stateful approximation of motor operating conditions and sensor response. It can generate reproducible scenarios and help test software behavior, but it is not a validated physical failure predictor.

### Twin state
- Asset ID, asset type, rated operating range and model version.
- Simulated motor speed and normalized load.
- Simulated ambient and motor temperature.
- Vibration amplitude and noise characteristics.
- Current/voltage relationships within chosen illustrative bounds.
- Sensor quality, connectivity, maintenance state and timestamps.

### Fidelity levels
1. **Level 0 — replay:** Play back real Phase 01/02 recordings with original provenance.
2. **Level 1 — statistical twin:** Generate synthetic features conditioned on speed/load and calibrated to measured healthy distributions.
3. **Level 2 — simplified dynamics:** Add documented thermal inertia, motor-speed transitions and correlated noise.
4. **Level 3 — physics-based validated twin:** Future work requiring real equipment parameters, calibrated instruments and experimental validation.

Start at Levels 0–1. Never call the simulator physics-accurate without validation.

## 5. Suggested repository layout

```text
phase-07-digital-twin/
├── README.md
├── configs/
│   ├── fleet.yaml
│   ├── scenarios.yaml
│   └── evaluation.yaml
├── twin/
│   ├── asset_model.py
│   ├── signals.py
│   ├── scenario_engine.py
│   ├── mqtt_publisher.py
│   └── replay.py
├── analytics/
│   ├── fleet_metrics.py
│   ├── drift.py
│   ├── reliability.py
│   └── reporting.py
├── eval/
│   ├── run_scenarios.py
│   ├── score_detection.py
│   ├── score_workflows.py
│   └── make_report.py
├── tests/
│   ├── test_reproducibility.py
│   ├── test_synthetic_provenance.py
│   ├── test_drift.py
│   ├── test_alert_dedup.py
│   └── test_failure_recovery.py
├── dashboards/
│   └── fleet-requirements.md
├── results/
│   └── README.md
└── docs/
    ├── twin-assumptions.md
    ├── scenario-catalog.md
    ├── benchmark-methodology.md
    └── evaluation-report.md
```

## 6. Step-by-step implementation

### Step 1 — Establish a trusted baseline
1. Export real, valid healthy-motor recordings from Phases 01–03.
2. Document sampling rate, motor type, sensor positions, speed/load and recording session.
3. Compute feature distributions per operating state, with confidence intervals where justified.
4. Partition sessions into development and held-out validation sets.
5. Record source hashes, firmware version and calibration limitations.
6. Do not infer failure signatures from healthy-only measurements.

**Deliverable:** baseline data card and a reproducible preprocessing script.

### Step 2 — Build the fleet registry
1. Create 10 simulated assets for the first test, with stable asset IDs.
2. Assign device IDs, location labels, operating ranges and criticality.
3. Include `data_origin: "synthetic"` and `simulator_version` in each simulated message.
4. Keep physical asset records labeled `data_origin: "measured"`.
5. Apply server-side validation so synthetic devices cannot impersonate real devices.
6. Use separate broker credentials and topic namespace for the simulator, e.g. `industrial-sim/v1/devices/{id}/telemetry`.

**Deliverable:** fleet configuration and verified identity isolation.

### Step 3 — Implement the signal generator
1. Use a seeded random-number generator for deterministic experiments.
2. Generate baseline vibration features conditioned on speed and load.
3. Generate slowly changing temperature using a documented first-order thermal model.
4. Generate current correlated with simulated load, with bounded sensor noise.
5. Respect physical units and the supported bandwidth of the original sensors.
6. Emit versioned telemetry with simulation time, gateway time, sequence ID and scenario ID.
7. Validate ranges, continuity and repeatability with automated tests.

Illustrative simplified temperature dynamics:

```text
T_next = T_now + dt/tau * (T_target(load, ambient) - T_now) + noise
```

This equation is a **teaching approximation**. Fit `tau` and target temperature relationships to measured data if possible; otherwise clearly label parameters as hypothetical.

### Step 4 — Create controlled scenarios

| Scenario | Simulated change | Expected platform behavior |
|---|---|---|
| Healthy baseline | Normal speed/load variation | Low false-alert rate |
| Speed transition | Operating point changes | Avoid unsupported fault diagnosis |
| Sustained vibration shift | Increased vibration feature | Correlated anomaly/inspection alert if threshold met |
| Gradual temperature drift | Rising simulated temperature | Trend alert with supporting evidence |
| Electrical load shift | Current changes with load | Context-aware alerting |
| Sensor stuck value | Constant or implausible reading | Sensor-quality incident |
| Sensor dropout | Missing fields or invalid status | Mark unknown/stale, not healthy |
| Network outage | Delay and reconnect | Bounded buffering, replay and deduplication |
| Device reboot | New boot ID, sequence reset | No duplicate logical events |
| Duplicate MQTT delivery | Repeat identical message | One stored logical event |
| Model drift | Healthy distribution shifts | Drift signal and review, not auto-retraining |
| Database outage | Temporary persistence failure | Retry/recovery with measured loss policy |
| Approval bypass attempt | Unauthorized work-order action | Denied and audited |
| SOP revision mismatch | Old procedure retrieved | Rejected by provenance policy |

Do **not** describe a synthetic vibration shift as a confirmed bearing failure.

### Step 5 — Build a replay engine
1. Load recorded sensor sessions with original timestamps and source hashes.
2. Replay at 1x, 2x and controlled accelerated rates.
3. Preserve original event order and model-relevant timing.
4. Optionally inject known communication faults while retaining a ground-truth manifest.
5. Ensure replayed measured data is labeled `data_origin: "replay_measured"`, not `measured_live`.
6. Verify deterministic outputs when model, thresholds and software versions are fixed.

### Step 6 — Multi-asset fleet analytics
Implement backend endpoints and Next.js views for:
- Fleet counts by healthy/anomaly/sensor fault/offline.
- Asset-specific last-seen, sample completeness and freshness.
- Anomaly events per asset and operating hour.
- Alert acknowledgment and inspection workflow state.
- Time-series comparison across assets with aligned units.
- Model and firmware version distribution.
- Data origin: measured, replayed or synthetic.
- Per-asset and fleet-wide ingestion lag and event rates.

Suggested endpoints:

```text
GET /api/v1/fleet/overview
GET /api/v1/fleet/assets
GET /api/v1/fleet/assets/{id}/health
GET /api/v1/fleet/assets/{id}/metrics
GET /api/v1/fleet/anomalies
GET /api/v1/fleet/data-quality
GET /api/v1/fleet/model-versions
GET /api/v1/fleet/drift
GET /api/v1/fleet/evaluation-runs
```

Require asset-level authorization and bounded query ranges. Downsample large series server-side.

### Step 7 — Detect data and model drift

Track **data drift** separately from **model performance degradation**.

- Compare current feature distributions against a documented healthy baseline.
- Segment by operating state to avoid confusing normal speed changes with drift.
- Use PSI, KS statistic or distribution distances only with assumptions and sample-size checks.
- Track sensor clipping, missingness, calibration changes and firmware revisions.
- When ground-truth labels exist, separately monitor false alarms, recall and detection delay.
- Alert operators to investigate drift; **do not auto-retrain and auto-deploy** a safety-adjacent model.
- Require review, versioning, parity checks and rollback for model updates.

Example drift record:

```json
{
  "asset_id": "motor-sim-003",
  "feature": "vibration_rms_mps2",
  "baseline_version": "healthy-v1",
  "window": "24h",
  "drift_status": "review_required",
  "data_origin": "synthetic",
  "method": "distribution_comparison"
}
```

### Step 8 — Design rigorous evaluation splits
1. Split measured recordings by session, asset or time to avoid overlapping-window leakage.
2. Keep a frozen final test set.
3. Run controlled synthetic scenarios as **software stress tests**, not proof of field fault accuracy.
4. Compare threshold rules, IsolationForest and PyTorch/ONNX models on the same valid dataset.
5. Evaluate operating-state changes and sensor faults independently.
6. Repeat stochastic tests across documented seeds.
7. Record confidence intervals where sample sizes support them.
8. Document dataset gaps, especially absence of real failure labels.

### Step 9 — Measure predictive maintenance quality

| Metric | What it measures | Ground truth needed |
|---|---|---|
| Precision, recall, F1, PR-AUC | Anomaly/fault classification quality | Yes |
| False alerts per operating hour | Nuisance alerts during healthy sessions | Healthy labels |
| Detection delay | Time from known event onset to alert | Known event onset |
| Missed-event rate | Known deviations not detected | Known scenarios |
| Alert duplication rate | Repeated incidents for one logical event | Event IDs/scenario labels |
| Incident correlation accuracy | Correct grouping of related events | Labeled incidents |
| Data completeness | Received valid / expected telemetry | Sequence/time manifest |
| Model latency p50/p95/p99 | Inference timing | Timing measurements |
| End-to-end alert latency | Sensor observation to visible incident | Synchronized clocks |
| Work-order approval integrity | Unauthorized actions blocked | Authorization test cases |
| RAG citation correctness | SOP references support claims | Curated answer rubric |
| Drift detection delay | Time to detect injected distribution shift | Drift scenario onset |

**RUL/MTBF caveat:** Remaining useful life, mean time between failures and maintenance cost savings cannot be credibly estimated from short healthy-only lab recordings. Report them only when appropriate real histories and assumptions exist.

### Step 10 — Fault injection and reliability
1. Stop and restart MQTT broker; observe device reconnection and queue depth.
2. Delay or duplicate packets; verify idempotency.
3. Kill and restart ingestion worker; verify recovery.
4. Restart database and validate transaction/outbox behavior.
5. Disconnect edge-to-backend link; confirm edge inference continues where sensor-to-edge transport remains available.
6. Simulate invalid sensor data; verify sensor fault instead of healthy state.
7. Rotate/revoke a simulator credential; verify denial.
8. Attempt unauthorized work-order approval; verify backend rejection.
9. Test document index unavailability; ensure RAG abstains rather than invents citations.
10. Record recovery time, data loss and audit completeness.

### Step 11 — Load and soak testing
- Start with 10 simulated assets; expand to 50 and 100 if hardware capacity permits.
- Define each asset's realistic message rate before calculating aggregate load.
- Test ingestion throughput, DB query p95, dashboard update delay and storage growth.
- Use bounded queues and rate limits; record backpressure behavior.
- Run a supervised 24-hour soak test with reproducible configuration.
- Do not invent throughput or reliability results.

### Step 12 — Build the evaluation report
Include:
1. Executive summary and architecture.
2. Real vs synthetic dataset composition.
3. Hardware and software versions.
4. Digital twin assumptions and calibration limitations.
5. Scenario manifest, seeds and exact commands.
6. Model quality and false-alert metrics.
7. Inference and end-to-end latency distributions.
8. Drift-monitoring behavior.
9. Security, human approval and RAG tests.
10. Failure recovery and load testing.
11. Known limitations and next engineering actions.

## 7. Example fleet configuration

```yaml
simulation:
  seed: 42
  clock_mode: real_time
  duration_minutes: 30
  telemetry_interval_ms: 1000
  data_origin: synthetic
assets:
  - asset_id: motor-sim-001
    device_id: esp32-sim-001
    rated_voltage_v: 12
    speed_profile: steady
    load_profile: low
    scenario: healthy_baseline
  - asset_id: motor-sim-002
    device_id: esp32-sim-002
    rated_voltage_v: 12
    speed_profile: variable
    load_profile: medium
    scenario: sustained_vibration_shift
```

This is a configuration example, not a verified simulator output.

## 8. Acceptance criteria

- [ ] Simulator uses seeded, repeatable scenarios with documented assumptions.
- [ ] Measured, replayed and synthetic records are labeled and isolated.
- [ ] At least 10 simulated assets publish schema-valid telemetry.
- [ ] Fleet dashboard shows per-asset health, freshness and data origin.
- [ ] Incident engine deduplicates repeated events.
- [ ] Drift monitoring produces review signals with baseline provenance.
- [ ] Test split prevents session/window leakage.
- [ ] Metrics are calculated from actual test runs, not placeholders.
- [ ] Network, worker, database and authorization failures are tested.
- [ ] Work-order approvals remain human-controlled.
- [ ] Evaluation report includes limitations and reproducible commands.

## 9. Security and safety

- Separate simulator credentials and topics from physical devices.
- Prevent synthetic events from opening real production work orders.
- Enforce server-side asset permissions and workflow authorization.
- Do not connect simulator outputs to PLCs, actuators or safety systems.
- Keep manual emergency disconnect independent of software.
- Do not train a deployed model on synthetic failure labels without real-world validation.
- Protect equipment data, operator identity and proprietary procedures.
- Version and checksum datasets, models, scenario definitions and reports.

## 10. Definition of done and next phase

Phase 07 is complete when the system can replay real recordings and simulate a labeled multi-asset fleet, display trustworthy fleet analytics, detect selected distribution shifts, survive documented fault-injection tests, and generate an evidence-backed evaluation report. It must clearly separate **simulation performance** from **real industrial predictive-maintenance accuracy**.

**Next: Phase 08 — Security Hardening, MLOps, Production Deployment & Portfolio Demonstration.** Focus on deployment gates, backups, device/model lifecycle, disaster recovery, security validation, observability and a recruiter-ready technical demonstration.

> This document is an implementation guide only; it does not assert that a digital twin or any benchmarks have already been executed.
