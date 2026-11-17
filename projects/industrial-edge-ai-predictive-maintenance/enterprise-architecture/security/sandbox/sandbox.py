"""EA-27 in-memory security-integration sandbox (synthetic identities only).

NOT a broker, TLS implementation, OIDC issuer, API service, or OT controller.
Mock credential handles authenticate against a fixed in-memory registry;
never use this as a production authentication implementation.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "security" / "policy"))
from edgeops_policy import authorize, POLICY  # noqa: E402

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = json.loads((ROOT / "contracts" / "telemetry-v2.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
BASE = json.loads((ROOT / "contracts" / "examples" / "telemetry-v2.synthetic-valid.json").read_text(encoding="utf-8"))

# These handles are synthetic tokens, not cryptographic secrets or credentials.
MOCK_HANDLES = {
    "fixture:device-a": "device-a",
    "fixture:gateway-a": "gateway-a",
    "fixture:operator-a": "operator-a",
    "fixture:reviewer-a": "reviewer-a",
    "fixture:rag-a": "rag-a",
    "fixture:agent-a": "agent-a",
    "fixture:operator-b": "operator-b",
}
MOCK_PRINCIPALS = {p["id"]: p for p in POLICY["fixtures"]["principals"]}
ASSET_REGISTRY = {
    "device-a": {"site_id": "site-a", "asset_id": "motor-a", "device_id": "device-a"}
}
TOPIC = "edgeops/v1/site-a/device-a/telemetry"


class SandboxDenied(Exception):
    """Denied access or invalid data in the in-memory demonstrator."""


class Sandbox:
    def __init__(self):
        self.accepted = []
        self.audit = []
        self.pending = {}

    def _principal(self, handle: str):
        pid = MOCK_HANDLES.get(handle) if isinstance(handle, str) else None
        principal = MOCK_PRINCIPALS.get(pid)
        if principal is None:
            self.audit.append(("authentication", "deny"))
            raise SandboxDenied("unauthenticated fixture")
        return principal

    def _authorize(self, principal, action, resource, *, context=None):
        ok = authorize(principal, action, resource, context=context)
        self.audit.append((action, "allow" if ok else "deny"))
        if not ok:
            raise SandboxDenied("authorization denied")
        return True

    def publish(self, handle: str, topic: str, payload: dict):
        """Simulate broker ACL, schema, and device registry binding."""
        principal = self._principal(handle)
        if not isinstance(topic, str) or topic != TOPIC:
            self.audit.append(("topic_acl", "deny"))
            raise SandboxDenied("topic ACL denied")
        if not isinstance(payload, dict):
            raise SandboxDenied("invalid payload")
        device_id = payload.get("device_id")
        registration = ASSET_REGISTRY.get(device_id)
        if (not registration or principal.get("device_id") != device_id
                or payload.get("site_id") != registration["site_id"]
                or payload.get("asset_id") != registration["asset_id"]):
            self.audit.append(("registry_binding", "deny"))
            raise SandboxDenied("registry identity mismatch")
        resource = {"type": "telemetry", **registration}
        self._authorize(principal, "telemetry.publish", resource)
        if not VALIDATOR.is_valid(payload):
            self.audit.append(("schema", "deny"))
            raise SandboxDenied("schema violation")
        # Further semantic enforcement will be needed in a real V2 adapter.
        key = (device_id, payload.get("boot_id"), payload.get("sequence"))
        if key in self.pending:
            raise SandboxDenied("duplicate fixture")
        # A null boot_id does not allow strong cross-restart deduplication.
        if payload.get("boot_id") is None:
            self.audit.append(("session_identity", "ambiguous"))
        self.pending[key] = copy.deepcopy(payload)
        return key

    def ingest(self, handle: str, key: tuple):
        principal = self._principal(handle)
        payload = self.pending.get(key)
        if payload is None:
            raise SandboxDenied("unknown queued event")
        resource = {"type": "telemetry", "site_id": payload["site_id"],
                    "asset_id": payload["asset_id"], "device_id": payload["device_id"]}
        self._authorize(principal, "telemetry.ingest", resource)
        self.accepted.append(copy.deepcopy(payload))
        del self.pending[key]
        return len(self.accepted)

    def read_asset(self, handle: str, site: str, asset: str):
        principal = self._principal(handle)
        resource = {"type": "asset", "site_id": site, "asset_id": asset}
        self._authorize(principal, "asset.read", resource)
        return {"site_id": site, "asset_id": asset, "status": "synthetic"}

    def read_sop(self, handle: str, site: str, asset: str):
        principal = self._principal(handle)
        resource = {"type": "sop", "site_id": site, "asset_id": asset}
        self._authorize(principal, "sop.read", resource)
        return {"citation": "synthetic:sop-001", "text": "Inspect and escalate to human."}

    def draft_workorder(self, handle: str, site: str, asset: str):
        principal = self._principal(handle)
        resource = {"type": "workorder", "site_id": site, "asset_id": asset}
        self._authorize(principal, "workorder.draft", resource)
        return {"created_by": principal["id"], "site_id": site, "asset_id": asset,
                "current_version": 1, "type": "workorder"}

    def approve_workorder(self, handle: str, workorder: dict, expected_version: int):
        principal = self._principal(handle)
        self._authorize(principal, "workorder.approve", workorder,
                        context={"expected_version": expected_version})
        return "synthetic-approved"

    def agent_tool(self, handle: str, action: str, site: str, asset: str):
        principal = self._principal(handle)
        resource = {"type": "workorder", "site_id": site, "asset_id": asset}
        self._authorize(principal, action, resource)
        return "synthetic-allowed"


def sample():
    """Return synthetic measured-data-shaped fixture without claiming measurement."""
    obj = copy.deepcopy(BASE)
    obj["site_id"] = "site-a"
    obj["asset_id"] = "motor-a"
    obj["device_id"] = "device-a"
    return obj
