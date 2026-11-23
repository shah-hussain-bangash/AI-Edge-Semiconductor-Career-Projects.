"use strict";
let offlineCaptureSequence=0,offlineCaptureReview=null,offlineCaptureReading=false;
let offlinePackageSequence=0,offlinePackageReview=null,offlinePackageManifest=null,offlinePackageReading=false;
let offlineVerifierSequence=0,offlineVerifierReview=null,offlineVerifierManifest=null,offlineVerifierReading=false;
let offlineAttachmentSequence=0,offlineAttachmentReview=null,offlineAttachmentManifest=null,offlineAttachmentReading=false;
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
const offlineReviewSteps=[
 ['manifest','Manifest metadata','offline-capture-file',null,'Declared counts, source classification and file references.'],
 ['attachment','Attachment identity','offline-attachment-file','offline-attachment-panel','Declared mapping and one selected attachment reference.'],
 ['files','Four file references','offline-package-files','offline-package-panel','Selected byte counts and hashes; contents are not validated.'],
 ['quarantine','Quarantine reasons','offline-quarantine-file','offline-quarantine-panel','Selected reason records; no independent fault diagnosis.'],
 ['report','Offline verifier report','offline-verifier-file','offline-verifier-panel','Unsigned report declarations; verifier is not run here.']
];

