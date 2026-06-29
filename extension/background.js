// Anticipy browser hand — MV3 service worker.
// Connects to the local engine over an AUTHENTICATED WebSocket, stays alive
// (20s pings + alarm backstop), auto-reconnects, and keeps ALL state in
// chrome.storage (SW globals are lost when Chrome idle-kills the worker ~30s).
// Browse-job execution (page read / input / screenshot) is wired in piece 3.

const DEFAULT_ENGINE_HTTP = "http://127.0.0.1:8787";
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
  { name: "LinkedIn", url: "https://www.linkedin.com/feed/" },
  { name: "GitHub", url: "https://github.com/" },
  { name: "X (Twitter)", url: "https://x.com/home" },
  { name: "Instagram", url: "https://www.instagram.com/" },
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

async function engineHttp() {
  const st = await getState();
  return (st.engine_http || DEFAULT_ENGINE_HTTP).replace(/\/+$/, "");
}

async function engineWs() {
  const base = await engineHttp();
  return base.replace(/^http:/, "ws:").replace(/^https:/, "wss:") + "/ws/extension";
}

async function fetchToken() {
  const r = await fetch((await engineHttp()) + "/ws/token");
  if (!r.ok) throw new Error("token fetch failed: " + r.status);
  return (await r.json()).token;
}

