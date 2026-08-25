// The planner must never be able to break a run.
//
// It exists because the loop had no idea where it was going: every job opened
// a hardcoded search page, so step 1 was always "type the goal into the box".
// "Send email to Andy from Barry" burned 19 steps on a Bing results page.
//
// But a planner that can fail a run is worse than no planner. So the rule is
// absolute: EVERY failure path returns null, and a null plan means the run
// behaves exactly as it did before this code existed. These tests are the
// wall, and each one is written so that removing the guard it covers makes it
// fail.
//
// Run: node extension/tests/test_planner.mjs

import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ext = join(here, "..");

// agent_loop.js touches `chrome` at import time only inside functions, but a
// bare import still needs the global to exist for the module to evaluate.
globalThis.chrome = globalThis.chrome || {
  tabs: { query: async () => [], create: async () => ({ id: 1 }), remove: async () => {} },
  storage: { local: { get: async () => ({}), set: async () => {} } },
  runtime: {}, debugger: {}, tabGroups: {}, notifications: {}, alarms: {},
};

const { planRun, planBlock, pageFingerprint, isAuthored } = await import(join(ext, "agent_loop.js"));

let pass = 0, fail = 0;
const realFetch = globalThis.fetch;
function check(ok, name) {
  if (ok) { pass++; console.log(`  ok    ${name}`); }
  else { fail++; console.log(`  FAIL  ${name}`); }
}
const reply = (content) => async () => ({
  ok: true, json: async () => ({ choices: [{ message: { content } }] }),
});

// ------------------------------------------------------- it produces a plan

globalThis.fetch = reply(JSON.stringify({
  start_url: "https://mail.google.com",
  why: "owner uses gmail",
  must_find: ["Andy's address, from contacts"],
  steps: ["open gmail", "compose"],
  fallback_urls: ["https://outlook.com"],
  ask_owner: null,
}));
let p = await planRun("k", "m", "send email to Andy", { first_name: "Omar" }, "");
check(p && p.startUrl === "https://mail.google.com/", "a good plan comes back with its start url");
check(p && p.mustFind.length === 1, "must_find survives");
check(p && p.askOwner === null, "a null ask_owner stays null");

// --------------------------------------------------- every failure is null

globalThis.fetch = async () => { throw new Error("network down"); };
check((await planRun("k", "m", "goal", null, "")) === null, "a network failure plans nothing");

globalThis.fetch = async () => ({ ok: false, status: 429, json: async () => ({}) });
check((await planRun("k", "m", "goal", null, "")) === null, "a rate limit plans nothing");

globalThis.fetch = reply("I think you should open Gmail!");
check((await planRun("k", "m", "goal", null, "")) === null, "prose instead of JSON plans nothing");

globalThis.fetch = reply("{ not valid json at all ");
check((await planRun("k", "m", "goal", null, "")) === null, "malformed JSON plans nothing");

globalThis.fetch = reply(JSON.stringify({ why: "no url given" }));
check((await planRun("k", "m", "goal", null, "")) === null, "a plan with no start_url plans nothing");

for (const bad of ["javascript:alert(1)", "file:///etc/passwd", "chrome://settings",
                   "data:text/html,<h1>x", "not a url", "", null, 42]) {
  globalThis.fetch = reply(JSON.stringify({ start_url: bad, why: "x" }));
  check((await planRun("k", "m", "goal", null, "")) === null,
        `an unusable start_url is refused: ${JSON.stringify(bad)}`);
}

globalThis.fetch = reply(JSON.stringify({ start_url: "https://ok.example" }));
check((await planRun("", "m", "goal", null, "")) === null, "no api key plans nothing");
check((await planRun("k", "m", "", null, "")) === null, "no goal plans nothing");

// ------------------------------------------------- it cannot run away with it

globalThis.fetch = reply(JSON.stringify({
  start_url: "https://ok.example",
  must_find: Array(50).fill("x"), steps: Array(50).fill("y"),
  fallback_urls: Array(50).fill("https://z.example"),
}));
p = await planRun("k", "m", "goal", null, "");
check(p.mustFind.length <= 6 && p.steps.length <= 8 && p.fallbacks.length <= 4,
      "a runaway plan is truncated, not pasted whole into every step");

globalThis.fetch = reply(JSON.stringify({
  start_url: "https://ok.example", must_find: "not-an-array", steps: { a: 1 },
}));
p = await planRun("k", "m", "goal", null, "");
check(p && Array.isArray(p.mustFind) && Array.isArray(p.steps),
      "wrong-typed fields degrade to empty lists rather than throwing");

