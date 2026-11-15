# Phase 7: AI-Assisted Chip Design Verification

**Status:** Planned — implement and validate before marking complete.

## Purpose
Develop practical competency in ai-assisted chip design verification through a verifiable build.

## Hardware
Laptop; optional FPGA board

## Implementation steps
1. Prepare hardware, drivers, versions, and a wiring or system diagram.
2. Create an agent that proposes RTL tests, runs Verilator/cocotb in sandbox, groups failures and summarizes coverage; require deterministic tests and human review.
3. Add unit/integration tests and capture baseline measurements.
4. Repeat the experiment, log failures and limitations, and document exact reproduction commands.
5. Publish a short demonstration only after validating the results.

## Software stack and tools
Python, LangGraph, FastAPI, SystemVerilog, cocotb, Verilator, React

## Required deliverables
Bug-seeded RTL benchmark, reproducible regressions, pass/fail evidence, coverage report

## Safety and accuracy
LLM suggestions are not verification proof.

## Completion checklist
- [ ] Hardware or simulation environment documented
- [ ] Source code and setup commands committed
- [ ] Automated tests pass
- [ ] Quantitative evidence attached
- [ ] Security and safety constraints reviewed
- [ ] README and demonstration updated
