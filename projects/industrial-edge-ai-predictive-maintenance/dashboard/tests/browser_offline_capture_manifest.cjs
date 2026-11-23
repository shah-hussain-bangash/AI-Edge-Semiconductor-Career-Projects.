const {chromium}=require('playwright');
const {auditContrast}=require('./contrast.cjs');
const {spawn,spawnSync}=require('child_process');
const fs=require('fs'),os=require('os'),path=require('path'),net=require('net'),crypto=require('crypto');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON_BINARY||'python';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'edgeops-offline-capture-review-')),password=crypto.randomBytes(24).toString('hex');
const env={...process.env,PYTHONDONTWRITEBYTECODE:'1',EDGEOPS_DASHBOARD_DB:path.join(temp,'auth.db'),EDGEOPS_DELIVERY_SPOOL_DB:path.join(temp,'delivery-spool.sqlite3'),EDGEOPS_ADMIN_EMAIL:'admin@example.invalid',EDGEOPS_ADMIN_PASSWORD:password};
const seed=spawnSync(python,['-c',`import server,os
server.init_db()
with server.database() as db:
 for email,role in [('creator@example.invalid','operator'),('assignee@example.invalid','operator'),('other@example.invalid','operator'),('auditor@example.invalid','auditor')]:
  db.execute('INSERT INTO users(email,password_hash,role) VALUES(?,?,?)',(email,server.password_hash(os.environ['EDGEOPS_ADMIN_PASSWORD']),role))`],{cwd:root,env,encoding:'utf8'});
if(seed.status!==0)throw Error(seed.stderr);