function currentOfflineReviewSections(){
 return {manifest:offlineCaptureReview,
  attachment:offlineAttachmentManifest===offlineCaptureReview?offlineAttachmentReview:null,
  files:offlinePackageManifest===offlineCaptureReview?offlinePackageReview:null,
  quarantine:offlineQuarantineManifest===offlineCaptureReview?offlineQuarantineReview:null,
  report:offlineVerifierManifest===offlineCaptureReview?offlineVerifierReview:null};
}
function syncOfflineReviewProgress(){
 if(!$('offline-review-progress'))return;
 const sections=currentOfflineReviewSections(),count=Object.values(sections).filter(Boolean).length;
 const reading={manifest:offlineCaptureReading,attachment:offlineAttachmentReading,files:offlinePackageReading,quarantine:offlineQuarantineReading,report:offlineVerifierReading};
 for(const [key] of offlineReviewSteps){$('offline-review-status-'+key).textContent=reading[key]?'Reading locally…':sections[key]?(key==='report'?'Unsigned report loaded':key==='files'?'Four references matched':'Review loaded'):'Not loaded';$('offline-review-jump-'+key).disabled=key!=='manifest'&&!offlineCaptureReview;}
 $('offline-review-coverage').textContent=count+' of 5 local reviews loaded. These optional views cover different checks; this is not package, ingestion or production acceptance.';
 $('offline-review-source').textContent=offlineCaptureReview?'Declared source: '+offlineCaptureReview.manifest.source_type+' · operator-declared, not physical authentication.':'Choose a manifest to start. No local review is retained after reload.';
 $('offline-review-export').disabled=!offlineCaptureReview;
}
function exportOfflineReviewSnapshot(){
 if(!offlineCaptureReview)return;
 const sections=currentOfflineReviewSections(),reading={manifest:offlineCaptureReading,attachment:offlineAttachmentReading,files:offlinePackageReading,quarantine:offlineQuarantineReading,report:offlineVerifierReading};
 const snapshot={schema_version:'1.0',scope:'local-browser-offline-capture-review-snapshot',exported_at:new Date().toISOString(),manifest_file_sha256:offlineCaptureReview.file_sha256,loaded_review_count:Object.values(sections).filter(Boolean).length,available_review_count:5,section_state:Object.fromEntries(offlineReviewSteps.map(([key])=>[key,reading[key]?'reading':sections[key]?'loaded':'not_loaded'])),sections,read_only:true,verification_executed_in_browser:false,report_authenticated:false,package_integrity_verified:false,source_transformation_recomputed:false,source_authenticated:false,device_enrolled:false,port_opened:false,uploaded:false,persisted:false,physical_source_verified:false,calibration_verified:false,hardware_connected:false,ready_for_ingestion:false,equipment_authorized:false,production_ready:false,note:'A document-memory snapshot of the currently loaded local reviews for one selected manifest. Missing or in-progress sections are null, not passed checks. Quarantine entries are complete regardless of display filtering or paging. Nested verifier results remain unsigned declarations. This export does not run verification, recheck current files, establish physical identity, admit observations or grant production acceptance.'};
 const url=URL.createObjectURL(new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-offline-capture-review-snapshot.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function bindOfflineReviewProgress(panel){
 const section=document.createElement('section');section.id='offline-review-progress';section.innerHTML='<h3>Current capture review</h3><p id="offline-review-coverage" role="status" aria-live="polite"></p><p id="offline-review-source"></p><button id="offline-review-export" class="action-outline" type="button" disabled>Export current local review</button><ol id="offline-review-steps"></ol><p>Open any review to inspect its details. Each view has its own limits and error messages. Loading all five does not verify hardware or authorize equipment.</p>';
 for(const [key,title,input,details,description] of offlineReviewSteps){const item=document.createElement('li'),heading=document.createElement('h4'),status=document.createElement('strong'),help=document.createElement('p'),button=document.createElement('button');heading.textContent=title;status.id='offline-review-status-'+key;help.textContent=description;button.id='offline-review-jump-'+key;button.className='action-outline';button.type='button';button.textContent='Open '+title.toLowerCase();button.addEventListener('click',()=>{if(button.disabled)return;if(details)$(details).open=true;$(input).focus({preventScroll:true});$(input).scrollIntoView({block:'center'});});item.append(heading,status,help,button);section.querySelector('ol').append(item);}
 panel.querySelector('.physical-preparation-tools').before(section);$('offline-review-export').addEventListener('click',exportOfflineReviewSnapshot);syncOfflineReviewProgress();
}

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
 syncOfflinePackageControls();
 syncOfflineVerifierControls();
 syncOfflineAttachmentControls();
 syncOfflineReviewProgress();
}
function clearOfflineCapture(restore=false,resetFile=true){
 clearOfflineQuarantine();
 clearOfflinePackage();
 clearOfflineVerifier();
 clearOfflineAttachment();
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
function syncOfflineAttachmentControls(){
 if(!$('offline-attachment-panel'))return;
 $('offline-attachment-file').disabled=!offlineCaptureReview;$('offline-attachment-export').disabled=!offlineAttachmentReview||offlineAttachmentManifest!==offlineCaptureReview;
 $('offline-attachment-clear').disabled=!offlineAttachmentReview&&!offlineAttachmentReading&&!$('offline-attachment-file').value;
 syncOfflineReviewProgress();
}
function clearOfflineAttachment(restore=false,resetFile=true){
 offlineAttachmentSequence++;offlineAttachmentReview=null;offlineAttachmentManifest=null;offlineAttachmentReading=false;
 if(!$('offline-attachment-panel'))return;
 if(resetFile)$('offline-attachment-file').value='';$('offline-attachment-facts').replaceChildren();$('offline-attachment-provenance').replaceChildren();$('offline-attachment-context').replaceChildren();
 $('offline-attachment-feedback').textContent='Load a supported manifest, then choose its attachment.json. Mapping values are declarations, not enrolled or authenticated hardware.';syncOfflineAttachmentControls();if(restore&&!$('offline-attachment-file').disabled)$('offline-attachment-file').focus();
}
function validateOfflineAttachment(data,manifest){
 const keys=['profile','site_id','asset_id','device_id','v1_device_id','serial_port','board_reference','configuration_ref','source_type','physical_verification','calibration','transport'];
 const fail=()=>{throw new Error('Unsupported attachment mapping, provenance or source declaration.');};
 if(!data||typeof data!=='object'||Array.isArray(data)||Object.keys(data).length!==keys.length||keys.some(key=>!Object.prototype.hasOwnProperty.call(data,key)))fail();
 // Match Python str.strip whitespace and code-point lengths used by the offline adapter.
 for(const key of keys)if(typeof data[key]!=='string'||Array.from(data[key]).length>200||!data[key].replace(/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/gu,''))fail();
 for(const key of ['site_id','asset_id','device_id','v1_device_id'])if(!/^[A-Za-z0-9_-]{1,64}$/.test(data[key]))fail();
 if(data.profile!=='edgeops.serial-attachment.v1'||data.transport!=='usb-serial'||data.source_type!==manifest.manifest.source_type||data.physical_verification!=='unverified'||data.calibration!=='not_verified')fail();
}
async function readOfflineAttachment(file){
 clearOfflineAttachment(false,false);const sequence=offlineAttachmentSequence,manifest=offlineCaptureReview;if(!file)return;
 if(!manifest){$('offline-attachment-feedback').textContent='Load a supported manifest before choosing its attachment.';return;}
 offlineAttachmentReading=true;syncOfflineAttachmentControls();$('offline-attachment-feedback').textContent='Checking attachment bytes, hash and declared mapping locally…';
 try{
  const reference=manifest.manifest.files['attachment.json'];if(file.size>8192)throw new Error('The attachment exceeds 8 KiB.');if(file.size!==reference.bytes)throw new Error('Attachment size differs from the selected manifest.');
  const bytes=await file.arrayBuffer();if(bytes.byteLength>8192||bytes.byteLength!==reference.bytes)throw new Error('Attachment read length differs from the supported manifest reference.');
  const digest=await crypto.subtle.digest('SHA-256',bytes),hash=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');if(hash!==reference.sha256)throw new Error('Attachment SHA-256 differs from the selected manifest.');
  const data=parseOfflineCaptureJson(new TextDecoder('utf-8',{fatal:true}).decode(bytes),'attachment');validateOfflineAttachment(data,manifest);if(sequence!==offlineAttachmentSequence||manifest!==offlineCaptureReview)return;
  offlineAttachmentManifest=manifest;offlineAttachmentReview={schema_version:'1.0',scope:'local-browser-offline-capture-attachment-review',reviewed_at:new Date().toISOString(),file_name:file.name,file_bytes:bytes.byteLength,file_sha256:hash,manifest_file_name:manifest.file_name,manifest_file_sha256:manifest.file_sha256,attachment:data,selected_file_reference_matched:true,attachment_structure_checked:true,source_declaration_matched:true,package_integrity_verified:false,source_transformation_recomputed:false,source_authenticated:false,device_enrolled:false,port_opened:false,read_only:true,uploaded:false,persisted:false,physical_source_verified:false,calibration_verified:false,hardware_connected:false,ready_for_ingestion:false,equipment_authorized:false,production_ready:false,note:'Only selected attachment bytes/hash, supported mapping shape and declared source agreement were checked against the loaded unauthenticated manifest. Site, asset, device, port, board and configuration references are declarations, not registry bindings, verified ordered models, current port availability or physical identity. No port was opened, device enrolled, input rewritten or readings ingested. Other package contents and transformation were not verified.'};
  const groups=[['offline-attachment-facts',[['Site ID · declared',data.site_id],['Asset ID · declared',data.asset_id],['Candidate device ID · declared',data.device_id],['V1 capture device ID · declared',data.v1_device_id],['Serial port · not opened by this review',data.serial_port],['Board reference · unverified',data.board_reference],['Configuration reference · unverified',data.configuration_ref]]],['offline-attachment-provenance',[['Source type · operator-declared',data.source_type],['Transport · declared',data.transport],['Mapping profile',data.profile],['Physical verification · declared',data.physical_verification],['Calibration · declared',data.calibration]]]];
  for(const [id,facts] of groups)for(const [label,value] of facts){const item=document.createElement('div'),term=document.createElement('dt'),description=document.createElement('dd');term.textContent=label;description.textContent=value;item.append(term,description);$(id).append(item);}
  $('offline-attachment-context').textContent=file.name+' · '+bytes.byteLength+' bytes · Attachment SHA-256 '+hash+' · Selected manifest SHA-256 '+manifest.file_sha256;
  $('offline-attachment-feedback').textContent='Attachment reference matched; mapping structure and source declaration supported. These details do not enroll hardware, verify ordered parts or establish a current connection. No port was opened or readings ingested.';
 }catch(error){if(sequence===offlineAttachmentSequence&&manifest===offlineCaptureReview)$('offline-attachment-feedback').textContent='Attachment review unavailable. '+(error instanceof TypeError?'Use a readable UTF-8 JSON attachment.':error instanceof SyntaxError?'The attachment JSON is malformed.':error.message)+' No previous mapping or export is retained.';}
 finally{if(sequence===offlineAttachmentSequence){offlineAttachmentReading=false;syncOfflineAttachmentControls();}}
}
function bindOfflineAttachment(panel){
 const section=document.createElement('details');section.id='offline-attachment-panel';section.innerHTML='<summary>Inspect offline capture identity and attachment locally</summary><p>Choose attachment.json after loading its manifest. This checks the selected file’s exact bytes/hash, supported mapping structure and declared source agreement. Site, asset, device IDs, serial port, board and configuration references remain unverified declarations. They do not create registry bindings or establish the exact ordered hardware model.</p><p>The serial port is not opened or checked. Measured/replayed declarations stay unchanged, and physical verification and calibration remain unverified. Use the existing offline verifier on the complete folder; review the same original 30 products before connection.</p><div class="physical-preparation-tools"><label for="offline-attachment-file">Attachment JSON · UTF-8 · up to 8 KiB<input id="offline-attachment-file" type="file" accept=".json,application/json" disabled></label><button id="offline-attachment-clear" class="action-outline" type="button" disabled>Clear attachment review</button><button id="offline-attachment-export" class="action-outline" type="button" disabled>Export attachment review</button></div><p id="offline-attachment-feedback" role="status" aria-live="polite"></p><dl id="offline-attachment-facts" class="persisted-inspector-facts"></dl><details><summary>Declared source, transport and verification labels</summary><dl id="offline-attachment-provenance" class="persisted-inspector-facts"></dl></details><details><summary>Selected attachment and manifest references</summary><p id="offline-attachment-context"></p></details>';
 panel.append(section);$('offline-attachment-file').addEventListener('change',event=>readOfflineAttachment(event.target.files[0]));$('offline-attachment-clear').addEventListener('click',()=>clearOfflineAttachment(true));$('offline-attachment-export').addEventListener('click',()=>{if(!offlineAttachmentReview||offlineAttachmentManifest!==offlineCaptureReview)return;const url=URL.createObjectURL(new Blob([JSON.stringify(offlineAttachmentReview,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-offline-attachment-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});clearOfflineAttachment();
}
function syncOfflineVerifierControls(){
 if(!$('offline-verifier-panel'))return;
 $('offline-verifier-file').disabled=!offlineCaptureReview;$('offline-verifier-export').disabled=!offlineVerifierReview||offlineVerifierManifest!==offlineCaptureReview;
 $('offline-verifier-clear').disabled=!offlineVerifierReview&&!offlineVerifierReading&&!$('offline-verifier-file').value;
 syncOfflineReviewProgress();
}
function clearOfflineVerifier(restore=false,resetFile=true){
 offlineVerifierSequence++;offlineVerifierReview=null;offlineVerifierManifest=null;offlineVerifierReading=false;
 if(!$('offline-verifier-panel'))return;
 if(resetFile)$('offline-verifier-file').value='';$('offline-verifier-facts').replaceChildren();$('offline-verifier-context').replaceChildren();$('offline-verifier-feedback').textContent='Load a supported manifest, then select its optional offline verification report. Reports are unsigned declarations.';syncOfflineVerifierControls();if(restore&&!$('offline-verifier-file').disabled)$('offline-verifier-file').focus();
}
function validateOfflineVerifierReport(data,manifest){
 const keys=['format','verified_at','manifest_bytes','manifest_sha256','manifest','package_consistency_checked','source_transformation_recomputed','report_authenticated','source_authenticated','atomic_folder_snapshot','ongoing_freshness_verified','physical_source_verified','calibration_verified','hardware_connected','ready_for_ingestion','equipment_authorized','production_ready'];
 const fail=()=>{throw new Error('Unsupported report structure, claims or manifest reference.');};
 if(!data||typeof data!=='object'||Array.isArray(data)||Object.keys(data).length!==keys.length||keys.some(key=>!Object.prototype.hasOwnProperty.call(data,key))||data.format!=='edgeops-offline-capture-verification-report-v1'||data.package_consistency_checked!==true||data.source_transformation_recomputed!==true)fail();
 for(const key of keys.slice(7))if(data[key]!==false)fail();
 validateOfflineCaptureManifest(data.manifest);
 const parent=manifest.manifest;
 if(data.manifest_bytes!==manifest.file_bytes||!Number.isInteger(data.manifest_bytes)||data.manifest_sha256!==manifest.file_sha256)fail();
 for(const key of Object.keys(parent))if(key!=='files'&&data.manifest[key]!==parent[key])fail();
 for(const name of offlineCaptureFiles)if(data.manifest.files[name].bytes!==parent.files[name].bytes||data.manifest.files[name].sha256!==parent.files[name].sha256)fail();
 const time=data.verified_at;
 if(typeof time!=='string'||!/^\d{4}-\d\d-\d\dT(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(time)||time.startsWith('0000')||!Number.isFinite(Date.parse(time))||new Date(time.slice(0,10)+'T00:00:00Z').toISOString().slice(0,10)!==time.slice(0,10))fail();
}
async function readOfflineVerifier(file){
 clearOfflineVerifier(false,false);const sequence=offlineVerifierSequence,manifest=offlineCaptureReview;if(!file)return;
 if(!manifest){$('offline-verifier-feedback').textContent='Load a supported manifest before selecting its verification report.';return;}
 offlineVerifierReading=true;syncOfflineVerifierControls();$('offline-verifier-feedback').textContent='Reading the report locally and matching its manifest reference…';
 try{
  if(file.size>16384)throw new Error('The report exceeds 16 KiB.');const bytes=await file.arrayBuffer();if(bytes.byteLength>16384)throw new Error('The report exceeds 16 KiB.');
  const data=parseOfflineCaptureJson(new TextDecoder('utf-8',{fatal:true}).decode(bytes),'verification report');validateOfflineVerifierReport(data,manifest);
  const digest=await crypto.subtle.digest('SHA-256',bytes),hash=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');if(sequence!==offlineVerifierSequence||manifest!==offlineCaptureReview)return;
  offlineVerifierManifest=manifest;offlineVerifierReview={schema_version:'1.0',scope:'local-browser-offline-verifier-report-review',reviewed_at:new Date().toISOString(),file_name:file.name,file_bytes:bytes.byteLength,file_sha256:hash,manifest_file_name:manifest.file_name,manifest_file_sha256:manifest.file_sha256,report:data,report_structure_checked:true,manifest_reference_matched:true,verification_executed_in_browser:false,report_authenticated:false,package_integrity_verified:false,source_transformation_recomputed:false,source_authenticated:false,read_only:true,uploaded:false,persisted:false,physical_source_verified:false,calibration_verified:false,hardware_connected:false,ready_for_ingestion:false,equipment_authorized:false,production_ready:false,note:'The selected unsigned report declares offline package checking and recomputed transformation for the loaded manifest. This browser checked only report structure and manifest reference, did not execute the verifier and cannot authenticate the report or its timestamp. This review grants no ingestion, hardware or production authority.'};
  for(const [label,value] of [['Offline result · report declaration','Package consistency and transformation checked'],['Verification time · declared by report',data.verified_at],['Source type · operator-declared',data.manifest.source_type],['Accepted / quarantined rows · declared',data.manifest.accepted_rows+' / '+data.manifest.quarantined_rows],['Adapter review flag · declared',data.manifest.requires_review?'Review required':'Not requested · not acceptance'],['Report authenticity','Unsigned · not authenticated'],['Verification executed in this browser','No']]){const item=document.createElement('div'),term=document.createElement('dt'),description=document.createElement('dd');term.textContent=label;description.textContent=value;item.append(term,description);$('offline-verifier-facts').append(item);}
  $('offline-verifier-context').textContent=file.name+' · '+bytes.byteLength+' bytes · Report SHA-256 '+hash+' · Selected manifest SHA-256 '+manifest.file_sha256;
  $('offline-verifier-feedback').textContent='Report structure supported and manifest reference matched. Its verification result and time remain unsigned declarations. The browser did not run the verifier, authenticate the report or ingest readings.';
 }catch(error){if(sequence===offlineVerifierSequence&&manifest===offlineCaptureReview)$('offline-verifier-feedback').textContent='Report review unavailable. '+(error instanceof TypeError?'Use a readable UTF-8 JSON report.':error instanceof SyntaxError?'The report JSON is malformed.':error.message)+' No previous report or export is retained.';}
 finally{if(sequence===offlineVerifierSequence){offlineVerifierReading=false;syncOfflineVerifierControls();}}
}
function bindOfflineVerifier(panel){
 const section=document.createElement('details');section.id='offline-verifier-panel';section.innerHTML='<summary>Review an offline verifier report locally</summary><p>Run the existing offline adapter verify command with --report and a new report filename outside the evidence folder, then choose that JSON here after loading its original manifest. This reader matches the report’s manifest fingerprint and declarations. It does not run the verifier or authenticate an unsigned report.</p><p>A report can be edited or forged. Its verification time is declared by the offline host, not a trusted timestamp. Successful report review does not establish current file contents, hardware connection, calibration, ingestion readiness or production acceptance.</p><div class="physical-preparation-tools"><label for="offline-verifier-file">Offline verifier report · UTF-8 JSON · up to 16 KiB<input id="offline-verifier-file" type="file" accept=".json,application/json" disabled></label><button id="offline-verifier-clear" class="action-outline" type="button" disabled>Clear report review</button><button id="offline-verifier-export" class="action-outline" type="button" disabled>Export report review</button></div><p id="offline-verifier-feedback" role="status" aria-live="polite"></p><dl id="offline-verifier-facts" class="persisted-inspector-facts"></dl><details><summary>Selected report and manifest references</summary><p id="offline-verifier-context"></p></details>';
 panel.append(section);$('offline-verifier-file').addEventListener('change',event=>readOfflineVerifier(event.target.files[0]));$('offline-verifier-clear').addEventListener('click',()=>clearOfflineVerifier(true));$('offline-verifier-export').addEventListener('click',()=>{if(!offlineVerifierReview||offlineVerifierManifest!==offlineCaptureReview)return;const url=URL.createObjectURL(new Blob([JSON.stringify(offlineVerifierReview,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-offline-verifier-report-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});clearOfflineVerifier();
}
function syncOfflinePackageControls(){
 if(!$('offline-package-panel'))return;
 $('offline-package-files').disabled=!offlineCaptureReview;
 $('offline-package-clear').disabled=!offlinePackageReview&&!offlinePackageReading&&!$('offline-package-files').value;
 $('offline-package-export').disabled=!offlinePackageReview||offlinePackageManifest!==offlineCaptureReview;
 syncOfflineReviewProgress();
}
function clearOfflinePackage(restore=false,resetFile=true){
 offlinePackageSequence++;offlinePackageReview=null;offlinePackageManifest=null;offlinePackageReading=false;
 if(!$('offline-package-panel'))return;
 if(resetFile)$('offline-package-files').value='';$('offline-package-results').replaceChildren();$('offline-package-context').replaceChildren();
 $('offline-package-feedback').textContent='Load a supported manifest, then select exactly its four evidence files. Nothing is uploaded or stored.';syncOfflinePackageControls();if(restore&&!$('offline-package-files').disabled)$('offline-package-files').focus();
}
async function readOfflinePackage(selected){
 clearOfflinePackage(false,false);const sequence=offlinePackageSequence,manifest=offlineCaptureReview,files=Array.from(selected||[]);if(!files.length)return;
 if(!manifest){$('offline-package-feedback').textContent='Load a supported manifest before choosing evidence files.';return;}
 const current=()=>sequence===offlinePackageSequence&&manifest===offlineCaptureReview;
 offlinePackageReading=true;syncOfflinePackageControls();$('offline-package-feedback').textContent='Checking the selected file inventory locally…';
 try{
  if(files.length!==4||new Set(files.map(file=>file.name)).size!==4||files.some(file=>!offlineCaptureFiles.includes(file.name)))throw new Error('Select exactly source.capture.csv, attachment.json, observations.jsonl and quarantine.jsonl, once each. Do not include manifest.json or other files.');
  const ordered=offlineCaptureFiles.map(name=>files.find(file=>file.name===name));
  for(const file of ordered)if(file.size!==manifest.manifest.files[file.name].bytes)throw new Error(file.name+': file size differs from the manifest. No partial match is retained.');
  const checked=[];
  for(const file of ordered){
   if(!current())return;$('offline-package-feedback').textContent='Checking file '+(checked.length+1)+' of 4 · '+file.name+'…';
   const bytes=await file.arrayBuffer();if(!current())return;
   if(bytes.byteLength!==manifest.manifest.files[file.name].bytes)throw new Error(file.name+': read length differs from the manifest. No partial match is retained.');
   const digest=await crypto.subtle.digest('SHA-256',bytes);if(!current())return;
   const hash=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');
   if(hash!==manifest.manifest.files[file.name].sha256)throw new Error(file.name+': SHA-256 differs from the manifest. No partial match is retained.');
   checked.push({name:file.name,bytes:bytes.byteLength,sha256:hash,reference_matched:true});
  }
  if(!current())return;
  offlinePackageManifest=manifest;offlinePackageReview={schema_version:'1.0',scope:'local-browser-offline-capture-file-reference-check',checked_at:new Date().toISOString(),manifest_file_name:manifest.file_name,manifest_file_bytes:manifest.file_bytes,manifest_file_sha256:manifest.file_sha256,declared_source_type:manifest.manifest.source_type,files:checked,all_selected_file_references_matched:true,package_integrity_verified:false,source_transformation_recomputed:false,source_authenticated:false,read_only:true,uploaded:false,persisted:false,physical_source_verified:false,calibration_verified:false,hardware_connected:false,ready_for_ingestion:false,equipment_authorized:false,production_ready:false,note:'All four selected files match the loaded manifest byte counts and SHA-256 references. This does not authenticate the manifest or prove the files came from one folder. File contents, observation/count semantics and source transformation were not validated. This is not the offline adapter verify command. Run that verifier on the complete original evidence folder; matching file references do not establish physical or production acceptance.'};
  for(const file of checked){const card=document.createElement('li'),heading=document.createElement('h3'),size=document.createElement('p'),hash=document.createElement('p');heading.textContent=file.name;size.textContent=file.bytes+' bytes · Reference matched';hash.className='bom-reference';hash.textContent='SHA-256 '+file.sha256;card.append(heading,size,hash);$('offline-package-results').append(card);}
  $('offline-package-context').textContent='Selected manifest: '+manifest.file_name+' · SHA-256 '+manifest.file_sha256+' · Declared source: '+manifest.manifest.source_type+' · Browser check time: '+offlinePackageReview.checked_at;
  $('offline-package-feedback').textContent='4 of 4 selected file references matched. File contents and source transformation were not validated. No readings were ingested. Use the offline adapter verifier on the complete folder.';
 }catch(error){if(current())$('offline-package-feedback').textContent='File-reference check unavailable. '+(error instanceof TypeError?'A selected file could not be read.':error.message)+' No previous result or export is retained.';}
 finally{if(current()){offlinePackageReading=false;syncOfflinePackageControls();}}
}
function bindOfflinePackage(panel){
 const section=document.createElement('details');section.id='offline-package-panel';section.innerHTML='<summary>Check all four evidence file references locally</summary><p>Select source.capture.csv, attachment.json, observations.jsonl and quarantine.jsonl together from your evidence folder. Their names, exact byte counts and SHA-256 values are compared with the loaded manifest. Files are read one at a time, within the manifest limits: capture 16 MiB, attachment 8 KiB, observations and quarantine 32 MiB each.</p><p>This checks file references only. It does not validate contents, row counts or the source conversion, authenticate the manifest, prove folder membership or establish hardware readiness. Run the existing offline adapter verifier on the complete original folder. The files stay in this browser page.</p><div class="physical-preparation-tools"><label for="offline-package-files">Select all four evidence files · exclude manifest.json<input id="offline-package-files" type="file" multiple aria-describedby="offline-package-feedback" disabled></label><button id="offline-package-clear" class="action-outline" type="button" disabled>Clear file-reference check</button><button id="offline-package-export" class="action-outline" type="button" disabled>Export file-reference check</button></div><p id="offline-package-feedback" role="status" aria-live="polite"></p><ul id="offline-package-results"></ul><details><summary>Selected manifest and check time</summary><p id="offline-package-context"></p></details>';
 panel.append(section);$('offline-package-files').addEventListener('change',event=>readOfflinePackage(event.target.files));$('offline-package-clear').addEventListener('click',()=>clearOfflinePackage(true));$('offline-package-export').addEventListener('click',()=>{if(!offlinePackageReview||offlinePackageManifest!==offlineCaptureReview)return;const url=URL.createObjectURL(new Blob([JSON.stringify(offlinePackageReview,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-offline-capture-file-reference-check.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});clearOfflinePackage();
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
 syncOfflineReviewProgress();
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
 $('persisted-panel').after(panel);bindOfflineAttachment(panel);bindOfflineQuarantine(panel);bindOfflinePackage(panel);bindOfflineVerifier(panel);bindOfflineReviewProgress(panel);$('offline-capture-file').addEventListener('change',event=>readOfflineCaptureManifest(event.target.files[0]));$('offline-capture-clear').addEventListener('click',()=>clearOfflineCapture(true));$('offline-capture-export').addEventListener('click',()=>{if(!offlineCaptureReview)return;const url=URL.createObjectURL(new Blob([JSON.stringify(offlineCaptureReview,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-offline-capture-metadata-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});clearOfflineCapture();
});
