# Opt-in synthetic threshold correlation

This working integration evaluates newly committed synthetic observations and groups eligible threshold matches into automatic cases. It does not verify real faults, notify external recipients, authorize equipment, execute maintenance or establish production acceptance. No policies, observations or cases are seeded on installation.

## Activate deliberately

In **Alerts → Automatic threshold cases**, an administrator activates an immutable policy for one exact active synthetic device binding, known dashboard asset and sensor channel. Creation and disabling require a current session, CSRF, administrator password reauthentication and a reason. The policy records its configuration hash and issuing account revision. Only one non-disabled policy per device/channel is retained at a time. Disable the old policy before creating a replacement; no edit/re-enable endpoint changes historical meaning.

Policies specify SI threshold, strict above/below comparison, severity, maximum declared source age, calibration eligibility and a sequence group size. There are no guessed threshold defaults. Unknown/invalid/null channel quality, unverified declared clocks, stale/future timestamps and required-but-unverified calibration produce recorded abstentions rather than cases. Legitimate zero readings remain values. Clock and calibration verification labels are synthetic declarations, not physical attestations. The explicit unverified-calibration option is for synthetic rehearsal only.

## Deterministic, limited correlation

A group is `(immutable policy ID, verified synthetic boot ID, floor(sequence / window_size))`. This is a logical sequence window, **not seconds, a consecutive-sample detector, a hysteresis/clearance policy or a confirmed physical fault episode**. Multiple threshold matches in that group append source evidence to one case; out-of-order accepted sequences do not create another case. Different boots, groups and replacement policies are separate cases. A group can have gaps or observations from before activation that were never evaluated. The first source means first centrally accepted, not earliest physical event.

Evaluation runs only on a new source key inside the same authorized central write transaction. Identical delivery retry returns the original receipt without re-evaluation. A modified duplicate retains the original and conflicts. Activating/replacing a policy never replays historical observations, including an old duplicate retried after activation. Current issuer role/access/account revision and exact binding status are rechecked; changed authority stops future evaluation. No source reading, origin or identity is rewritten.

Source commit, evaluation record and automatic case effect commit together. Policy corruption or retained correlation capacity refusal aborts the entire new observation transaction; no central receipt claims a partial success. The HTTP worker retains its existing retry/backoff behavior. Limits are 50 retained policies, 1,000 retained cases and 60,000 evaluations, with the existing 10,000 central observation cap. Disabled records remain retained; no cleanup, capacity reset or retention job is installed. Those limits are application bounds, not accepted disk/performance targets.

## Evidence and human handoff

Authenticated readers inspect cases, immutable policy context and hash-validated central source records. Evidence is bounded and paged by event key, not physical event time. Paging can require the loaded case revision and refuses newer case evidence instead of combining pages silently. Exports retain the loaded case page or loaded evidence page plus the first accepted source and all six source channels; they do not pretend to include unreturned pages or a frozen multi-request snapshot. Evaluation totals are labelled across all devices separately from the device-filtered case page.

An administrator/operator can explicitly create a governed synthetic incident from a case after entering a review note. The handoff checks the current case revision, freezes its context, uses the existing observation-capture workflow and preserves the actual human creator. It does not impersonate the service principal that committed the observation. A case has at most one governed handoff; an unchanged retry returns the same incident. Existing source/creation-key conflicts are refused rather than silently attaching another incident. Access to linked incidents follows the existing creator/assignment/admin/auditor rules.

Further matching observations update the automatic case revision, not the governed incident or approved plan snapshots. The incident displays a newer-source-evidence warning and a link to review the case. A planning draft captures the available correlation context. Users must explicitly review and attach relevant new evidence using existing revision-bound workflows. No automatic resolution, approval or execution is introduced. The existing manual incident API still describes its governed exercise scope; automatic-case provenance is supplied separately as `correlation_source`.

## Activation, restore and verification

The schema is additive and needs a backend restart. Ordinary startup preserves deliberate policies and existing data. A verified restore retains cases/evidence but disables retained non-disabled policies and revokes service credentials; fresh authorization is required before automatic evaluation resumes. Restore reports state how many policies were disabled.

Tests cover opt-in/no-retroactive behavior, concurrent and repeated source delivery, modified conflicts, out-of-order grouping, quality/calibration/clock/age abstention, legitimate zeros, current policy authority, atomic rollback at capacity, source/policy integrity, evidence paging/revision guards, idempotent human handoff, original incident access and restore protection. The browser rehearsal activates a policy explicitly, then uses the native test MQTT broker, durable spool and HTTP ingestion to produce a case and hand it into the existing incident/maintenance workflow. This is finite synthetic software evidence; measured fault correlation and operational acceptance remain pending.

For the opt-in native MQTT browser rehearsal, test certificate generation may use EDGEOPS_PKI_PYTHON to point to a separate Python interpreter with cryptography installed. This is test-fixture plumbing only; it does not change the dashboard runtime or certificate trust policy.
