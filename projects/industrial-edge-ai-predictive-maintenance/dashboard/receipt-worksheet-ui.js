"use strict";
const receiptWorksheetHeaders=['Product ID','BOM ID','Selected family','Planned quantity','Bench role','Actual received model / board revision','Received date','Label / photo reference','Inspection notes / unresolved issue','Record status'];
const receiptWorksheetLimit=128*1024;
let receiptWorksheetSequence=0,receiptWorksheetData=null,receiptWorksheetPlan=null,receiptWorksheetReading=false;
let receiptDeclarationContext=null,receiptDeclarationReturn=null;
let receiptComparisonSequence=0,receiptComparisonData=null,receiptComparisonReview=null,receiptComparisonReading=false;
const receiptComparisonFields=[['declared_model','Declared model / revision'],['declared_received_date','Declared received date'],['declared_label_reference','Label / photo reference'],['declared_notes','Owner notes / issues'],['declared_status','Declared status · unverified']];

function parseReceiptWorksheet(text,plan){
 validatePhysicalBuildPlan(plan);
 if(text.charCodeAt(0)===0xfeff)text=text.slice(1);
 if(!text||text.includes('\0'))throw new Error('The worksheet is empty or contains unsupported text.');
 const records=[];let row=[],field='',quoted=false,closed=false;
 function pushField(){if(field.length>2000)throw new Error('A worksheet field exceeds 2,000 characters.');row.push(field);field='';closed=false;if(row.length>10)throw new Error('The worksheet has extra columns.');}
 function pushRow(){pushField();records.push(row);row=[];if(records.length>31)throw new Error('The worksheet must contain exactly 30 product rows.');}
 for(let index=0;index<text.length;index++){
  const char=text[index];
  if(quoted){if(char==='"'){if(text[index+1]==='"'){field+='"';index++;}else{quoted=false;closed=true;}}else field+=char;}
  else if(char===',')pushField();
  else if(char==='\n'||char==='\r'){if(char==='\r'){if(text[index+1]!=='\n')throw new Error('Use UTF-8 CSV with LF or CRLF line endings.');index++;}pushRow();}
  else if(char==='"'){if(field||closed)throw new Error('A CSV quote is misplaced.');quoted=true;}
  else{if(closed)throw new Error('Unexpected text after a quoted CSV field.');field+=char;}
  if(field.length>2000)throw new Error('A worksheet field exceeds 2,000 characters.');
 }
 if(quoted)throw new Error('A quoted CSV field is incomplete.');
 if(field||closed||row.length)pushRow();
 if(records.length!==31||JSON.stringify(records[0])!==JSON.stringify(receiptWorksheetHeaders))throw new Error('Use the original 10-column arrival worksheet with all 30 rows in order.');
 return records.slice(1).map((values,index)=>{
  const part=plan.rows[index],identity=['P'+String(index+1).padStart(2,'0'),part.id,part.selected_family,part.quantity_basis,part.role];
  if(values.length!==10||identity.some((value,column)=>values[column]!==value))throw new Error('Planning fields or identity differ at '+part.id+'. Restore those fields from a fresh worksheet.');
  const date=values[6];if(date&&(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date+'T00:00:00Z'))||new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date))throw new Error('Use a valid YYYY-MM-DD declared date or leave it blank at '+part.id+'.');
  if(!['awaiting-delivery-unverified','owner-notes-unverified'].includes(values[9]))throw new Error('Keep Record status as awaiting-delivery-unverified or owner-notes-unverified at '+part.id+'.');
  return {product_id:values[0],bom_id:values[1],selected_family:values[2],quantity_basis:values[3],role:values[4],declared_model:values[5],declared_received_date:values[6],declared_label_reference:values[7],declared_notes:values[8],declared_status:values[9]};
 });
}

