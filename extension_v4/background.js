/**
 * Anticipy Bridge v4 — service worker (MV3).
 *
 * Architecture: this extension is a THIN SHELL. The daemon decides
 * everything. We open one chrome.runtime.connectNative port to
 * "com.anticipy.agent" and pump commands back and forth.
 *
 * Daemon → extension commands (`type` is the verb):
 *   navigate / click / type / extract / getDOMSnapshot / screenshot
 *   create_tab / close_tab / task_step / update_status / done / pong
 *
 * Extension → daemon messages:
 *   ready (after port open) / popup:start_task / popup:cancel_task
 *   result (one per command) / cancel / ping
 *
 * Key rule, from Omar: NEVER open about:blank as a seed tab. The first
 * navigate command from the daemon creates a real-URL tab — that tab
 * forms the Anticipy tab group; no orphan "outlook blank" detritus.
 */

const KEEPALIVE_MS = 25_000;
const RECONNECT_MS = 1500;
const NATIVE_HOST = "com.anticipy.agent";

let port = null;
let activeTask = null; // {taskId, summary, tabGroupId, tabIds: Set<number>}
let keepaliveTimer = null;
let portConnected = false;
// Last disconnect reason — surfaces in popup so the user can SEE the real
// Chrome native-messaging error (e.g. "Specified native messaging host
// not found" or "Native host has exited") instead of a generic "not
// connected" string.
let lastDisconnectReason = "";
let connectAttempts = 0;
let lastConnectAt = 0;

// ─── Native port plumbing ──────────────────────────────────────────────
function connectDaemon() {
  if (port) return;
  connectAttempts += 1;
  try {
    port = chrome.runtime.connectNative(NATIVE_HOST);
  } catch (err) {
    portConnected = false;
    lastDisconnectReason = String(err && err.message || err);
    chrome.storage.local.set({ lastDisconnectReason, connectAttempts });
    broadcastStatus("disconnected", lastDisconnectReason);
    setTimeout(connectDaemon, RECONNECT_MS);
    return;
  }
  portConnected = true;
  lastConnectAt = Date.now();
  port.onMessage.addListener(onDaemonMessage);
  port.onDisconnect.addListener(() => {
    const err = chrome.runtime.lastError;
    portConnected = false;
    port = null;
    stopKeepalive();
    lastDisconnectReason = err ? String(err.message || err) : "daemon closed";
    // Persist so the popup can read it even after the service worker recycles.
    chrome.storage.local.set({
      lastDisconnectReason,
      lastDisconnectAt: Date.now(),
      lastConnectAt,
      connectAttempts,
    });
    broadcastStatus("disconnected", lastDisconnectReason);
    setTimeout(connectDaemon, RECONNECT_MS);
  });
  chrome.storage.local.set({ lastDisconnectReason: "", lastConnectAt });
  sendToDaemon({ type: "ready", version: "4.0.0" });
  startKeepalive();
  broadcastStatus("connected");
}

function sendToDaemon(payload) {
  if (!port || !portConnected) return false;
  try {
    port.postMessage(payload);
    return true;
  } catch (_) {
    portConnected = false;
    return false;
  }
}

function startKeepalive() {
  stopKeepalive();
  keepaliveTimer = setInterval(() => {
    sendToDaemon({ type: "ping", t: Date.now() });
  }, KEEPALIVE_MS);
}

function stopKeepalive() {
  if (keepaliveTimer) clearInterval(keepaliveTimer);
  keepaliveTimer = null;
}

// ─── Command dispatch ──────────────────────────────────────────────────
async function onDaemonMessage(msg) {
  if (!msg || typeof msg !== "object") return;
  const cmdId = msg.cmdId;
  try {
    switch (msg.type) {
      case "navigate":
      case "click":
      case "type":
      case "extract":
      case "getDOMSnapshot":
        await ensureTaskFor(msg);
        await runInTab(msg, cmdId);
        break;
      case "screenshot":
        await ensureTaskFor(msg);
        await runScreenshot(msg, cmdId);
        break;
      case "create_tab":
        await ensureTaskFor(msg);
        await createTab(msg, cmdId);
        break;
      case "close_tab":
        await closeTab(msg, cmdId);
        break;
      case "task_step":
        if (activeTask) activeTask.currentStep = msg.step || msg.message || "";
        broadcastStatus("step");
        break;
      case "done":
        await finishTask(msg);
        break;
      case "update_status":
        broadcastStatus(msg.state || "info", msg.text || "");
        break;
      case "pong":
        break;
      default:
        if (cmdId) {
          sendToDaemon({ type: "result", cmdId, ok: false, error: `unknown command ${msg.type}` });
        }
    }
  } catch (err) {
    if (cmdId) {
      sendToDaemon({ type: "result", cmdId, ok: false, error: String(err && err.message || err) });
    }
  }
}

async function ensureTaskFor(msg) {
  if (activeTask && !activeTask.finished) return;
  activeTask = {
    taskId: msg.taskId || `t-${Date.now()}`,
    summary: msg.task || "(running)",
    tabGroupId: null,
    tabIds: new Set(),
    currentStep: "",
    finished: false,
  };
  broadcastStatus("running");
}

