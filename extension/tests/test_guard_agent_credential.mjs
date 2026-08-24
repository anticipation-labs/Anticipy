// A PRESENTED AGENT CREDENTIAL THAT DOES NOT RESOLVE MUST BE A REFUSAL.
//
// The bug this pins: guard.pb.js's Chrome-install branch was entered on
// `agentId && agentToken.length >= 40`, looked the pair up in `agents`, and
// then asked `if (agent)`. When the lookup came back with nothing — a wrong
// token, a revoked credential, a deleted agent row, somebody guessing ids —
// control fell OUT of that block and kept walking down the ladder into the
// anonymous branches, where the tokenless pairing bootstrap lives. So a caller
// presenting a BAD agent credential was treated exactly like a caller
// presenting NONE: it could still self-register an agent, still walk pair
// codes, still claim an unpaired record, still heartbeat a paired one. A
// failed authentication answered with the anonymous surface instead of a no,
// and silently — the same shape as HANDOFF.md:116-118, where an agent looked
// alive while every real read was 403 and nothing said which it was.
//
// The four allowed-by-the-bootstrap shapes are each driven twice here, once
// with a broken credential (must refuse) and once with no headers at all (must
// still work), because the second half is the regression that would break
// every new install: a fresh extension has no credential yet, and claiming one
// anonymously is the bootstrap's whole reason to exist.
//
// Harness technique is the one test_guard_superuser_dashboard.mjs and
// test_watch_lease.mjs already use on this same hook: load the real file with
// only the globals the JSVM provides, keep the callback routerUse() registers,
// and drive it with a fake `e`. `checkTheSuiteBites` at the bottom puts the
// original defect back with a string replace and requires the fall-through
// case to pass under it — nothing is written, the mutation lives in a local.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(
  join(here, "..", "..", "backend", "pb_hooks", "guard.pb.js"), "utf8");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const SERVICE_TOKEN = "service-token-for-the-worker";
// 40 is not a taste call: it is the `agent_token` column's own minimum
// (backend/pb_migrations/1700000026_agent_tokens.js:12), which is why a
// shorter token can never match a stored row.
const AGENT_TOKEN = "a".repeat(48);
const AGENT_ID = "b4d1e0f2-8c7a-4d31-9f60-2a1c5e8b7d44";
const OWNER = "owner_abc1234567";
const REFUSAL = "agent credential is not recognized";

const record = (id, fields) => ({
  id,
  getString: (f) => String(fields[f] ?? ""),
  getBool: (f) => fields[f] === true,
});

// Load a hook source and keep the middleware routerUse() registers, plus the
// lines it logged. `console` is injected rather than inherited so a refusal can
// be asserted to be LOUD — the original fail-open was invisible in the log,
// which is half of why it survived.
function load(source) {
  let handler = null;
  const logs = [];
  const globals = {
    routerUse: (fn) => { handler = fn; },
    $os: { getenv: (k) => (k === "ANTICIPY_SERVICE_TOKEN" ? SERVICE_TOKEN : "") },
    console: { log: (...parts) => logs.push(parts.join(" ")) },
  };
  const names = Object.keys(globals);
  new Function(...names, source)(...names.map((n) => globals[n]));
  return { handler, logs };
}

const guard = load(src);
check("the guard registers a router middleware", typeof guard.handler === "function");

