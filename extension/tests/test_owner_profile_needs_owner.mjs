// A PROFILE WITH NO OWNER IS A PERSON NOBODY CAN LOOK UP — pinned by driving
// the real hook and the real migration as code, offline.
//
// The state this suite exists to prevent recurring: on 2026-08-22 production
// held 10 `owner_profile` rows and 3 of them had `owner_ref = ""`. Every read
// in the product asks for a profile BY ACCOUNT (brain/worker.py
// `_latest_profile` sends `owner_ref="<id>"`; agent_key.pb.js:40 and
// password_reset.pb.js:64 filter `owner_ref = {:ref}`), and an empty relation
// satisfies none of them — so those rows hold a first name, an email, a phone
// number and a birthday that can never be read back, completed, or told about.
// They are not inert either: sms.pb.js:166 routes an inbound text through
// `owner_profile` by phone, `-updated`, LIMIT 3, and all three orphans carry
// the same number as a real person, so they crowd the real row out of that
// window.
//
// Two layers, and the split is the point:
//   - backend/pb_hooks/owner_profile_owner.pb.js refuses the create in the
//     router, which is the only layer that also covers a SUPERUSER (PocketBase
//     skips API rules for them entirely).
//   - backend/pb_migrations/1700000043_owner_profile_needs_owner.js closes the
//     collection's createRule, which is the only layer that survives a hook
//     file being renamed.
// Both are exercised here; both were also run live against pocketbase 0.30.4.
//
// What must KEEP working, because the three live rows hold the only copy of a
// phone number and must be reconcilable rather than deleted: any update that
// does not mention owner_ref, and the adoption in claim_legacy.pb.js:73-84 that
// PATCHes a real owner_ref onto them.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const backend = join(here, "..", "..", "backend");
const hookSrc = readFileSync(
  join(backend, "pb_hooks", "owner_profile_owner.pb.js"), "utf8");
const migrationSrc = readFileSync(
  join(backend, "pb_migrations", "1700000043_owner_profile_needs_owner.js"), "utf8");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// ---- the hook ----
// Loaded with NO `$os` global on purpose. guard.pb.js does nothing at all when
// ANTICIPY_SERVICE_TOKEN is unset, so a hook that gated itself on that env var
// would leave the door open on exactly the deployments that have no guard —
// and would throw a ReferenceError here instead of quietly passing.
let handler = null;
{
  const globals = { routerUse: (fn) => { handler = fn; } };
  const names = Object.keys(globals);
  new Function(...names, hookSrc)(...names.map((n) => globals[n]));
}
check("the hook registers a router middleware", typeof handler === "function");

// One request through the real hook: "next" (on to PocketBase) or {status,error}.
function request({ method, path, body = {} }) {
  let outcome = null;
  const e = {
    request: { method, url: { path }, header: { get: () => "" } },
    requestInfo: () => ({ body }),
    next: () => { outcome = "next"; },
    json: (status, payload) => { outcome = { status, error: payload.error }; },
  };
  handler(e);
  return outcome;
}
const create = (body) => request(
  { method: "POST", path: "/api/collections/owner_profile/records", body });
const update = (body) => request(
  { method: "PATCH", path: "/api/collections/owner_profile/records/prof123456789", body });

const ACCOUNT = "j7harvehogkn1ue";
const refused = (r) => !!r && r.status === 400 && r.error === "owner_profile needs an owner";

// ---- the door that produced the three live orphans ----
// The iPhone sends no owner_ref at all when it has no account id yet
// (app/ios/Anticipy/Backend/AnticipyBackend.swift:223: `if !accountID.isEmpty`).
check("a create with NO owner_ref is refused",
  refused(create({ owner_id: "device-uuid-0001", phone: "+16047245161" })));

check("a create with an EMPTY owner_ref is refused",
  refused(create({ owner_id: "device-uuid-0001", owner_ref: "", phone: "+16047245161" })));

check("a create with a whitespace owner_ref is refused",
  refused(create({ owner_id: "device-uuid-0001", owner_ref: "   " })));

check("a create with an empty ARRAY owner_ref is refused",
  refused(create({ owner_id: "device-uuid-0001", owner_ref: [] })));

// The refusal has to be readable in a client log, because the iOS write path
// reports a bare false and nothing else (AnticipyBackend.swift `upsertOwner`).
check("the refusal names owner_ref and says what to do",
  /owner_ref/.test(String(create({}).error) + " " +
    (() => { let d = ""; const e = {
      request: { method: "POST", url: { path: "/api/collections/owner_profile/records" },
                 header: { get: () => "" } },
      requestInfo: () => ({ body: {} }), next: () => {},
      json: (_s, p) => { d = String(p.detail || ""); } };
      handler(e); return d; })()));

// ---- what must still work ----
check("a create naming a real account still succeeds",
  create({ owner_id: "device-uuid-0001", owner_ref: ACCOUNT,
           first_name: "Real", phone: "+16047245161" }) === "next");

