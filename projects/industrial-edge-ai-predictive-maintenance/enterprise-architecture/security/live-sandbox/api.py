"""EA-28 local-only FastAPI contract test service.

Demonstrates JWT signature/issuer/audience, scoped claims, schema, source binding.
In-memory storage, ephemeral signing key, mock identities; NOT production auth.
"""
from __future__ import annotations
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import FastAPI, Header, HTTPException
from jsonschema import Draft202012Validator, FormatChecker

ARCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ARCH / "security" / "policy"))
from edgeops_policy import authorize, POLICY  # noqa: E402

SCHEMA = json.loads((ARCH / "contracts" / "telemetry-v2.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
ISS = "edgeops-synthetic-local-issuer"
AUD = "edgeops-synthetic-local-api"
KEY = secrets.token_urlsafe(48)  # process-local, ephemeral, never stored on disk
app = FastAPI(title="EDGEOPS EA-28 local-only sandbox", docs_url=None, redoc_url=None)
EVENTS = []
PRINCIPALS = {p["id"]: p for p in POLICY["fixtures"]["principals"]}
DEVICE_REGISTRY = {"device-a": {"site_id": "site-a", "asset_id": "motor-a"}}


def fixture_token(sub: str, *, audience=AUD, issuer=ISS, expires=60):
    """Test-only token issuer; do not expose via any route."""
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "iss": issuer, "aud": audience,
                       "iat": now, "exp": now + timedelta(seconds=expires)},
                      KEY, algorithm="HS256")


def get_principal(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        decoded = jwt.decode(authorization[7:], KEY, algorithms=["HS256"],
                             audience=AUD, issuer=ISS, options={"require": ["sub", "iss", "aud", "exp", "iat"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid token") from None
    principal = PRINCIPALS.get(decoded["sub"])
    if not principal:
        raise HTTPException(401, "unrecognized test principal")
    return principal


@app.post("/telemetry", status_code=202)
def ingest(payload: dict, authorization: str | None = Header(default=None)):
    principal = get_principal(authorization)
    errors = list(VALIDATOR.iter_errors(payload))
    if errors:
        raise HTTPException(422, "invalid telemetry payload")
    if payload["source_type"] != "synthetic":
        # This demonstrator does not handle measured or replayed records.
        raise HTTPException(422, "only synthetic fixtures allowed")
    # Device attestations cannot be inferred solely from request text.
    registration = DEVICE_REGISTRY.get(payload["device_id"])
    if registration is None or any(payload[k] != registration[k] for k in ("site_id", "asset_id")):
        raise HTTPException(403, "unregistered or mismatched asset")
    resource = {"type": "telemetry", "site_id": payload["site_id"],
                "asset_id": payload["asset_id"], "device_id": payload["device_id"]}
    if not authorize(principal, "telemetry.ingest", resource):
        raise HTTPException(403, "forbidden")
    # This is only an in-memory acceptance acknowledgement.
    EVENTS.append(payload.copy())
    return {"accepted": True, "durable": False, "record_count": len(EVENTS)}


@app.get("/assets/{site_id}/{asset_id}")
def read_asset(site_id: str, asset_id: str, authorization: str | None = Header(default=None)):
    principal = get_principal(authorization)
    resource = {"type": "asset", "site_id": site_id, "asset_id": asset_id}
    if not authorize(principal, "asset.read", resource):
        raise HTTPException(403, "forbidden")
    return {"site_id": site_id, "asset_id": asset_id, "status": "synthetic"}
