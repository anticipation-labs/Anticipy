/// <reference path="../pb_data/types.d.ts" />

// POST /me/delete   { "confirm": "delete" }   Authorization: <account token>
//
// The delete the privacy page has been promising and could not perform.
//
// `backend/pb_public/privacy.html` said, in the product's own voice: "I can't
// yet delete what's already on my server from in here. I'm building that."
// `design/CONSUMER-READINESS-2026-08-03.md` §5 makes that sentence a ship
// blocker for any consent surface — you cannot ask somebody for their inbox
// while the answer to "and can I take it back" is an email address.
//
// WHICH VALUE MAY MATCH WHICH COLUMN. The table below is the entire security of
// this endpoint, and the obvious shortcut — loop both identifiers over both
// columns — hands every signed-up user a way to delete a stranger's data.
//
//   owner_ref          a relation to `owners`. ONLY the caller's own account id.
//   the legacy column  holds the uuid a phone generated for itself before
//                      accounts existed, and its NAME DIFFERS PER COLLECTION:
//                      `owner_profile` calls it `owner_id`, the rest `owner`.
//
// `legacy_uuid` is a plain, client-writable field on `owners` (createRule is
// open, updateRule is self) and the iOS client posts it verbatim at signup. A
// value read from it is a CLAIM, never proof of anything about accounts.
// Applied to `owner_ref` it became: sign up declaring
// `legacy_uuid = <victim account id>`, POST here, and the victim's jobs,
// segments, agents, profile and transcripts are gone. The victim's id is not
// even secret — guard.pb.js's deliberately anonymous six-digit pair-code lookup
// hands it out, which claim_legacy.pb.js:50-58 documents as a real, exploited
// path. That file gets the pairing right; the first draft of this one did not.
//
// Naming the column per collection also fixes the quieter half of the same bug.
// A filter naming a column that does not exist throws for the WHOLE query — the
// failure that made the 2026-08-05 `agents` claim silently do nothing for two
// days — so querying `owner` on `owner_profile` threw, was swallowed, and left
// the densest PII in the system (name, email, phone, birthday, facts) behind
// while still reporting a count. sms.pb.js resolves inbound texts against
// owner_profile.phone BEFORE owners, so that residue kept routing somebody's
// texts after they believed they were gone.
//
// THE LIST LIVES INSIDE THE HANDLER, and that is not a style choice. A `const`
// declared at the top of a pb_hooks file is NOT in scope inside a routerAdd
// callback: the PocketBase JSVM gives each handler its own execution context,
// so the module body's bindings are gone by the time a request arrives.
// password_reset.pb.js:23-26 and audit_retention.pb.js:24-27 both warn about
// this, and this file was written as if they did not.
//
// It cost the whole feature. `for (const table of OWNER_TABLES)` threw
// `ReferenceError: OWNER_TABLES is not defined` on the first real delete, which
// PocketBase reports as a bare 400 "Something went wrong while processing your
// request." Nothing in that sentence names a scope, a file or a line, and the
// route answers 401 and 400 correctly right up until the moment it matters —
// so every cheap probe passes and only an authenticated delete, with the
// confirmation, ever reaches the bug. Measured 2026-08-22 against a local
// PocketBase 0.30.4 with a minimal two-route hook: a const declared outside
// throws, the identical const declared inside returns 200.
routerAdd("POST", "/me/delete", (e) => {
  const OWNER_TABLES = [
    { name: "jobs", legacy: "owner" },
    { name: "segments", legacy: "owner" },
    { name: "agents", legacy: "owner" },
    { name: "owner_profile", legacy: "owner_id" },
    { name: "pendants", legacy: "owner" },
    // Audit rows hold up to 1 MB each of verbatim task text, page content and
    // model responses, and their owner_ref is a TEXT column with no cascade — so
    // nothing else would ever remove them. audit_retention.pb.js caps the table
    // at 300 rows globally, which is a disk-space defence, not a privacy control.
    { name: "agent_llm_audit", legacy: null },
    { name: "agent_audit_sessions", legacy: null },
    // Last and largest, so a timeout lands on the cheapest table to retry.
    { name: "events", legacy: null },
  ];

  const auth = e.auth;
  if (!auth) return e.json(401, { ok: false, message: "Sign in first." });

  // `e.auth` is populated for ANY auth record in PocketBase 0.30.4, including
  // `_superusers` — guard.pb.js:110-118 documents this. Without the check a
  // superuser token drives this handler, writes a purge row naming its own id,
  // and leaves a stray pending purge aimed at a directory no owner owns.
  let collectionName = "";
  try { collectionName = String(auth.collection().name || ""); } catch (_) {}
  if (collectionName !== "owners") {
    return e.json(403, { ok: false, message: "Only an account can delete itself." });
  }

  // Proof of intent, not merely of possession. This is the one irreversible
  // operation in the product, and a bearer token is stateless and valid until
  // the record's tokenKey rotates — so one replayed request from a stolen
  // phone, a shared session or a logged Authorization header would otherwise be
  // a total wipe with no second step. password_reset.pb.js sets a far higher
  // bar just to change a password.
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  if (String(body.confirm || "") !== "delete") {
    return e.json(400, {
      ok: false,
      message: 'Send {"confirm":"delete"} to confirm. This cannot be undone.',
    });
  }

  const ref = String(auth.id || "").trim();
  const legacy = String(auth.getString("legacy_uuid") || "").trim();
  if (!ref) return e.json(400, { ok: false, message: "No account on that token." });

  const deleted = {};
  const failed = [];

  for (const table of OWNER_TABLES) {
    const keys = [["owner_ref", ref]];
    if (table.legacy) {
      // The account's own id can also sit in the legacy column, for rows this
      // device wrote after signing up.
      keys.push([table.legacy, ref]);
      if (legacy.length >= 8) keys.push([table.legacy, legacy]);
    }

    let count = 0;
    for (const pair of keys) {
      const field = pair[0];
      const value = pair[1];
      let rows = [];
      try {
        rows = e.app.findRecordsByFilter(table.name, `${field} = {:id}`, "", 0, 0, { id: value });
      } catch (err) {
        // Now that every column is named explicitly a throw is a REAL failure,
        // not an expected missing column. Swallowing it is what let
        // owner_profile survive while the response reported success.
        if (failed.indexOf(table.name) === -1) failed.push(table.name);
        console.log("delete: query failed on " + table.name + "." + field + ": " + err);
        continue;
      }
      for (const row of rows) {
        try {
          e.app.delete(row);
          count++;
        } catch (err) {
          if (failed.indexOf(table.name) === -1) failed.push(table.name);
          console.log("delete: " + table.name + " row survived: " + err);
        }
      }
    }
    deleted[table.name] = count;
  }

  // Data left behind means the promise cannot be made. Stop before the purge
  // row and before the account, so the caller still has an account to retry
  // with and nothing has been half-forgotten.
  if (failed.length) {
    return e.json(500, {
      ok: false,
      message: "I couldn't delete all of it, so I've stopped rather than tell you I had. Try again.",
      deleted: deleted,
      failed: failed,
    });
  }

  // The marker the worker acts on: memory is a per-owner SQLite file on the
  // brain's volume (brain/supervisor.py) and PocketBase cannot reach it.
  //
  // Written BEFORE the account goes. A crash between the two must not leave
  // memory on disk with no account left to name it — and the supervisor refuses
  // to purge any ref discovery still returns, so a purge row naming a surviving
  // account is deferred rather than dangerous.
  //
  // `legacy_uuid` rides along because the pre-migration founder's memory lives
  // OUTSIDE <state root>/<owner_ref> and the supervisor needs it to find that.
  try {
    const purges = e.app.findCollectionByNameOrId("purges");
    const row = new Record(purges);
    row.set("owner_ref", ref);
    row.set("legacy_uuid", legacy);
    row.set("memory_purged", false);
    row.set("requested_at", new Date().toISOString());
    e.app.save(row);
  } catch (err) {
    console.log("delete: could not record the purge request: " + err);
    return e.json(500, {
      ok: false,
      message: "I deleted what I could reach but couldn't schedule the rest. Try again.",
      deleted: deleted,
    });
  }

  // Last. This invalidates the token that authorised the call, which is
  // correct: there is nothing left for it to authorise. It also cascades
  // password_resets, a required relation on the account.
  //
  // If it fails this is NOT a success. The supervisor deliberately defers the
  // purge for an account that still exists, so reporting 200 would leave
  // somebody believing they had been forgotten while their memory sat on disk
  // with nothing prompting a retry.
  try {
    e.app.delete(auth);
  } catch (err) {
    console.log("DELETE INCOMPLETE: rows cleared but the account survived for "
                + ref + ": " + err);
    return e.json(409, {
      ok: false,
      message: "I deleted your data but couldn't close the account itself. Ask me again — what's already gone stays gone.",
      deleted: deleted,
      account_deleted: false,
      memory_purge: "waiting on the account closing",
    });
  }

  console.log("delete: " + JSON.stringify(deleted) + " account=closed for " + ref);
  return e.json(200, {
    ok: true,
    deleted: deleted,
    account_deleted: true,
    memory_purge: "scheduled",
  });
});
