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

const { planRun, planBlock, pageFingerprint, isAuthored, AUTHORED_WORDS } = await import(join(ext, "agent_loop.js"));

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


// ------------------------------ words she wrote vs facts he gave

// She composed a whole email and pressed Send under his name. Told as a RULE
// in the agent prompt this changed nothing — measured, 3 of 3 still clicked
// Send. So it is a stop, and these pin where the line sits.
const EMAIL = "Hi Priya, just wanted to follow up on the invoice. Could you let me know the status when you get a chance? Thanks, Omar";
check(isAuthored(EMAIL, "Email Priya about the invoice", ""),
      "a composed message body is HERS and must be shown");
check(!isAuthored("Omar Ebrahim", "Book dinner for two at Cactus Club tomorrow at 7 PM", ""),
      "his own name typed into a form is not composition");
check(!isAuthored("7:00 PM", "Book dinner for two at 7pm", ""), "a time is not composition");
check(!isAuthored("omarkebrahim@gmail.com", "Email omarkebrahim@gmail.com the invoice", ""),
      "an address he gave is not composition");
check(!isAuthored("noise cancelling headphones under 400 dollars",
                  "Research noise cancelling headphones under 400 dollars", ""),
      "a search built from his own goal is not composition");
// LONG but still his: caught by mutation testing. Every other "not
// composition" case here is short, so making isAuthored return true for
// anything long left the suite green while breaking the actual distinction.
check(!isAuthored(
        "noise cancelling headphones under 400 dollars for travel and commuting on long flights",
        "Research the best noise cancelling headphones under 400 dollars for travel and "
        + "commuting on long flights", ""),
      "a LONG value made of his own words is still not composition");
check(!isAuthored("book a table for two", "book a table for two at seven", ""),
      "anything short is never composition");
check(isAuthored("Dear Sir or Madam, I am writing to enquire about the availability of your "
                 + "premises for a private event later this month, and would welcome a call.",
                 "ask about venue hire", ""),
      "long prose she invented is composition even when the goal is short");
check(AUTHORED_WORDS >= 10, "the threshold sits past anything he could have dictated as a field");

const loop2 = readFileSync(join(ext, "agent_loop.js"), "utf8");
check(/if \(!draftShown && isAuthored\(decision\.text, goal, scope\)\)/.test(loop2),
      "the stop is wired into the type path");
check(/draftShown = true;/.test(loop2), "and it only ever fires once per run");
const stopIdx = loop2.indexOf("if (!draftShown && isAuthored");
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
