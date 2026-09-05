// AFTER A CRASH, "DID THE SEND HAPPEN?" IS ANSWERED BY LOOKING, NOT BY A CONSTANT.
//
// Audit #90, the reconciliation half. A worker reclaimed between a
// consequential click and its receipt used to leave the owner one constant
// sentence, and his Try again used to become a constant reconciliation
// written on his behalf ("owner explicitly checked the destination before
// retry") — which is exactly what the DB guard's retry leg checks. Now the
// surviving tab is read once, ONE model question is asked, and the answer is
// written beside the intent in four states. The row still parks: nothing in
// this path may write done or queued.
//
// Six legs, each behavioural — it drives the real reader, the real row
// writers, the real loop, and the real sweep, and watches what reaches the
// model, the page and the row:
//   A  THE FLOOR      reconcileUncertainEffect: the four states, a closed
//                     token set, and no call at all without an intent, a tab
//                     or the right host
//   B  THE ONLY PATCH recoveryFor, every verdict × both lease states: always
//                     needs_user, never done, never queued
//   C  WHICH HOST     background.js recoverUncertainEffect against a mock
//                     Chrome: a tab that moved to the owner's bank is neither
//                     read nor shipped
//   D  THE ERASURE    rowWriters: the intent survives the next throttled trace
//                     write, and its `after` half lands at once
//   E  THE LOOP       runAgentGoal hands the checkpoint the `after` half is
//                     derived from, and the pre-click page never qualifies
//   F  THE SWEEP      a crashed running row, through the real poll: one model
//                     call, one needs_user write carrying the verdict
//
// Run: node extension/tests/test_reconcile_after_crash.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { installChrome } from "./chrome_mock.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const harness = installChrome();
const sessionData = {};
globalThis.chrome.storage.session = {
  get: async (keys) => {
    const want = typeof keys === "string" ? [keys] : keys;
    const out = {};
    for (const k of want) if (k in sessionData) out[k] = sessionData[k];
    return out;
  },
  set: async (obj) => { Object.assign(sessionData, obj); },
};
globalThis.fetch = async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => "" });

const {
  APPLIED, NOT_APPLIED, UNCLEAR, NO_VERDICT,
  reconcileUncertainEffect, recoveryFor, readReconcileReply, sameHostAsIntent,
} = await import("../reconcile.js");
const { rowWriters, recoverUncertainEffect } = await import("../background.js");
const { effectIntentAfter, parseJobParams } = await import("../workflow_state.js");
const { runAgentGoal } = await import("../agent_loop.js");
// The worker polls on import, exactly as it does on boot. Let that settle so
// its writes cannot land in the middle of a leg below.
await new Promise((r) => setTimeout(r, 30));

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

// ------------------------------------------------------------- fixtures
const INTENT = Object.freeze({
  doing: "Clicking Book table on fixture.test", url: "https://fixture.test/book",
  sig: "https://fixture.test/book|click|button|Book table|||book-table|3",
  digest: "d1gest", at: "2026-09-05T00:00:00.000Z", step: 1, tab: 7, session: "sess-A",
});
// The surviving page. Its FIELDS carry a value on purpose: the leg below
// asserts that value never reaches the model or the row.
const CONFIRM = Object.freeze({
  url: "https://fixture.test/book/confirm", title: "Reservation confirmed",
  elements: "[1] <link> Modify reservation @(10,10)",
  text: "Your table for 6 is booked. Reference RG-88214.",
  fields: [{ index: 1, name: "guest_name", label: "Name", type: "text", value: "Alex Reyes" }],
});
// The owner's own page, in the tab the run used to own.
const BANK = Object.freeze({
  url: "https://bank.example/accounts", title: "Accounts",
  elements: "[1] <button> Transfer @(10,10)", text: "Chequing balance 4,210.55", fields: [],
});

