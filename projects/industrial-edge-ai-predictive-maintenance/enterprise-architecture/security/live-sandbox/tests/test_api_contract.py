"""EA-28 HTTP routing/security contract checks using FastAPI TestClient.

Run from enterprise-architecture/:
python -m unittest discover -s security/live-sandbox/tests -p 'test_api*.py' -v

In-memory HTTP dispatch only. No external network, broker, TLS or production IAM.
"""
from __future__ import annotations
import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from fastapi.testclient import TestClient
import api

SCHEMA_SAMPLE = json.loads((HERE.parents[1] / "contracts" / "examples" /
                            "telemetry-v2.synthetic-valid.json").read_text(encoding="utf-8"))


def sample():
    r = copy.deepcopy(SCHEMA_SAMPLE)
    r["site_id"], r["asset_id"], r["device_id"] = "site-a", "motor-a", "device-a"
    return r


def headers(sub="gateway-a", **kwargs):
    return {"Authorization": "Bearer " + api.fixture_token(sub, **kwargs)}


class APIContractTests(unittest.TestCase):
    def setUp(self):
        api.EVENTS.clear()
        self.client = TestClient(api.app)

    def test_01_gateway_ingests_synthetic(self):
        r = self.client.post("/telemetry", json=sample(), headers=headers())
        self.assertEqual(r.status_code, 202)
        self.assertFalse(r.json()["durable"])

    def test_02_missing_token_401(self):
        self.assertEqual(self.client.post("/telemetry", json=sample()).status_code, 401)

    def test_03_invalid_token_401(self):
        self.assertEqual(self.client.post("/telemetry", json=sample(),
                         headers={"Authorization": "Bearer bogus"}).status_code, 401)

    def test_04_expired_token_401(self):
        self.assertEqual(self.client.post("/telemetry", json=sample(),
                         headers=headers(expires=-60)).status_code, 401)

    def test_05_wrong_audience_401(self):
        self.assertEqual(self.client.post("/telemetry", json=sample(),
                         headers=headers(audience="other")).status_code, 401)

    def test_06_wrong_issuer_401(self):
        self.assertEqual(self.client.post("/telemetry", json=sample(),
                         headers=headers(issuer="other")).status_code, 401)

    def test_07_wrong_role_403(self):
        self.assertEqual(self.client.post("/telemetry", json=sample(),
                         headers=headers(sub="operator-a")).status_code, 403)

    def test_08_site_claim_mismatch_403(self):
        p = sample()
        p["site_id"] = "site-b"
        self.assertEqual(self.client.post("/telemetry", json=p,
                         headers=headers()).status_code, 403)

    def test_09_missing_schema_field_422(self):
        p = sample()
        del p["timestamp"]
        self.assertEqual(self.client.post("/telemetry", json=p,
                         headers=headers()).status_code, 422)

    def test_10_device_unknown_403(self):
        p = sample()
        p["device_id"] = "device-unknown"
        self.assertEqual(self.client.post("/telemetry", json=p,
                         headers=headers()).status_code, 403)

    def test_11_operator_reads_authorized_asset(self):
        self.assertEqual(self.client.get("/assets/site-a/motor-a",
                         headers=headers(sub="operator-a")).status_code, 200)

    def test_12_operator_cross_site_asset_403(self):
        self.assertEqual(self.client.get("/assets/site-b/motor-b",
                         headers=headers(sub="operator-a")).status_code, 403)

    def test_13_anonymous_asset_request_401(self):
        self.assertEqual(self.client.get("/assets/site-a/motor-a").status_code, 401)

    def test_14_no_motor_endpoint(self):
        self.assertEqual(self.client.post("/motor/start", json={},
                         headers=headers(sub="agent-a")).status_code, 404)


if __name__ == "__main__":
    unittest.main()
