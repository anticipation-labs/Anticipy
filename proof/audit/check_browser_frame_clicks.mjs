// REAL-CHROME PROOF: trusted clicks into embedded widgets, and clicks refused
// when something is in front of the control.
//
//   ANTICIPY_PLAYWRIGHT_MODULE=<path to playwright/index.mjs> \
//     node proof/audit/check_browser_frame_clicks.mjs
//
// The SHIPPED extension/agent_loop.js and page_map.js are driven against real
// Chrome (channel "chrome", headless) through the same Chrome-API bridge
// proof/audit/run_real_browser.mjs uses, over synthetic *.fixture.invalid
// pages fulfilled from a map. Every other request is aborted at the context,
// and the OS wrapper the runbook prescribes denies outbound network as a
// separate boundary. No model: the step model is a scripted fetch stub that
// picks the widget button BY INDEX off the map the loop actually produced, so
// what is measured is the loop's own geometry, not a hand-typed coordinate.
//
// Why proof/audit/check_browser_click_geometry.mjs was not enough: it injects
// page_map.js and dispatches at __anticipyCenter's answer in ONE frame. The
// two defects this proves fixed live in agent_loop.js's frame chain and in
// what the loop does with the point, neither of which that proof reaches.
//
// Scenarios, each a run of the real loop that must end with the fixture
// button having received exactly the click the loop claims it made — or,
// for the covered cases, with NO dispatch and a REFUSED line:
//   scroll      widget iframe below the fold on a scrollable page
//   nested      widget inside a src-less (srcdoc) wrapper that has a src-less parent — in-frame path
//   two-hop     widget inside a src-bearing wrapper — both hops re-measured
//   covered     role-less full-viewport interstitial over the control
//   late        the same interstitial injected between map and click
//   hidden      a menu that goes visibility:hidden between map and click, control underneath
//   inert       a pointer-events:none control over a live one
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "../..");
const candidates = [process.env.ANTICIPY_PLAYWRIGHT_MODULE,
  join(root, "node_modules/playwright/index.mjs"),
  ...(existsSync(join(homedir(), ".npm/_npx")) ? readdirSync(join(homedir(), ".npm/_npx")).map((name) =>
    join(homedir(), ".npm/_npx", name, "node_modules/playwright/index.mjs")) : [])].filter(Boolean);
const runtime = candidates.find(existsSync);
if (!runtime) throw new Error("Playwright runtime is required for this real Chrome proof (ANTICIPY_PLAYWRIGHT_MODULE)");
const pw = await import(pathToFileURL(runtime));
const { installChrome } = await import(pathToFileURL(join(root, "extension/tests/chrome_mock.mjs")));
const output = join(root, "output/playwright/browser-frame-clicks");
mkdirSync(output, { recursive: true });

const STYLE = "<style>body{font:18px system-ui;margin:0;padding:24px}button{font:inherit;padding:12px 20px;display:block;margin:12px 0}</style>";
const WIDGET = "https://widget.fixture.invalid/book";
const WRAPPER = "https://wrapper.fixture.invalid/shell";
const widget = STYLE + `<h2>Booking widget</h2><p>Pick a slot.</p>
<button id="target" onclick="window.__fixtureClicked('widget-target')">Reveal slots</button>`;
const interstitial = `<div id="interstitial" style="position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:999">
  <div style="background:#fff;width:420px;margin:120px auto;padding:24px" onclick="window.__fixtureClicked('interstitial')">
    <h2>Join our newsletter</h2><input placeholder="email"><button onclick="event.stopPropagation();window.__fixtureClicked('interstitial-dismiss')">No thanks</button>
  </div></div>`;
