# Physical build preparation in Hardware

This view uses the same 30 selected products. No replacement board, sensor, motor, driver, supply or accessory is introduced. The source is the existing phase-01 physical connection matrix and sensor-only named-net diagram, itself based on the newer GitHub sourcing table.

## Order report and physical facts

The user confirmed all 30 selected categories were ordered. The catalog now reports `ordered_count_user_reported: 30`, dated 20 November 2026, and each lifecycle is `ordered-user-reported`. This count concerns selected product categories, not an inspected count of individual pieces or pack quantities. `purchased_count` remains unknown as independently verified evidence; `purchase_verified`, `connected` and commissioned/physical-instance claims remain false or unverified. Order reporting does not create a sensor reading or satisfy a readiness criterion.

Hardware includes the power-off layout, conditional sensor harness, Pi assembly sequence and the unresolved motor-circuit review. It shows all 30 roles, including instruments, optional installation items and the cold spare. Export downloads the fixed-scope JSON plan. The sensor diagram is a named-net reference, not a guessed physical board-pin layout or a released motor-power circuit. No progress boxes silently mark equipment safe or connected.

The firmware reference remains GPIO21 SDA, GPIO22 SCL and GPIO4 temperature data, subject to actual board and sensor pin/supply identification. Motor power and driver-control assignments remain pending the ratings explicitly absent from the source. This view does not add a software motor-control action or require new hardware. Hardware testing is deferred; this software change performs none.

## Interfaces and source consistency

`GET /api/hardware/physical-plan` and `GET /api/hardware/physical-plan/sensor-map` require a supported authenticated local role. They are read-only. The plan rejects unsupported/expanded IDs, physical-connected or production-ready claims, replacement permissions and unexpected reference pins. It includes source and diagram hashes. The diagram is served only if its content matches the plan's recorded hash. The catalog's `/api/hardware` lifecycle now distinguishes the user order declaration from verified purchase/installation.

Every plan/map read now also checks bounded source snapshots: plan JSON (64 KiB), LF-normalized CSV matrix (256 KiB), and each map copy (512 KiB). The exact 30 identities and all five family/quantity/role/connection/pending fields must agree with the matrix. The CSV hash, map hash and dashboard/source map copies must agree. Invalid scope/declarations, malformed structures or duplicate JSON keys, blank fields, linked/outside/missing/oversized sources and source disagreement return a generic 503 without partial instructions. These are consistency checks against local versioned files, not signatures, supplier validation or physical approval; coordinated changes to those files still require independent review.

The map response contains the bytes already checked in memory instead of reopening the file later. Successful plan and map responses declare no-store and nosniff. Arrival-pack assembly independently rechecks the packaged map hash after its initial plan check, so a changed map cannot enter that download unnoticed. The original plan, CSV, maps and electrical notes remain unchanged. No new physical record, endpoint or schema is added.

The packaged `physical-build-plan.json` is a snapshot of the phase-01 connection matrix. Its CSV hash uses UTF-8 bytes with LF-normalized line endings; row names and order are tested against that source. The map copy is checked byte-for-byte. These are versioned source checks, not independent physical verification or signed purchase evidence. If the selected guide is revised, regenerate/review this snapshot and map together. No private order numbers, supplier accounts or payment evidence are included.

On a failed refresh, the view clears prior instructions, hides the diagram and disables export. It cannot present stale instructions as newly verified. Existing component filters, details, CSV and the other 17 workspaces remain accessible.

## Verification

Three new API/source cases verify all 30 identities, no additions/substitutions, agreement with the matrix/map, supported roles, read-only routes and the separation of ordered versus connected/verified states. The workspace browser suite exercises the map, 30-row table, export, unavailable/retry handling, all 18 views at five widths and text contrast. Existing review, delivery, readiness and telemetry checks remain in place. No bench action, hardware commissioning, database schema migration or physical acceptance occurs during this update.

The physical-plan suite now has 15 tests, including inconsistent but structurally valid notes, all five row-field mismatches, malformed/duplicate/deep JSON, shape/declaration/hash errors, source changes, row order, missing/bounded/linked sources, CRLF normalization, both map copies, generic refusal across all three authenticated read routes, exact in-memory map responses and a map changing during pack assembly. Tests use disposable source copies and accounts, not installed user data or hardware.


## Exact-BOM preparation details

Each family in the 30-row physical preparation table now opens a read-only component preparation view. Component catalog details also offer View connection preparation, linked by the exact BOM ID from the separately loaded fixed plan. No fuzzy part matching, variant substitution or physical-instance mapping is inferred. The view preserves the plan's selected family, quantity basis, role, connection notes and pending checks verbatim. Quantity basis is planning context rather than an inspected item count. No received model, connection, calibration, motor circuit or acceptance is established by opening the view.

An expandable reference section shows the loaded plan version, service-supplied plan hash, CSV/map reference hashes and user-reported order declaration. These identify source context; the browser does not independently re-query/sign those references or release electrical compatibility. Export this preparation row retains the exact loaded row and those references, with read-only/fixed-scope and false additional-hardware/substitution/physical-acceptance/equipment/connected/production flags. Neither the plan JSON, matrix nor map is changed by this feature.

The client refuses expanded/reordered/unsupported IDs, incorrect scope/version/flags/pins, malformed reference hashes and unsupported row fields before displaying a new plan. Refresh closes and clears old component/export content immediately, disables catalog links while the plan is unavailable, and leaves the full existing export/arrival-pack actions disabled until a supported response is loaded. Old close events cannot clear a newer component view. Close/Escape restores its opener, including a catalog dialog underneath; catalog refresh also invalidates a view opened from that catalog context. Independent physical-plan views remain separately sourced.

