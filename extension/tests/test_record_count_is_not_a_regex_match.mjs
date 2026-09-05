// A FINISHED RESEARCH ERRAND WAS REPORTED AS FAILED, AND NO MODEL EVER READ IT.
//
// `completionShapeGap` opened with `explicitRequestedCount` — a regex over the
// owner's sentence for "find|list|show|open ... three" — and
// `reportedRecordCount` — regexes over how the agent happened to word its
// answer: numbered lines, "Option N", "found N", bare URLs. When the two
// numbers disagreed, verifyDone returned verified:false before mapPage and
// before the auditor ran. Audit #74.
//
// Measured on the shipped functions, 2026-09-05, with the fixtures below:
//   goal   "Find three active listings under $2,500 near Commercial Drive and
//           report the rent for each"
//   claim  three addresses and three rents, in prose
//                                  -> "the goal requests 3 records but the result contains 0"
//   claim  the same three as {listings:{a,b,c}}       -> "... contains 1"
//   claim  [{id:1},{id:2},{id:3}], three EMPTY records -> ""  (passed)
//   goal   "Open two tabs and compare the fare on each" -> "requests 2 ... contains 0"
//   goal   "Set the table to show 5 rows per page ..."  -> "requests 5 ... contains 0"
//   and outputOnlyCompletionGap(that reason) === true, so the loop asked the
//   model to REWORD a correct answer, every rewording met the same regex, and
//   at eight rejections the owner was texted that a finished errand could not
//   be verified.
//
// The auditor already owns this question — "if the goal asks for N records/
// options, count them and verify=false when any is missing" — with the goal,
// the claim, the live page and the run's evidence in front of it, and its
// rejection must ground verbatim quotes in the goal and the claim. The fix is
// the #65 shape: the regex is gone, the auditor is the only judge of the
// count, and the measured shapes above ride into its prompt as teaching.
//
// This suite proves the auditor is now ASKED, in both directions; that
// nothing got looser (the floor still refuses without a verdict); that the
// teaching actually reaches the model; that the names are gone from the code;
// and — the blast radius itself — that the RUN now finishes.
//
// Run: node extension/tests/test_record_count_is_not_a_regex_match.mjs
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { verifyDone, completionEvidenceGap, runAgentGoal } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  [${detail}]`}`);
  if (!ok) failures++;
};

const GOAL = "Find three active listings under $2,500 near Commercial Drive and report the rent for each";
const PROSE = "1848 E 3rd Ave rents for $2,150 a month, 2211 Grant St for $2,300 and 1020 Victoria Dr for $1,975 — all three are active and under $2,500.";
const NESTED = { listings: {
  a: { address: "1848 E 3rd Ave", rent: "$2,150" },
  b: { address: "2211 Grant St", rent: "$2,300" },
  c: { address: "1020 Victoria Dr", rent: "$1,975" },
} };
const TWO = "1848 E 3rd Ave rents for $2,150 a month and 2211 Grant St for $2,300; both are active and under $2,500.";
const EMPTY3 = [{ id: 1 }, { id: 2 }, { id: 3 }];
const LISTINGS_PAGE = {
  url: "https://listings.example/search?near=commercial-drive&max=2500",
  title: "3 results near Commercial Drive",
  elements: "[0] <link> 1848 E 3rd Ave @(10,10)\n[1] <link> 2211 Grant St @(10,40)\n[2] <link> 1020 Victoria Dr @(10,70)",
  text: "1848 E 3rd Ave — 1 bed — $2,150/mo — active\n2211 Grant St — 1 bed — $2,300/mo — active\n1020 Victoria Dr — studio — $1,975/mo — active",
  fields: [],
};
const AUDIT_SENTINEL = /You audit a browser agent's claim/;
const opts = { scope: GOAL, facts: "", effectState: null, ownerProfile: null, evidenceJournal: [] };

