// RUNG 0's GATE, driven as real code rather than read as text.
//
// WHAT THIS PINS. `research/2026-08-26-hands2-better-answer.md` §4 names the one
// hand that beats both the browser and the API ladder for one verb: the phone
// picks a calendar job off the poll it already runs and `EKEventStore` executes
// it. The same section names the risk in the same breath — *"a device execution
// lane that does not route through the same gate is not a new hand, it is a hole
// in the gate"*. So every check below is about the hole, not about the hand.
//
// FOUR THINGS ARE ASSERTED, and the last two are the ones that matter.
//
//   1. ROUTING, both directions. A browser never SEES a device-lane job (the
//      server rewrites its poll) and never claims one (403). An owner session
//      never claims a browser-lane job. Same two-layer shape as the research
//      lane, for the same recorded reason: client code cannot be recalled.
//
//   2. THE POLL REWRITE HAS EXACTLY ONE OWNER. Two hooks appending lane
//      clauses to the same filter is not additive, it is subtractive: the first
//      to run makes the filter "mention lane", and every later hook's
//      `!MENTIONS_LANE` test then skips — silently dropping the research and
//      supervised exclusions that have been load-bearing since 2026-08-02. That
//      is a static property of the directory and it is asserted as one.
//
//   3. THE DEVICE LANE MAY NOT RIDE THE `read_only` EXEMPTION. This is the
//      finding, and it is not hypothetical:
//
//        brain/anticipy_core.py is_consequential("put dinner with Sara Thursday
//        7pm on my calendar", explicit=True) -> False
//
//      ...because "put" is not in `_VERBS`, and `explicit` short-circuits above
//      the read-only fallback. `_queue_job` then mints `Consequence.READ_ONLY`
//      (anticipy_core.py:3549), and `NO_APPROVAL_NEEDED = ["read_only"]` in
//      workflow_guard.pb.js waves that row into `queued` and `running` with NO
//      approval at all. Say "schedule dinner Thursday 7pm" instead and the same
//      act is held, because `schedul\w*` IS in the list. The wording decides.
//
//      workflow_guard's own comment says what `read_only`'s exemption rests on:
//      it is EARNED by `extension/background.js runSupervisedReadJob` failing
//      any job whose consequence !== "read_only", "and nothing in that lane acts
//      on the world". A device lane exists precisely TO act on the world. It
//      would inherit the exemption and none of the backstop.
//
//   4. AND THE GATE IS NOT DUPLICATED. The hook contains no approval check of
//      its own — asserted mechanically over its source, because "I did not
//      write a second one" is exactly the claim a reviewer cannot verify by
//      reading. What it does instead is force the row into the lane where
//      workflow_guard's existing, unchanged approval leg applies, and the last
//      block below drives workflow_guard itself to prove that leg still fires.
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const hooks = join(here, "..", "..", "backend", "pb_hooks");
const laneSrc = readFileSync(join(hooks, "research_lane.pb.js"), "utf8");
const guardSrc = readFileSync(join(hooks, "workflow_guard.pb.js"), "utf8");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const SERVICE_TOKEN = "service-token-for-the-worker";
const AGENT_TOKEN = "a".repeat(48);
const OWNER = "owner_abc1234567";
const DEVICE_LANE = "device_calendar";

const record = (id, fields) => ({
  id,
  get: (f) => fields[f],
  getString: (f) => String(fields[f] ?? ""),
  getBool: (f) => fields[f] === true,
});

const load = (src, extraGlobals = {}) => {
  let handler = null;
  const globals = {
    routerUse: (fn) => { handler = fn; },
    $os: { getenv: (k) => (k === "ANTICIPY_SERVICE_TOKEN" ? SERVICE_TOKEN : "") },
    console,
    ...extraGlobals,
  };
  const names = Object.keys(globals);
  new Function(...names, src)(...names.map((n) => globals[n]));
  return handler;
};

