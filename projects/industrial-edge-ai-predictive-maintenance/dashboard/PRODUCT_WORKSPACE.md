# EDGEOPS product workspace — 19 November 2026

This implementation provides 17 connected workspace views plus sign-in, with a slate/teal visual system, responsive navigation, searchable destinations, keyboard support, and six professional profile previews. It implements the presentation and interaction layer of the consolidated design. It does not establish production readiness.

## Capability coverage

| Design workspace | Current interface and interactions | Service boundary |
| --- | --- | --- |
| Access | Sign-in, authenticated session, sign-out, denied/error handling | Working local account service; enterprise identity/recovery not connected |
| Fleet | Consistent fixture counts, attention queue, asset spotlight | Synthetic equipment |
| Assets | Search, status filter, sort, details, investigation links | Synthetic registry; commissioning/calibration persistence pending |
| Telemetry | Four signals, accessible sample table, CSV and units | Fixed synthetic samples; live ranges/resolution pending ingestion |
| Device operations | Registry empty state, commissioning checklist, three receipt boundaries | No device enrollment, certificates, firmware or spool health integrated |
| Incidents | Filter, session acknowledgment, case context and proposed timeline | Assignment, suppression, escalation and operational decisions pending service |
| Maintenance | Seven-step guided path, independent approval/verification, session draft save/clear | Walkthrough is not a work-order state machine; no operational submission |
| AI assistant | Illustrative insights, evidence requirements, knowledge navigation | Retrieval and generation unavailable |
| Knowledge | Searchable design catalog, source context and revision/approval state | Catalog references are not approved SOPs or indexed documents |
| Models | Lifecycle, lineage, blocked release checklist, verified comparison link | Offline report review works; deployment and rollback unavailable |
| Hardware | 30 named BOM categories through authenticated API | All planned; purchases, instances, ratings and commissioning unverified |
| Simulation | Three deterministic scenarios, next sample/reset, explicit missing values | Browser fixture only; no firmware/broker/model execution |
| Security/audit | Authenticated local audit records and session boundary | Enterprise grant/session administration pending |
| Governance | Readiness and physical/security/model acceptance context | No release authorization inferred |
| Reports | Verified experiment integrity, real scoped approval/rejection/history | Report review only; no equipment or model deployment authority |
| Settings/people | Local density preference, shortcuts, six profile journeys, actual account identity | Profile preview never changes authenticated role or server permissions |

Profiles: operations, technician, approver, ML engineer, administrator and auditor. They expose responsibility-specific journeys and limitations. These previews do not replace server authorization or implement the full future role catalog. Browser session drafts are stored separately from authenticated report decisions and can be cleared. They must not contain confidential information.

## Document reconciliation

- `production-design/` is the current system design. EA milestone documents and evidence retain their historical scope.
- Removed the outdated 14-named/16-placeholder inventory definition from the running API and active dashboard guidance. `BOM-01..30` now matches the design categories. These identifiers replace the old grouped `HW-*` slots; they are not a one-to-one historical alias or a physical inventory migration.
- Removed seven obsolete HTML prototypes from the active `assets/` folder and retained their contents under `archive/ui-prototypes/`, explicitly marked superseded. This removes competing runnable UI references without deleting historical evidence. Repository Git history also retains the earlier paths.
- The source review manifest remains a dated record of its original input snapshot. It is not a current-tree integrity manifest; moved prototype paths and changed source hashes do not imply tampering with that historical snapshot.
- Physical wiring and lab evidence have not been deleted merely because a target architecture differs. Exact-part review and explicitly scoped tests still govern those records.

## Verification

On 19 November 2026, the local Python suite completed with 54 passed and 24 browser cases skipped because Python Playwright is unavailable in this environment. Two separate Chromium suites passed: saved comparison review (real isolated service, approval/rejection, persistence, escaping, outage/retry and auditor restrictions), and workspace acceptance (17 views at 1440/1024/768/390/320 pixels, profile selection without identity change, knowledge search/empty/source detail, release/lineage views, missing-sample replay/reset, session draft persistence/escaping/clear, maintenance independence, device checklist, existing search/filter/CSV/dialog/density behavior). No hardware acceptance is implied.

## Remaining production work

Durable ingestion, enrolled device identities, actual sensor acquisition, central operational records, independent work-order decisions, enterprise identity, model release, grounded assistant services, recovery/load/security validation and physical commissioning remain required. A polished interface does not close these gates.
