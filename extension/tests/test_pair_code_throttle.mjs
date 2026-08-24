// Pair codes are six digits and, until this suite existed, nobody counted the
// guesses.
//
// The attack, in the words of the test that already documented it
// (tests/test_pairing_claim_guard.py:26-32): a stranger walks the six-digit
// space against the anonymous pairing bootstrap, reads a real agent row off a
// hit, and claims somebody else's browser against their own account. A million
// codes sounds like a lot until you notice that a script asking ten times a
// second gets through all of them in a day, and that the two defences the
// guard already had — an anchored whole-filter match and a perPage cap — stop
// one request returning the whole table but cost an attacker nothing per
// attempt. guard.pb.js said so in its own comments ("six digits, no rate
// limit") for two weeks before anything counted.
//
// Driven as real code, not read as text, for the same reason
// test_guard_superuser_dashboard.mjs is: a throttle is a thing that must
// REFUSE the eleventh attempt and STILL PAIR the first, and only running it
// proves both. The regressions that share the branch — the anchored filter,
// the perPage cap, the service token bypass — are re-proved in the same run,
// because a new refusal in the middle of that branch is exactly the kind of
// edit that quietly relocks a door somewhere else.
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
const WINDOW_MS = 10 * 60 * 1000;

// ---------------------------------------------------------------------------
// The stand-ins.
// ---------------------------------------------------------------------------
// `e.app.store()` is PocketBase's own app-wide key/value store: one instance
// shared by every isolated hook runtime, which is why a counter can live in it
// at all. Probed against a real pocketbase 0.30.4 before the hook was written
// (set in one request, read in the next, getAll/remove present), and stood in
// for here so the ceiling can be crossed in milliseconds.
const makeStore = () => {
  const kv = new Map();
  return {
    kv,
    get: (k) => (kv.has(k) ? kv.get(k) : null),
    set: (k, v) => { kv.set(k, v); },
    getAll: () => Object.fromEntries(kv),
    remove: (k) => { kv.delete(k); },
    has: (k) => kv.has(k),
  };
};

// A clock the test owns. The hook reads Date.now() for its window, and a
// window that can only be crossed by sleeping ten minutes is a window nobody
// tests. `Date` is passed in as a global to the hook's own function scope, so
// this shadows it there and nowhere else.
let clock = Date.parse("2026-08-24T12:00:00.000Z");
class TestDate extends Date {
  static now() { return clock; }
}

const record = (id, fields) => ({
  id,
  getString: (f) => String(fields[f] ?? ""),
  getBool: (f) => fields[f] === true,
});

// Load the hook once and keep the middleware routerUse() registers.
let handler = null;
{
  const globals = {
    routerUse: (fn) => { handler = fn; },
    $os: { getenv: (k) => (k === "ANTICIPY_SERVICE_TOKEN" ? SERVICE_TOKEN : "") },
    Date: TestDate,
    console: { log: () => {} },
  };
  const names = Object.keys(globals);
  new Function(...names, src)(...names.map((n) => globals[n]));
}
check("the guard registers a router middleware", typeof handler === "function");

// One request through the real hook. Returns what the hook decided: "next"
// (allowed through to PocketBase, which is what a MISS must still be — the
// phone needs the empty list to say "that code didn't match") or
// {status, error}.
//
// `codes` is the agents/pendants table as far as a pair-code lookup can see
// it: code -> record.
function request({ method, path, query = "", headers = {}, body = {},
                   auth = null, superuser = false, rows = {}, codes = {},
                   ip = "203.0.113.7", store = sharedStore }) {
  const params = new URLSearchParams(query);
  let outcome = null;
  const e = {
    auth,
    hasSuperuserAuth: () => superuser,
    realIP: () => ip,
    remoteIP: () => ip,
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
      store: () => {
        if (!store) throw new TypeError("store is not a function");
        return store;
      },
      findRecordById: (collection, id) => {
        const rec = rows[`${collection}/${id}`];
        if (!rec) throw new Error("not found");
        return rec;
      },
      findFirstRecordByFilter: (collection, filter, args) => {
        if (filter.indexOf("pair_code") === 0) {
          const rec = codes[`${collection}/${args.code}`];
          if (!rec) throw new Error("not found");
          return rec;
        }
        const rec = rows[`${collection}/agent:${args.id}`];
        if (!rec || rec.getString("agent_token") !== args.token) {
          throw new Error("not found");
        }
        return rec;
      },
    },
  };
  handler(e);
  return outcome;
}

let sharedStore = makeStore();
const fresh = () => { sharedStore = makeStore(); };

