"""Descriptive first-window USB evidence review, never physical acceptance."""
import math
import hashlib
from statistics import median

from home_core import BOUNDARY, canonical, strict_json, utc_now
from home_recording import verify


def review(directory):
    manifest, files = verify(directory)
    events = [strict_json(line) for line in files['frames.jsonl'].splitlines()]
    # This fixed window matches the proposed H1 baseline. No user-controlled
    # threshold can turn a shorter or partial run into a 600-second result.
    window_seconds = 600
    events = [event for event in events if event['elapsed_seconds'] < window_seconds]
    counts = {kind: sum(event['kind'] == kind for event in events)
              for kind in ('accepted', 'rejected', 'diagnostic', 'partial')}
    accepted = [event for event in events if event['kind'] == 'accepted']
    times = [event['elapsed_seconds'] for event in accepted]
    intervals = [b-a for a, b in zip(times, times[1:])]
    sensor_mode = manifest['settings']['mode'] == 'sensors'
    valid = {}
    for group, keys in (
        ('adxl345', ('acceleration_x_mps2', 'acceleration_y_mps2', 'acceleration_z_mps2')),
        ('ds18b20', ('temperature_c',)),
        ('ina219', ('bus_voltage_v', 'current_a')),
    ):
        number = sum(sensor_mode and all(event['sample']['values'][key] is not None for key in keys) for event in accepted)
        valid[group] = dict(declared_valid=number, unavailable=len(accepted)-number)
    missing = duplicates = resets = 0
    previous = None
    for event in accepted:
        sample = event['sample']
        seq, uptime = sample['device_sequence'], sample['device_uptime_ms']
        if seq is None or uptime is None:
            continue
        if previous is not None:
            old_seq, old_uptime = previous
            if seq < old_seq or uptime < old_uptime:
                resets += 1
            elif seq == old_seq:
                duplicates += 1
            elif seq > old_seq + 1:
                missing += seq - old_seq - 1
        previous = seq, uptime
    ordered = sorted(intervals)
    span = times[-1] - times[0] if len(times) > 1 else None
    elapsed = manifest['elapsed_monotonic_seconds']
    issues = []
    if not sensor_mode: issues.append('communication-test-only-no-sensor-baseline')
    if manifest['requested_seconds'] != window_seconds or elapsed < window_seconds:
        issues.append('full-600-second-window-not-recorded')
    if manifest['stop_reason'] != 'duration-elapsed': issues.append('recording-did-not-finish-at-deadline')
    if manifest['withheld_read_bytes']: issues.append('raw-bytes-withheld-at-capacity-limit')
    if counts['rejected'] or counts['partial']: issues.append('rejected-or-partial-input-in-window')
    if missing or duplicates or resets: issues.append('sequence-discontinuity-needs-review')
    if any(number['declared_valid'] < 594 for number in valid.values()):
        issues.append('fewer-than-proposed-594-valid-records-per-group')
    if intervals and max(intervals) > 3: issues.append('accepted-receipt-interval-above-proposed-3-seconds')
    if times and times[0] > 3: issues.append('first-accepted-receipt-after-proposed-3-seconds')
    coverage = min(elapsed, window_seconds)
    if times and coverage - times[-1] > 3: issues.append('last-accepted-receipt-more-than-3-seconds-before-window-end')
    return dict(
        format='edgeops-home-baseline-review-v1', generated_at=utc_now(), session_id=manifest['session_id'],
        source=manifest['source'], mode=manifest['settings']['mode'], raw_integrity_reproduced=True,
        source_files=manifest['files'],
        source_manifest_canonical_sha256=hashlib.sha256(canonical(manifest).encode('utf-8')).hexdigest(),
        physical_acceptance='pending', outcome='review-required', checks_are_acceptance=False,
        observed=dict(requested_seconds=manifest['requested_seconds'], recorded_elapsed_seconds=elapsed,
                      stop_reason=manifest['stop_reason'], total_frame_counts=manifest['frame_counts'],
                      withheld_read_bytes=manifest['withheld_read_bytes']),
        window=dict(timing_basis='indexed host-monotonic receipt times after port open; not device sampling',
                    start_inclusive_seconds=0, end_exclusive_seconds=window_seconds,
                    available_seconds=coverage, frame_counts=counts, sensor_groups=valid,
                    first_accepted_receipt_seconds=times[0] if times else None,
                    last_accepted_receipt_seconds=times[-1] if times else None,
                    interval_median_seconds=median(intervals) if intervals else None,
                    interval_p95_seconds=ordered[math.ceil(.95 * len(ordered))-1] if ordered else None,
                    interval_max_seconds=max(intervals) if intervals else None,
                    observed_receipt_rate_hz=(len(times)-1)/span if span is not None and span > 0 else None,
                    records_with_device_sequence=sum(event['sample']['device_sequence'] is not None for event in accepted),
                    duplicate_receipt_times=intervals.count(0), sequence_gaps=missing,
                    duplicate_sequences=duplicates, sequence_or_uptime_resets=resets),
        proposed_targets=dict(window_seconds=600, valid_records_per_group=594, maximum_receipt_interval_seconds=3,
                              agreement_before_measurement_required=True),
        issues=issues,
        pending=['exact-part-and-wiring-review', 'firmware-build-and-configuration-provenance',
                 'pre-agreed-targets', 'sensor-reference-comparisons-and-uncertainty',
                 'independent-physical-review', 'guarded-motor-commissioning',
                 'real-data-AI-and-operational-validation'],
        limitations='Host receipt timing is not sensor sampling timing. Declared-valid flags, hashes and counts do not prove calibration, identity, acquisition continuity or physical acceptance. No vibration spectrum or failure prediction is inferred from 1 Hz summaries.',
        **BOUNDARY,
    )
