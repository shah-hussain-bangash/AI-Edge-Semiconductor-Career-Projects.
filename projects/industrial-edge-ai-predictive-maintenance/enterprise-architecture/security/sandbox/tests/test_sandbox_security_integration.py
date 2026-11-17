"""EA-27 sandbox-only integration tests; no real TLS, MQTT, OIDC or network."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox import Sandbox, SandboxDenied, TOPIC, sample  # noqa: E402


class SandboxSecurityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.lab = Sandbox()

    def assert_denied(self, method, *args):
        with self.assertRaises(SandboxDenied):
            method(*args)

    def test_01_device_publish_and_gateway_ingest(self):
        key = self.lab.publish("fixture:device-a", TOPIC, sample())
        self.assertEqual(self.lab.ingest("fixture:gateway-a", key), 1)
        self.assertEqual(self.lab.accepted[0]["source_type"], "synthetic")

    def test_02_unknown_auth_handle_denied(self):
        self.assert_denied(self.lab.publish, "invalid", TOPIC, sample())

    def test_03_cross_site_topic_denied(self):
        self.assert_denied(self.lab.publish, "fixture:device-a",
                           "edgeops/v1/site-b/device-a/telemetry", sample())

    def test_04_cross_device_topic_denied(self):
        self.assert_denied(self.lab.publish, "fixture:device-a",
                           "edgeops/v1/site-a/device-b/telemetry", sample())

    def test_05_payload_identity_mismatch_denied(self):
        payload = sample()
        payload["device_id"] = "device-b"
        self.assert_denied(self.lab.publish, "fixture:device-a", TOPIC, payload)

    def test_06_payload_asset_mismatch_denied(self):
        payload = sample()
        payload["asset_id"] = "motor-b"
        self.assert_denied(self.lab.publish, "fixture:device-a", TOPIC, payload)

    def test_07_invalid_schema_denied(self):
        payload = sample()
        payload["schema_version"] = "99"
        self.assert_denied(self.lab.publish, "fixture:device-a", TOPIC, payload)

    def test_08_invalid_sensor_numeric_fallback_denied(self):
        payload = sample()
        payload["quality"]["ina219"] = "invalid"
        self.assert_denied(self.lab.publish, "fixture:device-a", TOPIC, payload)

    def test_09_operator_cannot_publish(self):
        self.assert_denied(self.lab.publish, "fixture:operator-a", TOPIC, sample())

    def test_10_operator_cannot_ingest(self):
        key = self.lab.publish("fixture:device-a", TOPIC, sample())
        self.assert_denied(self.lab.ingest, "fixture:operator-a", key)

    def test_11_operator_reads_assigned_asset(self):
        self.assertEqual(self.lab.read_asset("fixture:operator-a", "site-a",
                                             "motor-a")["status"], "synthetic")

    def test_12_operator_cross_site_denied(self):
        self.assert_denied(self.lab.read_asset, "fixture:operator-a", "site-b", "motor-b")

    def test_13_rag_sop_read_allowed_for_assigned_site(self):
        self.assertIn("citation", self.lab.read_sop("fixture:rag-a", "site-a", "motor-a"))

    def test_14_rag_cross_site_sop_denied(self):
        self.assert_denied(self.lab.read_sop, "fixture:rag-a", "site-b", "motor-b")

    def test_15_agent_may_draft_workorder(self):
        obj = self.lab.draft_workorder("fixture:agent-a", "site-a", "motor-a")
        self.assertEqual(obj["created_by"], "agent-a")

    def test_16_agent_cannot_approve(self):
        obj = self.lab.draft_workorder("fixture:agent-a", "site-a", "motor-a")
        self.assert_denied(self.lab.approve_workorder, "fixture:agent-a", obj, 1)

    def test_17_reviewer_can_approve_operator_draft(self):
        obj = self.lab.draft_workorder("fixture:operator-a", "site-a", "motor-a")
        self.assertEqual(self.lab.approve_workorder("fixture:reviewer-a", obj, 1),
                         "synthetic-approved")

    def test_18_reviewer_self_approval_denied(self):
        obj = {"type": "workorder", "site_id": "site-a", "asset_id": "motor-a",
               "created_by": "reviewer-a", "current_version": 1}
        self.assert_denied(self.lab.approve_workorder, "fixture:reviewer-a", obj, 1)

    def test_19_stale_approval_denied(self):
        obj = self.lab.draft_workorder("fixture:operator-a", "site-a", "motor-a")
        self.assert_denied(self.lab.approve_workorder, "fixture:reviewer-a", obj, 0)

    def test_20_agent_motor_command_denied(self):
        self.assert_denied(self.lab.agent_tool, "fixture:agent-a", "motor.start",
                           "site-a", "motor-a")

    def test_21_agent_shell_command_denied(self):
        self.assert_denied(self.lab.agent_tool, "fixture:agent-a", "shell.execute",
                           "site-a", "motor-a")

    def test_22_replayed_pending_sequence_denied(self):
        payload = sample()
        self.lab.publish("fixture:device-a", TOPIC, payload)
        self.assert_denied(self.lab.publish, "fixture:device-a", TOPIC, payload)

    def test_23_missing_gateway_event_denied(self):
        self.assert_denied(self.lab.ingest, "fixture:gateway-a",
                           ("device-a", None, 999))

    def test_24_unverified_session_explicitly_ambiguous(self):
        self.lab.publish("fixture:device-a", TOPIC, sample())
        self.assertIn(("session_identity", "ambiguous"), self.lab.audit)


if __name__ == "__main__":
    unittest.main()
