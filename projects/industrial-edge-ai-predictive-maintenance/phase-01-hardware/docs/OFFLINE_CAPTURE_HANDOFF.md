# Offline capture handoff — awaiting complete hardware receipt

Status reviewed 24 November 2026: the owner reports partial receipt of the order; the complete set is still pending. Received product identities, quantities and exact variants have not been verified in this session. Connection remains deferred until the complete set is available and the bench is ready and reviewed. The existing 30-product selection and physical connection pack are unchanged. No device has been connected, enrolled, calibrated or accepted by this work. Do not mark individual receipt-worksheet rows received or verified from this aggregate report alone.

## What is prepared

`scripts/prepare_capture.py` converts an existing V1 USB serial capture CSV into an offline candidate V2 evidence folder. It opens no serial port, makes no network requests, sends no equipment commands and writes no dashboard database. Python 3.12 or later is sufficient; runtime dependencies use the standard library.

The authenticated dashboard continues to accept synthetic observations only. These candidate records are not an ingestion feature or a production release. Measured or replayed records stay offline. Do not relabel them as synthetic to bypass the dashboard boundary.

## Available now: synthetic demonstration

Run from `phase-01-hardware` in PowerShell. Choose an output directory that does not already exist:

```powershell
python scripts/prepare_capture.py prepare --input examples/offline-capture/synthetic.capture.csv --attachment examples/offline-capture/synthetic.attachment.json --output evidence/synthetic-handoff-001
python scripts/prepare_capture.py verify evidence/synthetic-handoff-001
```

The example contains no readings from physical equipment. The attachment says `NOT-CONNECTED`. Neither command connects hardware. A successful preparation reports two accepted rows and zero quarantined rows, with physical verification and ingestion readiness false.

Arrival ZIP version two includes the summary tool, its tests and the H1 checklist. The reviewed `dashboard/verify_arrival_pack.py` supports exact version-one and version-two inventories and reports `pack_format`; it rejects a version/inventory mismatch. Existing version-one ZIPs remain supported and unchanged, but do not include those three newer files. Use the new pack or the full reviewed repository for the current summary instructions. Older version-one-only checkers cannot verify version-two ZIPs. An archive's bundled checker is not a trust anchor; use an independently reviewed copy. Some links to wider production-design context require the full repository. Physical flags and the blank receipt worksheet remain unverified in either version.

## Descriptive timing and validity summary, without connecting hardware

An existing prepared package can be summarized offline with the standard-library tool below. Run from `phase-01-hardware`, using a new output filename outside the package:

```powershell
python scripts/summarize_capture.py evidence/synthetic-handoff-001 --output evidence/synthetic-handoff-001-summary.json
```

The tool verifies package inventory, hashes and source transformation first, then checks that the observation bytes it summarizes still match the verified manifest. It never opens a serial port or writes to the package or dashboard. The report records source classification, manifest hash, raw/accepted/quarantined counts, accepted sequence gaps and valid/invalid rows for ADXL345, DS18B20 and INA219. Valid zero remains valid; quarantined rows are excluded from group counts and timing. Group counts therefore sum to accepted rows, not total input rows.

Timing uses declared gateway receipts for accepted records in source order: receipt span, interval median, nearest-rank p95, maximum, zero intervals and observed receipt rate `(accepted rows - 1) / receipt span`. Empty or zero-span captures have no inferred rate; streams with fewer than two accepted records have no interval statistics. Receipt-clock quality and sensor sampling rate are not established by these calculations. Folder reads are not an atomic filesystem snapshot.

This report supports review of [H1](../validation/FIRST-HARDWARE-ACCEPTANCE.md) but applies no acceptance threshold. It does not supply capture start/stop elapsed time, stop reason, first-600-second window counts, reference comparisons, verified identity/calibration or physical sign-off. Physical acceptance remains pending and equipment authorization, ingestion readiness and production readiness remain false, including for operator-declared measured inputs. The original capture and capture-tool summary remain required evidence. Existing filenames and output paths inside the package are refused.

