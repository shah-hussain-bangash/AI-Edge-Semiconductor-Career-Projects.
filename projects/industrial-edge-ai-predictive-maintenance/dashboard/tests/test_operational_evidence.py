import unittest
import test_operational_workflow as fixture


class EvidenceTests(unittest.TestCase):
    setUp=fixture.OperationalTests.setUp
    login=fixture.OperationalTests.login
    post=fixture.OperationalTests.post
    rule=fixture.OperationalTests.rule
    ingest=fixture.OperationalTests.ingest
    summary=fixture.OperationalTests.summary

    def case(self):
        self.rule();self.assertEqual(self.ingest(temp_c=40).status_code,201)
        return self.summary()['cases'][0]

    def upload(self,case,data=b'Fixture evidence only',media='text/plain',filename='fixture.txt',csrf=True):
        headers={'content-type':media}
        if csrf:headers['x-edgeops-csrf']=self.http.cookies.get('edgeops_csrf')
        return self.http.post('/api/operational/evidence/case/'+case['id'],params={'filename':filename},content=data,headers=headers)

    def test_private_integrity_download_dedup_and_freeze(self):
        case=self.case();reply=self.upload(case);self.assertEqual(reply.status_code,201,reply.text)
        file=reply.json()['file'];self.assertEqual(file['scan_state'],'not-scanned')
        self.assertTrue(self.upload(case).json()['duplicate'])
        link='/api/operational/evidence/files/'+file['id']+'/download'
        downloaded=self.http.get(link);self.assertEqual(downloaded.content,b'Fixture evidence only');self.assertIn('attachment;',downloaded.headers['content-disposition']);self.assertEqual(downloaded.headers['content-type'],'application/octet-stream')
        self.login('operator');self.assertEqual(self.http.get(link).status_code,404)
        self.login('auditor');self.assertEqual(self.http.get(link).status_code,200);self.assertEqual(self.upload(case).status_code,403)
        self.login('admin')
        with self.server.database() as db:db.execute("UPDATE operational_cases SET state='resolved' WHERE id=?",(case['id'],))
        self.assertEqual(self.upload(case,b'Other evidence').status_code,409)
        with self.server.database() as db:db.execute('UPDATE operational_evidence SET payload=? WHERE id=?',(b'altered',file['id']))
        self.assertEqual(self.http.get(link).status_code,503)

    def test_file_validation_csrf_and_route_specific_size_limit(self):
        case=self.case();self.assertEqual(self.upload(case,csrf=False).status_code,403)
        for data,media,name,status in [(b'not a png','image/png','x.png',422),(b'\xff','text/plain','x.txt',422),(b'NaN','application/json','x.json',422),(b'valid','text/plain','../x.txt',422),(b'x','application/octet-stream','x.exe',415),(b'a'*(2097153),'text/plain','x.txt',413)]:
            with self.subTest(name=name,media=media):self.assertEqual(self.upload(case,data,media,name).status_code,status)
        self.assertEqual(self.upload(case,b'a'*9000).status_code,201)
        self.assertEqual(self.http.post('/api/operational/assets',content=b'a'*9000).status_code,413)
        self.assertEqual(self.http.post('/api/operational/evidence/case/'+case['id'],content=iter([b'a'*1048576,b'a'*1048577]),headers={'content-type':'text/plain','x-edgeops-csrf':self.http.cookies.get('edgeops_csrf')}).status_code,413)