const MIN = 60 * 1000;
function job({ intent = INTENT, leaseLive = true, params: extraParams = {}, ...extra } = {}) {
  const until = new Date(Date.now() + (leaseLive ? 2 * MIN : -10 * MIN)).toISOString();
  const claimed = new Date(Date.now() - (leaseLive ? 1 : 12) * MIN).toISOString();
  const wf = {
    plan_id: "plan-1", owner_ref: "owner-1", lineage_key: "lin-1", version: 3,
    goal: "book a table for 6 under the name Alex Reyes", consequence: "consequential",
    state: "running", facts: {}, required: [],
    approval: { plan_id: "plan-1", plan_version: 3, scope_digest: "scope-3",
                owner_words: "yes, book it", approved_at: "2026-09-05T00:00:00.000Z" },
    lease: { token: "lease-1", actor_id: "agent-1", acquired_at: claimed, expires_at: until, attempt: 1 },
    receipt: null, attempts: 1, reason: "claimed",
    created_at: "2026-09-05T00:00:00.000Z", updated_at: claimed,
  };
  return {
    id: "job-1", status: "running", goal: "agent_goal", owner_ref: "owner-1", lane: "",
    workflow_id: "plan-1", workflow_version: 3, workflow_state: "running",
    consequence: "consequential", lineage_key: "lin-1", effect_key: "effect-3",
    effect_uncertain: true, attempts: 1, lease_token: "lease-1", lease_until: until,
    claimed_by: "agent-1", claimed_at: claimed, result: "", trace: "",
    updated: claimed, created: "2026-09-05T00:00:00.000Z",
    params: JSON.stringify({ task: wf.goal, _workflow: wf,
      ...(intent ? { _effect_intent: intent } : {}), ...extraParams }),
    ...extra,
  };
}

