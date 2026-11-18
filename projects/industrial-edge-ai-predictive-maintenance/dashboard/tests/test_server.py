"""Local dashboard authentication and hardware catalog API tests.

Run from dashboard dir: python -m unittest discover -s tests -p test_server.py -v
"""
import importlib
import os
import secrets
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class DashboardApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="edgeops-dashboard-")
        cls.db = str(Path(cls.temp.name) / "auth.sqlite3")
        cls.email = "local-tester@example.invalid"
        cls.password = secrets.token_urlsafe(24)
        os.environ["EDGEOPS_DASHBOARD_DB"] = cls.db
        os.environ["EDGEOPS_SYNTHETIC_TELEMETRY_DB"] = str(Path(cls.temp.name) / "synthetic-telemetry.sqlite3")
        os.environ["EDGEOPS_ADMIN_EMAIL"] = cls.email
        os.environ["EDGEOPS_ADMIN_PASSWORD"] = cls.password
        import server
        cls.server = importlib.reload(server)
        cls.server.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        for key in ("EDGEOPS_DASHBOARD_DB", "EDGEOPS_SYNTHETIC_TELEMETRY_DB", "EDGEOPS_ADMIN_EMAIL", "EDGEOPS_ADMIN_PASSWORD"):
            os.environ.pop(key, None)

    def setUp(self):
        self.http = TestClient(self.server.app)

    def tearDown(self):
        self.http.close()

    def sign_in(self):
        response = self.http.post("/api/auth/login",
                                  json={"email": self.email, "password": self.password})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_01_unauthenticated_app_redirect(self):
        res = self.http.get("/app", follow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers["location"], "/signin")

    def test_02_unauthenticated_inventory_denied(self):
        self.assertEqual(self.http.get("/api/hardware").status_code, 401)

    def test_03_bad_password_denied(self):
        self.assertEqual(self.http.post("/api/auth/login",
                                       json={"email": self.email, "password": "incorrect"}).status_code, 401)

    def test_04_authenticated_session(self):
        self.sign_in()
        self.assertEqual(self.http.get("/api/me").json()["role"], "admin")

    def test_05_thirty_hardware_slots_with_unconfirmed_names(self):
        self.sign_in()
        data = self.http.get("/api/hardware").json()
        self.assertEqual(len(data["devices"]), 30)
        self.assertEqual(data["confirmed_hardware_count"], 14)
        self.assertEqual(sum(1 for d in data["devices"] if d["connected"]), 0)

    def test_06_static_file_allowlist_blocks_secrets(self):
        self.assertEqual(self.http.get("/static/server.py").status_code, 404)
        self.assertEqual(self.http.get("/static/.env").status_code, 404)
        self.assertEqual(self.http.get("/static/styles.css").status_code, 200)
        self.assertEqual(self.http.get("/static/industrial-motor.svg").status_code, 200)
        self.assertEqual(self.http.get("/static/industrial-plant.svg").status_code, 200)
        self.assertEqual(self.http.get("/static/architecture.js").status_code, 200)

    def test_07_logout_requires_csrf(self):
        self.sign_in()
        self.assertEqual(self.http.post("/api/auth/logout").status_code, 403)

    def test_08_logout_revokes_session(self):
        self.sign_in()
        csrf = self.http.cookies.get("edgeops_csrf")
        self.assertTrue(csrf)
        self.assertEqual(self.http.post("/api/auth/logout",
                                        headers={"x-edgeops-csrf": csrf}).status_code, 200)
        self.assertEqual(self.http.get("/api/me").status_code, 401)

    def test_09_authenticated_audit(self):
        self.sign_in()
        res = self.http.get("/api/audit")
        self.assertEqual(res.status_code, 200)
        self.assertIn("entries", res.json())

    def test_10_no_motor_controls_advertised(self):
        self.sign_in()
        health = self.http.get("/api/system/health").json()
        self.assertFalse(health["actuators_enabled"])
        self.assertFalse(health["hardware_connected"])
        self.assertEqual(health["physical_safety_gate"], "blocking")

    def test_11_security_headers(self):
        response = self.http.get("/signin")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_12_alert_ack_is_demo_only(self):
        self.sign_in()
        csrf = self.http.cookies.get("edgeops_csrf")
        result = self.http.post("/api/alerts/acknowledge",
                                json={"alert_id": "AL-2401"},
                                headers={"x-edgeops-csrf": csrf})
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()["persistent_alarm_state"])


    def test_13_synthetic_telemetry_endpoint_requires_authentication(self):
        self.assertEqual(self.http.get("/api/synthetic-telemetry").status_code, 401)
        self.assertEqual(self.http.post("/api/synthetic-telemetry", json=self.synthetic_event("evt-unauth-1")).status_code, 401)

    def test_14_synthetic_telemetry_requires_csrf_and_explicit_provenance(self):
        self.sign_in()
        event = self.synthetic_event("evt-csrf-1")
        self.assertEqual(self.http.post("/api/synthetic-telemetry", json=event).status_code, 403)
        csrf = self.http.cookies["edgeops_csrf"]
        event["provenance"] = "real-hardware"
        self.assertEqual(self.http.post("/api/synthetic-telemetry", json=event,
                                       headers={"x-edgeops-csrf": csrf}).status_code, 422)

    @staticmethod
    def synthetic_event(event_id):
        return {
            "event_id": event_id, "asset_id": "MTR-001",
            "captured_at": "2026-01-01T01:02:03+00:00",
            "vibration_mm_s": 2.6, "temperature_c": 41.2, "current_a": 1.7,
            "provenance": "synthetic-demo",
        }

    def test_15_synthetic_telemetry_durable_insert_and_idempotent_replay(self):
        self.sign_in()
        csrf = self.http.cookies["edgeops_csrf"]
        event = self.synthetic_event("evt-durable-1")
        response = self.http.post("/api/synthetic-telemetry", json=event,
                                  headers={"x-edgeops-csrf": csrf})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(response.json()["inserted"])
        self.assertFalse(response.json()["model_deployed"])
        again = self.http.post("/api/synthetic-telemetry", json=event,
                               headers={"x-edgeops-csrf": csrf})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertFalse(again.json()["inserted"])
        result = self.http.get("/api/synthetic-telemetry?asset_id=MTR-001")
        self.assertEqual(result.status_code, 200)
        matches = [x for x in result.json()["events"] if x["event_id"] == "evt-durable-1"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["provenance"], "synthetic-demo")

    def test_16_synthetic_telemetry_rejects_conflicts_and_invalid_values(self):
        self.sign_in()
        csrf = self.http.cookies["edgeops_csrf"]
        headers = {"x-edgeops-csrf": csrf}
        event = self.synthetic_event("evt-conflict-1")
        self.assertEqual(self.http.post("/api/synthetic-telemetry", json=event,
                                       headers=headers).status_code, 201)
        conflict = {**event, "temperature_c": 99.0}
        self.assertEqual(self.http.post("/api/synthetic-telemetry", json=conflict,
                                       headers=headers).status_code, 409)
        for edited in ({**event, "event_id": "evt-bad-nan", "vibration_mm_s": -1},
                       {**event, "event_id": "evt-bad-tz", "captured_at": "2026-01-01T01:02:03"},
                       {**event, "event_id": "evt-bad-range", "temperature_c": 250}):
            with self.subTest(edited=edited["event_id"]):
                self.assertEqual(self.http.post("/api/synthetic-telemetry", json=edited,
                                               headers=headers).status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