const target = `<button id="target" onclick="window.__fixtureClicked('target')">Reveal details</button>`;
const decoy = `<button id="decoy" onclick="window.__fixtureClicked('decoy')">Other action</button>`;
const pages = {
  [WIDGET]: widget,
  [WRAPPER]: STYLE + `<div style="height:150px">wrapper chrome</div><iframe src="${WIDGET}" style="width:600px;height:300px;margin-left:200px"></iframe>`,
  "https://site.fixture.invalid/scroll": STYLE + `<h1>Venue</h1><a href="https://site.fixture.invalid/scroll#menu">Menu</a>
    <div style="height:1400px"></div><iframe id="frame" src="${WIDGET}" style="width:600px;height:400px;border:1px solid #999"></iframe><div style="height:1400px"></div>`,
  "https://site.fixture.invalid/nested": STYLE + `<h1>Venue</h1><a href="https://site.fixture.invalid/nested#menu">Menu</a>
    <iframe id="wrapper" srcdoc="&lt;body style='margin:0'&gt;&lt;div style='height:150px'&gt;wrapper chrome&lt;/div&gt;&lt;iframe src='${WIDGET}' style='width:600px;height:300px;margin-left:200px'&gt;&lt;/iframe&gt;&lt;/body&gt;"
      style="position:absolute;left:250px;top:120px;width:900px;height:520px;border:1px solid #999"></iframe>`,
  "https://site.fixture.invalid/two-hop": STYLE + `<h1>Venue</h1><a href="https://site.fixture.invalid/two-hop#menu">Menu</a>
    <div style="height:900px"></div><iframe id="wrapper" src="${WRAPPER}" style="width:900px;height:520px;border:1px solid #999"></iframe><div style="height:900px"></div>`,
  "https://site.fixture.invalid/covered": STYLE + `<h1>Venue</h1><p>Opening hours below.</p>${target}${interstitial}`,
  "https://site.fixture.invalid/late": STYLE + `<h1>Venue</h1><p>Opening hours below.</p>${target}
    <script>setTimeout(() => document.body.insertAdjacentHTML("beforeend", ${JSON.stringify(interstitial)}), 2500)</script>`,
  "https://site.fixture.invalid/hidden": STYLE + `<h1>Venue</h1><div style="position:relative;height:120px">
      <div style="position:absolute;left:0;top:0">${decoy}</div>
      <div id="menu" style="position:absolute;left:0;top:0;background:#eee;z-index:5">${target}</div></div>
    <script>setTimeout(() => { document.getElementById("menu").style.visibility = "hidden"; }, 2500)</script>`,
  "https://site.fixture.invalid/inert": STYLE + `<h1>Venue</h1><div style="position:relative;height:120px">
      <div style="position:absolute;left:0;top:0">${decoy}</div>
      <div style="position:absolute;left:0;top:0;z-index:5;pointer-events:none">${target.replace('id="target"', 'id="target" style="pointer-events:none"')}</div></div>`,
};

const SCENARIOS = [
  { name: "scroll", label: /Reveal slots/, expectClick: "widget-target", coordinate: true },
  { name: "nested", label: /Reveal slots/, expectClick: "widget-target", coordinate: false },
  { name: "two-hop", label: /Reveal slots/, expectClick: "widget-target", coordinate: true },
  { name: "covered", label: /Reveal details/, expectClick: null, latencyMs: 0 },
  { name: "late", label: /Reveal details/, expectClick: null, latencyMs: 3000 },
  { name: "hidden", label: /Reveal details/, expectClick: null, latencyMs: 3000 },
  { name: "inert", label: /Reveal details/, expectClick: null, latencyMs: 0 },
];

