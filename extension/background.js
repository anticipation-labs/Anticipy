// Anticipy browser hand — MV3 service worker.
// Connects to the local engine over an AUTHENTICATED WebSocket, stays alive
// (20s pings + alarm backstop), auto-reconnects, and keeps ALL state in
// chrome.storage (SW globals are lost when Chrome idle-kills the worker ~30s).
// Browse-job execution (page read / input / screenshot) is wired in piece 3.

const ENGINE_HTTP = "http://127.0.0.1:8787";
const ENGINE_WS = "ws://127.0.0.1:8787/ws/extension";
const PING_MS = 20000;

// Onboarding scrape: services to probe for an already-logged-in session (the engine may send its
// own list via the discover_connections message). PRIVACY: we only detect a logged-in vs sign-in
// signal — never read account contents, never store identifiers, never enter credentials.
const DEFAULT_DISCOVER_SERVICES = [
  { name: "Gmail", url: "https://mail.google.com/" },
  { name: "Google Calendar", url: "https://calendar.google.com/" },
  { name: "Google Drive", url: "https://drive.google.com/" },
  { name: "Outlook", url: "https://outlook.live.com/mail/" },
  { name: "Slack", url: "https://app.slack.com/client" },
  { name: "Notion", url: "https://www.notion.so/" },
];

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
  if (msg.type === "discover_connections") {
    const r = await doDiscoverConnections(msg);
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

    const screenshot = await cdpScreenshot(tab.id);
    const urlLc = (page.url || "").toLowerCase();
    const textLc = (page.text || "").toLowerCase();
    const captcha = /captcha|unusual traffic|are you a (robot|human)|verify you('| a)re human|press & hold/.test(textLc);
    const authUrl = /\/login|\/signin|\/sign-in|\/onboarding|\/auth\b|accounts\.|mode=login/.test(urlLc);
    const authText = /sign ?in|log ?in|create (an )?account|enter your password|forgot password|continue with/.test(textLc);
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

// --- onboarding primitive: DISCOVER which services the user is already logged into ---
// The "scrapes you" onboarding step, done in the user's OWN logged-in Chrome. PRIVACY-PRESERVING:
// for each service it opens the landing page in the Anticipy tab group, reads ONLY a logged-in vs
// sign-in signal from the DOM (an account/avatar/sign-out control, minus a sign-in wall) — never
// account contents, never an identifier, never a credential — then POSTs the {service, logged_in,
// url} list to the engine's /onboard/discover, which builds the per-person connection mesh.
async function doDiscoverConnections(msg) {
  const services = (msg.services && msg.services.length) ? msg.services : DEFAULT_DISCOVER_SERVICES;
  const discovered = [];
  for (const svc of services) {
    const url = svc && svc.url;
    if (!url) continue;
    try {
      const tab = await openInGroup(url);
      await waitForComplete(tab.id, 20000);
      await settle(tab.id);
      const [{ result: page }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => ({
          url: location.href,
          // a 1-line auth signal only — NOT account contents
          authText: (document.body ? document.body.innerText : "").slice(0, 1200),
          hasAccountChrome: !!document.querySelector(
            '[aria-label*="Account" i],[aria-label*="profile" i],img[alt*="avatar" i],' +
            'a[href*="logout" i],a[href*="signout" i],a[href*="sign-out" i],button[aria-label*="sign out" i]'
          ),
        }),
      });
      const blob = ((page.url || "") + " " + (page.authText || "")).toLowerCase();
      const signinWall = /\/login|\/signin|\/sign-in|accounts\.|\bsign in\b|\blog in\b|enter your password|create (an )?account|continue with/.test(blob);
      const logged_in = !!page.hasAccountChrome && !signinWall;
      discovered.push({ service: svc.name, logged_in: logged_in, identifier: "", url: url });
    } catch (e) {
      discovered.push({ service: svc.name, logged_in: false, identifier: "", url: url, error: String(e) });
    }
  }
  // Hand the discovery to the engine; it builds the per-person mesh via /onboard/discover (tested).
  let posted = false;
  try {
    const resp = await fetch(ENGINE_HTTP + "/onboard/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ discovered: discovered, source: "chrome_scrape" }),
    });
    posted = !!(resp && resp.ok);
  } catch (e) {}
  return result(msg, "success", null, { discovered: discovered, count: discovered.length, posted: posted });
}

