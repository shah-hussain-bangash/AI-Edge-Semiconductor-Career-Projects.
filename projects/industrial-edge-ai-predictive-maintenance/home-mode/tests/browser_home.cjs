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
  child=spawn(process.env.PYTHON_BINARY||'python',['home-mode/tests/run_browser_server.py','--data-dir',directory,'--web-port',String(port),'--mode','demo','--connect'],{cwd:root,stdio:['pipe','pipe','pipe']});
  child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
  await until(async()=>{const r=await fetch(url+'/api/status');return r.ok;});
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url+'/app');
  await until(async()=> (await page.locator('#source').innerText())==='SIMULATED / TEST');
  assert.equal(await page.locator('.card').count(),6);
  assert.equal(await page.locator('.card').nth(1).locator('.value').innerText(),'0');
  await page.locator('#refresh-history').click();
  await until(async()=> (await page.locator('#history').innerText()).includes('simulated / demo'));
  const csv=await (await page.request.get(url+'/api/history.csv?limit=60')).text();
  assert.match(csv,/simulated,demo,software-demo/);assert.match(csv,/False,False,False/);
  for(const width of [320,390,768,1024,1440]){
   await page.setViewportSize({width,height:1000});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No page overflow at '+width);
   const contrast=await auditContrast(page);assert.deepEqual(contrast.failures,[],'Contrast at '+width+': '+JSON.stringify(contrast.failures));
  }
  await page.locator('#disconnect').click();
  await until(async()=> (await page.locator('#session-state').innerText()).includes('disconnected'));
  assert.deepEqual(await page.locator('.value').allTextContents(),Array(6).fill('Unavailable'));
  assert.match(await page.locator('#history').innerText(),/simulated/);
  await page.locator('#mode').selectOption('esp32-only');
  // Deliberately missing fixture device; never choose any enumerated real port.
  await page.locator('#port').fill(process.platform==='win32'?'COM999':'/dev/cu.edgeops_missing_fixture');
  await page.locator('#connect').click();
  await until(async()=> (await page.locator('#session-state').innerText()).includes('error'));
  assert.deepEqual(await page.locator('.value').allTextContents(),Array(6).fill('Unavailable'));
  assert.match(await page.locator('#mode-help').innerText(),/simulated/);
  await page.route('**/api/status',route=>route.abort());
  await until(async()=> (await page.locator('#source').innerText())==='LOCAL SERVICE UNAVAILABLE');
  assert.deepEqual(await page.locator('.value').allTextContents(),Array(6).fill('Unavailable'));
  assert.equal(await page.locator('#connect').isDisabled(),true);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'passed',checks:['demo labelled simulated','six cards and valid zero','source-labelled history and CSV','five widths and solid-surface contrast','stop clears current values','missing serial fixture never fabricates values','status outage clears controls and values'],physical_hardware_verified:false}));
 }catch(error){console.error(logs);throw error;}
 finally{
  if(browser)await browser.close();
  if(child&&child.exitCode===null){const ended=new Promise(resolve=>child.once('exit',resolve));child.stdin.end();await ended;}
  await fs.rm(directory,{recursive:true,force:true});
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
