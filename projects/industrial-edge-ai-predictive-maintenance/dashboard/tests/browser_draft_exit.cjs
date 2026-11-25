// Real browser exit dialogs; disposable records, no autosave or hardware.
const {chromium}=require('playwright');
const {spawn}=require('child_process');
const fs=require('fs'),os=require('os'),path=require('path'),net=require('net'),crypto=require('crypto');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON_BINARY||'python';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'edgeops-draft-exit-')),password=crypto.randomBytes(24).toString('hex');
const env={...process.env,PYTHONDONTWRITEBYTECODE:'1',EDGEOPS_DASHBOARD_DB:path.join(temp,'auth.db'),EDGEOPS_ADMIN_EMAIL:'exit@example.invalid',EDGEOPS_ADMIN_PASSWORD:password};
const socket=net.createServer();socket.listen(0,'127.0.0.1',async()=>{
 const port=socket.address().port;await new Promise(r=>socket.close(r));const base=`http://127.0.0.1:${port}`;
 const service=spawn(python,['-m','uvicorn','server:app','--host','127.0.0.1','--port',String(port)],{cwd:root,env,stdio:['ignore','pipe','pipe'],windowsHide:true});
 let log='',browser;service.stderr.on('data',x=>log+=x);
 const assert=(value,message)=>{if(!value)throw Error(message);};
 try{
  for(let i=0;i<80;i++){try{if((await fetch(base+'/signin')).ok)break;}catch{}await new Promise(r=>setTimeout(r,150));}
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
  const errors=[];
  async function login(){const context=await browser.newContext();const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));await page.goto(base+'/signin');await page.locator('#email').fill(env.EDGEOPS_ADMIN_EMAIL);await page.locator('#password').fill(password);await page.locator('#submit').click();await page.waitForURL('**/app');await page.locator('#connection-chip[data-state="ok"]').waitFor();return page;}
  async function reload(page,count,accept=false){
   const dialogs=[];const handle=async dialog=>{dialogs.push(dialog.type());await (accept?dialog.accept():dialog.dismiss());};page.on('dialog',handle);
   try{await page.reload({timeout:10000}).catch(error=>{if(!dialogs.length)throw error;});}finally{page.off('dialog',handle);}
   assert(dialogs.length===count&&dialogs.every(type=>type==='beforeunload'),'Unexpected reload dialog sequence: '+JSON.stringify(dialogs));
   if(count===0||accept)await page.locator('#connection-chip[data-state="ok"]').waitFor();
  }
  async function close(page,accept){
   const dialogPromise=page.waitForEvent('dialog',{timeout:5000});
   dialogPromise.catch(()=>{}); // Allow the main catch/finally to clean up on a premature close.
   const closed=accept?page.waitForEvent('close'):null;
   if(closed)closed.catch(()=>{});
   await page.close({runBeforeUnload:true});const dialog=await dialogPromise;
   assert(dialog.type()==='beforeunload','Exit did not use a browser-owned beforeunload warning');
   await (accept?dialog.accept():dialog.dismiss());if(closed)await closed;
  }
  const page=await login();
  const csrf=(await page.context().cookies()).find(c=>c.name==='edgeops_csrf').value;
  const created=await page.request.post(base+'/api/incidents',{headers:{'x-edgeops-csrf':csrf},data:{request_key:crypto.randomBytes(16).toString('hex'),source_type:'synthetic',asset_id:'MTR-001',title:'Synthetic browser exit example',observation:'An explicitly saved synthetic baseline.',severity:'watch',evidence_refs:''}});
  assert(created.ok(),'Incident fixture creation failed');const incident=(await created.json()).incident;
  async function openIncident(){await page.locator('.nav-item[data-page="alerts"]').click();await page.locator('#incident-refresh').click();await page.locator('[data-incident-open="'+incident.id+'"]').click();await page.locator('#incident-action-note').waitFor();}
  await openIncident();await reload(page,0);await openIncident();
  const marker='Unsaved synthetic exit marker';await page.locator('#incident-action-note').fill(marker);
  await reload(page,1);assert(await page.locator('#incident-action-note').inputValue()===marker,'Cancelled reload lost incident text');
  await close(page,false);assert(!page.isClosed()&&await page.locator('#incident-action-note').inputValue()===marker,'Cancelled close lost incident text');
  await reload(page,1,true);await openIncident();assert(await page.locator('#incident-action-note').inputValue()==='','Accepted reload silently restored a private draft');
  await page.locator('#incident-action-note').fill(marker);
  await page.locator('.nav-item[data-page="maintenance"]').click();await page.locator('#planning-new').click();await page.locator('#plan-proposal').fill(marker);
  await reload(page,1);assert(await page.locator('#plan-proposal').inputValue()===marker,'Cancelled reload lost planning text');
  await page.locator('#planning-dialog-close').click();await page.locator('#planning-draft-discard').click();
  await reload(page,1); // Clearing the planning guard must not remove the incident guard.
  await page.locator('.nav-item[data-page="alerts"]').click();await page.locator('#incident-action-note').fill('');
  await reload(page,0);await openIncident();await page.locator('#incident-history-search').fill('read-only search');await reload(page,0);
  const planning=await login();await planning.locator('.nav-item[data-page="maintenance"]').click();await planning.locator('#planning-new').click();await planning.locator('#plan-proposal').fill(marker);
  await close(planning,false);assert(await planning.locator('#plan-proposal').inputValue()===marker,'Cancelled close lost planning draft');
  const storage=await planning.evaluate(()=>[...Object.values(localStorage),...Object.values(sessionStorage)].join('\n'));
  assert(!storage.includes(marker),'Private draft was persisted in browser storage');await close(planning,true);
  const saved=await (await page.request.get(base+'/api/incidents/'+incident.id)).json();
  const plans=await (await page.request.get(base+'/api/maintenance-requests')).json();
  assert(saved.incident.revision===1&&!JSON.stringify(saved).includes(marker)&&plans.requests.length===0,'Exit warnings autosaved or mutated domain records');
  assert(errors.length===0,'Browser errors: '+errors.join(' | '));
  console.log('PASS: clean and read-only reloads; dirty incident/planning reload and close cancellation; accepted reload/close; independent guard cleanup; source revision unchanged; no draft autosave or browser storage.');
 }catch(error){console.error(error);console.error(log);process.exitCode=1;}
 finally{if(browser)await browser.close();service.kill();await new Promise(r=>service.once('exit',r));if(path.dirname(path.resolve(temp))!==path.resolve(os.tmpdir())||!path.basename(temp).startsWith('edgeops-draft-exit-'))throw Error('Unexpected temporary path');fs.rmSync(temp,{recursive:true,force:true});}
});
