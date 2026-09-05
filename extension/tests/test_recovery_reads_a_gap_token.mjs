// WHICH RECOVERY THE RUN TAKES WAS DECIDED BY THE VERIFIER'S PHRASING.
//
// F24. After a done claim is rejected, the loop picks what to do next — sleep
// and re-audit, press Escape on the owner's live page, scroll, open a cited
// URL, go and research, or let the model re-word its answer. Six regexes over
// the verifier's PROSE made that choice:
//
//     /load|spinner|progress|wait/i                     -> sleep 5s, re-audit
//     /not present|…|only shows|missing|unverified/     -> press Escape in the modal
//     /not observed|not opened|unvisited|never visited/ -> open the cited URL
//     missingCompletionEvidence / nonAuthoritativeCompletionEvidence -> research
//     outputOnlyCompletionGap                           -> allow a re-word with no action
//
// Some of those sentences are written by this file, where reading them back is
// a sense. But the same predicates ran over the MODEL's own sentence, and
// audit row #64 already classifies word lists over a model's reason as a law-1
// violation. Measured cost: an Escape keypress inside a live modal because a
// rejection said "missing", five seconds and a second audit call on a
// rejection that mentioned a "waitlist", a scroll-or-research choice made by
// phrasing.
//
// The verifier now says WHICH KIND of gap it found, as one token from a closed
// set, and the caller compares tokens. The polarity is a FLOOR: an absent or
// unrecognised token licenses none of the specific recoveries, because
// pressing Escape on someone's live page and sleeping five seconds are
// actions, and an action needs something to license it.
//
// THE TEST THIS SUITE IS BUILT AROUND: a reworded reason with the SAME token
// takes the same branch, and a DIFFERENT token with identical wording does
// not. That is the property a regex cannot have.
//
// Run: node extension/tests/test_recovery_reads_a_gap_token.mjs
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { verifyDone, completionGap, COMPLETION_GAPS, runAgentGoal } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const AUDIT_SENTINEL = /You audit a browser agent's claim/;
const STEP_SENTINEL = /You are Anticipy's browser agent/;
const GOAL = "Find the monthly price on the pricing page and tell me what it is.";
const CLAIM = "The Business plan is $14.16 per user per month.";
const PAGE = {
  url: "https://vendor.example/pricing",
  title: "Pricing",
  elements: "[0] <link> Plans @(10,10)",
  text: "Business — $14.16 per user per month",
  fields: [],
  overlay: true,
};

// One run of the real loop. The step model claims done once, the auditor
// rejects with a scripted (reason, gap), and everything the run then DOES is
// observed: keypresses, scrolls, navigations, extra audits, elapsed time.
async function runWithRejection({ reason, gap, verdictAfter = null, maxSteps = 6 }) {
  harness.tabs.clear();
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  harness.addTab({ url: "https://owner.example/notes", active: true });
  const seen = { audits: 0, steps: 0, keys: [], scrolls: 0, navigations: [] };
  harness.mapPage = (tabId) => ({ ...PAGE, url: harness.tabs.get(tabId)?.url || PAGE.url });
  harness.onCdp = (tabId, method, params) => {
    // pressKey dispatches rawKeyDown/keyUp, not keyDown — watch the down
    // edge it actually sends, or an Escape that IS pressed reads as absent.
    if (method === "Input.dispatchKeyEvent" && params?.type === "rawKeyDown") seen.keys.push(params.key || params.code);
    return undefined;
  };
  const realExecuteScript = chrome.scripting.executeScript;
  chrome.scripting.executeScript = async (opts) => {
    const src = opts?.func ? String(opts.func) : "";
    if (src.includes("scrollBy") || src.includes("__anticipyScroll") || src.includes("scrollTop")) {
      seen.scrolls += 1;
      return [{ result: { target: "document", moved: 900 } }];
    }
    return realExecuteScript(opts);
  };
  const realUpdate = chrome.tabs.update;
  chrome.tabs.update = async (id, props = {}) => {
    if (props && props.url !== undefined) seen.navigations.push(String(props.url));
    return realUpdate(id, props);
  };
  const rejection = JSON.stringify({
    verified: false, reason, ...(gap === undefined ? {} : { gap }),
    goal_quote: "monthly price", claimed_quote: "$14.16", evidence_quote: "$14.16",
    evidence_url: PAGE.url,
  });
  const trace = [];
  const startedAt = Date.now();
  // THE WAITS ARE ASSERTED, NOT SERVED. The still_loading recovery sleeps five
  // real seconds before re-auditing, and this suite drives that path a dozen
  // times; served literally it ran 143s and blew run_all.mjs's 120s per-suite
  // cap, so the suite passed alone and failed in the runner. Long sleeps are
  // compressed to ~0 and COUNTED instead, which is strictly more than the wall
  // clock was telling us: `seen.longWaits` is now evidence that the pause
  // happened, where elapsed time was only evidence that something was slow.
  // Short timers (the loop's own settle/poll delays) are left alone so nothing
  // reorders.
  const realSetTimeout = globalThis.setTimeout;
  seen.longWaits = [];
  globalThis.setTimeout = (fn, ms, ...rest) => {
    if (Number(ms) >= 1000) {
      seen.longWaits.push(Number(ms));
      return realSetTimeout(fn, 0, ...rest);
    }
    return realSetTimeout(fn, ms, ...rest);
  };
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n") : String(m.content || ""))).join("\n");
    let content = "{}";
    if (AUDIT_SENTINEL.test(joined)) {
      seen.audits += 1;
      content = (verdictAfter && seen.audits > 1) ? verdictAfter : rejection;
    } else if (STEP_SENTINEL.test(joined)) {
      seen.steps += 1;
      content = JSON.stringify({ action: "done", result: CLAIM });
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, readOnly: true, authorized: false, planning: false,
    startUrl: PAGE.url, maxSteps, budgetMs: 120_000, stillLive: async () => true,
    onTrace: (history) => { trace.length = 0; trace.push(...history); },
  });
  chrome.scripting.executeScript = realExecuteScript;
  chrome.tabs.update = realUpdate;
  globalThis.setTimeout = realSetTimeout;
  return { out, seen, trace, elapsed: Date.now() - startedAt };
}

