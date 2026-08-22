// "Delete everything on my server", driven as real code — including the scope
// rules of the runtime it actually runs in.
//
// THE BUG THIS EXISTS FOR. On 2026-08-22 POST /me/delete deleted nothing at
// all. `backend/pb_hooks/account_delete.pb.js` declared `const OWNER_TABLES`
// at the top of the file and read it inside the `routerAdd` callback, and the
// PocketBase JSVM gives each handler its OWN execution context — the module
// body's bindings are gone by the time a request arrives. `for (const table of
// OWNER_TABLES)` threw `ReferenceError: OWNER_TABLES is not defined`, which
// PocketBase reports to the caller as a bare 400 "Something went wrong while
// processing your request." The same file also called the global `app.` five
// times where the binding inside a handler is `e.app.`; agent_key.pb.js had
// the identical bare-`app.` mistake at three sites, silently voiding the
// model-call audit trail. Two files, one bug class — so the class is what is
// guarded here, not the instance.
//
// WHY NOTHING CHEAPER CATCHES IT. The route answers 401 without a token and
// 400 without the confirmation, so every probe short of a fully authenticated
// delete-with-confirm passes. It shipped and sat there.
//
// WHY THE HARNESS IS BUILT THE WAY IT IS. A test that loads the hook with
// `new Function(routerAdd, src)` and calls the captured closure would NOT have
// caught this: that closure keeps the module body in its scope chain, so the
// broken code passes. So the handler is re-compiled from its own source in a
// fresh scope, and the app is reachable only as `e.app` — there is no global
// `app` anywhere. `checkHarnessIsFaithful()` at the bottom proves both by
// running the pre-fix pattern through this same loader and requiring it to
// throw.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const hookPath = join(here, "..", "..", "backend", "pb_hooks", "account_delete.pb.js");
const hookSrc = readFileSync(hookPath, "utf8");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// ---------------------------------------------------------------------------
// The loader: a deliberately hostile model of the PocketBase JSVM.
//
// Two properties, both load-bearing:
//   1. The handler is re-compiled from `fn.toString()`, so its scope chain is
//      the bare global scope. Anything the module body declared is invisible,
//      exactly as in the JSVM.
//   2. Nothing is injected as a global except what pb_hooks genuinely provides
//      inside a handler (`Record`). In particular there is no `app`, so a bare
//      `app.findRecordsByFilter(...)` is a ReferenceError here just as it is in
//      production.
// ---------------------------------------------------------------------------
function loadHandler(src, { Record }) {
  const routes = [];
  const globals = { routerAdd: (method, path, fn) => routes.push({ method, path, fn }) };
  const names = Object.keys(globals);
  new Function(...names, src)(...names.map((n) => globals[n]));
  if (routes.length !== 1) throw new Error(`expected 1 route, got ${routes.length}`);
  const r = routes[0];
  // Re-compiled, NOT the captured closure. This is the whole point.
  const fn = new Function("Record", `"use strict"; return (${r.fn.toString()});`)(Record);
  return { method: r.method, path: r.path, fn };
}

// No `app` may exist in the scope a re-compiled handler runs in.
check("the harness leaves no global `app` for a handler to fall back on",
  new Function("return typeof app")() === "undefined" && typeof globalThis.app === "undefined");

// ---------------------------------------------------------------------------
// A fake PocketBase. It knows each collection's COLUMNS, because "which value
// may match which column" is the entire security of this endpoint and a filter
// naming a column that does not exist throws for the whole query in real
// PocketBase — the failure that once left owner_profile behind while the
// response still reported a count.
// ---------------------------------------------------------------------------
const SCHEMA = {
  owners: ["id", "legacy_uuid"],
  jobs: ["owner_ref", "owner"],
  segments: ["owner_ref", "owner"],
  agents: ["owner_ref", "owner"],
  owner_profile: ["owner_ref", "owner_id", "phone", "first_name"],
  pendants: ["owner_ref", "owner"],
  agent_llm_audit: ["owner_ref"],
  agent_audit_sessions: ["owner_ref"],
  events: ["owner_ref", "text"],
  purges: ["owner_ref", "legacy_uuid", "memory_purged", "requested_at"],
};

