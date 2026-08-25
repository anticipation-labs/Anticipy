// The watch lease, driven as real code rather than read as text.
//
// WHAT THIS PINS. `ContextSource.mail.promises` opens with "You open it. I read
// it once, in the front window, while you watch." Until `jobs.watching_until`
// existed, nothing enforced a word of it. The lease is what makes it a fact
// about the code: the phone pushes `now + 30s` every ten seconds and ONLY while
// `SupervisedReadView` is on screen with the scene phase `.active`, and the
// server re-reads that stamp before it lets a browser claim the row or write a
// line of narration.
//
// THE POINT OF THE EXEMPTION IS ITS EVIDENCE. `research_lane.pb.js` refuses
// every browser claim on a read-only lane; `supervised_read` is allowed through
// it. `side_trip.js`'s consent block is the standing rule on what may authorise that:
// NOT a flag, because a flag "is something another process set, and 'another
// process decided I may read your inbox' is exactly the sentence this product
// cannot afford to be true." So the checks below spend most of their weight on
// the negative case — a claimant that says all the right things in its own
// request body still gets 403'd, because the only thing consulted is a stamp
// that only a foregrounded app can keep fresh.
//
// Both hooks are executed, not grepped: this is the kind of guard where the
// branch can look right and evaluate wrong.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const hooks = join(here, "..", "..", "backend", "pb_hooks");
const laneSrc = readFileSync(join(hooks, "research_lane.pb.js"), "utf8");
const guardSrc = readFileSync(join(hooks, "guard.pb.js"), "utf8");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const SERVICE_TOKEN = "service-token-for-the-worker";
// Long enough to satisfy the guard's `agentToken.length >= 40`.
const AGENT_TOKEN = "a".repeat(48);
const OWNER = "owner_abc1234567";

const record = (id, fields) => ({
  id,
  getString: (f) => String(fields[f] ?? ""),
  getBool: (f) => fields[f] === true,
});

// PocketBase stores dates as "2026-08-21 12:00:00.000Z" — a space, not a T.
// Both hooks read them with `getString` + `new Date()`, the idiom
// workflow_guard.pb.js:160-161 already ships for `lease_until`, so the space
// form is the one that actually has to parse. Asserted below rather than
// assumed: if it ever stopped parsing, every supervised read would 403 with a
// message about nobody watching, and the cause would be a date format.
const pbStamp = (msFromNow) =>
  new Date(Date.now() + msFromNow).toISOString().replace("T", " ");

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

// One request through a real hook. Returns "next" (allowed through to
// PocketBase), {status, error} (refused), or the rewritten query when the hook
// only edited the request on its way past.
function drive(handler, { method, path, query = "", headers = {}, body = {},
                          auth = null, superuser = false, rows = {} }) {
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
    hasSuperuserAuth: () => superuser,
    request: { method, url, header: { get: (k) => headers[k] || "" } },
    requestInfo: () => ({ body }),
    next: () => { outcome = "next"; },
    json: (status, payload) => { outcome = { status, error: payload.error }; },
    app: {
      findRecordById: (collection, id) => {
        const rec = rows[`${collection}/${id}`];
        if (!rec) throw new Error("not found");
        return rec;
      },
      findFirstRecordByFilter: (collection, _filter, p) => {
        const rec = rows[`${collection}/agent:${p.id}`];
        if (!rec || rec.getString("agent_token") !== p.token) {
          throw new Error("not found");
        }
        return rec;
      },
    },
  };
  handler(e);
  return { outcome, filter: url.rawQuery };
}

// ---------------------------------------------------------------- the lane
const lane = load(laneSrc);
check("research_lane registers a router middleware", typeof lane === "function");

const CLAIM = { method: "PATCH", path: "/api/collections/jobs/records/job1" };
const claimBody = { claimed_by: "chrome-abc", status: "running" };
const readJob = (fields) =>
  ({ "jobs/job1": record("job1", { lane: "supervised_read", owner_ref: OWNER, ...fields }) });

const claim = (rows, body = claimBody, headers = {}) =>
  drive(lane, { ...CLAIM, body, headers, rows }).outcome;

check("a browser may claim a supervised read while somebody is watching",
  claim(readJob({ watching_until: pbStamp(25000) })) === "next");

check("the same claim is refused once the lease has lapsed",
  claim(readJob({ watching_until: pbStamp(-1000) }))?.status === 403);

