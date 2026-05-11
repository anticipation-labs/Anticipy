/**
 * Anticipy Bridge — service worker (MV3).
 *
 * THIN RELAY. No agent logic, no LLM calls, no rate-limiting,
 * no provider rotation. The server holds all of that.
 *
 * Responsibilities:
 *   1. Maintain a WebSocket to the engine.
 *   2. On task start, open an "Anticipy" Chrome tab group.
 *   3. Forward server commands (navigate/click/type/extract/screenshot/...)
 *      to the right tab's content script and pipe the response back.
 *   4. Keepalive ping every 25s to defeat MV3 service-worker eviction.
 *   5. Reconnect with exponential backoff if the socket drops.
 */
const DEFAULT_SERVER_URL = "wss://anticipy-production.up.railway.app/ws/agent";
const KEEPALIVE_MS = 25_000;
const MAX_BACKOFF_MS = 30_000;

// ─── Runtime state ─────────────────────────────────────────────────────────
let ws = null;
let wsBackoff = 1000;
let keepaliveTimer = null;
let activeTask = null; // {taskId, summary, tabGroupId, tabIds: Set<number>, currentStep}
let pendingReconnect = null;

// ─── Storage helpers ───────────────────────────────────────────────────────
async function getConfig() {
  const cfg = await chrome.storage.local.get(["userId", "code", "serverUrl"]);
  return {
    userId: cfg.userId || null,
    code: cfg.code || null,
    serverUrl: cfg.serverUrl || DEFAULT_SERVER_URL,
  };
}

// ─── WebSocket lifecycle ───────────────────────────────────────────────────
async function connect() {
  const { userId, code, serverUrl } = await getConfig();
  if (!userId || !code) {
    // No auth yet — wait until the popup completes /api/extension/auth.
    return;
  }
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  const url = `${serverUrl}?userId=${encodeURIComponent(userId)}&code=${encodeURIComponent(code)}`;
  try {
    ws = new WebSocket(url);
  } catch (e) {
    scheduleReconnect();
    return;
  }
  ws.addEventListener("open", () => {
    wsBackoff = 1000;
    startKeepalive();
    broadcastStatus("connected");
  });
  ws.addEventListener("message", onServerMessage);
  ws.addEventListener("close", () => {
    stopKeepalive();
    broadcastStatus("disconnected");
    scheduleReconnect();
  });
  ws.addEventListener("error", () => {
    // close handler will fire next; scheduleReconnect there.
  });
}

function scheduleReconnect() {
  if (pendingReconnect) return;
  const delay = Math.min(wsBackoff, MAX_BACKOFF_MS);
  pendingReconnect = setTimeout(() => {
    pendingReconnect = null;
    wsBackoff = Math.min(wsBackoff * 2, MAX_BACKOFF_MS);
    connect();
  }, delay);
}

function startKeepalive() {
  stopKeepalive();
  keepaliveTimer = setInterval(() => {
    sendToServer({ type: "ping", t: Date.now() });
  }, KEEPALIVE_MS);
}

function stopKeepalive() {
  if (keepaliveTimer) {
    clearInterval(keepaliveTimer);
    keepaliveTimer = null;
  }
}

function sendToServer(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify(payload));
      return true;
    } catch (_) {
      return false;
    }
  }
  return false;
}

// ─── Server → extension command dispatch ──────────────────────────────────
//
// v3 additions over v2:
//   - begin_remote_task: server initiates a task without popup interaction.
//     Creates activeTask + tab group so subsequent commands have context.
//   - show_dialog: server asks the user a question (proactive "first time
//     how do you do this" flow). Popup renders, response goes back.
//   - update_status: server-pushed connection/idle text shown in popup.
//   - generic auto-bootstrap: if a tab-touching command arrives with no
//     activeTask, we silently create one (handles server-initiated work
//     when the explicit begin_remote_task wasn't sent).
async function ensureActiveTaskForRemote(taskId, summary) {
  if (activeTask && !activeTask.finished) return;
  activeTask = {
    taskId: taskId || `remote-${Date.now()}`,
    summary: summary || "Remote task",
    tabGroupId: null,
    seedTabId: null,
    tabIds: new Set(),
    currentStep: "",
    finished: false,
    result: "",
    remote: true,
  };
  await ensureTabGroup();
  broadcastStatus("running");
}