The feature adds no endpoint, schema, physical receipt form, equipment command or hardware recommendation. A disposable Chromium suite covers all 30 exact identities and fields, quantity bases, catalog-to-plan links and nested dialog focus, single-row export, source-preserving loaded context, refresh/outage/unsupported metadata clearing, escaped text, read-only auditor access, no inspection reads/domain writes, contrast and five widths. Actual received labels, module compatibility and physical qualification remain pending.


## Searchable connection preparation

The fixed-plan table has its own literal, case-insensitive search over BOM ID, selected family, role, quantity basis, connection notes and pending checks. A row matches when any single field contains the trimmed query. The count explicitly remains out of 30; filtering changes presentation only and never reduces the selected hardware scope. Clear search restores source order and focuses the search field. Empty results explain recovery and disable the matching export. Catalog filters remain independent.

Export matching preparation downloads the exact visible source rows in source order, the trimmed query, matching/total counts, loaded version/hash references and user order declaration. It preserves false physical/order/equipment/production/substitution/additional-hardware flags and explicitly identifies a filtered planning copy. The complete fixed-30 plan export and authenticated arrival pack retain their original scope. Search/export issue no service requests or domain writes and store no browser preferences.

Refresh clears results and disables search/reset/matching export while retaining the typed query for recovery. Only a supported current response restores results; outage and unsupported metadata leave old rows/export unavailable. The existing request sequence prevents a late response from replacing a newer plan. No endpoint, schema, source plan, matrix, map or electrical instruction changes. Disposable browser verification covers literal matching across all fields, exact subset exports, scope separation, empty/reset, independent catalog filters, outage/retry, stale responses, auditor access, keyboard, contrast and five widths.

## Offline arrival ZIP consistency check

The arrival pack now includes `dashboard/verify_arrival_pack.py`, a standard-library-only checker. Prefer an independently reviewed repository copy, run from the dashboard directory before extracting the ZIP:

```powershell
python verify_arrival_pack.py "path/to/edgeops-hardware-arrival-pack.zip"
```

It prints JSON and exits 0 for internal file consistency or 2 for an unavailable, damaged or unsupported archive. It does not extract, import or execute archive members, contact services, open hardware, write output files or change the ZIP. The input cap is 8 MiB, each member is capped at 512 KiB, the manifest at 64 KiB, and expanded non-manifest content at 2 MiB. Only the exact current file set is accepted; duplicate/extra/missing/path-traversal entries, links, encryption and unsupported compression are refused. Each manifest size/hash must agree with the captured member bytes. The supported 30-row plan/matrix/map and untouched blank receipt worksheet must agree. Edited receipt worksheets belong in separate working copies; they are not the unopened export template.

An untrusted ZIP's own checker is not a trust anchor. Hashes can be rewritten together: this is not a signature, trusted release, supplier/model verification, electrical review or commissioning evidence. The report explicitly keeps source-authenticity, signature, physical-acceptance, connected, equipment and production flags false. The script's file list is also the arrival builder's source allowlist, preventing separate export/checker file lists from drifting. Older exports without the checker are outside this version's supported exact structure; obtain a fresh download.

Twelve disposable tests cover a real generated pack and bundled script, size/hash corruption, forged/rehashed inconsistent records, duplicates/missing/extra/unsafe paths, link types, bounded content, malformed/duplicate/deep JSON, unsupported authority, changed matrix/map/worksheet, truncated ZIPs, standalone isolated execution, exit codes, unchanged input bytes and no extracted files. Existing authenticated pack/source and dashboard browser tests remain in place. No selected hardware, source wiring note, physical record, endpoint or schema changes.

## Local receipt worksheet review

Hardware now offers a local working-copy CSV preview. It reads up to 128 KiB of UTF-8 CSV, including a BOM, LF/CRLF row endings and quoted commas, quotes or embedded newlines. The ten original headers, all 30 ordered P/BOM identities, family, quantity basis and role must match the separately loaded fixed plan exactly. Fields are bounded at 2,000 characters. Owner model/revision, received-date declaration, label/photo reference and notes remain unverified text; a nonblank date must be calendar-valid YYYY-MM-DD. Record status accepts only `awaiting-delivery-unverified` or `owner-notes-unverified`. Neither status establishes receipt or compatibility. Missing/extra/reordered rows, changed planning fields, malformed CSV, invalid dates/statuses, oversized fields/files and invalid UTF-8 are refused with no retained prior preview.

The preview counts model declarations and rows with notes, not physically received/accepted items. It offers exact-BOM links back to existing preparation notes and a local JSON export preserving the owner text, file name/byte count/SHA-256 and loaded plan references. Upload/persistence/order/receipt/physical-acceptance/connection/equipment/production/additional-hardware/substitution flags remain false. It performs no service reads or writes, stores no browser preference or database record, and does not inspect referenced photos. Input/notes render as text, including formula-like strings; there is no CSV re-export or automatic interpretation of board labels.

Clear review removes the selected file, rows, references and export and restores file-picker focus. Choosing a new file clears prior results immediately; delayed reads cannot replace a newer selection or resurrect cleared content. Plan refresh also clears the preview and file; outage disables file selection/export, and retry does not restore private notes. Reloading the page clears the review. Keep the original CSV working copy separately; the local review export is not a receipt register or commissioning evidence. The unopened arrival ZIP remains unchanged for the separate archive checker.

The disposable browser suite covers blank and owner-noted worksheets, exact bytes/hash/JSON and false authority, quoted multiline CSV, literal text, invalid files and identity/scope, no upload/service calls, clear/new-file races, plan outage/retry, source-link keyboard focus, auditor access, contrast, five widths and reload clearing. No physical hardware, source plan/matrix/map, authenticated receipt endpoint or database schema is added.
