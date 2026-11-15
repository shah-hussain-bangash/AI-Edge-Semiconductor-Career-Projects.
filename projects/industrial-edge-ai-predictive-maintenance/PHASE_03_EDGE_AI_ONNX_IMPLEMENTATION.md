# Phase 03 — Edge AI Model Development, ONNX Deployment and Benchmarking

**Project:** Industrial Edge AI Predictive Maintenance & Autonomous Operations Platform  
**Status:** Practical implementation plan — not a claim of completed training or hardware measurements.  
**Prerequisites:** Phase 01 sensor acquisition and Phase 02 MQTT telemetry ingestion.  
**Goal:** Train an anomaly detector on collected motor sensor data, validate it without data leakage, deploy inference on Raspberry Pi 5, and publish reproducible accuracy, latency, memory and reliability measurements.

## 1. Problem statement and scope

A stream of temperature, vibration and current measurements is not automatically a useful maintenance system. The edge processor must distinguish expected changes in speed/load from unusual conditions, remain functional without cloud connectivity, and communicate model uncertainty. **The first model detects deviations from observed normal behavior; it does not predict bearing failure dates or remaining useful life without validated failure/degradation labels.**

### Practical use cases
- Detect vibration signatures that differ from healthy operating baselines.
- Flag sustained temperature or electrical-load deviations.
- Reduce false alarms by conditioning on motor speed, load and ambient temperature when measured.
- Continue local scoring and event logging during internet outages.
- Compare CPU and hardware-accelerated inference where supported.

## 2. Hardware

| Component | Quantity | Role |
|---|---:|---|
| ESP32 + Phase 01 sensors | 1 set | Real physical measurements |
| ADXL345 | 1 | Vibration; introductory bandwidth only |
| DS18B20 | 1 | Temperature |
| INA219 | 1 | DC voltage/current within verified ratings |
| Raspberry Pi 5 (4GB or 8GB) | 1 | Main edge AI runtime |
| microSD/SSD, power supply, cooling | 1 set | Reliable Pi operation |
| Laptop/workstation | 1 | Dataset exploration, model training and reproducible experiments |
| Low-voltage motor test bench with guard | 1 | Safe baseline and operating-state data |
| NVIDIA Jetson Orin Nano Super | Optional | Later TensorRT/GPU benchmarking |
| Power meter / USB-C meter compatible with device | Optional | External system-power measurements |

**Start on your laptop if Raspberry Pi is not yet available.** Avoid claiming chip-acceleration results without compatible hardware.

## 3. End-to-end architecture

```text
Motor -> ADXL345 / DS18B20 / INA219 -> ESP32
        -> MQTT broker -> validated ingestion -> raw telemetry
                                           |
                                           v
                                dataset preparation / QA
                                           |
                               windowing + feature extraction
                                           |
                               train / validation / test
                                           |
                                  anomaly detection model
                                           |
                              ONNX export + parity checks
                                           |
                            Raspberry Pi 5 ONNX Runtime
                              |                  |
                      local event log      MQTT/API alerts
                              |                  |
                        backend and human-reviewed maintenance
```

Separate **training** (workstation, repeatable offline process) from **inference** (Pi, local and low latency). Preserve a versioned feature pipeline so the training and deployed models calculate exactly the same inputs.

## 4. Recommended software stack

| Layer | Technology | Why |
|---|---|---|
| Dataset processing | Python 3.11+, pandas, NumPy, PyArrow | Clean and version sensor data |
| Signal processing | SciPy | RMS, peaks, frequency features, filtering |
| Baseline models | scikit-learn IsolationForest, simple thresholds | Strong interpretable baselines |
| Neural models | PyTorch | Optional compact autoencoder or temporal model |
| Evaluation | scikit-learn metrics | Precision, recall, PR-AUC and false alarms |
| Export | torch.onnx, ONNX | Portable model artifact |
| Runtime | ONNX Runtime CPU | Raspberry Pi deployment |
| Acceleration | TensorRT on compatible Jetson | Optional, hardware-specific |
| Experiment tracking | MLflow or CSV + config | Compare experiments |
| Edge transport | MQTT client | Consume telemetry and publish scored events |
| Storage | SQLite initially; PostgreSQL later | Local events and auditability |
| Packaging | venv, requirements lock, systemd or Docker | Reproducible deployment |

**Important:** scikit-learn IsolationForest is not natively a PyTorch model. Use it as a baseline; for the ONNX deliverable choose a supported conversion path (e.g. skl2onnx with verified operator support) or train a small PyTorch model. Always validate runtime parity.

## 5. Suggested repository structure

```text
phase-03-edge-ai/
├── README.md
├── configs/
│   ├── dataset.yaml
│   ├── features.yaml
│   └── model.yaml
├── data/
│   ├── README.md
│   └── samples/                 # small, non-sensitive examples only
├── src/
│   ├── validate_data.py
│   ├── build_windows.py
│   ├── extract_features.py
│   ├── train_baseline.py
│   ├── train_autoencoder.py
│   ├── evaluate.py
│   ├── export_onnx.py
│   ├── check_onnx_parity.py
│   └── edge_infer.py
├── models/
│   └── README.md                # checksums, versions, provenance
├── tests/
│   ├── test_features.py
│   ├── test_split_leakage.py
│   ├── test_onnx_parity.py
│   └── test_alert_logic.py
├── benchmarks/
│   ├── benchmark_inference.py
│   └── results-template.csv
└── docs/
    ├── experiment-log.md
    ├── model-card.md
    └── test-report.md
```

