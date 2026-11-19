"""Leakage-safe time-series features for synthetic telemetry (standard library).

Events must be explicitly marked synthetic-demo. Features are trailing-only,
computed per asset and in captured-at order; no future observations are used.
No equipment failure labels or deployed model are supplied by this module.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from math import isfinite, sqrt
from statistics import mean, pstdev

SIGNALS = ("vibration_mm_s", "temperature_c", "current_a")


def _time(value):
    if not isinstance(value, str):
        raise ValueError("captured_at must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid captured_at timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("captured_at must have an offset")
    return parsed.astimezone(timezone.utc)


def trailing_features(events, window=3, *, min_points=None):
    """Build chronological, per-asset trailing features.

    Only observations up to and including the current event are used.
    Returns rows with event_id, asset_id, timestamp, and numerical features.
    Incomplete windows are skipped; duplicate identifiers or timestamps per
    asset are rejected to prevent ambiguous causal order.
    """
    if type(window) is not int or not 2 <= window <= 100:
        raise ValueError("window must be an integer from 2 to 100")
    if min_points is None:
        min_points = window
    if type(min_points) is not int or not 2 <= min_points <= window:
        raise ValueError("min_points must be between 2 and window")
    normalized = []
    seen_ids, seen_times = set(), set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each event must be a mapping")
        if event.get("provenance") != "synthetic-demo":
            raise ValueError("only synthetic-demo telemetry is accepted")
        asset, eid = event.get("asset_id"), event.get("event_id")
        if not isinstance(asset, str) or not asset or not isinstance(eid, str) or not eid:
            raise ValueError("asset_id and event_id are required strings")
        timestamp = _time(event.get("captured_at"))
        if eid in seen_ids or (asset, timestamp) in seen_times:
            raise ValueError("duplicate event identifier or asset timestamp")
        seen_ids.add(eid)
        seen_times.add((asset, timestamp))
        values = {}
        for signal in SIGNALS:
            value = event.get(signal)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError("missing or non-finite telemetry: " + signal)
            values[signal] = float(value)
        normalized.append((timestamp, asset, eid, values))
    normalized.sort(key=lambda row: (row[0], row[1], row[2]))
    histories = {}
    output = []
    for timestamp, asset, eid, values in normalized:
        history = histories.setdefault(asset, deque(maxlen=window))
        history.append(values)
        if len(history) < min_points:
            continue
        features = {}
        for signal in SIGNALS:
            series = [row[signal] for row in history]
            features[signal + "_latest"] = series[-1]
            features[signal + "_mean"] = mean(series)
            features[signal + "_std"] = pstdev(series)
            features[signal + "_delta"] = series[-1] - series[0]
        output.append({
            "event_id": eid, "asset_id": asset,
            "captured_at": timestamp.isoformat(),
            "window_points": len(history),
            "features": features,
            "provenance": "synthetic-demo",
        })
    return output
