# Production gap audit - 19 November 2026

Disposition: local software improvements implemented; complete end-to-end industrial production acceptance is still open. The user confirmed hardware will be connected later. No purchased parts, sensor calibration, hardware connectivity, target host, real labels or qualified sign-off have been inferred.

This audit inspected the current dashboard/authentication, SQLite domain stores, synthetic ledger, experiment integrity, readiness and planning services, consolidated architecture/contracts/backlog/source review, relevant firmware/hardware integration boundaries and automated checks. The historical source-review manifest remains its original dated snapshot. This is not an independent security assessment or a rerun of the historical MQTT/physical lab evidence.

## Defects and operational gaps addressed

| Finding | Resolution | Verification |
| --- | --- | --- |
| Header-only request size check missed chunked/undeclared or false-length bodies | Bounded actual-byte ASGI check before parsing, including malformed/duplicate length rejection | Real streamed API request and boundary/lying-header tests |
| Failed sign-in audit insert was rolled back when the denial exception left its transaction | Persist the sanitized denial before returning 401 | Reopen/read audit after denied sign-in; no submitted credentials retained |
| Hardcoded system mode was insufficient to observe database availability | Separate minimal process/database probes and authenticated diagnostics with bounded checks | Missing/corrupt stores, role denial, no private path/credential disclosure |
| No reusable recovery operation or restoration reconciliation | Standalone backups, hashes/counts, strict inventory, verification and restore-to-new-directory with session revocation | Actual disposable restore, WAL commits, corruption, traversal and overwrite refusal |
| Dashboard lacked current service/recovery visibility | Settings service checks, timestamp, source identity, export and outage/retry handling | Browser refresh/export/outage recovery; responsive and contrast checks |
| Active setup guide mixed obsolete counts, colors, ports, branch instructions and pending-test labels | Rewrite current guide; retain the old accumulated text in an explicitly superseded history folder | Current capabilities and instructions link to authoritative contracts/runbooks |

## All production requirements remain traceable

| Requirement | Current boundary and remaining work |
| --- | --- |
| REQ-01 Scope/architecture | Consolidated design exists; deployment scope, owners and acceptance targets require agreement |
| REQ-02 Physical hardware | 30-category design catalog; actual inventory, exact ratings/wiring and commissioning pending |
| REQ-03 Sensor acquisition | Existing embedded/serial source is a starting point; real timing, units, calibration and fault evidence pending |
| REQ-04 Device identity | Planning/previews; scoped enrollment, credential and hardware-replacement lifecycle pending |
| REQ-05 Durable delivery | Historical synthetic MQTT/HTTP lab exists; automatic bounded spool/retry, conflicts and measured transport cutover pending |
| REQ-06 Backend/storage | Transactional local review/planning/readiness domains; production database migrations, authoritative asset/incident/device APIs, retention and scale pending |
| REQ-07 Identity/security | Local sessions/CSRF/audit and bounded body parsing; enterprise identity/MFA/provisioning, device credentials, scoped policy, distributed throttling and TLS deployment pending |
| REQ-08 Connected dashboard | 18 usable views; most equipment views remain fixtures until authoritative APIs are implemented |
| REQ-09 Incidents | Browser examples; persisted correlation, assignments, expiry/escalation, resolution/reopening and operational effects pending |
| REQ-10 Maintenance | Saved synthetic planning and independent review work; technician execution, evidence, independent verification and operational closure pending |
| REQ-11 Real models | Synthetic chronological evaluation and reviewed immutable comparisons work; representative real labels, thresholds and independent evaluation pending |
| REQ-12 Deployment | No deployable/approved edge bundle, gateway parity, promotion, monitoring or rollback implementation established |
| REQ-13 Grounded AI | Illustrative guidance/catalog; approved knowledge ingestion, retrieval/access/citations/abstention and bounded assistant integration pending |
| REQ-14 Reproducible release | CI and local setup; pinned release artifacts, staged deployment, managed configuration, upgrade/rollback and supported host matrix pending |
| REQ-15 Monitoring/support | Actual local software checks added; sensor/queue/model metrics, alerts, support ownership and measured load/soak targets pending |
| REQ-16 Recovery | Verified local SQLite/artifact restore tool added; full deployment dependencies, encrypted/off-site retention, scheduled backups and accepted RPO/RTO drills pending |
| REQ-17 Governance | Evidence and immutable research records; deployment-specific data rights, retention/access policies and enforcement pending |
| REQ-18 Acceptance | Full 53-criterion register exists; no criterion is auto-approved and no production acceptance is inferred |

## Delivery sequence with hardware arriving later

1. Agree the first supported deployment: host/OS, one guarded motor, users/site, network boundary and measurable operating/recovery targets.
2. Implement strict operational observation contracts and scoped asset/device identity with compatibility fixtures; keep synthetic/replay/measured origins separate.
3. Implement bounded durable edge delivery and conflict-aware authoritative ingestion; prove restart/outage/response-loss behavior with isolated synthetic fixtures first.
4. Implement production storage/identity and authoritative incidents/work orders, connecting existing UI views without replacing current account/report/evidence data.
5. Complete operational execution/verification, approved knowledge assistance and controlled model release. Prepare managed deployment, monitoring and recovery procedures.
6. Connect actual hardware only after exact-part review and commissioning; collect real data and evaluate models, throughput, failure/recovery and qualified acceptance under the agreed scope.

Each slice needs tested code and observed evidence. A checklist, green local probe or synthetic demonstration cannot replace the implementation or prove physical safety. Current readiness APIs continue to report production_ready=false and equipment_authorized=false.