// ------------------------------------------------------- the injected text

check(planBlock(null) === "", "no plan injects NOTHING into the step prompt");
const block = planBlock({ startUrl: "https://mail.google.com", why: "gmail",
                          mustFind: ["addr"], steps: ["a", "b"], fallbacks: [], askOwner: null });
check(block.includes("mail.google.com"), "the plan reaches the step prompt");
check(/guidance, not orders|real page always wins/i.test(block),
      "the plan is framed as guidance the page can override, never as orders");

// --------------------------------------------- the old default still exists

const src = readFileSync(join(ext, "agent_loop.js"), "utf8");
check(/startUrl = "https:\/\/www\.bing\.com\/"/.test(src),
      "the pre-planner default is still there as the fallback");
check(/const openAt = \(plan && plan\.startUrl\) \|\| startUrl;/.test(src),
      "a null plan falls back to exactly that default");
check(/planning && !opts\.startUrl/.test(src),
      "an explicit start_url on the job still wins over the planner");

// ------------------------------------ progress means the PAGE changed

// The loop used to treat ONLY a url change as progress, so anything that
// happens in one place — a spreadsheet, composing mail, a long form, any
// single-page app — looked frozen from step one and was killed at nineteen
// while genuinely working. These pin the replacement.
const sheet = { url: "https://docs.google.com/spreadsheets/d/abc/edit",
                elements: "e".repeat(400), text: "t".repeat(9000) };
check(pageFingerprint(sheet) === pageFingerprint({ ...sheet }),
      "an unchanged page fingerprints the same (a real stall is still caught)");
check(pageFingerprint(sheet) !== pageFingerprint({ ...sheet, text: "t".repeat(9001) }),
      "SPREADSHEET: same url, one more character typed, counts as progress");
check(pageFingerprint(sheet) !== pageFingerprint({ ...sheet, text: "u".repeat(9000) }),
      "equal-sized but different page text counts as progress");
check(pageFingerprint(sheet) !== pageFingerprint({ ...sheet, elements: "e".repeat(401) }),
      "same url, a new element appeared (menu/dialog/row), counts as progress");
check(pageFingerprint(sheet) !== pageFingerprint({ ...sheet, url: sheet.url + "#gid=2" }),
      "navigation still counts as progress");
check(pageFingerprint(undefined) === "|0|0" && pageFingerprint({}) === "|0|0",
      "a missing or empty state does not throw");
check(pageFingerprint(undefined) === pageFingerprint({}),
      "and two empty states agree, so a broken map does not read as progress");

const loopSrc = readFileSync(join(ext, "agent_loop.js"), "utf8");
check(/const fingerprint = pageFingerprint\(state\);/.test(loopSrc),
      "the loop actually uses the fingerprint");
check(!/if \(state\.url !== lastUrl\) \{ stuckStreak = 0; stepsOnPage = 0; \}/.test(loopSrc),
      "the old url-only progress test is gone");
check(/if \(!researched\)/.test(loopSrc),
      "it researches before giving up");
check(/researched = true;/.test(loopSrc),
      "and researches only once per run");
check(/FORM VALUES: answer each field's LABEL/.test(loopSrc)
      && /CURRENT FORM VALUES:/.test(loopSrc),
      "field values are grounded in the exact authority and shown before submit");