// ============================================================ A. THE FLOOR
{
  const cases = [
    ["APPLIED", APPLIED], ["NOT_APPLIED", NOT_APPLIED], ["UNCLEAR", UNCLEAR],
    ["", NO_VERDICT],
    ["looks like it didn't go through", NO_VERDICT],
    ["APPLIED — I think", NO_VERDICT],
    ['{"verdict":"APPLIED"}', NO_VERDICT],
    ["NOT_APPLIED\nAPPLIED", NO_VERDICT],
    ["applied", NO_VERDICT],
  ];
  for (const [reply, want] of cases) {
    let asked = 0;
    const out = await reconcileUncertainEffect({
      intent: INTENT, tabUrl: CONFIRM.url, readPage: async () => CONFIRM,
      askModel: async () => { asked += 1; return reply; },
    });
    check(`A: reply ${JSON.stringify(reply)} reads as ${want}`, out.verdict === want && asked === 1,
      `${out.verdict}, asked ${asked}`);
  }
  const thrown = await reconcileUncertainEffect({
    intent: INTENT, tabUrl: CONFIRM.url, readPage: async () => CONFIRM,
    askModel: async () => { throw new Error("502"); },
  });
  check("A: a model that throws is NO_VERDICT — nobody answered is not a no",
    thrown.verdict === NO_VERDICT && /nobody could answer/.test(thrown.why));
  check("A: the reader is whole-token: readReconcileReply alone agrees",
    readReconcileReply(" APPLIED ") === APPLIED && readReconcileReply("APPLIED.") === NO_VERDICT
      && readReconcileReply(null) === NO_VERDICT);

  // No intent, no tab: neither the page nor the model is touched.
  for (const [name, args] of [
    ["no intent record", { intent: null, tabUrl: CONFIRM.url }],
    ["no surviving tab", { intent: INTENT, tabUrl: "" }],
    ["a tab on another site", { intent: INTENT, tabUrl: BANK.url }],
  ]) {
    let asked = 0, read = 0;
    const out = await reconcileUncertainEffect({
      ...args, readPage: async () => { read += 1; return CONFIRM; },
      askModel: async () => { asked += 1; return "APPLIED"; },
    });
    check(`A: ${name} -> NO_VERDICT with nothing read and nothing asked`,
      out.verdict === NO_VERDICT && asked === 0 && read === 0, `${out.verdict} read ${read} asked ${asked}`);
  }
  // The page can move between the tab query and the read: the read page's
  // host is checked again, and a page that moved is not shipped.
  {
    let asked = 0;
    const out = await reconcileUncertainEffect({
      intent: INTENT, tabUrl: CONFIRM.url, readPage: async () => BANK,
      askModel: async () => { asked += 1; return "APPLIED"; },
    });
    check("A: a page that moved hosts between the tab query and the read is not shipped",
      out.verdict === NO_VERDICT && asked === 0 && /moved on/.test(out.why));
  }
  // A submit that redirected to a confirmation domain: the first page after
  // the click names a second permitted host.
  {
    let asked = 0;
    const out = await reconcileUncertainEffect({
      intent: { ...INTENT, after: { url: "https://pay.fixture.test/done", title: "Done", fingerprint: "f", step: 2 } },
      tabUrl: "https://pay.fixture.test/done?ref=1",
      readPage: async () => ({ ...CONFIRM, url: "https://pay.fixture.test/done?ref=1" }),
      askModel: async () => { asked += 1; return "APPLIED"; },
    });
    check("A: the host of the first page AFTER the click is permitted too", out.verdict === APPLIED && asked === 1);
    check("A: sameHostAsIntent is exact — a lookalike host is not the intent's",
      !sameHostAsIntent(INTENT, "https://fixture.test.evil.example/book")
        && !sameHostAsIntent(INTENT, "https://notfixture.test/book")
        && sameHostAsIntent(INTENT, "https://FIXTURE.test/anything"));
  }
  // What the model is shown, and what it is not.
  {
    let sent = null;
    const out = await reconcileUncertainEffect({
      intent: INTENT, tabUrl: CONFIRM.url, readPage: async () => CONFIRM,
      askModel: async (system, user) => { sent = { system, user }; return "APPLIED"; },
    });
    check("A: the model sees the intent's sentence and the surviving page's text",
      out.verdict === APPLIED && sent.user.includes("Clicking Book table on fixture.test")
        && sent.user.includes("RG-88214") && sent.user.includes("Modify reservation"));
    check("A: the model does NOT see the page's form values",
      !sent.user.includes("Alex Reyes") && !sent.system.includes("Alex Reyes"));
    check("A: the question is asked on its own — its own system prompt, a bare-token reply",
      /exactly one token: APPLIED, NOT_APPLIED, or UNCLEAR/.test(sent.system)
        && /If you are not sure, answer UNCLEAR/.test(sent.system));
    check("A: the page rides inside one-time fences, and the intent does too",
      /<page_text [0-9a-f]+>/.test(sent.user) && /<intent [0-9a-f]+>/.test(sent.user));
    check("A: the evidence written back is structure, never the page's words",
      out.evidence.some((e) => e === "host:fixture.test") && out.evidence.some((e) => e.startsWith("fingerprint:"))
        && !out.evidence.join(" ").includes("RG-88214") && !out.evidence.join(" ").includes("Alex Reyes"));
  }
}