async function pickTab(msg) {
  if (Number.isInteger(msg.tabId)) return msg.tabId;
  if (activeTask && activeTask.tabIds.size > 0) {
    return [...activeTask.tabIds].at(-1);
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("no tab available");
  return tab.id;
}

// CRITICAL: per Omar's v4 spec — navigate MUST open a real URL. The
// daemon should ONLY send `navigate` for the first command; subsequent
// navigations re-use the existing tab via content.js's location.href.
// We DO support both modes for forward-compatibility, but the first
// navigate when the group is empty creates a new real-URL tab and
// groups it. NEVER about:blank.
async function runInTab(msg, cmdId) {
  if (msg.type === "navigate" && (!activeTask.tabIds.size || msg.newTab)) {
    // First nav or explicit new-tab: create directly. Skips the about:blank
    // injection problem from v3.
    const url = String(msg.url || "");
    if (!url) throw new Error("navigate: missing url");
    const tab = await chrome.tabs.create({ url, active: true });
    activeTask.tabIds.add(tab.id);
    await ensureGroupWith(tab.id);
    sendToDaemon({ type: "result", cmdId, ok: true, tabId: tab.id, data: { navigatedTo: url } });
    return;
  }

  const tabId = await pickTab(msg);
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content.js"],
  });
  const response = await chrome.tabs.sendMessage(tabId, { type: msg.type, payload: msg });
  sendToDaemon({
    type: "result",
    cmdId,
    ok: !!(response && response.ok),
    tabId,
    data: response && response.data,
    error: response && response.error,
  });
}

async function runScreenshot(msg, cmdId) {
  const tabId = await pickTab(msg);
  const tab = await chrome.tabs.get(tabId);
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
  sendToDaemon({ type: "result", cmdId, ok: true, tabId, data: { dataUrl } });
}

async function createTab(msg, cmdId) {
  const url = String(msg.url || "");
  if (!url) {
    // Refuse to create blank tabs — that's the v3 bug.
    sendToDaemon({ type: "result", cmdId, ok: false, error: "create_tab requires url" });
    return;
  }
  const tab = await chrome.tabs.create({ url, active: true });
  activeTask.tabIds.add(tab.id);
  await ensureGroupWith(tab.id);
  sendToDaemon({ type: "result", cmdId, ok: true, tabId: tab.id });
}

async function closeTab(msg, cmdId) {
  if (msg.tabId) {
    try { await chrome.tabs.remove(msg.tabId); } catch (_) {}
    if (activeTask) activeTask.tabIds.delete(msg.tabId);
  }
  sendToDaemon({ type: "result", cmdId, ok: true });
}

async function ensureGroupWith(tabId) {
  if (!activeTask) return;
  try {
    if (activeTask.tabGroupId == null) {
      const groupId = await chrome.tabs.group({ tabIds: [tabId] });
      await chrome.tabGroups.update(groupId, { title: "Anticipy", color: "blue" });
      activeTask.tabGroupId = groupId;
    } else {
      await chrome.tabs.group({ groupId: activeTask.tabGroupId, tabIds: [tabId] });
    }
  } catch (_) {
    // Group may have been closed by the user — leave the tab ungrouped.
  }
}

async function finishTask(msg) {
  if (activeTask) {
    activeTask.finished = true;
    activeTask.result = msg.summary || msg.message || "";
  }
  broadcastStatus("done", msg.summary || msg.message || "");
}

// ─── Popup ↔ background ────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case "popup:start_task": {
          if (activeTask && !activeTask.finished) {
            sendResponse({ ok: false, error: "task already running" });
            return;
          }
          if (!portConnected) connectDaemon();
          const taskId = `t-${Date.now()}`;
          activeTask = {
            taskId,
            summary: msg.task,
            tabGroupId: null,
            tabIds: new Set(),
            currentStep: "",
            finished: false,
          };
          const ok = sendToDaemon({ type: "task_start", taskId, task: msg.task });
          if (!ok) {
            sendResponse({ ok: false, error: "daemon not connected" });
            return;
          }
          sendResponse({ ok: true, taskId });
          broadcastStatus("running");
          break;
        }
        case "popup:cancel_task": {
          sendToDaemon({ type: "cancel", taskId: activeTask && activeTask.taskId });
          if (activeTask) {
            const ids = [...activeTask.tabIds];
            for (const id of ids) {
              try { await chrome.tabs.remove(id); } catch (_) {}
            }
            activeTask = null;
          }
          broadcastStatus("idle");
          sendResponse({ ok: true });
          break;
        }
        case "popup:get_status": {
          sendResponse({
            ok: true,
            connected: portConnected,
            lastDisconnectReason,
            connectAttempts,
            lastConnectAt,
            activeTask: activeTask ? {
              taskId: activeTask.taskId,
              summary: activeTask.summary,
              currentStep: activeTask.currentStep,
              finished: activeTask.finished,
              result: activeTask.result || "",
            } : null,
          });
          break;
        }
        case "popup:reconnect": {
          connectDaemon();
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
  return true;
});

function broadcastStatus(kind, detail) {
  try { chrome.runtime.sendMessage({ type: "bg:status", kind, detail }); } catch (_) {}
}

chrome.tabs.onRemoved.addListener((tabId) => {
  if (!activeTask) return;
  activeTask.tabIds.delete(tabId);
  if (activeTask.tabIds.size === 0 && !activeTask.finished) {
    sendToDaemon({ type: "cancel", taskId: activeTask.taskId, reason: "tabs_closed" });
    activeTask = null;
    broadcastStatus("idle");
  }
});

chrome.runtime.onStartup.addListener(() => connectDaemon());
chrome.runtime.onInstalled.addListener(() => connectDaemon());
connectDaemon();

// Test hook (exported only when test env sets this flag before importing)
if (typeof globalThis !== "undefined" && globalThis.__ANTICIPY_V4_TEST__) {
  globalThis.__bridgeV4 = {
    onDaemonMessage,
    runInTab,
    pickTab,
    getActiveTask: () => activeTask,
    setActiveTask: (t) => { activeTask = t; },
    setPort: (mock) => { port = mock; portConnected = !!mock; },
  };
}
