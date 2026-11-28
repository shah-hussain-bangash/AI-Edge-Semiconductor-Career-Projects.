"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const status = document.getElementById("usb-status");
  const detail = document.getElementById("usb-detail");
  const labels = {
    disabled: "USB reader disabled", waiting: "Waiting for ESP32 heartbeat",
    receiving: "Receiving ESP32 heartbeat", stale: "Heartbeat stale",
    disconnected: "USB disconnected or port unavailable",
    dependency_missing: "USB dependency missing", stopped: "USB reader stopped"
  };
  let generation = 0;
  let expiry;
  let ended = false;
  const clear = (message) => {
    clearTimeout(expiry);
    status.textContent = message;
    detail.textContent = "No fresh heartbeat verified. Sensor telemetry is not verified.";
  };
  async function refresh() {
    if (ended) return;
    const current = ++generation;
    if (document.hidden) { clear("USB observation paused"); return; }
    const started = performance.now();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch("/api/usb/status", {credentials:"same-origin", cache:"no-store", signal:controller.signal});
      if (current !== generation || document.hidden) return;
      if (response.status === 401) { clear("Sign in to inspect USB"); return; }
      if (!response.ok) throw new Error("Unavailable");
      const data = await response.json();
      if (current !== generation || document.hidden) return;
      if (!Object.hasOwn(labels, data.state) || typeof data.heartbeat_fresh !== "boolean") throw new Error("Invalid status");
      const age = Number(data.age_seconds) + (performance.now() - started) / 1000;
      if (data.heartbeat_fresh && (data.state !== "receiving" || data.message !== "ESP32 is working!" || typeof data.age_seconds !== "number" || !Number.isFinite(age) || age < 0)) throw new Error("Invalid heartbeat");
      if (data.heartbeat_fresh && age >= 5) { clear("Heartbeat observation expired"); return; }
      clearTimeout(expiry);
      status.textContent = labels[data.state] || "USB status unknown";
      detail.textContent = data.heartbeat_fresh
        ? `${data.message} · ${data.port} · ${data.baud} baud · ${data.heartbeat_count} heartbeats. Sensor telemetry is not verified.`
        : "No fresh heartbeat verified. Sensor telemetry is not verified.";
      if (data.heartbeat_fresh) expiry = setTimeout(() => clear("Heartbeat observation expired"), Math.max(0, 5000 - age * 1000));
    } catch (_) { if (current === generation) clear("USB status unavailable"); }
    finally { clearTimeout(timeout); }
  }
  document.addEventListener("visibilitychange", () => { ++generation; clear("USB observation paused"); refresh(); });
  document.getElementById("logout")?.addEventListener("click", () => { ended = true; ++generation; clear("USB observation cleared"); });
  refresh();
  setInterval(refresh, 2000);
});