// One request through a real hook. "next" means allowed through to PocketBase,
// {status, error} means refused, and `filter` is the query as the hook left it.
function drive(handler, { method, path, query = "", headers = {}, body = {},
                          auth = null, superuser = false, rows = {},
                          lineage = null }) {
  const params = new URLSearchParams(query);
  let outcome = null;
  const url = {
    path,
    rawQuery: query,
    query: () => ({
      get: (k) => (params.has(k) ? params.get(k) : null),
      set: (k, v) => params.set(k, v),
      encode: () => params.toString(),
    }),
  };
  const e = {
    auth,
    // "throw" stands for a runtime that will not answer the question. It is not
    // hypothetical: this hook runs in an isolated JSVM context where the event
    // surface has already differed from the types file twice (see the header of
    // test_hook_scope_trap.mjs), and a check whose failure mode is "assume
    // superuser" would switch the whole gate off exactly when the ground moved.
    hasSuperuserAuth: () => {
      if (superuser === "throw") throw new Error("no such method");
      return superuser;
    },
    request: { method, url, header: { get: (k) => headers[k] || "" } },
    requestInfo: () => ({ body }),
    next: () => { outcome = "next"; },
    json: (status, payload) => {
      outcome = { status, error: payload.error, detail: payload.detail };
    },
    app: {
      findRecordById: (collection, id) => {
        const rec = rows[`${collection}/${id}`];
        if (!rec) throw new Error("not found");
        return rec;
      },
      findRecordsByFilter: () => (lineage === null ? [] : lineage),
    },
  };
  handler(e);
  return { outcome, filter: url.rawQuery };
}

const lane = load(laneSrc);
check("the lane hook registers a router middleware", typeof lane === "function");

// `URLSearchParams.toString()` writes spaces as `+`, so a rewritten filter has
// to be decoded the way a query string is decoded before it reads as a filter.
const asFilter = (raw) => decodeURIComponent(String(raw).replace(/\+/g, "%20"));

// ------------------------------------------------------------------ routing
// Layer 1. An extension in the wild polls `status="queued"` and names no lane.
// It must never even SEE a device errand: it has no EventKit, so it would burn
// the job's attempts trying to do a calendar write in a browser tab.
const blindPoll = drive(lane, {
  method: "GET", path: "/api/collections/jobs/records",
  query: "filter=" + encodeURIComponent('status="queued" && (owner="abc" || owner="")'),
});
check("a lane-blind poll is rewritten to hide the device lane",
  /lane != "device_calendar"/.test(asFilter(blindPoll.filter)));
check("...and still hides the two lanes it already hid",
  /lane != "research"/.test(asFilter(blindPoll.filter)) &&
  /lane != "supervised_read"/.test(asFilter(blindPoll.filter)));

const phonePoll = drive(lane, {
  method: "GET", path: "/api/collections/jobs/records",
  query: "filter=" + encodeURIComponent(
    `status="queued" && owner_ref="${OWNER}" && lane="${DEVICE_LANE}"`),
});
check("a poll that names the device lane is left alone, so the phone finds its work",
  !/lane !=/.test(asFilter(phonePoll.filter)));

// THE DOUBLE-APPEND HAZARD, asserted over the directory rather than argued
// about. A second hook that appends a lane clause to this same filter would
// make the FIRST one's exclusions unreachable, because `MENTIONS_LANE` is then
// true for everybody downstream.
const rewriters = readdirSync(hooks)
  .filter((f) => f.endsWith(".pb.js"))
  .filter((f) => {
    const s = readFileSync(join(hooks, f), "utf8");
    return /rawQuery\s*=/.test(s) && /lane/.test(s);
  });
check("exactly one hook rewrites the jobs claim filter",
  rewriters.length === 1 && rewriters[0] === "research_lane.pb.js");

// Layer 2. The claim write itself.
const CLAIM = { method: "PATCH", path: "/api/collections/jobs/records/job1" };
const claimBody = { claimed_by: "phone-abc", status: "running" };
const ownerAuth = { id: OWNER };
const agentHeaders = {
  "X-Anticipy-Agent-ID": "ag1", "X-Anticipy-Agent-Token": AGENT_TOKEN,
};

// A device job that is well formed in every way this hook cares about: it
// carries a workflow (so workflow_guard runs at all) and it is consequential
// (so workflow_guard's approval leg applies to it).
const deviceJob = (fields = {}) => ({
  "jobs/job1": record("job1", {
    lane: DEVICE_LANE, owner_ref: OWNER, workflow_id: "wf1",
    consequence: "consequential", status: "queued", ...fields,
  }),
});
const claim = (opts) => drive(lane, { ...CLAIM, body: claimBody, ...opts }).outcome;

