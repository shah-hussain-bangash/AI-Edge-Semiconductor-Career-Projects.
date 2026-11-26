"use strict";
document.addEventListener('DOMContentLoaded',()=>{
 const anchor=document.getElementById('readiness-feedback');if(!anchor)return;
 const panel=document.createElement('article');panel.id='local-capability-panel';panel.className='panel product-pad';
 panel.innerHTML='<span class="section-kicker">LOCAL SOFTWARE / CURRENT OBSERVATIONS</span><h2>What is available, and what needs attention?</h2><p>All 14 local software areas are listed below. Configuration and saved activity are separate from the 53 acceptance criteria. Refreshing or exporting these observations changes no acceptance decision.</p><div class="replay-controls"><button type="button" id="local-capability-refresh" class="action-outline">Refresh local checks</button><button type="button" id="local-capability-export" class="action-outline" disabled>Export local observations</button><label>Show areas<select id="local-capability-filter"><option value="all">All 14 areas</option><option value="configuration_needed">Configuration needed</option><option value="records_needed">Records needed</option><option value="review_required">Review required</option><option value="optional_setup">Optional setup</option><option value="available_locally">Available locally</option><option value="access_restricted">Administrator / auditor view</option></select></label></div><p id="local-capability-status" role="status" aria-live="polite">Loading current local observations…</p><div id="local-capability-list" class="local-capability-grid"></div>';
 anchor.before(panel);
 const $=id=>document.getElementById(id),labels={configuration_needed:'Configuration needed',records_needed:'Records needed',review_required:'Review required',optional_setup:'Optional setup',available_locally:'Available locally',access_restricted:'Administrator / auditor view'};
 const routes=new Set(['telemetry','assets','alerts','maintenance','settings','models','knowledge']);let snapshot=null,ticket=0;
 function clear(){snapshot=null;$('local-capability-list').replaceChildren();$('local-capability-export').disabled=true;}
 function render(){const list=$('local-capability-list');list.replaceChildren();if(!snapshot)return;let shown=0;
  for(const item of snapshot.items){if($('local-capability-filter').value!=='all'&&item.state!==$('local-capability-filter').value)continue;shown++;
   const card=document.createElement('section');card.className='local-capability-card';card.dataset.capability=item.id;
   const title=document.createElement('h3');title.textContent=item.title;const state=document.createElement('p');state.className='local-capability-state';state.textContent=labels[item.state];
   const software=document.createElement('p');software.textContent='Software: '+item.software+'.';const observed=document.createElement('p');observed.textContent=item.observation;
   const next=document.createElement('p');next.textContent='Next review: '+item.next_step;card.append(title,state,software,observed,next);
   if(item.state!=='access_restricted'&&routes.has(item.workspace)){const open=document.createElement('button');open.type='button';open.className='action-outline';open.textContent='Open '+item.workspace;open.addEventListener('click',()=>navigate(item.workspace));card.append(open);}list.append(card);
  }
  if(!shown){const empty=document.createElement('p');empty.textContent='No areas match this filter. This is not a production acceptance result.';list.append(empty);}
  $('local-capability-status').textContent=shown+' of 14 areas shown · observed '+snapshot.generated_at+' · configuration presence and saved counts only; production acceptance remains unverified.';
 }
 async function refresh(){const mine=++ticket;clear();$('local-capability-refresh').disabled=true;$('local-capability-status').textContent='Checking current local records and configuration…';
  try{const data=await edgFetch('/api/production-readiness/local-capabilities');if(mine!==ticket)return;
   if(data.scope!=='local-capability-observations'||data.production_ready!==false||data.acceptance_records_changed!==false||!Array.isArray(data.items)||data.items.length!==14||new Set(data.items.map(item=>item.id)).size!==14||data.items.some(item=>!Object.hasOwn(labels,item.state)||item.production_accepted!==false))throw Error('Unsupported observation response');
   snapshot=data;render();$('local-capability-export').disabled=false;
  }catch{if(mine!==ticket)return;clear();$('local-capability-status').textContent='Local checks unavailable. Old observations and export have been cleared. Refresh to retry; the acceptance register remains separate.';}
  finally{if(mine===ticket)$('local-capability-refresh').disabled=false;}
 }
 $('local-capability-refresh').addEventListener('click',refresh);$('local-capability-filter').addEventListener('change',render);
 $('local-capability-export').addEventListener('click',()=>{if(!snapshot)return;const blob=new Blob([JSON.stringify(snapshot,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='edgeops-local-capability-observations.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);});
 refresh();
});
