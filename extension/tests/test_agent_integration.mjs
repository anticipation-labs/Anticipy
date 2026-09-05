// The two new organs, driven through the REAL step loop rather than in isolation.
//
// recipes.js and login_wall.js each have their own unit suite. This one asserts
// the wiring, which is where a module that works perfectly still delivers
// nothing: a recipe recalled but never consulted, a wall detected but never
// surfaced, a replayed action that skips the gates a reasoned action goes
// through. Wiring is the part unit tests cannot see.
//
// Run: node extension/tests/test_agent_integration.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
// A real CDP screenshot is tens of KB and `screenshot()` treats anything under
// 4000 chars as a blank frame — correctly, because a hidden background tab can
// return one. Without a believable fake, vision assertions can never fire and
// would look like the loop refusing to look.
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
harness.onCdp = (tabId, method) => (method === "Page.captureScreenshot"
  ? { data: FAKE_JPEG } : undefined);
// Imported AFTER installChrome(): agent_loop.js pulls in config.js, and a module
// that reads chrome.storage during evaluation needs the global to exist first.
const { runAgentGoal } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const GOAL = "check the happy hour times at Cactus Club Coal Harbour";

function fresh() {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  // Keep the screenshot responder — `fresh()` resets the world, not the camera.
  harness.onCdp = (tabId, method) => (method === "Page.captureScreenshot"
    ? { data: FAKE_JPEG } : undefined);
  harness.onInject = null;
  delete harness.storageData.agentTabs;
  harness.addTab({ url: "https://news.site/read", active: true });
}