check("the phone may claim a well-formed device errand",
  claim({ rows: deviceJob(), auth: ownerAuth }) === "next");

check("a browser may NOT claim a device errand",
  claim({ rows: deviceJob(), headers: agentHeaders })?.status === 403);

check("the refusal tells the browser where that errand belongs",
  /phone/i.test(claim({ rows: deviceJob(), headers: agentHeaders })?.error || ""));

check("a caller with no session at all may not claim a device errand",
  claim({ rows: deviceJob() })?.status === 403);

// The mirror. An owner session is the phone; the phone has no browser.
check("the phone may NOT claim a browser-lane errand",
  claim({ rows: { "jobs/job1": record("job1", { lane: "", owner_ref: OWNER,
                                                workflow_id: "wf1" }) },
          auth: ownerAuth })?.status === 403);

check("a browser still claims its own lane, untouched",
  claim({ rows: { "jobs/job1": record("job1", { lane: "", owner_ref: OWNER,
                                                workflow_id: "wf1" }) },
          headers: agentHeaders }) === "next");

// THE REGRESSION THIS MOST LIKELY CAUSES, so it is pinned. Approving and
// cancelling are the phone's whole job on a browser-lane errand and neither is
// a claim: `status: "queued"` and `status: "cancelled"` carry no `claimed_by`.
const browserRow = { "jobs/job1": record("job1", { lane: "", owner_ref: OWNER,
                                                   workflow_id: "wf1" }) };
check("the phone may still APPROVE a browser errand",
  drive(lane, { ...CLAIM, rows: browserRow, auth: ownerAuth,
                body: { status: "queued", approval: "{}" } }).outcome === "next");
check("the phone may still CANCEL a browser errand",
  drive(lane, { ...CLAIM, rows: browserRow, auth: ownerAuth,
                body: { status: "cancelled" } }).outcome === "next");

// A flag in the body is not evidence of anything (side_trip.js:194-198, and the
// supervised lane's whole design). None of these make a browser into a phone.
check("naming yourself the worker does not make you a phone",
  claim({ rows: deviceJob(), headers: agentHeaders,
          body: { ...claimBody, claimed_by: "worker-research" } })?.status === 403);
check("a body flag does not make a browser into a phone",
  claim({ rows: deviceJob(), headers: agentHeaders,
          body: { ...claimBody, device: true, on_device: true } })?.status === 403);
check("a body-supplied lane does not move the job off the device lane",
  claim({ rows: deviceJob(), headers: agentHeaders,
          body: { ...claimBody, lane: "" } })?.status === 403);

// Normalised once, like the two lanes beside it, or casing walks past both legs.
check("a mixed-case device lane is still a device lane",
  claim({ rows: deviceJob({ lane: "Device_Calendar" }),
          headers: agentHeaders })?.status === 403);
check("a padded device lane is still a device lane",
  claim({ rows: deviceJob({ lane: "  device_calendar  " }),
          headers: agentHeaders })?.status === 403);

// The worker queued the job and is the only thing that sweeps it when the phone
// never wakes up, so it stays exempt — on the authenticated marker, never the
// bare one (brain/pb.py:21-22).
check("the authenticated worker may still sweep a device errand",
  claim({ rows: deviceJob(),
          headers: { "X-Anticipy-Worker": "1", "X-Anticipy-Token": SERVICE_TOKEN } })
    === "next");
check("the bare marker is not the worker",
  claim({ rows: deviceJob(), headers: { "X-Anticipy-Worker": "1" } })?.status === 403);

// ------------------------------------------------- the exemption, and the hole
// A device errand stamped `read_only` is the failure this whole file exists for.
// It is not a made-up input: it is what `is_consequential` returns today for
// "put dinner with Sara Thursday 7pm on my calendar" said out loud.
const shape = (fields, opts = {}) => drive(lane, {
  ...CLAIM, auth: ownerAuth, body: claimBody, rows: deviceJob(fields), ...opts,
}).outcome;

check("a device errand may not ride the read_only exemption",
  shape({ consequence: "read_only" })?.status === 403);
check("...and the refusal says the backstop is what is missing",
  /backstop|read_only|acts on the world/i.test(
    shape({ consequence: "read_only" })?.detail
    || shape({ consequence: "read_only" })?.error || ""));

