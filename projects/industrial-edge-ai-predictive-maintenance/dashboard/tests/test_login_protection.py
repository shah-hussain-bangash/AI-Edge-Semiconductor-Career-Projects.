"""Bounded local login protection with synthetic identities and disposable stores."""
import unittest
from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import patch

import test_acquisition_registry as fixture
from login_protection import LoginThrottle, LoginThrottled


class LoginThrottleTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.throttle = LoginThrottle(clock=lambda: self.now)

    def fail(self, client, email):
        reservation = self.throttle.reserve(client, email)
        self.throttle.finish(reservation, False)

    def test_identity_limit_and_different_client_isolation(self):
        for _ in range(5):
            self.fail('client-a', 'user@example.invalid')
        with self.assertRaises(LoginThrottled):
            self.throttle.reserve('client-a', 'user@example.invalid')
        self.throttle.reserve('client-b', 'user@example.invalid')

    def test_rotating_identities_share_source_budget(self):
        for index in range(30):
            self.fail('client-a', str(index))
        with self.assertRaises(LoginThrottled):
            self.throttle.reserve('client-a', 'new-identity')
        self.throttle.reserve('client-b', 'new-identity')

    def test_expired_unrelated_keys_release_capacity_without_eviction(self):
        throttle = LoginThrottle(max_buckets=2, clock=lambda: self.now)
        reservation = throttle.reserve('client-a', 'user-a')
        throttle.finish(reservation, False)
        for index in range(20):
            with self.assertRaises(LoginThrottled):
                throttle.reserve('client-b', str(index))
        self.assertEqual(len(throttle._buckets), 2)
        self.now = 900
        throttle.reserve('client-b', 'user-b')
        self.assertEqual(len(throttle._buckets), 2)

    def test_success_clears_identity_failures_but_keeps_source_failures(self):
        throttle = LoginThrottle(identity_limit=5, source_limit=5)
        for _ in range(4):
            reservation = throttle.reserve('client-a', 'user-a')
            throttle.finish(reservation, False)
        success = throttle.reserve('client-a', 'user-a')
        throttle.finish(success, True)
        final = throttle.reserve('client-a', 'user-a')
        with self.assertRaises(LoginThrottled):
            throttle.reserve('client-a', 'user-b')
        throttle.finish(final, True)

    def test_success_preserves_other_inflight_identity_reservations(self):
        reservations = [self.throttle.reserve('client-a', 'user-a') for _ in range(5)]
        self.throttle.finish(reservations[0], True)
        self.throttle.reserve('client-a', 'user-a')
        with self.assertRaises(LoginThrottled):
            self.throttle.reserve('client-a', 'user-a')

    def test_concurrent_admissions_do_not_exceed_source_limit(self):
        def admit(index):
            try:
                return self.throttle.reserve('same-client', str(index))
            except LoginThrottled:
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(admit, range(60)))
        admitted = [result for result in results if result is not None]
        self.assertEqual(len(admitted), 30)
        for reservation in admitted:
            self.throttle.finish(reservation, False)
        with self.assertRaises(LoginThrottled):
            self.throttle.reserve('same-client', 'another')

    def test_late_completion_does_not_recreate_expired_reservations(self):
        stale = self.throttle.reserve('old-client', 'old-user')
        self.now = 900
        live = self.throttle.reserve('new-client', 'new-user')
        self.throttle.finish(stale, False)
        self.assertEqual(len(self.throttle._buckets), 2)
        self.throttle.finish(live, True)
        self.assertEqual(len(self.throttle._buckets), 0)

    def test_tracking_keys_do_not_contain_raw_client_or_email(self):
        self.throttle.reserve('private-client-marker', 'private-email-marker')
        self.assertNotIn('private-', str(self.throttle._buckets))


class LoginProtectionApiTests(unittest.TestCase):
    login = fixture.AcquisitionRegistryApiTests.login

    def setUp(self):
        fixture.AcquisitionRegistryApiTests.setUp(self)

    def test_rotating_emails_hit_client_limit_before_another_password_check(self):
        with self.server.database() as db:
            sessions_before = db.execute('SELECT count(*) FROM sessions').fetchone()[0]
        with patch.object(self.server, 'password_matches', return_value=False) as verify:
            statuses = [self.http.post('/api/auth/login', json={
                'email': f'rotating-{i}@example.invalid', 'password': 'private-test-marker'
            }).status_code for i in range(31)]
        self.assertEqual(statuses, [401] * 30 + [429])
        self.assertEqual(verify.call_count, 30)
        with self.server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], sessions_before)
            details = [row[0] for row in db.execute('SELECT detail FROM audit')]
        self.assertNotIn('private-test-marker', str(details))

    def test_identity_limit_expires_and_real_credentials_can_sign_in(self):
        now = [0]
        self.server.LOGIN_THROTTLE = LoginThrottle(clock=lambda: now[0])
        body = {'email': 'admin@example.invalid', 'password': self.password}
        with patch.object(self.server, 'password_matches', return_value=False):
            self.assertEqual([self.http.post('/api/auth/login', json=body).status_code
                              for _ in range(6)], [401] * 5 + [429])
        now[0] = 900
        self.assertEqual(self.http.post('/api/auth/login', json=body).status_code, 200)
        self.assertEqual(self.http.get('/api/me').status_code, 200)

    def test_concurrent_password_checks_are_reserved_before_verification(self):
        entered = threading.Barrier(6)
        release = threading.Event()
        def verify(*args):
            entered.wait(timeout=10)
            if not release.wait(timeout=10):
                raise AssertionError('Password-check fixture was not released')
            return False
        body = {'email': 'concurrent@example.invalid', 'password': 'test-only'}
        with patch.object(self.server, 'password_matches', side_effect=verify) as check:
            with ThreadPoolExecutor(max_workers=5) as pool:
                pending = [pool.submit(self.http.post, '/api/auth/login', json=body) for _ in range(5)]
                try:
                    entered.wait(timeout=10)
                    blocked = self.http.post('/api/auth/login', json=body)
                    self.assertEqual(blocked.status_code, 429)
                    self.assertEqual(check.call_count, 5)
                finally:
                    release.set()
                self.assertEqual([future.result(timeout=10).status_code for future in pending], [401] * 5)

    def test_capacity_refusal_precedes_password_check_and_expiry_recovers(self):
        now = [0]
        limiter = LoginThrottle(max_buckets=2, clock=lambda: now[0])
        self.server.LOGIN_THROTTLE = limiter
        first = {'email': 'first@example.invalid', 'password': 'test-only'}
        second = {'email': 'second@example.invalid', 'password': 'test-only'}
        with patch.object(self.server, 'password_matches', return_value=False) as verify:
            self.assertEqual(self.http.post('/api/auth/login', json=first).status_code, 401)
            blocked = self.http.post('/api/auth/login', json=second)
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.json()['detail'], 'Too many attempts; retry later')
            self.assertEqual(verify.call_count, 1)
            self.assertEqual(len(limiter._buckets), 2)
            now[0] = 900
            self.assertEqual(self.http.post('/api/auth/login', json=second).status_code, 401)
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(len(limiter._buckets), 2)


if __name__ == '__main__':
    unittest.main()