let nextId = 0;
const mkRow = (collection, data) => ({
  id: `${collection}-${++nextId}`,
  collection,
  data: { ...data },
  getString: (f) => String(data[f] ?? ""),
});

function makeApp({ rows, faults = {} }) {
  const store = new Map(); // collection -> row[]
  for (const [collection, list] of Object.entries(rows)) {
    store.set(collection, list.map((d) => mkRow(collection, d)));
  }
  const saved = [];
  const app = {
    _store: store,
    _saved: saved,
    live: (collection) => (store.get(collection) || []).slice(),
    findRecordsByFilter(collection, filter, _sort, _limit, _offset, params) {
      if (!SCHEMA[collection]) throw new Error(`no such collection: ${collection}`);
      if (faults[collection] === "query") throw new Error(`disk I/O error on ${collection}`);
      const m = /^\s*(\w+)\s*=\s*\{:(\w+)\}\s*$/.exec(String(filter));
      if (!m) throw new Error(`unsupported filter: ${filter}`);
      const [, field, key] = m;
      // Real PocketBase fails the WHOLE query on an unknown column.
      if (!SCHEMA[collection].includes(field)) {
        throw new Error(`sql: no such column: ${collection}.${field}`);
      }
      const want = String((params || {})[key] ?? "");
      if (!want) return [];
      return (store.get(collection) || []).filter((r) => String(r.data[field] ?? "") === want);
    },
    delete(row) {
      if (faults[row.collection] === "delete") {
        throw new Error(`constraint failed on ${row.collection}`);
      }
      const list = store.get(row.collection) || [];
      const i = list.indexOf(row);
      if (i === -1) throw new Error(`record not found in ${row.collection}`);
      list.splice(i, 1);
    },
    findCollectionByNameOrId(name) {
      if (faults[name] === "collection") throw new Error(`missing collection ${name}`);
      if (!SCHEMA[name]) throw new Error(`no such collection: ${name}`);
      return { name };
    },
    save(row) {
      if (faults[row.collection] === "save") throw new Error(`cannot save ${row.collection}`);
      (store.get(row.collection) || store.set(row.collection, []).get(row.collection)).push(row);
      saved.push(row);
    },
  };
  return app;
}

// `new Record(collection)` inside the handler.
function makeRecordCtor() {
  return function Record(collection) {
    const data = {};
    return {
      id: `${collection.name}-new`,
      collection: collection.name,
      data,
      set: (k, v) => { data[k] = v; },
      getString: (f) => String(data[f] ?? ""),
    };
  };
}

const route = loadHandler(hookSrc, { Record: makeRecordCtor() });
check("the hook registers exactly POST /me/delete",
  route.method === "POST" && route.path === "/me/delete" && typeof route.fn === "function");

// ---------------------------------------------------------------------------
// Seed: TWO accounts, so every delete can be checked for blast radius.
// ---------------------------------------------------------------------------
const A = "aaaaaaaaaaaaaaa";              // the caller
const A_LEGACY = "device-uuid-aaaa-0001"; // the phone's pre-account id
const B = "bbbbbbbbbbbbbbb";              // a stranger
const B_LEGACY = "device-uuid-bbbb-0002";

const OWNER_TABLES = [
  "jobs", "segments", "agents", "owner_profile",
  "pendants", "agent_llm_audit", "agent_audit_sessions", "events",
];

// Per-table rows for A, deliberately spread across owner_ref, the account id in
// the legacy column, and the legacy uuid in the legacy column — the three shapes
// the handler is supposed to reach. No row matches two keys, because in real
// PocketBase the second query runs after the first delete and would not see it.
const seedRows = () => ({
  owners: [
    { id: A, legacy_uuid: A_LEGACY },
    { id: B, legacy_uuid: B_LEGACY },
  ],
  jobs: [
    { owner_ref: A }, { owner_ref: A },
    { owner: A }, { owner: A_LEGACY },
    { owner_ref: B }, { owner: B_LEGACY },
  ],
  segments: [{ owner_ref: A }, { owner_ref: B }],
  agents: [{ owner: A_LEGACY }, { owner: B_LEGACY }, { owner_ref: B }],
  owner_profile: [
    { owner_ref: A, first_name: "Real", phone: "+16045550101" },
    { owner_id: A_LEGACY, first_name: "Real", phone: "+16045550101" },
    { owner_ref: B, first_name: "Stranger", phone: "+16045550202" },
  ],
  pendants: [{ owner_ref: A }, { owner_ref: B }],
  agent_llm_audit: [{ owner_ref: A }, { owner_ref: A }, { owner_ref: B }],
  agent_audit_sessions: [{ owner_ref: A }, { owner_ref: B }],
  events: [
    { owner_ref: A, text: "the private sentence" },
    { owner_ref: A }, { owner_ref: A }, { owner_ref: A },
    { owner_ref: B, text: "the stranger's sentence" },
  ],
  purges: [],
});

