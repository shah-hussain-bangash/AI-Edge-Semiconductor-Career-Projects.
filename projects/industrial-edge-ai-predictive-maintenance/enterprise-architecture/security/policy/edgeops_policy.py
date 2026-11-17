"""EA-25 offline authorization demonstrator.

This is NOT an identity provider, runtime authorization gateway, MQTT ACL, or
production implementation. The caller must authenticate principals separately.
All inputs here are synthetic and trusted only within the offline test harness.
"""
from __future__ import annotations

import json
from pathlib import Path

POLICY_PATH = Path(__file__).with_name("edgeops-zero-trust.v1.json")
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def authorize(principal: dict, action: str, resource: dict, *, context: dict | None = None,
              policy: dict | None = None) -> bool:
    """Fail closed for unknown actions, roles, scopes, or missing version proofs."""
    rules = policy if policy is not None else POLICY
    if not isinstance(principal, dict) or not isinstance(resource, dict):
        return False
    if not isinstance(action, str) or action in rules["forbidden_actions"]:
        return False
    definition = rules["actions"].get(action)
    if not definition:
        return False
    if principal.get("type") not in definition["principal_types"]:
        return False
    roles = principal.get("roles")
    if not isinstance(roles, list) or not any(
        isinstance(r, str) and r in definition["roles"] for r in roles
    ):
        return False
    if resource.get("type") != definition["resource_type"]:
        return False

    for flag, name, allowed_key in (
        ("enforce_site", "site_id", "sites"),
        ("enforce_asset", "asset_id", "assets"),
    ):
        if definition.get(flag):
            scope = resource.get(name)
            allowed = principal.get(allowed_key)
            if not isinstance(scope, str) or not scope:
                return False
            if not isinstance(allowed, list) or scope not in allowed:
                return False

    if definition.get("enforce_own_device"):
        if not isinstance(principal.get("device_id"), str):
            return False
        if resource.get("device_id") != principal["device_id"]:
            return False

    context = context if isinstance(context, dict) else {}
    if definition.get("separation_of_duties"):
        creator = resource.get("created_by")
        if not isinstance(creator, str) or not creator:
            return False
        if creator == principal.get("id"):
            return False

    if definition.get("require_current_version"):
        expected_version = context.get("expected_version")
        current_version = resource.get("current_version")
        if type(expected_version) is not int or type(current_version) is not int:
            return False
        if expected_version < 0 or expected_version != current_version:
            return False

    return True