async function onServerMessage(evt) {
  let msg;
  try {
    msg = JSON.parse(evt.data);
  } catch (_) {
    return;
  }
  const cmd = msg.type;
  const cmdId = msg.cmdId; // server's correlation id
  try {
    switch (cmd) {
      case "begin_remote_task":
        await ensureActiveTaskForRemote(msg.taskId, msg.task);
        sendToServer({ type: "result", cmdId, ok: true, tabGroupId: activeTask.tabGroupId, taskId: activeTask.taskId });
        break;
      case "show_dialog": {
        // Server proactive-ask. Popup will render and POST back. For now we
        // ack receipt + stash; popup picks it up via chrome.storage.local.
        try {
          await chrome.storage.local.set({ pendingDialog: msg });
        } catch (_) {}
        broadcastStatus("dialog");
        sendToServer({ type: "result", cmdId, ok: true });
        break;
      }
      case "update_status":
        broadcastStatus(msg.state || "info", msg.text || "");
        sendToServer({ type: "result", cmdId, ok: true });
        break;
      case "navigate":
      case "click":
      case "type":
      case "extract":
      case "getDOMSnapshot":
        // Auto-bootstrap activeTask if absent — handles servers that skip
        // the begin_remote_task explicit handshake.
        if (!activeTask || activeTask.finished) {
          await ensureActiveTaskForRemote(msg.taskId, "(remote task)");
        }
        await runInTab(msg, cmdId);
        break;
      case "screenshot":
        if (!activeTask || activeTask.finished) {
          await ensureActiveTaskForRemote(msg.taskId, "(remote task)");
        }
        await runScreenshot(msg, cmdId);
        break;
      case "create_tab":
        if (!activeTask || activeTask.finished) {
          await ensureActiveTaskForRemote(msg.taskId, "(remote task)");
        }
        await createTab(msg, cmdId);
        break;
      case "close_tab":
        await closeTab(msg, cmdId);
        break;
      case "done":
        await finishTask(msg);
        break;
      case "task_step":
        if (activeTask) activeTask.currentStep = msg.step || "";
        broadcastStatus("step");
        break;
      case "pong":
        // server keepalive ack; nothing to do.
        break;
      case "error":
        broadcastStatus("error", msg.message);
        break;
      default:
        // Unknown command type. Tell server so it can fail fast.
        sendToServer({ type: "error", cmdId, message: `unknown command ${cmd}` });
    }
  } catch (err) {
    sendToServer({ type: "result", cmdId, ok: false, error: String(err && err.message || err) });
  }
}

async function runInTab(msg, cmdId) {
  const tabId = await pickTab(msg);
  // Make sure content.js is injected (it is via manifest? no — we use programmatic injection
  // so we don't need <all_urls> as a content_scripts match).
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content.js"],
  });
  const response = await chrome.tabs.sendMessage(tabId, { type: msg.type, payload: msg });
  sendToServer({ type: "result", cmdId, ok: true, tabId, data: response });
}

async function runScreenshot(msg, cmdId) {
  // chrome.tabs.captureVisibleTab is window-level; need windowId of the active task tab.
  const tabId = await pickTab(msg);
  const tab = await chrome.tabs.get(tabId);
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
  sendToServer({ type: "result", cmdId, ok: true, tabId, data: { dataUrl } });
}

async function pickTab(msg) {
  if (msg.tabId && Number.isInteger(msg.tabId)) return msg.tabId;
  if (activeTask && activeTask.tabIds.size > 0) {
    // Prefer the most-recently-used tab in the group.
    return [...activeTask.tabIds].at(-1);
  }
  // Fallback: active tab in current window.
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("no tab available");
  return tab.id;
}

// ─── Tab / tab-group management ────────────────────────────────────────────
async function ensureTabGroup() {
  if (!activeTask) return null;
  if (activeTask.tabGroupId !== null && activeTask.tabGroupId !== undefined) {
    return activeTask.tabGroupId;
  }
  // Create a new tab to seed the group.
  const seed = await chrome.tabs.create({ url: "about:blank", active: true });
  activeTask.tabIds.add(seed.id);
  const groupId = await chrome.tabs.group({ tabIds: [seed.id] });
  await chrome.tabGroups.update(groupId, { title: "Anticipy", color: "blue" });
  activeTask.tabGroupId = groupId;
  activeTask.seedTabId = seed.id;
  return groupId;
}