// One request through a real hook. Returns "next" (allowed through to
// PocketBase) or {status, error}.
//
// `lookup` models the three things findFirstRecordByFilter actually does:
//   "rows"  — the real one: match `rows`, and THROW when nothing matches,
//             which is what PocketBase does on no rows.
//   "empty" — return nothing without throwing. The hook's own `if (agent)`
//             exists for this shape, so it is driven rather than assumed.
//   "throw" — an infrastructure failure (database unreachable), which is a
//             different event from a proven-bad credential and gets the same
//             answer.
//
// NOT SCAFFOLDING — the double was incomplete without it.
//
// The pair-code branches of guard.pb.js count failed lookups per caller in
// PocketBase's own app-wide key/value store and refuse a lookup they cannot
// count (`pairLookup`), because six digits with unlimited guesses is somebody
// else's browser waiting to be claimed. Fail-closed is deliberate there: a
// pairing that stops working is reported in minutes, a throttle that silently
// went missing is reported never.
//
// So an event that cannot answer `e.app.store()` and `e.realIP()` is no longer
// a real event, and the two pairing-bootstrap checks below came back 503 until
// this stub existed — red earned by the double, not by the product. Deleting
// it does not simplify anything; it re-breaks those two checks. One store for
// the whole file, since nothing here goes near a ceiling.
const pairFailures = new Map();
const throttleStore = {
  get: (k) => (pairFailures.has(k) ? pairFailures.get(k) : null),
  set: (k, v) => { pairFailures.set(k, v); },
  getAll: () => Object.fromEntries(pairFailures),
  remove: (k) => { pairFailures.delete(k); },
};
function request({ handler = guard.handler, method, path, query = "",
                   headers = {}, body = {}, auth = null, superuser = false,
                   rows = {}, lookup = "rows" } = {}) {
  const params = new URLSearchParams(query);
  let outcome = null;
  const e = {
    auth,
    hasSuperuserAuth: () => superuser,
    realIP: () => "198.51.100.9",
    request: {
      method,
      url: {
        path,
        query: () => ({ get: (k) => (params.has(k) ? params.get(k) : null) }),
      },
      header: { get: (k) => headers[k] || "" },
    },
    requestInfo: () => ({ body }),
    next: () => { outcome = "next"; },
    json: (status, payload) => { outcome = { status, error: payload.error }; },
    app: {
      store: () => throttleStore,
      findRecordById: (collection, id) => {
        const rec = rows[`${collection}/${id}`];
        if (!rec) throw new Error("not found");
        return rec;
      },
      findFirstRecordByFilter: (collection, _filter, p) => {
        if (lookup === "throw") throw new Error("dial tcp: connection refused");
        if (lookup === "empty") return null;
        const rec = rows[`${collection}/agent:${p.id}`];
        if (!rec || rec.getString("agent_token") !== p.token) {
          throw new Error("not found");
        }
        return rec;
      },
    },
  };
  handler(e);
  return outcome;
}

const agentRow = (fields = {}) => ({
  [`agents/agent:${AGENT_ID}`]: record("ag1", {
    agent_token: AGENT_TOKEN, owner_ref: OWNER, paired: true, ...fields,
  }),
  "agents/ag1": record("ag1", { owner_ref: OWNER, paired: true, ...fields }),
});

const good = { "X-Anticipy-Agent-ID": AGENT_ID, "X-Anticipy-Agent-Token": AGENT_TOKEN };

// ---------------------------------------------------------------------------
// 1. A VALID credential still does everything it was always allowed to do.
//    If this half breaks, the browser arm is dead and the fix is worse than
//    the bug.
// ---------------------------------------------------------------------------
check("a paired browser may still heartbeat its own agent row",
  request({ method: "PATCH", path: "/api/collections/agents/records/ag1",
            headers: good, body: { last_seen: "2026-08-24 10:00:00.000Z",
                                   browser: "Chrome/140 ext/0.4.0" },
            rows: agentRow() }) === "next");

check("a paired browser may still rotate its own token on its own row",
  request({ method: "PATCH", path: "/api/collections/agents/records/ag1",
            headers: good, body: { agent_token: "z".repeat(48) },
            rows: agentRow() }) === "next");

check("a paired browser may still list its owner's jobs",
  request({ method: "GET", path: "/api/collections/jobs/records",
            query: `filter=owner_ref="${OWNER}"`,
            headers: good, rows: agentRow() }) === "next");

check("a paired browser may still read one of its owner's jobs",
  request({ method: "GET", path: "/api/collections/jobs/records/job1",
            headers: good,
            rows: { ...agentRow(), "jobs/job1": record("job1", { owner_ref: OWNER }) } })
  === "next");

