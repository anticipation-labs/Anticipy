// EVERY VISIBLE OPTION KEEPS ITS INDEX. WHICH LIST IS THE AUTOCOMPLETE IS
// STRUCTURE FIRST, AND A MODEL'S CALL ONLY WHEN STRUCTURE CANNOT SAY.
//
// Audit #72. page_map.js's suggestion pass decided, from an option's own
// words, whether it was an airport suggestion the model may pick or a
// trip-type / passenger option to hide — and deleted the index:
//
//     if (/^(round.?trip|one.?way|multi.?city|\d+\s*(adult|child|traveler|passenger))/i.test(t)) {
//       counter--; delete window.__anticipyMap[idx]; continue; }
//
// Measured: "Change my Toronto flight to multi-city" could never click
// Multi-city; "2 Passenger Terminal Rd" vanished from a Places list. Nothing
// could see it — chrome_mock stubbed the function to "".
//
// HARNESS-LAWS.md law 1. What replaces it reads what a list is ATTACHED to
// (aria-controls / aria-owns / aria-activedescendant / combobox ancestry /
// anchoring geometry) and whether a person can see it (visible, not
// aria-hidden, uncovered at its centre — unknown KEEPS). Deletes nothing.
// One CEILING question, asked of a model on its own, only when two or more
// lists are unattached: it can re-head a list and never drop one, and every
// no-verdict leaves every list in view under the neutral heading.
//
// THE MUTATIONS THAT MUST TURN THIS RED (each run and restored, see the
// commit): the regex restored as "skip options whose text matches" in
// __anticipySuggestions -> (a); the loop never asking (fire condition
// false) -> (c); a no-verdict treated as a verdict (noverdict fences like
// NONE) -> (b); elementFromPoint null read as covered -> (a).
//
// Run: node extension/tests/test_suggestions_keep_every_option.mjs
import { installChrome } from "./chrome_mock.mjs";
import { FakeNode, installFakePage, evalPageMap } from "./fake_page.mjs";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const harness = installChrome();
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
// Imported AFTER installChrome(): config.js reads chrome.storage at evaluation.
const {
  MODEL_REPLY_FLOOR, SUGGESTION_LIST_SYSTEM, applySuggestionVerdict, renderSuggestionLists,
  runAgentGoal, suggestionListVerdict,
} = await import("../agent_loop.js");