check("a supervised read with no lease at all is refused",
  claim(readJob({}))?.status === 403);

check("an unparseable lease is refused rather than trusted",
  claim(readJob({ watching_until: "whenever" }))?.status === 403);

check("the refusal says why, in her voice",
  /nobody is watching/.test(claim(readJob({}))?.error || ""));

// The whole reason this is a lease and not a flag. Every one of these is a
// claimant asserting its own authority, which is the sentence side_trip.js
// refuses to let any other process say.
const lapsed = readJob({ watching_until: pbStamp(-1000) });
check("a body flag cannot stand in for a live lease",
  claim(lapsed, { ...claimBody, supervised: true, authorized: true })?.status === 403);
check("a body-supplied watching_until cannot stand in for the stored one",
  claim(lapsed, { ...claimBody, watching_until: pbStamp(60000) })?.status === 403);
check("params cannot carry the authorisation either",
  claim(lapsed, { ...claimBody, params: '{"authorized":true,"watching":true}' })?.status === 403);
// `claimed_by: "worker-research"` short-circuits the research branch — a
// legacy belt from before the X-Anticipy-Worker marker. It is a body field, so
// on the supervised lane it would have been a one-line bypass of the entire
// lease. Pinned here because the bypass is invisible: the claim just succeeds.
check("naming yourself the worker does not make you watched",
  claim(lapsed, { ...claimBody, claimed_by: "worker-research" })?.status === 403);

check("a lapsed lease also stops the progress updates of a read already running",
  claim(lapsed, { status: "running" })?.status === 403);

check("a non-claiming write still goes through, so she can report that she stopped",
  claim(lapsed, { result: "stopped when you looked away", status: "failed" }) === "next");

check("research is still refused outright, lease or no lease",
  claim({ "jobs/job1": record("job1", { lane: "research", watching_until: pbStamp(60000) }) })
    ?.status === 403);

check("ordinary browser work is untouched by any of this",
  claim({ "jobs/job1": record("job1", { lane: "", workflow_id: "wf1" }) }) === "next");

// THE MARKER IS NOT THE CREDENTIAL. This block used to assert that the bare
// `X-Anticipy-Worker` header exempted a caller from the lane and the lease,
// which PINNED a one-header bypass as correct behaviour. `brain/pb.py:21-22`
// says what the header is in so many words - "a ROUTING marker, not a
// credential; the service token is what authenticates" - and
// `test_config_base.mjs:197` pins that the extension never sends the service
// token, so demanding it costs nothing legitimate.
check("the marker alone does NOT exempt anybody from the watch lease",
  claim(readJob({}), claimBody, { "X-Anticipy-Worker": "1" })?.status === 403);
check("the marker alone does NOT let a browser claim research either",
  claim({ "jobs/job1": record("job1", { lane: "research" }) }, claimBody,
        { "X-Anticipy-Worker": "1" })?.status === 403);
check("the authenticated worker IS exempt",
  claim(readJob({}), claimBody,
        { "X-Anticipy-Worker": "1", "X-Anticipy-Token": SERVICE_TOKEN }) === "next");
check("a wrong service token is not a worker",
  claim(readJob({}), claimBody,
        { "X-Anticipy-Worker": "1", "X-Anticipy-Token": "nope" })?.status === 403);

// A lane is normalised before it is compared, so neither refusal can be walked
// past with casing or padding - and until the guard fix that accompanies this,
// `lane` was a column the claimant could write itself.
check("a mixed-case supervised lane is still judged by the lease",
  claim({ "jobs/job1": record("job1", { lane: "Supervised_Read" }) }, claimBody)
    ?.status === 403);
check("a padded research lane is still refused",
  claim({ "jobs/job1": record("job1", { lane: "  research  " }) }, claimBody)
    ?.status === 403);

// Layer 1: an 0.2.3 extension in the wild polls without naming a lane. It must
// never even SEE a supervised read — it has no read-only vocabulary narrowing
// and no narration, so it would run somebody's mailbox as an ordinary errand.
const oldPoll = drive(lane, {
  method: "GET", path: "/api/collections/jobs/records",
  query: 'filter=' + encodeURIComponent('status="queued" && (owner="abc" || owner="")'),
});
// `URLSearchParams.toString()` writes spaces as `+`, so the rewritten filter
// has to be decoded the way a query string is decoded before it can be read
// back as a PocketBase filter.
const asFilter = (raw) => decodeURIComponent(String(raw).replace(/\+/g, "%20"));
check("an old extension's poll is rewritten to hide both server-side lanes",
  /lane != "research"/.test(asFilter(oldPoll.filter)) &&
  /lane != "supervised_read"/.test(asFilter(oldPoll.filter)));

