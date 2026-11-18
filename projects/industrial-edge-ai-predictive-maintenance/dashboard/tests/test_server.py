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
        os.environ["EDGEOPS_ADMIN_EMAIL"] = cls.email
        os.environ["EDGEOPS_ADMIN_PASSWORD"] = cls.password
        import server
        cls.server = importlib.reload(server)
        cls.server.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        for key in ("EDGEOPS_DASHBOARD_DB", "EDGEOPS_ADMIN_EMAIL", "EDGEOPS_ADMIN_PASSWORD"):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