const EXPECTED_A = {
  jobs: 4, segments: 1, agents: 1, owner_profile: 2,
  pendants: 1, agent_llm_audit: 2, agent_audit_sessions: 1, events: 4,
};

// One request through the real handler.
function request({ auth = null, body = {}, faults = {}, rows = seedRows() } = {}) {
  const app = makeApp({ rows, faults });
  let authRec = null;
  if (auth) {
    authRec = (app.live("owners") || []).find((r) => r.data.id === auth.id) || null;
    if (authRec) {
      authRec.collection = "owners";
      // The token's account row is the ONLY source of legacy_uuid, so the spec
      // for this request decides what the row holds.
      authRec.data.legacy_uuid = String(auth.legacy_uuid ?? "");
    }
  }
  const e = {
    app,
    auth: auth
      ? {
          id: auth.id,
          collection: () => {
            if (auth.collectionThrows) throw new Error("no collection loaded");
            return { name: auth.collection };
          },
          getString: (f) => String((authRec && authRec.data[f]) ?? auth[f] ?? ""),
        }
      : null,
    requestInfo: () => {
      if (body === "unreadable") throw new Error("unparseable body");
      return { body };
    },
    json: (status, payload) => { e._out = { status, payload }; },
    _out: null,
  };
  // e.app.delete(auth) must hit the real owners row.
  if (authRec) {
    const realDelete = app.delete.bind(app);
    app.delete = (row) => realDelete(row === e.auth ? authRec : row);
  }
  // A throw out of the handler is the ORIGINAL bug's shape — PocketBase turns
  // it into a bare 400 that names nothing. Captured rather than allowed to
  // abort the run, so the suite reports which request died and why.
  let thrown = null;
  try { route.fn(e); } catch (err) { thrown = err; }
  // A handler that threw sent nothing. Stand in a status-0 non-response with
  // the shape the payload assertions read, so each of them reports its own
  // failure instead of the first dereference aborting the whole run.
  if (!e._out) e._out = { status: 0, payload: { deleted: {}, failed: [] } };
  return { out: e._out, app, thrown };
}

// ---------------------------------------------------------------------------
// 1. No auth.
// ---------------------------------------------------------------------------
{
  const { out, app } = request({ auth: null, body: { confirm: "delete" } });
  check("no token is 401", out && out.status === 401 && out.payload.ok === false);
  check("no token deletes nothing",
    OWNER_TABLES.every((t) => app.live(t).length === seedRows()[t].length));
  check("no token queues no purge", app._saved.length === 0);
}

// ---------------------------------------------------------------------------
// 2. An auth record that is not an `owners` record. This is the cross-account
//    deletion primitive the file's header documents; it must stay shut.
// ---------------------------------------------------------------------------
for (const collection of ["_superusers", "agents", "pendants", ""]) {
  const { out, app } = request({
    auth: { id: A, collection, legacy_uuid: A_LEGACY },
    body: { confirm: "delete" },
  });
  check(`an auth record from \`${collection || "(none)"}\` is 403`,
    out && out.status === 403 && out.payload.ok === false);
  check(`an auth record from \`${collection || "(none)"}\` deletes nothing`,
    OWNER_TABLES.every((t) => app.live(t).length === seedRows()[t].length)
    && app.live("owners").length === 2 && app._saved.length === 0);
}
{
  // A record whose collection() throws must fail CLOSED, not fall through.
  const { out, app } = request({
    auth: { id: A, collection: "owners", collectionThrows: true, legacy_uuid: A_LEGACY },
    body: { confirm: "delete" },
  });
  check("an auth record whose collection cannot be read is 403, not a wipe",
    out && out.status === 403 && app._saved.length === 0
    && app.live("events").length === seedRows().events.length);
}

