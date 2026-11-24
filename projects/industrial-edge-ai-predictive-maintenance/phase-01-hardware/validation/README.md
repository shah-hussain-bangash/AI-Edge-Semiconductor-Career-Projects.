# Bounded hardware-validation preparation — 24 November 2026

## Additional clean-installation verification — 24 November 2026

The dashboard and optional ML requirements were installed into a new, separate Windows Python 3.14.8 environment using published wheels. System and user site packages were excluded. The existing running dashboard and its data were untouched. This closes the reused-dependency limitation for the software checks listed here, not for every repository test or target platform.

[Installation evidence and exact package/archive versions](fresh-installation-result.json) · [Sanitized operations replay](fresh-installation-replay.json)

The verified source was GitHub commit `60e2ff5198838008d43a6c7694ad9de8b3844c01`, tree `85b6576562ea322018461951f1aa161b1d414018`. Installation used `python -m pip install --only-binary=:all: -r requirements.txt -r requirements-ml.txt` from the dashboard directory with the new interpreter. `python -m pip check` reported no broken requirements. API tests passed 26/26, scikit-learn comparison tests 3/3 and experiment-registry tests 5/5: **34 targeted tests passed**, plus the synthetic observation-to-incident-to-maintenance-draft replay. Every test used disposable data.

The result records the installed versions and downloaded archive SHA-256 values. They describe this installation snapshot, not a cross-platform lockfile or a security assessment of those packages. The replay's source-tree identity, draft state, content hash and sanitization were checked. Browser acceptance, real acquisition and deployment were not exercised in this new environment. All physical acceptance remains pending. The earlier evidence below retains its original source revision and scope.

## Disposable backup and recovery drill — 24 November 2026

[Sanitized recovery result](synthetic-recovery-result.json) · [Replay script](run_recovery_drill.py) · [Existing recovery implementation](../../dashboard/recovery.py)

One temporary dashboard database containing a synthetic observation, its incident and a linked maintenance draft was backed up, verified and restored to a new temporary directory. The restored database passed integrity and foreign-key checks. All five relevant domain tables retained one record each, including observation and incident-to-plan source links. The API returned the original frozen observation and plan snapshots after restoration; the maintenance request remained `draft` with execution disabled.

The restore revoked the single saved session. Its old browser token was rejected; a fresh login succeeded. An intentionally altered **separate backup copy** was rejected without publishing a restore directory. The original temporary source database remained byte-for-byte unchanged. Private databases/backups and generated credentials were removed by fixture cleanup; only the allowlisted result was retained.

The application source tree was `898aba69af1ec30e4d70914b219a139cf7d9d01a`, matching GitHub commit `e7b941ccdd9deb7f8ff7fd1862ba922466bbcbe7`. The replay tool and result are versioned together after that source snapshot. Result SHA-256 (original LF file bytes): `245e64513f8c4c07222c2c2257532b3e62fb9b8bffe750572e0d1fbadbad94a4`.

Related regression checks passed: `test_recovery.py` 8/8, `test_observation_incidents.py` 10/10 and `test_incident_planning.py` 9/9, for **27 passing tests**. No application recovery blocker was demonstrated, so the existing backup/restore implementation was unchanged.

To replay from the project directory inside a Git checkout, use an interpreter with the dashboard test dependencies and a new output filename:

```powershell
python phase-01-hardware/validation/run_recovery_drill.py --output synthetic-recovery-replay.json
```

The script trusts only its own checkout path for the Git source-tree read, without changing global Git configuration. Execution timestamps and source-tree revisions can differ between runs, so compare assertions and provenance rather than expecting the saved JSON hash to repeat. This is a one-store software drill: coordinated multi-store recovery, real cutover, offsite/encrypted backup, operational recovery-time/data-loss targets and physical maintenance remain unverified. No live data or connected equipment was involved.

## Synthetic model-evaluation review — 24 November 2026

[Review, demonstrated defect and verification](../../dashboard/reviews/2026-11-24-model-evaluation-review.md) · [Synthetic comparison result and source fingerprints](model-evaluation-review-result.json)

Equivalent UTC instants expressed with different offsets now retain the same chronological holdout and metrics. Experiment/comparison dataset ordering uses the same parsed-time key, and invalid or timezone-free timestamps are rejected. All 46 targeted regression tests passed, including a check that holdout changes leave threshold-selection inputs unchanged. The saved result contains invented labels with only ten holdout rows, nine labelled positive; its scores do not establish physical failure prediction or select a production model. Existing historical evidence below remains tied to its original source revisions.

## Saved synthetic operations example

[Sanitized result](synthetic-operations-result.json) · [replay script](run_synthetic_operations.py) · [first hardware acceptance checklist](FIRST-HARDWARE-ACCEPTANCE.md)

