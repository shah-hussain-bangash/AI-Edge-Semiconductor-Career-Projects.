"""EA-25 reproducible offline zero-trust authorization policy checks.

From enterprise-architecture/:
    python -m unittest discover -s security/tests -v

Mock principals, policy and resources only. Not evidence that actual OIDC,
certificate authentication, a broker, FastAPI or agent runtime is secured.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

POLICY_DIR = Path(__file__).resolve().parents[1] / "policy"
sys.path.insert(0, str(POLICY_DIR))
from edgeops_policy import POLICY, authorize  # noqa: E402

PRINCIPALS = {p["id"]: p for p in POLICY["fixtures"]["principals"]}


def asset(site="site-a", aid="motor-a"):
    return {"type": "asset", "site_id": site, "asset_id": aid}


def telemetry(site="site-a", aid="motor-a", device="device-a"):
    return {"type": "telemetry", "site_id": site, "asset_id": aid, "device_id": device}


def sop(site="site-a", aid="motor-a"):
    return {"type": "sop", "site_id": site, "asset_id": aid}


def workorder(creator="operator-a", version=3):
    return {"type": "workorder", "site_id": "site-a", "asset_id": "motor-a",
            "created_by": creator, "current_version": version}


class ZeroTrustPolicyTests(unittest.TestCase):
    def allow(self, principal, action, resource, **kwargs):
        self.assertTrue(authorize(PRINCIPALS[principal], action, resource, **kwargs))

    def deny(self, principal, action, resource, **kwargs):
        self.assertFalse(authorize(PRINCIPALS[principal], action, resource, **kwargs))

    def test_01_own_device_can_publish(self):
        self.allow("device-a", "telemetry.publish", telemetry())

    def test_02_other_device_topic_denied(self):
        self.deny("device-a", "telemetry.publish", telemetry(device="device-b"))

    def test_03_cross_site_device_denied(self):
        self.deny("device-a", "telemetry.publish", telemetry(site="site-b"))

    def test_04_cross_asset_device_denied(self):
        self.deny("device-a", "telemetry.publish", telemetry(aid="motor-b"))

    def test_05_ingestor_service_can_ingest_scoped_data(self):
        self.allow("gateway-a", "telemetry.ingest", telemetry())

    def test_06_ingestor_wrong_site_denied(self):
        self.deny("gateway-a", "telemetry.ingest", telemetry(site="site-b"))

    def test_07_operator_reads_assigned_asset(self):
        self.allow("operator-a", "asset.read", asset())

    def test_08_operator_cross_site_denied(self):
        self.deny("operator-a", "asset.read", asset(site="site-b"))

    def test_09_operator_cross_asset_denied(self):
        self.deny("operator-a", "asset.read", asset(aid="motor-b"))

    def test_10_unknown_action_denied(self):
        self.deny("operator-a", "asset.delete", asset())

    def test_11_operator_cannot_approve(self):
        self.deny("operator-a", "workorder.approve", workorder(),
                  context={"expected_version": 3})

    def test_12_reviewer_can_approve_current_version(self):
        self.allow("reviewer-a", "workorder.approve", workorder(),
                   context={"expected_version": 3})

    def test_13_reviewer_cannot_self_approve(self):
        self.deny("reviewer-a", "workorder.approve", workorder(creator="reviewer-a"),
                  context={"expected_version": 3})

    def test_14_stale_version_denied(self):
        self.deny("reviewer-a", "workorder.approve", workorder(),
                  context={"expected_version": 2})

    def test_15_missing_version_denied(self):
        self.deny("reviewer-a", "workorder.approve", workorder())

    def test_16_boolean_version_denied(self):
        self.deny("reviewer-a", "workorder.approve", workorder(),
                  context={"expected_version": True})

    def test_17_operator_can_read_authorized_sop(self):
        self.allow("operator-a", "sop.read", sop())

    def test_18_rag_service_can_read_authorized_sop(self):
        self.allow("rag-a", "sop.read", sop())

    def test_19_rag_service_denied_cross_site(self):
        self.deny("rag-a", "sop.read", sop(site="site-b"))

    def test_20_agent_can_only_draft_assigned_workorder(self):
        self.allow("agent-a", "workorder.draft", workorder())

    def test_21_agent_cannot_approve_workorder(self):
        self.deny("agent-a", "workorder.approve", workorder(),
                  context={"expected_version": 3})

    def test_22_agent_cannot_control_motor(self):
        self.deny("agent-a", "motor.start", workorder())

    def test_23_device_cannot_control_motor(self):
        self.deny("device-a", "motor.stop", telemetry())

    def test_24_agent_cannot_run_shell(self):
        self.deny("agent-a", "shell.execute", workorder())

    def test_25_agent_cannot_grant_role(self):
        self.deny("agent-a", "admin.grant_role", workorder())

    def test_26_unknown_principal_roles_denied(self):
        actor = copy.deepcopy(PRINCIPALS["operator-a"])
        actor["roles"] = []
        self.assertFalse(authorize(actor, "asset.read", asset()))

    def test_27_missing_scope_denied(self):
        resource = asset()
        del resource["site_id"]
        self.deny("operator-a", "asset.read", resource)

    def test_28_missing_resource_type_denied(self):
        resource = asset()
        del resource["type"]
        self.deny("operator-a", "asset.read", resource)

    def test_29_agent_cross_asset_draft_denied(self):
        resource = workorder()
        resource["asset_id"] = "motor-b"
        self.deny("agent-a", "workorder.draft", resource)

    def test_30_unavailable_identity_denied(self):
        self.assertFalse(authorize({}, "asset.read", asset()))

    def test_31_approval_wrong_resource_type_denied(self):
        self.deny("reviewer-a", "workorder.approve", asset(),
                  context={"expected_version": 3})

    def test_32_role_without_principal_type_denied(self):
        actor = copy.deepcopy(PRINCIPALS["operator-a"])
        actor["type"] = "agent"
        self.assertFalse(authorize(actor, "asset.read", asset()))

    def test_33_unknown_policy_action_denied(self):
        self.deny("reviewer-a", "credential.read", workorder())

    def test_34_approver_must_have_creator_id(self):
        resource = workorder()
        del resource["created_by"]
        self.deny("reviewer-a", "workorder.approve", resource,
                  context={"expected_version": 3})


if __name__ == "__main__":
    unittest.main()
