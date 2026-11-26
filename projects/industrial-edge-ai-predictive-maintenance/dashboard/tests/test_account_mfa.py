import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import pyotp
import private_crypto
import test_operational_workflow as fixture


class MFATests(unittest.TestCase):
    login=fixture.OperationalTests.login
    post=fixture.OperationalTests.post

    def setUp(self):
        fixture.OperationalTests.setUp(self)
        self.key=Path(self.temp.name)/'private.key';private_crypto.generate(self.key)
        setting=patch.dict(os.environ,{'EDGEOPS_PRIVATE_KEY_FILE':str(self.key)});setting.start();self.addCleanup(setting.stop)

    def begin(self):
        result=self.post('/api/account/mfa/begin',dict(current_password=self.password))
        self.assertEqual(result.status_code,200,result.text);return result.json()

    def confirm(self,pending):
        result=self.post('/api/account/mfa/confirm',dict(nonce=pending['nonce'],code=pyotp.TOTP(pending['secret']).now()))
        self.assertEqual(result.status_code,200,result.text);return result.json()

    def test_optional_email_password_enrollment_encrypted_seed_and_replay(self):
        self.assertFalse(self.http.get('/api/account/mfa').json()['enabled'])
        pending=self.begin();self.assertIn('otpauth://',pending['provisioning_uri'])
        with self.server.database() as db:self.assertNotIn(pending['secret'],json.dumps(dict(db.execute('SELECT * FROM account_mfa').fetchone())))
        result=self.confirm(pending);self.assertEqual(len(result['recovery_codes']),10)
        status=self.http.get('/api/account/mfa').json();self.assertTrue(status['enabled']);self.assertNotIn('secret',status)
        self.http.cookies.clear()
        base=dict(email='admin@example.invalid',password=self.password)
        self.assertEqual(self.http.post('/api/auth/login',json=base).status_code,401)
        self.assertEqual(self.http.post('/api/auth/login',json=dict(base,otp_code=pyotp.TOTP(pending['secret']).now())).status_code,401,'Enrollment counter cannot be replayed')
        self.assertEqual(self.http.post('/api/auth/login',json=dict(base,otp_code=result['recovery_codes'][0])).status_code,200)
        self.http.cookies.clear();self.assertEqual(self.http.post('/api/auth/login',json=dict(base,otp_code=result['recovery_codes'][0])).status_code,401)
        self.assertEqual(self.http.post('/api/auth/login',json=dict(base,otp_code=result['recovery_codes'][1])).status_code,200)

    def test_recovery_works_when_encryption_key_missing_and_disable_needs_factor(self):
        codes=self.confirm(self.begin())['recovery_codes']
        with patch.dict(os.environ,{'EDGEOPS_PRIVATE_KEY_FILE':''}):
            self.http.cookies.clear();response=self.http.post('/api/auth/login',json=dict(email='admin@example.invalid',password=self.password,otp_code=codes[0]))
            self.assertEqual(response.status_code,200,response.text)
            response=self.post('/api/account/mfa/disable',dict(current_password=self.password,code=codes[1]));self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(self.http.get('/api/account/mfa').json()['enabled'])
        self.http.cookies.clear();self.assertEqual(self.http.post('/api/auth/login',json=dict(email='admin@example.invalid',password=self.password)).status_code,200)

    def test_pending_nonce_expiry_denials_and_no_secret_status(self):
        pending=self.begin()
        self.assertEqual(self.post('/api/account/mfa/confirm',dict(nonce='0'*32,code='000000')).status_code,409)
        with self.server.database() as db:db.execute('UPDATE account_mfa SET pending_expires=0')
        self.assertEqual(self.post('/api/account/mfa/confirm',dict(nonce=pending['nonce'],code='000000')).status_code,409)
        for _ in range(5):self.assertEqual(self.post('/api/account/mfa/begin',dict(current_password='wrong password')).status_code,403)
        self.assertEqual(self.post('/api/account/mfa/begin',dict(current_password=self.password)).status_code,429)
        self.assertNotIn('secret',self.http.get('/api/account/mfa').text)

    def test_csrf_and_non_loopback_plaintext_enrollment_refused(self):
        self.assertEqual(self.post('/api/account/mfa/begin',dict(current_password=self.password),False).status_code,403)
        from fastapi.testclient import TestClient
        with TestClient(self.server.app,base_url='http://testserver',client=('203.0.113.1',1234)) as client:
            client.cookies.update(self.http.cookies)
            response=client.post('/api/account/mfa/begin',json=dict(current_password=self.password),headers={'x-edgeops-csrf':client.cookies.get('edgeops_csrf')})
            self.assertEqual(response.status_code,403)

    def test_new_key_never_overwrites_existing_key(self):
        original=self.key.read_bytes()
        with self.assertRaises(FileExistsError):private_crypto.generate(self.key)
        self.assertEqual(self.key.read_bytes(),original)
