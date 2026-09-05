// A CORRECT COMPARISON WAS REFUSED BECAUSE HE WROTE "BELL CANADA" AND THE
// SOURCE SAYS "BELL".
//
// F06. Audit #74 took the record COUNT off `completionShapeGap` and gave it to
// the auditor, and its own record named what it had not touched: the
// comparison-name branch, the direct-URL count, and the `openEach` regex
// gating provenance — "the same class ... they must not grow." They did not
// grow. They were still deciding.
//
// Both surviving branches read a REQUIREMENT off the owner's wording and
// returned verified:false from verifyDone before mapPage and before the
// auditor ran. Measured on the shipped functions:
//
//   "Compare the monthly cost for Bell Canada, Telus, and Rogers."
//     + a correct claim naming the carrier as its source does ("Bell:")
//       -> "the comparison result omits: Bell Canada"
//   "Compare the monthly cost for Telus, Rogers, and Bell and include direct URLs."
//     + three correct prices with one comparison-page URL
//       -> "the goal requests 3 direct URLs but the result contains 1"
//
// Each reason matched outputOnlyCompletionGap, so the loop asked the model to
// REWORD a correct answer; every rewording met the same regex; at eight
// rejections the owner was texted that a finished errand could not be
// verified. And two more regexes decided whether a safety check EXISTED at
// all: `openEach` over the goal for URL provenance, `\bofficial\b` over the
// goal for cited-price provenance — so "check each listing" and "the airline's
// own site" had no check whatsoever.
//
// Run: node extension/tests/test_completion_shape_is_a_model_verdict.mjs
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { verifyDone, completionEvidenceGap, officialRecordEvidenceGap, runAgentGoal } =
  await import("../agent_loop.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const AUDIT_SENTINEL = /You audit a browser agent's claim/;
const STEP_SENTINEL = /You are Anticipy's browser agent/;

const CARRIERS_PAGE = {
  url: "https://compare.example/mobile-plans",
  title: "Mobile plans compared",
  elements: "[0] <link> Bell @(10,10)\n[1] <link> Telus @(10,40)\n[2] <link> Rogers @(10,70)",
  text: "Bell: $65/mo\nTelus: $70/mo\nRogers: $60/mo",
  fields: [],
};

let mapped = 0;
function onPage(page) {
  harness.tabs.clear();
  const tab = harness.addTab({ url: page.url, active: false });
  mapped = 0;
  harness.mapPage = () => { mapped += 1; return page; };
  return tab;
}
function auditor(reply) {
  const calls = { audits: 0, prompts: [] };
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n") : String(m.content || ""))).join("\n");
    if (!AUDIT_SENTINEL.test(joined)) {
      return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "{}" } }] }), text: async () => "" };
    }
    calls.audits += 1;
    calls.prompts.push(joined);
    const content = typeof reply === "function" ? reply(calls.audits) : reply;
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return calls;
}
const grounded = (reason, goalQuote, claimedQuote, evidenceQuote, url) => JSON.stringify({
  verified: false, reason, goal_quote: goalQuote, claimed_quote: claimedQuote,
  evidence_quote: evidenceQuote, evidence_url: url,
});

// ---------------------------------------------------------------------------
// (a) THE DEFECT. The two measured goals, with correct claims, and an auditor
//     that reads them and says yes. Before the fix: verified=false, mapPage 0,
//     audits 0 — nobody ever looked.
// ---------------------------------------------------------------------------
let teaching = "";
{
  const goal = "Compare the monthly cost for Bell Canada, Telus, and Rogers.";
  const claim = "Bell: $65/mo, Telus: $70/mo, Rogers: $60/mo — Rogers is cheapest.";
  const tab = onPage(CARRIERS_PAGE);
  const calls = auditor('{"verified":true}');
  const v = await verifyDone("test-key", "test-model", goal, claim, tab.id, { scope: goal });
  check("(a) a correct comparison naming the source's own form of the name verifies",
    v.verified === true, JSON.stringify(v));
  check("(a) ...because the page was actually read", mapped >= 1);
  check("(a) ...and the auditor was actually asked, once", calls.audits === 1);
  teaching = calls.prompts[0] || "";
}
{
  const goal = "Compare the monthly cost for Telus, Rogers, and Bell and include direct URLs.";
  const claim = "Telus $70/mo, Rogers $60/mo and Bell $65/mo — all three are listed at "
    + "https://compare.example/mobile-plans";
  const tab = onPage(CARRIERS_PAGE);
  const calls = auditor('{"verified":true}');
  const v = await verifyDone("test-key", "test-model", goal, claim, tab.id, { scope: goal });
  check("(a) three prices from one cited comparison page verify — the URL COUNT is not the test",
    v.verified === true && calls.audits === 1, JSON.stringify(v));
}
{
  const goal = "Compare tuition for UBC, SFU, and UVic and provide direct URLs.";
  const claim = "UBC $6,150, SFU $6,010 and UVic $5,880 — all from https://compare.example/mobile-plans";
  const tab = onPage(CARRIERS_PAGE);
  const calls = auditor('{"verified":true}');
  const v = await verifyDone("test-key", "test-model", goal, claim, tab.id, { scope: goal });
  check("(a) and the tuition case with one cited source verifies",
    v.verified === true && calls.audits === 1, JSON.stringify(v));
}

