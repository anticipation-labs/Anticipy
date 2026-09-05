// WHETHER A MENU'S FIRST ENTRY MEANS "NOTHING CHOSEN" IS A VERDICT, NOT A
// WORD LIST — AND WITH NO VERDICT THE SEATBELT READS THE VALUE.
//
// Audit #73. page_map.js decided, for a <select> on its first entry, that the
// option MEANT "nothing chosen" when its label started with
// select/choose/pick/--/please/optional/none or contained "(optional)", and
// reported the value as "". That blank is a LOOSENING: unsupportedScopeFields
// skips a "" value, so the select was exempt from the seatbelt; and a first
// option that IS the answer — "None" under dietary requirements, "Pickup"
// under delivery — read as "" too, so the fact floor blocked a correct form
// ("these approved facts are not set") until the run died.
//
// HARNESS-LAWS.md law 1. What stays deterministic is what the form would
// SUBMIT: no option, an empty value attribute, a disabled option. A select on
// its first submittable entry is reported truthfully with firstOption +
// optionValue, and one question goes to a model at the pre-submit gates.
// FLOOR: only a positive PLACEHOLDER verdict blanks; VALUE, UNCLEAR, no
// judge and no answer all leave the value for the seatbelt to audit.
//
// THE MUTATIONS THAT MUST TURN THIS RED (each run and restored, see the
// commit): blank on anything but VALUE (`verdict !== "value"`) -> (b3);
// blank on UNCLEAR too -> (b3); the click gate audits the RAW state (never
// consulted) -> (c1); the disabled arm dropped from page_map -> (a).
//
// Run: node extension/tests/test_placeholder_is_a_verdict.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { installChrome } from "./chrome_mock.mjs";
import { FakeNode, installFakePage, evalPageMap } from "./fake_page.mjs";

const here = dirname(fileURLToPath(import.meta.url));
let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const harness = installChrome();
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
// Imported AFTER installChrome(): config.js reads chrome.storage at evaluation.
const {
  PLACEHOLDER_SYSTEM, placeholderVerdict, runAgentGoal, settleFirstOptions,
  unsupportedApprovedFacts, unsupportedScopeFields,
} = await import("../agent_loop.js");

