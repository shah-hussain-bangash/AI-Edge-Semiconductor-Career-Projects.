"""Isolated synthetic telemetry ledger. No hardware or model integration.

Uses a separate SQLite database to avoid modifying the operator's existing
dashboard auth/audit database. The only accepted provenance is synthetic-demo.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get(
    "EDGEOPS_SYNTHETIC_TELEMETRY_DB",
    str(ROOT / ".local" / "synthetic-telemetry.sqlite3")
)).resolve()


@contextmanager
def connect():
    """Commit or roll back work, then always close the SQLite file handle.

    sqlite3.Connection.__exit__ alone handles transactions but does not close
    the connection. Explicit close is required for Windows temp cleanup.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        with db:
            yield db
    finally:
        db.close()


def init_store():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS synthetic_telemetry(
            event_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            vibration_mm_s REAL NOT NULL,
            temperature_c REAL NOT NULL,
            current_a REAL NOT NULL,
            provenance TEXT NOT NULL CHECK(provenance='synthetic-demo'),
            payload_hash TEXT NOT NULL,
            ingested_at TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS ix_synthetic_asset_time ON synthetic_telemetry(asset_id, captured_at)")


def append_event(event):
    """Return (inserted, record), rejecting reuse of an ID with new values."""
    payload = {
        "event_id": event.event_id,
        "asset_id": event.asset_id,
        "captured_at": event.captured_at.astimezone(timezone.utc).isoformat(),
        "vibration_mm_s": event.vibration_mm_s,
        "temperature_c": event.temperature_c,
        "current_a": event.current_a,
        "provenance": "synthetic-demo",
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    ingest_time = datetime.now(timezone.utc).isoformat()
    init_store()
    with connect() as db:
        row = db.execute("SELECT payload_hash FROM synthetic_telemetry WHERE event_id=?", (event.event_id,)).fetchone()
        if row:
            if row["payload_hash"] != digest:
                raise ValueError("event_id is already used by a different synthetic event")
            return False, payload
        try:
            db.execute(
                """INSERT INTO synthetic_telemetry
                (event_id,asset_id,captured_at,vibration_mm_s,temperature_c,current_a,
                 provenance,payload_hash,ingested_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (payload["event_id"], payload["asset_id"], payload["captured_at"],
                 payload["vibration_mm_s"], payload["temperature_c"], payload["current_a"],
                 "synthetic-demo", digest, ingest_time)
            )
        except sqlite3.IntegrityError:
            existing = db.execute("SELECT payload_hash FROM synthetic_telemetry WHERE event_id=?", (event.event_id,)).fetchone()
            if not existing or existing["payload_hash"] != digest:
                raise ValueError("event_id is already used by a different synthetic event")
            return False, payload
    return True, payload


def read_events(asset_id=None, limit=100):
    init_store()
    limit = max(1, min(500, int(limit)))
    with connect() as db:
        if asset_id:
            rows = db.execute(
                """SELECT event_id,asset_id,captured_at,vibration_mm_s,temperature_c,
                current_a,provenance,ingested_at FROM synthetic_telemetry
                WHERE asset_id=? ORDER BY captured_at DESC,event_id DESC LIMIT ?""",
                (asset_id, limit)).fetchall()
        else:
            rows = db.execute(
                """SELECT event_id,asset_id,captured_at,vibration_mm_s,temperature_c,
                current_a,provenance,ingested_at FROM synthetic_telemetry
                ORDER BY captured_at DESC,event_id DESC LIMIT ?""", (limit,)).fetchall()
    return [dict(row) for row in rows]