// ---------------------------------------------------------------------------
// (a) THE PROPERTY. Same token, different words -> same branch. Same words,
//     different token -> different branch. A regex cannot do either.
// ---------------------------------------------------------------------------
{
  const wordings = [
    "the page had not finished rendering when I looked",
    "a skeleton placeholder stood where the price belongs",
    "the figure was still resolving",
  ];
  for (const reason of wordings) {
    const { seen } = await runWithRejection({ reason, gap: "still_loading",
      verdictAfter: '{"verified":true}' });
    check(`(a) still_loading re-audits once, however it is worded: "${reason.slice(0, 34)}..."`,
      seen.audits === 2, `audits=${seen.audits}`);
    check(`(a) ...after actually pausing for the page: "${reason.slice(0, 26)}..."`,
      seen.longWaits.includes(5000), `longWaits=${seen.longWaits.join(",")}`);
  }
  // None of those wordings contains load|spinner|progress|wait, so before the
  // fix every one of them skipped the re-check.
  check("(a) ...and none of those sentences would have matched the old regex",
    !wordings.some((r) => /load|spinner|progress|wait/i.test(r)));
}
{
  // IDENTICAL WORDING, different token. The sentence says "waitlist", which
  // the old regex read as "wait" and slept five seconds for.
  const reason = "the waitlist section does not carry the monthly price";
  const loading = await runWithRejection({ reason, gap: "still_loading", verdictAfter: '{"verified":true}' });
  const missing = await runWithRejection({ reason, gap: "missing_on_page" });
  check("(a) the SAME sentence with still_loading re-audits", loading.seen.audits === 2);
  check("(a) ...and paused, where the missing_on_page reading of it does not",
    loading.seen.longWaits.includes(5000) && !missing.seen.longWaits.includes(5000),
    `loading=${loading.seen.longWaits.join(",")} missing=${missing.seen.longWaits.join(",")}`);
  check("(a) ...and with missing_on_page does not — the words decided nothing",
    missing.seen.audits >= 1 && missing.seen.keys.includes("Escape"),
    `audits=${missing.seen.audits} keys=${missing.seen.keys.join(",")}`);
}