async function createTab(msg, cmdId) {
  const groupId = await ensureTabGroup();
  const tab = await chrome.tabs.create({ url: msg.url || "about:blank", active: true });
  activeTask.tabIds.add(tab.id);
  if (groupId !== null && groupId !== undefined) {
    try {
      await chrome.tabs.group({ groupId, tabIds: [tab.id] });
    } catch (_) { /* group may have been closed */ }
  }
  sendToServer({ type: "result", cmdId, ok: true, tabId: tab.id });
}

async function closeTab(msg, cmdId) {
  const tabId = msg.tabId;
  if (tabId) {
    try { await chrome.tabs.remove(tabId); } catch (_) {}
    if (activeTask) activeTask.tabIds.delete(tabId);
  }
  sendToServer({ type: "result", cmdId, ok: true });
}

async function closeTaskGroup() {
  if (!activeTask) return;
  const ids = [...activeTask.tabIds];
  for (const id of ids) {
    try { await chrome.tabs.remove(id); } catch (_) {}
  }
  activeTask = null;
  broadcastStatus("idle");
}

async function finishTask(msg) {
  // Server says we're done. Don't auto-close the group — user may want to inspect results.
  if (activeTask) {
    activeTask.finished = true;
    activeTask.result = msg.summary || msg.result || "";
  }
  broadcastStatus("done", msg.summary || "");
}

// ─── Popup → background commands ──────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case "popup:start_task": {
          if (activeTask && !activeTask.finished) {
            sendResponse({ ok: false, error: "task already running" });
            return;
          }
          activeTask = {
            taskId: `t-${Date.now()}`,
            summary: msg.task,
            tabGroupId: null,
            seedTabId: null,
            tabIds: new Set(),
            currentStep: "",
            finished: false,
            result: "",
          };
          await ensureTabGroup();
          await connect();
          const sent = sendToServer({
            type: "task_start",
            taskId: activeTask.taskId,
            task: msg.task,
            tabGroupId: activeTask.tabGroupId,
          });
          if (!sent) {
            sendResponse({ ok: false, error: "not connected to server" });
            return;
          }
          sendResponse({ ok: true, taskId: activeTask.taskId });
          broadcastStatus("running");
          break;
        }
        case "popup:cancel_task": {
          sendToServer({ type: "cancel", taskId: activeTask?.taskId });
          await closeTaskGroup();
          sendResponse({ ok: true });
          break;
        }
        case "popup:get_status": {
          sendResponse({
            ok: true,
            connected: !!(ws && ws.readyState === WebSocket.OPEN),
            activeTask: activeTask
              ? {
                  taskId: activeTask.taskId,
                  summary: activeTask.summary,
                  currentStep: activeTask.currentStep,
                  finished: activeTask.finished,
                  result: activeTask.result,
                }
              : null,
          });
          break;
        }
        case "popup:auth_done": {
          // Popup just finished /api/extension/auth and stored credentials.
          await connect();
          sendResponse({ ok: true });
          break;
        }
        default:
          sendResponse({ ok: false, error: `unknown popup msg ${msg.type}` });
      }
    } catch (err) {
      sendResponse({ ok: false, error: String(err && err.message || err) });
    }
  })();
  return true; // keep sendResponse alive across the async work
});

function broadcastStatus(kind, detail) {
  // Send a runtime message; popup listens when open. No-op if no listener.
  try {
    chrome.runtime.sendMessage({ type: "bg:status", kind, detail });
  } catch (_) { /* popup not open */ }
}

// ─── Tab tracking — drop closed tabs from the active task ─────────────────
chrome.tabs.onRemoved.addListener((tabId) => {
  if (activeTask) {
    activeTask.tabIds.delete(tabId);
    if (activeTask.seedTabId === tabId && activeTask.tabIds.size === 0) {
      // user closed the whole group — treat as cancel.
      sendToServer({ type: "cancel", taskId: activeTask.taskId, reason: "tabs_closed" });
      activeTask = null;
      broadcastStatus("idle");
    }
  }
});

// ─── Boot ────────────────────────────────────────────────────────────────
chrome.runtime.onStartup.addListener(() => connect());
chrome.runtime.onInstalled.addListener(() => connect());
// Also try on first load of the SW.
connect();

// Export for test harness (Jest with jsdom + chrome mocks).
if (typeof globalThis !== "undefined" && globalThis.__ANTICIPY_BRIDGE_TEST__) {
  globalThis.__bridge = {
    onServerMessage,
    runInTab,
    runScreenshot,
    pickTab,
    sendToServer,
    getActiveTask: () => activeTask,
    setActiveTask: (t) => { activeTask = t; },
    setWs: (mock) => { ws = mock; },
  };
}