// ---------------------------------------------------------------------------
// (a) THE PAGE SIDE. The real page_map.js against selects of every shape the
//     regex used to misread, and the three the form would not submit.
// ---------------------------------------------------------------------------
{
  const R = (x, y, width, height) => ({ x, y, width, height });
  const opt = (text, attrs = {}) => new FakeNode("option", attrs, [], { text });
  const sel = (name, label, options, y) =>
    new FakeNode("select", { name, "aria-label": label }, options, { rect: R(10, y, 200, 24) });
  const body = new FakeNode("body", {}, [], { rect: R(0, 0, 1280, 800) });
  const form = body.append(new FakeNode("form", {}, [], { rect: R(0, 0, 400, 400) }));
  form.append(sel("dietary", "Dietary requirements", [opt("None", { value: "none" }), opt("Vegetarian", { value: "veg" })], 10));
  form.append(sel("occasion", "Occasion", [opt("Select an occasion", { value: "" }), opt("Birthday", { value: "bd" })], 40));
  form.append(sel("delivery", "Delivery method", [opt("Choose…", { disabled: "", selected: "", hidden: "" }), opt("Pickup", { value: "pu" })], 70));
  form.append(sel("fulfil", "Fulfilment", [opt("Pickup", { value: "PU" }), opt("Delivery", { value: "DL" })], 100));
  form.append(sel("contact", "Contact preference", [opt("Please call me", { value: "please" }), opt("Email", { value: "email" })], 130));
  form.append(sel("size", "Party size", [opt("1", { value: "1" }), opt("2", { value: "2", selected: "" })], 160));
  form.append(sel("empty", "Nothing here", [], 190));
  form.append(sel("bare", "Bare options", [opt("-- Standard --"), opt("Express")], 220));

  const page = installFakePage({ body, url: "https://fixture.test/book" });
  const win = evalPageMap();
  const main = win.__anticipyMapPage();
  page.restore();
  const byName = Object.fromEntries(main.fields.map((f) => [f.name, f]));

  check("(a) 'None' on its first entry is reported as the value it is, with the structure a verdict needs",
    byName.dietary?.value === "None" && byName.dietary?.firstOption === true && byName.dietary?.optionValue === "none",
    JSON.stringify(byName.dietary));
  check("(a) 'Pickup' — a word the list blanked — is reported truthfully",
    byName.fulfil?.value === "Pickup" && byName.fulfil?.firstOption === true && byName.fulfil?.optionValue === "PU",
    JSON.stringify(byName.fulfil));
  check("(a) 'Please call me' — another — is reported truthfully",
    byName.contact?.value === "Please call me" && byName.contact?.firstOption === true, JSON.stringify(byName.contact));
  check("(a) an option with no value attribute submits its text, so it is a first entry with that text as its value",
    byName.bare?.value === "-- Standard --" && byName.bare?.firstOption === true && byName.bare?.optionValue === "-- Standard --",
    JSON.stringify(byName.bare));
  check("(a) an empty value attribute submits nothing: value \"\" and NO firstOption (never asked about)",
    byName.occasion?.value === "" && byName.occasion?.firstOption === undefined && byName.occasion?.optionValue === undefined,
    JSON.stringify(byName.occasion));
  check("(a) a disabled selected option submits nothing: value \"\" and NO firstOption",
    byName.delivery?.value === "" && byName.delivery?.firstOption === undefined, JSON.stringify(byName.delivery));
  check("(a) a select with no options submits nothing", byName.empty?.value === "" && byName.empty?.firstOption === undefined,
    JSON.stringify(byName.empty));
  check("(a) a select moved off its first entry is a plain value with no firstOption",
    byName.size?.value === "2" && byName.size?.firstOption === undefined, JSON.stringify(byName.size));
  check("(a) the * marker still shows the step model the truth in ELEMENTS",
    /Dietary requirements \(use select action; options: "None"\*, "Vegetarian"\)/.test(main.elements), main.elements);
  check("(a) no field carries an optionValue longer than 100 characters, and none but first entries carry one",
    main.fields.every((f) => (f.firstOption === true) === (typeof f.optionValue === "string") && String(f.optionValue || "").length <= 100));
}

// ---------------------------------------------------------------------------
// (b) THE VERDICT, through the exported functions with a scripted judge.
// ---------------------------------------------------------------------------
const dietaryField = () => ({ name: "dietary", label: "Dietary requirements", type: "select-one", index: 3,
  required: false, readOnly: false, value: "None", firstOption: true, optionValue: "none" });
const ELEMENTS = `[3] <combobox> Dietary requirements (use select action; options: "None"*, "Vegetarian", "Vegan") @(10,40)`;
const saying = (reply) => {
  const calls = [];
  return { calls, judge: async (args) => { calls.push(args); if (reply instanceof Error) throw reply; return reply; } };
};
const SCOPE = "book a table for four";

// (b1) VALUE: the truthful value passes the fact floor — today's run-dies block.
{
  const { judge, calls } = saying("VALUE");
  const state = { elements: ELEMENTS, fields: [dietaryField()] };
  const settled = await settleFirstOptions(state, judge, new Map());
  check("(b1) VALUE keeps 'None'", settled.state.fields[0].value === "None");
  check("(b1) ...and the fact floor passes dietary: None without any DOM rescue",
    unsupportedApprovedFacts("dietary: None", settled.state).length === 0,
    JSON.stringify(unsupportedApprovedFacts("dietary: None", settled.state)));
  check("(b1) the verdict is reported for the history line", JSON.stringify(settled.verdicts) === JSON.stringify([{ name: "dietary", verdict: "value" }]));
  check("(b1) the judge saw the field's structure and the page's own [idx] line",
    calls.length === 1 && calls[0].field.name === "dietary" && calls[0].elementLine === ELEMENTS);
  check("(b1) the input state was not mutated", state.fields[0].value === "None" && settled.state !== state);
}