function syncReceiptWorksheetControls(){
 if(!$('receipt-worksheet-panel'))return;
 const available=physicalBuildState==='ok'&&!!physicalBuildData;
 $('receipt-worksheet-file').disabled=!available;
 $('receipt-worksheet-clear').disabled=!receiptWorksheetData&&!receiptWorksheetReading&&!$('receipt-worksheet-file').value;
 $('receipt-worksheet-export').disabled=!available||!receiptWorksheetData||receiptWorksheetPlan!==physicalBuildData;
 for(const id of ['receipt-worksheet-search','receipt-worksheet-show','receipt-worksheet-filter-reset'])if($(id))$(id).disabled=!available||!receiptWorksheetData||receiptWorksheetPlan!==physicalBuildData;
 syncReceiptComparisonControls();
}
function receiptWorksheetHasEntries(row){return ['declared_model','declared_received_date','declared_label_reference','declared_notes'].some(key=>row[key].trim())||row.declared_status==='owner-notes-unverified';}
function receiptWorksheetSelection(){
 const query=$('receipt-worksheet-search').value.trim().toLowerCase(),mode=$('receipt-worksheet-show').value;
 return (receiptWorksheetData?.rows||[]).filter(row=>(mode==='all'||mode==='with-entries'&&receiptWorksheetHasEntries(row)||mode==='without-entries'&&!receiptWorksheetHasEntries(row))&&Object.values(row).some(value=>value.toLowerCase().includes(query)));
}
function renderReceiptWorksheetRows(){
 if(!$('receipt-worksheet-panel'))return;
 closeReceiptDeclaration();const available=!!receiptWorksheetData&&receiptWorksheetPlan===physicalBuildData&&physicalBuildState==='ok',rows=available?receiptWorksheetSelection():[];
 const shown=value=>value===''?'Not recorded':value;
 $('receipt-worksheet-rows').replaceChildren(...rows.map(row=>{const tr=document.createElement('tr');tr.innerHTML='<td><span class="bom-reference">'+escapeText(row.bom_id)+'</span><br><button class="asset-link" type="button" data-physical-plan-id="'+escapeText(row.bom_id)+'">'+escapeText(row.selected_family)+'</button><br><button class="action-outline" type="button" data-receipt-declaration="'+escapeText(row.bom_id)+'">View declaration</button></td>'+'<td></td>'.repeat(5);[row.declared_model,row.declared_received_date,row.declared_label_reference,row.declared_notes,row.declared_status].forEach((value,index)=>tr.children[index+1].textContent=shown(value));return tr;}));
 if(available&&!rows.length){const tr=document.createElement('tr'),cell=document.createElement('td'),message=document.createElement('span');cell.colSpan=6;cell.className='empty-state';message.className='receipt-filter-empty';message.textContent='No worksheet rows match. Try a different search or clear the review filters.';cell.append(message);tr.append(cell);$('receipt-worksheet-rows').append(tr);}
 $('receipt-worksheet-filter-count').textContent=available?rows.length+' of 30 worksheet rows displayed. All 30 remain in the complete review export.':'Load a worksheet to search its local declarations.';
 syncReceiptWorksheetControls();
}
function resetReceiptWorksheetFilters(restore=false){
 if(!$('receipt-worksheet-search'))return;
 $('receipt-worksheet-search').value='';$('receipt-worksheet-show').value='all';renderReceiptWorksheetRows();if(restore&&!$('receipt-worksheet-search').disabled)$('receipt-worksheet-search').focus();
}
function clearReceiptWorksheet(restore=false,resetFile=true){
 closeReceiptDeclaration();
 clearReceiptComparison();
 receiptWorksheetSequence++;receiptWorksheetData=null;receiptWorksheetPlan=null;receiptWorksheetReading=false;
 if(!$('receipt-worksheet-panel'))return;
 if(resetFile)$('receipt-worksheet-file').value='';$('receipt-worksheet-rows').replaceChildren();$('receipt-worksheet-context').replaceChildren();$('receipt-worksheet-counts').replaceChildren();
 resetReceiptWorksheetFilters();
 $('receipt-worksheet-feedback').textContent='No worksheet loaded. Choose a separate UTF-8 CSV working copy after recording your notes. Nothing is uploaded or saved.';
 syncReceiptWorksheetControls();if(restore&&!$('receipt-worksheet-file').disabled)$('receipt-worksheet-file').focus();
}
async function readReceiptWorksheet(file){
 clearReceiptWorksheet(false,false);const sequence=receiptWorksheetSequence,plan=physicalBuildData;
 if(!file)return;
 if(physicalBuildState!=='ok'||!plan){$('receipt-worksheet-feedback').textContent='Load the fixed 30-product plan before reviewing a worksheet.';return;}
 receiptWorksheetReading=true;syncReceiptWorksheetControls();$('receipt-worksheet-feedback').textContent='Reading your worksheet locally…';
 try{
  if(file.size>receiptWorksheetLimit)throw new Error('The worksheet exceeds 128 KiB.');
  const bytes=await file.arrayBuffer();if(bytes.byteLength>receiptWorksheetLimit)throw new Error('The worksheet exceeds 128 KiB.');
  const rows=parseReceiptWorksheet(new TextDecoder('utf-8',{fatal:true}).decode(bytes),plan);
  const digest=await crypto.subtle.digest('SHA-256',bytes),hash=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');
  if(sequence!==receiptWorksheetSequence||physicalBuildData!==plan)return;
  receiptWorksheetPlan=plan;
  receiptWorksheetData={schema_version:'1.0',scope:'local-browser-unverified-receipt-worksheet-review',reviewed_at:new Date().toISOString(),file_name:file.name,file_bytes:bytes.byteLength,file_sha256:hash,plan_version:plan.version,plan_sha256:plan.plan_sha256,source_csv_sha256:plan.source_csv_sha256,sensor_map_sha256:plan.sensor_map_sha256,rows,read_only:true,uploaded:false,persisted:false,order_verified:false,receipt_verified:false,physical_acceptance_verified:false,hardware_connected:false,equipment_authorized:false,production_ready:false,substitution_allowed:false,additional_hardware_allowed:false,note:'Local preview of owner-declared worksheet text only. Matching the original planning fields does not verify the declared model, date, label, notes, received quantity, electrical compatibility or physical installation. This is not a stored receipt or acceptance record.'};
  renderReceiptWorksheetRows();
  const labels=rows.filter(row=>row.declared_model.trim()).length,notes=rows.filter(row=>row.declared_notes.trim()).length;
  $('receipt-worksheet-counts').textContent='30 matched planning rows · '+labels+' model declarations · '+notes+' rows with notes. These counts do not verify receipt.';
  $('receipt-worksheet-context').textContent=file.name+' · '+bytes.byteLength+' bytes · File SHA-256: '+hash+' · Loaded plan SHA-256: '+plan.plan_sha256;
  $('receipt-worksheet-feedback').textContent='Worksheet structure matches the loaded 30-product plan. All owner declarations remain unverified. Export a local review copy or clear it when finished.';
 }catch(error){if(sequence===receiptWorksheetSequence&&physicalBuildData===plan)$('receipt-worksheet-feedback').textContent='Worksheet unavailable. '+(error instanceof TypeError?'Use a readable UTF-8 CSV file.':error.message)+' No prior review is retained.';}
 finally{if(sequence===receiptWorksheetSequence){receiptWorksheetReading=false;syncReceiptWorksheetControls();}}
}
function exportReceiptWorksheet(){
 if(!receiptWorksheetData||receiptWorksheetPlan!==physicalBuildData||physicalBuildState!=='ok')return;
 const url=URL.createObjectURL(new Blob([JSON.stringify(receiptWorksheetData,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-unverified-worksheet-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function closeReceiptDeclaration(restore=false){
 const dialog=$('receipt-declaration-dialog'),opener=receiptDeclarationReturn;
 receiptDeclarationContext=null;receiptDeclarationReturn=null;
 if(typeof physicalPartReturn!=='undefined'&&physicalPartReturn?.closest('#receipt-declaration-dialog'))closePhysicalPart();
 if(dialog?.open)dialog.close();$('receipt-declaration-body')?.replaceChildren();
 if(restore&&opener){if(opener.isConnected&&!opener.disabled)opener.focus();else if(!$('receipt-worksheet-file')?.disabled)$('receipt-worksheet-file')?.focus();else $('physical-build-refresh')?.focus();}
}
function openReceiptDeclaration(id,opener){
 closeReceiptDeclaration();
 const review=receiptWorksheetData,plan=receiptWorksheetPlan,row=review?.rows.find(item=>item.bom_id===id);
 if(!row||!plan||plan!==physicalBuildData||physicalBuildState!=='ok'){
  $('receipt-worksheet-feedback').textContent='Declaration unavailable. Load a supported worksheet against the current fixed plan before retrying.';return;
 }
 const dialog=$('receipt-declaration-dialog'),body=$('receipt-declaration-body'),context={review,plan,row};
 body.innerHTML='<p class="planning-boundary">Owner-declared worksheet text only. CSV identity matching does not verify the actual model, receipt, quantity, compatibility or installation. Nothing here authorizes equipment.</p><span class="bom-reference"></span><h3></h3><h3>Original planning context</h3><dl class="persisted-inspector-facts" id="receipt-declaration-planning"></dl><h3>Unverified owner declarations</h3><dl class="persisted-inspector-facts" id="receipt-declaration-facts"></dl><h3>Owner notes / unresolved issues</h3><p class="receipt-declaration-value" id="receipt-declaration-notes"></p><details id="receipt-declaration-provenance"><summary>Local file and loaded plan references</summary><dl class="persisted-inspector-facts" id="receipt-declaration-references"></dl><p>Hashes identify the loaded file and plan context. They do not verify the source, inspect referenced photos or establish physical acceptance. This row is a local preview, not a stored receipt record.</p></details><div class="replay-controls"><button id="receipt-declaration-plan" class="action-outline" type="button">View existing preparation notes</button><button id="receipt-declaration-export" class="action-outline" type="button">Export this unverified declaration</button></div>';
 body.querySelector('.bom-reference').textContent=row.bom_id;body.querySelector('h3').textContent=row.selected_family;
 const facts=(target,values)=>{for(const [label,value] of values){const item=document.createElement('div'),term=document.createElement('dt'),description=document.createElement('dd');term.textContent=label;description.textContent=value===''?'Not recorded':String(value);item.append(term,description);$(target).append(item);}};
 facts('receipt-declaration-planning',[['Product ID',row.product_id],['Role in the fixed plan',row.role],['Quantity basis · planning only',row.quantity_basis]]);
 facts('receipt-declaration-facts',[['Declared model / revision',row.declared_model],['Declared received date',row.declared_received_date],['Label / photo reference · not inspected',row.declared_label_reference],['Declared status · unverified',row.declared_status]]);
 $('receipt-declaration-notes').textContent=row.declared_notes===''?'Not recorded':row.declared_notes;
 facts('receipt-declaration-references',[['Local file name',review.file_name],['Local file bytes',review.file_bytes],['Local file SHA-256',review.file_sha256],['Loaded plan version',review.plan_version],['Loaded plan SHA-256',review.plan_sha256],['CSV reference hash',review.source_csv_sha256],['Map reference hash',review.sensor_map_sha256]]);
 receiptDeclarationContext=context;receiptDeclarationReturn=opener;dialog.showModal();$('receipt-declaration-close').focus();
 $('receipt-declaration-plan').addEventListener('click',event=>{if(receiptDeclarationContext===context&&receiptWorksheetData===review&&physicalBuildData===plan)openPhysicalPart(row.bom_id,event.currentTarget);});
 const button=$('receipt-declaration-export');button.addEventListener('click',()=>{
  if(!dialog.open||!button.isConnected||receiptDeclarationContext!==context||receiptWorksheetData!==review||physicalBuildData!==plan)return;
  const {rows,...references}=review,payload={...references,scope:'local-browser-unverified-worksheet-declaration',exported_at:new Date().toISOString(),total_worksheet_rows:rows.length,declaration:row,note:'Exact owner-declared row from the loaded worksheet only. Planning identity and hashes do not verify a physical item, received quantity, compatibility, referenced photo or acceptance. No upload or persistence occurred.'};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-'+row.bom_id.toLowerCase()+'-unverified-declaration.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
}
function bindReceiptDeclaration(){
 const dialog=document.createElement('dialog');dialog.id='receipt-declaration-dialog';dialog.className='product-dialog';dialog.setAttribute('aria-labelledby','receipt-declaration-title');dialog.innerHTML='<div class="product-dialog-head"><h2 id="receipt-declaration-title">Worksheet declaration</h2><button id="receipt-declaration-close" class="action-outline" type="button">Close</button></div><div id="receipt-declaration-body"></div>';$('main').append(dialog);
 $('receipt-declaration-close').addEventListener('click',()=>closeReceiptDeclaration(true));dialog.addEventListener('cancel',event=>{event.preventDefault();closeReceiptDeclaration(true);});dialog.addEventListener('close',()=>{if(!dialog.open)closeReceiptDeclaration(true);});
 document.addEventListener('click',event=>{const button=event.target.closest('[data-receipt-declaration]');if(button&&!button.disabled)openReceiptDeclaration(button.dataset.receiptDeclaration,button);});
 document.addEventListener('keydown',event=>{if(event.key!=='Escape'||!dialog.open)return;const target=event.target.closest?.('dialog'),top=[...document.querySelectorAll('dialog[open]')].at(-1);if(target===dialog||(!target&&top===dialog)){event.preventDefault();event.stopImmediatePropagation();closeReceiptDeclaration(true);}},{capture:true});
}
function syncReceiptComparisonControls(){
 if(!$('receipt-comparison-panel'))return;
 const available=!!receiptWorksheetData&&receiptWorksheetPlan===physicalBuildData&&physicalBuildState==='ok';
 $('receipt-comparison-file').disabled=!available;
 $('receipt-comparison-clear').disabled=!receiptComparisonData&&!receiptComparisonReading&&!$('receipt-comparison-file').value;
 $('receipt-comparison-export').disabled=!available||!receiptComparisonData||receiptComparisonReview!==receiptWorksheetData;
 $('receipt-comparison-report').disabled=!available||!receiptComparisonData||receiptComparisonReview!==receiptWorksheetData;
 $('receipt-comparison-changed').disabled=!available||!receiptComparisonData||receiptComparisonReview!==receiptWorksheetData;
}
function clearReceiptComparison(restore=false,resetFile=true){
 receiptComparisonSequence++;receiptComparisonData=null;receiptComparisonReview=null;receiptComparisonReading=false;
 if(!$('receipt-comparison-panel'))return;
 if(resetFile)$('receipt-comparison-file').value='';$('receipt-comparison-changed').checked=true;$('receipt-comparison-rows').replaceChildren();$('receipt-comparison-context').replaceChildren();$('receipt-comparison-files').replaceChildren();$('receipt-comparison-count').replaceChildren();
 $('receipt-comparison-report-feedback').replaceChildren();
 $('receipt-comparison-feedback').textContent='Load worksheet A above, then choose another CSV as B. A and B are comparison labels, not verified revision order. Nothing is uploaded or stored.';
 syncReceiptComparisonControls();if(restore&&!$('receipt-comparison-file').disabled)$('receipt-comparison-file').focus();
}
function renderReceiptComparison(){
 const data=receiptComparisonData;if(!data||receiptComparisonReview!==receiptWorksheetData)return;
 const rows=data.comparisons.filter(row=>!$('receipt-comparison-changed').checked||row.changed_fields>0);
 $('receipt-comparison-count').textContent=data.changed_rows+' of 30 rows changed · '+data.changed_fields+' of 150 owner fields changed · '+rows.length+' rows displayed. Text differences do not verify receipt or compatibility.';
 $('receipt-comparison-rows').replaceChildren(...rows.map(row=>{
  const card=document.createElement('details'),summary=document.createElement('summary');card.className='receipt-comparison-card';card.dataset.receiptComparisonId=row.bom_id;summary.textContent=row.bom_id+' · '+row.selected_family+' · '+row.changed_fields+' of 5 fields changed';card.append(summary);
  for(const field of row.fields){const section=document.createElement('section'),heading=document.createElement('h4'),pair=document.createElement('dl');heading.textContent=field.label+' · '+field.change;pair.className='receipt-comparison-pair';for(const [label,value] of [['A · unverified',field.a],['B · unverified',field.b]]){const item=document.createElement('div'),term=document.createElement('dt'),description=document.createElement('dd');term.textContent=label;description.textContent=value===''?'Not recorded':value;item.append(term,description);pair.append(item);}section.append(heading,pair);card.append(section);}return card;
 }));
 if(!rows.length){const empty=document.createElement('p');empty.textContent='No changed rows to display. Turn off Show only changed rows to inspect all 30. The export still contains both complete snapshots and every comparison.';$('receipt-comparison-rows').append(empty);}
}
async function readReceiptComparison(file){
 clearReceiptComparison(false,false);if(!file)return;
 const sequence=receiptComparisonSequence,review=receiptWorksheetData,plan=receiptWorksheetPlan;
 if(!review||!plan||plan!==physicalBuildData||physicalBuildState!=='ok'){$('receipt-comparison-feedback').textContent='Load a supported worksheet A against the current plan before choosing B.';return;}
 receiptComparisonReading=true;syncReceiptComparisonControls();$('receipt-comparison-feedback').textContent='Reading worksheet B and comparing locally…';
 try{
  if(file.size>receiptWorksheetLimit)throw new Error('Worksheet B exceeds 128 KiB.');const bytes=await file.arrayBuffer();if(bytes.byteLength>receiptWorksheetLimit)throw new Error('Worksheet B exceeds 128 KiB.');
  const rows=parseReceiptWorksheet(new TextDecoder('utf-8',{fatal:true}).decode(bytes),plan),digest=await crypto.subtle.digest('SHA-256',bytes),hash=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');
  if(sequence!==receiptComparisonSequence||receiptWorksheetData!==review||physicalBuildData!==plan)return;
  const comparisons=receiptComparisonRows(review.rows,rows);
  receiptComparisonReview=review;receiptComparisonData={schema_version:'1.0',scope:'local-browser-unverified-worksheet-comparison',compared_at:new Date().toISOString(),plan_version:review.plan_version,plan_sha256:review.plan_sha256,source_csv_sha256:review.source_csv_sha256,sensor_map_sha256:review.sensor_map_sha256,a:{file_name:review.file_name,file_bytes:review.file_bytes,file_sha256:review.file_sha256,rows:review.rows},b:{file_name:file.name,file_bytes:bytes.byteLength,file_sha256:hash,rows},comparisons,changed_rows:comparisons.filter(row=>row.changed_fields>0).length,changed_fields:comparisons.reduce((total,row)=>total+row.changed_fields,0),read_only:true,uploaded:false,persisted:false,order_verified:false,receipt_verified:false,physical_acceptance_verified:false,hardware_connected:false,equipment_authorized:false,production_ready:false,substitution_allowed:false,additional_hardware_allowed:false,note:'Exact text comparison of five unverified owner fields for the same 30 planning identities. A/B do not establish revision order. Whitespace and line-ending differences count as text changes. Added/removed/changed labels concern text fields, not physical receipt, compatibility, installation or approval. No photo references are opened. Both complete snapshots and all comparisons are exported regardless of display filtering.'};
  $('receipt-comparison-files').textContent='A: '+review.file_name+' | B: '+file.name;
  $('receipt-comparison-context').textContent='A: '+review.file_name+' · SHA-256 '+review.file_sha256+' | B: '+file.name+' · SHA-256 '+hash+' | Loaded plan SHA-256 '+review.plan_sha256;
  $('receipt-comparison-feedback').textContent='Both worksheets match the same loaded planning identities. Owner declarations remain unverified. The original worksheet A review is unchanged.';renderReceiptComparison();
 }catch(error){if(sequence===receiptComparisonSequence&&receiptWorksheetData===review&&physicalBuildData===plan)$('receipt-comparison-feedback').textContent='Comparison unavailable. '+(error instanceof TypeError?'Use a readable UTF-8 CSV file.':error.message)+' No prior comparison or export is retained. Worksheet A remains unchanged.';}
 finally{if(sequence===receiptComparisonSequence){receiptComparisonReading=false;syncReceiptComparisonControls();}}
}
function bindReceiptComparison(panel){
 const section=document.createElement('details');section.id='receipt-comparison-panel';section.innerHTML='<summary>Compare another worksheet locally</summary><p>The worksheet loaded above is A. Choose a separate working copy as B to compare declared model, date, label reference, notes and status. Both must retain the same 30 planning identities. Differences are text changes, not receipt, compatibility or commissioning evidence.</p><div class="physical-preparation-tools"><label for="receipt-comparison-file">Worksheet B · UTF-8 CSV · up to 128 KiB<input id="receipt-comparison-file" type="file" accept=".csv,text/csv" disabled></label><button id="receipt-comparison-clear" class="action-outline" type="button" disabled>Clear comparison</button><button id="receipt-comparison-export" class="action-outline" type="button" disabled>Export complete comparison</button></div><p id="receipt-comparison-feedback" role="status" aria-live="polite"></p><p id="receipt-comparison-files"></p><details><summary>Comparison file and plan references</summary><p id="receipt-comparison-context"></p></details><label class="receipt-comparison-toggle"><input type="checkbox" id="receipt-comparison-changed" checked disabled> Show only changed rows</label><p id="receipt-comparison-count" role="status" aria-live="polite"></p><div id="receipt-comparison-rows"></div>';
 panel.querySelector('#receipt-worksheet-search').closest('.physical-preparation-tools').before(section);
 const reportButton=document.createElement('button');reportButton.id='receipt-comparison-report';reportButton.className='action-outline';reportButton.type='button';reportButton.disabled=true;reportButton.textContent='Download printable comparison';$('receipt-comparison-export').after(reportButton);const reportFeedback=document.createElement('p');reportFeedback.id='receipt-comparison-report-feedback';reportFeedback.setAttribute('role','status');reportFeedback.setAttribute('aria-live','polite');$('receipt-comparison-feedback').after(reportFeedback);
 $('receipt-comparison-file').addEventListener('change',event=>readReceiptComparison(event.target.files[0]));$('receipt-comparison-clear').addEventListener('click',()=>clearReceiptComparison(true));$('receipt-comparison-changed').addEventListener('change',renderReceiptComparison);
 $('receipt-comparison-export').addEventListener('click',()=>{if(!receiptComparisonData||receiptComparisonReview!==receiptWorksheetData||receiptWorksheetPlan!==physicalBuildData||physicalBuildState!=='ok')return;const url=URL.createObjectURL(new Blob([JSON.stringify(receiptComparisonData,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='edgeops-unverified-worksheet-comparison.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 reportButton.addEventListener('click',()=>{if(!receiptComparisonData||receiptComparisonReview!==receiptWorksheetData||receiptWorksheetPlan!==physicalBuildData||physicalBuildState!=='ok')return;try{const html=receiptComparisonHtml(receiptComparisonData),url=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download='edgeops-unverified-worksheet-comparison.html';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);reportFeedback.textContent='Printable copy downloaded with all 30 rows and 150 field comparisons. Open it locally and use your browser’s Print command to print or save as PDF. Owner declarations remain unverified.';}catch(error){reportFeedback.textContent='Printable comparison unavailable. '+error.message;}});
 clearReceiptComparison();
}
function receiptComparisonRows(aRows,bRows){
 return aRows.map((a,index)=>{const b=bRows[index],fields=receiptComparisonFields.map(([key,label])=>({key,label,a:a[key],b:b[key],change:a[key]===b[key]?'unchanged':a[key]===''?'added':b[key]===''?'removed':'changed'}));return {bom_id:a.bom_id,selected_family:a.selected_family,changed_fields:fields.filter(field=>field.change!=='unchanged').length,fields};});
}
function receiptComparisonHtml(data,generatedAt=new Date().toISOString()){
 const refuse=()=>{throw new Error('A complete supported unverified comparison is required.');},hex=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
 if(data?.schema_version!=='1.0'||data.scope!=='local-browser-unverified-worksheet-comparison'||data.read_only!==true||data.plan_version!=='fixed-30-physical-build-v1'||typeof data.compared_at!=='string')refuse();
 for(const key of ['uploaded','persisted','order_verified','receipt_verified','physical_acceptance_verified','hardware_connected','equipment_authorized','production_ready','substitution_allowed','additional_hardware_allowed'])if(data[key]!==false)refuse();
 for(const key of ['plan_sha256','source_csv_sha256','sensor_map_sha256'])if(!hex(data[key]))refuse();
 for(const side of [data.a,data.b]){
  if(!side||typeof side.file_name!=='string'||side.file_name.length>2000||!Number.isInteger(side.file_bytes)||side.file_bytes<0||side.file_bytes>receiptWorksheetLimit||!hex(side.file_sha256)||!Array.isArray(side.rows)||side.rows.length!==30)refuse();
  side.rows.forEach((row,index)=>{
   if(!row||row.product_id!=='P'+String(index+1).padStart(2,'0')||row.bom_id!=='BOM-'+String(index+1).padStart(2,'0'))refuse();
   for(const key of ['selected_family','quantity_basis','role',...receiptComparisonFields.map(([key])=>key)])if(typeof row[key]!=='string'||row[key].length>2000)refuse();
   if(!row.selected_family.trim()||!row.quantity_basis.trim()||!row.role.trim()||!['awaiting-delivery-unverified','owner-notes-unverified'].includes(row.declared_status))refuse();
   const date=row.declared_received_date;if(date&&(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date+'T00:00:00Z'))||new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date))refuse();
  });
 }
 if(data.a.rows.some((row,index)=>['product_id','bom_id','selected_family','quantity_basis','role'].some(key=>row[key]!==data.b.rows[index][key])))refuse();
 const rows=receiptComparisonRows(data.a.rows,data.b.rows),changedRows=rows.filter(row=>row.changed_fields>0).length,changedFields=rows.reduce((count,row)=>count+row.changed_fields,0);
 if(JSON.stringify(rows)!==JSON.stringify(data.comparisons)||changedRows!==data.changed_rows||changedFields!==data.changed_fields)refuse();
 const text=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),shown=value=>value===''?'Not recorded':value,field=(label,value)=>'<div><dt>'+text(label)+'</dt><dd>'+text(shown(value))+'</dd></div>';
 const cards=rows.map((row,index)=>'<article class="comparison-row"><h2>'+text(row.bom_id)+' · '+text(row.selected_family)+'</h2><p>'+row.changed_fields+' of 5 owner fields changed</p><dl class="planning">'+field('Product ID',data.a.rows[index].product_id)+field('Original planning role',data.a.rows[index].role)+field('Quantity basis · planning only',data.a.rows[index].quantity_basis)+'</dl>'+row.fields.map(change=>'<section class="comparison-field"><h3>'+text(change.label)+' · '+text(change.change)+'</h3><dl class="pair">'+field('A · unverified',change.a)+field('B · unverified',change.b)+'</dl></section>').join('')+'</article>').join('');
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;"><title>EDGEOPS · Unverified worksheet comparison</title><style>'+receiptComparisonReportStyles+'</style></head><body><main><header><p class="brand">EDGEOPS / LOCAL WORKSHEET REVIEW</p><p class="badge">UNVERIFIED OWNER DECLARATIONS</p><h1>Worksheet A/B comparison</h1><p>'+changedRows+' of 30 rows changed · '+changedFields+' of 150 owner fields changed</p></header><aside><strong>Read-only local working copy</strong><p>All 30 rows and all 150 owner-field comparisons are included, regardless of display filters or collapsed cards in the dashboard. A/B labels do not establish revision order, receipt, compatibility or commissioning. Empty text displays Not recorded. Added/removed/changed labels concern exact text, including whitespace and line endings, not physical items.</p><p>Uploaded: false · Stored receipt: false · Receipt verified: false · Physical acceptance: false · Hardware connected: false · Equipment authorized: false · Production ready: false · Substitution allowed: false · Additional hardware allowed: false.</p><p>File hashes are loaded references, not signatures or independent source verification. Photo references are text only and have not been inspected.</p><p>Comparison prepared in the browser: '+text(data.compared_at)+'. This report generated in the browser: '+text(generatedAt)+'. Browser times are not verified service or device times.</p></aside><p class="screen-only">Open your browser’s Print command to print or save as PDF. This visual copy normalizes HTML line rendering; retain the complete JSON export for exact machine-readable strings. Keep the CSV originals separately. Downloaded copies remain under your control when the dashboard review is cleared.</p><section><h2>File and plan references</h2><dl class="references">'+field('A file',data.a.file_name)+field('B file',data.b.file_name)+field('A bytes',data.a.file_bytes)+field('B bytes',data.b.file_bytes)+field('A SHA-256',data.a.file_sha256)+field('B SHA-256',data.b.file_sha256)+field('Loaded plan version',data.plan_version)+field('Loaded plan SHA-256',data.plan_sha256)+field('CSV reference hash',data.source_csv_sha256)+field('Map reference hash',data.sensor_map_sha256)+'</dl></section>'+cards+'<footer>EDGEOPS · complete 30-row local comparison · unverified declarations · not a signed acceptance record or equipment authorization</footer></main></body></html>';
}
const receiptComparisonReportStyles=`
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#edf2f8;color:#142f49;font:15px/1.7 system-ui,"Segoe UI",sans-serif}main{max-width:1000px;margin:30px auto;padding:40px;background:#fff;border:1px solid #b8c9dc;border-radius:14px}header{border-bottom:3px solid #15836f;padding-bottom:22px}.brand{font-size:13px;font-weight:800;letter-spacing:.1em}.badge{display:inline-block;padding:5px 12px;background:#fff5d9;color:#614000;border:1px solid #ba8b31;border-radius:6px;font-size:12px;font-weight:750}h1{font-size:30px;line-height:1.3}h2{font-size:22px;line-height:1.4}h3{font-size:16px}aside{margin:24px 0;padding:18px;background:#edf6fa;border:1px solid #a4c4d5;border-left:4px solid #15836f;border-radius:7px}aside p,.screen-only{font-size:13px}.pair,.planning,.references{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.pair>div{padding:16px;border:1px solid #b8c9dc;border-radius:8px;background:#f6f9fc}dt{font-size:12px;font-weight:700;color:#385570}dd{margin:6px 0 0;white-space:pre-wrap}.comparison-row{padding:24px 0;border-top:1px solid #b8c9dc}.comparison-field{margin:20px 0}h1,h2,h3,p,dt,dd,footer{overflow-wrap:anywhere}footer{border-top:1px solid #b8c9dc;padding-top:16px;font-size:12px}@media(max-width:640px){main{margin:0;padding:20px;border:0;border-radius:0}h1{font-size:25px}.pair,.planning,.references{grid-template-columns:1fr}}@page{size:A4;margin:14mm}@media print{body{background:#fff;font-size:10pt}main{max-width:none;margin:0;padding:0;border:0;border-radius:0}.screen-only{display:none}h1{font-size:22pt}h2{font-size:15pt;break-after:avoid}h3{font-size:12pt;break-after:avoid}dt,footer{font-size:8pt}dd,aside p{font-size:9pt}.pair,.planning,.references{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.comparison-field,.references>div,.planning>div{break-inside:avoid}.pair>div{padding:10px}.comparison-row{padding:16px 0}aside{padding:12px}}
`;
document.addEventListener('DOMContentLoaded',()=>{
 const panel=document.createElement('article');panel.id='receipt-worksheet-panel';panel.className='panel operations-panel';panel.innerHTML='<span class="section-kicker">HARDWARE ARRIVAL / LOCAL WORKING COPY</span><h2>Review your receipt worksheet</h2><p>Choose the CSV working copy from your arrival pack. Planning fields must remain unchanged. Fill the model, date, label reference and notes after delivery; use YYYY-MM-DD dates. Keep Record status as awaiting-delivery-unverified or owner-notes-unverified.</p><p class="planning-boundary">This preview stays in this browser page. No file is uploaded or stored, and no receipt, connection or compatibility is verified. Keep your original CSV; reloading the page clears this review.</p><div class="physical-preparation-tools"><label for="receipt-worksheet-file">Worksheet CSV · UTF-8 · up to 128 KiB<input id="receipt-worksheet-file" type="file" accept=".csv,text/csv" aria-describedby="receipt-worksheet-feedback" disabled></label><button id="receipt-worksheet-clear" class="action-outline" type="button" disabled>Clear review</button><button id="receipt-worksheet-export" class="action-outline" type="button" disabled>Export unverified review</button></div><p id="receipt-worksheet-feedback" role="status" aria-live="polite"></p><p id="receipt-worksheet-counts"></p><details><summary>Local file and loaded plan references</summary><p id="receipt-worksheet-context"></p></details><div class="product-table-wrap"><table><thead><tr><th>Original planning item</th><th>Declared model / revision</th><th>Declared date</th><th>Label / photo reference</th><th>Owner notes / issues</th><th>Declared status · unverified</th></tr></thead><tbody id="receipt-worksheet-rows"></tbody></table></div>';
 const region=panel.querySelector('.product-table-wrap');region.tabIndex=0;region.setAttribute('role','region');region.setAttribute('aria-label','Unverified worksheet declarations');const hint=document.createElement('p');hint.className='product-muted';hint.textContent='On smaller screens, scroll this table sideways to review every declaration. Keyboard: focus the table and use the arrow keys.';region.before(hint);
 const filters=document.createElement('div');filters.className='physical-preparation-tools';filters.innerHTML='<label for="receipt-worksheet-search">Find a worksheet row<input id="receipt-worksheet-search" type="search" maxlength="160" placeholder="BOM, model, date, label or notes…" aria-describedby="receipt-worksheet-filter-count" disabled></label><label for="receipt-worksheet-show">Show rows<select id="receipt-worksheet-show" disabled><option value="all">All 30 rows</option><option value="with-entries">With owner entries</option><option value="without-entries">Without owner entries</option></select></label><button id="receipt-worksheet-filter-reset" class="action-outline" type="button" disabled>Clear review filters</button>';
 const count=document.createElement('p');count.id='receipt-worksheet-filter-count';count.setAttribute('role','status');count.setAttribute('aria-live','polite');hint.before(filters,count);
 $('physical-build-panel').after(panel);bindReceiptDeclaration();bindReceiptComparison(panel);$('receipt-worksheet-file').addEventListener('change',event=>readReceiptWorksheet(event.target.files[0]));$('receipt-worksheet-clear').addEventListener('click',()=>clearReceiptWorksheet(true));$('receipt-worksheet-export').addEventListener('click',exportReceiptWorksheet);clearReceiptWorksheet();
 $('receipt-worksheet-export').textContent='Export complete review';$('receipt-worksheet-search').addEventListener('input',renderReceiptWorksheetRows);$('receipt-worksheet-show').addEventListener('change',renderReceiptWorksheetRows);$('receipt-worksheet-filter-reset').addEventListener('click',()=>resetReceiptWorksheetFilters(true));
});
