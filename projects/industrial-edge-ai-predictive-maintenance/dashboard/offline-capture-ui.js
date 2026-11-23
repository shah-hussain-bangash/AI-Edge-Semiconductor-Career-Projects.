"use strict";
let offlineCaptureSequence=0,offlineCaptureReview=null,offlineCaptureReading=false;
let offlineQuarantineSequence=0,offlineQuarantineReview=null,offlineQuarantineManifest=null,offlineQuarantineReading=false,offlineQuarantinePage=0;
const offlineQuarantineLimit=2*1024*1024;
const offlineQuarantineReasons={
 'invalid-csv-row':'Capture columns or values are incomplete or unexpected. Inspect the original CSV.',
 'attachment-device-mismatch':'The V1 device ID differs from the attachment mapping. This does not authenticate either identity.',
 'invalid-counter':'Counter text is outside the supported unsigned decimal format.',
 'counter-out-of-range':'A counter exceeds the V1 unsigned 32-bit range.',
 'invalid-receipt-time':'Gateway receipt text is not a supported timestamp.',
 'receipt-time-without-timezone':'The declared receipt time lacks a timezone. Actual clock quality is not established.',
 'invalid-boolean':'Validity flags must use the capture writer’s True or False text.',
 'inconsistent-validity':'The aggregate validity flag disagrees with the sensor flags.',
 'invalid-number':'A numeric field is malformed or exceeds the supported text length.',
 'nonfinite-number':'A numeric field is not finite.',
 'unresolved-session-or-clock-discontinuity':'Sequence, uptime or receipt order has an unresolved boundary. Later records remain quarantined; this is not proof of a reboot or packet loss.'
};
const offlineCaptureFiles=['source.capture.csv','attachment.json','observations.jsonl','quarantine.jsonl'];