// ---------------------------------------------------------------------------
// 3. Missing or wrong confirmation.
// ---------------------------------------------------------------------------
for (const [label, body] of [
  ["no body at all", {}],
  ["the wrong word", { confirm: "yes" }],
  ["a near miss", { confirm: "Delete" }],
  ["an empty string", { confirm: "" }],
  ["a truthy non-string", { confirm: true }],
  ["a body that cannot be read", "unreadable"],
]) {
  const { out, app } = request({ auth: { id: A, collection: "owners" }, body });
  check(`${label} is 400 and says how to confirm`,
    out && out.status === 400 && out.payload.ok === false
    && /confirm/i.test(String(out.payload.message)));
  check(`${label} deletes NOTHING`,
    OWNER_TABLES.every((t) => app.live(t).length === seedRows()[t].length)
    && app.live("owners").length === 2 && app._saved.length === 0);
}

// ---------------------------------------------------------------------------
// 4. The happy path: every table, with counts.
// ---------------------------------------------------------------------------
const happy = request({
  auth: { id: A, collection: "owners", legacy_uuid: A_LEGACY },
  body: { confirm: "delete" },
});
// This is the check the original bug would have tripped first, and it says the
// word the 400 never did: the handler threw, and here is the name it could not
// resolve.
if (happy.thrown) console.error("  handler threw: " + happy.thrown);
check("a confirmed delete reaches the end of the handler without throwing",
  happy.thrown === null);
check("a confirmed delete from an owners token is 200",
  happy.out && happy.out.status === 200 && happy.out.payload.ok === true
  && happy.out.payload.account_deleted === true);

check("the response reports a count for EVERY table in the list",
  happy.out && OWNER_TABLES.every((t) =>
    Object.prototype.hasOwnProperty.call(happy.out.payload.deleted, t))
  && Object.keys(happy.out.payload.deleted).length === OWNER_TABLES.length);

for (const t of OWNER_TABLES) {
  check(`${t}: ${EXPECTED_A[t]} rows deleted and none of the caller's left`,
    happy.out.payload.deleted[t] === EXPECTED_A[t]
    && happy.app.live(t).every((r) =>
      r.data.owner_ref !== A && r.data.owner !== A
      && r.data.owner !== A_LEGACY && r.data.owner_id !== A_LEGACY));
}

// The two the swallowed-throw bug used to leave behind, called out by name.
check("owner_profile is emptied of the caller — the densest PII in the system",
  happy.app.live("owner_profile").every((r) => r.data.first_name !== "Real")
  && happy.out.payload.deleted.owner_profile === 2);
check("events is emptied of the caller — the private sentence is gone",
  happy.app.live("events").every((r) => r.data.text !== "the private sentence"));
check("the account itself is closed", happy.app.live("owners").length === 1
  && happy.app.live("owners")[0].data.id === B);

// ---------------------------------------------------------------------------
// 5. Any failure stops before the purge row and before the account.
// ---------------------------------------------------------------------------
for (const table of OWNER_TABLES) {
  for (const kind of ["query", "delete"]) {
    const { out, app } = request({
      auth: { id: A, collection: "owners", legacy_uuid: A_LEGACY },
      body: { confirm: "delete" },
      faults: { [table]: kind },
    });
    check(`a ${kind} failure on ${table} is 500 and names ${table}`,
      out && out.status === 500 && out.payload.ok === false
      && Array.isArray(out.payload.failed) && out.payload.failed.includes(table));
    check(`a ${kind} failure on ${table} queues NO purge and keeps the account`,
      app._saved.length === 0 && app.live("owners").some((r) => r.data.id === A));
    check(`a ${kind} failure on ${table} still reports what it did delete`,
      out.payload.deleted && typeof out.payload.deleted === "object"
      && Object.keys(out.payload.deleted).length === OWNER_TABLES.length);
  }
}
{
  // The stated rule, restated as one claim: a 500 never says account_deleted.
  const { out } = request({
    auth: { id: A, collection: "owners", legacy_uuid: A_LEGACY },
    body: { confirm: "delete" },
    faults: { events: "query" },
  });
  check("a partial delete never claims the account was deleted",
    out.status === 500 && out.payload.account_deleted !== true && out.payload.ok !== true);
}
{
  // Purge row unwritable: data is gone, but the account must survive so the
  // caller has something to retry with — and it must not report success.
  const { out, app } = request({
    auth: { id: A, collection: "owners", legacy_uuid: A_LEGACY },
    body: { confirm: "delete" },
    faults: { purges: "save" },
  });
  check("an unschedulable purge is 500 and leaves the account to retry with",
    out.status === 500 && out.payload.ok === false
    && app.live("owners").some((r) => r.data.id === A));
}

