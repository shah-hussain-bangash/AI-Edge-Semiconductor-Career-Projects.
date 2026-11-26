/* Software fixtures only: no USB board, model or remote portal. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),net=require('node:net');
const {chromium}=require('playwright');
const {auditContrast}=require('../../dashboard/tests/contrast.cjs');
const root=path.resolve(__dirname,'../..');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function freePort(){return new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});}
async function until(check){for(let i=0;i<120;i++){try{if(await check())return;}catch{}await sleep(100);}throw Error('Fixture condition timed out');}
(async()=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'edgeops-home-browser-'));
 const port=await freePort(),url='http://127.0.0.1:'+port;
 let child,browser,logs='';
 try{
  // Seed one explicitly simulated archived recording; no serial device is opened.
  const seedCode="import sys; from pathlib import Path; sys.path.insert(0,'home-mode'); from home_core import parse_line; from home_recording import Recorder; s=dict(mode='esp32-only',port='COM3',expected_device_id='motor-001'); r=Recorder(Path(sys.argv[1])/'captures','f'*32,s,10); b=b'ESP32 is working!\\n'; r.write(b); r.classify('accepted',parse_line(b,'esp32-only','motor-001')); r.finish('manual-stop')";
  await new Promise((resolve,reject)=>{const seed=spawn(process.env.PYTHON_BINARY||'python',['-c',seedCode,directory],{cwd:root,stdio:['ignore','ignore','pipe']});let error='';seed.stderr.on('data',b=>error+=b);seed.on('exit',code=>code===0?resolve():reject(Error('Archive fixture failed: '+error)));});
  child=spawn(process.env.PYTHON_BINARY||'python',['home-mode/tests/run_browser_server.py','--data-dir',directory,'--web-port',String(port),'--mode','demo','--connect'],{cwd:root,stdio:['pipe','pipe','pipe']});
  child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
  await until(async()=>{const r=await fetch(url+'/api/status');return r.ok;});
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url+'/app');
  await until(async()=> (await page.locator('#source').innerText())==='SIMULATED / TEST');
  assert.equal(await page.locator('.card').count(),6);
  assert.match(await page.locator('#connection-checks').innerText(),/Software demo selected: no USB communication/);
  await page.locator('#refresh-diagnostics').click();
  await until(async()=> (await page.locator('#diagnostics-status').innerText()).includes('Physical acceptance remains pending'));
  assert.equal(await page.locator('#export-diagnostics').isVisible(),true);
  const diagnostic=await (await page.request.get(url+'/api/diagnostics')).json();
  assert.equal(diagnostic.reader.communication,'not-demonstrated');
  assert.deepEqual(Object.values(diagnostic.reader.sensor_groups),Array(3).fill('unavailable'));
  assert.equal(diagnostic.hardware_verified,false);assert.equal(diagnostic.write_token,undefined);
  const guide=await page.request.get(url+'/guide/mac');assert.equal(guide.status(),200);assert.match(await guide.text(),/macOS Terminal/);
  assert.equal(await page.locator('#record-session').isDisabled(),true,'Demo cannot record USB');
  await until(async()=> (await page.locator('#library').innerText()).includes('simulated'));
  assert.equal(await page.locator('#library a').count(),1);
  await page.getByRole('button',{name:'Review baseline quality',exact:true}).click();
  await until(async()=> (await page.locator('#baseline-report').innerText()).includes('Physical acceptance: pending'));
  assert.match(await page.locator('#baseline-report').innerText(),/communication-test-only-no-sensor-baseline/);
  assert.equal(await page.locator('#export-baseline').isVisible(),true);
  const baseline=await (await page.request.get(url+'/api/captures/'+('f'.repeat(32))+'/review.json')).json();
  assert.equal(baseline.window.sensor_groups.adxl345.declared_valid,0);
  assert.equal(baseline.outcome,'review-required');
  const saved=await page.request.get(url+'/api/captures/'+('f'.repeat(32))+'.zip');assert.equal(saved.status(),200);
  assert.match(saved.headers()['content-type'],/application\/zip/);
  assert.equal(await page.locator('#export-capture').isVisible(),false);
  assert.equal(await page.locator('.card').nth(1).locator('.value').innerText(),'0');
  await page.locator('#refresh-history').click();
  await until(async()=> (await page.locator('#history').innerText()).includes('simulated / demo'));
  const csv=await (await page.request.get(url+'/api/history.csv?limit=60')).text();
  assert.match(csv,/simulated,demo,software-demo/);assert.match(csv,/False,False,False/);
  assert.match(await page.locator('#host-platform').innerText(),/USB hardware must be connected to this computer/);
  await page.locator('#session-summary').click();
  await until(async()=> (await page.locator('#session-report').innerText()).includes('Physical acceptance: pending'));
  assert.equal(await page.locator('#export-session').isVisible(),true);
  const packageResponse=await page.request.get(url+'/api/session.zip');
  assert.equal(packageResponse.status(),200);assert.match(packageResponse.headers()['content-type'],/application\/zip/);
  for(const width of [320,390,768,1024,1440]){
   await page.setViewportSize({width,height:1000});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No page overflow at '+width);
   const contrast=await auditContrast(page);assert.deepEqual(contrast.failures,[],'Contrast at '+width+': '+JSON.stringify(contrast.failures));
  }
  await page.locator('#disconnect').click();
  await until(async()=> (await page.locator('#session-state').innerText()).includes('disconnected'));
  assert.deepEqual(await page.locator('.value').allTextContents(),Array(6).fill('Unavailable'));
  assert.match(await page.locator('#history').innerText(),/simulated/);
  assert.equal(await page.locator('#export-session').isVisible(),true,'Stopped session remains exportable');
  await page.locator('#mode').selectOption('esp32-only');
  // Deliberately missing fixture device; never choose any enumerated real port.
  await page.locator('#port').fill(process.platform==='win32'?'COM999':'/dev/cu.edgeops_missing_fixture');
  assert.equal(await page.locator('#record-session').isDisabled(),false);
  await page.locator('#record-session').click();
  await until(async()=> (await page.locator('#session-state').innerText()).includes('error'));
  assert.deepEqual(await page.locator('.value').allTextContents(),Array(6).fill('Unavailable'));
  assert.match(await page.locator('#mode-help').innerText(),/simulated/);
  assert.equal(await page.locator('#export-capture').isVisible(),false,'Port failure never fabricates raw capture');
  await page.route('**/api/status',route=>route.abort());
  await until(async()=> (await page.locator('#source').innerText())==='LOCAL SERVICE UNAVAILABLE');
  assert.deepEqual(await page.locator('.value').allTextContents(),Array(6).fill('Unavailable'));
  assert.equal(await page.locator('#connect').isDisabled(),true);
  assert.equal(await page.locator('#export-session').isVisible(),false,'Outage clears session link');
  assert.equal(await page.locator('#library a').count(),0,'Outage clears archive links');
  assert.equal(await page.locator('#export-diagnostics').isVisible(),false,'Outage clears diagnostic link');
  assert.equal(await page.locator('#export-baseline').isVisible(),false,'Outage clears baseline link');
  assert.match(await page.locator('#baseline-report').innerText(),/Previous report cleared/);
  assert.equal(await page.locator('#connection-checks li').count(),0,'Outage clears connection checklist');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'passed',checks:['demo labelled simulated','six cards and valid zero','source-labelled history and CSV','five widths and solid-surface contrast','stop clears current values','missing serial fixture never fabricates values','status outage clears controls and values','host location guidance','session summary remains pending','ZIP session export and stop/outage states','demo raw-recording refusal','USB recording port failure does not fabricate capture','saved recording library and historical ZIP','archive links clear on outage','demo cannot pass USB checklist or sensor diagnostics','allowlisted Mac guide available offline','outage clears troubleshooting link and checklist','raw baseline review never approves communication-only data','outage clears baseline report and link'],physical_hardware_verified:false}));
 }catch(error){console.error(logs);throw error;}
 finally{
  if(browser)await browser.close();
  if(child&&child.exitCode===null){const ended=new Promise(resolve=>child.once('exit',resolve));child.stdin.end();await ended;}
  await fs.rm(directory,{recursive:true,force:true});
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