// owner_ref is a maxSelect:1 relation, so PocketBase accepts either form and
// refusing the array would break an honest write to stop a dishonest one.
check("a create naming a real account as a one-element array still succeeds",
  create({ owner_id: "device-uuid-0001", owner_ref: [ACCOUNT] }) === "next");

check("an update that never mentions owner_ref is untouched — the three "
  + "stranded rows stay editable",
  update({ first_name: "Reconciled", phone: "+16047245161" }) === "next");

check("adopting a stranded row by PATCHing a real owner_ref onto it is allowed",
  update({ owner_ref: ACCOUNT }) === "next");

check("an update that BLANKS owner_ref is refused — that would strand a row "
  + "that already had an owner",
  refused(update({ owner_ref: "" })));

// ---- blast radius ----
check("another collection's create is not touched",
  request({ method: "POST", path: "/api/collections/jobs/records",
            body: { goal: "book a table" } }) === "next");

check("a profile READ is not touched",
  request({ method: "GET", path: "/api/collections/owner_profile/records" }) === "next");

check("a profile DELETE is not touched",
  request({ method: "DELETE",
            path: "/api/collections/owner_profile/records/prof123456789" }) === "next");

// A create the hook cannot read the body of (unparseable payload) must fail
// CLOSED: an unreadable owner_ref is not a named one.
{
  let outcome = null;
  const e = {
    request: { method: "POST", url: { path: "/api/collections/owner_profile/records" },
               header: { get: () => "" } },
    requestInfo: () => { throw new Error("unparseable body"); },
    next: () => { outcome = "next"; },
    json: (status, payload) => { outcome = { status, error: payload.error }; },
  };
  handler(e);
  check("a create whose body cannot be read fails closed", refused(outcome));
}

// ---- the migration: the same law, in the database ----
// Driven, not grepped. A fake `app` records what it was asked to do, so the
// suite can also prove the migration touches no ROWS.
let up = null;
let down = null;
{
  const globals = { migrate: (u, d) => { up = u; down = d; }, console };
  const names = Object.keys(globals);
  new Function(...names, migrationSrc)(...names.map((n) => globals[n]));
}
check("the migration registers an up and a down step",
  typeof up === "function" && typeof down === "function");

function runMigration(step, { dropRule = false } = {}) {
  const collection = { name: "owner_profile", createRule: "" };
  const log = { saves: 0, deletes: 0, rowSaves: 0, queries: [] };
  let reads = 0;
  const app = {
    findCollectionByNameOrId: () => {
      reads++;
      // Second read is the verification read, and PocketBase hands these rule
      // properties back as a Go-backed OBJECT, not a JS primitive — the trap
      // 1700000013_owners_allow_signup.js:35-40 documents. A migration that
      // throws stops PocketBase from booting, so the String() coercion is
      // load-bearing and is pinned here.
      if (reads > 1) {
        return { ...collection,
                 createRule: dropRule ? null : new String(collection.createRule) };
      }
      return collection;
    },
    save: (arg) => { if (arg === collection) log.saves++; else log.rowSaves++; },
    delete: () => { log.deletes++; },
    findRecordsByFilter: (name, filter) => { log.queries.push(`${name}:${filter}`); return []; },
  };
  let threw = null;
  try { step(app); } catch (err) { threw = err; }
  return { collection, log, threw };
}

{
  const { collection, log, threw } = runMigration(up);
  check("the migration applies without throwing", threw === null);
  check("it closes owner_profile.createRule against an ownerless create",
    String(collection.createRule) === '@request.body.owner_ref != ""');
  check("it saves the collection exactly once", log.saves === 1);
  check("it deletes NOTHING — the three stranded rows carry the only copy of a "
    + "phone number", log.deletes === 0 && log.rowSaves === 0);
  check("it only ever COUNTS the stranded rows",
    log.queries.every((q) => q === "owner_profile:owner_ref = ''"));
}

{
  // If the rule did not actually land, booting with a door everyone believes is
  // shut is worse than failing loudly.
  const { threw } = runMigration(up, { dropRule: true });
  check("a rule that did not land makes the migration throw", threw !== null);
}

{
  const { collection, log } = runMigration(down);
  check("the down step restores the open createRule and touches no rows",
    String(collection.createRule) === "" && log.deletes === 0 && log.rowSaves === 0);
}

// The database layer must stay a RULE. Making owner_ref `required` instead was
// measured against pocketbase 0.30.4 with an orphan row present: it applies
// fine and then every write to that row fails `validation_required: Cannot be
// blank` — even a superuser patching only `phone`, and including `app.save()`
// inside a hook, because field validation is not an API rule. That freezes the
// very rows we were told to preserve.
// Comments stripped first: this migration explains the measurement by QUOTING
// `required = true`, and a check that matched prose would report the opposite
// of the truth (the same trap test_guard_superuser_dashboard.mjs:163-166 hit).
check("the migration does not make owner_ref a required field",
  !/required\s*[:=]\s*true/.test(
    migrationSrc.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n")));

if (failures) {
  console.error(`test_owner_profile_needs_owner: ${failures} failed`);
  process.exit(1);
}
console.log("test_owner_profile_needs_owner: all passed");