## 6. Step-by-step practical implementation

### Step 1 — Collect and label real measurements

1. Export validated Phase 02 messages into an immutable dataset.
2. Record hardware part numbers, accelerometer range, mounting position, sampling frequency, motor speed/load and environmental context.
3. Capture repeated sessions for `motor_off`, `healthy_low_speed`, `healthy_high_speed` and safely controlled load changes.
4. Add `session_id`, `device_id`, `boot_id`, `gateway_utc`, `experiment_label` and `sensor_valid`.
5. Keep raw readings and derived features separate.
6. Label **controlled operating-state changes** as such; do not claim these are actual mechanical failures.

Example schema:

```text
session_id,device_id,gateway_utc,seq,ax_mps2,ay_mps2,az_mps2,
temperature_c,bus_voltage_v,current_ma,rpm,experiment_label,sensor_valid
```

If the Phase 02 stream contains only 1-second summary features rather than raw acceleration samples, you **cannot reconstruct FFT vibration spectra** from it. Capture higher-rate raw accelerometer windows locally or compute frequency-domain features at acquisition time.

### Step 2 — Data quality checks

- Check missing samples, duplicates, out-of-order sequence IDs and reboot boundaries.
- Check physical ranges, units, invalid DS18B20 readings, current monitor saturation and accelerometer clipping.
- Verify effective sample rate and sampling jitter, not just configured rate.
- Remove or flag windows with insufficient valid samples.
- Preserve a data-quality report rather than silently deleting problematic records.

### Step 3 — Build fixed windows

1. Use time-based windows, e.g. **2 seconds** of accelerometer data with 50% overlap for initial experiments.
2. Compute accelerometer vector magnitude, then windowed features.
3. Align slower temperature/current observations with each window, marking age and missingness.
4. Group windows by original session to avoid train/test leakage.
5. Save feature configuration (window size, sample rate, filters and units) alongside the model.

Suggested vibration features: RMS, standard deviation, peak-to-peak, crest factor, dominant frequency and band energies **only when sampling bandwidth and anti-aliasing support them**. Include temperature, current, voltage and RPM where available.

### Step 4 — Establish simple baselines

Implement:
- Threshold rules for sensor validity and sustained overheating.
- Robust per-operating-state z-score / median absolute deviation.
- IsolationForest using healthy training sessions only.

Measure false alarms on held-out healthy sessions. Avoid tuning thresholds against the final test set.

### Step 5 — Train compact PyTorch anomaly model

A small fully connected autoencoder is a practical first ONNX candidate:

```python
import torch
from torch import nn

class Autoencoder(nn.Module):
    def __init__(self, features: int):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(features, 32), nn.ReLU(),
            nn.Linear(32, 8), nn.ReLU()
        )
        self.decoder = nn.Sequential(
            nn.Linear(8, 32), nn.ReLU(),
            nn.Linear(32, features)
        )

    def forward(self, x):
        return self.decoder(self.encoder(x))
```

Training plan:
1. Fit preprocessing/scalers on **training sessions only**.
2. Train reconstruction model on healthy data only.
3. Use a validation set to choose model settings and anomaly threshold.
4. Evaluate on untouched test sessions.
5. Calculate reconstruction error per window; use threshold persistence (e.g. multiple consecutive abnormal windows) to reduce noisy alerts.
6. Record seed, package versions, dataset hash, feature schema and trained weights.

**Caution:** A reconstruction model can fail to detect unseen faults. A controlled load change is not proof of real fault detection. Use public labeled machine-condition datasets for supplementary fault-classification research, clearly separated from your physical prototype measurements.

### Step 6 — Evaluate without leakage

- Split **by recording session or motor**, never random overlapping windows from the same recording across train and test.
- Report confusion matrix, precision, recall, F1 and PR-AUC **only where meaningful ground-truth labels exist**.
- Report false alerts per hour on healthy sessions and detection delay for known controlled deviations.
- Compare thresholds, IsolationForest and autoencoder on the same held-out sessions.
- Test sensitivity to speed/load changes, ambient conditions and sensor dropout.
- Keep a model card with limitations, dataset coverage and unsuitable uses.

### Step 7 — Export model to ONNX

Example for a trained PyTorch autoencoder (adapt export API to the installed PyTorch version):

```python
import torch

model.eval()
example = torch.randn(1, feature_count, dtype=torch.float32)
torch.onnx.export(
    model,
    (example,),
    "models/autoencoder.onnx",
    input_names=["features"],
    output_names=["reconstruction"],
    opset_version=17,
    dynamic_axes={"features": {0: "batch"}, "reconstruction": {0: "batch"}}
)
```