// One scripted model. Records every prompt so the assertions can count calls —
// the whole point of a recipe is that the call does not happen.
function scripted(actions, { onPrompt } = {}) {
  const a = [...actions];
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
    let kind = "step";
    if (/You plan a task/.test(joined)) kind = "plan";
    else if (/reading the open web to learn HOW/.test(joined)) kind = "learn";
    else if (/You audit a browser agent's claim/.test(joined)) kind = "verify";
    else if (/pre-submit form auditor/.test(joined)) kind = "form-audit";
    else if (/would following the remembered procedure/.test(joined)) kind = "recall";
    seen.push({ kind, user: all[all.length - 1], hasImage: /\[image\]/.test(joined) });
    if (onPrompt) onPrompt(kind, all[all.length - 1]);
    let content;
    if (kind === "plan") {
      content = JSON.stringify({ start_url: "https://cactusclubcafe.com/happy-hour", why: "the venue", steps: [], unfamiliar: false });
    } else if (kind === "verify") {
      content = JSON.stringify({ verified: true, evidence: ["happy hour 3-6pm"] });
    } else if (kind === "recall") {
      content = "YES";
    } else {
      content = JSON.stringify(a.shift() || { action: "wait" });
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return seen;
}
// A model that answers from what it is shown, rather than from a queue. Needed
// wherever replay is in play: replay changes WHICH step the model is asked
// about, so a positional script silently answers the wrong question.
function reactive(answer) {
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
    let kind = "step";
    if (/You plan a task/.test(joined)) kind = "plan";
    else if (/reading the open web to learn HOW/.test(joined)) kind = "learn";
    else if (/You audit a browser agent's claim/.test(joined)) kind = "verify";
    else if (/pre-submit form auditor/.test(joined)) kind = "form-audit";
    else if (/would following the remembered procedure/.test(joined)) kind = "recall";
    const prompt = all[all.length - 1];
    seen.push({ kind, user: prompt, hasImage: /\[image\]/.test(joined) });
    let content;
    if (kind === "plan") {
      content = JSON.stringify({ start_url: "https://cactusclubcafe.com/happy-hour", why: "the venue", steps: [], unfamiliar: false });
    } else if (kind === "verify") {
      content = JSON.stringify({ verified: true, evidence: ["happy hour 3-6pm"] });
    } else if (kind === "recall") {
      content = "YES";
    } else {
      content = JSON.stringify(answer(prompt));
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return seen;
}

// The ordinary page: a couple of links, nothing a label list cannot describe.
const plainPage = (tabId) => ({
  url: harness.tabs.get(tabId)?.url || "https://cactusclubcafe.com/happy-hour",
  title: "Happy hour",
  elements: "[0] <link> Menus @(10,10)\n[1] <link> Happy hour @(20,20)\n[2] <button> Reserve @(30,30)",
  text: "Happy hour runs 3-6pm daily at Coal Harbour.",
  fields: [],
});

// ------------------------------------------- 1. a wall hands back, specifically
{
  fresh();
  harness.mapPage = (tabId) => ({
    url: "https://portal.hydro-example.ca/login",
    title: "Sign in",
    // page_map redacts a sensitive input rather than listing its value, which is
    // the marker login_wall.js reads.
    elements: "[0] <textbox> Email @(10,10)\n"
      + "[1] <textbox> Password (sensitive field — never fill) @(10,40)\n"
      + "[2] <button> Sign in @(10,70)",
    text: "Sign in to your account to continue.",
    fields: [{ index: 0, label: "Email", value: "" }],
  });
  const seen = scripted([{ action: "done", result: "should never get here" }]);
  const out = await runAgentGoal("download my latest BC Hydro bill", {
    apiKey: "test-key", scope: "get my latest hydro bill", authorized: true,
    ownerProfile: { first_name: "Jose", email: "jose@example.test" },
    planning: false, stillLive: async () => true,
  });

  check("a login wall parks the run instead of burning steps",
    out.status === "needs_user");
  check("...naming the site", /hydro-example\.ca/.test(String(out.result)));
  check("...saying it will never type a password",
    /password/i.test(String(out.result)));
  check("...and keeping the tab so the session and the form survive",
    typeof out.tabId === "number");
  check("the wall is caught BEFORE the model is asked to act on the page",
    seen.filter((s) => s.kind === "step").length === 0);
  check("the hand-back is not the old generic stall",
    !/got nowhere|without getting anywhere/i.test(String(out.result)));
}

// ------------------- 2. a header "Sign in" link must NOT be read as a wall
// The expensive false positive: nearly every site has one, and treating it as a
// wall would park every successful errand one step from done.
{
  fresh();
  harness.mapPage = (tabId) => ({
    url: "https://cactusclubcafe.com/happy-hour",
    title: "Happy hour | Cactus Club",
    elements: "[0] <link> Menus @(10,10)\n[1] <link> Sign in @(900,10)\n"
      + "[2] <link> Happy hour @(20,40)\n[3] <button> Reserve @(30,70)",
    text: "Happy hour runs 3-6pm daily at Coal Harbour.",
    fields: [],
  });
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true,
    planning: false, stillLive: async () => true,
  });
  void scripted([{ action: "done", result: "Happy hour is 3-6pm" }]);
  check("a Sign in link in the header does not park the run",
    out.status !== "needs_user" || !/sign in|password/i.test(String(out.result)));
}

// ---------------------------------- 3. two clean runs compile, the third flies
{
  // A fixed page and a fixed route, run three times. Runs 1 and 2 pay the model;
  // run 3 must not.
  //
  // THREE dispatched actions, not one. recipes.js refuses to compile a route of
  // fewer than two steps, which is the right call — a single click is not a
  // procedure worth a script — so a one-action fixture would have tested nothing
  // and looked like a broken recorder.
  //
  // AND THE MODEL IS DRIVEN OFF THE PROMPT, not off a queue. A queue assumes the
  // model is asked once per step in order, which is exactly the assumption replay
  // breaks: on run 3 the first thing the model is asked is the TAIL, and a queue
  // handed it the head of the route again. That looked like replay saving nothing
  // when replay was in fact working — the fixture was lying, not the loop. A real
  // model reads its history and answers accordingly, so this one does too.
  const answerFromHistory = (prompt) => {
    if (/"index":0/.test(prompt)) return { action: "done", result: "Happy hour is 3-6pm at Coal Harbour" };
    if (/"index":1/.test(prompt)) return { action: "click", index: 0 };
    if (/"action":"scroll"/.test(prompt)) return { action: "click", index: 1 };
    return { action: "scroll", dy: 400 };
  };
  const stepCounts = [];
  for (let attempt = 1; attempt <= 3; attempt++) {
    fresh();
    harness.mapPage = plainPage;
    const seen = reactive(answerFromHistory);
    const out = await runAgentGoal(GOAL, {
      apiKey: "test-key", scope: GOAL, authorized: true,
      planning: false, stillLive: async () => true,
    });
    if (out.status !== "done") {
      check(`run ${attempt} finished cleanly (got ${out.status}: ${String(out.result).slice(0, 90)})`, false);
      break;
    }
    stepCounts.push(seen.filter((s) => s.kind === "step").length);
  }

  check("all three runs finished", stepCounts.length === 3);
  check("the first run reasons every step", stepCounts[0] >= 3);
  check("the second run still reasons — one success is luck, not a route",
    stepCounts[1] >= 3);
  // THE POINT. The spec calls this the moat and the margin: "recipes run for near
  // zero model cost at 10x the speed".
  check(`the THIRD run costs fewer model calls (${stepCounts[0]} -> ${stepCounts[2]})`,
    stepCounts[2] < stepCounts[0]);

  const saved = (await chrome.storage.local.get("recipes")).recipes || {};
  const entries = Object.values(saved);
  check("a recipe was stored", entries.length >= 1);

  // The disaster this must structurally prevent: replaying a value the owner
  // gave LAST time. Assert on the serialized cache, so any path that smuggled a
  // value in is caught whatever shape it used.
  const serialized = JSON.stringify(saved);
  check("no stored step carries typed text at all",
    !/"text"\s*:/.test(serialized) && !/"option"\s*:/.test(serialized));
  check("no stored action carries a value key",
    !/"value"\s*:/.test(serialized));
}

// ------------------------------- 4. a changed page abandons replay, in words
{
  fresh();
  // Same shape, but the control the recipe recorded is gone.
  harness.mapPage = (tabId) => ({
    url: "https://cactusclubcafe.com/happy-hour",
    title: "Happy hour",
    elements: "[0] <link> Menus @(10,10)\n[1] <button> Accept cookies @(20,20)\n[2] <link> Locations @(30,30)",
    text: "Happy hour runs 3-6pm daily.",
    fields: [],
  });
  const seen = scripted([{ action: "done", result: "Happy hour is 3-6pm" }]);
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true,
    planning: false, stillLive: async () => true,
  });
  check("a changed page still finishes, by reasoning live", out.status === "done");
  check("...and it asked the model again rather than replaying blind",
    seen.filter((s) => s.kind === "step").length >= 1);
}