// ---------------------------------------------------------------------------
// (b) THE ESCAPE KEYPRESS. It happens on missing_on_page and on nothing else —
//     this is a key sent to the owner's live page.
// ---------------------------------------------------------------------------
{
  // The guard is `dismissedRejectedOverlays`, keyed by PAGE fingerprint: one
  // Escape per page that gets a missing_on_page rejection, and never a second
  // on that same page. Held to two steps the run stays on one page, so the
  // whole run is that one page's budget. (Over more steps the run navigates to
  // search and that different page gets its own single Escape, which is the
  // guard working, not leaking.)
  const { seen } = await runWithRejection({
    reason: "the price is not shown on this page", gap: "missing_on_page", maxSteps: 2 });
  check("(b) missing_on_page dismisses the overlay once", seen.keys.filter((k) => k === "Escape").length === 1,
    seen.keys.join(","));
  check("(b) ...and a second rejection on that same page does not press it again",
    seen.audits >= 2 && seen.keys.filter((k) => k === "Escape").length === 1,
    `audits=${seen.audits} keys=${seen.keys.join(",")}`);
}
for (const [gap, label] of [
  ["contradiction", "contradiction"], ["result_omits", "result_omits"],
  ["non_authoritative", "non_authoritative"], [undefined, "no gap at all"],
  ["", "an empty gap"], ["MISSING_ON_PAGE", "a mis-cased token"],
  ["missing_on_page and still_loading", "two tokens in one string"],
  ["the evidence is missing from the page", "the old regex's own words as the token"],
]) {
  const { seen } = await runWithRejection({
    reason: "the price is not present, not shown and missing from this page", gap });
  check(`(b) ...and never on ${label}`, !seen.keys.includes("Escape"), seen.keys.join(","));
}

// ---------------------------------------------------------------------------
// (c) THE CITED-URL RECOVERY. source_unvisited is the one branch that
//     navigates to a URL out of the model's own sentence. It needs the token.
// ---------------------------------------------------------------------------
{
  const cited = "the result cites https://vendor.example/plans/business which is not among the pages read";
  const withToken = await runWithRejection({ reason: cited, gap: "source_unvisited" });
  check("(c) source_unvisited opens the cited page",
    withToken.seen.navigations.some((u) => u === "https://vendor.example/plans/business"),
    withToken.seen.navigations.join(" | "));
  const withoutToken = await runWithRejection({ reason: cited, gap: undefined });
  check("(c) ...and the identical sentence with no token does NOT open it",
    !withoutToken.seen.navigations.some((u) => u === "https://vendor.example/plans/business"),
    withoutToken.seen.navigations.join(" | "));
  const wrongToken = await runWithRejection({ reason: cited, gap: "contradiction" });
  check("(c) ...nor does it under a different token",
    !wrongToken.seen.navigations.some((u) => u === "https://vendor.example/plans/business"),
    wrongToken.seen.navigations.join(" | "));
}

// ---------------------------------------------------------------------------
// (d) THE RE-WORD PERMIT. result_omits is the one gap where claiming done
//     again with no browser action in between is progress; every other gap
//     must be blocked as a no-action repeat.
// ---------------------------------------------------------------------------
{
  const reason = "the result gives the annual figure and the goal asked for the monthly one";
  const omits = await runWithRejection({ reason, gap: "result_omits", maxSteps: 4 });
  check("(d) result_omits lets the model correct its answer without acting first",
    omits.trace.some((line) => /allowing an output-only repair/.test(line)),
    omits.trace.join(" | ").slice(0, 240));
  const contradiction = await runWithRejection({ reason, gap: "contradiction", maxSteps: 4 });
  check("(d) ...and the identical sentence under contradiction is blocked as a no-action repeat",
    contradiction.trace.some((line) => /BLOCKED NO-ACTION DONE/.test(line))
      && !contradiction.trace.some((line) => /allowing an output-only repair/.test(line)),
    contradiction.trace.join(" | ").slice(0, 240));
  const none = await runWithRejection({ reason, gap: undefined, maxSteps: 4 });
  check("(d) ...and with no token at all the stricter path runs — the floor",
    !none.trace.some((line) => /allowing an output-only repair/.test(line)),
    none.trace.join(" | ").slice(0, 240));
}

