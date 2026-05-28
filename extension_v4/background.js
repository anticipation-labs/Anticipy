/**
 * Anticipy Bridge v4 — service worker (MV3).
 *
 * Architecture: this extension is a THIN SHELL. The daemon decides
 * everything. We open one chrome.runtime.connectNative port to
 * "com.anticipy.agent" and pump commands back and forth.
 *
 * Daemon → extension commands (`type` is the verb):
 *   navigate / click / type / key / read / extract / getDOMSnapshot / screenshot
 *   list_tabs / close_tabs_matching / create_tab / close_tab / task_step
 *   update_status / done / pong
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
const tabsClosingByAnticipy = new Set();
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
      case "key":
      case "read":
      case "extract":
      case "getDOMSnapshot":
        await ensureTaskFor(msg);
        await runInTab(msg, cmdId);
        break;
      case "screenshot":
        await ensureTaskFor(msg);
        await runScreenshot(msg, cmdId);
        break;
      case "list_tabs":
        await listTabs(msg, cmdId);
        break;
      case "close_tabs_matching":
        await closeTabsMatching(msg, cmdId);
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
  if (msg.urlPrefix) {
    const prefix = String(msg.urlPrefix);
    const tabs = await chrome.tabs.query({});
    const tab = tabs.find((t) => typeof t.url === "string" && t.url.startsWith(prefix));
    if (!tab || !tab.id) throw new Error(`no tab matching urlPrefix: ${prefix}`);
    try {
      await chrome.windows.update(tab.windowId, { focused: true });
      await chrome.tabs.update(tab.id, { active: true });
    } catch (_) {}
    return tab.id;
  }
  if (msg.useActiveTab) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error("no active tab available");
    return tab.id;
  }
  if (activeTask && activeTask.tabIds.size > 0) {
    return [...activeTask.tabIds].at(-1);
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("no tab available");
  return tab.id;
}

function installContentScriptFallback(loadError) {
  if (window.__anticipyBridgeV4ContentLoaded) {
    return {
      alreadyLoaded: true,
      fallback: true,
      loadError: String(loadError || ""),
    };
  }
  window.__anticipyBridgeV4ContentLoaded = true;
  window.__anticipy_ext_installed__ = true;

  const MAX_TEXT_LEN = 200_000;

  function $(sel) {
    try { return document.querySelector(sel); } catch (_) { return null; }
  }

  function nodeOuter(node, limit = MAX_TEXT_LEN) {
    if (!node) return "";
    const html = node.outerHTML || "";
    return html.length > limit ? html.slice(0, limit) : html;
  }

  function visibleText(node, limit = MAX_TEXT_LEN) {
    if (!node) return "";
    const text = (node.innerText || node.textContent || "").trim();
    return text.length > limit ? text.slice(0, limit) : text;
  }

  async function actionNavigate(p) {
    if (!p.url) throw new Error("navigate: missing url");
    window.location.href = p.url;
    return { navigatedTo: p.url };
  }

  async function actionClick(p) {
    const el = $(p.selector);
    if (!el) throw new Error(`click: selector not found: ${p.selector}`);
    el.scrollIntoView({ block: "center", inline: "center" });
    el.click();
    return { clicked: p.selector };
  }

  async function actionType(p) {
    const el = $(p.selector);
    if (!el) throw new Error(`type: selector not found: ${p.selector}`);
    el.focus();
    const text = p.text == null ? "" : String(p.text);
    const shouldPreserveValue = p.submit && text === "";
    if (!shouldPreserveValue) {
      const proto = el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) setter.call(el, text); else el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (p.submit) {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", bubbles: true }));
    }
    return {
      typed: shouldPreserveValue ? 0 : text.length,
      selector: p.selector,
      submitted: Boolean(p.submit),
      preservedValue: shouldPreserveValue,
    };
  }

  async function actionKey(p) {
    const key = String(p.key || "Enter");
    const selector = p.selector || "";
    const el = selector ? $(selector) : document.activeElement;
    if (!el) throw new Error(`key: selector not found: ${selector}`);
    if (typeof el.focus === "function") el.focus();
    const modifiers = Array.isArray(p.modifiers) ? p.modifiers.map(String) : [];
    const eventInit = {
      key,
      code: String(p.code || (key === "Enter" ? "Enter" : key)),
      bubbles: true,
      cancelable: true,
      altKey: modifiers.includes("Alt"),
      ctrlKey: modifiers.includes("Control") || modifiers.includes("Ctrl"),
      metaKey: modifiers.includes("Meta") || modifiers.includes("Command"),
      shiftKey: modifiers.includes("Shift"),
    };
    el.dispatchEvent(new KeyboardEvent("keydown", eventInit));
    el.dispatchEvent(new KeyboardEvent("keyup", eventInit));
    return {
      key,
      selector,
      activeTag: document.activeElement && document.activeElement.tagName,
    };
  }

  async function actionExtract(p) {
    const sel = p.selector || "body";
    const el = $(sel);
    if (!el) throw new Error(`extract: selector not found: ${sel}`);
    return {
      selector: sel,
      text: visibleText(el),
      html: p.includeHtml ? nodeOuter(el) : undefined,
    };
  }

  async function actionGetDOMSnapshot(p) {
    const root = p.selector ? $(p.selector) : document.documentElement;
    if (!root) throw new Error("getDOMSnapshot: root not found");
    return {
      url: location.href,
      title: document.title,
      html: nodeOuter(root, p.limit || MAX_TEXT_LEN),
    };
  }

  const handlers = {
    navigate: actionNavigate,
    click: actionClick,
    type: actionType,
    key: actionKey,
    read: actionExtract,
    extract: actionExtract,
    getDOMSnapshot: actionGetDOMSnapshot,
  };

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    const fn = handlers[msg.type];
    if (!fn) {
      sendResponse({ ok: false, error: `unknown content action ${msg.type}` });
      return false;
    }
    Promise.resolve()
      .then(() => fn(msg.payload || {}))
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: String(err && err.message || err) }));
    return true;
  });

  try {
    window.postMessage({ type: "anticipy:extension_present", version: "4.0.0" }, "*");
  } catch (_) {}

  return {
    alreadyLoaded: false,
    fallback: true,
    loadError: String(loadError || ""),
  };
}

async function ensureContentScript(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
    return { fallback: false };
  } catch (err) {
    const loadError = String(err && err.message || err);
    await chrome.scripting.executeScript({
      target: { tabId },
      func: installContentScriptFallback,
      args: [loadError],
    });
    return { fallback: true, loadError };
  }
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
  await ensureContentScript(tabId);
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
  // Native messaging frames from the extension to the host are capped at
  // 1 MiB. Full-size PNG screenshots regularly exceed that on modern
  // displays, which corrupts the protocol stream before the daemon can
  // record a surface receipt. JPEG is sufficient for proof screenshots
  // and keeps the frame bounded.
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: "jpeg",
    quality: 45,
  });
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

function tabReceipt(t) {
  return {
    id: t.id,
    title: t.title || "",
    url: t.url || "",
    active: Boolean(t.active),
    windowId: t.windowId,
  };
}

function tabMatches(tab, msg) {
  const url = String(tab.url || "");
  const title = String(tab.title || "");
  const urlPrefix = String(msg.urlPrefix || msg.url_prefix || "");
  const titleIncludes = String(msg.titleIncludes || msg.title_includes || "");
  const urlIncludes = String(msg.urlIncludes || msg.url_includes || "");
  if (urlPrefix && !url.startsWith(urlPrefix)) return false;
  const hasNeedle = Boolean(titleIncludes || urlIncludes);
  if (!hasNeedle) return Boolean(urlPrefix);
  const urlMatch = Boolean(
    urlIncludes && url.toLowerCase().includes(urlIncludes.toLowerCase())
  );
  const titleMatch = Boolean(
    titleIncludes && title.toLowerCase().includes(titleIncludes.toLowerCase())
  );
  return urlMatch || titleMatch;
}

async function listTabs(msg, cmdId) {
  const tabs = await chrome.tabs.query({});
  const data = {
    tabs: tabs.map(tabReceipt),
    count: tabs.length,
  };
  sendToDaemon({ type: "result", cmdId, ok: true, data });
}

async function closeTabsMatching(msg, cmdId) {
  const maxClose = Math.max(0, Math.min(Number(msg.maxClose || msg.max_close || 10), 50));
  const tabs = await chrome.tabs.query({});
  const matched = tabs.filter((tab) => tabMatches(tab, msg));
  const closable = matched
    .filter((tab) => Number.isInteger(tab.id))
    .slice(0, maxClose);
  const closed = [];
  for (const tab of closable) {
    try {
      tabsClosingByAnticipy.add(tab.id);
      if (activeTask) activeTask.tabIds.delete(tab.id);
      await chrome.tabs.remove(tab.id);
      closed.push(tabReceipt(tab));
    } catch (_) {}
  }
  if (activeTask && activeTask.tabIds.size === 0) {
    activeTask = null;
    broadcastStatus("idle");
  }
  sendToDaemon({
    type: "result",
    cmdId,
    ok: true,
    data: {
      matched: matched.map(tabReceipt),
      closed,
      matchedCount: matched.length,
      closedCount: closed.length,
      maxClose,
    },
  });
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
  if (tabsClosingByAnticipy.has(tabId)) {
    tabsClosingByAnticipy.delete(tabId);
    return;
  }
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
    ensureContentScript,
    installContentScriptFallback,
    listTabs,
    closeTabsMatching,
    pickTab,
    getActiveTask: () => activeTask,
    setActiveTask: (t) => { activeTask = t; },
    setPort: (mock) => { port = mock; portConnected = !!mock; },
  };
}