// The valid path's OWN refusal must stay distinct from the new one, or a real
// browser reaching too far would be reported to the client as a bad credential
// and every install would look revoked.
const overreach = request({ method: "GET", path: "/api/collections/owner_profile/records",
                            headers: good, rows: agentRow() });
check("a valid credential reaching too far is still refused as a record "
  + "violation, not as a bad credential",
  overreach?.status === 403
  && overreach.error === "agent is not allowed to access that record");

check("a valid credential is never logged as unrecognized",
  !guard.logs.some((l) => l.includes("unrecognized")));

// ---------------------------------------------------------------------------
// 2. THE FAIL-OPEN. A credential presented and not resolvable must be refused,
//    and specifically must NOT land on the anonymous surface below.
//
//    Each shape here is one the tokenless bootstrap ALLOWS, so before the fix
//    every one of them answered "next" to a caller holding a wrong token.
// ---------------------------------------------------------------------------
const bad = { "X-Anticipy-Agent-ID": AGENT_ID, "X-Anticipy-Agent-Token": "c".repeat(48) };

const ANONYMOUS_SURFACE = [
  ["heartbeat a paired agent row",
    { method: "PATCH", path: "/api/collections/agents/records/ag1",
      body: { last_seen: "2026-08-24 10:00:00.000Z", browser: "Chrome/140" },
      rows: { "agents/ag1": record("ag1", { paired: true }) } }],
  ["self-register a fresh agent",
    { method: "POST", path: "/api/collections/agents/records",
      body: { browser: "Chrome/140", last_seen: "2026-08-24 10:00:00.000Z" } }],
  ["look an agent up by its pair code",
    { method: "GET", path: "/api/collections/agents/records",
      query: 'filter=pair_code="123456"' }],
  ["claim an unpaired agent row",
    { method: "PATCH", path: "/api/collections/agents/records/ag1",
      body: { owner: "uuid-from-the-phone", paired: true },
      rows: { "agents/ag1": record("ag1", { paired: false }) } }],
  ["look a pendant up by its pair code",
    { method: "GET", path: "/api/collections/pendants/records",
      query: 'filter=pair_code="123456"' }],
];

for (const [what, shape] of ANONYMOUS_SURFACE) {
  const out = request({ ...shape, headers: bad });
  check(`a token that resolves to no agent may not ${what}`,
    out?.status === 403 && out.error === REFUSAL);
}

// The same request under a valid credential is a different refusal, which is
// what makes the failure diagnosable from the client instead of looking like
// the generic lock.
const genericLock = request({ method: "POST", path: "/api/collections/agents/records",
                             headers: good, body: {}, rows: agentRow() });
check("the new body is distinct from every other refusal on the ladder",
  genericLock?.error === "agent is not allowed to access that record"
  && REFUSAL !== "forbidden"
  && REFUSAL !== "record belongs to a different owner"
  && REFUSAL !== "account is not allowed to access that collection");

// A lookup that returns nothing WITHOUT throwing. PocketBase throws on no
// rows, so this shape is the hook's own defensive `if (agent)` being driven —
// and it fell through exactly the same way.
{
  const out = request({ method: "PATCH", path: "/api/collections/agents/records/ag1",
                        headers: bad, lookup: "empty",
                        body: { last_seen: "now" },
                        rows: { "agents/ag1": record("ag1", { paired: true }) } });
  check("a lookup that returns nothing without throwing is refused too",
    out?.status === 403 && out.error === REFUSAL);
}

// An infrastructure failure is NOT a proven-bad credential. It fails closed
// anyway: a guard that opens when the database hiccups can be opened by making
// the database hiccup.
{
  const out = request({ method: "PATCH", path: "/api/collections/agents/records/ag1",
                        headers: good, lookup: "throw",
                        body: { last_seen: "now" },
                        rows: { "agents/ag1": record("ag1", { paired: true }) } });
  check("a lookup that THROWS fails closed rather than falling through",
    out?.status === 403 && out.error === REFUSAL);
}

