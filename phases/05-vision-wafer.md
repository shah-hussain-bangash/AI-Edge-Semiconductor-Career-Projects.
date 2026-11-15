# Phase 5: Computer Vision and Semiconductor Quality AI

**Status:** Planned — implement and validate before marking complete.

## Purpose
Develop practical competency in computer vision and semiconductor quality ai through a verifiable build.

## Hardware
USB camera and edge computer; GPU workstation for wafer dataset

## Implementation steps
1. Prepare hardware, drivers, versions, and a wiring or system diagram.
2. Build controlled visual defect inspection; separately train wafer-map defect classifier using public data; evaluate class imbalance and drift.
3. Add unit/integration tests and capture baseline measurements.
4. Repeat the experiment, log failures and limitations, and document exact reproduction commands.
5. Publish a short demonstration only after validating the results.

## Software stack and tools
OpenCV, PyTorch, ONNX, CVAT, MLflow, FastAPI

## Required deliverables
Confusion matrices, edge FPS/latency, dataset provenance, failure examples

## Safety and accuracy
Do not claim access to actual fab production data.

## Completion checklist
- [ ] Hardware or simulation environment documented
- [ ] Source code and setup commands committed
- [ ] Automated tests pass
- [ ] Quantitative evidence attached
- [ ] Security and safety constraints reviewed
- [ ] README and demonstration updated
