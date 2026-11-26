import io
from contextlib import closing
import json
from pathlib import Path
import unittest
import zipfile
import private_crypto
import protected_recovery
import recovery
import test_operational_workflow as fixture


class ProtectedRecoveryTests(unittest.TestCase):
    setUp=fixture.OperationalTests.setUp
    login=fixture.OperationalTests.login
    post=fixture.OperationalTests.post
    rule=fixture.OperationalTests.rule
    ingest=fixture.OperationalTests.ingest
    summary=fixture.OperationalTests.summary

    def test_encrypted_backup_roundtrip_and_restore_disables_effects(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        case=self.summary()['cases'][0]
        upload=self.http.post('/api/operational/evidence/case/'+case['id']+'?filename=fixture.txt',content=b'Private backup evidence fixture',headers={'content-type':'text/plain','x-edgeops-csrf':self.http.cookies.get('edgeops_csrf')})
        self.assertEqual(upload.status_code,201,upload.text)
        root=Path(self.temp.name);key=root/'private.key';private_crypto.generate(key)
        output=root/'backup.enc'
        report=protected_recovery.backup(self.server.DB_PATH,key,output)
        self.assertTrue(report['encrypted']);self.assertFalse(report['key_included']);self.assertNotIn(b'Isolated fixture motor',output.read_bytes())
        unsealed=protected_recovery.unseal(output,key,root/'unpacked')
        recovery.verify_backup(unsealed['decrypted_backup'])
        restored=root/'restored';recovery.restore_backup(unsealed['decrypted_backup'],restored)
        report=json.loads((restored/'restore-report.json').read_text(encoding='utf-8'))
        self.assertGreater(report['bench_credentials_revoked'],0);self.assertEqual(report['operational_rules_disabled'],1)
        import sqlite3
        with closing(sqlite3.connect(restored/'dashboard.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM operational_cases').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT payload FROM operational_evidence').fetchone()[0],b'Private backup evidence fixture')
            self.assertEqual(db.execute('SELECT sum(enabled) FROM operational_rules').fetchone()[0],0)
        self.assertEqual(self.summary()['rules'][0]['enabled'],1,'Original live fixture database untouched')

    def test_tamper_wrong_key_and_existing_destinations_preserved(self):
        root=Path(self.temp.name);key=root/'key';private_crypto.generate(key);output=root/'backup.enc'
        protected_recovery.backup(self.server.DB_PATH,key,output)
        original=output.read_bytes()
        with self.assertRaises(ValueError):protected_recovery.backup(self.server.DB_PATH,key,output)
        self.assertEqual(output.read_bytes(),original)
        other=root/'other-key';private_crypto.generate(other)
        with self.assertRaises(Exception):protected_recovery.unseal(output,other,root/'wrong-key')
        self.assertFalse((root/'wrong-key').exists())
        output.write_bytes(original[:-5]+b'bad!!')
        with self.assertRaises(Exception):protected_recovery.unseal(output,key,root/'tampered')
        self.assertFalse((root/'tampered').exists())

    def test_authenticated_traversal_archive_is_not_extracted(self):
        root=Path(self.temp.name);key=root/'key';private_crypto.generate(key)
        payload=io.BytesIO()
        with zipfile.ZipFile(payload,'w',zipfile.ZIP_STORED) as archive:archive.writestr('../outside.txt',b'unsafe fixture')
        token=root/'malicious.enc';token.write_bytes(private_crypto.cipher(key).encrypt(payload.getvalue()))
        with self.assertRaises(ValueError):protected_recovery.unseal(token,key,root/'new-output')
        self.assertFalse((root/'outside.txt').exists());self.assertFalse((root/'new-output').exists())

    def test_backup_source_inventory_not_modified_and_output_never_inside_source(self):
        root=Path(self.temp.name);key=root/'key';private_crypto.generate(key);backup=root/'snapshot'
        recovery.create_backup(self.server.DB_PATH,backup)
        original=recovery.verify_backup(backup)
        with self.assertRaises(ValueError):protected_recovery.seal(backup,key,backup/'bad.enc')
        self.assertEqual(recovery.verify_backup(backup),original)