// ======================================================= B. THE ONLY PATCH
{
  for (const leaseLive of [true, false]) {
    for (const verdict of [APPLIED, NOT_APPLIED, UNCLEAR, NO_VERDICT]) {
      const j = job({ leaseLive });
      const outcome = { verdict, why: verdict === NO_VERDICT ? "the tab had moved on to a different site" : "",
        evidence: ["host:fixture.test", `verdict:${verdict}`] };
      const patch = recoveryFor(j, outcome);
      const tag = `${verdict}, lease ${leaseLive ? "live" : "expired"}`;
      check(`B: ${tag}: parks as needs_user`,
        patch.status === "needs_user" && patch.workflow_state === "needs_user");
      check(`B: ${tag}: never done, never queued, no receipt`,
        !["done", "queued", "succeeded"].includes(patch.status) && !patch.receipt);
      check(`B: ${tag}: effect_uncertain stays true — the tap is still his`, patch.effect_uncertain === true);
      const p = parseJobParams(patch);
      check(`B: ${tag}: _reconciliation is written beside the intent, which survives`,
        p._reconciliation?.verdict === verdict && Array.isArray(p._reconciliation.evidence)
          && /^\d{4}-\d{2}-\d{2}T/.test(p._reconciliation.at) && p._effect_intent?.digest === "d1gest");
      check(`B: ${tag}: the embedded plan parks and drops its lease`,
        p._workflow.state === "needs_user" && p._workflow.lease === null && patch.lease_token === "");
      check(`B: ${tag}: the sentence names the control and the page, in reason and result alike`,
        patch.result.includes("Clicking Book table on fixture.test")
          && patch.result.includes("https://fixture.test/book") && patch.result === p._workflow.reason);
    }
  }
  const say = (verdict, why = "") => recoveryFor(job(), { verdict, why, evidence: [] }).result;
  check("B: APPLIED tells him it went through and that nothing will be touched again",
    /went through/.test(say(APPLIED)) && /not touching it again/.test(say(APPLIED)));
  check("B: NOT_APPLIED tells him it did not go through and to check before a retry",
    /did not go through/.test(say(NOT_APPLIED)) && /try again/.test(say(NOT_APPLIED)));
  check("B: UNCLEAR keeps the standing warning and says the page could not tell",
    /Check the site before I try again/.test(say(UNCLEAR)) && /could not tell either way/.test(say(UNCLEAR)));
  check("B: NO_VERDICT keeps the standing warning and says why nothing could be said",
    /Check the site before I try again/.test(say(NO_VERDICT, "the page it was on is gone"))
      && /I could not look: the page it was on is gone/.test(say(NO_VERDICT, "the page it was on is gone")));
  check("B: four sentences are four different sentences",
    new Set([APPLIED, NOT_APPLIED, UNCLEAR, NO_VERDICT].map((v) => say(v, "x"))).size === 4);
}

// ========================================== C. WHICH HOST, through Chrome
const BASE = "http://127.0.0.1:8090";
const patches = [];       // every jobs PATCH: {id, body, lease}
const modelCalls = [];    // every /agent/llm body
let runningRows = [];     // what the sweep's running-lane read returns
let reply = "APPLIED";
let modelStatus = 200;
const pages = new Map();  // tabId -> page map
let reads = 0;
harness.mapPage = (tabId) => { reads += 1; return pages.get(tabId) || BANK; };
const respond = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status,
  json: async () => body, text: async () => JSON.stringify(body),
});
// The fake backend for legs C and F. Named, because leg E swaps in the
// loop's own model mock and reset() has to put this one back.
const backendFetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.includes("/agent/llm")) {
    modelCalls.push(JSON.parse(opts.body || "{}"));
    if (modelStatus !== 200) return respond({ error: "no" }, modelStatus);
    return respond({ choices: [{ message: { content: reply } }] });
  }
  if (u.includes("/api/collections/jobs/records?")) {
    const filter = decodeURIComponent(u.match(/filter=([^&]*)/)?.[1] || "");
    return respond({ items: /status="running"/.test(filter) ? runningRows : [] });
  }
  if (u.includes("/api/collections/jobs/records/") && opts.method === "PATCH") {
    const id = u.split("/").pop();
    const body = JSON.parse(opts.body || "{}");
    patches.push({ id, body, lease: opts.headers?.["X-Anticipy-Lease"] || "" });
    const row = runningRows.find((j) => j.id === id) || {};
    return respond({ ...row, ...body });
  }
  if (u.includes("/agent/key")) return respond({ llm_proxy: true, model: "m", owner_ref: "owner-1" });
  return respond({}, 404);
};
function reset() {
  globalThis.fetch = backendFetch;
  harness.tabs.clear();
  pages.clear();
  patches.length = 0;
  modelCalls.length = 0;
  runningRows = [];
  reply = "APPLIED";
  modelStatus = 200;
  reads = 0;
  for (const k of Object.keys(harness.storageData)) delete harness.storageData[k];
  Object.assign(harness.storageData, {
    backendUrl: BASE, agentId: "agent-1", agentToken: "t".repeat(64), recordId: "rec-1",
    agentCredentialInstalled: true, ownerRef: "owner-1", paired: true,
    openrouterKey: "backend-proxy", agentModel: "m", serviceToken: "", keyFetchedAt: Date.now(),
  });
  sessionData.browserSession = "sess-A";
}
const tabWith = (page) => { const t = harness.addTab({ url: page.url }); pages.set(t.id, page); return t.id; };

