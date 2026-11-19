/* EDGEOPS Architecture Explorer: read-only, static architecture documentation.
 * Facts describe proposed design, historical software-lab tests or local API demo;
 * never claim a deployed plant, physical connected hardware or model inference.
 */
"use strict";
const ARCH_COMPONENTS = Object.freeze({
  sensors:{
    title:"Sensors & Bench Rig",stage:"PLANNED",status:"planned",
    summary:"Proposed vibration, temperature and electrical measurements for a guarded low-voltage bench motor. Physical hardware has not been validated as connected.",
    tech:"ADXL345 accelerometer · DS18B20 · INA219 · 12 V motor",
    security:"Independent fuse, motor guard and human supervision. No remote actuation or safety-interlock claims.",
    failure:"Inspect sensor disconnection, calibration and implausible ranges before accepting readings; verification remains future work.",
    evidence:"Proposed bill of materials: 14 named items out of 30 planning slots. No electrical or machinery-safety approval.",
    decision:"Isolate physical experiments from the enterprise console. Do not energize a prototype without separately reviewed guarding, power and test procedures."
  },
  esp32:{
    title:"ESP32 Acquisition",stage:"PLANNED",status:"planned",
    summary:"Proposed microcontroller collects sensor samples and creates device-scoped telemetry envelopes, then publishes to a secure broker.",
    tech:"ESP32-WROOM-32 · embedded firmware · device identity · sampling and timestamps",
    security:"Plan unique credentials per board; avoid storing fleet secrets in the UI or committing them to Git.",
    failure:"Plan buffering, monotonic sequence numbers, bounded retry and explicit degraded-state reporting. Firmware has not been validated on the physical board.",
    evidence:"Design-stage hardware acquisition; local dashboard does not consume actual ESP32 packets.",
    decision:"Make acquisition deterministic, validate measurement provenance and isolate cloud dependencies from real-time measurement."
  },
  mqtt:{
    title:"MQTT / Mutual TLS",stage:"LAB TESTED",status:"lab",
    summary:"Secure message transport has software-laboratory verification for MQTT with mutual TLS, independent of physical sensor acquisition.",
    tech:"MQTT broker · TLS client certificates · topic policy · identity lifecycle",
    security:"Lab-tested certificate-based client authentication and policy boundaries. Production CA rotation and fleet enrollment remain open.",
    failure:"Broker restarts, unauthorized publishers, reconnect and message replay scenarios are security concerns. Do not claim guaranteed production delivery.",
    evidence:"EA-31 software-only MQTT mTLS integration evidence; broker test environment was stopped after verification.",
    decision:"Treat broker topics as an authorization boundary and authenticate workloads before decoding or persisting telemetry."
  },
  gateway:{
    title:"Edge API Gateway",stage:"LAB TESTED",status:"lab",
    summary:"A local gateway and FastAPI boundary validates incoming simulated telemetry and checks policy, payload and replay conditions.",
    tech:"Python · FastAPI · Uvicorn · validation contracts · loopback services",
    security:"Policy enforcement and request validation at the lab boundary; production API gateway controls are not deployed.",
    failure:"Reject malformed envelopes and duplicate/replayed events rather than silently accepting ambiguous device states.",
    evidence:"EA-31 loopback Uvicorn API exercised in independent local integration tests with simulated messages.",
    decision:"Separate transport trust from payload validity so a trusted certificate cannot bypass schema or sequence controls."
  },
  pipeline:{
    title:"Data Pipeline & Persistence",stage:"LAB TESTED",status:"lab",
    summary:"The laboratory persistence layer demonstrates durable local event handling concepts without asserting cloud replication or industrial service levels.",
    tech:"SQLite lab store · idempotency key · event provenance · restart/replay fixtures",
    security:"Persist data provenance and restrict access to telemetry and audit records. Enterprise database governance remains planned.",
    failure:"Lab tests address duplicate, replay and restart conditions. Durable production retry, distributed recovery and high availability remain unfinished.",
    evidence:"EA-30/EA-31 local database and replay test evidence; separate from the dashboard's authentication SQLite database.",
    decision:"Keep append-oriented audit evidence distinct from derived user-facing health indicators; do not overwrite the original source event."
  },
  ai:{
    title:"AI / Agentic Intelligence",stage:"NOT DEPLOYED",status:"blocked",
    summary:"Architecture placeholder for anomaly detection, maintenance recommendations, retrieval and accountable agent orchestration. No predictive model executes here.",
    tech:"Proposed anomaly model · feature quality checks · RAG knowledge layer · bounded agents",
    security:"Planned least-privilege tool access, evidence citation, model validation, human approvals and prompt-injection defenses.",
    failure:"Plan low-confidence abstention, drift monitoring, model rollback and explainable alerts. None are demonstrated as working production services.",
    evidence:"Current AI-insights cards are curated illustrative text, explicitly NOT inference output or calibrated probabilities.",
    decision:"Do not allow autonomous equipment commands. Require human review before presenting an advisory as an actionable maintenance decision."
  },
  api:{
    title:"Enterprise API & Access",stage:"LOCAL DEMO",status:"demo",
    summary:"Authenticated local FastAPI app exposes read-only hardware catalog, session/account endpoints and demonstration alert/audit functionality.",
    tech:"FastAPI · opaque server-side sessions · PBKDF2 · CSRF · SQLite",
    security:"Local login, hashed session tokens and CSRF tested. Production SSO, scale-out throttling, key management and penetration testing remain open.",
    failure:"Authentication denial and logout-revocation are covered by API tests. Production monitoring/availability and multi-instance behavior unproven.",
    evidence:"12 dashboard backend tests recently passed on the user's Windows environment; no deployed enterprise API integration.",
    decision:"Keep the local executive interface read-only for equipment and use explicit role-checked business APIs for any future state mutations."
  },
  dashboard:{
    title:"Human Operations Console",stage:"LOCAL DEMO",status:"demo",
    summary:"Interactive authenticated dashboard lets reviewers explore simulated assets, telemetry charts, alerts, security controls and the architecture itself.",
    tech:"HTML5 · responsive CSS · vanilla JavaScript · SVG · same-origin FastAPI",
    security:"Session required for the console; no physical actuator controls; synthetic provenance disclosed on every relevant section.",
    failure:"When API inventory is unavailable, display an error rather than fictitious connected devices. Visual QA and accessibility audits remain incomplete.",
    evidence:"13 structural and 12 API tests locally reported passed before this architecture explorer addition. Browser-based acceptance still required.",
    decision:"Provide a readable, accessible executive story while keeping lab achievements, product demonstrations and not-yet-implemented systems unambiguously separate."
  }
});
const ARCH_MODES = Object.freeze({
  overview:{title:"8 SYSTEM STAGES",description:"Select a stage to review purpose, technology, evidence and the architectural decision."},
  security:{title:"TRUST BOUNDARIES",description:"Inspect device identity, validation controls and human approval gates."},
  failure:{title:"FAILURE PATHS",description:"Inspect resilience choices, remaining gaps and safe degradation principles."}
});
function archSetText(id,value){const el=document.getElementById(id);if(el)el.textContent=value;}
function archSelect(id){
  const entry=ARCH_COMPONENTS[id];if(!entry)return;
  document.querySelectorAll("[data-arch-node]").forEach(button=>{
    const selected=button.dataset.archNode===id;
    button.classList.toggle("active",selected);
    button.setAttribute("aria-pressed",String(selected));
  });
  archSetText("arch-detail-title",entry.title);
  archSetText("arch-detail-summary",entry.summary);
  archSetText("arch-detail-tech",entry.tech);
  archSetText("arch-detail-security",entry.security);
  archSetText("arch-detail-failure",entry.failure);
  archSetText("arch-detail-evidence",entry.evidence);
  archSetText("arch-detail-decision",entry.decision);
  const badge=document.getElementById("arch-detail-badge");
  if(badge){badge.textContent=entry.stage;badge.dataset.status=entry.status;}
}
function archMode(mode){
  const spec=ARCH_MODES[mode];if(!spec)return;
  document.querySelectorAll("[data-arch-mode]").forEach(button=>{
    const active=button.dataset.archMode===mode;
    button.classList.toggle("active",active);
    button.setAttribute("aria-pressed",String(active));
  });
  const pipeline=document.getElementById("arch-pipeline");
  if(pipeline)pipeline.dataset.mode=mode;
  archSetText("arch-map-status",spec.title);
  const help=document.getElementById("arch-view-help");
  if(help)help.textContent=spec.description;
}
document.addEventListener("DOMContentLoaded",()=>{
  const map=document.getElementById("arch-pipeline");
  if(!map)return;
  map.addEventListener("click",event=>{
    const button=event.target.closest("button[data-arch-node]");
    if(button&&map.contains(button))archSelect(button.dataset.archNode);
  });
  document.querySelectorAll("[data-arch-mode]").forEach(button=>button.addEventListener("click",()=>archMode(button.dataset.archMode)));
  archSelect("sensors");
  archMode("overview");
});