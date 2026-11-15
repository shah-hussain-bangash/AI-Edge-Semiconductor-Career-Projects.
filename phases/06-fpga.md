# Phase 6: FPGA and Digital Chip Engineering

**Status:** Planned — implement and validate before marking complete.

## Purpose
Develop practical competency in fpga and digital chip engineering through a verifiable build.

## Hardware
FPGA dev board optional initially; simulation-capable laptop

## Implementation steps
1. Prepare hardware, drivers, versions, and a wiring or system diagram.
2. Write and simulate fixed-point MAC and small matrix multiplier; add assertions; synthesize on board; compare cycles, LUTs, DSPs and timing.
3. Add unit/integration tests and capture baseline measurements.
4. Repeat the experiment, log failures and limitations, and document exact reproduction commands.
5. Publish a short demonstration only after validating the results.

## Software stack and tools
Verilog/SystemVerilog, Verilator, cocotb, GTKWave, Vivado or Quartus

## Required deliverables
RTL, testbench, waveform, synthesis/timing reports, demo

## Safety and accuracy
Report simulated vs FPGA-measured results separately.

## Completion checklist
- [ ] Hardware or simulation environment documented
- [ ] Source code and setup commands committed
- [ ] Automated tests pass
- [ ] Quantitative evidence attached
- [ ] Security and safety constraints reviewed
- [ ] README and demonstration updated