// ---------------------------------------------------------------------------
// (b) THE OTHER DIRECTION. Nothing got looser: a claim that really does omit a
//     named carrier is still refused — by the auditor, in its own grounded
//     words, never in the regex's fixed sentence.
// ---------------------------------------------------------------------------
{
  const goal = "Compare the monthly cost for Bell Canada, Telus, and Rogers.";
  const claim = "Telus is $70/mo and Rogers is $60/mo.";
  const tab = onPage(CARRIERS_PAGE);
  const calls = auditor(grounded(
    "the goal names three carriers and the result gives only two; Bell, shown on the page at $65/mo, is absent",
    "Bell Canada", "Telus is $70/mo", "Bell: $65/mo", CARRIERS_PAGE.url));
  const v = await verifyDone("test-key", "test-model", goal, claim, tab.id, { scope: goal });
  check("(b) a genuinely incomplete comparison is still refused", v.verified === false);
  check("(b) ...by the auditor, which was asked", calls.audits === 1);
  check("(b) ...in the auditor's own words, not the regex's",
    /is absent/.test(String(v.reason)) && !/the comparison result omits/.test(String(v.reason)),
    String(v.reason));
}

// ---------------------------------------------------------------------------
// (c) THE TEACHING RIDES IN. The two shapes the deleted branches got wrong are
//     now instructions to the model that owns the question.
// ---------------------------------------------------------------------------
{
  check("(c) the auditor is told to judge a named item by WHICH THING IT IS",
    /Judge a named item by WHICH THING IT IS/.test(teaching));
  check("(c) ...with the measured name-form case spelled out",
    /"Bell" for "Bell Canada"/.test(teaching));
  check("(c) ...and told that the NUMBER of URLs is not the requirement",
    /the NUMBER of URLs is not the requirement/.test(teaching)
      && /one page that carries several of the named items can satisfy that/.test(teaching));
  check("(c) ...while a figure with no cited source at all is still incomplete",
    /left with no cited source at all/.test(teaching));
  check("(c) and it still sees the goal and the claim verbatim",
    teaching.includes("GOAL: Compare the monthly cost for Bell Canada, Telus, and Rogers."));
}

// ---------------------------------------------------------------------------
// (d) THE GATE NO LONGER DECIDES WHETHER IT EXISTS. Provenance ran only for
//     goals containing "open each" / "official"; it now runs on every errand,
//     and it is blind to how the goal is worded.
// ---------------------------------------------------------------------------
{
  const opened = { url: "https://example.test/listing/one", title: "one", text: "", elements: "" };
  const journal = [{ url: "https://example.test/listing/two" }];
  const cited = "Two are at https://example.test/listing/one and https://example.test/listing/two, "
    + "the third at https://example.test/listing/three";
  for (const goal of [
    "Find three records. Open each actual listing and report the direct URL.",
    "Check each listing and report the direct URL.",           // never matched openEach
    "Look at all three pages and give me the links.",          // nor this
    "Give me three rentals with links.",                       // nor this
  ]) {
    check(`(d) a cited page nobody opened is refused for "${goal.slice(0, 30)}..."`,
      /listing\/three/.test(completionEvidenceGap(goal, cited, opened, journal)));
  }
  check("(d) ...and pages the run DID open are not refused, on any wording",
    completionEvidenceGap("Give me three rentals with links.",
      "https://example.test/listing/one and https://example.test/listing/two", opened, journal) === "");
  const record = [{ vendor: "ExampleCo", plan_name: "Business Pro", displayed_price: "14.16",
                    currency: "USD", url: "https://example.test/pricing/pro" }];
  for (const goal of [
    "Compare the current plans on each vendor's official pricing page.",
    "Compare the plans from the vendor itself, not a comparison site.",
    "Get the price off the airline's own site.",
    "Compare several plans and summarize them.",
  ]) {
    check(`(d) a claimed price on a page nobody opened is refused for "${goal.slice(0, 30)}..."`,
      /was not observed as a live page/.test(officialRecordEvidenceGap(goal, record,
        { url: "https://search.test/?q=example", text: "ExampleCo Business Pro $14.16 USD" }, [])));
  }
  check("(d) ...and the same record cited off the page the run opened passes, on any wording",
    officialRecordEvidenceGap("Compare several plans and summarize them.", record,
      { url: "https://example.test/pricing/pro", title: "Business Pro",
        text: "Business Pro — $14.16 USD per user", elements: "" }, []) === "");
  check("(d) neither check reads the goal any more: a transport prefix changes nothing",
    completionEvidenceGap("[AUDIT:opaque] Give me three rentals with links.", cited, opened, journal)
      === completionEvidenceGap("Give me three rentals with links.", cited, opened, journal));
}

