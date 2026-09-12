// A CLICK IS NOT DISPATCHED INTO WHATEVER HAPPENS TO BE ON TOP.
//
// Measured in real Chrome on 2026-09-12 with the shipped loop: a full-viewport
// newsletter interstitial with no dialog role took the trusted click meant
// for the button beneath it and the run said done; a menu that went
// visibility:hidden while the model was thinking left its box laid out, so
// the control UNDERNEATH it was pressed — a wrong action — and history
// recorded "click 1"; a pointer-events:none control the map itself printed as
// [UNAVAILABLE] was dispatched at anyway. On the second identical decision
// the shipped fallback fired el.click() THROUGH the overlay.
//
// The repair is two structural facts the page itself answers, read at the
// moment the point is handed out: is this node paintable and
// pointer-reachable (computed style, native disabled), and is the topmost
// element at the point this node or its own chain (elementFromPoint). Neither
// reads a word of anything. `inert` / `coveredBy` ride on the point and every
// click site refuses to dispatch and says why; the repeat counter is unwound
// so the refusal never turns into the click-through fallback.
//
// Half 1 drives the REAL page_map.js over the fake DOM. Half 2 drives the REAL
// step loop under the Chrome mock and counts CDP mouse events.
//
// Run: node extension/tests/test_click_is_hit_tested.mjs
import { FakeNode, installFakePage, evalPageMap } from "./fake_page.mjs";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : "\n     " + detail}`);
  if (!ok) failures++;
};

function pageWith(nodes) {
  const body = new FakeNode("body", {}, nodes);
  const { restore } = installFakePage({ body, viewport: { w: 1000, h: 700 } });
  const win = evalPageMap();
  win.__anticipyMapPage();
  const indexOf = (id) => Number(Object.entries(win.__anticipyMap).find(([, n]) => n.id === id)?.[0]);
  return { win, restore, indexOf };
}

// ---- half 1: what the page map says about the point -----------------------
{
  const target = new FakeNode("button", { id: "target" }, [], { text: "Reveal details", rect: { x: 40, y: 140, width: 120, height: 30 } });
  const stranger = new FakeNode("div", { id: "interstitial", role: "presentation" }, [], { rect: { x: 0, y: 0, width: 1000, height: 700 }, style: { zIndex: "999" } });
  const { win, restore, indexOf } = pageWith([target, stranger]);
  const c = win.__anticipyCenter(indexOf("target"));
  check("covered: the point names the stranger the page reports on top",
        c && c.coveredBy === "div#interstitial[presentation]" && c.x === 100 && c.y === 155, JSON.stringify(c));
  restore();
}
{
  const target = new FakeNode("button", { id: "target" }, [], { text: "Reveal details", rect: { x: 40, y: 2000, width: 120, height: 30 } });
  const { win, restore, indexOf } = pageWith([target]);
  const c = win.__anticipyCenter(indexOf("target"));
  check("below the fold: elementFromPoint is null, unknown KEEPS the point (no refusal)",
        c && !c.coveredBy && !c.inert && c.x === 100 && c.y === 2015, JSON.stringify(c));
  restore();
}
{
  const target = new FakeNode("button", { id: "target" }, [], { text: "Reveal details", rect: { x: 40, y: 140, width: 120, height: 30 } });
  const { win, restore, indexOf } = pageWith([target]);
  const idx = indexOf("target");
  check("hidden-after-map: the control was on the map while visible", Number.isInteger(idx));
  target.style.visibility = "hidden";          // the menu closed while the model thought
  const c = win.__anticipyCenter(idx);
  check("hidden-after-map: the point is inert (hidden), never dispatched at",
        c && c.inert === "hidden", JSON.stringify(c));
  restore();
}
{
  const target = new FakeNode("button", { id: "target" }, [], { text: "Reveal details", rect: { x: 40, y: 140, width: 120, height: 30 }, style: { pointerEvents: "none" } });
  const { win, restore, indexOf } = pageWith([target]);
  const c = win.__anticipyCenter(indexOf("target"));
  check("pointer-events:none: the point is inert", c && c.inert === "inert", JSON.stringify(c));
  restore();
}
{
  const target = new FakeNode("button", { id: "target", disabled: "" }, [], { text: "Reveal details", rect: { x: 40, y: 140, width: 120, height: 30 } });
  const { win, restore, indexOf } = pageWith([target]);
  const c = win.__anticipyCenter(indexOf("target"));
  check("native disabled: the point is inert", c && c.inert === "inert", JSON.stringify(c));
  restore();
}
{
  // A <label> laid over its own <input> is the page's declared activation
  // path — clicking the label IS clicking the control — not a stranger.
  const input = new FakeNode("input", { id: "agree", type: "checkbox" }, [], { rect: { x: 40, y: 140, width: 20, height: 20 } });
  const label = new FakeNode("label", { id: "agree-label", for: "agree" }, [], { text: "I agree", rect: { x: 30, y: 130, width: 200, height: 40 }, style: { zIndex: "2" } });
  label.control = input;
  const { win, restore, indexOf } = pageWith([input, label]);
  const c = win.__anticipyCenter(indexOf("agree"));
  check("a label over its own control is not a covering stranger", c && !c.coveredBy && !c.inert, JSON.stringify(c));
  restore();
}
{
  const target = new FakeNode("button", { id: "target" }, [], { text: "Reveal details", rect: { x: 40, y: 140, width: 120, height: 30 } });
  const { win, restore, indexOf } = pageWith([target]);
  const c = win.__anticipyCenter(indexOf("target"));
  check("the ordinary case is untouched: a plain {x,y}", c && !c.coveredBy && !c.inert && c.x === 100 && c.y === 155, JSON.stringify(c));
  restore();
}

// ---- half 2: the loop refuses to dispatch, and says so ----------------------
const { installChrome } = await import("./chrome_mock.mjs");
const harness = installChrome();
const { runAgentGoal } = await import("../agent_loop.js");
function scriptFetch(actions, verdicts = [{ verified: true }]) {
  const a = [...actions], v = [...verdicts];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const body = JSON.parse(opts.body);
    const audit = body.messages.some((m) => String(m.content).startsWith("You audit"));
    const content = JSON.stringify(audit ? (v.shift() || { verified: true }) : (a.shift() || { action: "wait" }));
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
}
async function drive(centerAnswer) {
  harness.tabs.clear(); harness.onCdp = null; delete harness.storageData.agentTabs;
  harness.addTab({ url: "https://owner.fixture.invalid/reading", active: true });
  const native = chrome.scripting.executeScript;
  chrome.scripting.executeScript = async (opts) => {
    if (String(opts.func).includes("__anticipyCenter")) return [{ result: centerAnswer }];
    return native(opts);
  };
  const pressed = [];
  harness.onCdp = (tabId, method, params) => { if (method === "Input.dispatchMouseEvent" && params.type === "mousePressed") pressed.push(params); };
  harness.mapPage = (tabId) => ({ url: harness.tabs.get(tabId)?.url || "", title: "Venue",
    elements: "[0] <button> Reveal details @(100,155)", text: "Opening hours below." });
  scriptFetch([{ action: "click", index: 0 }, { action: "done", result: "Revealed the venue details." }]);
  const traces = [];
  const out = await runAgentGoal("reveal the venue details", { apiKey: "k", maxSteps: 4,
    startUrl: "https://site.fixture.invalid/covered", onTrace: (h) => traces.push([...h]) });
  chrome.scripting.executeScript = native;
  const history = traces.length ? traces[traces.length - 1] : [];
  return { out, pressed, history };
}
{
  const { pressed, history } = await drive({ x: 100, y: 155, coveredBy: "div#interstitial" });
  check("loop: a covered point dispatches NO mouse event", pressed.length === 0, `dispatched ${pressed.length}`);
  check("loop: history says the click was refused and names what covers it",
        history.some((l) => /REFUSED/.test(l) && /covered by div#interstitial/.test(l)), history.join("\n"));
  check("loop: the refusal never records the click as made",
        !history.some((l) => /retried click|via element handler/.test(l)), history.join("\n"));
}
{
  const { pressed, history } = await drive({ x: 100, y: 155, inert: "hidden" });
  check("loop: an inert point dispatches NO mouse event", pressed.length === 0, `dispatched ${pressed.length}`);
  check("loop: history says the point is hidden now", history.some((l) => /REFUSED/.test(l) && /hidden now/.test(l)), history.join("\n"));
}
{
  const { pressed } = await drive({ x: 100, y: 155 });
  check("CONTROL: an uncovered point IS dispatched exactly once", pressed.length === 1, `dispatched ${pressed.length}`);
}

console.log(`\nclick is hit-tested: ${failures ? failures + " FAILED" : "all passed"}`);
process.exit(failures ? 1 : 0);