Local verification on 24 November 2026: all 60 hardware-side software tests passed, including 10 summary tests covering irregular intervals, nearest-rank p95, invalid groups, valid zero, quarantine reconciliation, empty/single/equal-time captures, UTC offsets, tampering, post-verification changes, CLI behavior and exclusive output creation. All fixtures are synthetic; no equipment was connected.

## When the ordered hardware arrives

Physical work remains deferred until the complete ordered set is available and the bench is ready and reviewed.

1. Follow the existing physical connection pack for the same 30 selected products. Resolve the exact ordered board labels, motor/driver current limits, INA219 shunt and supply ratings before energizing. This software handoff grants no electrical approval.
2. Perform the pack's staged sensor-only checks first. Existing firmware reports V1 over USB serial at 115200 baud, nominally once per second. No motor actuation is implemented by this adapter.
3. Capture with the existing `scripts/capture_serial.py` instructions. Always use a new capture filename: the capture command now refuses existing files before opening a serial port. Preserve the original capture and record the actual connection configuration separately. Review the capture exit status and summary before conversion.
4. Copy the example attachment to a new file. Fill in site, asset and device identifiers, actual port, exact board reference and configuration reference. Keep `v1_device_id` equal to the firmware's actual identity (currently `motor-001`). Set `source_type` truthfully to `measured` for direct physical capture or `replayed` for replay. Keep `physical_verification: unverified`, `calibration: not_verified`, `transport: usb-serial` and `profile: edgeops.serial-attachment.v1`. These classifications are operator declarations, not hardware authentication.
5. Run `prepare` with that capture and attachment, using a new output directory. Run `verify` on the resulting folder, then review every quarantined row and all provenance before any later integration.

Identifiers allow ASCII letters, numbers, hyphen and underscore, maximum 64 characters. Attachment keys must match the example exactly. Do not store passwords, certificates or secrets in the attachment. Board/configuration references are descriptive references, not independently verified credentials.

## Transformation and review rules

| V1 capture | Candidate V2 output |
| --- | --- |
| ADXL345 acceleration in m/s² | Same units and values for valid sensor; all three axes null when invalid |
| DS18B20 temperature in °C | Same value when valid; null when invalid |
| INA219 bus voltage in V | Same value when valid; null when invalid |
| INA219 current in mA | Divided by 1000 once to A when valid; null when invalid |
| Valid numeric zero | Preserved as zero |
| Captured gateway UTC | Preserved as the receipt instant, normalized to UTC; conversion time is separate |
| No verified device UTC or boot UUID in V1 | Device time and boot ID null; gateway-receipt-only clock; unavailable session |

Headers must be the exact 14-field V1 capture set, with no duplicates. Booleans use the capture writer's `True`/`False` text. Counters must be unsigned 32-bit integers and numbers finite. Missing or extra values, unknown device identity and inconsistent aggregate validity are quarantined. An invalid sensor flag does not establish whether the fault was disconnection, calibration or another cause.

Sequence nonincrease, uptime decrease (including rollover), or receipt-clock regression quarantines that record and every later record. This is an unresolved boundary requiring review, not proof of a restart. A sequence gap is counted only between accepted records; it is not independently established packet loss. No verified sessions are inferred, even for monotonic captures. Limits: 16 MiB input and 10,000 rows per preparation; split large captures deliberately before conversion and retain originals.

## Evidence folder and exit codes

The new folder contains the original `source.capture.csv`, canonical `attachment.json`, accepted `observations.jsonl`, rejected-line reasons in `quarantine.jsonl`, and `manifest.json` with counts, file sizes and SHA-256 hashes. The verifier checks inventory, hashes, counts, provenance flags, and recomputes the transformation from the included original. Existing output folders are refused. Preserve evidence with appropriate access controls; captures contain operational identifiers.

Hashes detect corruption and inconsistent edits. They are not signatures, trusted timestamps, source authentication or proof against a party rewriting the entire folder. Capture UTC is a gateway declaration, not independently verified time. `hardware_connected`, `physical_source_verified`, `calibration_verified`, `ready_for_ingestion` and `production_ready` remain false. Historical evidence cannot establish current hardware connection.

