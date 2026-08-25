// THE TAKEOVER LIST, against a page built to defeat it.
//
// Card HANDS 3's first bullet: "credential fields, payment fields — never
// touched, even inside an approved plan." That is a claim about behaviour, so
// this suite is built as a reproduction rather than a unit test:
//
//   PART 1 parses extension/tests/hostile_checkout.html — a real page, openable
//   in Chrome — into faithful DOM stubs and runs the SHIPPED extraction
//   (`readDeclaredKind`, the exact function chrome.scripting injects) and the
//   SHIPPED stop (`protectedInput`) over every control in it. There is one
//   page, so the fixture and the manual proof cannot drift apart.
//
//   PART 2 drives the real step loop (`runAgentGoal`) at two of those controls
//   with `authorized: true` and a scope that plainly approves the errand, which
//   is the "even inside an approved plan" half. A guard that only holds when
//   nobody authorised anything is not a guard.
//
// WHAT PART 1 CAUGHT THE DAY IT WAS WRITTEN (all four now fixed, and each is a
// mutation in research/2026-08-25-hands3.md):
//   row 2  a "show password" toggle — type="text", autocomplete="current-password"
//   row 3  autocomplete="section-blue billing cc-number" (the spec's own syntax)
//   row 4  the card-expiry <select>, i.e. every checkout in the world
//   row 5/6 a <textarea> and a contenteditable <div>
// Rows 4, 5 and 6 shared one root cause: the extraction returned `{}` for
// anything that was not an <input>, and `{}` is what the stop reads as "an
// ordinary field, go ahead."
//
// Run: node extension/tests/test_takeover_list.mjs
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { installChrome } from "./chrome_mock.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const harness = installChrome();
const { protectedInput, readDeclaredKind, unquotedCode, runAgentGoal } =
  await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// ---------------------------------------------------------------- the fixture
//
// A scanner over a file THIS REPO WROTE, to build DOM stubs out of it. Law 1
// permits pattern-matching in tests without reservation, and this one decides
// nothing about meaning: it reads our own page back so that the assertions
// below are made against the page a person can open, not against a
// hand-written object that quietly agrees with the code.
// Comments stripped FIRST. The page documents itself heavily, and the comment
// above row 8 contains the words "<label>" — which swallowed the real
// `<label for="h8">Credit card number</label>` on the first run and quietly
// turned that row's assertion into a test of nothing. A browser would never
// have made that mistake, so neither may the reader.
const html = readFileSync(join(here, "hostile_checkout.html"), "utf8")
  .replace(/<!--[\s\S]*?-->/g, "");

function parseAttrs(source) {
  const out = {};
  const re = /([a-zA-Z][a-zA-Z0-9-]*)(?:\s*=\s*"([^"]*)")?/g;
  let m;
  while ((m = re.exec(source))) out[m[1].toLowerCase()] = m[2] === undefined ? "" : m[2];
  return out;
}

// id -> the text a <label>/<span> carries, so aria-labelledby and el.labels
// resolve the way they do in a browser.
const labelledBy = new Map();   // id of the span/label -> its text
const labelFor = new Map();     // "for" target id -> the label's text
for (const m of html.matchAll(/<(label|span)\b([^>]*)>([^<]*)</g)) {
  const a = parseAttrs(m[2]);
  if (a.id) labelledBy.set(a.id, m[3].trim());
  if (a.for) labelFor.set(a.for, m[3].trim());
}

