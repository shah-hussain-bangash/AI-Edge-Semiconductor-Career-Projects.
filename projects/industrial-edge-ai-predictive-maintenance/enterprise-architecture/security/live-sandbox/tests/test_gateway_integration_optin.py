"""EA-29 real localhost MQTT delivery + in-process FastAPI gateway tests.

Opt-in because a real running loopback Mosquitto with disposable test PKI
is required. These are NOT standalone HTTP-network or production IAM tests.
"""
from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import api
from gateway import Gateway, publish_synthetic, synthetic_sample, TOPIC


@unittest.skipUnless(os.environ.get("EDGEOPS_GATEWAY_TEST") == "1",
                     "EA-29 requires opt-in and a running local MQTT broker")
class LocalGatewayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker CLI unavailable")
        if not all((HERE / "generated" / p).exists()
                   for p in ("ca.crt", "gateway-a.crt", "gateway-a.key",
                             "device-a.crt", "device-a.key")):
            raise unittest.SkipTest("Generate disposable local test certificates")
        proc = subprocess.run(
            ["docker", "compose", "-f", str(HERE / "compose.yaml"),
             "ps", "--status", "running", "--services"],
            cwd=str(HERE), capture_output=True, text=True, timeout=15)
        if proc.returncode != 0 or "broker" not in proc.stdout.split():
            raise unittest.SkipTest("EA-29 local broker not running")

    def setUp(self):
        api.EVENTS.clear()
        self.gateway = Gateway().start()

    def tearDown(self):
        self.gateway.stop()

    def assert_delivered(self, payload, expected):
        ack = publish_synthetic(payload)
        self.assertIn(ack, (0, 16), f"broker PUBACK={ack}")
        self.assertEqual(self.gateway.await_result(), expected)

    def test_01_broker_to_api_valid_synthetic_telemetry(self):
        self.assert_delivered(synthetic_sample(101), ("accepted", 202))
        self.assertEqual(len(api.EVENTS), 1)
        self.assertEqual(api.EVENTS[0]["sequence"], 101)

    def test_02_duplicate_sequence_rejected_in_gateway(self):
        payload = synthetic_sample(102)
        self.assert_delivered(payload, ("accepted", 202))
        self.assert_delivered(payload, ("duplicate_rejected", None))
        self.assertEqual(len(api.EVENTS), 1)

    def test_03_invalid_json_rejected_before_api(self):
        self.assert_delivered(b'{"invalid": ', ("json_rejected", None))
        self.assertEqual(api.EVENTS, [])

    def test_04_invalid_schema_rejected_before_api(self):
        bad = synthetic_sample(104)
        bad.pop("timestamp")
        self.assert_delivered(bad, ("schema_rejected", None))
        self.assertEqual(api.EVENTS, [])

    def test_05_cross_site_identity_in_message_rejected(self):
        bad = synthetic_sample(105)
        bad["site_id"] = "site-b"
        self.assert_delivered(bad, ("registry_rejected", None))
        self.assertEqual(api.EVENTS, [])

    def test_06_unregistered_asset_rejected(self):
        bad = synthetic_sample(106)
        bad["asset_id"] = "motor-b"
        self.assert_delivered(bad, ("registry_rejected", None))
        self.assertEqual(api.EVENTS, [])

    def test_07_invalid_sensor_flag_numeric_reading_rejected(self):
        bad = synthetic_sample(107)
        bad["quality"]["ina219"] = "invalid"
        self.assert_delivered(bad, ("schema_rejected", None))
        self.assertEqual(api.EVENTS, [])

    def test_08_wrong_gateway_api_role_denied(self):
        self.gateway.stop()
        self.gateway = Gateway(jwt_subject="operator-a").start()
        self.assert_delivered(synthetic_sample(108), ("api_rejected", 403))
        self.assertEqual(api.EVENTS, [])

    def test_09_two_distinct_sequences_accepted(self):
        self.assert_delivered(synthetic_sample(109), ("accepted", 202))
        self.assert_delivered(synthetic_sample(110), ("accepted", 202))
        self.assertEqual(len(api.EVENTS), 2)

    def test_10_non_synthetic_source_rejected(self):
        bad = synthetic_sample(111)
        bad["source_type"] = "measured"
        self.assert_delivered(bad, ("registry_rejected", None))
        self.assertEqual(api.EVENTS, [])

    def test_11_gateway_rejects_unexpected_topic_without_network(self):
        self.assertEqual(self.gateway.forward("wrong/topic", b"{}"),
                         ("topic_or_size_rejected", None))
        self.assertEqual(api.EVENTS, [])

    def test_12_gateway_rejects_oversize_without_network(self):
        self.assertEqual(self.gateway.forward(TOPIC, b"x" * 65537),
                         ("topic_or_size_rejected", None))
        self.assertEqual(api.EVENTS, [])


if __name__ == "__main__":
    unittest.main()
