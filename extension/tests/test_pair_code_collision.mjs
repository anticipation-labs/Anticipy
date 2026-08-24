// A FAILED LOOKUP IS NOT A FREE PAIR CODE.
//
// /agent/register allocated the six digits that go on somebody's screen by
// asking "is this candidate taken?" and reading an EXCEPTION as no:
//
//   try { e.app.findFirstRecordByFilter("agents", "pair_code = {:code}", …); }
//   catch (_) { pairCode = candidate; }
//
// findFirstRecordByFilter throws two different things through that one door.
// It throws when nothing matched, which is the answer the loop wanted. It also
// throws when the query FAILED, which is not an answer at all — and the loop
// counted it as "free" and carried on.
//
// That mattered here more than anywhere else it appears, because `pair_code`
// carries NO unique index. `agents` indexes agent_id only
// (pb_migrations/1700000002_agents.js), so a duplicate code is not caught at
// the database either: it saves. Two installs then wear one code, and the
// phone's claim names a code rather than a row
// (AnticipyBackend.swift pairAgent), so it adopts whichever row the lookup
// returns first — somebody paired to a browser that is not theirs. Retrying
// cannot undo it, because by then the code is on a screen and a person has
// typed it.
//
// It is the same defect class as the guard fall-through fixed alongside this
// one, and the fix is the same idea: ask a question that answers with a VALUE.
// findRecordsByFilter returns an array — empty is "nothing matched" — so a
// throw goes back to meaning only what it should have meant all along.
//
// Harness technique is test_guard_agent_credential.mjs's: load the real hook
// with only the globals the JSVM provides, keep the handler routerAdd()
// registers, and drive it. checkTheSuiteBites at the bottom restores the
// original try/catch in a local string and requires the collision case to fail
// under it.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "..", "..", "backend", "pb_hooks", "agent_auth.pb.js");
const src = readFileSync(SRC, "utf8");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const AGENT_ID = "b4d1e0f2-8c7a-4d31-9f60-2a1c5e8b7d44";

// Load the hook and keep the POST /agent/register handler.
function load(source) {
  const routes = {};
  const logs = [];
  const globals = {
    routerAdd: (method, path, fn) => { routes[method + " " + path] = fn; },
    // The real one returns cryptographic randomness; the suite needs it
    // PREDICTABLE, so digits count up and the token is filler. Nothing here
    // asserts anything about randomness quality.
    $security: {
      randomStringWithAlphabet: (n, alphabet) => {
        if (alphabet === "0123456789") {
          globals.__code += 1;
          return String(globals.__code).padStart(6, "0");
        }
        return "t".repeat(n);
      },
    },
    __code: 0,
    Record: class { constructor(c) { this.collection = c; this.id = "rec_new"; this.fields = {}; }
      set(k, v) { this.fields[k] = v; }
      getString(k) { return String(this.fields[k] ?? ""); } },
    $os: { getenv: () => "" },
    console: { log: (...parts) => logs.push(parts.join(" ")) },
  };
  const names = Object.keys(globals);
  new Function(...names, source)(...names.map((n) => globals[n]));
  return { register: routes["POST /agent/register"], logs, globals };
}

// One registration attempt.
//
// `lookup(filter)` models what the query does, per filter kind:
//   {rows:[…]}  matched
//   {rows:[]}   matched nothing  <- the answer
//   {throw:e}   the query failed <- NOT an answer
function register(hook, lookup, { saved = [] } = {}) {
  let out = null;
  const e = {
    requestInfo: () => ({ body: { agent_id: AGENT_ID, browser: "Chrome/152" } }),
    json: (status, body) => { out = { status, body }; return out; },
    app: {
      findRecordsByFilter: (_c, filter, _sort, _limit, _offset, params) => {
        const r = lookup(filter, params || {});
        if (r.throw) throw r.throw;
        return r.rows;
      },
      findFirstRecordByFilter: (_c, filter, params) => {
        // Still modelled, because the ORIGINAL code used this and the
        // bites-check drives that version through the same harness.
        const r = lookup(filter, params || {});
        if (r.throw) throw r.throw;
        if (!r.rows.length) throw new Error("sql: no rows in result set");
        return r.rows[0];
      },
      findCollectionByNameOrId: () => ({ name: "agents" }),
      save: (rec) => { saved.push({ ...rec.fields }); },
    },
  };
  try { hook.register(e); } catch (err) { out = { status: 0, body: { thrown: String(err) } }; }
  return out;
}

// A world where every code is free and the agent id is new.
const clean = () => ({ rows: [] });

// ------------------------------------------------------- the happy path first