// `reversible_local` is Shelf 2's act-and-tell. Its admitted set is
// `SHELF2_ACT_TYPES = ["local_draft"]` — a calendar write is not a member, and
// `EKEvent.eventIdentifier` is assigned by EventKit ON SAVE, which is the shape
// §6.1 excludes by name. Refused here so the row cannot reach the shelf leg and
// be refused there with a message nobody reads.
check("a device errand may not claim Shelf 2 either",
  shape({ consequence: "reversible_local" })?.status === 403);

check("an unrecognised consequence is refused, never defaulted",
  shape({ consequence: "" })?.status === 403 &&
  shape({ consequence: "constructor" })?.status === 403 &&
  shape({ consequence: "consequentia" })?.status === 403);

// workflow_guard.pb.js:24 — `if (!workflow) return e.next();`. A device errand
// with no workflow_id skips the ENTIRE confirmation gate, silently. The browser
// lane closes this client-side (`workflow_id!=""` in background.js BROWSER_LANE);
// the device lane closes it on the server, where it cannot be un-shipped.
check("a device errand with no workflow is refused, because the gate would skip it",
  shape({ workflow_id: "" })?.status === 403);

check("a well-formed device errand passes the shape legs",
  shape({}) === "next");

// THE MOVE THE SUPERVISED LEASE ALREADY REFUSES, pointed at this lane: a
// claimant re-declaring what the job IS in the same breath as claiming it. The
// phone is the legitimate claimant here, which is exactly why it is the one
// worth testing — it is the only caller the routing legs let this far.
check("the phone may not re-declare a read_only errand as consequential",
  shape({ consequence: "read_only" },
        { body: { ...claimBody, consequence: "consequential" } })?.status === 403);
check("...nor mint itself a workflow the row does not have",
  shape({ workflow_id: "" },
        { body: { ...claimBody, workflow_id: "wf1" } })?.status === 403);
// And the mirror: the write itself must not be the thing that spoils the row.
check("a write may not un-say a good errand's consequence on the way live",
  shape({}, { body: { ...claimBody, consequence: "read_only" } })?.status === 403);

// SHAPE BINDS THE WORKER TOO. It is a question about the row, not about who is
// writing it — and the worker is the half that MINTS the row, so exempting it
// would exempt the only thing that can get this wrong.
const asWorker = { "X-Anticipy-Worker": "1", "X-Anticipy-Token": SERVICE_TOKEN };
check("the worker may not put a read_only calendar errand live",
  drive(lane, { ...CLAIM, headers: asWorker, body: claimBody,
                rows: deviceJob({ consequence: "read_only" }) }).outcome?.status === 403);
check("the worker may not put a workflow-less calendar errand live",
  drive(lane, { ...CLAIM, headers: asWorker, body: claimBody,
                rows: deviceJob({ workflow_id: "" }) }).outcome?.status === 403);

// The superuser is neither hand. The dashboard has to stay able to touch a row
// or an operator cannot repair one, which is the same call guard.pb.js:395
// makes one file over.
// The superuser is neither hand. The dashboard has to stay able to touch a row
// or an operator cannot repair one, which is the same call guard.pb.js:395
// makes one file over. Tested on the BROWSER lane as well as the device lane,
// because a superuser holds an account session and would otherwise be caught by
// the phone-may-not-claim-a-browser-errand leg — the device-lane case alone
// cannot tell the exemption from its own absence.
check("a superuser is not mistaken for either hand",
  claim({ rows: deviceJob(), auth: { id: "su1" }, superuser: true }) === "next");
check("...on the browser lane too, or the dashboard cannot repair a row",
  claim({ rows: { "jobs/job1": record("job1", { lane: "", owner_ref: OWNER,
                                                workflow_id: "wf1" }) },
          auth: { id: "su1" }, superuser: true }) === "next");

// AND IT FAILS CLOSED. If the runtime will not say whether this is a superuser,
// the answer is "no". Reading a thrown call as "yes" would hand every caller the
// exemption — one unanswered question and both routing legs stop existing.
check("a runtime that cannot answer does not mint a superuser",
  claim({ rows: deviceJob(), headers: agentHeaders,
          superuser: "throw" })?.status === 403);