// ---------------------------------------------------------------------------
// (a) THE PAGE SIDE. The real page_map.js against a page that has every shape
//     the regex used to delete, plus the two the review added.
// ---------------------------------------------------------------------------
{
  const R = (x, y, width, height) => ({ x, y, width, height });
  const body = new FakeNode("body", {}, [], { rect: R(0, 0, 1280, 2000) });
  // A modal's backdrop over the page, and the dialog above it (Google Flights
  // shape): the main map scopes itself to the dialog.
  body.append(new FakeNode("div", { class: "backdrop" }, [], { rect: R(0, 0, 1280, 800), style: { zIndex: "90" } }));
  const dialog = body.append(new FakeNode("div", { role: "dialog", "aria-modal": "true" }, [],
    { rect: R(50, 50, 700, 400), style: { zIndex: "100" } }));
  dialog.append(new FakeNode("label", { for: "from" }, [], { text: "From", rect: R(100, 70, 100, 20) }));
  const from = dialog.append(new FakeNode("input", { id: "from", name: "from", type: "text", "aria-controls": "from-list" },
    [], { value: "SFO", rect: R(100, 100, 300, 32) }));
  const sfo = new FakeNode("li", { role: "option" }, [], { text: "San Francisco (SFO)", rect: R(100, 136, 300, 40) });
  const passenger = new FakeNode("li", {}, [], { text: "2 Passenger Terminal Rd, San Francisco", rect: R(100, 176, 300, 40) });
  dialog.append(new FakeNode("ul", { id: "from-list", role: "listbox" }, [sfo, passenger], { rect: R(100, 136, 300, 80) }));
  const roundTrip = new FakeNode("div", { role: "option", "aria-selected": "true" }, [], { text: "Round trip", rect: R(500, 100, 200, 40) });
  const oneWay = new FakeNode("div", { role: "option" }, [], { text: "One way", rect: R(500, 140, 200, 40) });
  const multiCity = new FakeNode("div", { role: "option" }, [], { text: "Multi-city", rect: R(500, 180, 200, 40) });
  dialog.append(new FakeNode("div", { role: "listbox", "aria-label": "Trip type" }, [roundTrip, oneWay, multiCity],
    { rect: R(500, 100, 200, 120) }));
  dialog.append(new FakeNode("button", {}, [], { text: "Search", rect: R(100, 400, 120, 40) }));
  // Behind the backdrop: a page-level listbox a person cannot click.
  const price = new FakeNode("div", { role: "option" }, [], { text: "Price", rect: R(900, 600, 200, 40) });
  const duration = new FakeNode("div", { role: "option" }, [], { text: "Duration", rect: R(900, 640, 200, 40) });
  body.append(new FakeNode("div", { role: "listbox", "aria-label": "Sort by" }, [price, duration], { rect: R(900, 600, 200, 80) }));
  // A body-appended Places container floating above everything — the hit at
  // its centre is the item's inner span, not the item.
  const childSt = new FakeNode("div", { class: "pac-item" },
    [new FakeNode("span", { class: "pac-item-query" }, [], { text: "3 Child St", rect: R(100, 500, 150, 40) })],
    { rect: R(100, 500, 300, 40) });
  body.append(new FakeNode("div", { class: "pac-container" }, [childSt], { rect: R(100, 500, 300, 40), style: { zIndex: "1000" } }));
  // Below the fold: elementFromPoint is null there. Unknown must KEEP.
  const yyz = new FakeNode("li", {}, [], { text: "Toronto (YYZ)", rect: R(100, 900, 300, 40) });
  body.append(new FakeNode("ul", { role: "listbox", "aria-label": "Recent searches" }, [yyz], { rect: R(100, 900, 300, 40) }));
  // An option in an open shadow root, whose hit is retargeted to the host.
  const host = body.append(new FakeNode("x-picker", {}, [], { rect: R(800, 50, 200, 60), style: { zIndex: "200" } }));
  const inShadow = host.attachShadow().append(new FakeNode("div", { role: "option" }, [], { text: "In shadow", rect: R(800, 50, 200, 60) }));

  const page = installFakePage({ body, active: from, url: "https://fixture.test/flights" });
  // The fake never pierces a shadow root from the document, like a browser;
  // this pin drives the composed walk directly by handing the mapper the
  // shadow option through the one selector that reaches it.
  const realQSA = page.document.querySelectorAll;
  page.document.querySelectorAll = (selector) => [...realQSA(selector),
    ...(selector.includes("[role=option]") && inShadow.matches("[role=option]") ? [inShadow] : [])];
  const win = evalPageMap();
  const main = win.__anticipyMapPage();
  const { lists } = win.__anticipySuggestions();
  page.restore();

  const optionsOf = (list) => (list?.options || []).map((o) => o.text);
  const every = lists.flatMap((l) => l.options);
  const texts = every.map((o) => o.text);
  check("(a) the main map scoped to the dialog and numbered the role=option nodes",
    /\[1\] <option> San Francisco \(SFO\)/.test(main.elements) && /\[4\] <option> Multi-city/.test(main.elements),
    main.elements);
  check("(a) Multi-city is in the suggestion lists", texts.includes("Multi-city"), texts.join(" | "));
  check("(a) '2 Passenger Terminal Rd' — the \\d+\\s*passenger arm — is in the lists",
    texts.some((t) => t.startsWith("2 Passenger Terminal Rd")), texts.join(" | "));
  check("(a) '3 Child St' from a floating .pac-container above the dialog survives (hit inside the item)",
    texts.includes("3 Child St"), texts.join(" | "));
  check("(a) Round trip / One way are there too — nothing string-shaped decides",
    texts.includes("Round trip") && texts.includes("One way"));
  check("(a) the From list is first, attached, and named by the box that declares it",
    lists[0]?.attached === true && lists[0]?.name === "From" && lists[0]?.letter === "A",
    JSON.stringify(lists.map((l) => [l.letter, l.name, l.attached])));
  check("(a) ...and holds both its options, including the li the main selector cannot reach",
    optionsOf(lists[0]).length === 2 && optionsOf(lists[0]).includes("San Francisco (SFO)"), JSON.stringify(optionsOf(lists[0])));
  const trip = lists.find((l) => l.name === "Trip type");
  check("(a) Trip type is present and NOT attached — structure, not wording, says so",
    !!trip && trip.attached === false && optionsOf(trip).length === 3, JSON.stringify(trip));
  check("(a) the already-chosen option is marked from aria-selected", trip?.options.find((o) => o.text === "Round trip")?.picked === true);
  check("(a) the list behind the dialog backdrop is absent — a person cannot click it",
    !lists.some((l) => l.name === "Sort by") && !texts.includes("Price") && !texts.includes("Duration"));
  check("(a) a list below the fold (elementFromPoint null) SURVIVES: unknown keeps",
    texts.includes("Toronto (YYZ)"), texts.join(" | "));
  check("(a) an option in an open shadow root whose hit is the host SURVIVES: the composed walk",
    texts.includes("In shadow"), texts.join(" | "));
  // Indexes: every option resolves to its own node, the set of distinct
  // indexes is the set of uncovered option nodes, and nodes the main map
  // already numbered keep that number.
  const distinct = new Set(every.map((o) => o.idx));
  const uncovered = [sfo, passenger, roundTrip, oneWay, multiCity, childSt, yyz, inShadow];
  check("(a) the SET of distinct indexes equals the set of uncovered option nodes (nothing skipped, nothing twice)",
    distinct.size === uncovered.length && every.length === uncovered.length
      && uncovered.every((node) => every.some((o) => win.__anticipyMap[o.idx] === node)),
    `${distinct.size} distinct for ${uncovered.length} nodes`);
  check("(a) each index resolves to the node whose text it shows",
    every.every((o) => (win.__anticipyMap[o.idx].innerText || "").trim().replace(/\s+/g, " ").startsWith(o.text)));
  check("(a) a role=option the main map numbered REUSES that index (the WeakMap), never a second one",
    every.find((o) => o.text === "San Francisco (SFO)")?.idx === 1
      && every.find((o) => o.text === "Multi-city")?.idx === 4);
  check("(a) nodes only the suggestion selector reaches get fresh indexes above the main map's",
    every.find((o) => o.text.startsWith("2 Passenger"))?.idx >= 6 && every.find((o) => o.text === "3 Child St")?.idx >= 6);
  check("(a) the page side returns structure only: no heading, no verdict",
    !JSON.stringify(lists).includes("SUGGESTIONS") && !JSON.stringify(lists).includes("attached to the box"));
  // And, rendered the way the loop renders it with no verdict at all:
  const text = renderSuggestionLists(applySuggestionVerdict(lists, { state: "unasked" }), "From");
  const optionLines = text.split("\n").filter((line) => /^\[\d+\] <option>/.test(line));
  check("(a) rendered: the From list heads the block under a heading naming the box and 'attached'",
    text.split("\n")[0].includes("SUGGESTIONS for «From»") && text.split("\n")[0].includes("attached to the box"));
  check("(a) rendered: Trip type sits under a 'not attached' heading",
    /OTHER OPTION LIST: Trip type — not attached/.test(text));
  check("(a) rendered: the count of [n] option lines equals the count of uncovered option nodes",
    optionLines.length === uncovered.length && new Set(optionLines.map((l) => l.match(/^\[(\d+)\]/)[1])).size === uncovered.length,
    `${optionLines.length} lines`);
}

