# Arrival-pack source completeness — 24 November 2026

Reviewed baseline: `702443e13f9dbb24d5521b2e2967dc0002d08d20`, draft PR #2. Scope: the existing read-only hardware-preparation export and offline ZIP checker. No equipment, running user service, installation, merge or deployment is used.

## Demonstrated omission

The exported handoff guide described `scripts/summarize_capture.py`, but the fixed source inventory omitted that tool, its test file and `validation/FIRST-HARDWARE-ACCEPTANCE.md`. Inspection of a newly generated baseline archive confirmed all three were absent. The standalone pack could therefore not run the newly documented summary command.

## Versioned correction

New exports use `edgeops-arrival-pack-v2`, adding exactly those three preparation files. The start guide identifies the included tool/checklist, partial owner-reported receipt and unverified item-level state. Wider production-design links still require the full reviewed repository; the pack does not claim to contain the entire project.

The checker preserves the original version-one inventory and accepts either exact supported inventory only when it matches the declared format. Missing, duplicate, extra, unsafe or version-mismatched entries remain rejected. Its report includes `pack_format`. Existing ZIPs and editable worksheet copies are not rewritten. An older version-one-only checker will reject a new version-two pack; use a current independently reviewed checker, not an untrusted archive's bundled copy as a trust anchor.

The matrix, sensor map, original 30 categories, worksheet defaults and physical authority flags remain unchanged. No receipt, compatibility, wiring, calibration or acceptance is inferred from export or verification.

## Verification

- All 31 tests passed across `test_arrival_verifier.py` and `test_physical_build.py`, including new version compatibility, mismatched version/inventory, source-byte inclusion and rehashed missing-file rejection cases.
- The actual previously saved version-one ZIP passed the updated verifier without modification.
- A newly generated version-two ZIP passed verification: 32 non-manifest files checked, all 30 hardware categories retained, physical acceptance false.
- All 60 hardware-side software tests passed from a temporary extraction of that freshly generated, fixed-inventory pack, independently of the checkout. This checks included source/test dependencies; it is not hardware acceptance or a production installation test.

These are distinct software executions, not a combined unique-test total. The offline verifier reads bounded ZIP members without extracting or running them; only the trusted, freshly generated package was extracted for the separate software test run. File consistency does not prove source authenticity, physical receipt or electrical compatibility. Physical acceptance and equipment authorization remain pending/false.