// (b2) PLACEHOLDER: blank, so the seatbelt skips it and the fact floor sees no answer.
{
  const { judge } = saying("PLACEHOLDER");
  const settled = await settleFirstOptions({ elements: ELEMENTS, fields: [dietaryField()] }, judge, new Map());
  check("(b2) PLACEHOLDER blanks the value", settled.state.fields[0].value === "");
  check("(b2) ...the seatbelt does not list it", !unsupportedScopeFields(SCOPE, settled.state).includes("dietary"));
  check("(b2) ...and the fact floor lists dietary as not set",
    JSON.stringify(unsupportedApprovedFacts("dietary: None", settled.state)) === JSON.stringify(["dietary"]));
}

// (b3) THE POLARITY PIN. Every way of not getting a positive verdict keeps the
//      value, and the seatbelt STILL audits it.
{
  const arms = [
    ["the judge throws", saying(new Error("boom")).judge, "unanswered"],
    ["an empty reply", saying("").judge, "unanswered"],
    ["prose ('It looks like a placeholder')", saying("It looks like a placeholder").judge, "unanswered"],
    ["no judge at all", null, "unasked"],
    ["exactly UNCLEAR", saying("UNCLEAR").judge, "unclear"],
  ];
  for (const [name, judge, expected] of arms) {
    const settled = await settleFirstOptions({ elements: ELEMENTS, fields: [dietaryField()] }, judge, new Map());
    check(`(b3) ${name} -> ${expected}: the field still reads 'None'`,
      settled.state.fields[0].value === "None" && settled.verdicts[0]?.verdict === expected, JSON.stringify(settled.verdicts));
    check(`(b3) ${name}: ...and unsupportedScopeFields('${SCOPE}') STILL LISTS dietary — the seatbelt reads the value when nobody answered`,
      unsupportedScopeFields(SCOPE, settled.state).includes("dietary"), JSON.stringify(unsupportedScopeFields(SCOPE, settled.state)));
  }
  check("(b3) UNCLEAR, unasked and unanswered are three different labels",
    new Set([await placeholderVerdict(dietaryField(), ELEMENTS, saying("UNCLEAR").judge),
             await placeholderVerdict(dietaryField(), ELEMENTS, null),
             await placeholderVerdict(dietaryField(), ELEMENTS, saying("nope").judge)]).size === 3);
}

// (b4) An ordinary run pays nothing: nothing but a first submittable entry is ever asked about.
{
  const { judge, calls } = saying("PLACEHOLDER");
  const fields = [
    { name: "occasion", label: "Occasion", type: "select-one", index: 1, value: "", firstOption: true, optionValue: "" },
    { name: "size", label: "Party size", type: "select-one", index: 2, value: "2" },
    { name: "notes", label: "Notes", type: "text", index: 4, value: "window seat" },
    { name: "empty", label: "Nothing", type: "select-one", index: 5, value: "" },
  ];
  const settled = await settleFirstOptions({ elements: "", fields }, judge, new Map());
  check("(b4) zero judge calls for an empty-value first option, an index>0 select, a text box and an empty select",
    calls.length === 0, String(calls.length));
  check("(b4) ...and every value is exactly as the page held it",
    JSON.stringify(settled.state.fields.map((f) => f.value)) === JSON.stringify(["", "2", "window seat", ""]) && settled.verdicts.length === 0);
}

