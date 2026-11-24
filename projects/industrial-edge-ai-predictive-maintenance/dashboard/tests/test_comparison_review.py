"""Saved comparison integrity, review authorization, concurrency and history."""
import importlib
from copy import deepcopy
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparison_registry import save_comparison, verify_comparison, validate_result
from experiment_registry import _digest, _json_bytes
from ml_evaluation import evaluate_scores
from run_offline_experiment import synthetic_fixture


class ComparisonReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.password = secrets.token_urlsafe(24)
        self.env = patch.dict(os.environ, {
            "EDGEOPS_DASHBOARD_DB": str(self.root / "auth.sqlite3"),
            "EDGEOPS_ADMIN_EMAIL": "reviewer@example.invalid",
            "EDGEOPS_ADMIN_PASSWORD": self.password,
            "EDGEOPS_OFFLINE_EXPERIMENT_ROOT": str(self.root / "experiments")})
        self.env.start()
        import server
        self.server = importlib.reload(server)
        self.server.init_db()
        self.http = TestClient(self.server.app)
        self.saved = save_comparison(synthetic_fixture(), self.root / "experiments")
        self.id = self.saved["comparison_id"]
        self.url = "/api/model-comparisons/" + self.id + "/review"

    def tearDown(self):
        self.http.close()
        self.env.stop()
        self.temp.cleanup()

    def login(self):
        response = self.http.post("/api/auth/login", json={
            "email": "reviewer@example.invalid", "password": self.password})
        self.assertEqual(response.status_code, 200)
        return {"x-edgeops-csrf": self.http.cookies.get("edgeops_csrf")}

    def body(self, revision=0, status="approved", note="Synthetic report reviewed; no deployment approval."):
        return {"expected_revision": revision, "status": status, "note": note}

    def test_01_content_addressed_save_and_tamper_detection(self):
        repeated = save_comparison(synthetic_fixture(), self.root / "experiments")
        self.assertEqual(self.id, repeated["comparison_id"])
        report = verify_comparison(self.root / "experiments", self.id)
        self.assertEqual(report["result"]["split"]["test_count"], 10)
        path = self.root / "experiments" / "comparison-datasets" / (report["dataset_sha256"] + ".json")
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_comparison(self.root / "experiments", self.id)
        with self.assertRaises(ValueError):
            save_comparison(synthetic_fixture(), self.root / "experiments")

    def test_02_review_lifecycle_revision_conflict_and_history(self):
        headers = self.login()
        data = self.http.get("/api/model-comparisons").json()
        self.assertEqual(data["comparisons"][0]["review"]["status"], "pending")
        self.assertNotIn("rows", str(data))
        for revision, status in enumerate(("approved", "rejected", "pending")):
            response = self.http.post(self.url, headers=headers,
                                      json=self.body(revision, status))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["review"]["revision"], revision + 1)
            self.assertFalse(response.json()["model_deployed"])
        self.assertEqual(self.http.post(self.url, headers=headers,
                                       json=self.body(0)).status_code, 409)
        comparison = self.http.get("/api/model-comparisons").json()["comparisons"][0]
        self.assertEqual([x["status"] for x in comparison["review_history"]],
                         ["pending", "rejected", "approved"])
        self.assertTrue(all(x["note"] for x in comparison["review_history"]))
        with self.server.database() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='offline_comparison_review'").fetchone()[0], 3)
        self.assertFalse(self.http.get("/api/system/health").json()["actuators_enabled"])

    def test_03_auth_csrf_and_role_required(self):
        self.assertEqual(self.http.get("/api/model-comparisons").status_code, 401)
        self.assertEqual(self.http.post(self.url, json=self.body()).status_code, 401)
        headers = self.login()
        self.assertEqual(self.http.post(self.url, json=self.body()).status_code, 403)
        for role in ("operator", "auditor"):
            with self.server.database() as db:
                db.execute("UPDATE users SET role=?", (role,))
            self.assertFalse(self.http.get("/api/model-comparisons").json()["can_review"])
            self.assertEqual(self.http.post(self.url, headers=headers, json=self.body()).status_code, 403)

    def test_04_tampered_report_hidden_and_cannot_be_approved(self):
        headers = self.login()
        path = self.root / "experiments" / "comparisons" / (self.id + ".json")
        path.write_text("{}", encoding="utf-8")
        self.assertEqual(self.http.get("/api/model-comparisons").json()["comparisons"], [])
        self.assertEqual(self.http.post(self.url, headers=headers, json=self.body()).status_code, 409)
        with self.server.database() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM comparison_reviews").fetchone()[0], 0)

    def test_05_invalid_review_and_id_rejected(self):
        headers = self.login()
        for body in (self.body(note="   "), self.body(status="deployed"),
                     self.body(-1), {"status": "approved", "note": "Missing revision"}):
            self.assertEqual(self.http.post(self.url, headers=headers, json=body).status_code, 422)
        self.assertEqual(self.http.post("/api/model-comparisons/invalid/review", headers=headers,
                                       json=self.body()).status_code, 422)
        self.assertEqual(self.http.post("/api/model-comparisons/" + "0" * 64 + "/review",
                                       headers=headers, json=self.body()).status_code, 409)

    def test_06_invalid_dataset_writes_nothing(self):
        rows = synthetic_fixture()
        del rows[0]["label"]
        destination = self.root / "invalid"
        with self.assertRaises((ValueError, KeyError)):
            save_comparison(rows, destination)
        self.assertFalse(destination.exists())


    def test_07_rehashed_contradictory_metrics_are_hidden_and_cannot_be_approved(self):
        headers = self.login()
        for index in range(2):
            for metric in ('precision', 'recall', 'f1', 'accuracy'):
                with self.subTest(model=index, metric=metric):
                    report = deepcopy(self.saved['report'])
                    report['result']['models'][index]['test_metrics'][metric] = 0.123
                    content = _json_bytes(report)
                    identifier = _digest(content)
                    (self.root/'experiments/comparisons'/(identifier+'.json')).write_bytes(content)
                    with self.assertRaisesRegex(ValueError, 'confusion matrix'):
                        verify_comparison(self.root/'experiments', identifier)
                    rows = self.http.get('/api/model-comparisons').json()['comparisons']
                    self.assertEqual([row['comparison_id'] for row in rows], [self.id])
                    denied = self.http.post('/api/model-comparisons/'+identifier+'/review',
                                            headers=headers, json=self.body())
                    self.assertEqual(denied.status_code, 409)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comparison_reviews').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM comparison_review_events').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='offline_comparison_review'").fetchone()[0], 0)

    def test_08_consistent_zero_denominators_and_tiny_float_roundoff_are_accepted(self):
        for label, score in ((0,0), (1,0), (0,1), (1,1)):
            result = deepcopy(self.saved['report']['result'])
            for model in result['models']:
                count = result['split']['test_count']
                model['test_metrics'] = evaluate_scores([label]*count, [score]*count,
                                                        threshold=model['threshold']).as_dict()
            validate_result(result)
        result = deepcopy(self.saved['report']['result'])
        result['models'][0]['test_metrics']['precision'] += 5e-13
        validate_result(result)

    def test_09_boolean_sample_count_and_model_threshold_are_rejected(self):
        for field in ('sample_count', 'model_threshold'):
            with self.subTest(field=field):
                result = deepcopy(self.saved['report']['result'])
                result['split']['test_count'] = 1
                result['split']['holdout_event_ids'] = result['split']['holdout_event_ids'][:1]
                for model in result['models']:
                    model['threshold'] = 1.0
                    model['test_metrics'] = evaluate_scores([0], [0], threshold=1.0).as_dict()
                if field == 'sample_count':
                    result['models'][0]['test_metrics']['sample_count'] = True
                else:
                    result['models'][0]['threshold'] = True
                with self.assertRaises(ValueError):
                    validate_result(result)


    def assert_access_change_during_verification_is_denied(self, sql, params, expected):
        # Keep a second enabled administrator so demotion/disable is a valid
        # account-management scenario, not removal of the final administrator.
        with self.server.database() as db:
            if not db.execute("SELECT 1 FROM users WHERE email='backup-admin@example.invalid'").fetchone():
                db.execute('INSERT INTO users(email,password_hash,role) VALUES(?,?,?)',
                           ('backup-admin@example.invalid', self.server.password_hash(self.password), 'admin'))
            db.execute("UPDATE users SET role='admin',disabled=0 WHERE email='reviewer@example.invalid'")
            db.execute('DELETE FROM comparison_review_events')
            db.execute('DELETE FROM comparison_reviews')
            db.execute("DELETE FROM audit WHERE action='offline_comparison_review'")
        self.http.cookies.clear()
        headers = self.login()
        def verify_then_change(*args, **kwargs):
            report = verify_comparison(*args, **kwargs)
            with self.server.database() as db:
                db.execute(sql, params)
            return report
        with patch('comparison_registry.verify_comparison', side_effect=verify_then_change):
            response = self.http.post(self.url, headers=headers, json=self.body())
        self.assertEqual(response.status_code, expected, response.text)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comparison_reviews').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM comparison_review_events').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='offline_comparison_review'").fetchone()[0], 0)

    def test_10_role_change_before_write_prevents_review(self):
        for role in ('operator', 'auditor'):
            with self.subTest(role=role):
                self.assert_access_change_during_verification_is_denied(
                    'UPDATE users SET role=? WHERE email=?', (role,'reviewer@example.invalid'), 403)

    def test_11_disable_or_session_revocation_before_write_prevents_review(self):
        changes = [
            ('disable', 'UPDATE users SET disabled=1 WHERE email=?'),
            ('revoke', 'DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)'),
            ('expire', 'UPDATE sessions SET expires_at=0 WHERE user_id=(SELECT id FROM users WHERE email=?)'),
        ]
        for name, sql in changes:
            with self.subTest(change=name):
                self.assert_access_change_during_verification_is_denied(sql, ('reviewer@example.invalid',), 401)

    def test_12_revoking_another_session_does_not_deny_current_admin(self):
        headers = self.login()
        other = TestClient(self.server.app)
        self.addCleanup(other.close)
        self.assertEqual(other.post('/api/auth/login', json={
            'email':'reviewer@example.invalid','password':self.password}).status_code, 200)
        other_csrf_hash = self.server.token_hash(other.cookies['edgeops_csrf'])
        def verify_then_revoke_other(*args, **kwargs):
            report = verify_comparison(*args, **kwargs)
            with self.server.database() as db:
                db.execute('DELETE FROM sessions WHERE csrf_hash=?', (other_csrf_hash,))
            return report
        with patch('comparison_registry.verify_comparison', side_effect=verify_then_revoke_other):
            response = self.http.post(self.url, headers=headers, json=self.body())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()['model_deployed'])
        self.assertEqual(self.http.get('/api/me').status_code, 200)
        self.assertEqual(other.get('/api/me').status_code, 401)


if __name__ == "__main__":
    unittest.main()