// ---------------------------------------------------------------------------
// (e) FAIL CLOSED. Deleting the branches must not have opened a way for a done
//     claim to pass when nobody can judge it.
// ---------------------------------------------------------------------------
{
  const goal = "Compare the monthly cost for Bell Canada, Telus, and Rogers.";
  const claim = "Bell: $65/mo, Telus: $70/mo, Rogers: $60/mo.";
  const tab = onPage(CARRIERS_PAGE);
  const calls = auditor("{}");
  const v = await verifyDone("test-key", "test-model", goal, claim, tab.id, { scope: goal });
  check("(e) an unreadable verdict, twice, stays unverified",
    v.verified === false && calls.audits === 2, `${JSON.stringify(v)} audits=${calls.audits}`);
}
{
  const goal = "Compare the monthly cost for Bell Canada, Telus, and Rogers.";
  const tab = onPage(CARRIERS_PAGE);
  globalThis.fetch = async () => { throw new Error("provider down"); };
  const v = await verifyDone("test-key", "test-model", goal, "Bell: $65/mo.", tab.id, { scope: goal });
  check("(e) a provider that cannot be reached stays unverified", v.verified === false);
}

// ---------------------------------------------------------------------------
// (f) THE RUN FINISHES. The blast radius was the run: eight verifier rounds
//     that never ran the verifier, then a false failure text. Drive the real
//     loop on the measured errand.
// ---------------------------------------------------------------------------
const GOAL = "Compare the monthly cost for Bell Canada, Telus, and Rogers.";
const CLAIM = "Bell: $65/mo, Telus: $70/mo, Rogers: $60/mo — Rogers is cheapest.";
async function drive(auditVerdict) {
  const asked = { step: 0, audit: 0 };
  const trace = [];
  harness.tabs.clear();
  harness.addTab({ url: "https://owner.example/notes", active: true });
  harness.mapPage = (tabId) => ({ ...CARRIERS_PAGE, url: harness.tabs.get(tabId)?.url || CARRIERS_PAGE.url });
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n") : String(m.content || ""))).join("\n");
    let content = "{}";
    if (AUDIT_SENTINEL.test(joined)) { asked.audit += 1; content = auditVerdict; }
    else if (STEP_SENTINEL.test(joined)) { asked.step += 1; content = JSON.stringify({ action: "done", result: CLAIM }); }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, readOnly: true, authorized: false, planning: false,
    startUrl: CARRIERS_PAGE.url, maxSteps: 8, budgetMs: 60_000, stillLive: async () => true,
    onTrace: (history) => { trace.length = 0; trace.push(...history); },
  });
  return { out, asked, trace };
}
{
  const { out, asked, trace } = await drive('{"verified":true}');
  check("(f) the run ends done with the comparison as its result",
    out.status === "done" && out.result === CLAIM, `${out.status}: ${String(out.result).slice(0, 140)}`);
  check("(f) ...on one step question and one audit", asked.step === 1 && asked.audit === 1,
    `step=${asked.step} audit=${asked.audit}`);
  check("(f) ...with no rejection and no reword round in the trace",
    !trace.some((line) => /done claim rejected|BLOCKED NO-ACTION DONE/.test(line)),
    trace.join(" | ").slice(0, 240));
}
{
  // THE CONTROL. Flip only the auditor and the identical run does not finish.
  const { out, asked } = await drive(grounded(
    "the goal names three carriers and the result gives only two",
    "Bell Canada", "Telus: $70/mo", "Bell: $65/mo", CARRIERS_PAGE.url));
  check("(f) flip the auditor to NO and the identical run does not end done",
    out.status !== "done" && asked.audit >= 1, `${out.status} audits=${asked.audit}`);
}

// ---------------------------------------------------------------------------
// (g) THE LAW LEG. The names are gone from the code, the record survives, and
//     nothing here is tape.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  for (const gone of ["comparisonNames", "completionShapeGap", "openEach"]) {
    check(`(g) law 1: ${gone} stays deleted from the code`, !code.includes(gone));
  }
  check("(g) no goal-word trigger survives in the two provenance checks",
    !/\\bofficial\\b/.test(code) && !/open\\s\+each/.test(code));
  check("(g) the record names the measured cases",
    /WHAT WAS HERE UNTIL 2026-09-05 \(F06\)/.test(src)
      && /the comparison result omits: Bell Canada/.test(src)
      && /requests 3 direct URLs but the result contains 1/.test(src));
  check("(g) ...and states the cost of running provenance on every errand",
    /THE COST, said plainly/.test(src) && /source_unvisited/.test(src));
  const marker = "TA" + "PE:";
  check("(g) no tape marker was added for this audit",
    !new RegExp(marker + "[^\\n]*(?:F06|comparison|direct URL)", "i").test(src));
}

if (failures) { console.log(`test_completion_shape_is_a_model_verdict: ${failures} FAILED`); process.exit(1); }
console.log("test_completion_shape_is_a_model_verdict: what the goal requires is the auditor's to read");
process.exit(0);