// A mocked auditor with a scripted verdict. Counts how often it is asked and
// keeps the bytes it was sent, which is the whole measurement. `reply` may be
// a string, an Error (thrown from fetch), {status} (a non-2xx transport), or
// a function of the attempt number returning any of those.
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
    if (content instanceof Error) throw content;
    if (content && typeof content === "object") {
      return { ok: false, status: content.status, json: async () => ({}), text: async () => "" };
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return calls;
}
let mapped = 0;
function onPage(page) {
  harness.tabs.clear();
  const tab = harness.addTab({ url: page.url, active: false });
  mapped = 0;
  harness.mapPage = () => { mapped += 1; return page; };
  return tab;
}
const grounded = (reason, goalQuote, claimedQuote, evidenceQuote) => JSON.stringify({
  verified: false, reason, goal_quote: goalQuote, claimed_quote: claimedQuote,
  evidence_quote: evidenceQuote, evidence_url: LISTINGS_PAGE.url,
});

// ------------------------------------------------------ (a) THE DEFECT
// The exact goal and a correct three-record answer in prose, on the page that
// shows all three, with an auditor that reads it and says yes. Measured
// before the fix: verified=false, mapPage 0, audits 0 — nobody ever looked.
let teachingPrompt = "";
{
  const tab = onPage(LISTINGS_PAGE);
  const calls = auditor('{"verified":true}');
  const v = await verifyDone("test-key", "test-model", GOAL, PROSE, tab.id, opts);
  check("(a) a correct three-record answer in prose verifies", v.verified === true, JSON.stringify(v));
  check("(a) ...because the page was actually read", mapped >= 1);
  check("(a) ...and the auditor was actually asked, once", calls.audits === 1);
  check("(a) ...and the receipt records that a model audited it",
    (v.evidence || []).some((e) => e === "proof:independent-model-audit"));
  teachingPrompt = calls.prompts[0] || "";
}
// The same three records as a nested object — "contains 1" before the fix.
{
  const tab = onPage(LISTINGS_PAGE);
  const calls = auditor('{"verified":true}');
  const v = await verifyDone("test-key", "test-model", GOAL, NESTED, tab.id, opts);
  check("(a) the same three records as a nested object verify — layout is not the count",
    v.verified === true && calls.audits === 1, JSON.stringify(v));
}

// ------------------------------------------------------ (b) THE OTHER DIRECTION
// Two records for a goal that asks for three. The auditor, given the page
// that shows the third, says no — and its reason is ITS sentence, grounded in
// the goal and the claim, never the regex's fixed one.
{
  const tab = onPage(LISTINGS_PAGE);
  const calls = auditor(grounded(
    "the goal asks for three listings and the result names only two; the third listing on the page, 1020 Victoria Dr, is absent from the result",
    "Find three active listings", "2211 Grant St for $2,300", "1020 Victoria Dr"));
  const v = await verifyDone("test-key", "test-model", GOAL, TWO, tab.id, opts);
  check("(b) a genuinely short answer is still rejected", v.verified === false);
  check("(b) ...by the auditor, which was asked", calls.audits === 1);
  check("(b) ...with the auditor's own grounded reason, never the regex's",
    /third listing/.test(String(v.reason || "")) && !/the goal requests \d+ records/.test(String(v.reason || "")),
    String(v.reason));
}

// ------------------------------------------------------ (c) THE REGEX'S FALSE PASS
// Three EMPTY records satisfied the regex ("" — passed) because it counted
// braces, not rents. The auditor is asked and, reading what the goal asks
// for, rejects them. Nothing got looser.
{
  const tab = onPage(LISTINGS_PAGE);
  const calls = auditor(grounded(
    "the result has three entries but none carries a rent; the goal asks for the rent for each and the page shows $2,150/mo for the first",
    "report the rent for each", '{"id":1}', "$2,150/mo"));
  const v = await verifyDone("test-key", "test-model", GOAL, EMPTY3, tab.id, opts);
  check("(c) three empty records are rejected", v.verified === false);
  check("(c) ...by the auditor, which was asked", calls.audits === 1);
}

// ------------------------------------------------------ (d) NOT A RECORD COUNT
// A number in the goal that is not a count of records to deliver. Both were
// walled before the fix ("requests 2 ... contains 0", "requests 5 ... 0").
for (const [goal, claim] of [
  ["Open two tabs and compare the fare on each",
    "The fare is $4.05 on the first tab and $3.85 on the second; the second is cheaper."],
  ["Set the table to show 5 rows per page and tell me the first row",
    "Set to 5 rows per page; the first row is 1848 E 3rd Ave at $2,150."],
]) {
  const tab = onPage(LISTINGS_PAGE);
  const calls = auditor('{"verified":true}');
  const v = await verifyDone("test-key", "test-model", goal, claim, tab.id, { ...opts, scope: goal });
  check(`(d) "${goal.slice(0, 26)}..." reaches the auditor and verifies`,
    v.verified === true && calls.audits === 1, JSON.stringify(v));
}