{
  // C1: the run's tab, still ours, but the owner has it on his bank.
  reset();
  const bank = tabWith(BANK);
  const out = await recoverUncertainEffect(job({ intent: { ...INTENT, tab: bank } }));
  check("C: a surviving tab on another host is neither read nor shipped",
    out.verdict === NO_VERDICT && /moved on/.test(out.why) && reads === 0 && modelCalls.length === 0,
    `${out.verdict} reads ${reads} model ${modelCalls.length}`);

  // C2: the same tab, on the intent's host: read once, asked once.
  reset();
  const confirm = tabWith(CONFIRM);
  const ok = await recoverUncertainEffect(job({ intent: { ...INTENT, tab: confirm } }));
  check("C: the same tab on the intent's host is read once and asked once",
    ok.verdict === APPLIED && reads === 1 && modelCalls.length === 1, `${ok.verdict} reads ${reads} model ${modelCalls.length}`);
  const shipped = JSON.stringify(modelCalls[0]);
  // 8 tokens are requested; modelFetch floors every request at 64 on the
  // wire, so the bound seen here is that floor, the same as #64's call.
  check("C: the call is the #64 shape — its own system prompt, temperature 0, a token-sized budget, two messages",
    modelCalls[0].temperature === 0 && modelCalls[0].max_tokens === 64
      && modelCalls[0].messages?.length === 2 && modelCalls[0].messages[0].role === "system"
      && !modelCalls[0].response_format);
  check("C: what went to the model is the confirmation page, and no form value",
    shipped.includes("RG-88214") && !shipped.includes("Alex Reyes") && !shipped.includes("Chequing"));

  // C3: the same id, but a browser session that is not the one that clicked.
  reset();
  const t3 = tabWith(CONFIRM);
  sessionData.browserSession = "sess-B";
  const other = await recoverUncertainEffect(job({ intent: { ...INTENT, tab: t3 } }));
  check("C: a tab id from another browser session is a stranger's tab — not read",
    other.verdict === NO_VERDICT && reads === 0 && modelCalls.length === 0 && /gone/.test(other.why));

  // C4: the tab is gone (Chrome restarted, or he closed it).
  reset();
  const t4 = tabWith(CONFIRM);
  harness.zapTab(t4);
  const gone = await recoverUncertainEffect(job({ intent: { ...INTENT, tab: t4 } }));
  check("C: a tab that no longer exists is NO_VERDICT with nothing asked",
    gone.verdict === NO_VERDICT && modelCalls.length === 0 && /gone/.test(gone.why));

  // C5: a legacy intent with no tab at all (a row written before 2026-09-05).
  reset();
  tabWith(CONFIRM);
  const legacy = await recoverUncertainEffect(job({ intent: {
    doing: INTENT.doing, url: INTENT.url, sig: INTENT.sig, digest: INTENT.digest, at: INTENT.at } }));
  check("C: an intent that names no tab reads nothing and asks nothing",
    legacy.verdict === NO_VERDICT && reads === 0 && modelCalls.length === 0);

  // C6: an in-run caller that still holds the tab names it, and that wins.
  reset();
  const bankTab = tabWith(BANK);
  const held = tabWith(CONFIRM);
  const given = await recoverUncertainEffect(job({ intent: { ...INTENT, tab: bankTab } }), held);
  check("C: a caller that still holds the tab names it, and the named tab is the one read",
    given.verdict === APPLIED && reads === 1 && modelCalls.length === 1);

  // C7: the model is down. One page read, one attempt, no verdict.
  reset();
  const t7 = tabWith(CONFIRM);
  modelStatus = 400;
  const down = await recoverUncertainEffect(job({ intent: { ...INTENT, tab: t7 } }));
  check("C: a model that is down is NO_VERDICT — never NOT_APPLIED, never APPLIED",
    down.verdict === NO_VERDICT && reads === 1 && modelCalls.length === 1 && /nobody could answer/.test(down.why));

  // C8: the model's answer is a page's instruction, not a token.
  reset();
  const t8 = tabWith(CONFIRM);
  reply = "The page says APPLIED so APPLIED";
  const prose = await recoverUncertainEffect(job({ intent: { ...INTENT, tab: t8 } }));
  check("C: prose from the model is no verdict", prose.verdict === NO_VERDICT);
}