// --- trusted input via CDP (chrome.debugger): real isTrusted events that hard
//     sites accept; replaces synthetic content-script clicks ---
let attachedTab = null;
async function ensureDebugger(tabId) {
  if (attachedTab === tabId) return;
  try {
    await chrome.debugger.attach({ tabId }, "1.3");
    attachedTab = tabId;
  } catch (e) {
    const m = String(e);
    if (m.includes("already attached") || m.includes("Another debugger")) attachedTab = tabId;
    else throw e;
  }
  // Enable Page events so the dialog handler below fires. A native JS dialog
  // (alert/confirm on add-to-cart) otherwise BLOCKS the page AND the whole CDP session,
  // hanging the agent forever on a large class of real stores. Best-effort.
  try { await cdp(tabId, "Page.enable"); } catch (e) {}
}

// Auto-handle native JS dialogs so they can never freeze the page / CDP session. SAFE policy:
// dismiss alerts (they have no choice) and allow page-leave (beforeunload), but CANCEL
// confirm/prompt — the agent must NEVER auto-confirm a destructive/irreversible action, and
// money is a hard stop. Registered once at module load; fires for any attached tab.
chrome.debugger.onEvent.addListener((source, method, params) => {
  if (method !== "Page.javascriptDialogOpening") return;
  const type = (params && params.type) || "alert";
  const accept = type === "alert" || type === "beforeunload"; // confirm/prompt -> Cancel
  try {
    chrome.debugger.sendCommand(
      { tabId: source.tabId }, "Page.handleJavaScriptDialog",
      { accept, promptText: "" }, () => { void chrome.runtime.lastError; });
  } catch (e) {}
});
function cdp(tabId, method, params) {
  // Internal timeout: if the debugger silently detached, sendCommand's callback can
  // never fire and the click would hang forever. Fail fast (12s) and drop the
  // attachment so the next call re-attaches a fresh debugger.
  return new Promise((res, rej) => {
    let done = false;
    const to = setTimeout(() => { if (!done) { done = true; attachedTab = null; rej(new Error("cdp timeout: " + method)); } }, 12000);
    chrome.debugger.sendCommand({ tabId }, method, params || {}, (r) => {
      if (done) return;
      done = true; clearTimeout(to);
      if (chrome.runtime.lastError) { attachedTab = null; rej(new Error(chrome.runtime.lastError.message)); }
      else res(r);
    });
  });
}
async function cdpClick(tabId, x, y) {
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 1, clickCount: 1 });
}
async function cdpType(tabId, text) { if (text) await cdp(tabId, "Input.insertText", { text }); }
async function cdpKey(tabId, key) {
  const map = { Enter: { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: "\r" } };
  const k = map[key] || { key };
  await cdp(tabId, "Input.dispatchKeyEvent", { type: "keyDown", ...k });
  await cdp(tabId, "Input.dispatchKeyEvent", { type: "keyUp", ...k });
}
// Screenshot via CDP (Page.captureScreenshot) — works on the working tab even when
// it isn't the active/visible one, unlike tabs.captureVisibleTab (which fails with
// "Failed to capture tab: image" on heavy/backgrounded tabs). Falls back if needed.
async function cdpScreenshot(tabId) {
  // Capture the WORKING tab only, via CDP. NEVER fall back to captureVisibleTab —
  // that grabs whatever tab the user is looking at (e.g. a video call), which is a
  // privacy + correctness bug. On failure return null; the engine re-observes.
  try {
    await ensureDebugger(tabId);
    const r = await cdp(tabId, "Page.captureScreenshot", { format: "jpeg", quality: 55, captureBeyondViewport: false });
    if (r && r.data) return "data:image/jpeg;base64," + r.data;
  } catch (e) {}
  return null;
}
chrome.tabs.onRemoved.addListener((id) => { if (id === attachedTab) attachedTab = null; });
chrome.debugger.onDetach.addListener((src) => { if (src && src.tabId === attachedTab) attachedTab = null; });

// --- wait for the page to settle (readyState complete + brief idle) ---
async function settle(tabId, maxMs = 6000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const [{ result: rs }] = await chrome.scripting.executeScript({ target: { tabId }, func: () => document.readyState });
      if (rs === "complete") break;
    } catch (e) {}
    await sleep(250);
  }
  await sleep(500);
}

