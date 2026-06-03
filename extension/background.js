// Anticipy browser hand — MV3 service worker.
// Connects to the local engine over an AUTHENTICATED WebSocket, stays alive
// (20s pings + alarm backstop), auto-reconnects, and keeps ALL state in
// chrome.storage (SW globals are lost when Chrome idle-kills the worker ~30s).
// Browse-job execution (page read / input / screenshot) is wired in piece 3.

const ENGINE_HTTP = "http://127.0.0.1:8787";
const ENGINE_WS = "ws://127.0.0.1:8787/ws/extension";
const PING_MS = 20000;

let ws = null;
let pingTimer = null;
let reconnectTimer = null;

async function setState(patch) {
  const cur = (await chrome.storage.local.get("anticipy")).anticipy || {};
  await chrome.storage.local.set({ anticipy: { ...cur, ...patch } });
}
async function getState() {
  return (await chrome.storage.local.get("anticipy")).anticipy || { connected: false };
}

async function fetchToken() {
  const r = await fetch(ENGINE_HTTP + "/ws/token");
  if (!r.ok) throw new Error("token fetch failed: " + r.status);
  return (await r.json()).token;
}

async function connect() {
  try {
    const token = await fetchToken();
    ws = new WebSocket(ENGINE_WS + "?token=" + encodeURIComponent(token));
    ws.onopen = async () => {
      await setState({ connected: true, lastConnect: Date.now(), error: null });
      startPing();
      console.log("[anticipy] engine link open");
    };
    ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
    ws.onclose = async () => {
      await setState({ connected: false });
      stopPing();
      scheduleReconnect();
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  } catch (e) {
    await setState({ connected: false, error: String(e) });
    scheduleReconnect();
  }
}

function startPing() {
  stopPing();
  pingTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
  }, PING_MS);
}
function stopPing() { if (pingTimer) { clearInterval(pingTimer); pingTimer = null; } }

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, 2000);
}

async function handleMessage(msg) {
  if (msg.type === "pong") return;
  if (msg.type === "reload") { console.log("[anticipy] hot reload"); chrome.runtime.reload(); return; }
  if (msg.type === "browse_job") {
    const result = await executeBrowseJob(msg);
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(result));
  }
}

// Real execution: open the target page in a controlled tab, read it
// (DOM + accessibility text), capture a compressed screenshot for the brain's
// vision verify, detect login/verification walls, and clean up. Never fakes
// success; surfaces needs_human on a wall or error.
async function executeBrowseJob(msg) {
  const args = msg.args || {};
  const url = args.url || extractUrl(args.task);
  if (!url) {
    return result(msg, "needs_human", null, { reason: "no url/task to browse" });
  }
  try {
    const tab = await openInGroup(url);    // ALWAYS operate inside the "Anticipy" tab group
    const groupId = (await getState()).groupId;
    await waitForComplete(tab.id, 25000);  // hard sites can be slow
    await sleep(900);                      // let JS-heavy pages paint/settle

    const [{ result: page }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        title: document.title,
        url: location.href,
        text: (document.body ? document.body.innerText : "").slice(0, 1800),
      }),
    });

    const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 40 });
    const urlLc = (page.url || "").toLowerCase();
    const textLc = (page.text || "").toLowerCase();
    const captcha = /captcha|unusual traffic|are you a (robot|human)|verify you('| a)re human|press & hold/.test(textLc);
    const authUrl = /\/login|\/signin|\/sign-in|\/onboarding|\/auth\b|accounts\.|mode=login/.test(urlLc);
    const authText = /continue with (phone|apple|google|email)|sign in to|log ?in to|create (an )?account|enter your password|forgot password/.test(textLc);
    if (captcha || (authUrl && authText)) {
      return result(msg, "needs_human",
        { screenshot, url: page.url, title: page.title },
        { reason: "login/verification wall — handed back to you", url: page.url, group_id: groupId });
    }
    return result(msg, "success",
      { screenshot, url: page.url, title: page.title },
      { title: page.title, text: (page.text || "").slice(0, 400), group_id: groupId });
  } catch (e) {
    return result(msg, "needs_human", null, { reason: "browser error: " + String(e) });
  }
}

// --- the "Anticipy" tab group: always operate here, reusing one working tab ---
async function openInGroup(url) {
  let tab = await getWorkingTab();
  if (tab) {
    tab = await chrome.tabs.update(tab.id, { url, active: true });
  } else {
    tab = await chrome.tabs.create({ url, active: true });
    await setState({ workTabId: tab.id });
  }
  await ensureGroup(tab.id);
  return await chrome.tabs.get(tab.id);
}
async function getWorkingTab() {
  const st = await getState();
  if (st.workTabId != null) {
    try { return await chrome.tabs.get(st.workTabId); } catch (e) {}
  }
  return null;
}
async function ensureGroup(tabId) {
  const st = await getState();
  let groupId = st.groupId;
  try {
    if (groupId == null) throw new Error("no group yet");
    await chrome.tabs.group({ groupId, tabIds: [tabId] });
  } catch (e) {
    groupId = await chrome.tabs.group({ tabIds: [tabId] });
    try { await chrome.tabGroups.update(groupId, { title: "Anticipy", color: "yellow" }); } catch (_) {}
    await setState({ groupId });
  }
}

function result(msg, status, proof, output) {
  return { type: "result", job_id: msg.job_id, status, proof, output };
}
function extractUrl(task) {
  const m = task && String(task).match(/https?:\/\/[^\s]+/);
  return m ? m[0] : null;
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function waitForComplete(tabId, timeout) {
  return new Promise((resolve, reject) => {
    const to = setTimeout(() => { chrome.tabs.onUpdated.removeListener(listener); reject(new Error("load timeout")); }, timeout);
    function listener(id, info) {
      if (id === tabId && info.status === "complete") {
        clearTimeout(to);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

// Keepalive backstop: an alarm wakes the SW even after an idle-kill.
chrome.alarms.create("anticipy-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name !== "anticipy-keepalive") return;
  if (!ws || ws.readyState !== WebSocket.OPEN) connect();
  else ws.send(JSON.stringify({ type: "ping" }));
});

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();

chrome.runtime.onMessage.addListener((m, _s, send) => {
  if (m === "status") { getState().then(send); return true; }
});