// A DOM stub that mirrors the IDL, not the attributes: a browser gives
// `input.type` the value "text" when the attribute is absent, gives
// `select.type` "select-one", and gives a <div> no `.type` at all. Getting
// that wrong would make the suite easier to pass than the real page.
function stub(tag, attrs) {
  const labelable = ["input", "select", "textarea"].includes(tag);
  const el = {
    tagName: tag.toUpperCase(),
    id: attrs.id || "",
    isContentEditable: String(attrs.contenteditable || "") === "true",
    getAttribute: (n) => (n.toLowerCase() in attrs ? attrs[n.toLowerCase()] : null),
  };
  if (labelable) {
    el.name = attrs.name || "";
    el.autocomplete = attrs.autocomplete || "";
    el.placeholder = attrs.placeholder || "";
    el.type = tag === "input" ? (attrs.type || "text").toLowerCase()
      : tag === "select" ? "select-one" : "textarea";
    const text = labelFor.get(attrs.id);
    el.labels = text ? [{ textContent: text }] : [];
  }
  return el;
}

const controls = [];
for (const m of html.matchAll(/<(input|select|textarea|div)\b([^>]*)>/g)) {
  const attrs = parseAttrs(m[2]);
  if (!attrs["data-expect"]) continue;
  controls.push({ id: attrs.id, expect: attrs["data-expect"], el: stub(m[1], attrs) });
}

// The page-side function reads `window.__anticipyMap` and `document`, because
// that is where it runs. Give it both, then call it exactly as chrome.scripting
// would — by index into the map.
globalThis.window = globalThis.window || {};
globalThis.window.__anticipyMap = {};
globalThis.document = {
  getElementById: (id) => (labelledBy.has(id)
    ? { textContent: labelledBy.get(id) } : null),
};
controls.forEach((c, i) => { globalThis.window.__anticipyMap[i] = c.el; });

check(`the hostile page yields controls to test (${controls.length})`,
  controls.length >= 13);

// ------------------------------------------------ PART 1: every control, once
const gaps = [];
controls.forEach((c, i) => {
  const meta = readDeclaredKind(i);
  const stop = protectedInput(meta);
  if (c.expect === "refuse") {
    check(`#${c.id} is refused — ${labelFor.get(c.id) || meta.attrs || c.id}`,
      typeof stop === "string" && /^refused:/.test(stop));
  } else if (c.expect === "allow") {
    check(`#${c.id} is NOT refused (an ordinary field must still be fillable)`,
      stop === null);
  } else if (c.expect === "code-guard") {
    // protectedInput lets it through on purpose; the code guard owns it, and
    // owns it in a way that still permits a code the owner actually gave.
    const invented = unquotedCode("666666", meta.attrs, "sign me up", "sign me up", "");
    const given = unquotedCode("742913", meta.attrs, "sign me up", "sign me up",
      "verification_code: 742913");
    check(`#${c.id} is left to the code guard, which refuses an invented code`,
      stop === null && typeof invented === "string" && given === null);
  } else if (c.expect === "known-gap") {
    gaps.push({ id: c.id, caught: stop !== null, attrs: meta.attrs });
  }
});

// A gap that is written down is a gap the next agent does not rediscover
// (law 4). It is REPORTED, never pinned: pinning it red would block the only
// honest fix, and pinning it green would forbid one.
for (const g of gaps) {
  console.log(`NOTE: known gap #${g.id} — ${g.caught ? "now caught" : "still not caught"}`
    + ` (declares nothing; only its wording says what it is: "${g.attrs}")`);
}

// --------------------------------- the shape of the refusal, not just its fact
{
  const pw = controls.findIndex((c) => c.id === "h2");
  const card = controls.findIndex((c) => c.id === "h4");
  check("a disguised password field says PASSWORD, not something generic",
    /password field/.test(protectedInput(readDeclaredKind(pw)) || ""));
  check("a card field says PAYMENT-CARD",
    /payment-card field/.test(protectedInput(readDeclaredKind(card)) || ""));
}

// ------------------------------------- an element the map no longer holds
check("a vanished element reads as nothing, and nothing is not a green light",
  JSON.stringify(readDeclaredKind(999)) === "{}"
  && protectedInput(readDeclaredKind(999)) === null);