const readPoll = drive(lane, {
  method: "GET", path: "/api/collections/jobs/records",
  query: 'filter=' + encodeURIComponent(
    `status="queued" && owner_ref="${OWNER}" && lane="supervised_read"`),
});
check("a poll that names the lane is left alone, so the read loop can find its work",
  !/lane !=/.test(asFilter(readPoll.filter)));

// ------------------------------------------------------------- the guard
// The narration channel. A Chrome install could not write an event at all
// before this; now it may write exactly two kinds, for exactly one job, for
// exactly as long as somebody is watching.
const guard = load(guardSrc);
check("guard registers a router middleware", typeof guard === "function");

const agentRows = (jobFields) => ({
  "agents/agent:ag1": record("ag1", { agent_token: AGENT_TOKEN, owner_ref: OWNER }),
  "jobs/job1": record("job1", { lane: "supervised_read", owner_ref: OWNER, ...jobFields }),
});
const agentHeaders = { "X-Anticipy-Agent-ID": "ag1", "X-Anticipy-Agent-Token": AGENT_TOKEN };
const narrate = (body, jobFields) => drive(guard, {
  method: "POST", path: "/api/collections/events/records",
  headers: agentHeaders, body, rows: agentRows(jobFields),
}).outcome;

const line = { kind: "read_line", text: "Opening your mail now.", goal: "job1", owner_ref: OWNER };
const fact = { kind: "read_fact", text: "Marcus Bell is a client; a proposal is in flight.",
               goal: "job1", owner_ref: OWNER, source: "supervised_mail", importance: 4 };

check("a narrated line is allowed while the lease is live",
  narrate(line, { watching_until: pbStamp(25000) }) === "next");
check("a distilled fact is allowed while the lease is live",
  narrate(fact, { watching_until: pbStamp(25000) }) === "next");
check("narration stops the moment the lease lapses",
  narrate(fact, { watching_until: pbStamp(-1000) })?.status === 403);
check("narration on a job that never had a lease is refused",
  narrate(fact, {})?.status === 403);
check("only the two narration kinds may be written by a browser",
  narrate({ ...fact, kind: "transcript" }, { watching_until: pbStamp(25000) })?.status === 403);
check("raw page text cannot be smuggled in as a profile seed",
  narrate({ ...fact, kind: "profile" }, { watching_until: pbStamp(25000) })?.status === 403);
check("narration must name the job it came from",
  narrate({ ...fact, goal: "" }, { watching_until: pbStamp(25000) })?.status === 403);
check("narration must be owned, or the person it is about can never read it",
  narrate({ ...fact, owner_ref: "" }, { watching_until: pbStamp(25000) })?.status === 403);
check("a browser cannot narrate into somebody else's account",
  narrate({ ...fact, owner_ref: "someone_else" }, { watching_until: pbStamp(25000) })?.status === 403);
check("a live lease on a job in another lane authorises nothing",
  narrate(fact, { lane: "", watching_until: pbStamp(25000) })?.status === 403);
check("a live lease on somebody else's job authorises nothing",
  narrate(fact, { owner_ref: "someone_else", watching_until: pbStamp(25000) })?.status === 403);
check("a pasted message body is not a distilled fact",
  narrate({ ...fact, text: "x".repeat(401) }, { watching_until: pbStamp(25000) })?.status === 403);
check("a fact-length sentence still gets through",
  narrate({ ...fact, text: "x".repeat(400) }, { watching_until: pbStamp(25000) }) === "next");
check("an empty narration line is refused rather than written as a blank row",
  narrate({ ...fact, text: "" }, { watching_until: pbStamp(25000) })?.status === 403);
// THE CLAIMANT MAY NOT AUTHOR THE EVIDENCE ABOUT ITSELF.
//
// The guard protected only `owner_ref` on a job PATCH, so the Chrome install
// could write `watching_until` and `lane` on its own owner's jobs - one extra
// request before the claim, and research_lane's belief that the column "is what
// the PHONE last wrote" became false. Same shape as the `legacy_uuid` hole a
// prior audit found in the delete endpoint: a client-authored value trusted as
// proof about the world. Nothing covered this before.
const patchJob = (body) => drive(guard, {
  method: "PATCH", path: "/api/collections/jobs/records/job1",
  headers: agentHeaders, body, rows: agentRows({ watching_until: pbStamp(-1000) }),
}).outcome;

