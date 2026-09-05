// READING THE CACHE COSTS NOTHING, SO IT MUST NOT BE BEHIND A JUDGEMENT.
//
// HANDS 1, §5.2 of docs/superpowers/specs/2026-08-25-hands1-skills-reach.md:
// one condition — `plan.unfamiliar` — controlled BOTH whether to spend money
// researching AND whether to read the cache at all. Those are not the same
// question and they do not cost the same thing.
//
// The consequence was precise and invisible: a cached procedure was silently
// discarded whenever the second run's planner happened to feel familiar —
// which is MORE likely on the second run than the first, because that is what
// having done a thing once feels like. So "never pay for the same learning
// twice" failed in exactly the case it exists for, and nothing anywhere said
// so. Moment #32 of the fifty ("the same errand a second time, two weeks
// later → near-instant, the recipe is cached, not relearned") could not
// happen for procedures, only for recipes.
//
// The other cache does not have this defect: recallRecipe is unconditional on
// shape, gated only by "is this a resume", two dozen lines above. This suite
// holds procedures to the same discipline.
//
// Run: node extension/tests/test_recall_is_not_gated.mjs
import { installChrome } from "./chrome_mock.mjs";
import { taskShape } from "../learn.js";

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const GOAL = "claim the warranty on my Anker charger";
const PROCEDURE_STEP = "Open the returns portal";

const harness = installChrome();
const { runAgentGoal } = await import("../agent_loop.js");

// A procedure this shape learned on some earlier run, already in the cache.
// Seeded directly rather than by running the loop twice, so what this suite
// measures is the RECALL path and not the learning path.
await chrome.storage.local.set({
  procedures: {
    [taskShape(GOAL)]: {
      startUrl: "https://support.anker.com/returns",
      needs: ["your order number"],
      steps: [PROCEDURE_STEP, "Enter the order number"],
      caveats: ["there is a 30-day window"],
      sources: ["https://support.anker.com/returns"],
      learnedAt: Date.now(),
      question: "how do I claim an Anker warranty",
    },
  },
});

harness.mapPage = (tabId) => ({
  url: harness.tabs.get(tabId)?.url || "",
  title: "Returns portal",
  elements: "[0] <link> Start a return https://support.anker.com/returns",
  text: "Start a return. Enter your order number.",
  fields: [],
});

const opened = [];
const realCreate = chrome.tabs.create.bind(chrome.tabs);
chrome.tabs.create = async (props) => {
  opened.push(String(props?.url || ""));
  return realCreate(props);
};

// `unfamiliar` is what the planner reports. Flipped per scenario below; the
// point of the suite is that recall does not depend on it.
let plannerSaysUnfamiliar = false;
// Audit #76: the judge that reads whether the cached procedure is the SAME
// errand. Section 6 flips it to NO; every other section leaves it at YES.
let judgeSays = "YES";
let seen = [];
globalThis.fetch = async (url, opts = {}) => {
  if (!String(url).includes("openrouter")) {
    return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
  }
  const body = JSON.parse(opts.body);
  const all = body.messages.map((m) => (Array.isArray(m.content)
    ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n")
    : String(m.content || "")));
  const joined = all.join("\n");
  let kind = "step";
  if (/You plan a task/.test(joined)) kind = "plan";
  else if (/reading the open web to learn HOW/.test(joined)) kind = "learn";
  else if (/You audit a browser agent's claim/.test(joined)) kind = "verify";
  else if (/pre-submit form auditor/.test(joined)) kind = "form-audit";
  else if (/would following the remembered procedure/.test(joined)) kind = "recall";
  seen.push({ kind, user: all[all.length - 1] });

  let content;
  if (kind === "plan") {
    content = JSON.stringify({
      start_url: "https://www.anker.com/", why: "vendor site", steps: [],
      unfamiliar: plannerSaysUnfamiliar,
      learn: plannerSaysUnfamiliar ? "how do I claim an Anker warranty" : null,
    });
  } else if (kind === "learn") {
    content = JSON.stringify({
      start_url: "https://support.anker.com/somewhere-else",
      needs: [], steps: ["A freshly researched step"],
    });
  } else if (kind === "verify") {
    content = JSON.stringify({ verified: true });
  } else if (kind === "recall") {
    // The floor added 2026-09-05 (audit #76): a cached candidate is released
    // only on a positive YES. Sections 1-5 are about recall not being GATED on
    // the planner's mood, so the judge says yes there; section 6 says NO and
    // proves the loop honours it. test_recall_is_confirmed.mjs pins the floor
    // itself, all four states.
    content = judgeSays;
  } else {
    content = JSON.stringify({ action: "done", result: "Return started, reference R-1190" });
  }
  return {
    ok: true, status: 200,
    json: async () => ({ choices: [{ message: { content } }] }),
    text: async () => "",
  };
};

async function run(opts = {}) {
  seen = [];
  opened.length = 0;
  harness.tabs.clear();
  harness.addTab({ url: "https://news.site/read", active: true });
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: true,
    stillLive: async () => true, ...opts,
  });
  return {
    out,
    steps: seen.filter((s) => s.kind === "step"),
    learned: seen.filter((s) => s.kind === "learn"),
  };
}

