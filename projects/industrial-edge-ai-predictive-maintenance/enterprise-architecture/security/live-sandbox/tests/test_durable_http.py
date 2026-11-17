"""EA-30 tests: independent subprocess HTTP server and SQLite persistence.

No Docker, MQTT, physical hardware, real OIDC or network TLS required.
Run from enterprise-architecture: python -m unittest discover
-s security/live-sandbox/tests -p "test_durable_http.py" -v
"""
from __future__ import annotations

import copy
import json
import os
import secrets
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
ARCH = LAB.parents[1]
SAMPLE = ARCH / "contracts" / "examples" / "telemetry-v2.synthetic-valid.json"
ISS = "edgeops-ea30-local-fixture-issuer"
AUD = "edgeops-ea30-local-api"


def sample(seq=1):
    obj = json.loads(SAMPLE.read_text(encoding="utf-8"))
    obj.update(site_id="site-a", asset_id="motor-a", device_id="device-a",
               boot_id="synthetic-boot-001", sequence=seq)
    obj["quality"]["session_quality"] = "verified"
    return obj


def token(secret, sub="gateway-a", **overrides):
    now = datetime.now(timezone.utc)
    claims = {"sub": sub, "iss": ISS, "aud": AUD, "iat": now,
              "exp": now + timedelta(seconds=60)}
    claims.update(overrides)
    return jwt.encode(claims, secret, algorithm="HS256")


class DurableHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="edgeops-ea30-")
        cls.db_path = Path(cls.temp.name) / "events.sqlite3"
        cls.key = secrets.token_urlsafe(48)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        cls.port = sock.getsockname()[1]
        sock.close()
        cls.env = dict(os.environ,
                       EDGEOPS_EA30_SIGNING_KEY=cls.key,
                       EDGEOPS_EA30_DB_PATH=str(cls.db_path))
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.start_server()

    @classmethod
    def start_server(cls):
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "durable_service:app",
             "--host", "127.0.0.1", "--port", str(cls.port),
             "--no-access-log"],
            cwd=str(LAB), env=cls.env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            if cls.proc.poll() is not None:
                raise RuntimeError("EA-30 test HTTP server exited unexpectedly")
            try:
                if httpx.get(cls.base + "/health", timeout=.5).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.1)
        raise RuntimeError("EA-30 localhost HTTP startup timeout")

    @classmethod
    def stop_server(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.proc.wait(timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.stop_server()
        cls.temp.cleanup()

    def post(self, record, sub="gateway-a", bearer=None):
        headers = {"Authorization": "Bearer " + (bearer or token(self.key, sub))}
        return httpx.post(self.base + "/telemetry", json=record, headers=headers, timeout=5)

    def count(self):
        r = httpx.get(self.base + "/telemetry/count",
                      headers={"Authorization": "Bearer " + token(self.key)},
                      timeout=5)
        self.assertEqual(r.status_code, 200)
        return r.json()["count"]

    def test_01_accepted_new_record(self):
        r = self.post(sample(3001))
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["durable"])

    def test_02_duplicate_is_idempotent(self):
        self.post(sample(3002))
        r = self.post(sample(3002))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["duplicate"])

    def test_03_store_survives_server_restart(self):
        self.post(sample(3003))
        initial = self.count()
        self.stop_server()
        self.start_server()
        self.assertEqual(self.count(), initial)
        self.assertEqual(self.post(sample(3003)).status_code, 200)

    def test_04_distinct_sequences(self):
        self.assertEqual(self.post(sample(3004)).status_code, 201)
        self.assertEqual(self.post(sample(3005)).status_code, 201)

    def test_05_missing_token_denied(self):
        self.assertEqual(httpx.post(self.base + "/telemetry", json=sample(3006)).status_code, 401)

    def test_06_invalid_signature_denied(self):
        bad = token("not-the-test-signing-key" * 4)
        self.assertEqual(self.post(sample(3007), bearer=bad).status_code, 401)

    def test_07_wrong_role_denied(self):
        self.assertEqual(self.post(sample(3008), sub="operator-a").status_code, 403)

    def test_08_cross_site_denied(self):
        obj = sample(3009)
        obj["site_id"] = "site-b"
        self.assertEqual(self.post(obj).status_code, 403)

    def test_09_missing_boot_id_rejected(self):
        obj = sample(3010)
        obj["boot_id"] = None
        obj["quality"]["session_quality"] = "inferred"
        self.assertEqual(self.post(obj).status_code, 422)

    def test_10_invalid_schema_denied(self):
        obj = sample(3011)
        obj.pop("timestamp")
        self.assertEqual(self.post(obj).status_code, 422)

    def test_11_measured_data_rejected_in_sandbox(self):
        obj = sample(3012)
        obj["source_type"] = "measured"
        self.assertEqual(self.post(obj).status_code, 422)

    def test_12_asset_registry_mismatch_denied(self):
        obj = sample(3013)
        obj["asset_id"] = "motor-b"
        self.assertEqual(self.post(obj).status_code, 403)

    def test_13_wrong_audience_denied(self):
        bad = token(self.key, aud="other-api")
        self.assertEqual(self.post(sample(3014), bearer=bad).status_code, 401)

    def test_14_anonymous_count_denied(self):
        self.assertEqual(httpx.get(self.base + "/telemetry/count").status_code, 401)

    def test_15_operator_count_denied(self):
        r = httpx.get(self.base + "/telemetry/count",
                      headers={"Authorization": "Bearer " + token(self.key, "operator-a")})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