// (b5) The cache: a positive verdict is asked once per run; a no-verdict is asked again.
{
  const cache = new Map();
  const { judge, calls } = saying("VALUE");
  await settleFirstOptions({ elements: ELEMENTS, fields: [dietaryField()] }, judge, cache);
  await settleFirstOptions({ elements: ELEMENTS, fields: [dietaryField()] }, judge, cache);
  check("(b5) two settles of the same field with one cache: one call", calls.length === 1, String(calls.length));
  let n = 0;
  const flaky = async () => { n++; if (n === 1) throw new Error("timeout"); return "VALUE"; };
  const cache2 = new Map();
  const first = await settleFirstOptions({ elements: ELEMENTS, fields: [dietaryField()] }, flaky, cache2);
  const second = await settleFirstOptions({ elements: ELEMENTS, fields: [dietaryField()] }, flaky, cache2);
  check("(b5) UNANSWERED then VALUE: two calls — a no-verdict is never cached",
    n === 2 && first.verdicts[0].verdict === "unanswered" && second.verdicts[0].verdict === "value", `${n} ${JSON.stringify([first.verdicts, second.verdicts])}`);
  const { judge: unclear, calls: unclearCalls } = saying("UNCLEAR");
  const cache3 = new Map();
  await settleFirstOptions({ elements: ELEMENTS, fields: [dietaryField()] }, unclear, cache3);
  await settleFirstOptions({ elements: ELEMENTS, fields: [dietaryField()] }, unclear, cache3);
  check("(b5) UNCLEAR is an answer and is cached", unclearCalls.length === 1);
}

// (b6) REGRESSION PIN — a source read, labelled as such and green by
//      construction: the structural arm is there and the word list survives
//      only inside the WHAT WAS HERE record.
{
  const source = readFileSync(join(here, "..", "page_map.js"), "utf8");
  check("(b6) page_map.js blanks on option?.disabled (the form-data-set rule)", source.includes("!!option?.disabled"));
  const regexLines = source.split("\n").filter((line) => line.includes("/^(select|choose|pick|"));
  check("(b6) the word list appears only in comment lines", regexLines.length > 0 && regexLines.every((line) => line.trim().startsWith("//")),
    regexLines.join(" | "));
  check("(b6) the precondition the Python pin reads is still literal", source.includes("el.selectedIndex <= 0"));
  check("(b6) the system prompt names the three counter-examples the word list got wrong",
    /'None' under dietary requirements is an answer/.test(PLACEHOLDER_SYSTEM) && /'Pick up in store'/.test(PLACEHOLDER_SYSTEM) && /'Please call me'/.test(PLACEHOLDER_SYSTEM));
}

// ---------------------------------------------------------------------------
// (c) THE LOOP. The 2026-08-15 shape, offline: an optional select whose
//     index-0 option is "-- Select occasion --" with value "0" and a change
//     handler that snaps back to index 0, beside Dietary sitting on "None"
//     with fact dietary: None, behind a Book button.
// ---------------------------------------------------------------------------
let page = null;
let controls = {};
let clearAttempts = 0;
const realExecuteScript = chrome.scripting.executeScript;
chrome.scripting.executeScript = async (opts) => {
  const src = opts?.func ? String(opts.func) : "";
  const index = Array.isArray(opts?.args) ? Number(opts.args[0]) : null;
  if (src.includes("navigationLink")) {               // commitControl
    return [{ frameId: 0, result: !!controls[index]?.commit }];
  }
  if (src.includes("fieldsIn")) {                     // controlContext
    const c = controls[index];
    if (!c) return [{ frameId: 0, result: null }];
    return [{ frameId: 0, result: {
      label: c.label, tag: c.tag, href: "", nearbyText: c.label,
      formAction: c.formAction, name: c.name || "", elementId: c.elementId || "",
      fieldIndexes: c.fieldIndexes,
    } }];
  }
  if (src.includes("el.required || el.readOnly")) {    // the optional-field clear: "works", then the page snaps back
    clearAttempts++;
    return [{ frameId: 0, result: true }];
  }
  return realExecuteScript(opts);
};

