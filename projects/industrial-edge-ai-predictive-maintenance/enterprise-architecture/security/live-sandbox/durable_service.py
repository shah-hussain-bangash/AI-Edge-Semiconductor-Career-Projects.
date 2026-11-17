"""EA-30 local-only independent HTTP FastAPI ingestion with SQLite durability.

Intentionally TEST-ONLY: shared HS256 fixture key (not OIDC), HTTP loopback (not
TLS), one fixed synthetic device registry, no operational controls or hardware.
No self-minted bearer endpoint. Always set test key and DB path via environment.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import jwt
from fastapi import FastAPI, Header, HTTPException, Response
from jsonschema import Draft202012Validator, FormatChecker

ARCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ARCH / "security" / "policy"))
from edgeops_policy import POLICY, authorize  # noqa: E402

SCHEMA = json.loads((ARCH / "contracts" / "telemetry-v2.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
ISSUER = "edgeops-ea30-local-fixture-issuer"
AUDIENCE = "edgeops-ea30-local-api"
REGISTRY = {"device-a": {"site_id": "site-a", "asset_id": "motor-a"}}
PRINCIPALS = {p["id"]: p for p in POLICY["fixtures"]["principals"]}
app = FastAPI(title="EDGEOPS EA-30 loopback-only durable lab", docs_url=None, redoc_url=None)


def settings() -> tuple[str, Path]:
    key = os.environ.get("EDGEOPS_EA30_SIGNING_KEY", "")
    raw = os.environ.get("EDGEOPS_EA30_DB_PATH", "")
    if len(key) < 32 or not raw:
        raise RuntimeError("EA-30 requires test-only SIGNING_KEY (>=32 chars) and DB_PATH")
    return key, Path(raw).resolve()


def connect_db() -> sqlite3.Connection:
    _, path = settings()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10)
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            device_id TEXT NOT NULL,
            boot_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            site_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            received_utc TEXT NOT NULL,
            PRIMARY KEY (device_id, boot_id, sequence)
        )
    """)
    return db


def authenticate(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "bearer token required")
    key, _ = settings()
    try:
        claims = jwt.decode(
            authorization[7:], key, algorithms=["HS256"],
            issuer=ISSUER, audience=AUDIENCE,
            options={"require": ["sub", "iss", "aud", "exp", "iat"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid test token") from None
    principal = PRINCIPALS.get(claims.get("sub"))
    if principal is None:
        raise HTTPException(401, "unrecognized fixture principal")
    return principal


@app.get("/health")
def health():
    # loopback-only demo. No secret or DB content disclosed.
    return {"service": "ea30", "scope": "synthetic-local-only"}


@app.post("/telemetry", status_code=201)
def telemetry(payload: dict, response: Response, authorization: str | None = Header(default=None)):
    principal = authenticate(authorization)
    if not VALIDATOR.is_valid(payload):
        raise HTTPException(422, "invalid telemetry contract")
    if payload["source_type"] != "synthetic":
        raise HTTPException(422, "non-synthetic source not accepted")
    # Fail closed on unverified sessions: duplicate-free across restart
    # cannot be honestly claimed when boot_id is null or inferred.
    if (not payload["boot_id"] or
            payload["quality"]["session_quality"] != "verified"):
        raise HTTPException(422, "verified boot session required for this demo")
    registered = REGISTRY.get(payload["device_id"])
    if not registered or any(payload[field] != registered[field] for field in ("site_id", "asset_id")):
        raise HTTPException(403, "unknown or mismatched registered device")
    resource = {"type": "telemetry", "site_id": payload["site_id"],
                "asset_id": payload["asset_id"], "device_id": payload["device_id"]}
    if not authorize(principal, "telemetry.ingest", resource):
        raise HTTPException(403, "forbidden")

    db = connect_db()
    try:
        with db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO telemetry
                   (device_id, boot_id, sequence, site_id, asset_id, payload_json, received_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (payload["device_id"], payload["boot_id"], payload["sequence"],
                 payload["site_id"], payload["asset_id"],
                 json.dumps(payload, separators=(",", ":"), sort_keys=True),
                 datetime.now(timezone.utc).isoformat()),
            )
            accepted = cursor.rowcount == 1
        response.status_code = 201 if accepted else 200
    finally:
        db.close()
    # Ack follows SQLite transaction commit; no exactly-once external delivery claim.
    return {"stored": accepted, "duplicate": not accepted,
            "durable": True, "ack": "sqlite-committed"}


@app.get("/telemetry/count")
def count(authorization: str | None = Header(default=None)):
    principal = authenticate(authorization)
    # Never expose cross-scope data to arbitrary human users.
    if principal.get("id") != "gateway-a" or "ingestor" not in principal.get("roles", []):
        raise HTTPException(403, "forbidden")
    db = connect_db()
    try:
        return {"count": db.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]}
    finally:
        db.close()