// ------------------------------------------- 1. THE DEFECT THIS SUITE EXISTS FOR
// The planner feels familiar — which is what a planner on the SECOND run of a
// shape sounds like. The knowledge is in hand and free to read.
{
  plannerSaysUnfamiliar = false;
  const { out, steps, learned } = await run();
  check("a familiar-feeling second run still finishes", out.status === "done");
  check("the cached procedure is recalled even though the planner said familiar",
    steps.length > 0 && steps.every((s) => s.user.includes(PROCEDURE_STEP)));
  check("and nothing was paid to research it again", learned.length === 0);
}

// ------------------------------------------------- 2. RECALL IS KEYED ON SHAPE
// Not on the wording. "the March bill" and "the April bill" are one procedure,
// and so are these two — this is the same key recallRecipe uses.
{
  plannerSaysUnfamiliar = false;
  seen = [];
  const out = await runAgentGoal("claim the warranty on my ANKER charger!!", {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: true,
    stillLive: async () => true,
  });
  const steps = seen.filter((s) => s.kind === "step");
  check("a differently worded errand of the same shape hits the same entry",
    out.status === "done" && steps.every((s) => s.user.includes(PROCEDURE_STEP)));
}

// ------------------------------- 3. NO PLAN AT ALL IS STILL NOT A REASON TO FORGET
// `plan` is null outright when the caller supplied a start URL. Under the old
// condition that meant the cache was not even looked at — the run threw away
// knowledge it already had, for free, because of a field that did not exist.
{
  plannerSaysUnfamiliar = false;
  const { out, steps } = await run({ startUrl: "https://support.anker.com/returns" });
  check("a caller-supplied start URL still gets the cached procedure",
    out.status === "done" && steps.length > 0
      && steps.every((s) => s.user.includes(PROCEDURE_STEP)));
  // ...and recall must not become a way for a stored page to redirect a run.
  // The procedure's startUrl may only ever improve the PLANNER's guess; when
  // the caller named a page, the caller wins.
  check("but the recalled procedure cannot redirect where the run opens",
    opened.every((u) => !u.includes("somewhere-else")));
}

// ------------------------------------------ 4. SPEND IS STILL GATED, ON A FACT
// The half that costs money stays behind a condition — but the FIRST condition
// is now "is there a live cached answer for this shape", which is a fact
// anybody can check from either side of the wire without a model.
{
  plannerSaysUnfamiliar = true;
  const { learned, steps } = await run();
  check("a cache hit means no research even when the planner asks for it",
    learned.length === 0);
  check("...and the cached procedure is what the steps get, not a fresh one",
    steps.every((s) => s.user.includes(PROCEDURE_STEP)
      && !s.user.includes("A freshly researched step")));
}

// A shape nobody has learned: the spend path must still work, or this suite
// would pass just as well against a loop that never researches anything.
{
  plannerSaysUnfamiliar = true;
  seen = [];
  harness.tabs.clear();
  harness.addTab({ url: "https://news.site/read", active: true });
  const out = await runAgentGoal("dispute the March bill from BC Hydro", {
    apiKey: "test-key", scope: "dispute the bill", authorized: true,
    planning: true, stillLive: async () => true,
  });
  const learned = seen.filter((s) => s.kind === "learn");
  const steps = seen.filter((s) => s.kind === "step");
  check("an unknown shape still goes and reads first",
    out.status === "done" && learned.length === 1);
  check("...and what it learned rides into the run",
    steps.length > 0 && steps.every((s) => s.user.includes("A freshly researched step")));
}

// ------------------------------------------ 6. THE LOOP GOES THROUGH THE DOOR
// Audit #76. The shape key is blind to direction, so it hands back whatever
// collided; the floor's job is to stop the LOOP replaying it when a model says
// it is a different errand. This is the behavioural pin for that: same seeded
// procedure, same familiar planner, judge says NO — and the procedure must
// reach no step prompt at all. A source grep for "no bare recall call" was
// tried first and a mutation that reached the bare function through an alias
// walked past it; this cannot be dodged by spelling.
{
  plannerSaysUnfamiliar = false;
  judgeSays = "NO";
  const refused = await run();
  check("when the judge says NO, the cached procedure reaches no step prompt",
    refused.steps.length > 0 && refused.steps.every((s) => !s.user.includes(PROCEDURE_STEP)));
  check("...and the run still finishes, reasoning live instead of replaying unread",
    refused.out.status === "done");
  // THE CONTROL. Flip only the judge back and the identical seed IS replayed —
  // so what stopped it above was the verdict, not the fixture.
  judgeSays = "YES";
  const released = await run();
  check("flip the judge back to YES and the identical seed is replayed — the verdict is what decided",
    released.steps.length > 0 && released.steps.every((s) => s.user.includes(PROCEDURE_STEP)));
}

if (failures) {
  console.error(`test_recall_is_not_gated: ${failures} failed`);
  process.exit(1);
}
console.log("test_recall_is_not_gated: all passed");
