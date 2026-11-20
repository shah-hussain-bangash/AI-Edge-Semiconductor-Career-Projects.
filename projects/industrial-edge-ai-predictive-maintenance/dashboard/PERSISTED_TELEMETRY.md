# Persisted synthetic telemetry explorer - 20 November 2026

The Telemetry workspace now queries the central synthetic observation records created by the delivery service. It does not replace or relabel the historical browser fixtures or the separate mm/s synthetic research ledger. No measured source, physical device, inference, alert or work-order effect is introduced.

## Use

Open **View persisted telemetry** on a Device test-binding row, including a retired binding, or enter its exact test device ID in Telemetry > Persisted observation explorer. Only observations that received a central commit appear. A merely queued observation is absent until delivered. Empty and unknown bindings are explicit states; no data is generated automatically.

Choose one of six SI channels: acceleration X/Y/Z in m/s2, case temperature in C, bus voltage in V, or current in A. The newest value on a page is shown as recorded, even when missing; the interface does not substitute an earlier valid value. Zero remains a legitimate reading. Missing/invalid/stale-at-observation sensor groups are null according to the acquisition contract and create chart gaps, not zero points. Session changes break connecting lines.

The chart is equally spaced **central commit order**, not a source-time waveform. UTC commit labels show its endpoints. It does not establish sampling rate, vibration spectrum or source timing. The accessible table and JSON page export retain exact readings, units, quality, source timestamps, identity and receipt references. Existing fixture charts and CSV remain available below, with their existing provenance.

## Time, quality and age

Three timestamps remain distinct: declared device time, declared gateway receipt time and server-generated central commit time. A newly delivered backlog cannot become recent merely because its central receipt is recent.

- A declared verified synthetic device clock plus an observation timestamp permits an observation-age calculation.
- An unavailable/unverified clock remains **clock-unverified**; gateway/central receipt time is not substituted.
- Old observations are **stale** relative to the selected display threshold.
- A declared observation later than the server's snapshot time is **future-time**.
- **within-display-age** only means the declared synthetic timestamp is within that display threshold. It is not a healthy-device, trustworthy-clock or accepted-production claim.

The default 60-second threshold is an operator display policy, not an approved measurement, alert or availability target. It is bounded to 1-86400 seconds. Sensor quality and declared calibration are shown separately; a valid number does not prove calibrated hardware. All observations remain synthetic declarations.

Data is retrieved on explicit refresh/page navigation. Age labels advance locally every five seconds using elapsed monotonic browser time anchored to the server response; this does not fetch new observations. The loading timestamp is visible. The JSON export preserves the server snapshot and its as_of timestamp, not a falsely refreshed data set. Device/filter changes clear the old result and disable export until the new query succeeds. Outages clear the table/chart rather than displaying a stale result as current authority.

## Query contract

`GET /api/acquisition/observations?device_id=...&limit=50&max_age_seconds=60&before=...` is read-only for supported authenticated local roles. It is project-wide authorization, not multi-tenant/site policy. Device ID is required and bounded; limit is 1-100. The response includes binding status/site/asset, all six channel definitions, as_of, age policy, records, next_before and explicit synthetic/non-production boundaries.

History uses keyset pagination ordered by server commit time and event key. Tied timestamps are deterministic; newer arrivals do not shift an older-page cursor into repeated records. Older/newest page controls are explicit. The first page is not an asset-health calculation, and a historical page's newest row is not advertised as the current measurement. Unknown device IDs return 404. A retired binding's committed history remains readable.

The database index covers device/commit/key. Reads are bounded and use a transaction snapshot. Each returned envelope is checked against its typed contract, canonical content hash, source key, stored device/revision and immutable binding. Corrupt or inconsistent selected records return 503 without partial history. Hash checking is content integrity against stored metadata, not independent digital-signature verification or proof of a trustworthy database administrator. No PII actor field is returned.

## Verification and limits

Five API tests verify zero/null/SI semantics, clock ambiguity, stale backlog despite recent receipt, future timestamps, operator display thresholds, pagination with tied commits/new arrivals, bounded parameters, supported roles, retired history and corrupt-content rejection. The browser suite exercises real committed records, two numeric points including zero, missing-current gaps, source age states, JSON export, outage clearing/retry and navigation from Device. Existing fixture controls/exports and all 18 workspaces remain tested at five widths with text contrast checks.

This slice adds one history index and no seeded observations or changes to existing records. Production ingestion, real device clocks/calibration, fleet-wide query isolation, durable operational incidents, managed time-series retention and qualified performance/load/freshness targets remain separate work.