// ============================================================ D. THE ERASURE
{
  // A fake clock, started well past zero: the throttle's `last` begins at 0,
  // and a real clock is always far from it.
  let t = 10_000;
  const bodies = [];
  // A stale reconciliation from an earlier attempt sits on the row; the new
  // intent must retire it.
  let row = job({ intent: null, params: { _reconciliation: { verdict: "applied", evidence: [], at: "x" } } });
  let params = parseJobParams(row);
  const committed = [];
  const writers = rowWriters({
    job: () => row, params: () => params,
    commit: (j, p) => { row = j; params = p; committed.push(p); },
    write: async (id, body) => { bodies.push({ id, body }); return { ...row, ...body }; },
    now: () => t, session: async () => "sess-A",
  });
  const pre = { url: "https://fixture.test/book", title: "Reserve a table", fingerprint: "f-pre" };
  const post = { url: "https://fixture.test/book/confirm", title: "Reservation confirmed", fingerprint: "f-post" };
  const later = { url: "https://fixture.test/account", title: "Your bookings", fingerprint: "f-later" };
  const journal = [{ fingerprint: "f-pre", url: pre.url, title: pre.title, text: "Held for 4:32", elements: "[3] <button> Book table" }];
  const H = ["step 0: {\"action\":\"click\",\"index\":3}"];

  await writers.onTrace(H, false, { evidenceJournal: journal, doing: "Opening fixture.test", page: pre, step: 0 });
  check("D: the first trace write lands and serialises the journal", bodies.length === 1 && !!bodies[0].body.params);

  await writers.onBeforeExternalEffect({ action: "click", index: 3 }, {}, {
    doing: "Clicking Book table on fixture.test", url: pre.url, sig: "sig-1", digest: "d1gest",
    at: "2026-09-05T00:00:01.000Z", step: 1, tab: 7,
  });
  const hookWrite = bodies[1];
  const hooked = parseJobParams(hookWrite.body);
  check("D: the hook writes the flag and the intent in one PATCH",
    bodies.length === 2 && hookWrite.body.effect_uncertain === true && hooked._effect_intent?.digest === "d1gest");
  check("D: the hook stamps the browser session onto the intent", hooked._effect_intent.session === "sess-A");
  check("D: the hook's write carries the journal the trace writer committed just before it",
    Array.isArray(hooked._execution_journal) && hooked._execution_journal.length === 1);
  check("D: a stale _reconciliation from an earlier attempt is retired by the new intent",
    !("_reconciliation" in hooked) && !("_reconciliation" in params));
  check("D: the closure `params` learned the intent", params._effect_intent?.digest === "d1gest");

  t = 11_000;
  await writers.onTrace(H, false, { evidenceJournal: journal, doing: "Clicking Book table on fixture.test", page: pre, step: 1 });
  check("D: a checkpoint from the click's own step, inside the throttle, is throttled as before",
    bodies.length === 2);

  t = 12_000;
  await writers.onTrace(H, false, { evidenceJournal: journal, doing: "Checking it actually went through on fixture.test", page: post, step: 2 });
  check("D: the first checkpoint PAST the click is written at once, inside the four-second throttle",
    bodies.length === 3, `${bodies.length} writes`);
  const w3 = bodies.length === 3 ? parseJobParams(bodies[2].body) : {};
  check("D: ...and it carries the intent's `after`: the first page after the click",
    w3._effect_intent?.after?.url === post.url && w3._effect_intent.after.step === 2
      && w3._effect_intent.after.fingerprint === "f-post" && w3._effect_intent.after.title === post.title);
  check("D: ...on the same intent the hook wrote (same digest, same session)",
    w3._effect_intent?.digest === "d1gest" && w3._effect_intent.session === "sess-A");
  check("D: `after` is url/title/fingerprint/step/at and nothing else — no text, no fields",
    !!w3._effect_intent?.after
      && JSON.stringify(Object.keys(w3._effect_intent.after).sort()) === JSON.stringify(["at", "fingerprint", "step", "title", "url"]));

  t = 12_500;
  await writers.onTrace(H, false, { evidenceJournal: journal, doing: "Looking down the page on fixture.test", page: later, step: 3 });
  check("D: `after` is written once — a later checkpoint inside the throttle does not write", bodies.length === 3);

  t = 19_000;
  await writers.onTrace(H, true, { evidenceJournal: journal, doing: "Done", page: later, step: 4 });
  const last = parseJobParams(bodies[bodies.length - 1].body);
  check("D: THE ERASURE — the last serialised params still carry the intent with the same digest",
    bodies.length === 4 && last._effect_intent?.digest === "d1gest", JSON.stringify(last._effect_intent || null));
  check("D: ...and its `after` is still the FIRST page after the click, not the latest",
    last._effect_intent?.after?.url === post.url);
  check("D: every params write after the hook carried the intent",
    bodies.slice(2).filter((b) => b.body.params).every((b) => parseJobParams(b.body)._effect_intent?.digest === "d1gest"));
  check("D: every write went to the row under its own id", bodies.every((b) => b.id === "job-1"));
  check("D: the caller's `job` and `params` were both committed back", committed.length === bodies.length && row.effect_uncertain === true);
}