function bookingWorld() {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.activationLog.length = 0;
  harness.onInject = null;
  harness.onCdp = (tabId, method) => (method === "Page.captureScreenshot" ? { data: FAKE_JPEG } : undefined);
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  clearAttempts = 0;
  page = {
    url: "https://fixture.test/book",
    title: "Book a table",
    elements: `[1] <combobox> Occasion (use select action; options: "-- Select occasion --"*, "Birthday", "Anniversary") @(10,10)\n`
      + `[2] <combobox> Dietary requirements (use select action; options: "None"*, "Vegetarian", "Vegan") @(10,40)\n`
      + `[3] <textbox> Notes @(10,70)\n[4] <button> Book now @(10,100)`,
    text: "Book a table.",
    fields: [
      { index: 1, name: "occasion", label: "Occasion", type: "select-one", required: false, readOnly: false,
        value: "-- Select occasion --", firstOption: true, optionValue: "0" },
      { index: 2, name: "dietary", label: "Dietary requirements", type: "select-one", required: false, readOnly: false,
        value: "None", firstOption: true, optionValue: "none" },
      // Required and wrong under every reading: attempt 1 blocks on it, so
      // attempt 2 exists and the cache is observable.
      { index: 3, name: "notes", label: "Notes", type: "text", required: true, readOnly: false, value: "OLD-4" },
    ],
  };
  controls = { 4: { commit: true, label: "Book now", tag: "button", name: "", elementId: "book",
                    formAction: "https://fixture.test/book", fieldIndexes: [1, 2, 3] } };
  harness.mapPage = () => page;
  harness.addTab({ url: "https://news.site/read", active: true });
}

