// A CHOSEN SOURCE THAT WALLS US IS NOT THE END OF THE ERRAND.
//
// Written 2026-08-20 after the owner's own flagship example failed live. He
// said, to nobody in particular, "Oh my goodness, I forgot to cook for my kids
// this afternoon." The brain correctly heard an errand and planned a read-only
// search for kid-friendly delivery near him. The browser landed on doordash,
// met a "prove you're human" check, and parked to ask HIM for help - so an
// ambient thought became a chore, on a question with a hundred readable
// answers. The MVP spec sells quiet competence; asking him to tick a box so she
// can read a menu is the opposite of it.
//
// These are BEHAVIOURAL, not source greps: the whole change is control flow, so
// the only honest proof is running the loop and seeing where it goes.
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { runAgentGoal, goalNamesHost } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// A real CDP screenshot is tens of KB, and screenshot() treats anything under
// 4000 chars as a blank frame, so vision must look believable or the loop
// refuses to look.
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");

const GOAL = "find kid-friendly dinner delivery options for this afternoon";

// The wall, the search page it should retreat to, and the source that answers.
const WALL = "https://fastbite.example.com/browse";
// chrome_mock's stand-in for whichever provider the browser is configured to
// use. The agent never knows or chooses the real provider URL.
const SEARCH = "https://search.test/";
const OPEN = "https://eater.example.com/vancouver/kid-friendly-delivery";

// Audit #71: the wall's WORDS decide nothing any more. What makes this page
// a wall is the Turnstile frame it renders (the sift) and the model's
// BLOCKED to the one challenge question (below, in model()).
const TURNSTILE_FRAME = {
  src: "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2/av0/rcv/x/0x4AAAA/light/normal/",
  x: 380, y: 420, w: 300, h: 65, hidden: false, inViewport: true,
};
function pageFor(url) {
  if (url.startsWith(WALL)) {
    return {
      url, title: "Just a moment...",
      text: "Verify you are human by completing the challenge below.",
      elements: '[0] <button> Verify you are human',
      frames: [TURNSTILE_FRAME], widgets: [],
    };
  }
  if (url.startsWith(SEARCH)) {
    return {
      url, title: "kid friendly delivery - Search",
      text: "Results for kid-friendly dinner delivery in Vancouver.",
      // The walled host is STILL the top hit, which is exactly why the model
      // has to be told it is dead rather than merely nudged.
      elements: `[0] <link> fastbite.example.com - Order food now\n`
        + `[1] <link> Eater - 12 kid-friendly delivery spots in Vancouver`,
    };
  }
  return {
    url, title: "12 kid-friendly delivery spots in Vancouver",
    text: "Best kid-friendly delivery: Nook (pasta, 30 min), "
      + "Superbaba (falafel, 25 min), and Anh & Chi (Vietnamese, 35 min).",
    elements: "[0] <link> Nook",
  };
}
function fresh() {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.onCdp = (tabId, method) => (method === "Page.captureScreenshot"
    ? { data: FAKE_JPEG } : undefined);
  // Keyed on the TAB, not fixed: the retreat is a navigation, and a static map
  // would hide whether it actually happened.
  harness.mapPage = (tabId) => pageFor(harness.tabs.get(tabId)?.url || WALL);
  harness.onInject = null;
  delete harness.storageData.agentTabs;
}

// One scripted model. It answers from whatever page it is shown, so the run's
// path is decided by the loop, not by a queue of pre-baked moves.
function model() {
  const prompts = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const body = JSON.parse(opts.body);
    const seen = JSON.stringify(body.messages);
    prompts.push(seen);
    // The completion verifier is a SECOND, independent model call with its own
    // contract; answering it with an action verb yields "unparseable verifier
    // response" and the run ends needs_user for a reason that has nothing to do
    // with walls. Its prompt is identifiable by CLAIMED RESULT.
    // The challenge question (audit #71) is its own call with its own
    // contract: a bare token. This wall IS a wall.
    if (seen.includes("standing between the assistant")) {
      return {
        ok: true, status: 200,
        json: async () => ({ choices: [{ message: { content: "BLOCKED" } }] }),
        text: async () => "",
      };
    }
    if (seen.includes("CLAIMED RESULT")) {
      const verdict = { verified: /Superbaba/.test(seen),
        reason: "the page names the restaurants claimed",
        evidence: ["https://eater.example.com"] };
      return {
        ok: true, status: 200,
        json: async () => ({ choices: [{ message: { content: JSON.stringify(verdict) } }] }),
        text: async () => "",
      };
    }
    let decision;
    if (seen.includes("Superbaba")) {
      decision = { action: "done", result: "Nook, Superbaba and Anh & Chi all deliver and are kid-friendly." };
    } else if (seen.includes("Results for kid-friendly")) {
      // Deliberately tries the walled host FIRST if it is still on offer -
      // proving the loop removed it, rather than the model politely avoiding it.
      decision = seen.includes("do not go back to it")
        ? { action: "click", index: 1 }
        : { action: "click", index: 0 };
    } else {
      decision = { action: "click", index: 0 };
    }
    return {
      ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content: JSON.stringify(decision) } }] }),
      text: async () => "",
    };
  };
  return prompts;
}

