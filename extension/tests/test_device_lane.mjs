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
// carries a workflow (so workflow_guard runs at all), it is consequential (so
// workflow_guard's approval leg applies to it), and it DECLARES A CALENDAR ACT.
//
// The act was not here when this file was written, and its absence is what let
// the lane be calendar-only by client convention: any approved errand — a send,
// a payment — satisfied every server-side device-lane leg. `deviceParams` is
// spelled out rather than inlined because half the checks below vary it.
const CAL_ACT = {
  act_type: "calendar_write", reach: "device_calendar_store",
  executor: "anticipy_phone",
};
const deviceParams = (act = CAL_ACT) => JSON.stringify({
  _workflow: {
    plan_id: "wf1", version: 1, state: "queued",
    consequence: "consequential", act,
  },
});
const deviceJob = (fields = {}) => ({
  "jobs/job1": record("job1", {
    lane: DEVICE_LANE, owner_ref: OWNER, workflow_id: "wf1",
    consequence: "consequential", status: "queued",
    params: deviceParams(), approval: "", ...fields,
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

// --------------------------------------- the live write that is not a claim
// A SURVIVING MUTANT ON THE MOST IMPORTANT TRANSITION THIS LANE HAS, and the
// reason it survived is that every shape check above drives `claimBody`, which
// carries `claimed_by` and `status:"running"`. So no check exercised a live
// write that is NOT a claim — and the non-claiming write into `queued` is the
// phone's APPROVAL write, the moment a device errand becomes runnable.
//
// `const LIVE = ["queued", "running"]` -> `["running"]` switched the shape legs
// off for exactly that write and the whole suite stayed green. These four kill
// it: each is a `queued` write with no `claimed_by` anywhere in it.
const release = (fields, body = { status: "queued" }) => drive(lane, {
  ...CLAIM, auth: ownerAuth, body, rows: deviceJob({ status: "awaiting_confirm", ...fields }),
}).outcome;

check("releasing a read_only device errand into queued is refused",
  release({ consequence: "read_only" })?.status === 403);
check("releasing a workflow-less device errand into queued is refused",
  release({ workflow_id: "" })?.status === 403);
check("releasing one whose act is not a calendar act is refused",
  release({ params: deviceParams({ ...CAL_ACT, act_type: "send_message" }) })?.status === 403);
check("...and a well-formed one is still released",
  release({}) === "next");

// AND THE WORKER'S OWN RELEASE, because the worker is the half that mints the
// row and `queued` is where it puts it.
check("the worker may not release a malformed device errand either",
  drive(lane, { ...CLAIM, headers: asWorker, body: { status: "queued" },
                rows: deviceJob({ status: "awaiting_confirm",
                                  consequence: "read_only" }) }).outcome?.status === 403);

// ------------------------------------------------------- what the errand IS
// THE LANE WAS CALENDAR-ONLY BY CLIENT CONVENTION AND BY NOTHING THE SERVER
// CHECKED. The shape was two questions — has a workflow, is consequential — and
// neither looked at what the act IS. `workflow_guard.pb.js:598` reads
// `embedded.act` only inside `if (live && consequence === SHELF2)`, and this
// lane forbids `reversible_local`, so a device row's act declaration was
// inspected by no hook anywhere. Any approved errand — a send, a payment —
// satisfied every server-side device-lane leg, which is the general device
// execution lane the research declines by name.
const withAct = (act) => shape({ params: deviceParams(act) });
const actType = (t) => withAct({ ...CAL_ACT, act_type: t });

check("a calendar write is admitted", actType("calendar_write") === "next");
check("a calendar undo is admitted, because moment 11 asks for one",
  actType("calendar_undo") === "next");
check("a send is NOT a calendar act, however approved it is",
  actType("send_message")?.status === 403);
check("...and neither is Shelf 2's local_draft",
  actType("local_draft")?.status === 403);
check("the refusal names the act it turned away",
  /send_message/.test(actType("send_message")?.detail || ""));

// Floor polarity, and the object-as-set hazard this file's hook argues about
// three times: `{calendar_write: 1}["constructor"]` is truthy.
check("an undeclared act is refused, never defaulted",
  actType("")?.status === 403 &&
  shape({ params: JSON.stringify({ _workflow: { plan_id: "wf1" } }) })?.status === 403 &&
  shape({ params: "" })?.status === 403 &&
  shape({ params: "{not json" })?.status === 403);
check("an inherited property name is not an act type",
  actType("constructor")?.status === 403 &&
  actType("toString")?.status === 403 &&
  actType("hasOwnProperty")?.status === 403);
check("an act that is not an object is not an act",
  withAct("calendar_write")?.status === 403 &&
  withAct(null)?.status === 403 &&
  withAct(["calendar_write"])?.status === 403);
const blankAct = shape({ params: JSON.stringify({ _workflow: { act: { act_type: "   " } } }) });
check("an act_type that is not a string is not an act type",
  shape({ params: JSON.stringify({ _workflow: { act: { act_type: 1 } } }) })?.status === 403 &&
  shape({ params: JSON.stringify({ _workflow: { act: { act_type: ["calendar_write"] } } }) })?.status === 403 &&
  blankAct?.status === 403);
// AND IT READS AS SILENCE, NOT AS A STRANGER ACT. A refusal has to say which leg
// failed or it is a 403 somebody works around, and quoting `"   "` back at the
// reader is the message being technically true and useless. Whitespace is a row
// that declared nothing, and it gets the sentence for declaring nothing.
check("a blank act type is silence, not an unknown verb",
  /declares none/.test(blankAct?.detail || ""));
check("a params blob that is not an object has no act in it",
  shape({ params: "null" })?.status === 403 &&
  shape({ params: "7" })?.status === 403 &&
  shape({ params: '"calendar_write"' })?.status === 403 &&
  shape({ params: "[]" })?.status === 403);

// A ROW'S `params` IS A STRING; A BODY'S MAY ALREADY BE AN OBJECT. Stringifying
// first would turn a well-formed errand into "[object Object]", which does not
// parse, and refuse it for the shape its client happened to send it in.
check("a body may declare its act as an object rather than a string",
  shape({}, { body: { ...claimBody,
                      params: { _workflow: { act: { ...CAL_ACT } } } } }) === "next");
check("...and that spelling is judged, not waved through",
  shape({}, { body: { ...claimBody,
                      params: { _workflow: { act: { ...CAL_ACT,
                                                    act_type: "send_message" } } } } })
    ?.status === 403);

// Body-or-row, the same both-must-be-right rule the consequence leg has: the
// claimant may not re-declare what the errand IS in the breath that claims it.
check("a write may not re-declare a calendar errand as a send",
  shape({}, { body: { ...claimBody,
                      params: deviceParams({ ...CAL_ACT, act_type: "send_message" }) } })
    ?.status === 403);
check("...nor mint an act onto a row that declares none",
  shape({ params: "" }, { body: { ...claimBody, params: deviceParams() } })
    ?.status === 403);

// THE DRIFT THIS PIN EXISTS FOR. Three layers spelled these strings three
// different ways once — the brain minting `phone_eventkit` / `calendar_event` /
// `owner_calendar` while the phone refused everything that was not
// `anticipy_phone` / `calendar_write` / `device_calendar_store` — and a grep
// across the repo found ZERO overlap with nothing anywhere red. A vocabulary
// held in three files and pinned in none is the same failure this suite's lane
// pin already exists to prevent, one field over. So the hook's list is read out
// of the hook and compared with the other two files rather than restated here.
const swiftSrc = readFileSync(join(here, "..", "..", "app", "ios", "Anticipy",
  "Backend", "CalendarHandPolicy.swift"), "utf8");
const brainSrc = readFileSync(join(here, "..", "..", "brain",
  "anticipy_core.py"), "utf8");
const hookActs = (() => {
  const m = laneSrc.match(/DEVICE_ACT_TYPES\s*=\s*\[([^\]]*)\]/);
  return m ? (m[1].match(/"([^"]+)"/g) || []).map((s) => s.slice(1, -1)) : [];
})();
const swiftActs = ["writeActType", "undoActType"].map((n) => {
  const m = swiftSrc.match(new RegExp(n + '\\s*=\\s*"([^"]+)"'));
  return m ? m[1] : null;
});
const brainAct = (brainSrc.match(/PHONE_CALENDAR_ACT_TYPE\s*=\s*"([^"]+)"/) || [])[1];

check("the hook names an admitted act set at all", hookActs.length === 2);
check("the hook and the phone admit the same two calendar acts",
  swiftActs.every((a) => a && hookActs.indexOf(a) >= 0) &&
  hookActs.every((a) => swiftActs.indexOf(a) >= 0));
check("the brain mints an act the hook admits",
  !!brainAct && hookActs.indexOf(brainAct) >= 0);

// ----------------------------------------------------- the lane is evidence
// `guard.pb.js:449` lets an account session PATCH any field of its own job row,
// and the EVIDENCE map that protects `lane` (guard.pb.js:261) sits only in the
// agent-credential branch. So the hook's own claim — "a claimant that could name
// its own lane could name its way out of every leg here" — was true of the
// extension and FALSE of the phone, which is the caller the routing leg hands
// the whole lane to. Both vectors were driven and both were admitted.
const lanelessRow = (fields = {}) => ({
  "jobs/job1": record("job1", { lane: "", owner_ref: OWNER, workflow_id: "wf1",
                                consequence: "consequential", status: "queued",
                                params: deviceParams(), approval: "", ...fields }),
});
const relane = (rows, body) => drive(lane, { ...CLAIM, auth: ownerAuth, rows, body }).outcome;

check("(a) a body may not move a lane-less row onto the device lane",
  relane(lanelessRow({ status: "awaiting_confirm", consequence: "read_only" }),
         { lane: DEVICE_LANE, status: "queued", consequence: "read_only" })?.status === 403);
check("(b) nor in two writes, which is how the one-write refusal was walked past",
  relane(lanelessRow(), { lane: DEVICE_LANE })?.status === 403);
check("a device errand may not be laundered back onto the browser lane either",
  relane(deviceJob(), { lane: "" })?.status === 403);
check("the refusal says the lane is minted, not chosen",
  /mint|rewrit/i.test(relane(deviceJob(), { lane: "" })?.error || ""));
check("case and padding do not buy a lane change",
  relane(lanelessRow(), { lane: "Device_Calendar" })?.status === 403 &&
  relane(lanelessRow(), { lane: "  device_calendar  " })?.status === 403);
check("even the worker may not rewrite a lane",
  drive(lane, { ...CLAIM, headers: asWorker, rows: lanelessRow(),
                body: { lane: DEVICE_LANE } }).outcome?.status === 403);
check("even a superuser may not rewrite a lane",
  relane(lanelessRow(), { lane: DEVICE_LANE }) !== "next" &&
  drive(lane, { ...CLAIM, auth: { id: "su1" }, superuser: true, rows: lanelessRow(),
                body: { lane: DEVICE_LANE } }).outcome?.status === 403);

// ECHO STAYS ALLOWED, or PocketBase clients resending fields break ordinary
// work for no gain — the same allowance guard.pb.js makes for `owner_ref`. And
// the echo has to be normalised the way the comparison is, or the allowance is
// narrower than the rule it serves.
check("echoing the stored lane back unchanged is not a lane change",
  relane(deviceJob(), { ...claimBody, lane: DEVICE_LANE }) === "next");
check("...normalised, the way every other lane read here is",
  relane(deviceJob(), { ...claimBody, lane: " Device_Calendar " }) === "next");

// ------------------------------------------------- the approver and the hand
// workflow_guard's "an executor cannot rewrite or approve its plan" (:178) is
// keyed on `agentCaller` (:36), the X-Anticipy-Agent-ID header. The phone never
// sends one (AnticipyBackend.swift:144 carries the account token alone), so on
// the device lane — where the executor IS the phone — that leg cannot fire.
// Driven before this: an owner session moved `awaiting_confirm` -> `queued`
// carrying an approval every field of which the same request supplied, and both
// hooks said next; the byte-identical body with an agent credential is 409.
//
// The hook cannot mint a second credential and does not pretend to. What it
// refuses is the ONE-REQUEST forge: the write that releases or claims the
// errand may not also be the write that mints the tap.
const TAP = JSON.stringify({ plan_id: "wf1", plan_version: 1,
  scope_digest: "digest1",
  gesture: { kind: "tap", actor: OWNER, plan_id: "wf1", plan_version: 1 } });
const held = (fields = {}) => deviceJob({ status: "awaiting_confirm", ...fields });
const asOwner = (rows, body) => drive(lane, { ...CLAIM, auth: ownerAuth, rows, body }).outcome;

check("a hand may not mint the tap in the write that releases the errand",
  asOwner(held(), { status: "queued", approval: TAP })?.status === 403);
check("nor in the write that claims it",
  asOwner(deviceJob(), { ...claimBody, approval: TAP })?.status === 403);
// A bare claim stamp changes no status, so `live` is false for it and the claim
// half of that condition is the only thing standing there. Driven separately, or
// that half is a second copy of the status check waiting to disagree with it.
check("nor alongside a bare claim stamp that moves no status",
  asOwner(held(), { claimed_by: "phone", approval: TAP })?.status === 403);
check("nor re-approve one already running under its own hand",
  asOwner(deviceJob({ status: "running", approval: TAP }),
          { approval: TAP.replace('"plan_version":1', '"plan_version":2') })
    ?.status === 403);
check("the refusal says what to do instead",
  /two separate writes|held/i.test(
    asOwner(held(), { status: "queued", approval: TAP })?.error
    || asOwner(held(), { status: "queued", approval: TAP })?.detail || ""));

// AND THE FLOW IT FORCES IS A REAL ONE, driven end to end, or this leg is a
// refusal that bricks the lane rather than a rule the phone can obey.
check("the tap lands on a held errand", asOwner(held(), { approval: TAP }) === "next");
check("...a later write releases it", asOwner(held({ approval: TAP }), { status: "queued" }) === "next");
check("...and the phone then claims it",
  asOwner(deviceJob({ approval: TAP }), claimBody) === "next");
check("resending the STORED tap alongside the claim is not minting one",
  asOwner(deviceJob({ approval: TAP }), { ...claimBody, approval: TAP }) === "next");

// AND IT MUST NOT LOCK THE ROW, the same way the shape legs must not.
check("a device errand carrying a fresh approval can still be cancelled",
  asOwner(held(), { status: "cancelled", approval: TAP }) === "next");
check("...and still be failed",
  asOwner(held(), { status: "failed", approval: TAP }) === "next");

// THE BROWSER LANE IS UNTOUCHED. Approving is the phone's whole job there, and
// there the approver and the executor really are different credentials, which
// is the only reason workflow_guard:178 can bite at all.
check("the phone may still approve a browser errand in one write",
  asOwner(lanelessRow({ status: "awaiting_confirm" }),
          { status: "queued", approval: TAP }) === "next");

// ----------------------------------------------------------- and on a CREATE
// THE SHAPE LEGS NEVER RAN ON A CREATE, AND A CREATE IS HOW EVERY ROW IS BORN.
// The whole device block sat inside `method === "PATCH"`, so one POST carrying
// `{lane:"device_calendar", status:"queued", consequence:"read_only"}` minted a
// live unapproved device errand and neither hook asked anything: workflow_guard
// returns at :24 before any leg exists when `workflow_id` is blank, and
// `read_only` is exempt at :534 when it is not. The byte-identical row arriving
// as a PATCH was 403'd twice. workflow_guard.pb.js:202-220 carries the scar for
// exactly this shape — "a job created `running` skipped Shelf 2's whole
// admission" — and this lane repeated it.
const MINT = { method: "POST", path: "/api/collections/jobs/records" };
const mint = (over = {}) => drive(lane, {
  ...MINT, auth: ownerAuth,
  body: { lane: DEVICE_LANE, status: "queued", consequence: "consequential",
          workflow_id: "wf1", owner_ref: OWNER, params: deviceParams(), ...over },
}).outcome;

check("a device errand may not be BORN read_only and live",
  mint({ consequence: "read_only" })?.status === 403);
check("...nor born live with no workflow behind it",
  mint({ workflow_id: "" })?.status === 403);
check("...nor born live declaring an act this lane does not carry",
  mint({ params: deviceParams({ ...CAL_ACT, act_type: "send_message" }) })?.status === 403);
check("...nor born live declaring no act at all",
  mint({ params: "" })?.status === 403);
// AND WITH NO `params` KEY IN THE REQUEST AT ALL, which is not the same input:
// a create has no row to fall back on, so this is the one write where NOBODY
// speaks about the act. Silence is a rejection here, exactly as an unrecognised
// consequence is — polarity is a floor.
check("...nor born live with the act simply left out",
  drive(lane, { ...MINT, auth: ownerAuth,
                body: { lane: DEVICE_LANE, status: "queued",
                        consequence: "consequential", workflow_id: "wf1",
                        owner_ref: OWNER } }).outcome?.status === 403);
check("...nor born already approved AND already live",
  mint({ approval: TAP })?.status === 403);
// ...NOR BORN CARRYING A TAP WHILE MERELY HELD, which is the same forge one
// method over, and it was open. The separation leg above fires on a write that
// CHANGES the approval while the row goes live or is claimed. A create that
// arrives already approved changes it while the row is still HELD — so the
// two-write rule that leg exists to create was satisfied by a single request
// that mints the errand AND its tap, and a bare `{status:"queued"}` afterwards
// is a write that changes no approval at all.
//
// DRIVEN END TO END AGAINST BOTH HOOKS, with every mirror field workflow_guard
// compares (plan_id, version, state, goal, consequence, lineage_key, owner_ref,
// scope_digest, effect_key, attempts, approval, receipt, lease) supplied by the
// same caller in the same request:
//
//   POST  {status:"awaiting_confirm", approval:<tap bound to wf1/v1/d1>} -> next, next
//   PATCH {status:"queued"}                                             -> next, next
//   PATCH {claimed_by:"phone-abc", status:"running", lease_token:"lt1"} -> next, next
//
// After those three the row is live, claimed by the phone, running, and the
// database — "the final authority" — records an owner approval for an errand
// nobody was ever shown. workflow_guard cannot see it: its own separation leg
// (:178) is keyed on the X-Anticipy-Agent-ID header the phone does not send,
// and the approval it validates is bound to a plan version the same request
// wrote.
//
// A ROW THAT DOES NOT YET EXIST CANNOT HAVE BEEN TAPPED. That is the whole
// argument, and it costs nothing legitimate: `brain/pb.py` never writes an
// `approval` on any request (the column does not appear in the file at all) and
// `extension/background.js` never writes one either. A tap is always a later
// write onto a row the owner has already been shown.
check("...nor born carrying a tap while merely HELD, which is the same forge",
  mint({ status: "awaiting_confirm", approval: TAP })?.status === 403);
check("...nor born with one at any status at all, because the status is not the point",
  mint({ status: "needs_user", approval: TAP })?.status === 403 &&
  mint({ status: "draft", approval: TAP })?.status === 403);
check("the refusal says a tap lands on an errand that already exists",
  /already exist|does not yet exist|never shown/i.test(
    mint({ status: "awaiting_confirm", approval: TAP })?.detail || ""));
// A BLANK APPROVAL IS NOT A TAP, or every ordinary create that echoes the empty
// column back is refused for carrying nothing.
check("an empty approval column on a create is not a tap",
  mint({ status: "awaiting_confirm", approval: "" }) === "next");
// AND THE HELD-CREATE ALLOWANCE ABOVE IS UNTOUCHED: it is about SHAPE, and a
// held row still runs nothing, so it stays exactly as wide as it was.
check("a held device errand carrying no tap is still minted however it is shaped",
  mint({ status: "awaiting_confirm", consequence: "read_only" }) === "next");
// THE BROWSER LANE IS NOT THIS LANE'S BUSINESS. There the approver and the
// executor are different credentials, which is the only reason workflow_guard's
// own separation leg can bite, so nothing here narrows it.
check("a browser-lane create may still carry whatever workflow_guard admits",
  drive(lane, { ...MINT, auth: ownerAuth,
                body: { lane: "", status: "awaiting_confirm", owner_ref: OWNER,
                        approval: TAP } }).outcome === "next");
// AND IT IS A QUESTION ABOUT THE ROW, NOT ABOUT WHO IS ASKING — the same
// polarity the shape legs have. The worker holds the service token and is the
// one caller with no owner in front of it at all, so if anything it is the
// LAST credential that may mint a tap. Nothing legitimate is lost: `brain/pb.py`
// never writes this column, and an approval carried onto a re-queued row would
// be a tap on the old plan version, which workflow_guard binds against anyway.
check("the worker may not mint an approved device errand either",
  drive(lane, { ...MINT, headers: asWorker,
                body: { lane: DEVICE_LANE, status: "awaiting_confirm",
                        consequence: "consequential", workflow_id: "wf1",
                        params: deviceParams(), approval: TAP } }).outcome
    ?.status === 403);
check("a well-formed device errand is still minted",
  mint() === "next");
check("and a HELD one may be minted however it is shaped, because nothing runs",
  mint({ status: "awaiting_confirm", consequence: "read_only" }) === "next");
check("the worker mints under the same shape rule it patches under",
  drive(lane, { ...MINT, headers: asWorker,
                body: { lane: DEVICE_LANE, status: "queued",
                        consequence: "read_only", workflow_id: "wf1",
                        params: deviceParams() } }).outcome?.status === 403);
check("a browser-lane create is untouched by any of this",
  drive(lane, { ...MINT, auth: ownerAuth,
                body: { lane: "", status: "queued", owner_ref: OWNER } }).outcome
    === "next");

// THE SCOPE BOUNDARY, WITH ITS COMPENSATING CONTROL, because a boundary
// asserted alone is a hole written down. The claim legs stay PATCH-only: they
// judge a transition and a create is not one, and widening them would change
// the research and supervised lanes, which this card does not own. So a create
// MAY name itself claimed — and the row still cannot run, because the PATCH that
// would move it to `running` is the write those legs judge.
check("a create may name itself claimed, because a label is not a transition",
  drive(lane, { ...MINT, headers: agentHeaders,
                body: { lane: DEVICE_LANE, status: "queued",
                        consequence: "consequential", workflow_id: "wf1",
                        params: deviceParams(), claimed_by: "chrome" } }).outcome
    === "next");
check("...and it still cannot RUN, which is the write that matters",
  claim({ rows: deviceJob({ claimed_by: "chrome" }), headers: agentHeaders })
    ?.status === 403);

// A PATCH WHOSE ROW CANNOT BE READ IS STILL A PATCH. Keying the immutability leg
// on `rec` rather than on the method would make a not-found row the one place a
// body could mint its own lane.
check("a not-found row does not let a body name its own lane",
  drive(lane, { ...CLAIM, auth: ownerAuth, rows: {},
                body: { lane: DEVICE_LANE } }).outcome?.status === 403);

// ------------------------------------------------ the gate is NOT duplicated
// "I did not write a second approval check" is the one claim a reviewer cannot
// confirm by reading, so it is measured. The lane hook decides ROUTING and
// SHAPE. Whether the owner approved is workflow_guard's question and it is
// asked in exactly one place.
// `approval` IS NOT ON THIS LIST ANY MORE, and that is a weakening of the grep
// paid for with something stronger below, not a quiet retreat.
//
// The hook now asks one question about that column — did THIS write change it?
// — because workflow_guard's separation leg ("an executor cannot rewrite or
// approve its plan") is keyed on the X-Anticipy-Agent-ID header, the phone does
// not send one, and on the device lane the phone IS the executor. So the leg
// that stops an executor approving its own plan could not fire on the only lane
// where the executor holds owner authority. Closing that needs the hook to know
// the column changed, which needs it to read the column.
//
// What must stay true is not "never touches the word". It is that this file
// cannot DECIDE approval. Two properties carry that, and together they are
// sharper than the string check they replace:
//
//   1. It never looks INSIDE an approval. Every field an approval is judged by
//      — the digest, the version, the words, the gesture — stays on this list,
//      in every access form, so a check of the contents cannot be written
//      without going red.
//   2. An approval can only ever COST a refusal here, never buy a pass. That is
//      driven, over every shape below: for each request, the outcome with the
//      approval present is compared with the outcome without it, and a body
//      that is admitted must still be admitted with the approval stripped out.
//      A second gate cannot satisfy that — waving a row through on the strength
//      of an approval is the one thing it exists to do.
const vocabulary = ["scope_digest", "plan_version", "owner_words",
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

// AND THE PROPERTY ITSELF, DRIVEN. The grep above says the hook cannot read the
// fields an approval is judged by. This says the hook cannot ACT on an approval
// in the only direction that would make it a second gate: every request below is
// run twice, once as written and once with `approval` deleted from the body, and
// a body that is admitted must still be admitted without it.
//
// A second approval gate cannot pass this. Waving a row through on the strength
// of an approval is the one thing such a gate exists to do, and the moment this
// file did it, some row here would be `next` with the approval and refused
// without. The reverse — refused WITH, admitted without — is allowed and is
// exactly what the separation leg does, which is why the comparison is one-way.
const WITHOUT = [
  // The shapes where an approval would be worth forging: a malformed errand
  // going live, a claim, a release, a create, and the browser lane beside them.
  { label: "a read_only errand going live", rows: deviceJob({ consequence: "read_only" }),
    body: { ...claimBody, approval: TAP } },
  { label: "a workflow-less errand going live", rows: deviceJob({ workflow_id: "" }),
    body: { ...claimBody, approval: TAP } },
  { label: "an errand whose act is a send", body: { ...claimBody, approval: TAP },
    rows: deviceJob({ params: deviceParams({ ...CAL_ACT, act_type: "send_message" }) }) },
  { label: "a browser claiming a device errand", rows: deviceJob(),
    body: { ...claimBody, approval: TAP }, auth: null, headers: agentHeaders },
  { label: "a lane change", rows: lanelessRow(),
    body: { lane: DEVICE_LANE, approval: TAP } },
  { label: "a well-formed claim", rows: deviceJob(), body: { ...claimBody, approval: TAP } },
  { label: "a release", rows: deviceJob({ status: "awaiting_confirm" }),
    body: { status: "queued", approval: TAP } },
  { label: "a create", method: "POST", path: "/api/collections/jobs/records",
    body: { lane: DEVICE_LANE, status: "queued", consequence: "consequential",
            workflow_id: "wf1", owner_ref: OWNER, params: deviceParams(),
            approval: TAP } },
  { label: "a browser-lane approval", rows: lanelessRow({ status: "awaiting_confirm" }),
    body: { status: "queued", approval: TAP } },
];
let bought = [];
for (const c of WITHOUT) {
  const { label, body, ...rest } = c;
  const opts = { ...CLAIM, auth: ownerAuth, ...rest };
  const stripped = { ...body };
  delete stripped.approval;
  const withIt = drive(lane, { ...opts, body }).outcome;
  const withoutIt = drive(lane, { ...opts, body: stripped }).outcome;
  if (withIt === "next" && withoutIt !== "next") bought.push(label);
}
check("an approval can only cost a refusal here, never buy a pass",
  bought.length === 0);

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

// AND ON THE CREATE PATH TOO, which is the compensating control for this file
// saying "next" to a well-formed `mint()`. The lane hook asks what the errand
// IS and who may run it; whether he approved it is workflow_guard's question,
// asked in one place, and the create is the path finding 1 showed nobody was
// asking on. Driven: a device row born `queued` + `consequential` with no
// approval is 409 "consequential work needs parseable approval" — so the lane
// hook admitting the shape does not admit the act.
check("workflow_guard holds an unapproved device errand BORN live, too",
  drive(guard, { ...MINT, auth: ownerAuth, rows: {},
                 body: guardBody() }).outcome?.status === 409);
check("...and for the same reason it holds one that got there by PATCH",
  /approval/i.test(drive(guard, { ...MINT, auth: ownerAuth, rows: {},
                                  body: guardBody() }).outcome?.detail || ""));

console.log(failures ? `\n${failures} FAILED` : "\nall device-lane checks passed");
process.exit(failures ? 1 : 0);