// ---------------------------------------------------------------------------
// (b) THE ONE QUESTION, through the exported functions with a fetch stub.
//     Four states, and the CEILING polarity: no fence without a verdict.
// ---------------------------------------------------------------------------
{
  const twoLists = () => [
    { letter: "A", name: "Trip type", attached: false, total: 3, options: [
      { idx: 3, text: "Round trip", picked: true, cx: 600, cy: 120 },
      { idx: 4, text: "One way", picked: false, cx: 600, cy: 160 },
      { idx: 5, text: "Multi-city", picked: false, cx: 600, cy: 200 } ] },
    { letter: "B", name: "", attached: false, total: 2, options: [
      { idx: 6, text: "San Francisco (SFO)", picked: false, cx: 250, cy: 156 },
      { idx: 7, text: "2 Passenger Terminal Rd, San Francisco", picked: false, cx: 250, cy: 196 } ] },
  ];
  const stub = (reply) => {
    const calls = [];
    globalThis.fetch = async (url, opts = {}) => {
      calls.push(JSON.parse(opts.body));
      if (reply instanceof Error) throw reply;
      if (reply === null) return { ok: false, status: 400, json: async () => ({}), text: async () => "" };
      return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: reply } }] }), text: async () => "" };
    };
    return calls;
  };
  const args = { field: "From", typed: "SFO", lists: twoLists() };

  let calls = stub("B");
  let verdict = await suggestionListVerdict("test-key", "m", args);
  check("(b) two unattached lists produce exactly one call", calls.length === 1, String(calls.length));
  check("(b) ...whose system prompt is the one question, on its own",
    calls[0]?.messages?.[0]?.role === "system" && /which list, if any, is offering COMPLETIONS/.test(calls[0].messages[0].content)
      && calls[0].messages[0].content === SUGGESTION_LIST_SYSTEM);
  // The call asks for 8 tokens, like authoredJudge and meantForTheOwner;
  // modelFetch floors every request at MODEL_REPLY_FLOOR on the wire.
  check("(b) ...bounded: temperature 0, a one-token ask floored at MODEL_REPLY_FLOOR on the wire",
    calls[0]?.temperature === 0 && calls[0]?.max_tokens === MODEL_REPLY_FLOOR, JSON.stringify([calls[0]?.temperature, calls[0]?.max_tokens]));
  const user = String(calls[0]?.messages?.[1]?.content || "");
  check("(b) ...carrying the box label, the typed text and every list as page content inside the fence",
    /<PAGE \S+>/.test(user) && user.includes("The box: «From»") && user.includes("What was typed: «SFO»")
      && user.includes("List A (Trip type): Round trip | One way | Multi-city")
      && user.includes("List B (unnamed): San Francisco (SFO)"), user);
  check("(b) 'B' -> ATTACHED(B)", verdict.state === "attached" && verdict.letter === "B", JSON.stringify(verdict));
  let headed = applySuggestionVerdict(twoLists(), verdict);
  let text = renderSuggestionLists(headed, "From");
  check("(b) ...promotes list B first under the attached heading", headed.lists[0].letter === "B" && headed.lists[0].standing === "attached"
    && text.indexOf("SUGGESTIONS for «From»") < text.indexOf("[6] <option> San Francisco"), text);
  check("(b) ...and heads A 'not attached' — demoted, never dropped",
    headed.lists[1].standing === "other" && text.includes("[5] <option> Multi-city") && text.includes("OTHER OPTION LIST: Trip type"));

  calls = stub("NONE");
  verdict = await suggestionListVerdict("test-key", "m", args);
  text = renderSuggestionLists(applySuggestionVerdict(twoLists(), verdict), "From");
  check("(b) 'NONE' -> every list 'not attached' plus the wait line, every option still present",
    verdict.state === "none" && /no visible list offers completions for «From» yet/.test(text)
      && (text.match(/OTHER OPTION LIST/g) || []).length === 2 && text.includes("[7] <option> 2 Passenger"), text);

  calls = stub("UNCLEAR");
  verdict = await suggestionListVerdict("test-key", "m", args);
  text = renderSuggestionLists(applySuggestionVerdict(twoLists(), verdict), "From");
  check("(b) 'UNCLEAR' -> the neutral heading, nothing demoted",
    verdict.state === "unclear" && /VISIBLE OPTION LISTS/.test(text) && !/not attached/.test(text) && !/SUGGESTIONS for/.test(text), text);

  // THE POLARITY PIN. Every way of not answering leaves every list neutral.
  for (const [name, reply] of [["prose ('I think B')", "I think B"], ["an empty body", ""], ["a letter outside the offered set", "D"],
                               ["a non-2xx", null], ["a rejected promise", new Error("boom")]]) {
    calls = stub(reply);
    verdict = await suggestionListVerdict("test-key", "m", args);
    headed = applySuggestionVerdict(twoLists(), verdict);
    text = renderSuggestionLists(headed, "From");
    check(`(b) ${name} -> UNANSWERED, and the CEILING fences nothing: neutral heading, both lists, all five options`,
      verdict.state === "unanswered" && headed.lists.every((l) => l.standing === "neutral")
        && /VISIBLE OPTION LISTS/.test(text) && !/not attached/.test(text) && !/SUGGESTIONS for/.test(text)
        && (text.match(/^\[\d+\] <option>/gm) || []).length === 5,
      `${JSON.stringify(verdict)} ${text}`);
  }
  calls = stub("B");
  verdict = await suggestionListVerdict("", "m", args);
  check("(b) no model -> UNASKED, no call", verdict.state === "unasked" && calls.length === 0, JSON.stringify(verdict));
  verdict = await suggestionListVerdict("test-key", "m", { ...args, lists: twoLists().slice(0, 1) });
  check("(b) one list -> UNASKED, no call", verdict.state === "unasked" && calls.length === 0, JSON.stringify(verdict));
  check("(b) UNANSWERED and UNCLEAR are different states, and both are different from NONE",
    new Set([(await (async () => { stub(""); return (await suggestionListVerdict("test-key", "m", args)).state; })()),
             (await (async () => { stub("UNCLEAR"); return (await suggestionListVerdict("test-key", "m", args)).state; })()),
             (await (async () => { stub("NONE"); return (await suggestionListVerdict("test-key", "m", args)).state; })())]).size === 3);
  // Structure beats the question: with a list attached by the page, the
  // others are 'not attached' and no verdict is needed to say so.
  const attachedByPage = twoLists(); attachedByPage[1].attached = true;
  text = renderSuggestionLists(applySuggestionVerdict(attachedByPage, { state: "unasked" }), "From");
  check("(b) a list the page attaches heads the block with no verdict, and the other reads 'not attached'",
    text.startsWith("--- SUGGESTIONS for «From»") && /OTHER OPTION LIST: Trip type — not attached/.test(text), text);
  check("(b) applySuggestionVerdict never drops a list or an option, in any state",
    ["attached", "none", "unclear", "unasked", "unanswered"].every((state) => {
      const out = applySuggestionVerdict(twoLists(), { state, letter: "A" });
      return out.lists.length === 2 && out.lists.reduce((n, l) => n + l.options.length, 0) === 5;
    }));
}

