"""EA-31 opt-in real localhost MQTT -> separate HTTP server -> SQLite tests.

Requires disposable EA-28 PKI and the EA-28 loopback Mosquitto container.
No physical devices; no production network/security claims. Explicit replay,
not automatic delivery, is used to demonstrate idempotence after failures.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
from gateway import publish_synthetic
from mqtt_http_bridge import HttpMqttBridge, verified_sample
from durable_service import ISSUER, AUDIENCE


@unittest.skipUnless(os.environ.get("EDGEOPS_EA31_TEST") == "1",
                     "opt-in real MQTT broker and separately launched HTTP server required")
class LiveMqttToDurableApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker CLI missing")
        if not all((LAB / "generated" / x).exists()
                   for x in ("ca.crt", "gateway-a.crt", "gateway-a.key",
                             "device-a.crt", "device-a.key")):
            raise unittest.SkipTest("EA-28 disposable mTLS test PKI missing")
        proc = subprocess.run(
            ["docker", "compose", "-f", str(LAB / "compose.yaml"),
             "ps", "--services", "--status", "running"],
            cwd=str(LAB), capture_output=True, text=True, timeout=15)
        if proc.returncode != 0 or "broker" not in proc.stdout.split():
            raise unittest.SkipTest("MQTT broker not running")

        cls.tmp = tempfile.TemporaryDirectory(prefix="edgeops-ea31-")
        cls.key = secrets.token_urlsafe(48)
        cls.db = str(Path(cls.tmp.name) / "data.sqlite3")
        cls.env = dict(os.environ,
                       EDGEOPS_EA30_SIGNING_KEY=cls.key,
                       EDGEOPS_EA30_DB_PATH=cls.db)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.server = None
        cls.start_http()

    @classmethod
    def start_http(cls):
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "durable_service:app",
             "--host", "127.0.0.1", "--port", str(cls.port), "--no-access-log"],
            cwd=str(LAB), env=cls.env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        for _ in range(100):
            if cls.server.poll() is not None:
                raise RuntimeError("standalone API exited unexpectedly")
            try:
                if httpx.get(cls.base + "/health", timeout=.5).status_code == 200:
                    return
            except httpx.RequestError:
                pass
            time.sleep(.1)
        raise RuntimeError("HTTP localhost server did not start")

    @classmethod
    def stop_http(cls):
        if cls.server is None:
            return
        if cls.server.poll() is None:
            cls.server.terminate()
            try:
                cls.server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                cls.server.kill()
                cls.server.wait(timeout=5)
        cls.server = None

    @classmethod
    def tearDownClass(cls):
        cls.stop_http()
        cls.tmp.cleanup()

    def setUp(self):
        self.bridge = HttpMqttBridge(api_base=self.base, signing_key=self.key).start()

    def tearDown(self):
        self.bridge.stop()
        # Recover API in case an assertion stops the test mid-failure scenario.
        if self.server is None or self.server.poll() is not None:
            self.start_http()

    def delivered(self, record, expected):
        code = publish_synthetic(record)
        self.assertIn(code, (0, 16), f"MQTT PUBACK={code}")
        self.assertEqual(self.bridge.await_result(10), expected)

    def count(self):
        now = datetime.now(timezone.utc)
        tok = jwt.encode({"sub": "gateway-a", "iss": ISSUER, "aud": AUDIENCE,
                          "iat": now, "exp": now + timedelta(seconds=60)},
                         self.key, algorithm="HS256")
        res = httpx.get(self.base + "/telemetry/count",
                        headers={"Authorization": "Bearer " + tok}, timeout=4)
        self.assertEqual(res.status_code, 200)
        return res.json()["count"]

    def test_01_full_mqtt_to_durable_sqlite(self):
        start = self.count()
        self.delivered(verified_sample(5101), ("stored", 201))
        self.assertEqual(self.count(), start + 1)

    def test_02_replay_idempotent_across_mqtt(self):
        self.delivered(verified_sample(5102), ("stored", 201))
        self.delivered(verified_sample(5102), ("already_stored", 200))

    def test_03_api_restart_durable_replay(self):
        self.delivered(verified_sample(5103), ("stored", 201))
        before = self.count()
        self.stop_http()
        self.start_http()
        self.assertEqual(self.count(), before)
        self.delivered(verified_sample(5103), ("already_stored", 200))

    def test_04_mqtt_delivered_bad_json_rejected(self):
        self.delivered(b'{broken-json', ("json_rejected", None))

    def test_05_mqtt_delivered_invalid_schema_rejected(self):
        invalid = verified_sample(5105)
        invalid.pop("timestamp")
        self.delivered(invalid, ("schema_rejected", None))

    def test_06_cross_site_body_rejected(self):
        invalid = verified_sample(5106)
        invalid["site_id"] = "site-b"
        self.delivered(invalid, ("registry_rejected", None))

    def test_07_unverified_boot_rejected(self):
        invalid = verified_sample(5107)
        invalid["boot_id"] = None
        invalid["quality"]["session_quality"] = "inferred"
        self.delivered(invalid, ("session_rejected", None))

    def test_08_wrong_gateway_role_denied_by_remote_api(self):
        self.bridge.stop()
        self.bridge = HttpMqttBridge(
            api_base=self.base, signing_key=self.key, subject="operator-a").start()
        self.delivered(verified_sample(5108), ("api_rejected", 403))

    def test_09_http_unavailable_never_acknowledged_as_stored(self):
        self.stop_http()
        self.delivered(verified_sample(5109), ("http_unavailable", None))

    def test_10_explicit_replay_after_http_recovery(self):
        self.stop_http()
        self.delivered(verified_sample(5110), ("http_unavailable", None))
        self.start_http()
        self.delivered(verified_sample(5110), ("stored", 201))
        self.delivered(verified_sample(5110), ("already_stored", 200))

    def test_11_two_events_saved_over_real_mqtt(self):
        start = self.count()
        self.delivered(verified_sample(5111), ("stored", 201))
        self.delivered(verified_sample(5112), ("stored", 201))
        self.assertEqual(self.count(), start + 2)

    def test_12_reject_oversized_payload_at_gateway(self):
        self.assertEqual(self.bridge.forward("edgeops/v1/site-a/device-a/telemetry", b"x"*65537),
                         ("topic_or_size_rejected", None))


if __name__ == "__main__":
    unittest.main()