function bookingFetch(decisions, { judgeDown = false } = {}) {
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
    if (/is that entry a real answer, or a prompt standing in for/.test(joined)) kind = "menu";
    else if (/what KIND of value that field is FOR/.test(joined)) kind = "kinds";
    else if (/You audit a browser agent's claim/.test(joined)) kind = "verify";
    else if (/pre-submit form auditor/.test(joined)) kind = "form-audit";
    else if (/You plan a task/.test(joined)) kind = "plan";
    else if (/reading the open web to learn HOW/.test(joined)) kind = "learn";
    // The login-wall question (audit #70) fires once a page has not moved
    // for two steps; answered NONE so it never eats a scripted step.
    else if (/ONE question about the page's PURPOSE/.test(joined)) kind = "wall";
    seen.push({ kind, user, joined, system: all[0] });
    if (kind === "menu" && judgeDown) {
      return { ok: false, status: 400, json: async () => ({}), text: async () => "" };
    }
    let content;
    if (kind === "menu") content = /name: occasion/.test(user) ? "PLACEHOLDER" : /name: dietary/.test(user) ? "VALUE" : "UNCLEAR";
    else if (kind === "wall") content = "NONE";
    else if (kind === "kinds") content = "{}";
    else if (kind === "verify") content = JSON.stringify({ verified: true, evidence: ["confirmed"] });
    else if (kind === "form-audit") content = JSON.stringify({ values: [] });
    else if (kind === "plan" || kind === "learn") content = JSON.stringify({ steps: [] });
    else {
      const next = queue.shift();
      content = JSON.stringify(typeof next === "function" ? next() : (next || { action: "wait" }));
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return seen;
}

const GOAL = "Book a table for four at 7:30 tomorrow";
async function bookingRun(seenHistory) {
  let effects = 0;
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, facts: "dietary: None", authorized: true, planning: false,
    maxSteps: 6, startUrl: page.url, stillLive: async () => true,
    onBeforeExternalEffect: async () => { effects += 1; },
    onTrace: async (history) => { seenHistory.length = 0; seenHistory.push(...history); },
  });
  return { out, effects };
}

// (c1) the judge answers: occasion=placeholder, dietary=value — the form goes out.
{
  bookingWorld();
  const history = [];
  const seen = bookingFetch([
    { action: "click", index: 4 },
    // "The model fixed Notes": the page now reads as if the value were gone.
    () => { page.fields[2].value = ""; return { action: "click", index: 4 }; },
    { action: "done", result: "Booked" },
  ]);
  const { out, effects } = await bookingRun(history);
  check("(c1) the run reaches the submit and finishes", out?.status === "done" && effects === 1,
    `${out?.status} effects=${effects}: ${String(out?.result).slice(0, 120)}`);
  check("(c1) the history carries the verdicts, one line per settle: occasion=placeholder, dietary=value",
    history.some((line) => /menu verdicts: occasion=placeholder, dietary=value/.test(line)), history.join("\n"));
  const blocks = history.filter((line) => /PRE-SUBMIT BLOCK/.test(line));
  check("(c1) no PRE-SUBMIT BLOCK ever names occasion or dietary — the placeholder was exempt, and 'None' evidenced its fact",
    blocks.every((line) => !/occasion|dietary/.test(line)), blocks.join("\n"));
  check("(c1) ...the only block was the required Notes box, which is what made attempt 2 exist",
    blocks.length === 1 && /notes/.test(blocks[0]), blocks.join("\n"));
  check("(c1) the optional placeholder select was never 'cleared' — no select/clear thrash", clearAttempts === 0, String(clearAttempts));
  check("(c1) the verifier reads the same audited state the gate passed: the done claim is not rejected for the placeholder",
    !history.some((line) => /done claim rejected/.test(line)), history.filter((line) => /done claim/.test(line)).join("\n"));
  const menus = seen.filter((s) => s.kind === "menu");
  check("(c1) the judge was asked exactly twice for two attempts — once per first-entry select, then cached",
    menus.length === 2, `${menus.length}: ${seen.map((s) => s.kind).join(",")}`);
  const occasion = menus.find((m) => /name: occasion/.test(m.user));
  check("(c1) the ask is one question on its own, with the verbatim system prompt",
    !!occasion && occasion.system === PLACEHOLDER_SYSTEM);
  check("(c1) ...carrying the field's label, name, the entry's text and its submitted value, and the page's own menu line",
    !!occasion && /The field: Occasion \(name: occasion\)/.test(occasion.user)
      && /The entry it sits on: "-- Select occasion --" — submitted as "0"/.test(occasion.user)
      && /The whole menu, as the page lists it: \[1\] <combobox> Occasion \(use select action; options: "-- Select occasion --"\*/.test(occasion.user),
    occasion?.user);
  check("(c1) ...and no other field's value", !!occasion && !occasion.user.includes("OLD-4") && !occasion.user.includes("Vegetarian"));
  check("(c1) the submitted payload the duplicate guard keys on is the RAW form: the digest is not a verdict's to change",
    history.some((line) => /menu verdicts/.test(line)) && effects === 1);
}

// (c2) the judge is down: the FLOOR refuses — the site default on occasion is
//      audited, 'None' still evidences its fact, and nothing is submitted.
{
  bookingWorld();
  page.fields[2].value = "";   // Notes already fine: only the menus stand between the run and the submit
  const history = [];
  const seen = bookingFetch([
    { action: "click", index: 4 },
    { action: "click", index: 4 },
    { action: "done", result: "Booked" },
  ], { judgeDown: true });
  const { out, effects } = await bookingRun(history);
  check("(c2) nothing was submitted", effects === 0, `effects=${effects} ${out?.status}: ${String(out?.result).slice(0, 120)}`);
  check("(c2) the history says nobody answered: occasion=unanswered, dietary=unanswered",
    history.some((line) => /menu verdicts: occasion=unanswered, dietary=unanswered/.test(line)), history.join("\n"));
  const blocks = history.filter((line) => /PRE-SUBMIT BLOCK/.test(line));
  check("(c2) the seatbelt AUDITED the site default sitting on occasion — with no verdict the value is not exempt",
    blocks.some((line) => /not supported by what the owner approved: .*occasion/.test(line)), blocks.join("\n"));
  check("(c2) ...while 'None' stayed and evidenced dietary: None — no 'approved facts are not set'",
    !blocks.some((line) => /approved facts are not set/.test(line)), blocks.join("\n"));
  check("(c2) a no-verdict is asked again on the next attempt, never cached",
    seen.filter((s) => s.kind === "menu").length > 2, seen.map((s) => s.kind).join(","));
}
chrome.scripting.executeScript = realExecuteScript;

if (failures) {
  console.error(`test_placeholder_is_a_verdict: ${failures} failed`);
  process.exit(1);
}
console.log("test_placeholder_is_a_verdict: all passed");
