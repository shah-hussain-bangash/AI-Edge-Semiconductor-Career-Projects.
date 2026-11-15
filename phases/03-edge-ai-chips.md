# Phase 3: Edge AI and Chip Optimization

**Status:** Planned — implement and validate before marking complete.

## Purpose
Develop practical competency in edge ai and chip optimization through a verifiable build.

## Hardware
Raspberry Pi 5 or Jetson; optional NPU accelerator

## Implementation steps
1. Prepare hardware, drivers, versions, and a wiring or system diagram.
2. Train anomaly model; export ONNX; compare CPU vs accelerator, FP32 vs quantized; measure p50/p95 latency, throughput, memory, accuracy and watts.
3. Add unit/integration tests and capture baseline measurements.
4. Repeat the experiment, log failures and limitations, and document exact reproduction commands.
5. Publish a short demonstration only after validating the results.

## Software stack and tools
PyTorch, ONNX Runtime, TensorRT when compatible, OpenVINO, Python

## Required deliverables
Benchmark scripts, device specs, reproducible results CSV, accuracy tradeoff chart

## Safety and accuracy
Compare identical datasets and workloads; don't invent hardware results.

## Completion checklist
- [ ] Hardware or simulation environment documented
- [ ] Source code and setup commands committed
- [ ] Automated tests pass
- [ ] Quantitative evidence attached
- [ ] Security and safety constraints reviewed
- [ ] README and demonstration updated
