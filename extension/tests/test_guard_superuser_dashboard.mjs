// The data-API guard, driven as real code rather than read as text.
//
// The bug this pins: in PocketBase 0.30.4 `e.auth` is filled for ANY auth
// record, superusers included, so the guard's owner branch (`if (e.auth)`)
// swallowed superuser sessions and refused every path outside its
// six-collection regex — with the superuser allowance sitting BELOW it, dead.
// The dashboard's first call after a successful login is auth-refresh, which
// is exactly such a path, so the Admin UI got "account is not allowed to
// access that collection", read it as an invalid session, and threw the person
// back to the login screen. Creating the superuser did not help and could not.
//
// The rest of the file is the reason this is a behavioural suite and not a
// grep: hoisting an allowance is precisely the kind of edit that quietly opens
// a door somewhere else, so the owner-scoping and tokenless-pairing rules are
// re-proved against the same code in the same run.
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

const record = (id, fields) => ({
  id,
  getString: (f) => String(fields[f] ?? ""),
  getBool: (f) => fields[f] === true,
});

// Load the hook once and keep the handler routerUse() registers.
let handler = null;
{
  const globals = {
    routerUse: (fn) => { handler = fn; },
    $os: { getenv: (k) => (k === "ANTICIPY_SERVICE_TOKEN" ? SERVICE_TOKEN : "") },
  };
  const names = Object.keys(globals);
  new Function(...names, src)(...names.map((n) => globals[n]));
}
check("the guard registers a router middleware", typeof handler === "function");

// One request through the real hook. Returns what the hook decided:
// "next" (allowed through to PocketBase) or {status, error}.
function request({ method, path, query = "", headers = {}, body = {},
                   auth = null, superuser = false, rows = {} }) {
  const params = new URLSearchParams(query);
  let outcome = null;
  const e = {
    auth,
    hasSuperuserAuth: () => superuser,
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
      findRecordById: (collection, id) => {
        const rec = rows[`${collection}/${id}`];
        if (!rec) throw new Error("not found");
        return rec;
      },
      findFirstRecordByFilter: (collection, _filter, params2) => {
        const rec = rows[`${collection}/agent:${params2.id}`];
        if (!rec || rec.getString("agent_token") !== params2.token) {
          throw new Error("not found");
        }
        return rec;
      },
    },
  };
  handler(e);
  return outcome;
}

const superuserSession = {
  auth: record("su000000000000", { }),
  superuser: true,
};

// ---- the finding ----
check("a superuser's auth-refresh is not refused as a collection violation",
  request({ method: "POST", path: "/api/collections/_superusers/auth-refresh",
            ...superuserSession }) === "next");

check("a superuser may browse a collection the owner regex does not list",
  request({ method: "GET", path: "/api/collections/password_resets/records",
            ...superuserSession }) === "next");

check("a superuser may read a collection's own schema endpoint",
  request({ method: "GET", path: "/api/collections/jobs", ...superuserSession }) === "next");

check("a superuser is not owner-scoped out of another account's job",
  request({ method: "GET", path: "/api/collections/jobs/records/job1",
            rows: { "jobs/job1": record("job1", { owner_ref: "someone-else" }) },
            ...superuserSession }) === "next");

// Superuser LOGIN carries no auth at all, and must still reach PocketBase.
check("superuser login itself is still reachable with no session",
  request({ method: "POST",
            path: "/api/collections/_superusers/auth-with-password" }) === "next");

// ---- what the hoist must NOT have opened ----
const owner = { auth: record("owner_abc123456", {}) };

check("an ordinary signed-in account still cannot reach _superusers",
  request({ method: "GET", path: "/api/collections/_superusers/records",
            ...owner })?.status === 403);

check("an ordinary signed-in account still cannot reach an unlisted collection",
  request({ method: "GET", path: "/api/collections/password_resets/records",
            ...owner })?.status === 403);

check("an account cannot list another owner's jobs",
  request({ method: "GET", path: "/api/collections/jobs/records",
            query: 'filter=owner_ref="someone-else"', ...owner })?.status === 403);

check("an account can list its own jobs",
  request({ method: "GET", path: "/api/collections/jobs/records",
            query: `filter=owner_ref="${owner.auth.id}"`, ...owner }) === "next");

check("a filter that ORs the owner scope back open is refused",
  request({ method: "GET", path: "/api/collections/jobs/records",
            query: `filter=owner_ref="${owner.auth.id}" || id!=""`,
            ...owner })?.status === 403);

// ---- the tokenless pairing bootstrap, unchanged by the hoist ----
check("an anonymous claim may not name an owner_ref",
  request({ method: "PATCH", path: "/api/collections/agents/records/ag1",
            body: { owner: "uuid-from-the-phone", owner_ref: "victim_account", paired: true },
            rows: { "agents/ag1": record("ag1", { paired: false }) } })?.status === 403);

check("an anonymous claim of an unpaired record still works",
  request({ method: "PATCH", path: "/api/collections/agents/records/ag1",
            body: { owner: "uuid-from-the-phone", paired: true },
            rows: { "agents/ag1": record("ag1", { paired: false }) } }) === "next");

check("an anonymous pair-code lookup may not append to the filter",
  request({ method: "GET", path: "/api/collections/agents/records",
            query: 'filter=pair_code="000000" || id!=""&perPage=500' })?.status === 403);

check("the shared service token still opens everything",
  request({ method: "GET", path: "/api/collections/anything/records",
            headers: { "X-Anticipy-Token": SERVICE_TOKEN } }) === "next");

// The ordering IS the fix, so assert it structurally too: a future edit that
// moves the owner branch back above the superuser allowance relocks the
// dashboard, and the behavioural checks above would still pass if someone
// "fixed" it by widening the collection regex instead.
// Comments stripped first: this file explains the bug by quoting the very
// lines being ordered, and a positional check that matched prose would report
// the opposite of the truth.
const code = src.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
const superuserAt = code.indexOf("e.hasSuperuserAuth()");
const ownerBranchAt = code.indexOf("if (e.auth)");
check("the superuser allowance is evaluated before the owner branch",
  superuserAt > 0 && ownerBranchAt > 0 && superuserAt < ownerBranchAt);

if (failures) { console.error(`test_guard_superuser_dashboard: ${failures} failed`); process.exit(1); }
console.log("test_guard_superuser_dashboard: all passed");