// The table every lookup below sees: one code waiting to be claimed, one code
// whose browser is already somebody's.
const CODES = {
  "agents/314159": record("ag_live", { pair_code: "314159", paired: false }),
  "agents/271828": record("ag_taken", { pair_code: "271828", paired: true, owner_ref: "victim_account" }),
  "pendants/161803": record("pd_live", { pair_code: "161803", paired: false }),
};
const lookup = (code, extra = {}) => request({
  method: "GET", path: "/api/collections/agents/records",
  query: `filter=pair_code="${code}"`, codes: CODES, ...extra,
});

// ---------------------------------------------------------------------------
// The person pairing must not notice any of this.
// ---------------------------------------------------------------------------
fresh();
check("a first-try anonymous pair-code lookup still goes through",
  lookup("314159") === "next");

check("a pendant pair-code lookup still goes through", request({
  method: "GET", path: "/api/collections/pendants/records",
  query: 'filter=pair_code="161803"', codes: CODES }) === "next");

check("a code that matches nothing still reaches PocketBase, so the phone can "
  + "say \"that code didn't match\" rather than \"I can't reach Anticipy\"",
  lookup("000001") === "next");

// A person mistyping is the ONLY legitimate source of failures, and the phone
// auto-submits at six digits, so one fumble costs one attempt. Two fumbles and
// the right code must still pair.
fresh();
check("two mistypes then the real code still pairs",
  lookup("000002") === "next" && lookup("000003") === "next"
  && lookup("314159") === "next");

// Successes are free, or a busy household pairing several browsers would lock
// itself out of the last one.
fresh();
{
  let ok = true;
  for (let i = 0; i < 30; i++) if (lookup("314159") !== "next") ok = false;
  check("thirty successful pairings from one address spend no budget at all",
    ok && lookup("000004") === "next");
}

// ---------------------------------------------------------------------------
// The finding: an attacker hammering the space is refused.
// ---------------------------------------------------------------------------
fresh();
{
  const statuses = [];
  for (let i = 0; i < 14; i++) statuses.push(lookup(String(500000 + i)));
  const passed = statuses.filter((s) => s === "next").length;
  const refused = statuses.filter((s) => s && s.status === 429).length;
  check("a walk of the code space is refused once the per-address ceiling is "
    + `hit (10 counted, ${refused} refused of 14 tried)`,
    passed === 10 && refused === 4);
  check("the refusal says what happened rather than a bare forbidden",
    statuses[13] && statuses[13].status === 429
    && /too many pair code attempts/.test(statuses[13].error));
  // A locked-out address must not be able to pair either — otherwise the
  // ceiling is a suggestion.
  check("the correct code is refused too once that address is locked out",
    lookup("314159")?.status === 429);
}

// The lockout is scoped, and it ends.
check("another address can still pair while the first one is locked out",
  lookup("314159", { ip: "198.51.100.4" }) === "next");

clock += WINDOW_MS + 1;
check("the locked-out address is served again once the window has passed",
  lookup("314159") === "next");

// ---------------------------------------------------------------------------
// A hit on an already-paired record is a guess, not a pairing.
// ---------------------------------------------------------------------------
// Nothing can re-claim a paired record (both claim paths require paired to be
// false), so the only thing a guesser gets from one is the row: owner id,
// owner_ref, agent_id — the owner_ref that
// tests/test_pairing_claim_guard.py's attack needs. Refusing it costs the
// phone nothing: typing an already-paired code has always ended as a thrown
// error there, because the claim after the lookup is refused.
fresh();
check("a hit on an already-paired record is refused, not returned",
  lookup("271828")?.status === 403);
check("and it is charged as a failed attempt", (() => {
  for (let i = 0; i < 9; i++) lookup("271828");
  // Ten spent on paired hits; the eleventh attempt of any kind is refused.
  return lookup("000005")?.status === 429;
})());

// ---------------------------------------------------------------------------
// The all-callers ceiling: the per-address key is only as good as the address.
// ---------------------------------------------------------------------------
// e.realIP() reads a trusted-proxy header when one is configured, and that
// header is written by the caller. Configure it and per-address buckets become
// free to mint, so a second ceiling counts every failure regardless of who
// claims to be asking. It is also what bounds how many keys this can leave in
// the store.
fresh();
{
  let refusedAt = 0;
  for (let i = 0; i < 200 && !refusedAt; i++) {
    // A fresh "address" every six attempts: under the per-address ceiling
    // every time, so only the all-callers count can stop this.
    const spoofed = `10.0.${Math.floor(i / 6)}.${i % 6}`;
    if (lookup(String(600000 + i), { ip: spoofed })?.status === 429) refusedAt = i + 1;
  }
  check(`spoofed addresses are stopped by the all-callers ceiling `
    + `(refused at attempt ${refusedAt})`, refusedAt === 61);
}

// Bounded memory: the store must not accumulate a key per address forever.
{
  const before = sharedStore.kv.size;
  clock += WINDOW_MS + 1;
  lookup("000006", { ip: "192.0.2.99" });
  const after = sharedStore.kv.size;
  check(`stale per-address buckets are swept when the window rolls `
    + `(${before} keys -> ${after})`, before > 10 && after <= 3);
}