`prepare`: exit 0 means preparation completed with accepted rows and no quarantine; exit 2 means the folder was written but requires review (quarantine or no accepted rows); exit 1 means preparation failed. `verify`: exit 0 means local package consistency only, even when `requires_review` is true; exit 1 means failure. Always inspect the printed review flag. Successful conversion never establishes physical or production acceptance.

## Software verification

Test dependencies are separate from runtime dependencies:

```powershell
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
```

The 50 software checks use synthetic fixtures and simulated serial streams only. They cover the V1 parser, interrupted and oversized messages, output preservation, disconnection, capture-to-adapter compatibility, compile-record inventory boundaries, strict offline evidence verification, optional report export/refusal behavior, bounded serial capture with explicit stop reasons, and no-connection settings previews. Adapter output is checked against the existing candidate V2 JSON Schema and semantic rules. Physical wiring, acquisition accuracy, calibration, electrical safety, long-duration reliability, deployment and industrial acceptance remain pending.

### Optional unsigned verification report

Keep the report outside the evidence folder, using a new filename. From `phase-01-hardware`:

```powershell
python scripts/prepare_capture.py verify evidence/synthetic-handoff-001 --report evidence/synthetic-handoff-001-verification.json
```

Existing output files, report paths inside the evidence folder and late competing targets are refused. Verification failures create no report. Interrupted write failures may leave an incomplete new report; preserve it for inspection and use a fresh filename. The report contains the captured manifest byte count, SHA-256 and exact metadata, declared host verification time, true package-consistency/transformation-check fields and false source/authentication/physical/readiness authority. It contains no raw readings, attachment identifiers or evidence-folder path. A report is unsigned and editable, not a certificate or trusted timestamp; local snapshot checking grants no physical or production acceptance. The original evidence folder is unchanged, so its inventory remains verifiable. Existing short stdout and verify exit 0/1 meanings stay unchanged, including exit 0 with a declared review-required flag.

The dashboard can display a separately selected report only after matching its manifest reference. That browser review does not execute this verifier, authenticate its report or import observations. Retain the original folder and review all quarantine and provenance declarations before any later integration.

### Strict evidence verification

The offline verifier requires the exact manifest field set, integer counts and byte lengths (booleans and floating-point counts are refused), a boolean review flag, bounded lowercase SHA-256 references, and a calendar-valid UTC creation declaration. All existing physical/readiness flags must remain false. JSON is UTF-8, without duplicate fields (including escaped spellings), nonfinite values, excessive nesting or more than 512 parsed values per document/record. The same strict attachment parser is used before preparation, so ambiguous mappings cannot be silently rewritten into an evidence folder.

Each input is read once into a bounded snapshot: manifest 64 KiB, original capture 16 MiB, attachment 8 KiB, accepted observations and quarantine 32 MiB each. Every transformation comparison uses those same bytes after their hashes were checked, with no unbounded second file reads. Observation JSONL records are limited to 16 KiB including the terminator, quarantine records to 256 bytes, and each file to 10,000 records. Blank records and unsupported JSON are refused. Numeric comparisons preserve equivalent JSON numbers such as 0 and 0.0, but never treat false as zero or true as one, including nested observation fields.

These checks describe the captured local snapshots, not an atomic folder snapshot or ongoing freshness guarantee. Files may change after being read. Exact retries, reviewed source identity and retention remain operational concerns. Successful verification still establishes only package consistency and recomputed transformation; it does not authenticate the manifest, establish calibration, connect hardware, authorize equipment or accept production deployment. Verification does not modify the evidence folder, and malformed input exits with a short error instead of a traceback.

### Capture behavior and result interpretation

The USB capture reader buffers timeout fragments until newline, limits a complete line to 4096 bytes including its terminator, drains oversized lines before accepting the next record, and rejects malformed UTF-8, duplicate JSON fields, extra fields and out-of-range V1 counters. A trailing incomplete record is counted as invalid and is not written. Complete rows are flushed to the CSV as they are captured; flushing is not a guarantee against power loss. No automatic reconnect or resumption is performed.

