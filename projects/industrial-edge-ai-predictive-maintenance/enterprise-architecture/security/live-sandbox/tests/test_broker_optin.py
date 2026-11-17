"""Opt-in tests against actual local-loopback Mosquitto mTLS broker.

Set EDGEOPS_BROKER_TEST=1 *only after* generating disposable certificates
and starting the local Docker Compose broker. These tests cannot be used
as proof of production or remotely deployed broker security.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CERT = ROOT / "generated"


def cmd(*args):
    return subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "compose.yaml"),
         "exec", "-T", "broker", *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=15)


@unittest.skipUnless(os.environ.get("EDGEOPS_BROKER_TEST") == "1",
                     "real loopback broker test requires explicit opt-in")
class LocalMosquittoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker CLI unavailable")
        if not (CERT / "device-a.crt").exists():
            raise unittest.SkipTest("Run bootstrap_pki.py first")
        p = subprocess.run(["docker", "compose", "-f", str(ROOT / "compose.yaml"),
                            "ps", "--status", "running", "--services"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=15)
        if p.returncode or "broker" not in p.stdout.split():
            raise unittest.SkipTest("local broker not running")

    def test_01_authorized_device_publish(self):
        result = cmd("mosquitto_pub", "-h", "localhost", "-p", "8883",
                     "--cafile", "/mosquitto/generated/ca.crt",
                     "--cert", "/mosquitto/generated/device-a.crt",
                     "--key", "/mosquitto/generated/device-a.key",
                     "-t", "edgeops/v1/site-a/device-a/telemetry",
                     "-m", '{"source_type":"synthetic"}', "-q", "1")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_02_unassigned_rogue_publish_denied(self):
        result = cmd("mosquitto_pub", "-h", "localhost", "-p", "8883",
                     "--cafile", "/mosquitto/generated/ca.crt",
                     "--cert", "/mosquitto/generated/rogue.crt",
                     "--key", "/mosquitto/generated/rogue.key",
                     "-t", "edgeops/v1/site-a/device-a/telemetry",
                     "-m", "synthetic", "-q", "1")
        self.assertNotEqual(result.returncode, 0,
                            "Unexpected rogue publisher success; inspect broker ACL logs")

    def test_03_device_cross_site_publish_denied(self):
        result = cmd("mosquitto_pub", "-h", "localhost", "-p", "8883",
                     "--cafile", "/mosquitto/generated/ca.crt",
                     "--cert", "/mosquitto/generated/device-a.crt",
                     "--key", "/mosquitto/generated/device-a.key",
                     "-t", "edgeops/v1/site-b/device-a/telemetry",
                     "-m", "synthetic", "-q", "1")
        self.assertNotEqual(result.returncode, 0,
                            "Unexpected cross-site publisher success; inspect broker ACL logs")


if __name__ == "__main__":
    unittest.main()