// ------------------------------------------------------ (e) FAIL CLOSED — FOUR STATES
// Removing the regex must not have opened a way for "done" to slip through
// when nobody can judge it. yes / no are (a) and (b); these are the other two.
{
  // unclear: the auditor answers, unreadably, twice
  const tab = onPage(LISTINGS_PAGE);
  const calls = auditor("{}");
  const v = await verifyDone("test-key", "test-model", GOAL, PROSE, tab.id, opts);
  check("(e) an unreadable verdict, twice, stays unverified", v.verified === false && calls.audits === 2,
    `${JSON.stringify(v)} audits=${calls.audits}`);
}
{
  // no-verdict: the transport says 500 every time
  const tab = onPage(LISTINGS_PAGE);
  const calls = auditor({ status: 500 });
  const v = await verifyDone("test-key", "test-model", GOAL, PROSE, tab.id, opts);
  check("(e) a provider that only ever fails stays unverified", v.verified === false && calls.audits >= 1);
}
{
  // no-verdict: the transport throws every time
  const tab = onPage(LISTINGS_PAGE);
  const calls = auditor(new Error("provider down"));
  const v = await verifyDone("test-key", "test-model", GOAL, PROSE, tab.id, opts);
  check("(e) a provider that cannot be reached stays unverified", v.verified === false && calls.audits >= 1,
    JSON.stringify(v));
}

// ------------------------------------------------------ (f) THE TEACHING RIDES IN
// The bytes actually sent to the auditor in (a): the count/named-parts
// instruction that makes it the judge, the measured shapes as teaching, and
// the goal and the claim verbatim — it judges the real claim, not a summary.
{
  check("(f) the auditor is told to count records and named items",
    /asks for N records\/options, count them and verify=false/.test(teachingPrompt));
  check("(f) ...that layout is not the count (prose, a numbered list and JSON)",
    /Count what the result DELIVERS, not how it is laid out/.test(teachingPrompt)
      && /prose, a numbered list and JSON/.test(teachingPrompt));
  check("(f) ...that a named record with none of the asked-for details is missing",
    /carries none of the details the goal asks for/.test(teachingPrompt));
  check("(f) ...that a number which is not a record count creates no requirement",
    /creates no record requirement/.test(teachingPrompt) && /rows per page/.test(teachingPrompt));
  check("(f) ...and it sees the goal and the claim verbatim",
    teachingPrompt.includes(`GOAL: ${GOAL}`) && teachingPrompt.includes(`CLAIMED RESULT: ${PROSE}`));
}