// ---------------------------------------------------------------------------
// (c) THE LOOP. The real agent, the bytes it sends to the step model: the
//     question fires once, on the step after the type, only when nothing is
//     attached, and the verdict shapes the block the step model reads.
// ---------------------------------------------------------------------------
const LISTS = (attachB = false) => ({ lists: [
  { letter: "A", name: "Trip type", attached: false, total: 3, options: [
    { idx: 3, text: "Round trip", picked: true, cx: 600, cy: 120 },
    { idx: 4, text: "One way", picked: false, cx: 600, cy: 160 },
    { idx: 5, text: "Multi-city", picked: false, cx: 600, cy: 200 } ] },
  { letter: "B", name: "", attached: attachB, total: 2, options: [
    { idx: 6, text: "San Francisco (SFO)", picked: false, cx: 250, cy: 156 },
    { idx: 7, text: "2 Passenger Terminal Rd, San Francisco", picked: false, cx: 250, cy: 196 } ] },
] });

function recordingFetch(decisions, suggest = "B") {
  const queue = [...decisions];
  const seen = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const body = JSON.parse(opts.body);
    const all = body.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n")
      : String(m.content || "")));
    const joined = all.join("\n");
    const user = all[all.length - 1];
    let kind = "step";
    if (/which list, if any, is offering COMPLETIONS/.test(joined)) kind = "suggest";
    else if (/COMPOSE it, or is it CARRYING/.test(joined)) kind = "authored";
    else if (/You audit a browser agent's claim/.test(joined)) kind = "verify";
    else if (/You plan a task/.test(joined)) kind = "plan";
    else if (/pre-submit form auditor/.test(joined)) kind = "form-audit";
    else if (/what KIND of value that field is FOR/.test(joined)) kind = "kinds";
    // The login-wall question (audit #70) fires once a page has not moved
    // for two steps; answered NONE so it never eats a scripted step.
    else if (/ONE question about the page's PURPOSE/.test(joined)) kind = "wall";
    seen.push({ kind, user, joined });
    let content;
    if (kind === "suggest") content = suggest;
    else if (kind === "wall") content = "NONE";
    else if (kind === "authored") content = "CARRIED";
    else if (kind === "verify") content = JSON.stringify({ verified: true, evidence: ["ok"] });
    else if (kind === "plan") content = JSON.stringify({ steps: [] });
    else if (kind === "form-audit") content = JSON.stringify({ values: [] });
    else if (kind === "kinds") content = "{}";
    else {
      const next = queue.shift();
      content = JSON.stringify(typeof next === "function" ? next() : (next || { action: "wait" }));
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return seen;
}

function world({ afterType = null, always = null } = {}) {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.activationLog.length = 0;
  harness.onInject = null;
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  let typed = false;
  harness.onCdp = (tabId, method, params) => {
    if (method === "Page.captureScreenshot") return { data: FAKE_JPEG };
    if (method === "Input.dispatchKeyEvent" && params?.type === "char") typed = true;
    return undefined;
  };
  harness.mapPage = () => ({
    url: "https://fixture.test/flights",
    title: "Flights",
    elements: `[0] <textbox> From${typed ? ' [contains "SFO"]' : ""} @(250,116)\n[1] <textbox> To @(250,216)\n[2] <button> Search @(160,420)`,
    text: "Search flights.",
    fields: [
      { index: 0, name: "from", label: "From", type: "text", autocomplete: "", searchLike: false,
        required: false, readOnly: false, value: typed ? "SFO" : "" },
      { index: 1, name: "to", label: "To", type: "text", autocomplete: "", searchLike: false,
        required: false, readOnly: false, value: "" },
    ],
    sugg: always || (typed && afterType ? afterType : { lists: [] }),
  });
  harness.addTab({ url: "https://news.site/read", active: true });
}
const GOAL = "Search flights from SFO to Toronto";
const run = () => runAgentGoal(GOAL, {
  apiKey: "test-key", scope: GOAL, authorized: true, planning: false, maxSteps: 6,
  startUrl: "https://fixture.test/flights", stillLive: async () => true,
});

// (c1) type, then two unattached lists: asked once, B promoted, memoised.
{
  world({ afterType: LISTS(false) });
  const seen = recordingFetch([
    { action: "type", index: 0, text: "SFO", enter: false },
    { action: "wait" },
    { action: "done", result: "Searched." },
  ]);
  const out = await run();
  check("(c1) the scripted run finished", out?.status === "done", `${out?.status}: ${String(out?.result).slice(0, 120)}`);
  const steps = seen.filter((s) => s.kind === "step");
  const asks = seen.map((s, i) => (s.kind === "suggest" ? i : -1)).filter((i) => i >= 0);
  const stepAt = seen.map((s, i) => (s.kind === "step" ? i : -1)).filter((i) => i >= 0);
  check("(c1) three step prompts went out", steps.length === 3, String(steps.length));
  check("(c1) the question was asked EXACTLY ONCE across the type step and the wait-and-remap (memoised)",
    asks.length === 1, `${asks.length} asks: ${seen.map((s) => s.kind).join(",")}`);
  check("(c1) ...between the type step's prompt and the next step's prompt — after the type, before the model chose again",
    asks.length === 1 && asks[0] > stepAt[0] && asks[0] < stepAt[1], seen.map((s) => s.kind).join(","));
  const ask = seen[asks[0]] || { user: "", joined: "" };
  check("(c1) the ask named the box and what was typed, and listed every list",
    ask.user.includes("The box: «From»") && ask.user.includes("What was typed: «SFO»")
      && ask.user.includes("List A (Trip type)") && ask.user.includes("List B (unnamed)"), ask.user);
  const p1 = steps[1]?.user || "";
  const heading = p1.indexOf("--- SUGGESTIONS for «From» (attached to the box you typed into");
  const other = p1.indexOf("--- OTHER OPTION LIST: Trip type — not attached to that box");
  const sfo = p1.indexOf("[6] <option> San Francisco (SFO)");
  check("(c1) the next step prompt carries list B FIRST under the attached heading",
    heading >= 0 && sfo > heading && (other < 0 || sfo < other), p1.slice(Math.max(0, heading - 40), heading + 400));
  check("(c1) ...and Trip type under 'not attached', with Multi-city still clickable",
    other > 0 && p1.includes("[5] <option> Multi-city") && p1.indexOf("[5] <option> Multi-city") > other);
  check("(c1) ...and '2 Passenger Terminal Rd' present — the regex arm that ate addresses is gone",
    p1.includes("[7] <option> 2 Passenger Terminal Rd"));
  const elementsAt = p1.indexOf("ELEMENTS:"), valuesAt = p1.indexOf("CURRENT FORM VALUES:");
  check("(c1) the block sits inside ELEMENTS, where the step model reads controls",
    elementsAt >= 0 && heading > elementsAt && (valuesAt < 0 || heading < valuesAt));
  const p2 = steps[2]?.user || "";
  check("(c1) after the wait the remap is still headed by the memoised verdict, with no second ask",
    p2.includes("--- SUGGESTIONS for «From»") && p2.indexOf("[6] <option> San Francisco") > p2.indexOf("--- SUGGESTIONS for «From»"));
  check("(c1) the trace line the live leg counts is in the history the model reads",
    /suggestions: 2 lists visible, none attached — asked; verdict attached B/.test(p2), p2.slice(0, 600));
  check("(c1) the type step's own prompt had no option list (none was visible yet)",
    !/<option>/.test(steps[0]?.user || ""));
}

// (c2) the page attaches list B itself: no question, same headings.
{
  world({ afterType: LISTS(true) });
  const seen = recordingFetch([
    { action: "type", index: 0, text: "SFO", enter: false },
    { action: "done", result: "Searched." },
  ]);
  const out = await run();
  const steps = seen.filter((s) => s.kind === "step");
  check("(c2) run finished", out?.status === "done", `${out?.status}: ${String(out?.result).slice(0, 120)}`);
  check("(c2) a structurally attached list means NO model question — an ordinary autocomplete pays nothing",
    seen.filter((s) => s.kind === "suggest").length === 0, seen.map((s) => s.kind).join(","));
  const p1 = steps[1]?.user || "";
  check("(c2) ...and the block still heads B as attached and Trip type as not attached",
    p1.indexOf("--- SUGGESTIONS for «From»") >= 0 && p1.indexOf("[6] <option> San Francisco") > p1.indexOf("--- SUGGESTIONS for «From»")
      && /OTHER OPTION LIST: Trip type — not attached/.test(p1) && p1.includes("[5] <option> Multi-city"), p1.slice(-700));
}

// (c3) lists visible with nothing typed: no question, neutral heading, all there.
{
  world({ always: LISTS(false) });
  const seen = recordingFetch([
    { action: "wait" },
    { action: "done", result: "Nothing to do." },
  ]);
  const out = await run();
  const steps = seen.filter((s) => s.kind === "step");
  check("(c3) run finished", out?.status === "done", `${out?.status}: ${String(out?.result).slice(0, 120)}`);
  check("(c3) with no type behind them, two unattached lists are NOT asked about",
    seen.filter((s) => s.kind === "suggest").length === 0, seen.map((s) => s.kind).join(","));
  const p0 = steps[0]?.user || "";
  check("(c3) ...they are shown whole under the neutral heading, nothing promoted, nothing demoted",
    /VISIBLE OPTION LISTS/.test(p0) && !/SUGGESTIONS for/.test(p0) && !/not attached/.test(p0)
      && (p0.match(/^\[\d+\] <option>/gm) || []).length === 5, p0.slice(-700));
}

if (failures) {
  console.error(`test_suggestions_keep_every_option: ${failures} failed`);
  process.exit(1);
}
console.log("test_suggestions_keep_every_option: all passed");