async function connect() {
  try {
    const token = await fetchToken();
    const wsUrl = await engineWs();
    ws = new WebSocket(wsUrl + "?token=" + encodeURIComponent(token));
    ws.onopen = async () => {
      await setState({ connected: true, lastConnect: Date.now(), error: null });
      sendHeartbeat().catch(() => {});
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
  if (msg.type === "deep_scrape") {
    const r = await doDeepScrape(msg);
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
    await waitForComplete(tab.id, 25000, tab._anticipyBeforeUrl, tab._anticipyTargetUrl);  // hard sites can be slow
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
function discoverServiceKey(svc) {
  const raw = (((svc && svc.name) || "") + " " + ((svc && svc.url) || "")).toLowerCase();
  if (raw.includes("gmail") || raw.includes("mail.google")) return "gmail";
  if (raw.includes("calendar.google") || raw.includes("google calendar")) return "calendar";
  if (raw.includes("drive.google") || raw.includes("google drive")) return "drive";
  if (raw.includes("outlook") || raw.includes("office")) return "outlook";
  if (raw.includes("slack")) return "slack";
  if (raw.includes("notion")) return "notion";
  if (raw.includes("linkedin")) return "linkedin";
  if (raw.includes("github")) return "github";
  if (raw.includes("x.com") || raw.includes("twitter")) return "x";
  if (raw.includes("instagram")) return "instagram";
  return "generic";
}

function classifyDiscoverPage(svc, page) {
  const key = discoverServiceKey(svc);
  const url = String((page && page.url) || "").toLowerCase();
  const title = String((page && page.title) || "").toLowerCase();
  const authText = String((page && page.authText) || "").toLowerCase();
  const signals = (page && page.signals) || {};
  const hardLoginUrl = (
    /accounts\.google\.com\/(signin|servicelogin|interactive|v3\/signin)/.test(url) ||
    /login\.live\.com|\/login\b|\/signin\b|\/sign-in\b|\/users\/sign_in\b|\/i\/flow\/login\b/.test(url)
  );
  const hardLoginText = /enter your password|forgot password|create (an )?account|sign in to continue|log in to continue/.test(authText);
  const genericSignedIn = !!(page && page.hasAccountChrome) || !!signals.googleAccount || !!signals.userMenu;

  if (hardLoginUrl && !genericSignedIn) return { logged_in: false, reason: "login_url" };

  if (key === "gmail" && /mail\.google\.com\/mail/.test(url) &&
      (signals.gmailShell || signals.googleAccount || title.includes("gmail"))) {
    return { logged_in: true, reason: "gmail_shell" };
  }
  if (key === "calendar" && /calendar\.google\.com/.test(url) &&
      (signals.calendarShell || signals.googleAccount || title.includes("calendar"))) {
    return { logged_in: true, reason: "calendar_shell" };
  }
  if (key === "drive" && /drive\.google\.com\/drive/.test(url) &&
      (signals.driveShell || signals.googleAccount || title.includes("drive"))) {
    return { logged_in: true, reason: "drive_shell" };
  }
  if (key === "outlook" && /(outlook\.live\.com|outlook\.office\.com)\/mail/.test(url) &&
      (signals.outlookShell || genericSignedIn)) {
    return { logged_in: true, reason: "outlook_shell" };
  }
  if (key === "slack" && /app\.slack\.com\/client/.test(url) &&
      (signals.slackShell || genericSignedIn)) {
    return { logged_in: true, reason: "slack_shell" };
  }
  if (key === "notion" && /notion\.so/.test(url) &&
      (signals.notionShell || genericSignedIn)) {
    return { logged_in: true, reason: "notion_shell" };
  }
  if (key === "linkedin" && /linkedin\.com\/(feed|in|mynetwork|jobs|notifications|messaging)/.test(url) &&
      (signals.linkedinShell || genericSignedIn)) {
    return { logged_in: true, reason: "linkedin_shell" };
  }
  if (key === "github" && /github\.com/.test(url) && (signals.githubShell || signals.userMenu)) {
    return { logged_in: true, reason: "github_shell" };
  }
  if (key === "x" && /x\.com\/(home|notifications|messages|compose|explore)/.test(url) &&
      (signals.xShell || genericSignedIn)) {
    return { logged_in: true, reason: "x_shell" };
  }
  if (key === "instagram" && /instagram\.com/.test(url) &&
      (signals.instagramShell || genericSignedIn)) {
    return { logged_in: true, reason: "instagram_shell" };
  }

  if (hardLoginUrl || (hardLoginText && !genericSignedIn)) return { logged_in: false, reason: "login_wall" };
  if (genericSignedIn) return { logged_in: true, reason: "account_chrome" };
  return { logged_in: false, reason: "no_signed_in_signal" };
}

async function doDiscoverConnections(msg) {
  const services = (msg.services && msg.services.length) ? msg.services : DEFAULT_DISCOVER_SERVICES;
  const discovered = [];
  for (const svc of services) {
    const url = svc && svc.url;
    if (!url) continue;
    try {
      const tab = await openInGroup(url);
      await waitForComplete(tab.id, 20000, tab._anticipyBeforeUrl, tab._anticipyTargetUrl);
      await settle(tab.id);
      const [{ result: page }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => ({
          url: location.href,
          title: document.title,
          // a 1-line auth signal only — NOT account contents
          authText: (document.body ? document.body.innerText : "").slice(0, 1200),
          hasAccountChrome: !!document.querySelector(
            '[aria-label*="Account" i],[aria-label*="profile" i],img[alt*="avatar" i],' +
            'a[href*="logout" i],a[href*="signout" i],a[href*="sign-out" i],button[aria-label*="sign out" i]'
          ),
          signals: {
            googleAccount: !!document.querySelector(
              'a[aria-label*="Google Account" i],button[aria-label*="Google Account" i],' +
              'a[href*="SignOutOptions"],a[href*="accounts.google.com/SignOutOptions"]'
            ),
            userMenu: !!document.querySelector(
              '[aria-label*="account menu" i],[aria-label*="user menu" i],[aria-label*="profile menu" i],' +
              'summary[aria-label*="View profile" i],button[aria-label*="Open user account menu" i]'
            ),
            appShell: !!document.querySelector('main,[role="main"],nav,[role="navigation"]'),
            gmailShell: !!document.querySelector(
              'div[gh="tl"],div[gh="cm"],tr.zA,a[href*="#inbox"],[aria-label*="Inbox" i],[role="main"] [role="grid"]'
            ),
            calendarShell: !!document.querySelector(
              '[data-eventid],[data-eventchip],[aria-label*="Main calendar" i],[aria-label*="Create" i],[role="main"] [role="grid"]'
            ),
            driveShell: !!document.querySelector(
              '[aria-label*="New" i],[aria-label*="My Drive" i],[data-target="doc"],[role="main"] [role="grid"]'
            ),
            outlookShell: !!document.querySelector(
              '[aria-label*="New mail" i],[aria-label*="Message list" i],[role="listbox"],[role="main"]'
            ),
            slackShell: !!document.querySelector(
              '[data-qa="channel_sidebar_name_"],[data-qa="workspace_sidebar"],[data-qa="slack_kit_scrollbar"]'
            ),
            notionShell: !!document.querySelector('.notion-frame,[data-testid="sidebar"],[aria-label*="Private" i]'),
            linkedinShell: !!document.querySelector(
              '[data-test-global-nav],nav[aria-label*="Primary" i],a[href*="/mynetwork/"],a[href*="/messaging/"]'
            ),
            githubShell: !!document.querySelector(
              'meta[name="user-login"],.AppHeader-user,[data-login],summary[aria-label*="View profile" i]'
            ),
            xShell: !!document.querySelector(
              '[data-testid="SideNav_AccountSwitcher_Button"],[data-testid="primaryColumn"],a[href="/messages"]'
            ),
            instagramShell: !!document.querySelector(
              'nav a[href="/direct/inbox/"],a[href="/accounts/edit/"],svg[aria-label="Home"]'
            ),
          },
        }),
      });
      const classified = classifyDiscoverPage(svc, page);
      discovered.push({
        service: svc.name,
        logged_in: classified.logged_in,
        identifier: "",
        url: page.url || url,
        reason: classified.reason,
      });
    } catch (e) {
      discovered.push({ service: svc.name, logged_in: false, identifier: "", url: url, error: String(e) });
    }
  }
  // Hand the discovery to the engine; it builds the per-person mesh via /onboard/discover (tested).
  let posted = false;
  try {
    const resp = await fetch((await engineHttp()) + "/onboard/discover", {
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
  // that can grab whatever tab the user is looking at. The only fallback allowed
  // here first proves the requested tab is the active tab in its own window.
  try {
    await ensureDebugger(tabId);
    const r = await cdp(tabId, "Page.captureScreenshot", { format: "jpeg", quality: 55, captureBeyondViewport: false });
    if (r && r.data) return "data:image/jpeg;base64," + r.data;
  } catch (e) {}
  try {
    const tab = await chrome.tabs.get(tabId);
    const [active] = await chrome.tabs.query({ active: true, windowId: tab.windowId });
    if (active && active.id === tabId) {
      return await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 55 });
    }
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
  const requestedUrl = args.url || msg.url || "";
  const debug = { requested_url: requestedUrl, arg_keys: Object.keys(args) };
  try {
    let tab = await getWorkingTab();
    debug.before_url = tab && tab.url ? tab.url : "";
    if (requestedUrl || !tab) {
      tab = await openInGroup(requestedUrl || (tab ? tab.url : "about:blank"));
      debug.after_open_url = tab && tab.url ? tab.url : "";
      debug.recreated = !!tab._anticipyRecreated;
      await waitForComplete(tab.id, 25000, tab._anticipyBeforeUrl, tab._anticipyTargetUrl);
      try {
        const afterWait = await chrome.tabs.get(tab.id);
        debug.after_wait_url = afterWait && afterWait.url ? afterWait.url : "";
        debug.after_wait_status = afterWait && afterWait.status ? afterWait.status : "";
      } catch (e) {}
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
          if (r.bottom < -50 || r.right < 0 || r.top > innerHeight + 4000 || r.left > innerWidth) continue;
          el.setAttribute('data-anticipy-idx', String(i));
          let labelText = '';
          try {
            if (el.labels && el.labels.length) labelText = Array.from(el.labels).map(l => l.innerText || l.textContent || '').join(' ').trim();
            if (!labelText && el.id) {
              const lab = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
              if (lab) labelText = (lab.innerText || lab.textContent || '').trim();
            }
            if (!labelText) {
              const parentLabel = el.closest('label');
              if (parentLabel) labelText = (parentLabel.innerText || parentLabel.textContent || '').trim();
            }
          } catch (e) {}
          let name = (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.value || labelText || el.getAttribute('title') || el.innerText || '').trim();
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
          if (++i >= 600) break;
        }
        return { url: location.href, title: document.title, text: (document.body ? document.body.innerText : '').slice(0, 12000), elements: out };
      },
    });
    const screenshot = await cdpScreenshot(tab.id);
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => { const e = document.getElementById('anticipy-som'); if (e) e.remove(); } });
    return result(msg, "success",
      { screenshot, url: page.url, title: page.title },
      { url: page.url, title: page.title, text: page.text, elements: page.elements, group_id: (await getState()).groupId,
        debug });
  } catch (e) {
    return result(msg, "needs_human", null, { reason: "observe error: " + String(e),
      debug });
  }
}