// An id with a token shorter than the column's minimum, and an id with no
// token at all. Neither can ever match a row, so both are the same failed
// lookup — and both used to be handed the anonymous surface.
for (const [what, headers] of [
  ["a token shorter than the column minimum", { ...good, "X-Anticipy-Agent-Token": "a".repeat(39) }],
  ["an empty token", { "X-Anticipy-Agent-ID": AGENT_ID, "X-Anticipy-Agent-Token": "" }],
  ["no token header at all", { "X-Anticipy-Agent-ID": AGENT_ID }],
]) {
  const out = request({ method: "PATCH", path: "/api/collections/agents/records/ag1",
                        headers, body: { last_seen: "now" },
                        rows: { "agents/ag1": record("ag1", { paired: true }) } });
  check(`an agent id presented with ${what} is refused, not downgraded to `
    + `anonymous`, out?.status === 403 && out.error === REFUSAL);
}

// A refusal that says nothing in the log is how a revoked extension in the
// field goes on looking like an anonymous client.
check("the refusal is loud: the agent id it could not resolve is logged",
  guard.logs.some((l) => l.startsWith("guard: unrecognized agent credential")
    && l.includes(AGENT_ID)));
check("the token is never written to the log",
  !guard.logs.some((l) => l.includes(AGENT_TOKEN) || l.includes("c".repeat(48))));

// Two identities, one of them broken, is still a refusal. Nothing in this tree
// sends both (the iPhone app sends no agent headers at all), and a caller that
// does is not entitled to have the broken half quietly ignored.
{
  const out = request({ method: "GET", path: "/api/collections/jobs/records",
                        query: `filter=owner_ref="${OWNER}"`,
                        headers: bad, auth: record(OWNER, {}) });
  check("a signed-in account presenting a broken agent credential is refused "
    + "rather than silently downgraded to its account rights",
    out?.status === 403 && out.error === REFUSAL);
}

// ---------------------------------------------------------------------------
// 3. NO AGENT HEADERS AT ALL. This is every fresh install on its first run,
//    and it must be untouched. If this section goes red, nobody can pair.
// ---------------------------------------------------------------------------
for (const [what, shape] of ANONYMOUS_SURFACE) {
  check(`a caller with no agent headers may still ${what} — the pairing `
    + `bootstrap is unchanged`, request(shape) === "next");
}

check("the bootstrap's own refusals still fire: a claim may not name an owner_ref",
  request({ method: "PATCH", path: "/api/collections/agents/records/ag1",
            body: { owner: "uuid-from-the-phone", owner_ref: "victim_account", paired: true },
            rows: { "agents/ag1": record("ag1", { paired: false }) } })?.error
  === "pair from the signed-in app");

check("the bootstrap's own refusals still fire: a pair-code filter may not be "
  + "appended to",
  request({ method: "GET", path: "/api/collections/agents/records",
            query: 'filter=pair_code="000000" || id!=""&perPage=500' })?.error
  === "forbidden");

check("the bootstrap's own refusals still fire: an agent may not be born paired",
  request({ method: "POST", path: "/api/collections/agents/records",
            body: { paired: true, owner: "victim" } })?.error === "forbidden");

check("a tokenless caller reaching a collection outside the bootstrap is still "
  + "the generic lock",
  request({ method: "GET", path: "/api/collections/owner_profile/records" })?.error
  === "forbidden");

// ---------------------------------------------------------------------------
// 4. The paths above and below the agent branch, re-proved in the same run.
//    Hoisting or widening a branch in this ladder is exactly the edit that
//    quietly closes a door somewhere else — the ordering IS the behaviour.
// ---------------------------------------------------------------------------
check("the shared service token still short-circuits first, even when the "
  + "request also carries a broken agent credential",
  request({ method: "GET", path: "/api/collections/anything/records",
            headers: { ...bad, "X-Anticipy-Token": SERVICE_TOKEN } }) === "next");