check(/const boundedPayload/.test(loopSrc) && /Math\.min\(4096/.test(loopSrc),
      "every model call has a bounded output budget");
const submitBlock = loopSrc.indexOf("PRE-SUBMIT BLOCK — these visible values");
check(submitBlock > 0 && loopSrc.indexOf("delete actionCounts[sig]", submitBlock) > submitBlock,
      "a safety-blocked submit is not counted as a dead page click");


// ------------------------------ words she wrote vs facts he gave

// She composed a whole email and pressed Send under his name. Told as a RULE
// in the agent prompt this changed nothing — measured, 3 of 3 still clicked
// Send. So it is a stop, and these pin where the line sits.
//
// AUDIT #66, fixed 2026-08-24. This stop used to be a 12-word floor and a 0.6
// novelty ratio. Owner: "Tell the clinic I can do Friday morning but not
// Thursday afternoon." Composed: "Hi, I can do Thursday afternoon but not
// Friday morning, thanks." Every token is his, the overlap is ~1.0, the
// negation IS kept — so the ratio said "not composition", no draft was shown,
// and the swapped appointment went out in his name. Five everyday sentences
// did this on the shipped function. test_authored_draft.mjs owns that boundary
// in full; what is pinned here is the contract the loop stands on.
const EMAIL = "Hi Priya, just wanted to follow up on the invoice. Could you let me know the status when you get a chance? Thanks, Omar";
const COMPOSED = async () => "COMPOSED";
check(await isAuthored(EMAIL, "Email Priya about the invoice", "", { judge: COMPOSED }),
      "a composed message body is HERS and must be shown");
check(await isAuthored(EMAIL, "Email Priya about the invoice", ""),
      "...and with no model to read it, it is still shown rather than sent");
check(!(await isAuthored("Omar Ebrahim", "Book dinner for two at Cactus Club tomorrow at 7 PM",
                         "", { profile: { first_name: "Omar Ebrahim" }, judge: COMPOSED })),
      "his own name, verbatim from his profile, never reaches a model at all");
check(!(await isAuthored("noise cancelling headphones under 400 dollars",
                         "Research noise cancelling headphones under 400 dollars", "",
                         { judge: COMPOSED })),
      "a search built from his own goal is carried, whatever a model would say");
check(!(await isAuthored("omarkebrahim@gmail.com", "Email omarkebrahim@gmail.com the invoice",
                         "", { judge: COMPOSED })),
      "an address he gave is carried, verbatim");
// LONG but still his: caught by mutation testing. Every other "not
// composition" case here is short, so making isAuthored return true for
// anything long left the suite green while breaking the actual distinction.
check(!(await isAuthored(
        "noise cancelling headphones under 400 dollars for travel and commuting on long flights",
        "Research the best noise cancelling headphones under 400 dollars for travel and "
        + "commuting on long flights", "", { judge: COMPOSED })),
      "a LONG value made of his own words, verbatim, is still not composition");
// SHORT IS NO LONGER A FREE PASS. "Cancel my 3pm" is four words and is a
// message; the 12-word floor waved every one of those straight through.
check(await isAuthored("Please cancel it, thanks", "cancel my appointment", "",
                       { judge: COMPOSED }),
      "a SHORT sentence the agent wrote is composition — the word floor is gone");
check(await isAuthored("Dear Sir or Madam, I am writing to enquire about the availability of your "
                 + "premises for a private event later this month, and would welcome a call.",
                 "ask about venue hire", "", { judge: COMPOSED }),
      "prose she invented is composition");
// FAIL CLOSED. Not being able to decide shows him the draft.
check(await isAuthored("Hi, I can do Thursday afternoon but not Friday morning, thanks.",
                       "send a message",
                       "Tell the clinic I can do Friday morning but not Thursday afternoon."),
      "with no model to read it, the inversion is shown rather than sent");

const loop2 = readFileSync(join(ext, "agent_loop.js"), "utf8");
check(/if \(!draftShown && await composedByTheAgent\(decision\.text,/.test(loop2),
      "the stop is wired into the type path");
check(/draftShown = true;/.test(loop2), "and it only ever fires once per run");
const stopIdx = loop2.indexOf("if (!draftShown && await composedByTheAgent(decision.text,");
const enterIdx = loop2.indexOf("await pressEnter(tab.id);", stopIdx);
check(stopIdx > 0 && enterIdx > stopIdx, "it stops BEFORE the keystroke that commits");

// ------------------------------ the field's own verdict
const pm = readFileSync(join(ext, "page_map.js"), "utf8");
check(/window\.__anticipyValidity/.test(pm), "the page exposes its own validity verdict");
const vBlock = pm.slice(pm.indexOf("window.__anticipyValidity"),
                        pm.indexOf("window.__anticipyClear"));
check(/activeEditable\(\) \|\| window\.__anticipyMap\[idx\]/.test(vBlock),
      "validated on the field that actually received the text, not the mapped placeholder");
check(/checkValidity/.test(pm) && !/@|gmail|email address regex/i.test(
        pm.slice(pm.indexOf("__anticipyValidity"), pm.indexOf("__anticipyValidity") + 900)),
      "it asks the browser rather than knowing about formats itself");
const bad = loop2.indexOf("const bad = await fieldRejects");
const enter2 = loop2.indexOf("await pressEnter(tab.id);", bad);
check(bad > 0 && enter2 > bad, "a rejected value is never committed with Enter");

globalThis.fetch = realFetch;
console.log(`\ntest_planner: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