// --- agent primitive: ACT (click / type / scroll / navigate / back) ---
async function doAct(msg) {
  const a = msg.args || {};
  let step = "start";
  try {
    let tab = await getWorkingTab();
    step = "get_working_tab";
    if (!tab) return result(msg, "needs_human", null, { reason: "no working tab" });

    if (a.action === "navigate") {
      tab = await chrome.tabs.update(tab.id, { url: a.url, active: true });
      await waitForComplete(tab.id, 25000, tab._anticipyBeforeUrl, tab._anticipyTargetUrl); await settle(tab.id);
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
    // --- agent primitive: CHECK (force a checkbox on/off and dispatch app-level events) ---
    if (a.action === "check") {
      step = "check";
      const [{ result: r }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id }, args: [a.index, a.checked !== false],
        func: (i, wantChecked) => {
          const e = document.querySelector('[data-anticipy-idx="' + i + '"]');
          if (!e) return { ok: false, reason: 'missing element' };
          let cb = null;
          if (e.matches && e.matches('input[type="checkbox"]')) cb = e;
          if (!cb && e.querySelector) cb = e.querySelector('input[type="checkbox"]');
          if (!cb && e.getAttribute) {
            const forId = e.getAttribute('for');
            if (forId) cb = document.getElementById(forId);
          }
          if (!cb || !cb.matches || !cb.matches('input[type="checkbox"]')) {
            return { ok: false, reason: 'not a checkbox', tag: e.tagName, role: e.getAttribute('role') };
          }
          if (cb.disabled) return { ok: false, reason: 'disabled checkbox' };
          cb.scrollIntoView({ block: 'center', inline: 'center' });
          if (cb.focus) cb.focus();
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked') &&
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked').set;
          if (setter) setter.call(cb, !!wantChecked);
          else cb.checked = !!wantChecked;
          cb.dispatchEvent(new Event('input', { bubbles: true }));
          cb.dispatchEvent(new Event('change', { bubbles: true }));
          return { ok: cb.checked === !!wantChecked, checked: !!cb.checked };
        },
      });
      await sleep(900);
      return result(msg, (r && r.ok) ? "success" : "needs_human", null, { action: "check", ...(r || {}) });
    }
    // --- agent primitive: SELECT (choose an option in a <select>/combobox by VISIBLE TEXT) ---
    if (a.action === "select") {
      step = "select";
      const [{ result: r }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id }, args: [a.index, String(a.value || a.text || "")],
        func: (i, want) => {
          const e = document.querySelector('[data-anticipy-idx="' + i + '"]');
          if (!e) return { ok: false, reason: 'missing element' };
          const w = String(want || '').trim().toLowerCase();
          const sel = e.tagName === 'SELECT' ? e : e.querySelector && e.querySelector('select');
          if (sel && sel.options) {
            const opts = Array.from(sel.options);
            const norm = (s) => String(s || '').trim().toLowerCase();
            let opt = opts.find(o => norm(o.textContent) === w || norm(o.value) === w)
                   || opts.find(o => norm(o.textContent).replace(/\s+/g, ' ') === w)
                   || opts.find(o => norm(o.textContent).startsWith(w + ' '))
                   || opts.find(o => norm(o.textContent || '').includes(w))
                   || opts.find(o => norm(o.value || '').includes(w));
            if (!opt) return { ok: false, reason: 'no matching option', options: opts.map(o => (o.textContent || '').trim()).slice(0, 15) };
            sel.value = opt.value; sel.selectedIndex = opt.index;
            sel.dispatchEvent(new Event('input', { bubbles: true }));
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            return { ok: true, selected: (opt.textContent || '').trim() };
          }
          return { ok: false, reason: 'not a select', tag: e.tagName, role: e.getAttribute('role') };
        },
      });
      await sleep(600);
      return result(msg, (r && r.ok) ? "success" : "needs_human", null, { action: "select", ...(r || {}) });
    }
    if (a.action === "click" || a.action === "type") {
      // locate element, scroll it into view, get its viewport-center coords
      step = "locate_element";
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
      let cdpReady = false;
      let cdpError = "";
      step = "ensure_debugger";
      try {
        await ensureDebugger(tab.id);
        cdpReady = true;
      } catch (e) {
        cdpError = String(e);
      }
      if (cdpReady) {
        try {
          step = "cdp_click";
          await cdpClick(tab.id, rc.x, rc.y);               // TRUSTED click (isTrusted=true)
        } catch (e) {
          cdpReady = false;
          cdpError = String(e);
        }
      }
      step = "js_focus_click";
      await chrome.scripting.executeScript({
        target: { tabId: tab.id }, args: [a.index],
        func: (i) => {
          const e = document.querySelector('[data-anticipy-idx="'+i+'"]');
          if (e) { if (e.focus) e.focus(); if (e.click) e.click(); }
        },
      }).catch(() => {});
      if (a.action === "type") {
        await sleep(120);
        if (cdpReady) {
          step = "cdp_type";
          await cdpType(tab.id, a.text || "");
        }
        step = "value_setter";
        await chrome.scripting.executeScript({
          target: { tabId: tab.id }, args: [a.index, a.text || ""],
          func: (i, text) => {
            const e = document.querySelector('[data-anticipy-idx="' + i + '"]');
            if (!e) return { ok: false, reason: 'missing element' };
            const current = ('value' in e) ? String(e.value || '') : String(e.textContent || '');
            if (text && current.includes(text)) return { ok: true, method: 'trusted', value: current };
            if ('value' in e) {
              const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
              const setter = Object.getOwnPropertyDescriptor(proto, 'value') && Object.getOwnPropertyDescriptor(proto, 'value').set;
              if (setter) setter.call(e, text);
              else e.value = text;
              e.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
              e.dispatchEvent(new Event('change', { bubbles: true }));
              return { ok: true, method: 'value_setter', value: e.value };
            }
            if (e.isContentEditable) {
              e.textContent = text;
              e.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
              e.dispatchEvent(new Event('change', { bubbles: true }));
              return { ok: true, method: 'contenteditable', value: e.textContent };
            }
            return { ok: false, reason: 'not typeable' };
          },
        }).catch(() => {});
        if (a.enter) { await sleep(120); await cdpKey(tab.id, "Enter"); }
      }
      await sleep((a.enter || a.action === "click") ? 1400 : 400);
      return result(msg, "success", null, { ok: true, action: a.action, step: "done", cdp_ready: cdpReady, cdp_error: cdpError });
    }
    return result(msg, "needs_human", null, { ok: false, err: "unknown action " + a.action });
  } catch (e) {
    return result(msg, "needs_human", null, { reason: "act error at " + step + ": " + String(e), step });
  }
}