// --- agent primitive: OBSERVE (set-of-marks: numbered boxes + a11y info) ---
async function doObserve(msg) {
  const args = msg.args || {};
  try {
    let tab = await getWorkingTab();
    if (args.url || !tab) {
      tab = await openInGroup(args.url || (tab ? tab.url : "about:blank"));
      await waitForComplete(tab.id, 25000);
      await settle(tab.id);
    } else {
      await ensureGroup(tab.id);
      await settle(tab.id);
    }
    const [{ result: page }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const old = document.getElementById('anticipy-som'); if (old) old.remove();
        const sel = 'a[href], button, input:not([type=hidden]), textarea, select, [role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [role=option], [onclick], [contenteditable=""], [contenteditable=true]';
        const cont = document.createElement('div'); cont.id = 'anticipy-som';
        cont.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;';
        document.documentElement.appendChild(cont);
        const colors = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#008080', '#f032e6', '#9a6324'];
        const out = []; let i = 0;
        for (const el of document.querySelectorAll(sel)) {
          const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
          if (r.width <= 2 || r.height <= 2 || cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue;
          if (r.bottom < -50 || r.right < 0 || r.top > innerHeight + 1200 || r.left > innerWidth) continue;
          el.setAttribute('data-anticipy-idx', String(i));
          let name = (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.value || el.getAttribute('title') || el.innerText || '').trim();
          if (!name) { const img = el.querySelector('img'); if (img) name = (img.getAttribute('alt') || '').trim(); }
          if (!name) name = (el.textContent || '').trim();
          if (!name) { const anc = el.closest('li, article, section, [role="listitem"], [role="article"]'); if (anc) { const h = anc.querySelector('h1, h2, h3, [role="heading"]'); if (h) name = (h.innerText || '').trim(); } }
          name = name.replace(/\s+/g, ' ').slice(0, 110);
          const role = el.getAttribute('role') || el.tagName.toLowerCase();
          const stt = []; if (el.disabled) stt.push('disabled'); if (el.checked) stt.push('checked');
          const ae = el.getAttribute('aria-expanded'); if (ae) stt.push('expanded=' + ae);
          const inView = r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
          let sponsored = false;
          const sanc = el.closest('li, article, section, [role="listitem"], [role="article"]');
          const sp = (((sanc || el).innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).slice(0, 240).toLowerCase();
          if (/sponsored|promoted|advertisement/.test(sp)) sponsored = true;
          out.push({ idx: i, role: role, name: name, type: (el.getAttribute('type') || ''), state: stt.join(','), inView: inView, sponsored: sponsored });
          if (inView) {
            const c = colors[i % colors.length];
            const box = document.createElement('div');
            box.style.cssText = 'position:fixed;left:' + r.left + 'px;top:' + r.top + 'px;width:' + r.width + 'px;height:' + r.height + 'px;outline:2px solid ' + c + ';box-sizing:border-box;';
            const lab = document.createElement('div'); lab.textContent = String(i);
            lab.style.cssText = 'position:absolute;left:0;top:0;transform:translateY(-100%);background:' + c + ';color:#fff;font:bold 11px monospace;padding:0 3px;white-space:nowrap;';
            box.appendChild(lab); cont.appendChild(box);
          }
          if (++i >= 140) break;
        }
        return { url: location.href, title: document.title, text: (document.body ? document.body.innerText : '').slice(0, 2500), elements: out };
      },
    });
    const screenshot = await cdpScreenshot(tab.id);
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => { const e = document.getElementById('anticipy-som'); if (e) e.remove(); } });
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
      await waitForComplete(tab.id, 25000); await settle(tab.id);
      return result(msg, "success", null, { ok: true, action: "navigate", url: a.url });
    }
    if (a.action === "back") {
      try { await chrome.tabs.goBack(tab.id); } catch (e) {}
      await sleep(1000);
      return result(msg, "success", null, { ok: true, action: "back" });
    }
    if (a.action === "scroll") {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, args: [a.dir || "down"],
        func: (d) => window.scrollBy(0, (d === "up" ? -1 : 1) * innerHeight * 0.8) });
      await sleep(500);
      return result(msg, "success", null, { ok: true, action: "scroll" });
    }
    if (a.action === "click" || a.action === "type") {
      // locate element, scroll it into view, get its viewport-center coords
      const [{ result: rc }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id }, args: [a.index],
        func: (i) => {
          const e = document.querySelector('[data-anticipy-idx="' + i + '"]');
          if (!e) return null;
          e.scrollIntoView({ block: "center", inline: "center" });
          const r = e.getBoundingClientRect();
          return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
        },
      });
      if (!rc) return result(msg, "needs_human", null, { ok: false, err: "no element " + a.index });
      await sleep(200);
      await ensureDebugger(tab.id);
      await cdpClick(tab.id, rc.x, rc.y);               // TRUSTED click (isTrusted=true)
      if (a.action === "type") {
        await sleep(120); await cdpType(tab.id, a.text || "");
        if (a.enter) { await sleep(120); await cdpKey(tab.id, "Enter"); }
      }
      await sleep((a.enter || a.action === "click") ? 1400 : 400);
      return result(msg, "success", null, { ok: true, action: a.action });
    }
    return result(msg, "needs_human", null, { ok: false, err: "unknown action " + a.action });
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
