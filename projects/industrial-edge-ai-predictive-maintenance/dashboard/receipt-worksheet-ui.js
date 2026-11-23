"use strict";
const receiptWorksheetHeaders=['Product ID','BOM ID','Selected family','Planned quantity','Bench role','Actual received model / board revision','Received date','Label / photo reference','Inspection notes / unresolved issue','Record status'];
const receiptWorksheetLimit=128*1024;
let receiptWorksheetSequence=0,receiptWorksheetData=null,receiptWorksheetPlan=null,receiptWorksheetReading=false;
let receiptDeclarationContext=null,receiptDeclarationReturn=null;

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
}
function clearReceiptWorksheet(restore=false,resetFile=true){
 closeReceiptDeclaration();
 receiptWorksheetSequence++;receiptWorksheetData=null;receiptWorksheetPlan=null;receiptWorksheetReading=false;
 if(!$('receipt-worksheet-panel'))return;
 if(resetFile)$('receipt-worksheet-file').value='';$('receipt-worksheet-rows').replaceChildren();$('receipt-worksheet-context').replaceChildren();$('receipt-worksheet-counts').replaceChildren();
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
  const shown=value=>value===''?'Not recorded':value;
  $('receipt-worksheet-rows').replaceChildren(...rows.map(row=>{const tr=document.createElement('tr');tr.innerHTML='<td><span class="bom-reference">'+escapeText(row.bom_id)+'</span><br><button class="asset-link" type="button" data-physical-plan-id="'+escapeText(row.bom_id)+'">'+escapeText(row.selected_family)+'</button><br><button class="action-outline" type="button" data-receipt-declaration="'+escapeText(row.bom_id)+'">View declaration</button></td>'+'<td></td>'.repeat(5);[row.declared_model,row.declared_received_date,row.declared_label_reference,row.declared_notes,row.declared_status].forEach((value,index)=>tr.children[index+1].textContent=shown(value));return tr;}));
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
document.addEventListener('DOMContentLoaded',()=>{
 const panel=document.createElement('article');panel.id='receipt-worksheet-panel';panel.className='panel operations-panel';panel.innerHTML='<span class="section-kicker">HARDWARE ARRIVAL / LOCAL WORKING COPY</span><h2>Review your receipt worksheet</h2><p>Choose the CSV working copy from your arrival pack. Planning fields must remain unchanged. Fill the model, date, label reference and notes after delivery; use YYYY-MM-DD dates. Keep Record status as awaiting-delivery-unverified or owner-notes-unverified.</p><p class="planning-boundary">This preview stays in this browser page. No file is uploaded or stored, and no receipt, connection or compatibility is verified. Keep your original CSV; reloading the page clears this review.</p><div class="physical-preparation-tools"><label for="receipt-worksheet-file">Worksheet CSV · UTF-8 · up to 128 KiB<input id="receipt-worksheet-file" type="file" accept=".csv,text/csv" aria-describedby="receipt-worksheet-feedback" disabled></label><button id="receipt-worksheet-clear" class="action-outline" type="button" disabled>Clear review</button><button id="receipt-worksheet-export" class="action-outline" type="button" disabled>Export unverified review</button></div><p id="receipt-worksheet-feedback" role="status" aria-live="polite"></p><p id="receipt-worksheet-counts"></p><details><summary>Local file and loaded plan references</summary><p id="receipt-worksheet-context"></p></details><div class="product-table-wrap"><table><thead><tr><th>Original planning item</th><th>Declared model / revision</th><th>Declared date</th><th>Label / photo reference</th><th>Owner notes / issues</th><th>Declared status · unverified</th></tr></thead><tbody id="receipt-worksheet-rows"></tbody></table></div>';
 const region=panel.querySelector('.product-table-wrap');region.tabIndex=0;region.setAttribute('role','region');region.setAttribute('aria-label','Unverified worksheet declarations');const hint=document.createElement('p');hint.className='product-muted';hint.textContent='On smaller screens, scroll this table sideways to review every declaration. Keyboard: focus the table and use the arrow keys.';region.before(hint);
 $('physical-build-panel').after(panel);bindReceiptDeclaration();$('receipt-worksheet-file').addEventListener('change',event=>readReceiptWorksheet(event.target.files[0]));$('receipt-worksheet-clear').addEventListener('click',()=>clearReceiptWorksheet(true));$('receipt-worksheet-export').addEventListener('click',exportReceiptWorksheet);clearReceiptWorksheet();
});