// ---------------------------------------------------------------------------
// 6. Exactly one purges row, carrying both identifiers.
// ---------------------------------------------------------------------------
{
  const purges = happy.app._saved.filter((r) => r.collection === "purges");
  check("the happy path queues exactly one purges row", purges.length === 1
    && happy.app._saved.length === 1);
  const purge = purges[0] ? purges[0].data : {};
  check("the purge row carries owner_ref and legacy_uuid, unpurged",
    purge.owner_ref === A && purge.legacy_uuid === A_LEGACY
    && purge.memory_purged === false
    && typeof purge.requested_at === "string" && purge.requested_at.length > 0);
}
{
  // An account that never had a pre-migration uuid still gets a purge row; the
  // supervisor keys on owner_ref and legacy_uuid is only the extra directory.
  const { out, app } = request({ auth: { id: A, collection: "owners" }, body: { confirm: "delete" } });
  check("an account with no legacy uuid still deletes and still queues a purge",
    out.status === 200 && app._saved.length === 1
    && app._saved[0].data.owner_ref === A && app._saved[0].data.legacy_uuid === "");
  // Keys become owner_ref=A and owner=A only. An empty legacy value must not
  // become a wildcard: the row keyed by the phone's old uuid is left alone,
  // which is correct — nothing on that token claims it.
  check("with no legacy uuid an empty value sweeps nothing",
    app.live("jobs").length === 3
    && app.live("jobs").some((r) => r.data.owner === A_LEGACY)
    && app.live("jobs").every((r) => r.data.owner_ref !== A && r.data.owner !== A)
    && out.payload.deleted.jobs === 3
    && out.payload.deleted.agents === 0);
}

// ---------------------------------------------------------------------------
// 7. Blast radius: a delete never reaches another account.
// ---------------------------------------------------------------------------
{
  const before = seedRows();
  const survivors = (app, t) =>
    app.live(t).length === before[t].filter((r) =>
      r.owner_ref === B || r.owner === B_LEGACY || r.owner === B || r.owner_id === B_LEGACY).length;
  for (const t of OWNER_TABLES) {
    check(`${t}: the stranger's rows survive the caller's delete`, survivors(happy.app, t));
  }
  check("the stranger's profile and sentence are still there",
    happy.app.live("owner_profile").some((r) => r.data.first_name === "Stranger")
    && happy.app.live("events").some((r) => r.data.text === "the stranger's sentence")
    && happy.app.live("owners").some((r) => r.data.id === B));
}
{
  // The exploit the header describes: `legacy_uuid` is client-writable, so a
  // caller can sign up declaring the VICTIM'S ACCOUNT ID as their legacy uuid.
  // It must never be applied to `owner_ref`.
  const rows = seedRows();
  rows.owners[0].legacy_uuid = B; // A claims B's account id
  const { out, app } = request({
    auth: { id: A, collection: "owners", legacy_uuid: B },
    body: { confirm: "delete" },
    rows,
  });
  check("claiming a stranger's account id as legacy_uuid still returns 200 for the caller",
    out.status === 200);
  check("a claimed legacy_uuid is NEVER matched against owner_ref — the "
    + "stranger's owner_ref rows all survive",
    OWNER_TABLES.every((t) => app.live(t).every((r) => true))
    && app.live("events").some((r) => r.data.owner_ref === B)
    && app.live("owner_profile").some((r) => r.data.owner_ref === B)
    && app.live("segments").some((r) => r.data.owner_ref === B)
    && app.live("agents").some((r) => r.data.owner_ref === B)
    && app.live("pendants").some((r) => r.data.owner_ref === B)
    && app.live("agent_llm_audit").some((r) => r.data.owner_ref === B)
    && app.live("agent_audit_sessions").some((r) => r.data.owner_ref === B)
    && app.live("jobs").some((r) => r.data.owner_ref === B));
  check("the stranger's ACCOUNT survives", app.live("owners").some((r) => r.data.id === B));
  check("the purge row names the caller, not the account they claimed",
    app._saved.length === 1 && app._saved[0].data.owner_ref === A);
}