Export the **scaler parameters, feature ordering and anomaly threshold** with the model. Test PyTorch vs ONNX outputs on the same inputs with a documented tolerance. Run ONNX checker and record artifact hashes.

### Step 8 — Deploy ONNX Runtime to Raspberry Pi

1. Install supported 64-bit Raspberry Pi OS and verify Python/CPU architecture.
2. Install a compatible ONNX Runtime package; record exact versions and installation method.
3. Copy the versioned ONNX model, scaler/feature schema and threshold.
4. Run a local inference smoke test on a known saved feature window.
5. Subscribe to Phase 02 telemetry; assemble valid windows or consume precomputed features.
6. Score windows locally and publish a **separate** `industrial/v1/devices/motor-001/edge-events` topic.
7. Store local alerts and queue for synchronization when upstream is unavailable.
8. Run the process under systemd or Docker with health checks and restart policy.
9. Prevent duplicate alert storms with persistence, hysteresis and cooldown.
10. Keep any maintenance action human-approved.

Example ONNX Runtime inference:

```python
import numpy as np
import onnxruntime as ort

session = ort.InferenceSession(
    "models/autoencoder.onnx",
    providers=["CPUExecutionProvider"]
)
features = np.asarray([[0.1, 0.2, 0.3]], dtype=np.float32)  # illustrative only
# Replace example with correctly ordered/scaled feature vector of actual model width.
# reconstructed = session.run(None, {"features": features})[0]
# anomaly_score = np.mean((features - reconstructed) ** 2, axis=1)
```

**Never** use a placeholder vector as a real model input; actual vector width, units and preprocessing must match the exported model.

### Step 9 — Benchmark edge inference

Use a fixed, documented test dataset and run enough iterations for stable estimates.

| Measurement | Definition |
|---|---|
| p50/p95/p99 latency | Distribution of per-window inference time, excluding/including preprocessing as separately reported |
| Throughput | Windows scored per second |
| CPU utilization | Process and device load |
| Memory | Resident memory and peak usage |
| End-to-end delay | Sensor acquisition to local alert |
| Model quality | Same held-out test set and threshold policy |
| Power (optional) | External measured device/system power, with measurement method |
| Reliability | Missed windows, restarts, queue depth and offline recovery |

Compare Pi CPU FP32 with a supported optimized/quantized runtime **only after** parity and model-quality checks. For Jetson, TensorRT requires compatible JetPack, ONNX operators and build settings; do not assume the same ONNX Runtime execution provider is available on every device.

### Step 10 — Controlled failure experiments

- Disconnect Wi-Fi: confirm local inference continues on already-arriving or locally available data; document what stops if ESP32-to-Pi transport itself is disrupted.
- Restart inference process: confirm clean model reload and state handling.
- Corrupt model artifact: reject it via checksum/version validation.
- Feed invalid/missing sensors: return `sensor_fault` instead of a misleading healthy classification.
- Change motor speed: quantify false alarms due to operating-state shift.
- Run a supervised 24-hour soak test: log errors, memory, throughput and dropped windows.

## 7. Suggested edge event payload

```json
{
  "schema_version": 1,
  "device_id": "motor-001",
  "model_version": "ae-v0.1.0",
  "window_end_utc": "2026-11-15T12:00:00Z",
  "anomaly_score": 0.081,
  "threshold": 0.06,
  "status": "anomaly",
  "quality": "valid",
  "evidence": ["elevated vibration feature"]
}
```

Values above are **illustrative only**. Do not generate specific causal fault diagnoses from a generic anomaly score.

## 8. Security and operational safeguards

- Validate MQTT inputs and constrain payload size.
- Authenticate edge publisher and apply topic-specific ACLs.
- Check model artifact checksum before loading; never execute untrusted model files.
- Keep credentials outside Git and use least privilege.
- Version features, scaler, threshold, ONNX file and firmware together.
- Log inference failures, drift signals and alert decisions.
- Treat AI explanations as suggestions, not verified mechanical diagnoses.
- Never allow model output to bypass manual safety controls or human approval.

## 9. GitHub completion checklist

- [ ] Real dataset provenance, hardware details and acquisition settings documented
- [ ] Reproducible feature extraction with unit tests
- [ ] Session-disjoint train/validation/test split
- [ ] Simple threshold + IsolationForest baselines
- [ ] Trained compact PyTorch model and evaluation report
- [ ] ONNX export, checker and parity tests
- [ ] Raspberry Pi inference service and restart behavior
- [ ] Local anomaly events with model version and evidence
- [ ] Reproducible latency, throughput and memory benchmarks
- [ ] Offline/restart/invalid-sensor tests
- [ ] Model card documenting limitations
- [ ] Short demo video of sensor -> edge inference -> alert

## 10. Definition of done

Phase 03 is complete when **real sensor data** can be processed into validated windows, a model trained without session leakage can score those windows locally on Raspberry Pi, ONNX outputs match the reference model within a documented tolerance, and measured quality and performance are published with reproducible test commands.

**Next phase:** Phase 04 — Industrial Predictive Maintenance, alert correlation, equipment health scoring and human-approved maintenance workflows.

> This is a planned implementation guide. No model, benchmark or hardware experiment is represented as completed.