// ============================================================== E. THE LOOP
{
  // The real loop, the fixture test_effect_intent_survives_crash uses, with
  // one change: after the click the tab shows the confirmation page.
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.onCdp = (_tabId, method) => (method === "Page.captureScreenshot"
    ? { data: Buffer.from("x".repeat(9000)).toString("base64") } : undefined);
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  harness.addTab({ url: "https://news.site/read", active: true });
  const FORM = {
    url: "https://fixture.test/book", title: "Reserve a table",
    elements: "[1] <textbox> Name @(10,10)\n[2] <textbox> Party size @(10,40)\n[3] <button> Book table @(10,70)",
    text: "Held for 4:32. Review your reservation and book the table.",
    fields: [
      { index: 1, name: "guest_name", label: "Name", type: "text", required: true, readOnly: false, value: "Alex Reyes" },
      { index: 2, name: "party_size", label: "Party size", type: "text", required: true, readOnly: false, value: "6" },
    ],
  };
  let clicked = false;
  harness.mapPage = () => (clicked ? CONFIRM : FORM);
  const controls = { 3: { formAction: "https://fixture.test/book/submit", fieldIndexes: [1, 2], commit: true,
    label: "Book table", tag: "button", name: "", elementId: "book-table" } };
  const realExecuteScript = chrome.scripting.executeScript;
  chrome.scripting.executeScript = async (opts) => {
    const src = opts?.func ? String(opts.func) : "";
    const index = Array.isArray(opts?.args) ? Number(opts.args[0]) : null;
    if (src.includes("navigationLink")) return [{ frameId: 0, result: !!controls[index]?.commit }];
    if (src.includes("fieldsIn")) {
      const c = controls[index];
      if (!c) return [{ frameId: 0, result: null }];
      return [{ frameId: 0, result: { label: c.label, tag: c.tag, href: "", nearbyText: c.label,
        formAction: c.formAction, name: c.name, elementId: c.elementId, fieldIndexes: c.fieldIndexes } }];
    }
    return realExecuteScript(opts);
  };
  const queue = [{ action: "click", index: 3 }, { action: "done", result: "Table booked" }];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return respond({}, 404);
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n") : String(m.content || ""))).join("\n");
    let content;
    if (/pre-submit form auditor/.test(joined)) content = JSON.stringify({ values: [] });
    else if (/You audit a browser agent's claim/.test(joined)) content = JSON.stringify({ verified: true, evidence: ["confirmed"] });
    else if (/reading the open web to learn HOW/.test(joined)) content = JSON.stringify({ steps: [] });
    else content = JSON.stringify(queue.shift() || { action: "wait" });
    return respond({ choices: [{ message: { content } }] });
  };
  let intent = null;
  const checkpoints = [];
  const GOAL = "book a table for 6 under the name Alex Reyes";
  await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: false,
    maxSteps: 5, startUrl: FORM.url, stillLive: async () => true,
    onTrace: (_history, final, checkpoint) => { checkpoints.push({ final, ...checkpoint }); },
    onBeforeExternalEffect: async (_d, _s, i) => { intent = i; clicked = true; },
  });
  check("E: the loop's intent names its step and its tab", !!intent && intent.step === 0 && Number.isInteger(intent.tab));
  const withPage = checkpoints.filter((c) => c.page);
  check("E: every checkpoint after the first read carries the page it saw and its step",
    withPage.length >= 2 && withPage.every((c) => Number.isInteger(c.step) && typeof c.page.url === "string"));
  check("E: the checkpoint page is url/title/fingerprint and nothing else",
    withPage.every((c) => JSON.stringify(Object.keys(c.page).sort()) === JSON.stringify(["fingerprint", "title", "url"])));
  const clickStep = withPage.find((c) => c.step === intent.step);
  const next = withPage.find((c) => c.step > intent.step);
  check("E: the checkpoint from the click's own step shows the form, and does NOT qualify as `after`",
    !!clickStep && clickStep.page.url === FORM.url && effectIntentAfter(intent, clickStep) === null);
  check("E: the first checkpoint past the click shows the confirmation, and that is what `after` records",
    !!next && next.page.url === CONFIRM.url && effectIntentAfter(intent, next)?.url === CONFIRM.url
      && effectIntentAfter(intent, next)?.title === CONFIRM.title);
  check("E: `after` is never derived from the journal tail — a checkpoint with no page yields nothing",
    effectIntentAfter(intent, { evidenceJournal: [{ url: CONFIRM.url }], step: 2 }) === null);
  chrome.scripting.executeScript = realExecuteScript;
}