// ---------------------------------------------------------------------------
// The harness, checked against the bug it exists to catch.
//
// Everything above only means something if this loader really does refuse the
// pre-fix pattern. Both halves of the original defect are reconstructed here in
// miniature and run through the SAME loadHandler(); each must throw a
// ReferenceError. If somebody later "simplifies" the loader into calling the
// captured closure, these two go red and say why.
// ---------------------------------------------------------------------------
function throwsReferenceError(src) {
  let handler;
  try {
    handler = loadHandler(src, { Record: makeRecordCtor() }).fn;
  } catch (err) {
    return err instanceof ReferenceError;
  }
  const e = {
    app: makeApp({ rows: seedRows() }),
    auth: { id: A, collection: () => ({ name: "owners" }), getString: () => A_LEGACY },
    requestInfo: () => ({ body: { confirm: "delete" } }),
    json: () => {},
  };
  try { handler(e); } catch (err) { return err instanceof ReferenceError; }
  return false;
}

check("a top-level const read inside the handler throws, as it does in the JSVM",
  throwsReferenceError(`
    const OWNER_TABLES = [{ name: "events", legacy: null }];
    routerAdd("POST", "/me/delete", (e) => {
      for (const table of OWNER_TABLES) { e.app.findRecordsByFilter(table.name, "owner_ref = {:id}", "", 0, 0, { id: "x" }); }
      return e.json(200, { ok: true });
    });`));

check("a bare `app.` inside the handler throws — there is no global app",
  throwsReferenceError(`
    routerAdd("POST", "/me/delete", (e) => {
      app.findRecordsByFilter("events", "owner_ref = {:id}", "", 0, 0, { id: "x" });
      return e.json(200, { ok: true });
    });`));

check("a top-level FUNCTION called from the handler throws too — the same trap "
  + "with a different shape",
  throwsReferenceError(`
    function tables() { return [{ name: "events", legacy: null }]; }
    routerAdd("POST", "/me/delete", (e) => {
      tables();
      return e.json(200, { ok: true });
    });`));

// And the control: the shipped shape must NOT throw, or the three checks above
// would pass for the wrong reason.
check("the real hook's shape survives the same loader",
  !throwsReferenceError(`
    routerAdd("POST", "/me/delete", (e) => {
      const OWNER_TABLES = [{ name: "events", legacy: null }];
      for (const table of OWNER_TABLES) { e.app.findRecordsByFilter(table.name, "owner_ref = {:id}", "", 0, 0, { id: "x" }); }
      return e.json(200, { ok: true });
    });`));

// The static half, cheap and specific: no `app.` call that is not `e.app.`.
// agent_key.pb.js carried this same defect at three sites, so it is checked
// too — one grep-shaped claim guarding the whole class across both files.
for (const file of ["account_delete.pb.js", "agent_key.pb.js"]) {
  const src = readFileSync(join(here, "..", "..", "backend", "pb_hooks", file), "utf8")
    .split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
  const bare = (src.match(/(^|[^.\w$])app\s*\.\s*(find|save|delete|dao|runInTransaction)/g) || []);
  check(`${file} never calls a bare \`app.\` — the binding inside a handler is e.app`,
    bare.length === 0);
}

if (failures) {
  console.error(`test_account_delete_flow: ${failures} check(s) failed`);
  process.exit(1);
}
console.log("test_account_delete_flow: all passed");