// Robustly create a tab even when the MV3 service worker has "No current window" (the cause of
// the observe failure): target the last-focused NORMAL window, else any normal window, else make a
// new window. chrome.tabs.create({active:true}) alone throws when the SW has no current window.
async function createTab(url) {
  let winId = null;
  try { const w = await chrome.windows.getLastFocused({ windowTypes: ["normal"] }); if (w && w.id != null) winId = w.id; } catch (e) {}
  if (winId == null) {
    try { const ws = await chrome.windows.getAll({ windowTypes: ["normal"] }); if (ws && ws.length) winId = ws[ws.length - 1].id; } catch (e) {}
  }
  if (winId != null) {
    try { return await chrome.tabs.create({ url, active: true, windowId: winId }); } catch (e) {}
  }
  const win = await chrome.windows.create({ url, focused: true });
  if (win && win.tabs && win.tabs[0]) return win.tabs[0];
  const q = await chrome.tabs.query({ windowId: win && win.id });
  return q[0];
}

// --- the "Anticipy" tab group: always operate here, reusing one working tab ---
async function openInGroup(url) {
  let tab = await getWorkingTab();
  const beforeUrl = tab && tab.url ? tab.url : "";
  let recreated = false;
  if (tab) {
    tab = await chrome.tabs.update(tab.id, { url, active: true });
    await sleep(200);
    const current = await chrome.tabs.get(tab.id);
    if (url && beforeUrl && url !== beforeUrl && current.url === beforeUrl && current.status === "loading") {
      try { await chrome.tabs.remove(tab.id); } catch (e) {}
      tab = await createTab(url);
      await setState({ workTabId: tab.id });
      recreated = true;
    }
  } else {
    tab = await createTab(url);
    await setState({ workTabId: tab.id });
  }
  await ensureGroup(tab.id);
  const current = await chrome.tabs.get(tab.id);
  current._anticipyBeforeUrl = beforeUrl;
  current._anticipyTargetUrl = url;
  current._anticipyRecreated = recreated;
  return current;
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
function navigationHasMoved(tab, beforeUrl, targetUrl) {
  if (!beforeUrl) return true;
  if (targetUrl && beforeUrl === targetUrl) return true;
  if (tab && tab.url && tab.url !== beforeUrl) return true;
  // Already sitting on the target (re-observe / no redirect / trailing-slash) = arrived, not stuck.
  var norm = function (u) { return (u || "").replace(/[#?].*$/, "").replace(/\/+$/, ""); };
  if (tab && targetUrl && tab.url && norm(tab.url) === norm(targetUrl)) return true;
  return false;
}
function waitForComplete(tabId, timeout, beforeUrl, targetUrl) {
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(to);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    };
    const fail = (err) => {
      if (done) return;
      done = true;
      chrome.tabs.onUpdated.removeListener(listener);
      reject(err || new Error("load timeout"));
    };
    const finishIfDomUsable = () => {
      chrome.tabs.get(tabId, (tab) => {
        const status = tab && tab.status ? tab.status : "unknown";
        const currentUrl = tab && tab.url ? tab.url : "";
        chrome.scripting.executeScript({
          target: { tabId },
          func: () => document.readyState,
        }, (rows) => {
          const rs = rows && rows[0] && rows[0].result ? rows[0].result : "unknown";
          if (navigationHasMoved(tab, beforeUrl, targetUrl) && (rs === "interactive" || rs === "complete")) finish();
          else fail(new Error("load timeout status=" + status + " url=" + currentUrl + " readyState=" + rs));
        });
      });
    };
    const to = setTimeout(finishIfDomUsable, timeout);
    function listener(id, info) {
      if (id === tabId && info.status === "complete") {
        chrome.tabs.get(tabId, (tab) => {
          if (navigationHasMoved(tab, beforeUrl, targetUrl)) finish();
        });
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
    setTimeout(() => chrome.tabs.get(tabId, (tab) => {
      if (chrome.runtime.lastError) return;
      if (tab && tab.status === "complete" && navigationHasMoved(tab, beforeUrl, targetUrl)) finish();
    }), 500);
  });
}

// Keepalive backstop: an alarm wakes the SW even after an idle-kill.
chrome.alarms.create("anticipy-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name !== "anticipy-keepalive") return;
  sendHeartbeat().catch(() => {});
  if (!ws || ws.readyState !== WebSocket.OPEN) connect();
  else ws.send(JSON.stringify({ type: "ping" }));
});

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();

chrome.runtime.onMessage.addListener((m, _s, send) => {
  if (m === "status" || (m && m.type === "status")) { getState().then(send); return true; }
  if (m && m.type === "pair_device") {
    pairDevice(m).then(send).catch((e) => send({ ok: false, error: String(e) }));
    return true;
  }
  if (m && m.type === "heartbeat") {
    sendHeartbeat().then(send).catch((e) => send({ ok: false, error: String(e) }));
    return true;
  }
});

// ── External messages from the frontend page (Vercel or localhost:3000) ──
// This lets the scrape work WITHOUT a WebSocket connection to the engine.
// The frontend page sends { type: "discover_connections" } directly to the
// extension, and the extension does the scrape and sends results back.
chrome.runtime.onMessageExternal.addListener((msg, sender, sendResponse) => {
  if (msg.type === "ping") {
    getState().then((state) => sendResponse({
      ok: true,
      version: "0.3.0",
      paired: !!state.paired,
      connected: !!state.connected,
      device_id: state.device_id || "",
    }));
    return true;
  }
  if (msg.type === "pair_device") {
    pairDevice(msg)
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  if (msg.type === "heartbeat") {
    sendHeartbeat()
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  if (msg.type === "discover_connections") {
    const services = (msg.services && msg.services.length) ? msg.services : DEFAULT_DISCOVER_SERVICES;
    doDiscoverConnections({ type: "discover_connections", services })
      .then((r) => {
        const discovered = (r.output && r.output.discovered) || [];
        sendResponse({ ok: true, discovered, posted: !!(r.output && r.output.posted), count: (r.output && r.output.count) || discovered.length });
      })
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  if (msg.type === "deep_scrape") {
    const services = msg.services || [];
    doDeepScrape({ type: "deep_scrape", services })
      .then((r) => {
        const scraped = (r.output && r.output.scraped) || [];
        sendResponse({ ok: true, scraped, count: (r.output && r.output.count) || scraped.length });
      })
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  sendResponse({ ok: false, error: "unknown message type" });
});

async function pairDevice(msg) {
  const pairingCode = String(msg.pairing_code || msg.code || "").trim();
  const base = String(msg.engine_http || msg.engineHttp || DEFAULT_ENGINE_HTTP).replace(/\/+$/, "");
  if (!pairingCode) return { ok: false, error: "pairing_code_required" };
  await setState({ engine_http: base, pairing_error: null });
  const resp = await fetch(base + "/pairing/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pairing_code: pairingCode,
      label: msg.label || msg.device_name || "Chrome extension",
      device_kind: "chrome_extension",
      extension_id: chrome.runtime.id,
      capabilities: ["browser", "onboarding_scrape", "deep_scrape", "prepare_then_park"],
    }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data.ok) {
    const error = (data.detail && (data.detail.reason || data.detail.status)) || data.reason || data.error || ("HTTP " + resp.status);
    await setState({ paired: false, pairing_error: error });
    return { ok: false, error, detail: data.detail || data };
  }
  await setState({
    paired: true,
    pairing_error: null,
    device_id: data.device.device_id,
    device_token: data.device_token,
    device_label: data.device.label,
    engine_http: base,
    lastHeartbeat: Date.now(),
  });
  connect();
  return { ok: true, paired: true, device: data.device };
}

async function sendHeartbeat() {
  const st = await getState();
  if (!st.device_id || !st.device_token) return { ok: false, skipped: true, reason: "not_paired" };
  const resp = await fetch((await engineHttp()) + "/devices/heartbeat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: st.device_id, device_token: st.device_token }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data.ok) {
    const error = (data.detail && (data.detail.reason || data.detail.status)) || data.reason || data.error || ("HTTP " + resp.status);
    await setState({ lastHeartbeatError: error });
    return { ok: false, error, detail: data.detail || data };
  }
  await setState({ paired: true, lastHeartbeat: Date.now(), lastHeartbeatError: null });
  return { ok: true, device: data.device };
}

// ── Deep scrape: for each signed-in service, extract shallow metadata ──
// Subjects/titles/times/senders only — no email bodies, no private message bodies.
async function doDeepScrape(msg) {
  const services = msg.services || [];
  const scraped = [];
  for (const svc of services) {
    const url = svc && svc.url;
    if (!url) continue;
    try {
      const tab = await openInGroup(url);
      await waitForComplete(tab.id, 25000, tab._anticipyBeforeUrl, tab._anticipyTargetUrl);
      await settle(tab.id);
      await sleep(1500);
      const [{ result: pageData }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: (serviceName) => {
          const data = { service: serviceName, url: location.href, title: document.title, extracted: {} };
          const blob = (location.href + " " + (document.body ? document.body.innerText : "")).toLowerCase().slice(0, 3000);
          const isLogin = /\/login|\/signin|\/sign-in|accounts\.|enter your password|create (an )?account|continue with google|sign in with/.test(blob);
          if (isLogin) { data.signed_in = false; return data; }
          data.signed_in = true;
          const sn = serviceName.toLowerCase();
          if (sn.includes("gmail")) {
            const rows = document.querySelectorAll('tr.zA, tr[role="row"]');
            const emails = [];
            rows.forEach((row, i) => {
              if (i >= 20) return;
              const sender = row.querySelector('.yW, .bA4, [email]');
              const subject = row.querySelector('.bog, .y6, .xT .y6');
              if (sender || subject) emails.push({ from: (sender ? sender.textContent : '').trim().slice(0, 60), subject: (subject ? subject.textContent : '').trim().slice(0, 120) });
            });
            data.extracted.emails = emails;
          }
          if (sn.includes("calendar")) {
            const events = [];
            document.querySelectorAll('[data-eventchip], [data-eventid]').forEach((el, i) => {
              if (i >= 15) return;
              const text = (el.textContent || el.getAttribute('aria-label') || '').trim();
              if (text) events.push(text.slice(0, 150));
            });
            data.extracted.events = events;
          }
          if (sn.includes("drive")) {
            const files = [];
            document.querySelectorAll('[data-id][aria-label], .Q5txwe').forEach((el, i) => {
              if (i >= 15) return;
              const name = (el.getAttribute('aria-label') || el.textContent || '').trim();
              if (name && name.length > 2) files.push(name.slice(0, 120));
            });
            data.extracted.recent_files = files;
          }
          if (sn.includes("linkedin")) {
            const nameEl = document.querySelector('.text-heading-xlarge');
            if (nameEl) data.extracted.profile_name = nameEl.textContent.trim().slice(0, 80);
          }
          if (sn.includes("outlook")) {
            const emails = [];
            document.querySelectorAll('[aria-label*="message" i], [role="option"]').forEach((el, i) => {
              if (i >= 15) return;
              const text = (el.textContent || el.getAttribute('aria-label') || '').trim();
              if (text && text.length > 5) emails.push(text.slice(0, 200));
            });
            data.extracted.emails = emails;
          }
          if (sn.includes("slack")) {
            const channels = [];
            document.querySelectorAll('[data-qa="channel_sidebar_name_"]').forEach((el, i) => {
              if (i >= 15) return;
              const name = (el.textContent || '').trim();
              if (name) channels.push(name.slice(0, 60));
            });
            data.extracted.channels = channels;
          }
          if (sn.includes("github")) {
            const usernameEl = document.querySelector('.AppHeader-user .Button-label, [data-login]');
            if (usernameEl) data.extracted.username = (usernameEl.textContent || usernameEl.getAttribute('data-login') || '').trim().slice(0, 40);
          }
          return data;
        },
        args: [svc.name],
      });
      scraped.push(pageData);
    } catch (e) {
      scraped.push({ service: svc.name, url, error: String(e) });
    }
  }
  // Hand the CONTENT scrape to the engine (mirrors discover_connections -> /onboard/discover):
  // POST to /onboard/deep-scrape, which synthesizes a dossier from this real-Chrome content and
  // writes it to memory. This is what makes the scrape actually LEARN about the user.
  let posted = false;
  try {
    const resp = await fetch((await engineHttp()) + "/onboard/deep-scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scraped: scraped, source: "chrome_deep_scrape" }),
    });
    posted = !!(resp && resp.ok);
  } catch (e) {}
  return result(msg, "success", null, { scraped, count: scraped.length, posted });
}