// AND IT MUST NOT LOCK THE ROW. workflow_guard's own comment warns that a
// refusal on a live write "blocks even the write that would park or fail it, so
// the row would hang until its lease expired". A malformed device row must stay
// failable.
check("a malformed device errand can still be failed",
  drive(lane, { ...CLAIM, auth: ownerAuth, rows: deviceJob({ consequence: "read_only" }),
                body: { status: "failed" } }).outcome === "next");
check("a malformed device errand can still be cancelled",
  drive(lane, { ...CLAIM, auth: ownerAuth, rows: deviceJob({ consequence: "read_only" }),
                body: { status: "cancelled" } }).outcome === "next");

// ------------------------------------------------ the gate is NOT duplicated
// "I did not write a second approval check" is the one claim a reviewer cannot
// confirm by reading, so it is measured. The lane hook decides ROUTING and
// SHAPE. Whether the owner approved is workflow_guard's question and it is
// asked in exactly one place.
const vocabulary = ["approval", "scope_digest", "plan_version", "owner_words",
                    "gesture", "lease_token", "receipt"];
// MEASURED AS FIELD ACCESS, not as the bare word, and that is the sharper test
// rather than the looser one. The hook's refusal messages have to NAME the gate
// to be worth reading — "read_only carries an approval exemption that is earned
// by a backstop this lane does not have" is the whole point of the 403 — and a
// word-anywhere check would have forced that sentence to be worse in order to
// go green, which is a test editing the product to suit itself.
//
// What a second gate cannot avoid is READING the field. Every read in this tree
// takes one of three shapes, so all three are refused. (A whole-file word check
// would need string literals blanked, and that needs the real lexer
// test_hook_scope_trap.mjs had to write, because `/…"queued"/` is a regex
// literal with a quote in it.)
const codeOnly = laneSrc
  .replace(/\/\*[\s\S]*?\*\//g, " ")
  .split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
for (const word of vocabulary) {
  const reads = [`.${word}`, `["${word}"]`, `("${word}")`];
  check(`the lane hook never reads \`${word}\` — that is the gate's question`,
    reads.every((form) => codeOnly.indexOf(form) < 0));
}

// ...and the gate it defers to still fires. Driven, because "it routes through
// the same gate" is worth exactly as much as a run that proves it.
const guard = load(guardSrc);
const plan = (over = {}) => ({
  plan_id: "wf1", version: 1, state: "queued", goal: "put dinner Thursday 7pm",
  consequence: "consequential", lineage_key: "lin1", owner_ref: OWNER,
  scope_digest: "digest1", effect_key: "eff1", attempts: 0, ...over,
});
const guardBody = (over = {}, planOver = {}) => ({
  status: "queued", workflow_state: "queued", workflow_id: "wf1",
  workflow_version: 1, lineage_key: "lin1", owner_ref: OWNER,
  goal: "put dinner Thursday 7pm", scope_digest: "digest1", effect_key: "eff1",
  consequence: "consequential", attempts: 0,
  params: JSON.stringify({ _workflow: plan(planOver) }), ...over,
});
const guardRow = { "jobs/job1": record("job1", {
  lane: DEVICE_LANE, owner_ref: OWNER, status: "awaiting_confirm",
  workflow_id: "wf1", workflow_version: 1, workflow_state: "awaiting_approval",
  lineage_key: "lin1", goal: "put dinner Thursday 7pm", scope_digest: "digest1",
  effect_key: "eff1", consequence: "consequential", attempts: 0,
}) };
const throughGuard = (over, planOver) => drive(guard, {
  ...CLAIM, auth: ownerAuth, rows: guardRow, body: guardBody(over, planOver),
}).outcome;

check("workflow_guard still holds an unapproved device errand at the gate",
  throughGuard()?.status === 409);
check("...and holds it for the reason the gate exists",
  /approval/i.test(throughGuard()?.detail || ""));

const approval = {
  plan_id: "wf1", plan_version: 1, scope_digest: "digest1",
  gesture: { kind: "tap", actor: OWNER, plan_id: "wf1", plan_version: 1,
             scope_digest: "digest1" },
};
check("...and lets the same errand through once he has actually tapped",
  throughGuard({ approval: JSON.stringify(approval) },
               { approval: approval }) === "next");

console.log(failures ? `\n${failures} FAILED` : "\nall device-lane checks passed");
process.exit(failures ? 1 : 0);