One existing synthetic fixture was committed to an isolated temporary database through the authenticated API. Its history was inspected before preparing an incident and a maintenance draft. Assertions verified content identity, receipt linkage, retained source snapshot, units, valid zero, missing current as null, unverified observation clock and exactly one saved observation. The maintenance record was checked in storage to remain `draft`; no approval or equipment action occurred. The temporary database and ephemeral authentication were discarded. No running dashboard, live database, serial port or equipment was used. This is an API walkthrough, not a browser, real acquisition or physical acceptance test.

The input is deliberately partial: acceleration axes are synthetic zero, temperature/current/voltage are null, calibration is unknown and the declared gateway timestamp is an old fixture timestamp. The synthetic boot/session declaration does not verify any physical device session. No fault, freshness, calibration or predictive accuracy is inferred.

Result SHA-256: `1a06a3ae2c4035fed2175267f4b71f37e48ea8a890c1d1c880392d6b72fe1922`.

Replay from the predictive-maintenance project directory, using an interpreter with the existing dashboard test dependencies:

```powershell
python phase-01-hardware/validation/run_synthetic_operations.py --output synthetic-operations-replay.json
```

The output path must not exist. The script uses existing test fixtures; it is not a production acquisition command. Runs contain a new execution timestamp, so compare assertions and content identity rather than expecting identical output hashes. `software_tree` identifies the checked application tree before this documentation/tool-only change; it excludes uncommitted walkthrough files. The script itself is versioned alongside this record.

## Repository and checks