// ---------------------------------------------------------------------------
// Fail closed, loudly, if the counter cannot be reached at all.
// ---------------------------------------------------------------------------
// Serving lookups nobody is counting is the hole this closes. A pairing that
// stops working is reported in minutes; a throttle that silently went missing
// is reported never.
check("with no app store to count in, the lookup is refused rather than "
  + "served uncounted",
  lookup("314159", { store: null })?.status === 503);

// ---------------------------------------------------------------------------
// What the new refusal must NOT have broken.
// ---------------------------------------------------------------------------
fresh();
check("an anonymous pair-code lookup still may not append to the filter",
  request({ method: "GET", path: "/api/collections/agents/records",
            query: 'filter=pair_code="000000" || id!=""&perPage=500',
            codes: CODES })?.status === 403);
check("the appended-filter refusal happens before any counting, so it cannot "
  + "be used to burn a legitimate person's budget either",
  sharedStore.kv.size === 0);

check("perPage is still capped on the pair-code branch",
  request({ method: "GET", path: "/api/collections/agents/records",
            query: 'filter=pair_code="314159"&perPage=51',
            codes: CODES })?.status === 403);
check("a page size a real caller would send is still fine",
  request({ method: "GET", path: "/api/collections/agents/records",
            query: 'filter=pair_code="314159"&perPage=30',
            codes: CODES }) === "next");

check("a filter with no pair_code at all is still refused",
  request({ method: "GET", path: "/api/collections/agents/records",
            query: 'filter=paired=false', codes: CODES })?.status === 403);
check("the owner-id branch below the pair-code one still works",
  request({ method: "GET", path: "/api/collections/agents/records",
            query: 'filter=owner="A1B2C3D4-5E6F-7890"', codes: CODES }) === "next");

check("the shared service token is not throttled — the worker is not a "
  + "stranger",
  (() => {
    for (let i = 0; i < 40; i++) {
      if (request({ method: "GET", path: "/api/collections/agents/records",
                    query: `filter=pair_code="${700000 + i}"`, codes: CODES,
                    headers: { "X-Anticipy-Token": SERVICE_TOKEN } }) !== "next") {
        return false;
      }
    }
    return true;
  })());

// The signed-in branch runs ABOVE the tokenless one and had the same
// unthrottled lookup. Signing up is open (the guard lets anyone create an
// owners record), so an account is not a cost an enumerator would notice.
fresh();
{
  const signedIn = { auth: record("owner_abc123456", {}) };
  const signedInLookup = (code) => request({
    method: "GET", path: "/api/collections/agents/records",
    query: `filter=pair_code="${code}"`, codes: CODES, ...signedIn });
  check("a signed-in account's first pair-code lookup goes through",
    signedInLookup("314159") === "next");
  let refused = 0;
  for (let i = 0; i < 12; i++) if (signedInLookup(String(800000 + i))?.status === 429) refused++;
  check(`a signed-in account walking the space is refused too (${refused} of 12)`,
    refused === 2);
}

// ---------------------------------------------------------------------------
// The ordering that two production incidents paid for.
// ---------------------------------------------------------------------------
// Adding a branch in the middle of this file is exactly the edit that reorders
// something by accident, so the two orderings the comments in guard.pb.js call
// load-bearing are asserted structurally as well. Comments are stripped first:
// this file and that one both quote the very lines being ordered.
const code = src.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
const superuserAt = code.indexOf("e.hasSuperuserAuth()");
const ownerBranchAt = code.indexOf("if (e.auth)");
check("the superuser allowance is still evaluated before the owner branch",
  superuserAt > 0 && ownerBranchAt > 0 && superuserAt < ownerBranchAt);

const pairCodeAt = code.lastIndexOf('pair_code\\s*=\\s*"(\\d{6})"');
const ownerFilterAt = code.lastIndexOf('owner\\s*=\\s*"[A-Za-z0-9._-]{8,64}"');
check("the pair-code filter is still checked before the owner-id filter in "
  + "the tokenless branch",
  pairCodeAt > 0 && ownerFilterAt > 0 && pairCodeAt < ownerFilterAt);

// The anchors are the 2026-08-03 incident. A capture group was added to them so
// the counter can see the digits; nothing else about them may drift.
const anchored = src.match(/\/\^\\s\*pair_code\\s\*=\\s\*"\(\\d\{6\}\)"\\s\*\$\//g) || [];
check("both pair-code filters are still anchored whole-filter matches",
  anchored.length === 2);

if (failures) { console.error(`test_pair_code_throttle: ${failures} failed`); process.exit(1); }
console.log("test_pair_code_throttle: all passed");