// ^ Stated out loud because it is the one place this design is fail-OPEN. It
//   has to be: `{}` also means "a <button>", and refusing every unreadable
//   control would park every run on the first frame that re-rendered. What
//   makes that survivable is that a field the map cannot read is a field the
//   loop cannot focus either — and it is why the extraction must cover every
//   control kind that CAN be written to, which is what rows 4-6 are about.

// ------------------------------- PART 2: through the real loop, when approved
function scripted(actions) {
  const a = [...actions];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const body = JSON.parse(opts.body);
    const joined = body.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n")
      : String(m.content || ""))).join("\n");
    let content;
    if (/You plan a task/.test(joined)) {
      content = JSON.stringify({ start_url: "https://shop.example.com/checkout",
        why: "the checkout", steps: [], unfamiliar: false });
    } else if (/You audit a browser agent's claim/.test(joined)) {
      content = JSON.stringify({ verified: false, reason: "nothing was submitted" });
    } else {
      content = JSON.stringify(a.shift() || { action: "wait" });
    }
    return { ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
}

// The loop asks the page two different questions on the select door. Answer
// both from the SAME stub the fixture built, so part 2 exercises the same
// extraction part 1 does rather than a convenient constant.
function answerFrom(control) {
  globalThis.window.__anticipyMap = { 0: control.el };
  harness.onInject = (src) => {
    if (src.includes("readDeclaredKind")) return readDeclaredKind(0);
    // The select door's "is this really a <select>" probe.
    if (src.includes('getAttribute("role")')) {
      return { tag: control.el.tagName, type: control.el.type || "", role: "" };
    }
    return undefined;
  };
}

function freshTab() {
  harness.tabs.clear();
  delete harness.storageData.agentTabs;
  delete harness.storageData.recipes;
  harness.addTab({ url: "https://news.site/read", active: true });
}

// --- the card-expiry dropdown, inside a plan the owner authorized
{
  freshTab();
  const expiry = controls.find((c) => c.id === "h4");
  answerFrom(expiry);
  harness.mapPage = () => ({
    url: "https://shop.example.com/checkout",
    title: "Checkout",
    elements: '[0] <combobox> Expiry month (use select action; options: "Month", "09")',
    text: "Pay for your order.",
    fields: [{ index: 0, label: "Expiry month", type: "select-one", value: "" }],
  });
  scripted([{ action: "select", index: 0, option: "09" },
            { action: "done", result: "paid" }]);
  const out = await runAgentGoal("finish paying for the order", {
    apiKey: "test-key", scope: "finish paying for the order with my saved card",
    authorized: true, planning: false, stillLive: async () => true,
    ownerProfile: { first_name: "Omar", email: "omar@example.test" },
  });
  check("an APPROVED, AUTHORIZED plan still cannot touch a card-expiry select",
    out.status === "needs_user" && /payment-card field/.test(String(out.result)));
  check("...and it hands the tab back rather than dropping the errand",
    typeof out.tabId === "number");
}

// --- the show-password toggle, same conditions
{
  freshTab();
  const shown = controls.find((c) => c.id === "h2");
  answerFrom(shown);
  harness.mapPage = () => ({
    url: "https://shop.example.com/signin",
    title: "Sign in",
    elements: "[0] <textbox> Password (visible) @(10,10)",
    text: "Enter your password to continue to checkout.",
    fields: [{ index: 0, label: "Password (visible)", value: "" }],
  });
  scripted([{ action: "type", index: 0, text: "hunter2" },
            { action: "done", result: "signed in" }]);
  const out = await runAgentGoal("sign in and finish the order", {
    apiKey: "test-key", scope: "sign in as me and finish the order",
    authorized: true, planning: false, stillLive: async () => true,
    ownerProfile: { first_name: "Omar", email: "omar@example.test" },
  });
  check("a password box declared type=\"text\" is refused through the type door",
    out.status === "needs_user" && /password field/.test(String(out.result)));
}

console.log(failures === 0
  ? `test_takeover_list: ${controls.length} hostile controls, credential and payment fields untouchable through both write doors`
  : `test_takeover_list: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
