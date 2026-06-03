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
    let r;
    if (msg.intent === "observe") r = await doObserve(msg);
    else if (msg.intent === "act") r = await doAct(msg);
    else r = await executeBrowseJob(msg);
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(r));
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

// --- agent primitive: OBSERVE (label interactive elements + screenshot) ---
async function doObserve(msg) {
  const args = msg.args || {};
  try {
    let tab = await getWorkingTab();
    if (args.url || !tab) {
      tab = await openInGroup(args.url || (tab ? tab.url : "about:blank"));
      await waitForComplete(tab.id, 25000);
      await sleep(800);
    } else {
      await ensureGroup(tab.id);
    }
    const [{ result: page }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const sel = 'a[href], button, input:not([type=hidden]), textarea, select, [role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [onclick], [contenteditable=""], [contenteditable=true]';
        const out = []; let i = 0;
        for (const el of document.querySelectorAll(sel)) {
          const r = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          if (r.width <= 1 || r.height <= 1 || cs.visibility === 'hidden' || cs.display === 'none') continue;
          if (r.bottom < 0 || r.right < 0 || r.top > innerHeight + 600) continue;
          el.setAttribute('data-anticipy-idx', String(i));
          const label = (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.value || el.innerText || el.getAttribute('title') || el.getAttribute('name') || '').trim().replace(/\s+/g, ' ').slice(0, 90);
          out.push({ idx: i, tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || el.getAttribute('role') || ''), text: label });
          if (++i >= 120) break;
        }
        return { url: location.href, title: document.title, text: (document.body ? document.body.innerText : '').slice(0, 2500), elements: out };
      },
    });
    const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 40 });
    return result(msg, "success",
      { screenshot, url: page.url, title: page.title },
      { url: page.url, title: page.title, text: page.text, elements: page.elements, group_id: (await getState()).groupId });
  } catch (e) {
    return result(msg, "needs_human", null, { reason: "observe error: " + String(e) });
  }
}

// --- agent primitive: ACT (click / type / scroll / navigate / back) ---
async function doAct(msg) {
  const a = msg.args || {};
  try {
    let tab = await getWorkingTab();
    if (!tab) return result(msg, "needs_human", null, { reason: "no working tab" });
    if (a.action === "navigate") {
      tab = await chrome.tabs.update(tab.id, { url: a.url, active: true });
      await waitForComplete(tab.id, 25000); await sleep(700);
      return result(msg, "success", null, { ok: true, action: "navigate", url: a.url });
    }
    if (a.action === "back") {
      try { await chrome.tabs.goBack(tab.id); } catch (e) {}
      await sleep(900);
      return result(msg, "success", null, { ok: true, action: "back" });
    }
    const [{ result: res }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      args: [a],
      func: (a) => {
        const pick = (i) => document.querySelector('[data-anticipy-idx="' + i + '"]');
        if (a.action === "click") {
          const e = pick(a.index); if (!e) return { ok: false, err: "no element " + a.index };
          e.scrollIntoView({ block: "center" }); e.click(); return { ok: true };
        }
        if (a.action === "type") {
          const e = pick(a.index); if (!e) return { ok: false, err: "no element " + a.index };
          e.focus(); try { e.value = a.text; } catch (x) {}
          e.dispatchEvent(new Event("input", { bubbles: true }));
          e.dispatchEvent(new Event("change", { bubbles: true }));
          if (a.enter) {
            e.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
            e.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
            if (e.form) { try { e.form.requestSubmit ? e.form.requestSubmit() : e.form.submit(); } catch (x) {} }
          }
          return { ok: true };
        }
        if (a.action === "scroll") { window.scrollBy(0, (a.dir === "up" ? -1 : 1) * innerHeight * 0.8); return { ok: true }; }
        return { ok: false, err: "unknown action " + a.action };
      },
    });
    await sleep(a.action === "click" || a.enter ? 1200 : 400); // let navigation/JS settle
    return result(msg, res && res.ok ? "success" : "needs_human", null, { ...(res || {}), action: a.action });
  } catch (e) {
    return result(msg, "needs_human", null, { reason: "act error: " + String(e) });
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