const results = [];
for (const scenario of SCENARIOS) {
  const browser = await pw.chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1000, height: 700 } });
  const network = [];
  await context.route("**/*", (route) => {
    const req = route.request();
    network.push(req.url());
    if (req.method() === "GET" && Object.hasOwn(pages, req.url())) {
      return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: pages[req.url()] });
    }
    return route.abort();
  });
  const clicks = [];
  await context.exposeFunction("__fixtureClicked", (id) => clicks.push(id));

  // The bridge: chrome_mock's tabs/storage over real pages, frames and CDP.
  const harness = installChrome();
  const realPages = new Map(), cdps = new Map(), dispatches = [];
  const nativeCreate = chrome.tabs.create, nativeUpdate = chrome.tabs.update, nativeGet = chrome.tabs.get, nativeRemove = chrome.tabs.remove;
  const makePage = async (id, url) => { const page = await context.newPage(); realPages.set(id, page); if (url && url !== "about:blank") await page.goto(url); return page; };
  chrome.tabs.create = async (props) => { const tab = await nativeCreate(props); await makePage(tab.id, tab.url); return tab; };
  chrome.tabs.update = async (id, props) => { const tab = await nativeUpdate(id, props); if (props.url) await realPages.get(id).goto(props.url); return tab; };
  chrome.tabs.get = async (id) => { const tab = await nativeGet(id); const p = realPages.get(id); if (p) { tab.url = p.url(); harness.tabs.get(id).url = tab.url; } return tab; };
  chrome.tabs.remove = async (id) => { await realPages.get(id)?.close(); realPages.delete(id); return nativeRemove(id); };
  chrome.tabs.reload = async (id) => { await realPages.get(id)?.reload(); };
  chrome.scripting.executeScript = async ({ target, func, args = [], files = [] }) => {
    const page = realPages.get(target.tabId);
    if (!page) throw new Error("fixture tab disappeared");
    const all = page.frames();
    const frames = target.allFrames ? all : target.frameIds ? target.frameIds.map((id) => all[id]).filter(Boolean) : [page.mainFrame()];
    const values = [];
    for (const frame of frames) {
      for (const file of files) await frame.evaluate(readFileSync(join(root, "extension", file), "utf8"));
      const result = func ? await frame.evaluate(({ source, args }) => (0, eval)("(" + source + ")")(...args), { source: String(func), args }) : null;
      values.push({ frameId: all.indexOf(frame), result });
    }
    return values;
  };
  const session = async (tabId) => { if (!cdps.has(tabId)) cdps.set(tabId, await context.newCDPSession(realPages.get(tabId))); return cdps.get(tabId); };
  chrome.debugger.attach = async ({ tabId }) => { await session(tabId); };
  chrome.debugger.detach = async ({ tabId }) => { await cdps.get(tabId)?.detach(); cdps.delete(tabId); };
  chrome.debugger.sendCommand = async ({ tabId }, method, params = {}) => {
    const cdp = await session(tabId);
    if (method === "Input.dispatchMouseEvent" && params.type === "mousePressed") {
      const page = realPages.get(tabId);
      let observed = null;
      try {
        observed = await page.evaluate(({ x, y }) => {
          const hit = document.elementFromPoint(x, y);
          return { topAtPoint: hit ? `${hit.tagName.toLowerCase()}#${hit.id || ""}` : null, scrollY: window.scrollY };
        }, params);
      } catch (e) { observed = { error: String(e) }; }
      dispatches.push({ x: params.x, y: params.y, observed });
    }
    return cdp.send(method, params);
  };
  harness.addTab({ url: "https://owner.fixture.invalid/reading", active: true });

  // The scripted model: click the fixture button by its MAP index, then done.
  let clicked = 0;
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const body = JSON.parse(opts.body);
    const audit = body.messages.some((m) => String(m.content).startsWith("You audit"));
    let reply;
    if (audit) reply = { verified: true };
    else {
      const text = body.messages.map((m) => (typeof m.content === "string" ? m.content : JSON.stringify(m.content))).join("\n");
      const m = text.match(new RegExp(`\\[(\\d+)\\] <[a-z-]+> ${scenario.label.source}`, "m"));
      if (!m) reply = { action: "wait" };
      else if (clicked >= 1) reply = { action: "done", result: "Revealed it." };
      else { clicked++; reply = { action: "click", index: Number(m[1]) }; }
    }
    if (scenario.latencyMs) await new Promise((r) => setTimeout(r, scenario.latencyMs));
    const content = JSON.stringify(reply);
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };

  const { runAgentGoal } = await import(pathToFileURL(join(root, "extension/agent_loop.js")) + `?scenario=${scenario.name}`);
  const traces = [];
  let outcome;
  try {
    outcome = await runAgentGoal("Reveal it on the venue page. Read only.", {
      apiKey: "scripted", maxSteps: 4, budgetMs: 120000, authorized: true, readOnly: true,
      stillLive: async () => true, startUrl: `https://site.fixture.invalid/${scenario.name}`,
      onTrace: (h) => traces.push([...h]),
    });
  } finally {
    await context.close();
    await browser.close();
  }
  const history = traces.length ? traces[traces.length - 1] : [];
  const refused = history.some((l) => /REFUSED/.test(l.replace(/https?:\S+/g, "")));
  const row = { scenario: scenario.name, status: outcome?.status, dispatched: dispatches, fixtureClicks: clicks, refused,
    historyClickLines: history.filter((l) => /click|REFUSED|BLOCKED/i.test(l)).slice(0, 6),
    nonFixtureNetwork: network.filter((u) => !/fixture\.invalid/.test(u)) };
  if (scenario.expectClick) {
    row.passed = clicks.length === 1 && clicks[0] === scenario.expectClick
      && (scenario.coordinate ? dispatches.length === 1 : dispatches.length === 0);
  } else {
    // A covered/inert control: nothing dispatched, nothing else clicked, and
    // the loop said so.
    row.passed = dispatches.length === 0 && clicks.length === 0 && refused;
  }
  results.push(row);
  console.log(JSON.stringify(row, null, 2));
}
writeFileSync(join(output, "results.json"), JSON.stringify(results, null, 2));
assert.ok(results.every((r) => r.nonFixtureNetwork.length === 0), "no request may leave the fixture hosts");
assert.ok(results.every((r) => r.passed), `real-Chrome frame/hit-test scenarios failed: ${results.filter((r) => !r.passed).map((r) => r.scenario).join(", ")}`);
console.log(`\n${results.length}/${results.length} real-Chrome frame and hit-test scenarios passed`);
