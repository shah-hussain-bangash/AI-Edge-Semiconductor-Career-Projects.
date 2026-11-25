#!/usr/bin/env python3
"""Summarize an existing verified offline capture; no serial or network access."""
import argparse
import csv
from datetime import datetime, timezone
import math
from pathlib import Path
import statistics

import prepare_capture as evidence


def summarize(directory):
    root = Path(directory)
    verification = evidence.verify(root, include_report=True)
    manifest = verification['manifest']
    raw = evidence.read_file(root / 'observations.jsonl', evidence.EVIDENCE_LIMITS['observations.jsonl'])
    if manifest['files']['observations.jsonl'] != {'bytes': len(raw), 'sha256': evidence.sha(raw)}:
        raise ValueError('Evidence changed before summary')
    records = evidence.evidence_lines(raw, 16384)
    times = [evidence.utc(row['timestamp']['gateway_received_utc']) for row in records]
    intervals = [(later - earlier).total_seconds() for earlier, later in zip(times, times[1:])]
    ordered = sorted(intervals)
    span = (times[-1] - times[0]).total_seconds() if times else None
    groups = {}
    for sensor in ('adxl345', 'ds18b20', 'ina219'):
        valid = sum(row['quality'][sensor] == 'valid' for row in records)
        groups[sensor] = {'valid_rows': valid, 'invalid_rows': len(records) - valid}
    return {
        'format': 'edgeops-offline-capture-summary-v1',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_manifest_sha256': verification['manifest_sha256'],
        'source_type': manifest['source_type'],
        'input_rows': manifest['input_rows'], 'accepted_rows': manifest['accepted_rows'],
        'quarantined_rows': manifest['quarantined_rows'],
        'accepted_sequence_gaps': manifest['accepted_sequence_gaps'],
        'requires_review': manifest['requires_review'], 'sensor_groups': groups,
        'timing': {
            'basis': 'declared gateway receipt times of accepted records in source order',
            'interval_count': len(intervals), 'receipt_span_seconds': span,
            'interval_median_seconds': statistics.median(intervals) if intervals else None,
            'interval_p95_seconds': ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else None,
            'interval_max_seconds': max(intervals) if intervals else None,
            'zero_interval_count': intervals.count(0),
            'observed_receipt_rate_hz': (len(records) - 1) / span if span is not None and span > 0 else None,
            'capture_elapsed_verified': False, 'sensor_sampling_rate_verified': False},
        'physical_acceptance': 'pending', 'physical_source_verified': False,
        'calibration_verified': False, 'hardware_connected': False,
        'equipment_authorized': False, 'ready_for_ingestion': False, 'production_ready': False,
        'atomic_folder_snapshot': False,
        'limitations': 'Descriptive statistics only. Quarantined records are excluded from timing and sensor counts. Receipt span is not capture duration or sensor sampling rate. H1 still requires start/stop records, stop reason, first-600-second counts, reference comparisons and independent physical review. No threshold or acceptance decision is applied.'}


def write_summary(directory, output):
    root = Path(directory).resolve()
    target = Path(output).absolute()
    if target.resolve().is_relative_to(root):
        raise ValueError('Summary must be outside the evidence folder')
    if target.exists() or target.is_symlink():
        raise ValueError('Summary must use a new filename')
    report = summarize(directory)
    with target.open('xb') as stream:
        stream.write(evidence.json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--output', required=True, help='New JSON filename outside the evidence folder')
    args = parser.parse_args()
    try:
        write_summary(args.directory, args.output)
    except (ValueError, OSError, KeyError, TypeError, csv.Error):
        parser.exit(1, 'Capture summary failed; check the verified evidence and new output filename.\n')
    print('Saved descriptive offline summary; physical acceptance remains pending.')


if __name__ == '__main__':
    main()
