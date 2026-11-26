"use strict";
/* Production-facing features are intentionally unavailable in this local demo:
   SSO, remote reset and external signup require a configured identity provider. */
document.addEventListener("DOMContentLoaded",()=>{
 const form=document.getElementById("signin-form");
 document.querySelectorAll("img[data-fallback]").forEach(image=>{const recover=()=>{const backup=image.dataset.fallback;if(backup&&image.getAttribute("src")!==backup)image.src=backup;};image.addEventListener("error",recover);if(image.complete&&image.naturalWidth===0)recover();});
 const error=document.getElementById("form-error");
 const submit=document.getElementById("submit");
 const pass=document.getElementById("password");
 const email=document.getElementById("email");
 const note=document.getElementById("access-note");
 const remember=document.getElementById("remember-email");
 try { const saved=localStorage.getItem("edgeops_remembered_email");if(saved){email.value=saved;remember.checked=true} }catch{}
 document.getElementById("toggle-password").addEventListener("click",e=>{
   const visible=pass.type==="text";pass.type=visible?"password":"text";
   e.currentTarget.textContent=visible?"Show":"Hide";
   e.currentTarget.setAttribute("aria-label",visible?"Show password":"Hide password");
 });
 document.getElementById("forgot-password").addEventListener("click",()=>{
   note.textContent="Password recovery is not configured in this local development environment. Contact your workspace administrator.";
 });
 document.getElementById("sso-button").addEventListener("click",()=>{
   note.textContent="Enterprise SSO is planned, but no identity provider is connected. Use your local administrator credentials.";
 });
 document.getElementById("demo-button").addEventListener("click",()=>{
   note.textContent="Demo access is managed locally. Ask the repository owner to configure an administrator account; no public registration is enabled.";
 });
 form.addEventListener("submit",async event=>{
   event.preventDefault();error.textContent="";
   const address=email.value.trim(),password=pass.value;
   if(!address||!password){error.textContent="Enter your email and password.";return}
   submit.disabled=true;
   try{
     const response=await fetch("/api/auth/login",{method:"POST",credentials:"same-origin",headers:{"content-type":"application/json"},body:JSON.stringify({email:address,password,otp_code:document.getElementById("otp-code").value.trim()})});
     if(response.ok){
       try{if(remember.checked)localStorage.setItem("edgeops_remembered_email",address);else localStorage.removeItem("edgeops_remembered_email")}catch{}
       const view=new URLSearchParams(window.location.search).get("view");
       window.location.assign("/app"+(["registered","demonstration"].includes(view)?"?view="+view:""));return;
     }
     error.textContent=response.status===429?"Too many attempts. Try again later.":response.status===401?"Invalid email, password or verification code.":"Unable to sign in. Check local server configuration.";
   }catch{error.textContent="Cannot reach the EDGEOPS local server. Confirm Uvicorn is running."}
   finally{submit.disabled=false}
 });
});