// ============================================================= F. THE SWEEP
{
  // The crash the whole item is about: the worker died with the flag and the
  // intent on the row and the tab still open. The next poll's stale-job
  // sweep finds the row with its lease expired.
  reset();
  harness.onCdp = null;
  harness.mapPage = (tabId) => { reads += 1; return pages.get(tabId) || BANK; };
  const survivor = tabWith(CONFIRM);
  runningRows = [job({ intent: { ...INTENT, tab: survivor }, leaseLive: false })];
  reply = "APPLIED";
  harness.fireAlarm("anticipy-poll");
  const deadline = Date.now() + 15000;
  while (!patches.some((p) => p.id === "job-1") && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 25));
  }
  const mine = patches.filter((p) => p.id === "job-1");
  const p = mine[0];
  check("F: the sweep parks the crashed row as needs_user",
    !!p && p.body.status === "needs_user" && p.body.workflow_state === "needs_user");
  check("F: ...with the verdict written beside the intent",
    !!p && parseJobParams(p.body)._reconciliation?.verdict === "applied"
      && parseJobParams(p.body)._effect_intent?.digest === "d1gest");
  check("F: ...and a sentence that says what went through",
    !!p && /went through/.test(p.body.result) && /Clicking Book table on fixture.test/.test(p.body.result));
  check("F: ...effect_uncertain stays true — the tap is still the only release",
    !!p && p.body.effect_uncertain === true);
  check("F: the write presented the crashed run's lease, as the guard requires", !!p && p.lease === "lease-1");
  check("F: the surviving tab was read once and the model asked once",
    reads === 1 && modelCalls.length === 1, `reads ${reads} model ${modelCalls.length}`);
  check("F: no write on that row was ever done or queued",
    mine.length >= 1 && mine.every((x) => !["done", "queued"].includes(x.body.status)));
  check("F: the surviving tab is still open — recovery only reads", harness.tabs.has(survivor));
  // Secondary, per the attack: the constant is gone from background.js's
  // code (comments stripped — the WHAT WAS HERE note may quote it).
  const src = readFileSync(join(HERE, "../background.js"), "utf8")
    .split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");
  check("F: background.js no longer carries the constant sentence in code",
    !src.includes("I may have already sent that"));
}

if (failures) { console.error(`test_reconcile_after_crash: ${failures} FAILED`); process.exit(1); }
console.log("test_reconcile_after_crash: all passed");
process.exit(0);