The JSON summary reports `records` (rows successfully written and flushed), `invalid` (rejected/incomplete frames), `sensor_invalid` (saved records with a false aggregate sensor flag), `sequence_gaps` (saved-row counter gaps), and `discontinuities` (nonincreasing sequence or decreasing uptime among saved rows). Saved sensor-invalid readings remain explicitly flagged in V1 and become null by sensor group in V2. Neither records nor gaps establish physical accuracy or actual transport loss. Discontinuities do not establish a verified reboot; the offline adapter quarantines the unresolved boundary.

Capture exit 0 means the duration elapsed with at least one complete valid-format row saved; review sensor flags and counts even on success. Exit 2 means no such rows were captured or a configured record/byte limit stopped capture early. Exit 1 covers file or serial connection failure; exit 130 means the operator interrupted capture. Failures and interruptions may leave a partial or empty new CSV, including an incomplete row after a failed write; preserve it for review and use another new filename. No raw serial payload or device error text is printed by the failure handler. This utility opens only the requested USB serial port and does not send application-level equipment commands; opening a serial port may itself reset some ESP32 boards through their USB bridge.

### Bounded serial capture files

#### Preview settings before any hardware connection

From `phase-01-hardware`, use a fresh planned output filename:

```powershell
python scripts/capture_serial.py --dry-run --port NOT-CONNECTED --seconds 600 --output data/planned-capture.csv
```

`--dry-run` validates duration, positive baud, bounded nonblank port text and adapter-compatible limits, refuses existing output files/directories/links and file-shaped output ancestors, and prints effective settings as `edgeops-serial-capture-settings-preview-v1` JSON. It does not import the serial driver, open/query a port, create files/directories or reserve the filename. Missing output parents are reported as missing rather than created. Exit 0 means this limited settings/path-shape preview succeeded, not that capture can run. Invalid arguments exit 2; an occupied/unsupported output path exits 1 without a capture. Port names are declarations, not availability or hardware evidence.

The preview includes explicit false capture/port/output-reservation/writability/hardware/equipment/production flags. It does not test permissions, free space, drivers, actual baud compatibility, calibration or received parts. A target can appear or change after preview; a later real invocation rechecks the path and still creates exclusively. Keep `--dry-run` while preparing without hardware. Only after the original physical connection checks are completed should an operator choose the actual reviewed port and deliberately invoke capture without `--dry-run`. The dashboard does not start either command.

The recorder defaults to at most 10,000 saved rows and 16 MiB of UTF-8 CSV including the header and CRLF terminators, matching the offline adapter's file/row limits. `--max-records` accepts 1–10,000; `--max-output-bytes` accepts an integer from the CSV header size through 16 MiB. Invalid settings are refused before creating output or opening a serial port. The CLI writes UTF-8 with newline translation disabled; callers of `capture_stream` must provide the same output configuration for exact byte accounting.

Each candidate CSV row is serialized separately before writing. If it would exceed the remaining byte budget, it is withheld in full and capture stops; a capacity stop therefore retains complete rows. Exact-fit byte and record limits stop without reading another frame. The record limit takes precedence if both limits are reached by the same row. No automatic file rotation, reconnect, overwrite, continuation identity or resumption is introduced. Choose a new filename deliberately, retain the original and review connection/session context before another capture. A size-compatible file can still require quarantine or source review; these limits do not establish valid sensor values or physical performance.

The summary adds `output_bytes` (successfully written/flushed UTF-8 prefix, including the header), `withheld_records` (a valid-format candidate omitted because it would exceed the byte budget), and `stop_reason`: `duration_elapsed`, `record_limit`, `byte_limit`, `interrupted` or `capture_failed`. On write/flush failure, counts can understate bytes actually present; inspect and preserve the file instead of assuming the uncounted row is absent. Flush counts are not power-loss durability evidence. A header-only byte budget writes only the header, with no frame read. Limits do not operate hardware or authorize production use.