// ------------------------------------------------------ (g) THE LAW LEG
// The names stay gone from the CODE (they survive in the comment that records
// what they did), and the one other place the count was read — the "N
// underlying pages" return in completionEvidenceGap — is gone behaviourally:
// two cited-and-visited pages on a "find three, open each" goal are the
// auditor's to judge, while a cited page the run never opened is still
// refused, because that is provenance and not a count.
{
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  for (const gone of ["COUNT_WORDS", "explicitRequestedCount", "reportedRecordCount",
                      "completionCoverageScore", "bestCompletionCoverage"]) {
    check(`(g) law 1: ${gone} stays deleted from the code`, !code.includes(gone));
  }
  check("(g) the record of what was here names the measured cases",
    /WHAT WAS HERE UNTIL 2026-09-05 \(audit #74\)/.test(src)
      && /three EMPTY records/.test(src) && /Open two tabs/.test(src));
  const opened = { url: "https://example.test/listing/one", title: "one", text: "", elements: "" };
  const journal = [{ url: "https://example.test/listing/two" }];
  const twoVisited = [{ url: "https://example.test/listing/one" }, { url: "https://example.test/listing/two" }];
  check("(g) two visited pages on 'find three, open each' are not walled by a count",
    completionEvidenceGap("Find three records. Open each actual listing and report the direct URL.",
      twoVisited, opened, journal) === "");
  check("(g) ...while a cited page the run never opened is still refused — provenance stays",
    /listing\/three/.test(completionEvidenceGap(
      "Find three records. Open each actual listing and report the direct URL.",
      [...twoVisited, { url: "https://example.test/listing/three" }], opened, journal)));
  // The marker is spelled in two halves so overnight/tape_gate.py's own scan
  // does not read this assertion as a piece of unregistered tape.
  const marker = "TA" + "PE:";
  check("(g) no tape marker remains for this audit — nothing string-shaped survived to expire",
    !new RegExp(marker + "[^\\n]*(?:#74|record count|explicitRequestedCount|reportedRecordCount)", "i").test(src));
}

// ------------------------------------------------------ (h) THE RUN FINISHES
// The blast radius was the RUN: a finished errand reported as failed after
// eight verifier rounds that never ran the verifier. Drive the real loop on a
// read-only research errand whose step model answers correctly in prose on
// its first step. With the auditor saying yes the run must end done, having
// asked exactly one step question and one audit and nothing else; with the
// auditor saying no it must not — so what decides is the verdict.
const STEP_SENTINEL = /You are Anticipy's browser agent/;
async function drive(auditVerdict) {
  const asked = { step: 0, audit: 0, other: [] };
  const trace = [];
  harness.tabs.clear();
  harness.addTab({ url: "https://owner.example/notes", active: true });
  harness.mapPage = (tabId) => ({ ...LISTINGS_PAGE, url: harness.tabs.get(tabId)?.url || LISTINGS_PAGE.url });
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n") : String(m.content || ""))).join("\n");
    let content = "{}";
    if (AUDIT_SENTINEL.test(joined)) { asked.audit += 1; content = auditVerdict; }
    else if (STEP_SENTINEL.test(joined)) { asked.step += 1; content = JSON.stringify({ action: "done", result: PROSE }); }
    else asked.other.push(joined.slice(0, 80));
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, readOnly: true, authorized: false, planning: false,
    startUrl: LISTINGS_PAGE.url, maxSteps: 6, budgetMs: 60_000, stillLive: async () => true,
    onTrace: (history) => { trace.length = 0; trace.push(...history); },
  });
  return { out, asked, trace };
}
{
  const { out, asked, trace } = await drive('{"verified":true}');
  check("(h) the run ends done with the prose answer as its result",
    out.status === "done" && out.result === PROSE, JSON.stringify(out).slice(0, 200));
  check("(h) ...having asked one step question and one audit, and no other model question",
    asked.step === 1 && asked.audit === 1 && asked.other.length === 0,
    `step=${asked.step} audit=${asked.audit} other=${JSON.stringify(asked.other)}`);
  check("(h) ...with no rejection, no reword round and no research in the trace",
    !trace.some((line) => /done claim rejected|BLOCKED NO-ACTION DONE|RESEARCH after rejected completion/.test(line)),
    trace.join(" | ").slice(0, 300));
  check("(h) ...and a receipt that says a model verified it",
    !!out.receipt && out.receipt.verified === true
      && (out.receipt.evidence || []).some((e) => e === "proof:independent-model-audit"));
}
{
  // THE CONTROL. Flip only the auditor to a grounded no and the identical run
  // does not finish — so what decided above was the verdict, not the fixture.
  const { out, asked, trace } = await drive(grounded(
    "the goal asks for three listings and the result names only two; the third listing on the page, 1020 Victoria Dr, is absent from the result",
    "Find three active listings", "2211 Grant St for $2,300", "1020 Victoria Dr"));
  check("(h) flip the auditor to NO and the identical run does not end done",
    out.status !== "done" && asked.audit >= 1, `${out.status} audits=${asked.audit}`);
  check("(h) ...and the trace says the auditor rejected it, in the auditor's words",
    trace.some((line) => /done claim rejected \(the goal asks for three listings/.test(line)));
}

if (failures) { console.log(`test_record_count_is_not_a_regex_match: ${failures} FAILED`); process.exit(1); }
console.log("test_record_count_is_not_a_regex_match: a record count is a model's verdict, never a regex's");