Inspected [draft PR #2](https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects./pull/2), head `ui/production-workspace-20261119` at `44cbaae2ae9d1e92e53d7854e6b6f7c32a268ab5`, base `dashboard-live-edit` at `25f943a5a34aa1f70c9fcf8c7c595b2d265db140`. The working checkout was clean before this work, on local `ui/production-workspace`; its application tree matched remote head (`a8cb8c760978edccd86954d52251c8f81fff89c9`). Existing hardware notes were checked against the original 30-product connection matrix and the production implementation/acceptance document.

Latest completed CI observed on that inspected head:

| Workflow | Outcome |
| --- | --- |
| [Dashboard Checks](https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects./actions/runs/45181515842) | success |
| [UI Browser Acceptance](https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects./actions/runs/45181515845) | success |
| [Offline Experiment Registry](https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects./actions/runs/45181516057) | success |
| [Offline Scikit-Learn Comparison](https://github.com/shah-hussain-bangash/AI-Edge-Semiconductor-Career-Projects./actions/runs/45181515808) | success |

Local checks performed on 24 November 2026:

| Check | Outcome |
| --- | --- |
| Isolated one-observation walkthrough including persisted maintenance `draft` assertion | PASS |
| `test_observation_incidents.py` | 10/10 PASS |
| `test_observation_queries.py` | 5/5 PASS |
| `test_acquisition_registry.py` | 7/7 PASS |
| `test_incident_planning.py` | 9/9 PASS |

31 regression tests passed. Existing FastAPI/Starlette deprecation warnings were observed; they did not block the walkthrough. No application software blocker was demonstrated, so no dashboard or application behavior changed. These results are software evidence only. The linked CI runs describe the inspected pre-change head, not an assertion that a later commit has already passed CI.

## First physical milestone and remaining dependency

H1 defines a measured 600-second sensor-only baseline, acceleration/temperature/current reference comparisons, metadata, quality checks and independently reviewed evidence. Every physical gate is pending. Targets are proposed for acceptance by the owner and qualified reviewer before a real run; they do not approve wiring, electrical ratings or energized work. A zero-current check does not replace a reviewed nonzero current reference check.

Exact dependency: receipt and identification of the already ordered components, a ready reviewed bench and adequate existing reference capability have not been evidenced. The current measured capture handoff is offline; the dashboard remains synthetic-only. No extra hardware, dashboard scope, substitutions, installations, merges, deployments or work on the other six concepts was added. This bounded repository session ends with preparation complete and physical validation pending.

## Synthetic workflow rollback and retry evidence — 24 November 2026

[Sanitized result](synthetic-workflow-integrity-result.json) and [replay tool](run_workflow_integrity.py) verify the existing observation → incident → maintenance-draft path against application commit `61e93848f07dc229652d88d145c6c7416fff3d9b`, tree `71f325c515e6a931ecc1a5f7c4088ad5f4f5e0e7`. The tree identifies the application baseline before this evidence-only addition; the tool is versioned beside the result.

The drill creates exactly one synthetic observation and incident in a disposable authenticated test database. A temporary database trigger forces failure at the linked-plan audit write. Assertions check unchanged plan/link/event/audit counts, the stored incident row and retained observation snapshot. After removing the trigger, the same request saves one draft. An exact retry returns that draft without writes; a changed proposal returns 409 without writes. A later incident acknowledgement increments its revision while the original draft and frozen source snapshot remain unchanged and the changed-source flag is set. No application blocker was demonstrated, so application behavior and dashboard scope are unchanged.

Replay from the predictive-maintenance project directory with the existing dashboard test dependencies:

```powershell
python phase-01-hardware/validation/run_workflow_integrity.py --output synthetic-workflow-integrity-replay.json
```

The output path must be new. Temporary credentials, database, trigger and records are discarded; only allowlisted assertions, counts, timestamp and software tree are exported. Result SHA-256: `aa3ca4c9cdf9ba9425612a942fb2129345e9ff478bdd6ddcda7b5aef5a543626`.

Local verification: the drill passed, and the existing `test_observation_incidents.py`, `test_incident_planning.py` and `test_maintenance_requests.py` suites passed all 27 tests. These include scope, access, concurrent retry, stale revision, independent review, rollback and source-preservation regressions. Existing test-client deprecation warnings did not block execution. These local results do not assert the outcome of a later GitHub workflow run.

This establishes deterministic local transaction rollback and sequential retry behavior, not power-loss recovery, distributed exactly-once delivery, real acquisition or physical acceptance. Maintenance stays `draft`, execution is disabled, and hardware/authorization/physical-acceptance/production flags remain false. The original 30 categories are unchanged; connection awaits the complete hardware set and a ready, reviewed bench. The other six concepts remain future scope. No merge or deployment is included.

## Source corruption and retained evidence review — 24 November 2026

[Sanitized regression result](synthetic-source-preservation-result.json) records 24 passing existing tests on application commit `16e6cf95272f52a2c30694355523c85757b03baf`, tree `a3b4f16cf5cac7350d843ba8735e29c48d97a90e`. No application change or additional dashboard scope was needed.

The disposable fixtures deliberately alter a committed observation's payload. History inspection and new incident capture reject the inconsistent payload with HTTP 503. A previously captured incident still returns its original source snapshot, an exact retry reuses that saved capture, and a linked maintenance draft preserves it. Other regressions check source identity through local backup/restore, authorization, stale revisions, independent review and transactional rollback. These tests overlap earlier suites; their counts are not additional independent acceptance criteria.

Replay from the dashboard directory with its existing test dependencies:

```powershell
python -m unittest discover -s tests -p test_observation_incidents.py -v
python -m unittest discover -s tests -p test_observation_queries.py -v
python -m unittest discover -s tests -p test_incident_planning.py -v
```

All 24 test cases passed with no failures, errors or skips. The first combined evidence harness then failed while collecting Git metadata because its environment was missing a Git configuration value. A separate command confirmed the local tree against the GitHub commit tree before the sanitized result was written. This collection limitation is recorded in the result; it is not counted as an application failure or silently omitted. Existing test-client deprecation warnings also remain.

Result SHA-256: `e52c435506afe55d4447ce00e1507c66bb2ea175817c4a40709e09e087b4ef8c`. This is software regression evidence, not proof against a privileged administrator changing the database and its snapshots together. It establishes neither real sensor authenticity nor physical acceptance. Hardware connection and acceptance remain pending, with the same original 30 categories; no merge, deployment or work on the other six concepts is included.

## Process stop after central commit — 24 November 2026

[Sanitized result](synthetic-process-stop-recovery-result.json) records a separate worker process using actual HTTP against an isolated loopback test server. Application behavior is the unchanged baseline `99e989aff13e78d2b145f159d350f079bdf85371`; the new regression is versioned alongside this result in [test_delivery.py](../../dashboard/tests/test_delivery.py).

The fixture stops the worker with `os._exit(74)` only after it receives a matching central-commit receipt and before it saves the local outcome. The parent verifies one committed central observation and an unfinished first queue claim. A controlled active lease prevents early replay; after the disposable lease is explicitly expired, the normal worker replays the observation and saves the original receipt ID and commit timestamp. Final checks show one central observation, one central-commit audit event, two queue claims, an unchanged queued payload and successful SQLite quick checks on both stores.

Replay from the dashboard directory with its existing test dependencies:

```powershell
python -m unittest discover -s tests -p test_delivery.py -k process_exit_after_central_commit -v
```

The test uses temporary accounts, credentials and databases; no running user dashboard or equipment is contacted. Abrupt exit intentionally skips normal worker cleanup, and the disposable fixture removes its test state afterward. Lease deadlines are controlled in test storage: this is not a measured wait, RTO, power-loss or remote transport test. The injected stop occurs after receipt arrival, so it does not prove every possible network-loss or crash location. It is evidence for this specific local replay path, not a general exactly-once guarantee.

The isolated drill passed, and all 48 tests passed across delivery, worker, history, capacity and timing suites. Counts overlap earlier checks and must not be added as independent acceptance milestones. No application blocker was found or application behavior changed; only regression coverage and sanitized evidence were added. Existing test-client deprecation warnings remain. Result SHA-256: `deafb89bc36301d47ee74873274f2edbe7765b8083bba5b12a6f936eb338a03f`.

The same original 30 hardware categories are preserved. Physical acceptance and equipment authorization remain pending/false; no merge, deployment or work on the other six concepts is included.