// ---------------------------------------------------------------------------
// (e) THE DETERMINISTIC GAPS NAME THEMSELVES. verifyDone's own refusals have
//     always known their category; they carry it now instead of writing a
//     sentence for a regex to read back.
// ---------------------------------------------------------------------------
{
  harness.tabs.clear();
  const tab = harness.addTab({ url: PAGE.url, active: false });
  harness.mapPage = () => PAGE;
  globalThis.fetch = async () => ({ ok: true, status: 200,
    json: async () => ({ choices: [{ message: { content: '{"verified":true}' } }] }), text: async () => "" });
  const cited = "The price is $14.16, from https://vendor.example/never-opened";
  const v = await verifyDone("test-key", "test-model", GOAL, cited, tab.id, { scope: GOAL });
  check("(e) a cited page nobody opened is source_unvisited",
    v.verified === false && v.gap === "source_unvisited", JSON.stringify(v));
  // The claimed figure must be one the opened page does NOT carry. PAGE shows
  // "Business — $14.16"; a record claiming 14.16 is CORRECTLY verified, so the
  // number here is deliberately absent from the page.
  const record = [{ plan_name: "Business", displayed_price: "19.99", currency: "USD",
                    url: "https://vendor.example/pricing" }];
  const wrong = await verifyDone("test-key", "test-model", GOAL, record, tab.id, { scope: GOAL });
  check("(e) a cited page that WAS opened and lacks the number is non_authoritative",
    wrong.verified === false && wrong.gap === "non_authoritative", JSON.stringify(wrong));
  const facts = await verifyDone("test-key", "test-model", GOAL, "Booked.", tab.id,
    { scope: GOAL, facts: "guest: Alex Reyes", effectState: { fields: [], elements: "", url: PAGE.url } });
  check("(e) an approved fact with no evidence on the page is missing_on_page",
    facts.verified === false && facts.gap === "missing_on_page", JSON.stringify(facts));
}

// ---------------------------------------------------------------------------
// (f) THE TOKEN READER IS A FLOOR, AND THE CONTRACT IS IN THE PROMPT.
// ---------------------------------------------------------------------------
{
  check("(f) the closed set is exactly six categories", COMPLETION_GAPS.size === 6);
  for (const token of [...COMPLETION_GAPS]) check(`(f) ${token} is accepted`, completionGap(token) === token);
  for (const junk of ["", " ", "missing", "MISSING_ON_PAGE", "still loading", "gap", null, undefined, 7, {}]) {
    check(`(f) ${JSON.stringify(junk)} is no gap at all`, completionGap(junk) === "");
  }
  // The bytes actually sent: the auditor is asked for the token, told what
  // each one means, and told to omit rather than guess.
  harness.tabs.clear();
  const tab = harness.addTab({ url: PAGE.url, active: false });
  harness.mapPage = () => PAGE;
  let prompt = "";
  globalThis.fetch = async (url, opts = {}) => {
    const joined = JSON.parse(opts.body).messages.map((m) => String(m.content || "")).join("\n");
    if (AUDIT_SENTINEL.test(joined)) prompt = joined;
    return { ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content: '{"verified":true}' } }] }), text: async () => "" };
  };
  await verifyDone("test-key", "test-model", GOAL, CLAIM, tab.id, { scope: GOAL });
  check("(f) the reply contract asks for the token", /"gap":"<one token, below>"/.test(prompt));
  for (const token of [...COMPLETION_GAPS]) {
    check(`(f) ...and defines ${token}`, new RegExp(`${token} \\(`).test(prompt));
  }
  check("(f) ...and tells it to omit the field rather than guess",
    /omit the field entirely rather than guessing/.test(prompt));
}

// ---------------------------------------------------------------------------
// (g) THE LAW LEG. The six predicates are gone from the code.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  for (const gone of ["outputOnlyCompletionGap", "missingCompletionEvidence",
                      "nonAuthoritativeCompletionEvidence"]) {
    check(`(g) law 1: ${gone} stays deleted from the code`, !code.includes(gone));
  }
  check("(g) the three inline reason regexes are gone too",
    !/load\|spinner\|progress\|wait/.test(code)
      && !/not observed\|not opened\|unvisited\|never visited/.test(code)
      && !/only shows\|missing\|unverified/.test(code));
  check("(g) the record names the six predicates and what they cost",
    /WHAT KIND OF GAP THE VERIFIER FOUND/.test(src) && /waitlist/.test(src)
      && /audit row #64/.test(src));
  const marker = "TA" + "PE:";
  check("(g) no tape marker was added for this audit",
    !new RegExp(marker + "[^\\n]*(?:F24|gap|recovery)", "i").test(src));
}

if (failures) { console.log(`test_recovery_reads_a_gap_token: ${failures} FAILED`); process.exit(1); }
console.log("test_recovery_reads_a_gap_token: the recovery is chosen by a token, never by the verifier's wording");
process.exit(0);