check("a browser cannot stamp its own watch lease",
  patchJob({ watching_until: pbStamp(600000) })?.status === 403);
check("a browser cannot stamp one alongside honest progress either",
  patchJob({ status: "running", watching_until: pbStamp(600000) })?.status === 403);
check("a browser cannot blank the lane out of the lease check",
  patchJob({ lane: "" })?.status === 403);
check("a browser cannot rename the lane to escape either comparison",
  patchJob({ lane: "Supervised_Read" })?.status === 403);
check("a browser cannot launder research into browser-claimable work",
  patchJob({ lane: "researchX" })?.status === 403);
check("but it can still report on the job it is running",
  patchJob({ status: "done", result: "read your last 30 subject lines" }) === "next");
check("and an echoed owner_ref is not treated as an attack",
  patchJob({ status: "running", owner_ref: OWNER }) === "next");

check("the agent still cannot touch a collection it has no business in",
  drive(guard, { method: "GET", path: "/api/collections/owner_profile/records",
                 headers: agentHeaders, rows: agentRows({}) }).outcome?.status === 403);

// The phone's side of the same channel: it reads the narration back with an
// account token, and `supervisedLines` builds a filter with no `||` in it
// precisely because this branch refuses one.
const account = { auth: record(OWNER, {}) };
// The filters are URL-encoded because `&&` is otherwise two query separators —
// unencoded, the guard would only ever see the first clause and this pair of
// checks would pass without touching the rule they name.
const listing = (filter) => drive(guard, {
  method: "GET", path: "/api/collections/events/records",
  query: "filter=" + encodeURIComponent(filter), ...account,
}).outcome;
check("the phone may read one read's narration back",
  listing(`owner_ref="${OWNER}" && (goal="job1")`) === "next");
check("an OR in that filter is still refused, which is why the kinds are split client-side",
  listing(`owner_ref="${OWNER}" && (kind="read_line" || kind="read_fact")`)?.status === 403);

// ------------------------------------------------- the phone writes the lease
// Structural, and deliberately so: this half is Swift and cannot be executed
// here. What it pins is the agreement between the two sides — the column name,
// the lane name, and the fact that the first lease is set at creation. A job
// born without one is unclaimable until the first heartbeat, which reads as a
// dead screen, and the obvious "fix" for a dead screen is a flag.
const swift = readFileSync(
  join(here, "..", "..", "app", "ios", "Anticipy", "AnticipyApp.swift"), "utf8");
const backend = readFileSync(
  join(here, "..", "..", "app", "ios", "Anticipy", "Backend", "AnticipyBackend.swift"), "utf8");
const migration = readFileSync(
  join(here, "..", "..", "backend", "pb_migrations", "1700000041_watch_lease.js"), "utf8");

check("the migration adds watching_until as a date on jobs",
  /name: "watching_until", type: "date"/.test(migration) &&
  /findCollectionByNameOrId\("jobs"\)/.test(migration));
check("the phone and the server spell the lane the same way",
  /supervisedLane = "supervised_read"/.test(swift) &&
  /SUPERVISED_LANE = "supervised_read"/.test(laneSrc));
check("a supervised read is born with its lease already set",
  /watchingUntil: Date\(\)\.addingTimeInterval\(Self\.watchLeaseSeconds\)/.test(swift));
check("the read job is read-only on the row, not just in the prompt",
  /consequence: "read_only"/.test(swift));
check("the heartbeat writes the same column the server reads",
  /"watching_until": ISO8601DateFormatter/.test(swift));
check("stopping by hand lapses the lease instead of waiting it out",
  /func dropWatchLease/.test(swift) && /addingTimeInterval\(-1\)/.test(swift));
check("the lease is thirty seconds, which is what the promise depends on",
  /watchLeaseSeconds: TimeInterval = 30/.test(swift));
check("queueJob is the one job writer, widened rather than duplicated",
  backend.split("func queueJob").length === 2 &&
  /lane: String\? = nil, consequence: String\? = nil/.test(backend));

if (failures) { console.error(`test_watch_lease: ${failures} failed`); process.exit(1); }
console.log("test_watch_lease: all passed");
