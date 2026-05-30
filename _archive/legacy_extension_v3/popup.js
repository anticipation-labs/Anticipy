/**
 * Anticipy Bridge — popup script.
 *
 * Three responsibilities:
 *   1. Auth: POST /api/extension/auth with the code → store {userId, code, serverUrl}.
 *   2. Idle: collect a plain-English task and send to background → server.
 *   3. Active: show current step, expose a big red Cancel button.
 *
 * No LLM calls, no API keys. The server validates the code and holds keys.
 */
const DEFAULT_AUTH_URL = "https://anticipy.ai/api/extension/auth";
const DEFAULT_WS_URL = "wss://anticipy-production.up.railway.app/ws/agent";

const $ = (id) => document.getElementById(id);

const panels = {
  auth: $("auth-panel"),
  idle: $("idle-panel"),
  active: $("active-panel"),
  done: $("done-panel"),
};
const dot = $("status-dot");

function showPanel(name) {
  for (const [n, el] of Object.entries(panels)) el.hidden = (n !== name);
}

function setDot(state, title) {
  dot.classList.remove("connected", "disconnected", "running");
  dot.classList.add(state);
  if (title) dot.title = title;
}

async function getStored() {
  return chrome.storage.local.get(["userId", "code", "serverUrl", "authUrl"]);
}

async function setStored(obj) {
  return chrome.storage.local.set(obj);
}

async function authenticate(code, serverUrl) {
  const stored = await getStored();
  const authUrl = stored.authUrl || DEFAULT_AUTH_URL;
  const resp = await fetch(authUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  if (!resp.ok) {
    let msg = "Invalid access code";
    try { const j = await resp.json(); if (j && j.error) msg = j.error; } catch (_) {}
    throw new Error(msg);
  }
  const data = await resp.json();
  if (!data.userId) throw new Error("Server did not return a userId");
  await setStored({
    userId: String(data.userId),
    code,
    serverUrl: serverUrl || DEFAULT_WS_URL,
  });
  // Tell background to (re)connect.
  await chrome.runtime.sendMessage({ type: "popup:auth_done" });
}

async function refresh() {
  const stored = await getStored();
  if (!stored.userId || !stored.code) {
    showPanel("auth");
    setDot("disconnected", "not signed in");
    $("server-input").value = stored.serverUrl || "";
    return;
  }
  // Ask background for current status / active task.
  let status;
  try {
    status = await chrome.runtime.sendMessage({ type: "popup:get_status" });
  } catch (_) {
    status = { ok: true, connected: false, activeTask: null };
  }
  setDot(status.connected ? "connected" : "disconnected",
         status.connected ? "connected" : "disconnected");

  const task = status.activeTask;
  if (task && task.finished) {
    $("done-summary").textContent = task.result || task.summary || "";
    showPanel("done");
  } else if (task) {
    $("task-summary").textContent = task.summary || "";
    $("task-step").textContent = task.currentStep || "starting…";
    showPanel("active");
  } else {
    showPanel("idle");
  }
}

// ─── Wiring ──────────────────────────────────────────────────────────────
$("auth-btn").addEventListener("click", async () => {
  const code = $("code-input").value.trim();
  const serverUrl = $("server-input").value.trim();
  const errEl = $("auth-error");
  errEl.hidden = true;
  if (!code) { errEl.textContent = "Enter your access code"; errEl.hidden = false; return; }
  $("auth-btn").disabled = true;
  try {
    await authenticate(code, serverUrl);
    await refresh();
  } catch (err) {
    errEl.textContent = err.message || "Auth failed";
    errEl.hidden = false;
  } finally {
    $("auth-btn").disabled = false;
  }
});

$("send-btn").addEventListener("click", async () => {
  const task = $("task-input").value.trim();
  if (!task) return;
  $("send-btn").disabled = true;
  try {
    const res = await chrome.runtime.sendMessage({ type: "popup:start_task", task });
    if (!res || !res.ok) throw new Error(res && res.error || "Could not start task");
    $("task-input").value = "";
    await refresh();
  } catch (err) {
    alert(err.message);
  } finally {
    $("send-btn").disabled = false;
  }
});

$("cancel-btn").addEventListener("click", async () => {
  $("cancel-btn").disabled = true;
  try {
    await chrome.runtime.sendMessage({ type: "popup:cancel_task" });
    await refresh();
  } finally {
    $("cancel-btn").disabled = false;
  }
});

$("dismiss-btn").addEventListener("click", async () => {
  // Clear "done" state by clearing active task in background — easiest: cancel.
  await chrome.runtime.sendMessage({ type: "popup:cancel_task" });
  await refresh();
});

$("signout-btn").addEventListener("click", async () => {
  await chrome.storage.local.remove(["userId", "code"]);
  await refresh();
});

// Listen for status pings from background.
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "bg:status") refresh();
});

document.addEventListener("DOMContentLoaded", refresh);