// -------------------------------------- 5. vision is not billed on plain pages
{
  fresh();
  harness.mapPage = plainPage;
  const seen = scripted([{ action: "done", result: "Happy hour is 3-6pm" }]);
  await runAgentGoal("look up something else entirely on this page", {
    apiKey: "test-key", scope: "look it up", authorized: true,
    planning: false, stillLive: async () => true,
  });
  const steps = seen.filter((s) => s.kind === "step");
  check("no screenshot rides along on a page a label list describes",
    steps.length > 0 && steps.every((s) => !s.hasImage));
}

// ---------------------------------------------- 6. vision IS billed on a picker
{
  fresh();
  harness.mapPage = (tabId) => ({
    url: "https://cactusclubcafe.com/reserve",
    title: "Pick a date",
    overlay: true,
    elements: "[0] <button> 17 (calendar=September 17) @(10,10)\n[1] <button> 18 (calendar=September 18) @(30,10)",
    text: "Choose a date",
    fields: [],
  });
  const seen = scripted([{ action: "done", result: "Picked a date" }]);
  await runAgentGoal("pick a date on the reservation calendar", {
    apiKey: "test-key", scope: "pick a date", authorized: true,
    planning: false, stillLive: async () => true,
  });
  const steps = seen.filter((s) => s.kind === "step");
  check("a picker DOES get looked at, on the first step, not after two wasted ones",
    steps.length > 0 && steps[0].hasImage);
}

if (failures) {
  console.error(`test_agent_integration: ${failures} failed`);
  process.exit(1);
}
console.log("test_agent_integration: all passed");
