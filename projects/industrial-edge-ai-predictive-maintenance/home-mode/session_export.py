"""Derived home-session packages; never raw acquisition or physical acceptance."""
from collections import Counter
from contextlib import closing
from datetime import datetime
import csv
import hashlib
import io
import re
import zipfile
from home_core import BOUNDARY, CHANNELS, canonical, strict_json, utc_now


def checked_rows(store, session_id):
    if not isinstance(session_id, str) or not re.fullmatch('[a-f0-9]{32}', session_id):
        raise ValueError('No reader session is available')
    with closing(store.connect()) as db:
        rows = db.execute('SELECT * FROM home_samples WHERE session_id=? ORDER BY id LIMIT 10001', (session_id,)).fetchall()
    if len(rows) > 10000: raise ValueError('Session package exceeds 10000 retained rows')
    result = []
    for row in rows:
        raw = row['payload_json']
        if hashlib.sha256(raw.encode()).hexdigest() != row['content_hash']:
            raise ValueError('Session integrity check failed')
        item = strict_json(raw)
        if item['session_id'] != session_id or item['source'] != row['source'] or item['received_at'] != row['received_at']:
            raise ValueError('Session metadata integrity check failed')
        if item['source'] not in ('simulated', 'serial-unverified') or any(item.get(k) is not False for k in ('production_ready', 'hardware_verified', 'calibration_verified', 'equipment_authorized')):
            raise ValueError('Unsupported session verification labels')
        result.append(item)
    return result


def summarize(snapshot):
    items = snapshot['items']
    if len(items) > snapshot['accepted']: raise ValueError('Session count integrity check failed')
    counts = Counter(item['source'] for item in items)
    available = {c[0]: sum(item['values'][c[0]] is not None for item in items) for c in CHANNELS}
    gaps = duplicates = resets = 0
    previous = None
    for item in items:
        seq, uptime = item['device_sequence'], item['device_uptime_ms']
        if seq is None or uptime is None: previous = None; continue
        if previous is not None:
            if uptime < previous[1] or seq < previous[0]: resets += 1
            elif seq == previous[0]: duplicates += 1
            else: gaps += max(0, seq - previous[0] - 1)
        previous = (seq, uptime)
    first = items[0]['received_at'] if items else None
    last = items[-1]['received_at'] if items else None
    span = (datetime.fromisoformat(last) - datetime.fromisoformat(first)).total_seconds() if first else None
    complete = len(items) == snapshot['accepted']
    return dict(format='edgeops-home-session-v1', session_id=snapshot['session_id'], mode=snapshot['mode'],
        generated_at=utc_now(), reader_state_at_snapshot=snapshot['state'], reader_notice=snapshot['error'],
        accepted_at_snapshot=snapshot['accepted'], rejected_at_snapshot=snapshot['rejected'],
        retained_records=len(items), all_accepted_records_retained=complete,
        missing_accepted_records=max(0, snapshot['accepted'] - len(items)),
        source_counts=dict(counts), available_value_counts=available,
        first_host_receipt_utc=first, last_host_receipt_utc=last,
        host_receipt_span_seconds=span, device_sequence_gaps=gaps,
        device_duplicate_sequences=duplicates, device_sequence_or_uptime_resets=resets,
        summary_scope='retained accepted records only; malformed frames and exact wire bytes are not archived',
        receipt_span_is_run_duration=False, device_clock_verified=False,
        physical_acceptance='pending', raw_serial_capture_included=False,
        calibration_references_included=False, **BOUNDARY)


def build_package(snapshot):
    manifest = summarize(snapshot)
    items = snapshot['items']
    samples = ''.join(canonical(item) + '\n' for item in items).encode('utf-8')
    stream = io.StringIO(newline='')
    fields = ['received_at', 'session_id', 'source', 'mode', 'kind', 'device_id', 'device_sequence', 'device_uptime_ms']
    fields += [c[0] for c in CHANNELS] + [c[0] + '_quality' for c in CHANNELS]
    fields += ['hardware_verified', 'calibration_verified', 'production_ready', 'equipment_authorized']
    writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
    for item in items:
        row = {k: item.get(k) for k in fields}
        row.update(item['values']); row.update({k + '_quality': v for k, v in item['sensor_quality'].items()})
        writer.writerow(row)
    files = {'samples.jsonl': samples, 'samples.csv': stream.getvalue().encode('utf-8')}
    manifest['files'] = {name: dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)) for name, data in files.items()}
    files['manifest.json'] = (canonical(manifest) + '\n').encode('utf-8')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items(): archive.writestr(name, data)
    return output.getvalue()
