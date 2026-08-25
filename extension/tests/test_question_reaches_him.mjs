// WHETHER HE IS ASKED AT ALL.
//
// Audit #64. When the step model stops with `needs_user`, this gate decided
// whether the sentence reached the owner or was swallowed into fallback
// navigation. It decided with two word lists: `questionShaped` (a "?", one of
// eleven wh-openers, or one of seven choice verbs) against `pageFailure`
// (fourteen failure words). Missing the first while matching the second sent
// the run off to another source and the owner never saw the sentence.
//
//   "The 7pm slot is fully booked and I need to know whether 8pm is
//    acceptable before I commit."
//
// No "?", no wh-opener, none of the choice verbs, and "fully booked" in the
// failure list. Driven through the whole shipped loop: the question vanished
// and the run carried on and reported "booked". Four more everyday sentences
// did the same — §1 is that reproduction turned into a check.
//
// This one is upstream of every other consent gate in the extension. A
// sentence wrongly read as a dead page is a question that is never put to
// anybody, so no consent is ever sought about anything.
//
// Whether a sentence is a decision for a person is what it MEANS, so a model
// reads it whole. HARNESS-LAWS.md law 1. Failing to decide hands back.
//
// Run: node extension/tests/test_question_reaches_him.mjs
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const harness = installChrome();
const { runAgentGoal } = await import("../agent_loop.js");

// Drive the whole loop: the step model stops with `reason`, and a fallback
// source EXISTS — without one there is nothing to divert into and the gate is
// moot, which is exactly the case the shipped code got right by accident.
async function stopWith(reason, { verdict = "OWNER", reachable = true } = {}) {
  harness.tabs.clear();
  harness.addTab({ url: "https://news.site/read", active: true });
  harness.mapPage = (tabId) => ({
    url: harness.tabs.get(tabId)?.url || "https://booking.example.com/",
    title: "Booking", elements: "[0] <button> Book", text: "Choose a time.", fields: [],
  });
  const queue = [{ action: "needs_user", reason }, { action: "done", result: "booked" }];
  let asked = 0;
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const parsed = JSON.parse(opts.body);
    const joined = parsed.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n")
      : String(m.content || ""))).join("\n");
    let content;
    if (/is that sentence/.test(joined)) {
      asked++;
      if (!reachable) return { ok: false, status: 500, json: async () => ({}), text: async () => "" };
      content = verdict;
    } else if (/You plan a task/.test(joined)) {
      content = JSON.stringify({ start_url: "https://booking.example.com/", why: "the site",
                                 steps: [], fallbacks: ["https://other.example.com/"], unfamiliar: false });
    } else if (/You audit a browser agent's claim/.test(joined)) {
      content = JSON.stringify({ verified: true });
    } else {
      content = JSON.stringify(queue.shift() || { action: "wait" });
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  const out = await runAgentGoal("book a table at 7pm", {
    apiKey: "k", scope: "book a table at 7pm tonight", ownerProfile: { email: "omar@gmail.com" },
    authorized: true, planning: true, maxSteps: 4, stillLive: async () => true,
  });
  return { out, asked, delivered: out.status === "needs_user" && String(out.result) === reason };
}

// ---------------------------------------------------------------------------
// 1. THE DEFECT. Five ordinary sentences, every one swallowed by the shipped
//    word lists, every one of them a decision only he can make.
// ---------------------------------------------------------------------------
const SWALLOWED = [
  "The 7pm slot is fully booked and I need to know whether 8pm is acceptable before I commit.",
  "Their online booking is down for maintenance — do I phone them instead, or leave it for today.",
  "The size you wanted is sold out. I can order the next size up or wait for a restock, tell me which.",
  "Delivery to that address came back as unavailable; I need an alternative address from you.",
  "There are no results for that name — I do not want to guess which of the three clinics you meant.",
];
for (const reason of SWALLOWED) {
  const { delivered, out } = await stopWith(reason);
  check(`reaches him: ${JSON.stringify(reason.slice(0, 46))}...`,
    delivered, `${out.status}: ${String(out.result).slice(0, 60)}`);
}
{
  // And the run must NOT report success on an errand it never finished. That
  // is what the swallowed question turned into: "booked", on a table nobody
  // had agreed to.
  const { out } = await stopWith(SWALLOWED[0]);
  check("...and the run does not go on to claim it finished the errand",
    out.status !== "done", `${out.status}: ${String(out.result).slice(0, 60)}`);
}

// ---------------------------------------------------------------------------
// 2. A GENUINE DEAD END STILL SELF-RECOVERS. The gate must not turn every
//    page failure into a message; that trades one bug for a chattier one.
// ---------------------------------------------------------------------------
{
  const dead = "That page returns a 404 and there is nothing on it to act on.";
  const { out, asked, delivered } = await stopWith(dead, { verdict: "PAGE" });
  check("a sentence the model reads as a dead page still diverts to another source",
    !delivered, `${out.status}: ${String(out.result).slice(0, 60)}`);
  check("...and the model was the one that said so", asked === 1, String(asked));
}

// ---------------------------------------------------------------------------
// 3. FAIL CLOSED, AND CHEAP.
// ---------------------------------------------------------------------------
{
  const dead = "That page returns a 404 and there is nothing on it to act on.";
  const { delivered } = await stopWith(dead, { reachable: false });
  check("with no model to read it, the sentence goes to HIM", delivered);
  for (const verdict of ["", "It's probably a page problem", "PAGE — and keep going",
                         "OWNER", "page"]) {
    const { delivered: d } = await stopWith(dead, { verdict });
    check(`fails to the owner on verdict ${JSON.stringify(verdict.slice(0, 26))}`, d);
  }
}

// ---------------------------------------------------------------------------
// 4. THE LAW LEG. What stays red if a word list decides this again.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  // The names survive in the comment that records what they did and why they
  // went; what must stay gone is the code. Comments stripped before asking.
  const srcCode = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  for (const gone of ["questionShaped", "pageFailure"]) {
    check(`law 1: ${gone} stays deleted from the code`, !srcCode.includes(gone));
  }
  const block = src.slice(src.indexOf('if (decision.action === "needs_user") {'),
                          src.indexOf('if (decision.action === "navigate") {',
                                      src.indexOf('if (decision.action === "needs_user") {')));
  const code = block.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  check("law 1: the gate declares no regex over the sentence",
    !/\/[^\n/]*\/[gimsuy]*\.test\(/.test(code), code);
  check("law 1: no vocabulary of question words or failure words survives",
    !/which|sold out|fully booked|no results|unavailable/i.test(code), code);
  check("the gate is the awaited model verdict", /await meantForTheOwner\(/.test(code));
  check("hand-back is the default: the diversion is the branch that must argue",
    /return \(handBack = true\) && \{ status: "needs_user", result: reason/.test(code));
  const judge = src.slice(src.indexOf("async function meantForTheOwner"),
                          src.indexOf("async function meantForTheOwner") + 2600);
  check("the call is bounded, so a hung model cannot hang the run",
    /withTimeout\(/.test(judge), judge.slice(0, 160));
  check("the verdict is one specified token, not prose searched for a word",
    /!== "PAGE"/.test(judge) && !/includes\("PAGE"\)/.test(judge));
  check("an ordinary run with nowhere to divert to pays no model call at all",
    /fallbackQueue\.length\s*\n?\s*&& !\(await meantForTheOwner/.test(code), code);
}

if (failures) { console.error(`test_question_reaches_him: ${failures} failed`); process.exit(1); }
console.log("test_question_reaches_him: all passed");