const evidence=spawnSync(python,['-c',`import importlib.util,json,csv,io
from pathlib import Path
root=Path.cwd().parent/'phase-01-hardware'
spec=importlib.util.spec_from_file_location('offline_capture_fixture',root/'scripts/prepare_capture.py');adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
base=Path(__import__('os').environ['EDGEOPS_DASHBOARD_DB']).parent
mapping=json.loads((root/'examples/offline-capture/synthetic.attachment.json').read_bytes())
for source in ('synthetic','measured','replayed'):
 mapping['source_type']=source;attachment=base/(source+'.attachment.json');attachment.write_bytes(adapter.json_bytes(mapping))
 adapter.prepare(root/'examples/offline-capture/synthetic.capture.csv',attachment,base/source)
mapping['source_type']='synthetic';attachment=base/'synthetic.attachment.json'
rows=list(csv.reader(io.StringIO((root/'examples/offline-capture/synthetic.capture.csv').read_text(encoding='utf-8'))))
for name,values in [('empty',rows[:1]),('quarantine',[rows[0],rows[1][:-1]+['False'],rows[2]])]:
 source=base/(name+'.csv');stream=io.StringIO(newline='');csv.writer(stream).writerows(values);source.write_text(stream.getvalue(),encoding='utf-8')
 adapter.prepare(source,attachment,base/name)
`],{cwd:root,env,encoding:'utf8'});if(evidence.status!==0)throw Error(evidence.stderr);
const socket=net.createServer();socket.listen(0,'127.0.0.1',async()=>{
 const port=socket.address().port;await new Promise(r=>socket.close(r));const base=`http://127.0.0.1:${port}`;
 const service=spawn(python,['-m','uvicorn','server:app','--host','127.0.0.1','--port',String(port)],{cwd:root,env,stdio:['ignore','pipe','pipe'],windowsHide:true});let log='',browser;service.stderr.on('data',x=>log+=x);
 const assert=(value,message)=>{if(!value)throw Error(message);};
 try{
  for(let i=0;i<80;i++){try{if((await fetch(base+'/signin')).ok)break;}catch{}await new Promise(r=>setTimeout(r,150));}
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});const errors=[];
  async function login(email){const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});page.on('pageerror',e=>errors.push(String(e)));await page.goto(base+'/signin');await page.locator('#email').fill(email);await page.locator('#password').fill(password);await page.locator('#submit').click();await page.waitForURL('**/app');await page.locator('.nav-item[data-page="devices"]').click();await page.locator('#registry-feedback').getByText(/Persisted synthetic bindings loaded/).waitFor();return page;}




  const page=await login('creator@example.invalid');await page.locator('.nav-item[data-page="telemetry"]').click();await page.waitForFunction(()=>physicalBuildState==='ok'&&hardwareCatalog.state==='ok');await page.locator('#persisted-device-status').getByText(/No test devices yet/).waitFor();const calls=[],writes=[];page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/')){calls.push(r.method()+' '+r.url());if(r.method()!=='GET')writes.push(r.url());}});
  const file=page.locator('#offline-capture-file'),feedback=page.locator('#offline-capture-feedback');
  const raw=fs.readFileSync(path.join(temp,'synthetic/manifest.json')),manifest=JSON.parse(raw);
  async function load(value,name='manifest.json'){await file.setInputFiles({name,mimeType:'application/json',buffer:Buffer.isBuffer(value)?value:Buffer.from(typeof value==='string'?value:JSON.stringify(value))});}
  async function loaded(){await feedback.getByText(/Manifest structure supported/).waitFor();}
  async function rejected(){await feedback.getByText(/Manifest unavailable/).waitFor();assert(await page.locator('#offline-capture-summary dd').count()===0&&await page.locator('#offline-capture-files tr').count()===0&&await page.locator('#offline-capture-export').isDisabled()&&await page.locator('#offline-capture-context').innerText()==='','Invalid manifest retained old data/export');}
  for(const source of ['synthetic','measured','replayed','empty','quarantine']){const data=fs.readFileSync(path.join(temp,source+'/manifest.json'));await load(data,source+'-manifest.json');await loaded();const expected=JSON.parse(data),facts=await page.locator('#offline-capture-summary dd').allTextContents();assert(facts[0]===expected.source_type+' · operator-declared'&&facts[1]===String(expected.input_rows)&&facts[2]===String(expected.accepted_rows)&&facts[3]===String(expected.quarantined_rows),'Declared source/count changed');assert(facts[5]===(expected.requires_review?'Review required':'Not requested · not acceptance'),'Review flag misrepresented');assert(await page.locator('#offline-capture-files tr').count()===4,'Declared file references omitted');}
  await load(raw,'<manifest>.json');await loaded();await page.locator('#offline-capture-export').focus();const downloaded=page.waitForEvent('download');await page.keyboard.press('Enter');const download=await downloaded;assert(download.suggestedFilename()==='edgeops-offline-capture-metadata-review.json','Unexpected metadata export filename');const report=JSON.parse(fs.readFileSync(await download.path(),'utf8'));assert(JSON.stringify(report.manifest)===JSON.stringify(manifest)&&report.file_sha256===crypto.createHash('sha256').update(raw).digest('hex')&&report.file_bytes===raw.length,'Export changed manifest or file fingerprint');assert(report.manifest_structure_checked===true,'Export omitted structure-only scope');for(const key of ['package_files_checked','source_transformation_recomputed','source_authenticated','uploaded','persisted','physical_source_verified','calibration_verified','hardware_connected','ready_for_ingestion','equipment_authorized','production_ready'])assert(report[key]===false,'Metadata review gained authority '+key);assert(await page.locator('#offline-capture-panel img').count()===0,'Manifest file name became markup');
  const changes=[d=>d.production_ready=true,d=>d.physical_source_verified=true,d=>d.source_type='live',d=>d.source_classification='authenticated',d=>d.boot_identity='verified',d=>d.input_rows=false,d=>d.accepted_rows='2',d=>d.input_rows=-1,d=>d.input_rows=10001,d=>d.accepted_rows=1.5,d=>d.requires_review=true,d=>d.accepted_sequence_gaps=-1,d=>d.accepted_sequence_gaps=4294967296,d=>d.created_at='2026-02-31T00:00:00Z',d=>d.created_at='2026-11-20T10:00:00',d=>d.files['source.capture.csv'].bytes=16*1024*1024+1,d=>d.files['attachment.json'].bytes=8193,d=>d.files['observations.jsonl'].sha256='bad',d=>d.files['quarantine.jsonl'].bytes=true,d=>d.files['unknown.txt']=d.files['quarantine.jsonl'],d=>delete d.files['source.capture.csv'],d=>d.extra='unsupported'];
  changes.push(d=>d.hardware_connected=0,d=>d.files['observations.jsonl'].bytes=0,d=>d.files['quarantine.jsonl'].bytes=1);
  for(const change of changes){const invalid=structuredClone(manifest);change(invalid);await load(invalid);await rejected();}
  for(const text of ['null','[]','{}','{"format":"first","format":"second"}',raw.toString().replace('"format":','"format":"duplicate","format":'),raw.toString().replace('"sha256":','"sha256":"duplicate","sha256":'),'['.repeat(20)+']'.repeat(20),Buffer.from([0xff]),'x'.repeat(65537),raw.toString()+' trailing']){await load(text);await rejected();}
  const escapedKey='"'+String.fromCharCode(92)+'u0066ormat"';await load(raw.toString().replace('"format":',escapedKey+':"duplicate","format":'));await rejected();await load('  '+JSON.stringify(manifest,null,2)+'  ');await loaded();
  await load(raw);await loaded();await page.locator('#offline-capture-clear').click();assert(await file.inputValue()===''&&await file.evaluate(n=>n===document.activeElement)&&await page.locator('#offline-capture-export').isDisabled(),'Clear retained data or lost focus');
  await page.evaluate(()=>{window.slowManifest=readOfflineCaptureManifest({size:1,name:'slow.json',arrayBuffer:()=>new Promise(resolve=>window.releaseManifest=resolve)});});await page.locator('#offline-capture-clear').click();await page.evaluate(text=>window.releaseManifest(new TextEncoder().encode(text).buffer),raw.toString());await page.evaluate(()=>window.slowManifest);assert(await page.locator('#offline-capture-export').isDisabled(),'Late read restored cleared metadata');
  await page.evaluate(()=>{window.slowManifest=readOfflineCaptureManifest({size:1,name:'old.json',arrayBuffer:()=>new Promise(resolve=>window.releaseManifest=resolve)});});const quarantined=fs.readFileSync(path.join(temp,'quarantine/manifest.json'));await load(quarantined);await loaded();await page.evaluate(text=>window.releaseManifest(new TextEncoder().encode(text).buffer),raw.toString());await page.evaluate(()=>window.slowManifest);assert((await page.locator('#offline-capture-summary dd').allTextContents())[3]==='1','Old manifest replaced newer quarantine declaration');
  assert(calls.length===0&&writes.length===0,'Local metadata review contacted service '+calls.join(','));assert(await page.locator('#persisted-rows tr').count()===0&&await page.locator('#persisted-export').isDisabled(),'Offline manifest populated persisted readings');
  const auditor=await login('auditor@example.invalid');await auditor.locator('.nav-item[data-page="telemetry"]').click();await auditor.locator('#offline-capture-file').setInputFiles({name:'auditor.json',mimeType:'application/json',buffer:raw});await auditor.locator('#offline-capture-feedback').getByText(/Manifest structure supported/).waitFor();assert(await auditor.locator('#offline-capture-export').isEnabled()&&await auditor.locator('#registry-create').isHidden(),'Metadata review changed auditor rights');
  const contrast=await auditContrast(page);assert(contrast.failures.length===0,'Offline metadata contrast '+JSON.stringify(contrast.failures));const captures=path.join(root,'.acceptance-captures');fs.mkdirSync(captures,{recursive:true});for(const width of [1440,1024,768,390,320]){await page.setViewportSize({width,height:1000});await file.evaluate(n=>n.scrollIntoView({block:'start'}));assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'Offline metadata page overflow '+width);if(width===1440||width===390)await page.screenshot({path:path.join(captures,'offline-capture-manifest-'+width+'.png')});}
  await page.reload();assert(await page.locator('#offline-capture-summary dd').count()===0&&await page.locator('#offline-capture-export').isDisabled(),'Reload retained manifest');assert(writes.length===0&&errors.length===0,'Domain write/browser error '+errors.join(' | '));console.log('PASS: adapter-generated manifest review for declared synthetic/measured/replayed, empty and quarantined captures; exact metadata/hash export with false package/physical authority; bounded typed structure/counters/provenance/time/files/duplicate JSON/depth/encoding rejection; no service calls, ingestion or storage; clear/newer-file races, auditor access, contrast and five widths.');
 }catch(error){console.error(error);console.error(log);process.exitCode=1;}
 finally{if(browser)await browser.close();service.kill();await new Promise(r=>service.once('exit',r));if(path.dirname(path.resolve(temp))!==path.resolve(os.tmpdir())||!path.basename(temp).startsWith('edgeops-offline-capture-review-'))throw Error('Unexpected temporary path');fs.rmSync(temp,{recursive:true,force:true});}
});
