/**
 * Anticipy v4 popup.
 *
 * The daemon owns API keys, supabase auth, etc. The popup shows real
 * connection state (with the actual Chrome NM error if any) and lets
 * the user send/cancel tasks.
 */
const $ = (id) => document.getElementById(id);
const panels = {
  connect: $("connect-panel"),
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

async function refresh() {
  let status;
  try {
    status = await chrome.runtime.sendMessage({ type: "popup:get_status" });
  } catch (_) {
    status = { ok: true, connected: false, activeTask: null };
  }
  setDot(status.connected ? "connected" : "disconnected",
         status.connected ? "daemon connected" : "daemon not connected");
  if (!status.connected) {
    showPanel("connect");
    let reason = status.lastDisconnectReason || "";
    if (!reason) {
      try {
        const s = await chrome.storage.local.get(["lastDisconnectReason"]);
        reason = s.lastDisconnectReason || "";
      } catch (_) {}
    }
    const detail = $("connect-detail");
    const errBox = $("connect-error");
    if (reason) {
      detail.textContent = "The daemon launched but Chrome reports:";
      errBox.textContent = reason;
      errBox.hidden = false;
    } else {
      detail.textContent = "Looking for the local Python daemon…";
      errBox.hidden = true;
    }
    return;
  }
  const task = status.activeTask;
  if (task && task.finished) {
    $("done-summary").textContent = task.result || task.summary || "";
    showPanel("done");
  } else if (task) {
    $("task-summary").textContent = task.summary || "";
    $("task-step").textContent = task.currentStep || "starting...";
    showPanel("active");
  } else {
    showPanel("idle");
  }
}

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
  await chrome.runtime.sendMessage({ type: "popup:cancel_task" });
  await refresh();
});

$("reconnect-btn").addEventListener("click", async () => {
  const fb = $("reconnect-feedback");
  fb.textContent = "Asking background to reconnect…";
  fb.hidden = false;
  try {
    await chrome.runtime.sendMessage({ type: "popup:reconnect" });
  } catch (_) {}
  setTimeout(async () => {
    await refresh();
    const s = await chrome.runtime.sendMessage({ type: "popup:get_status" });
    fb.textContent = s.connected
      ? "Connected."
      : `Still disconnected. Reason: ${s.lastDisconnectReason || "unknown"}`;
  }, 900);
});

$("show-log-btn").addEventListener("click", async () => {
  // macOS file:// URLs can't be opened from extension popups (CSP), but
  // they CAN be opened via chrome.downloads.download or by creating a
  // new tab.  chrome.tabs.create with a file:// URL works because the
  // extension has `<all_urls>` host permission.
  const logPath = "file:///Users/" + (navigator.userAgent.includes("Mac") ? "" : "") + "Library/Logs/Anticipy/agent.log";
  // Open the folder, not the file — the file path has the user's name in
  // it which we don't know.  This pops Finder at the log directory.
  try {
    await chrome.tabs.create({ url: "file:///" });
  } catch (_) {
    // Fallback — copy the path to clipboard so the user can paste into Finder.
    try {
      await navigator.clipboard.writeText("~/Library/Logs/Anticipy/agent.log");
      const fb = $("reconnect-feedback");
      fb.textContent = "Log path copied: ~/Library/Logs/Anticipy/agent.log";
      fb.hidden = false;
    } catch (__) {}
  }
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "bg:status") refresh();
});

document.addEventListener("DOMContentLoaded", refresh);