check("with no service token configured the guard is inert, broken agent "
  + "credential and all",
  (() => {
    const open = load(src.replace('$os.getenv("ANTICIPY_SERVICE_TOKEN")', '""'));
    return request({ handler: open.handler, method: "GET",
                     path: "/api/collections/owner_profile/records",
                     headers: bad }) === "next";
  })());

check("owners auth endpoints are still reachable",
  request({ method: "POST",
            path: "/api/collections/owners/auth-with-password" }) === "next");

check("signing up is still reachable",
  request({ method: "POST", path: "/api/collections/owners/records",
            body: { email: "a@b.c" } }) === "next");

check("a superuser session is still allowed before the e.auth branch",
  request({ method: "POST", path: "/api/collections/_superusers/auth-refresh",
            auth: record("su000000000000", {}), superuser: true }) === "next");

check("superuser login itself is still reachable with no session",
  request({ method: "POST",
            path: "/api/collections/_superusers/auth-with-password" }) === "next");

check("a signed-in account with no agent headers may still list its own jobs",
  request({ method: "GET", path: "/api/collections/jobs/records",
            query: `filter=owner_ref="${OWNER}"`,
            auth: record(OWNER, {}) }) === "next");

check("a signed-in account still cannot list another account's jobs",
  request({ method: "GET", path: "/api/collections/jobs/records",
            query: 'filter=owner_ref="someone-else"',
            auth: record(OWNER, {}) })?.status === 403);

// The service-token short circuit must stay ABOVE the agent branch or the
// worker's own requests would start being judged as agent credentials.
{
  const code = src.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
  const serviceAt = code.indexOf('e.request.header.get("X-Anticipy-Token")');
  const agentAt = code.indexOf('e.request.header.get("X-Anticipy-Agent-ID")');
  const superuserAt = code.indexOf("e.hasSuperuserAuth()");
  const authAt = code.indexOf("if (e.auth)");
  check("the ladder's load-bearing order still holds: service token, then "
    + "agent, then superuser, then e.auth",
    serviceAt > 0 && agentAt > serviceAt && superuserAt > agentAt
    && authAt > superuserAt);
}

// ---------------------------------------------------------------------------
// 5. DOES THIS SUITE ACTUALLY BITE? Put the original defect back — the branch
//    entered on `agentId && agentToken.length >= 40` with nothing after the
//    `if (agent)` block — and require the fall-through to be ALLOWED under it.
//    A suite that passes against the broken file proves nothing.
// ---------------------------------------------------------------------------
{
  const rebroken = src
    .replace("\n  if (agentId) {\n", "\n  if (agentId && agentToken.length >= 40) {\n")
    .replace(/\n *console\.log\("guard: unrecognized agent credential[^\n]*\n *return e\.json\(403, \{ error: "agent credential is not recognized" \}\);/,
      "");
  check("the re-broken fixture really is different from the shipped file",
    rebroken !== src && !rebroken.includes("agent credential is not recognized")
    && rebroken.includes("if (agentId && agentToken.length >= 40) {"));

  const old = load(rebroken);
  const fellThrough = request({ handler: old.handler, method: "PATCH",
    path: "/api/collections/agents/records/ag1", headers: bad,
    body: { last_seen: "2026-08-24 10:00:00.000Z", browser: "Chrome/140" },
    rows: { "agents/ag1": record("ag1", { paired: true }) } });
  check("the ORIGINAL bug is reproduced by this harness: a wrong token used to "
    + "reach the anonymous heartbeat", fellThrough === "next");

  const oldRegister = request({ handler: old.handler, method: "POST",
    path: "/api/collections/agents/records", headers: bad,
    body: { browser: "Chrome/140" } });
  check("the ORIGINAL bug is reproduced for self-registration too",
    oldRegister === "next");
}

if (failures) {
  console.error(`test_guard_agent_credential: ${failures} failed`);
  process.exit(1);
}
console.log("test_guard_agent_credential: all passed");