// A click on a search result navigates; the mock does not, so the loop's own
// navigation is what we watch. Clicks are wired to move the tab.
function wireClicks() {
  const realCdp = harness.onCdp;
  harness.onCdp = (tabId, method, params) => {
    if (method === "Input.dispatchMouseEvent" && params?.type === "mousePressed") {
      const t = harness.tabs.get(tabId);
      if (t && String(t.url).startsWith(SEARCH)) t.url = OPEN;
    }
    return realCdp ? realCdp(tabId, method, params) : undefined;
  };
}

// ---- 1. a source NOBODY named is abandoned, and the errand finishes
// This is the real failure shape: the brain's planner chose the host, so
// start_url IS the walled site. What makes it replaceable is that the owner's
// sentence never mentions it.
{
  fresh();
  const prompts = model();
  wireClicks();
  harness.addTab({ url: WALL, active: true });
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: false,
    readOnly: true, stillLive: async () => true,
    startUrl: WALL,
  });
  check("a walled source nobody named does not end the errand",
    out.status === "done");
  check("and the answer comes from somewhere else",
    /Superbaba/.test(String(out.result)));
  check("the model is told the host is unusable, not just nudged",
    prompts.some((p) => /do not go back to it/.test(p)));
  check("it retreated to a search rather than sitting on the wall",
    prompts.some((p) => /Results for kid-friendly/.test(p)));
}

// ---- 2. a wall on a site the OWNER'S OWN WORDS name is still terminal
// No other website is his delivery account, so moving on would be a lie
// dressed up as competence. Same start_url as case 1 - only the goal differs,
// which is the whole point: the sentence decides, not the plan.
{
  fresh();
  model();
  harness.addTab({ url: WALL, active: true });
  const out = await runAgentGoal("check the balance on my fastbite account", {
    apiKey: "test-key", scope: "check my fastbite balance",
    authorized: true, planning: false, readOnly: true,
    stillLive: async () => true, startUrl: WALL,
  });
  check("a wall on the site the owner named hands back",
    out.status === "needs_user");
  check("and says where it is, so the hand-back is actionable",
    /prove you're human/.test(String(out.result)));
}

// ---- 3. a consequential run never restarts elsewhere
// Half of a booking may already be done on this page; beginning again on
// another site is how one dinner becomes two.
{
  fresh();
  model();
  harness.addTab({ url: WALL, active: true });
  const out = await runAgentGoal("book a table for four tonight", {
    apiKey: "test-key", scope: "book a table", authorized: true,
    planning: false, readOnly: false, stillLive: async () => true,
    startUrl: WALL,
  });
  check("a consequential run hands back rather than starting over elsewhere",
    out.status === "needs_user");
}

// ---- 4. the brand match is a brand, not a substring accident
{
  check("a goal naming the brand matches its domain",
    goalNamesHost("dispute the charge on my BC Hydro bill", "bchydro.com"));
  check("a goal naming nobody matches nothing",
    !goalNamesHost("find kid-friendly dinner delivery", "doordash.com"));
  check("a subdomain word in the goal does not claim the host",
    !goalNamesHost("arrange a delivery", "doordash.com"));
  check("two-letter hosts are noise, never a brand",
    !goalNamesHost("go see it", "go.com"));
}

if (failures) {
  console.error(`test_walled_source: ${failures} failed`);
  process.exit(1);
}
console.log("test_walled_source: all passed");
