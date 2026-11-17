"""EA-28 real loopback Mosquitto MQTT v5 QoS 1 ACL checks.

These opt-in tests use a locally running broker and disposable test certificates.
They assert MQTT v5 PUBACK reason codes, NOT mosquitto_pub's process exit
status: MQTT v3 clients can return exit 0 even when the broker discards a
publish denied by ACL. Do not treat skips as passes.

From enterprise-architecture/security/live-sandbox:
  $env:EDGEOPS_BROKER_TEST = "1"
  python -m unittest discover -s tests -p "test_broker_optin.py" -v
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import unittest
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]
CERT = ROOT / "generated"
TOPIC_A = "edgeops/v1/site-a/device-a/telemetry"
TOPIC_B = "edgeops/v1/site-b/device-a/telemetry"


def publish_v5(identity: str, topic: str) -> int:
    """Return the broker's actual MQTT v5 QoS 1 PUBACK reason-code integer.

    Timeouts, TLS errors and MQTT disconnects fail the test (rather than being
    incorrectly treated as ACL denials).
    """
    connected = threading.Event()
    acknowledged = threading.Event()
    state: dict[str, object] = {}

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
    )
    client.tls_set(
        ca_certs=str(CERT / "ca.crt"),
        certfile=str(CERT / f"{identity}.crt"),
        keyfile=str(CERT / f"{identity}.key"),
    )

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        state["connect_code"] = int(reason_code.value)
        connected.set()

    def on_publish(_client, _userdata, _mid, reason_code, _properties):
        state["puback_code"] = int(reason_code.value)
        acknowledged.set()

    client.on_connect = on_connect
    client.on_publish = on_publish
    try:
        client.connect("localhost", 8883, keepalive=15)
        client.loop_start()
        if not connected.wait(8):
            raise AssertionError("MQTT v5 CONNACK timeout")
        if state["connect_code"] != 0:
            raise AssertionError(f"MQTT v5 CONNECT refused: {state['connect_code']}")
        info = client.publish(topic, payload="ea28-synthetic-authorization-test", qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise AssertionError(f"Client publish call failed: {info.rc}")
        if not acknowledged.wait(8):
            raise AssertionError("MQTT v5 PUBACK timeout (not an ACL verdict)")
        return int(state["puback_code"])
    finally:
        client.disconnect()
        client.loop_stop()


@unittest.skipUnless(
    os.environ.get("EDGEOPS_BROKER_TEST") == "1",
    "real localhost MQTT broker checks require explicit opt-in",
)
class LocalMosquittoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker CLI unavailable")
        if not all((CERT / f).exists() for f in
                   ("ca.crt", "device-a.crt", "device-a.key",
                    "rogue.crt", "rogue.key")):
            raise unittest.SkipTest("Run bootstrap_pki.py first")
        p = subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "compose.yaml"),
             "ps", "--status", "running", "--services"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=15,
        )
        if p.returncode or "broker" not in p.stdout.split():
            raise unittest.SkipTest("local broker not running")

    def test_01_authorized_device_publish(self):
        # 0 = accepted; 16 = accepted but no subscribers.
        code = publish_v5("device-a", TOPIC_A)
        self.assertIn(code, (0, 16),
                      f"Authorized publish rejected: MQTT PUBACK={code}")

    def test_02_unassigned_rogue_publish_denied(self):
        code = publish_v5("rogue", TOPIC_A)
        self.assertEqual(code, 135,
                         f"Expected MQTT PUBACK 135 (Not authorized), got {code}")

    def test_03_device_cross_site_publish_denied(self):
        code = publish_v5("device-a", TOPIC_B)
        self.assertEqual(code, 135,
                         f"Expected MQTT PUBACK 135 (Not authorized), got {code}")


if __name__ == "__main__":
    unittest.main()