// Preserve JSON types while refusing duplicate keys, excessive nesting and tokens.
function parseOfflineCaptureJson(text,label='manifest'){
 let index=0,tokens=0;const fail=()=>{throw new Error('Use an unmodified supported JSON '+label+' without duplicate keys.');},space=()=>{while(/[\x20\t\r\n]/.test(text[index]||'!'))index++;};
 function string(){const start=index++;while(index<text.length){if(text[index]==='\\'){index+=2;continue;}if(text[index++]==='"')return JSON.parse(text.slice(start,index));}fail();}
 function value(depth=0){
  if(++tokens>512||depth>8)fail();space();const char=text[index];
  if(char==='"')return string();
  if(char==='{'){index++;const result=Object.create(null),seen=new Set();space();if(text[index]==='}'){index++;return result;}while(index<text.length){space();if(text[index]!=='"')fail();const key=string();if(seen.has(key))fail();seen.add(key);space();if(text[index++]!==':')fail();result[key]=value(depth+1);space();const separator=text[index++];if(separator==='}')return result;if(separator!==',')fail();}fail();}
  if(char==='['){index++;const result=[];space();if(text[index]===']'){index++;return result;}while(index<text.length){result.push(value(depth+1));space();const separator=text[index++];if(separator===']')return result;if(separator!==',')fail();}fail();}
  const token=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(text.slice(index));if(!token)fail();index+=token[0].length;const result=JSON.parse(token[0]);if(typeof result==='number'&&!Number.isFinite(result))fail();return result;
 }
 const result=value();space();if(index!==text.length)fail();return result;
}
function validateOfflineCaptureManifest(data){
 const keys=['format','created_at','source_type','source_classification','input_rows','accepted_rows','quarantined_rows','accepted_sequence_gaps','requires_review','boot_identity','physical_source_verified','calibration_verified','hardware_connected','ready_for_ingestion','production_ready','files'];
 const exact=(object,expected)=>object&&typeof object==='object'&&!Array.isArray(object)&&Object.keys(object).length===expected.length&&expected.every(key=>Object.prototype.hasOwnProperty.call(object,key));
 const fail=()=>{throw new Error('Unsupported capture manifest structure, counts or verification claims.');};
 if(!exact(data,keys)||data.format!=='edgeops-v1-csv-to-v2-evidence-v1'||!['synthetic','measured','replayed'].includes(data.source_type)||data.source_classification!=='operator-declared; not physical authentication'||data.boot_identity!=='unavailable')fail();
 for(const key of ['physical_source_verified','calibration_verified','hardware_connected','ready_for_ingestion','production_ready'])if(data[key]!==false)fail();
 for(const key of ['input_rows','accepted_rows','quarantined_rows'])if(!Number.isInteger(data[key])||data[key]<0||data[key]>10000)fail();
 if(data.accepted_rows+data.quarantined_rows!==data.input_rows||!Number.isInteger(data.accepted_sequence_gaps)||data.accepted_sequence_gaps<0||data.accepted_sequence_gaps>4294967295||(data.accepted_rows<2&&data.accepted_sequence_gaps!==0)||typeof data.requires_review!=='boolean'||data.requires_review!==(data.quarantined_rows>0||data.accepted_rows===0))fail();
 const time=data.created_at;if(typeof time!=='string'||!/^\d{4}-\d\d-\d\dT(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(time)||time.startsWith('0000')||!Number.isFinite(Date.parse(time))||new Date(time.slice(0,10)+'T00:00:00Z').toISOString().slice(0,10)!==time.slice(0,10))fail();
 if(!exact(data.files,offlineCaptureFiles))fail();
 for(const name of offlineCaptureFiles){const item=data.files[name],limit=name==='source.capture.csv'?16*1024*1024:name==='attachment.json'?8192:32*1024*1024;if(!exact(item,['bytes','sha256'])||!Number.isInteger(item.bytes)||item.bytes<0||item.bytes>limit||typeof item.sha256!=='string'||!/^[0-9a-f]{64}$/.test(item.sha256))fail();}
 if(data.files['source.capture.csv'].bytes===0||data.files['attachment.json'].bytes===0||(data.accepted_rows===0)!==(data.files['observations.jsonl'].bytes===0)||(data.quarantined_rows===0)!==(data.files['quarantine.jsonl'].bytes===0))fail();
}
function syncOfflineCaptureControls(){
 $('offline-capture-export').disabled=!offlineCaptureReview;$('offline-capture-clear').disabled=!offlineCaptureReview&&!offlineCaptureReading&&!$('offline-capture-file').value;
 syncOfflineQuarantineControls();
}
function clearOfflineCapture(restore=false,resetFile=true){
 clearOfflineQuarantine();
 offlineCaptureSequence++;offlineCaptureReview=null;offlineCaptureReading=false;
 if(resetFile)$('offline-capture-file').value='';$('offline-capture-summary').replaceChildren();$('offline-capture-files').replaceChildren();$('offline-capture-context').replaceChildren();
 $('offline-capture-feedback').textContent='No manifest loaded. Choose manifest.json from a folder prepared by the existing offline capture adapter. Nothing is uploaded or stored.';syncOfflineCaptureControls();if(restore)$('offline-capture-file').focus();
}
async function readOfflineCaptureManifest(file){
 clearOfflineCapture(false,false);const sequence=offlineCaptureSequence;if(!file)return;offlineCaptureReading=true;syncOfflineCaptureControls();$('offline-capture-feedback').textContent='Reading manifest metadata locally…';
 try{
  if(file.size>65536)throw new Error('The manifest exceeds 64 KiB.');const bytes=await file.arrayBuffer();if(bytes.byteLength>65536)throw new Error('The manifest exceeds 64 KiB.');
  const data=parseOfflineCaptureJson(new TextDecoder('utf-8',{fatal:true}).decode(bytes));validateOfflineCaptureManifest(data);
  const digest=await crypto.subtle.digest('SHA-256',bytes),hash=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');if(sequence!==offlineCaptureSequence)return;
  offlineCaptureReview={schema_version:'1.0',scope:'local-browser-offline-capture-manifest-review',reviewed_at:new Date().toISOString(),file_name:file.name,file_bytes:bytes.byteLength,file_sha256:hash,manifest:data,manifest_structure_checked:true,package_files_checked:false,source_transformation_recomputed:false,source_authenticated:false,read_only:true,uploaded:false,persisted:false,physical_source_verified:false,calibration_verified:false,hardware_connected:false,ready_for_ingestion:false,equipment_authorized:false,production_ready:false,note:'Metadata structure only. Counts, timestamps, source classification and package file hashes are declarations in the selected manifest. Other files were not read or verified and no readings were admitted to the dashboard. Run the existing offline adapter verifier against the complete evidence folder; even successful consistency verification is not physical acceptance.'};
  const facts=[['Declared source type',data.source_type+' · operator-declared'],['Input rows · declared',data.input_rows],['Accepted rows · declared',data.accepted_rows],['Quarantined rows · declared',data.quarantined_rows],['Accepted sequence gaps · declared',data.accepted_sequence_gaps],['Adapter review flag',data.requires_review?'Review required':'Not requested · not acceptance'],['Adapter creation time · declared',data.created_at],['Boot identity',data.boot_identity]];
  for(const [label,value] of facts){const item=document.createElement('div'),term=document.createElement('dt'),description=document.createElement('dd');term.textContent=label;description.textContent=String(value);item.append(term,description);$('offline-capture-summary').append(item);}
  for(const name of offlineCaptureFiles){const row=document.createElement('tr');for(const value of [name,data.files[name].bytes,data.files[name].sha256]){const cell=document.createElement('td');cell.textContent=String(value);row.append(cell);}$('offline-capture-files').append(row);}
  $('offline-capture-context').textContent=file.name+' · '+bytes.byteLength+' bytes · Selected manifest SHA-256: '+hash;
  $('offline-capture-feedback').textContent='Manifest structure supported. '+(data.requires_review?'The adapter requests review. ':'The adapter did not request review; this does not establish readiness. ')+'Package contents and transformation have not been checked here. No observations were ingested.';
 }catch(error){if(sequence===offlineCaptureSequence)$('offline-capture-feedback').textContent='Manifest unavailable. '+(error instanceof TypeError?'Use a readable UTF-8 JSON file.':error instanceof SyntaxError?'The JSON is malformed.':error.message)+' No prior manifest or export is retained.';}
 finally{if(sequence===offlineCaptureSequence){offlineCaptureReading=false;syncOfflineCaptureControls();}}
}
function syncOfflineQuarantineControls(){
 if(!$('offline-quarantine-panel'))return;
 const available=!!offlineCaptureReview,current=!!offlineQuarantineReview&&offlineQuarantineManifest===offlineCaptureReview;
 $('offline-quarantine-file').disabled=!available;$('offline-quarantine-export').disabled=!current;
 $('offline-quarantine-clear').disabled=!offlineQuarantineReview&&!offlineQuarantineReading&&!$('offline-quarantine-file').value;
 const searchable=current&&offlineQuarantineReview.entries.length>0;
 $('offline-quarantine-search').disabled=!searchable;$('offline-quarantine-reason').disabled=!searchable;
 $('offline-quarantine-reset-filters').disabled=!current||(!$('offline-quarantine-search').value&& !$('offline-quarantine-reason').value);
 $('offline-quarantine-prev').disabled=!current||offlineQuarantinePage===0;$('offline-quarantine-next').disabled=!current||(offlineQuarantinePage+1)*50>=filteredOfflineQuarantine().length;
}
function clearOfflineQuarantine(restore=false,resetFile=true){
 offlineQuarantineSequence++;offlineQuarantineReview=null;offlineQuarantineManifest=null;offlineQuarantineReading=false;offlineQuarantinePage=0;
 if(!$('offline-quarantine-panel'))return;
 if(resetFile)$('offline-quarantine-file').value='';$('offline-quarantine-rows').replaceChildren();$('offline-quarantine-count').replaceChildren();$('offline-quarantine-context').replaceChildren();
 $('offline-quarantine-search').value='';$('offline-quarantine-reason').replaceChildren(new Option('All reasons',''));$('offline-quarantine-reason-summary').replaceChildren();
 $('offline-quarantine-feedback').textContent='Load a supported manifest, then choose its quarantine.jsonl file. Only this selected file can be checked here.';syncOfflineQuarantineControls();if(restore&&!$('offline-quarantine-file').disabled)$('offline-quarantine-file').focus();
}
function filteredOfflineQuarantine(){
 if(!offlineQuarantineReview||offlineQuarantineManifest!==offlineCaptureReview)return [];
 const reason=$('offline-quarantine-reason').value,query=$('offline-quarantine-search').value.trim().toLowerCase();
 return offlineQuarantineReview.entries.filter(entry=>(!reason||entry.reason===reason)&&(!query||('CSV line '+entry.csv_line+' record end '+entry.reason+' '+offlineQuarantineReasons[entry.reason]).toLowerCase().includes(query)));
}
function resetOfflineQuarantineFilters(){
 $('offline-quarantine-search').value='';$('offline-quarantine-reason').value='';offlineQuarantinePage=0;renderOfflineQuarantine();if(!$('offline-quarantine-search').disabled)$('offline-quarantine-search').focus();
}
function renderOfflineQuarantine(){
 const review=offlineQuarantineReview;if(!review||offlineQuarantineManifest!==offlineCaptureReview)return;
 const matching=filteredOfflineQuarantine(),count=matching.length,total=review.entries.length;offlineQuarantinePage=Math.min(Math.max(0,offlineQuarantinePage),Math.max(0,Math.ceil(count/50)-1));const start=offlineQuarantinePage*50,entries=matching.slice(start,start+50);
 $('offline-quarantine-count').textContent=!total?'No quarantined entries in this matching file. This does not establish sensor health or ingestion readiness.':count?'Entries '+(start+1)+'–'+(start+entries.length)+' of '+count+' matching · '+total+' total. Up to 50 per page. The export retains every entry.':'No entries match these filters · 0 of '+total+' total. Clear filters to see all entries. The export still retains every entry.';
 $('offline-quarantine-rows').replaceChildren(...entries.map(entry=>{const item=document.createElement('li'),heading=document.createElement('h3'),code=document.createElement('p'),description=document.createElement('p');heading.textContent='CSV line '+entry.csv_line+' · record end';code.className='bom-reference';code.textContent=entry.reason;description.textContent=offlineQuarantineReasons[entry.reason];item.append(heading,code,description);return item;}));syncOfflineQuarantineControls();
}
async function readOfflineQuarantine(file){
 clearOfflineQuarantine(false,false);const sequence=offlineQuarantineSequence,manifest=offlineCaptureReview;if(!file)return;
 if(!manifest){$('offline-quarantine-feedback').textContent='Load a supported manifest before selecting its quarantine file.';return;}
 offlineQuarantineReading=true;syncOfflineQuarantineControls();$('offline-quarantine-feedback').textContent='Checking selected quarantine file bytes and hash locally…';
 try{
  const reference=manifest.manifest.files['quarantine.jsonl'];if(file.size>offlineQuarantineLimit)throw new Error('The quarantine viewer limit is 2 MiB. Use the offline verifier for larger files.');if(file.size!==reference.bytes)throw new Error('File size does not match the selected manifest reference.');
  const bytes=await file.arrayBuffer();if(bytes.byteLength>offlineQuarantineLimit||bytes.byteLength!==reference.bytes)throw new Error('File length differs from the supported manifest reference.');const digest=await crypto.subtle.digest('SHA-256',bytes),hash=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');if(hash!==reference.sha256)throw new Error('File SHA-256 does not match the selected manifest reference.');
  const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes),lines=text===''?[]:text.split(/\r?\n/);if(lines.at(-1)==='')lines.pop();if(lines.length!==manifest.manifest.quarantined_rows||lines.length>10000)throw new Error('Entry count differs from the manifest.');
  let previous=1;const entries=lines.map(line=>{if(!line||line.length>256)throw new Error('Each quarantine entry must be a bounded JSON line.');const entry=parseOfflineCaptureJson(line,'quarantine entry');if(!entry||typeof entry!=='object'||Array.isArray(entry)||Object.keys(entry).length!==2||!Object.prototype.hasOwnProperty.call(entry,'csv_line')||!Object.prototype.hasOwnProperty.call(entry,'reason')||!Number.isInteger(entry.csv_line)||entry.csv_line<=previous||entry.csv_line>16*1024*1024+1||typeof entry.reason!=='string'||!Object.prototype.hasOwnProperty.call(offlineQuarantineReasons,entry.reason))throw new Error('Unsupported quarantine line reference or reason code.');previous=entry.csv_line;return {csv_line:entry.csv_line,reason:entry.reason};});
  if(sequence!==offlineQuarantineSequence||offlineCaptureReview!==manifest)return;
  offlineQuarantineManifest=manifest;offlineQuarantineReview={schema_version:'1.0',scope:'local-browser-capture-quarantine-review',reviewed_at:new Date().toISOString(),manifest_file_name:manifest.file_name,manifest_file_sha256:manifest.file_sha256,declared_source_type:manifest.manifest.source_type,declared_quarantined_rows:manifest.manifest.quarantined_rows,file_name:file.name,file_bytes:bytes.byteLength,file_sha256:hash,entries,selected_file_reference_matched:true,package_integrity_verified:false,source_transformation_recomputed:false,source_authenticated:false,read_only:true,uploaded:false,persisted:false,physical_source_verified:false,calibration_verified:false,hardware_connected:false,ready_for_ingestion:false,equipment_authorized:false,production_ready:false,note:'Only the selected quarantine file bytes/hash and entry count/shape were checked against the loaded manifest. The manifest is not authenticated. CSV line numbers are record-ending physical lines, not telemetry sequences. Reasons are adapter classifications, not independently recomputed findings or confirmed physical faults. Source CSV, attachment and accepted observations were not checked; use the existing offline verifier on the complete folder.'};
  $('offline-quarantine-context').textContent=file.name+' · '+bytes.byteLength+' bytes · SHA-256 '+hash+' · Selected manifest SHA-256 '+manifest.file_sha256;
  const counts=new Map();for(const entry of entries)counts.set(entry.reason,(counts.get(entry.reason)||0)+1);
  for(const reason of Object.keys(offlineQuarantineReasons))if(counts.has(reason))$('offline-quarantine-reason').append(new Option(reason+' · '+counts.get(reason),reason));
  $('offline-quarantine-reason-summary').textContent=entries.length+' entries across '+counts.size+' reason '+(counts.size===1?'category':'categories')+' in the complete selected file. Reason counts do not change with filters and are not confirmed physical faults.';
  $('offline-quarantine-feedback').textContent='Selected quarantine file matches the manifest’s byte/hash reference and declared entry count. Other package files and source transformation are not checked. No readings were ingested.';renderOfflineQuarantine();
 }catch(error){if(sequence===offlineQuarantineSequence&&offlineCaptureReview===manifest)$('offline-quarantine-feedback').textContent='Quarantine review unavailable. '+(error instanceof TypeError?'Use a readable UTF-8 JSONL file.':error instanceof SyntaxError?'A JSON line is malformed.':error.message)+' No prior quarantine review or export is retained.';}
 finally{if(sequence===offlineQuarantineSequence){offlineQuarantineReading=false;syncOfflineQuarantineControls();}}
}
function bindOfflineQuarantine(panel){
 const section=document.createElement('details');section.id='offline-quarantine-panel';section.innerHTML='<summary>Inspect quarantined-row reasons locally</summary><p>Choose quarantine.jsonl from the same evidence folder after loading its manifest. This checks only the selected file’s size/hash and entry count/shape, not the complete package or the source transformation. Reason codes describe software quarantine decisions, not confirmed physical faults. CSV line references are record-ending physical lines, not observation IDs or telemetry sequence numbers.</p><div class="physical-preparation-tools"><label for="offline-quarantine-file">Quarantine JSONL · UTF-8 · up to 2 MiB<input id="offline-quarantine-file" type="file" accept=".jsonl,.ndjson,application/x-ndjson,text/plain" disabled></label><button id="offline-quarantine-clear" class="action-outline" type="button" disabled>Clear quarantine review</button><button id="offline-quarantine-export" class="action-outline" type="button" disabled>Export complete quarantine review</button></div><p id="offline-quarantine-feedback" role="status" aria-live="polite"></p><details><summary>Selected file references</summary><p id="offline-quarantine-context"></p></details><p id="offline-quarantine-count" role="status" aria-live="polite"></p><ol id="offline-quarantine-rows"></ol><div class="replay-controls"><button id="offline-quarantine-prev" class="action-outline" type="button" disabled>Previous entries</button><button id="offline-quarantine-next" class="action-outline" type="button" disabled>Next entries</button></div>';
 const filters=document.createElement('div');filters.className='offline-quarantine-filters';filters.innerHTML='<p id="offline-quarantine-reason-summary"></p><label for="offline-quarantine-reason">Reason · count in complete file<select id="offline-quarantine-reason" disabled><option value="">All reasons</option></select></label><label for="offline-quarantine-search">Search CSV line, reason or explanation<input id="offline-quarantine-search" type="search" maxlength="160" autocomplete="off" spellcheck="false" aria-describedby="offline-quarantine-filter-help offline-quarantine-count" disabled></label><button id="offline-quarantine-reset-filters" class="action-outline" type="button" disabled>Clear filters</button><p id="offline-quarantine-filter-help">Literal, case-insensitive search within this local review. Filters combine, preserve source order and affect only the displayed cards. Export complete quarantine review always includes every entry.</p>';
 section.querySelector('#offline-quarantine-count').before(filters);
 panel.append(section);$('offline-quarantine-file').addEventListener('change',event=>readOfflineQuarantine(event.target.files[0]));$('offline-quarantine-clear').addEventListener('click',()=>clearOfflineQuarantine(true));$('offline-quarantine-prev').addEventListener('click',()=>{offlineQuarantinePage--;renderOfflineQuarantine();});$('offline-quarantine-next').addEventListener('click',()=>{offlineQuarantinePage++;renderOfflineQuarantine();});$('offline-quarantine-export').addEventListener('click',()=>{if(!offlineQuarantineReview||offlineQuarantineManifest!==offlineCaptureReview)return;const url=URL.createObjectURL(new Blob([JSON.stringify(offlineQuarantineReview,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-offline-quarantine-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 $('offline-quarantine-search').addEventListener('input',()=>{offlineQuarantinePage=0;renderOfflineQuarantine();});$('offline-quarantine-reason').addEventListener('change',()=>{offlineQuarantinePage=0;renderOfflineQuarantine();});$('offline-quarantine-reset-filters').addEventListener('click',resetOfflineQuarantineFilters);clearOfflineQuarantine();
}
document.addEventListener('DOMContentLoaded',()=>{
 const panel=document.createElement('article');panel.id='offline-capture-panel';panel.className='panel operations-panel';panel.innerHTML='<span class="section-kicker">OFFLINE CAPTURE / MANIFEST METADATA ONLY</span><h2>Review an offline capture manifest</h2><p>Choose manifest.json produced by the existing USB capture adapter. Review its declared counts and source classification before any later integration. This view does not display live or stored sensor readings.</p><p class="planning-boundary">The file stays in this browser page. Source type, counters, timestamps and hashes are declarations, not physical authentication. Package files and source transformation are not verified here. Measured and replayed observations remain offline; do not relabel them as synthetic.</p><div class="physical-preparation-tools"><label for="offline-capture-file">Manifest JSON · UTF-8 · up to 64 KiB<input id="offline-capture-file" type="file" accept=".json,application/json" aria-describedby="offline-capture-feedback"></label><button id="offline-capture-clear" class="action-outline" type="button" disabled>Clear manifest</button><button id="offline-capture-export" class="action-outline" type="button" disabled>Export metadata review</button></div><p id="offline-capture-feedback" role="status" aria-live="polite"></p><dl id="offline-capture-summary" class="persisted-inspector-facts"></dl><details><summary>Declared package file references · not checked</summary><div class="product-table-wrap"><table><thead><tr><th>Expected file</th><th>Declared bytes</th><th>Declared SHA-256</th></tr></thead><tbody id="offline-capture-files"></tbody></table></div></details><details><summary>Selected manifest file reference</summary><p id="offline-capture-context"></p></details><p>Use the existing offline adapter’s verify command on the complete evidence folder. A successful file-consistency check still does not verify electrical safety, calibration or production acceptance. This review cannot create bindings, charts, incidents or equipment commands; physical and ingestion readiness remain false.</p>';
 const references=panel.querySelector('.product-table-wrap');references.tabIndex=0;references.setAttribute('role','region');references.setAttribute('aria-label','Declared package file references, not checked');
 $('persisted-panel').after(panel);bindOfflineQuarantine(panel);$('offline-capture-file').addEventListener('change',event=>readOfflineCaptureManifest(event.target.files[0]));$('offline-capture-clear').addEventListener('click',()=>clearOfflineCapture(true));$('offline-capture-export').addEventListener('click',()=>{if(!offlineCaptureReview)return;const url=URL.createObjectURL(new Blob([JSON.stringify(offlineCaptureReview,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-offline-capture-metadata-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});clearOfflineCapture();
});
