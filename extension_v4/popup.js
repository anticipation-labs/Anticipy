/**
 * Anticipy v4 popup.
 *
 * No auth flow — the daemon owns API keys, supabase auth, etc. The
 * popup just shows daemon connection state and lets the user send /
 * cancel tasks.
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
  await chrome.runtime.sendMessage({ type: "popup:reconnect" });
  setTimeout(refresh, 600);
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "bg:status") refresh();
});

document.addEventListener("DOMContentLoaded", refresh);
