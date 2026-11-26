import os
import unittest
from unittest.mock import patch
import operational_notifications as notifications
import test_operational_workflow as fixture

SMTP={'EDGEOPS_SMTP_HOST':'smtp.example.invalid','EDGEOPS_SMTP_USERNAME':'fixture-user',
      'EDGEOPS_SMTP_PASSWORD':'fixture-secret-not-a-real-password','EDGEOPS_SMTP_FROM':'fixture@example.invalid',
      'EDGEOPS_SMTP_TLS':'starttls','EDGEOPS_SMTP_PORT':'587'}


class NotificationTests(unittest.TestCase):
    setUp=fixture.OperationalTests.setUp
    login=fixture.OperationalTests.login
    post=fixture.OperationalTests.post
    rule=fixture.OperationalTests.rule
    ingest=fixture.OperationalTests.ingest

    def enable(self,enabled=True,revision=0):
        return self.post('/api/operational/email/configuration',dict(enabled=enabled,expected_revision=revision,**self.authorization))

    def pending(self):
        self.rule()
        # Synthetic harness declares this unverified source solely to test the
        # notification path. It never claims physical measurements or acceptance.
        self.post('/api/operational/assets',dict(site_id='fixture-site',asset_id='fixture-asset',device_id='motor-001',label='Unverified-source software harness',source_type='measured-unverified',**self.authorization))
        data=self.http.get('/api/operational/summary').json();asset=next(a for a in data['assets'] if a['source_type']=='measured-unverified')
        self.asset=asset;self.rule();self.assertEqual(self.ingest(source='measured-unverified',temp_c=40).status_code,201)

    def test_no_configuration_no_send_fixture_lane_local_only_and_read_is_not_ack(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        data=self.http.get('/api/operational/notifications').json();self.assertEqual(len(data['items']),1)
        self.assertEqual(data['items'][0]['email_state'],'local-only-fixture');self.assertFalse(data['email']['enabled'])
        with patch.object(notifications,'send') as send:
            result=notifications.deliver(self.server.database);self.assertEqual(result['delivered'],0);send.assert_not_called()
        response=self.post('/api/operational/notifications/'+data['items'][0]['id']+'/read',{})
        self.assertEqual(response.status_code,200,response.text);self.assertFalse(response.json()['case_acknowledged'])
        with self.server.database() as db:self.assertEqual(db.execute('SELECT state FROM operational_cases').fetchone()[0],'open')
        self.login('operator');self.assertEqual(self.http.get('/api/operational/notifications').json()['items'],[])

    def test_missing_provider_tls_and_role_guards(self):
        with patch.dict(os.environ,{'EDGEOPS_SMTP_HOST':''}):self.assertEqual(self.enable().status_code,422)
        with patch.dict(os.environ,dict(SMTP,EDGEOPS_SMTP_TLS='plaintext')):self.assertIsNone(notifications.smtp_settings())
        self.login('operator');self.assertEqual(self.enable().status_code,403)
        self.login('admin')
        with patch.dict(os.environ,SMTP):
            response=self.enable();self.assertEqual(response.status_code,200,response.text)
            self.assertNotIn('fixture-secret',response.text);self.assertNotIn('fixture-user',response.text)
            self.assertEqual(self.enable(revision=0).status_code,409)

    def test_delivery_retry_receipt_and_stable_message_identity(self):
        self.pending()
        with patch.dict(os.environ,SMTP):
            self.assertEqual(self.enable().status_code,200)
            with patch.object(notifications,'send',side_effect=OSError('credential must not appear in stored error')):
                result=notifications.deliver(self.server.database);self.assertEqual(result['failed'],1)
            with self.server.database() as db:
                row=db.execute("SELECT * FROM operational_notifications WHERE email_state='pending'").fetchone()
                self.assertEqual(row['last_error'],'smtp-delivery-unconfirmed');identity=row['id']
                db.execute('UPDATE operational_notifications SET next_attempt=0')
            with patch.object(notifications,'send') as send:
                result=notifications.deliver(self.server.database);self.assertEqual(result['delivered'],1);self.assertEqual(send.call_args.args[1]['id'],identity)
                self.assertEqual(notifications.deliver(self.server.database)['delivered'],0)
            with self.server.database() as db:self.assertEqual(db.execute('SELECT attempts FROM operational_notifications WHERE id=?',(identity,)).fetchone()[0],2)

    def test_recipient_revocation_cancels_before_external_boundary(self):
        self.pending()
        with patch.dict(os.environ,SMTP):
            self.assertEqual(self.enable().status_code,200)
            with self.server.database() as db:
                operator=db.execute("SELECT id FROM users WHERE role='operator'").fetchone()[0]
                # Queue is redirected only inside this test to a user without
                # case access; dispatcher must not leak the notification.
                db.execute('UPDATE operational_notifications SET user_id=?',(operator,))
            with patch.object(notifications,'send') as send:
                result=notifications.deliver(self.server.database);self.assertEqual(result['cancelled'],1);send.assert_not_called()

    def test_smtp_requires_tls_auth_and_emits_no_sensor_payload(self):
        self.pending()
        with self.server.database() as db:row=dict(db.execute('SELECT * FROM operational_notifications LIMIT 1').fetchone())
        with patch.dict(os.environ,SMTP),patch.object(notifications.smtplib,'SMTP') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            notifications.send(notifications.smtp_settings(),row,'recipient@example.invalid')
            session=smtp.return_value.__enter__.return_value
            session.starttls.assert_called_once();session.login.assert_called_once()
            message=session.send_message.call_args.args[0]
            self.assertIn(row['id'],message['Message-ID']);self.assertNotIn('temp_c',message.get_content());self.assertNotIn('fixture-secret',message.as_string())