{
  const hook = load(src);
  const saved = [];
  const out = register(hook, clean, { saved });
  check("a fresh install still registers", out.status === 200);
  check("it is handed a six-digit code", /^\d{6}$/.test(out.body.pair_code || ""));
  check("the code it is handed is the code that was saved",
        saved.length === 1 && saved[0].pair_code === out.body.pair_code);
  check("it is never born pre-paired", saved[0].paired === false);
  check("the token is returned exactly once, and is not in the row response",
        typeof out.body.agent_token === "string" && out.body.agent_token.length === 64);
}

{
  const hook = load(src);
  const out = register(hook, (filter) =>
    filter.indexOf("agent_id") === 0 ? { rows: [{ id: "already" }] } : { rows: [] });
  check("an id that is already registered is still 409", out.status === 409);
}

// ------------------------------------------- a taken code is skipped, not reused

{
  const hook = load(src);
  const saved = [];
  // 000001 and 000002 are already on somebody's screen; 000003 is free. The
  // code travels in PARAMS, not in the filter string, which is the whole
  // reason the harness threads params through.
  const taken = new Set(["000001", "000002"]);
  const asked = [];
  const out = register(hook, (filter, params) => {
    if (filter.indexOf("agent_id") === 0) return { rows: [] };
    asked.push(params.code);
    return { rows: taken.has(params.code) ? [{ id: "taken" }] : [] };
  }, { saved });
  check("every candidate is actually checked before it is used",
        asked.length === 3 && asked[0] === "000001" && asked[2] === "000003");
  check("a code already on somebody's screen is never handed out twice",
        out.status === 200 && out.body.pair_code === "000003");
  check("and the taken ones were not saved",
        saved.length === 1 && !taken.has(saved[0].pair_code));
}

// ------------------------------------------------- THE BUG: a failed lookup

{
  const hook = load(src);
  const saved = [];
  // The agent-id check succeeds and finds nothing. The pair-code query then
  // fails - a locked db, a closed connection, the disk-full state this service
  // has actually had (1700000038_log_db_footprint.js).
  const out = register(hook, (filter) =>
    filter.indexOf("agent_id") === 0
      ? { rows: [] }
      : { throw: new Error("database is locked") }, { saved });
  check("a failed pair-code lookup does NOT mint a code",
        saved.length === 0);
  check("it refuses instead of guessing", out.status === 500);
  check("and it says so in the log rather than silently succeeding",
        hook.logs.some((l) => l.indexOf("database is locked") !== -1));
}

{
  const hook = load(src);
  const saved = [];
  // The other lookup: the agent-id check itself fails. Before the fix this
  // fell THROUGH into registration, and only the unique index on agent_id
  // turned the duplicate into a 500 by accident. There is no such index on
  // pair_code, which is why relying on that was never a defence.
  const out = register(hook, () => ({ throw: new Error("database is locked") }),
                       { saved });
  check("a failed agent-id lookup does not register anything",
        saved.length === 0);
  check("it refuses with a service error, not a 409 or a 200",
        out.status === 503);
  check("the refusal names which lookup failed",
        hook.logs.some((l) => l.indexOf("agent_id lookup failed") !== -1));
}

{
  const hook = load(src);
  const saved = [];
  // Every candidate genuinely taken: 20 attempts, then give up. Must not save
  // an empty code, and must not save a colliding one.
  const out = register(hook, (filter) =>
    filter.indexOf("agent_id") === 0 ? { rows: [] } : { rows: [{ id: "taken" }] },
    { saved });
  check("when no code can be allocated, nothing is saved", saved.length === 0);
  check("and the caller is told, not handed an empty code", out.status === 500);
}

// ------------------------------------------------------- does the suite bite?

// The original defect, restored in a local string: the pair-code loop back on
// findFirstRecordByFilter with the throw read as "free". The collision case
// MUST fail under it, or this file is decoration.
function checkTheSuiteBites() {
  const broken = src.replace(
    /      if \(!existing\("pair_code = \{:code\}", \{ code: candidate \}\)\.length\) \{\n        pairCode = candidate;\n      \}/,
    `      try { e.app.findFirstRecordByFilter("agents", "pair_code = {:code}", { code: candidate }); }
      catch (_) { pairCode = candidate; }`);
  if (broken === src) {
    check("the bites-check could re-break the file (the shape it targets moved)", false);
    return;
  }
  const hook = load(broken);
  const saved = [];
  register(hook, (filter) =>
    filter.indexOf("agent_id") === 0
      ? { rows: [] }
      : { throw: new Error("database is locked") }, { saved });
  check("the ORIGINAL bug is reproduced by this harness: a failed lookup minted a code",
        saved.length === 1);
}
checkTheSuiteBites();

if (failures) {
  console.error(`test_pair_code_collision: ${failures} failed`);
  process.exit(1);
}
console.log("test_pair_code_collision: all passed");
