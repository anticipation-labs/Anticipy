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

const { planRun, planBlock } = await import(join(ext, "agent_loop.js"));

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

globalThis.fetch = realFetch;
console.log(`\ntest_planner: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
