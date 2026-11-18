/* EDGEOPS signed-in dashboard API glue. Read-only physical equipment view.
 * NEVER infer that inventory slots are installed, connected, or purchased.
 */
"use strict";
const edg = id => document.getElementById(id);
function safeText(value){return String(value ?? "").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));}
async function edgFetch(url,options={}){
  const response=await fetch(url,{credentials:"same-origin",...options});
  if(response.status===401){window.location.assign("/signin");throw new Error("Session expired");}
  if(!response.ok)throw new Error("Service returned "+response.status);
  return response.json();
}
function csrfToken(){
  const field=document.cookie.split("; ").find(x=>x.startsWith("edgeops_csrf="));
  return field?decodeURIComponent(field.slice("edgeops_csrf=".length)):"";
}
async function initializeHardware(){
  const result=await edgFetch("/api/hardware");
  const metrics=edg("hardware-metrics"), table=edg("hardware-table");
  if(metrics) metrics.innerHTML=[
    ["30","Planned catalog slots"],[String(result.confirmed_hardware_count),"Named components"],["16","Unconfirmed slots"],["0","Verified connected devices"]
  ].map(([value,title])=>'<article class="metric"><div class="metric-label">'+safeText(title)+'</div><div class="metric-number">'+safeText(value)+'</div><div class="metric-foot">Planning inventory only</div></article>').join("");
  if(table)table.innerHTML=result.devices.map(device=>'<tr><td><strong>'+safeText(device.id)+'</strong></td><td><strong>'+safeText(device.name)+'</strong></td><td>'+safeText(device.purpose)+'</td><td>'+safeText(device.category)+'</td><td><span class="status-tag watch">Not connected</span></td></tr>').join("");
}
document.addEventListener("DOMContentLoaded",async()=>{
  try{
    const [me,health]=await Promise.all([edgFetch("/api/me"),edgFetch("/api/system/health")]);
    if(edg("account-label"))edg("account-label").textContent=me.email;
    if(health.hardware_connected||health.actuators_enabled){
      throw new Error("Unexpected operational hardware state; this UI expects read-only local fixtures");
    }
    await initializeHardware();
  }catch(error){
    if(edg("hardware-table"))edg("hardware-table").textContent="Inventory service unavailable: "+error.message;
  }
  const logout=edg("logout");
  if(logout)logout.addEventListener("click",async()=>{
    logout.disabled=true;
    try{
      await edgFetch("/api/auth/logout",{method:"POST",headers:{"x-edgeops-csrf":csrfToken()}});
      window.location.assign("/signin");
    }catch(error){logout.disabled=false;alert("Could not sign out: "+error.message);}
  });
});
