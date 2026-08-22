/// <reference path="../pb_data/types.d.ts" />

// A PROFILE WITH NO OWNER IS A PERSON NOBODY CAN LOOK UP.
//
// Production, 2026-08-22: 3 of 10 `owner_profile` rows carry `owner_ref = ""`.
// Every read path in the product asks for a profile BY ACCOUNT —
// brain/worker.py `_latest_profile` sends `owner_ref="<id>"`, agent_key.pb.js
// and password_reset.pb.js both filter `owner_ref = {:ref}` — and an empty
// relation satisfies none of those. So an orphan can never be read, never be
// completed, and never be told about: it is a first name, an email, a phone
// number and a birthday written into a drawer with no handle.
//
// They are not harmless while they sit there, either. sms.pb.js:166 resolves an
// inbound text to an account through `owner_profile` by `phone`, `-updated`,
// LIMIT 3. All three orphans carry the same number as a real person. Empty refs
// are skipped there (sms.pb.js:170), so they cannot mis-route a text — but they
// DO occupy that three-row window, and once three of them share a number the
// real row is pushed out of it and the text falls through to the `owners.phone`
// fallback, which is empty for exactly the accounts password_reset.pb.js:55-64
// documents. Then every "yes, go ahead" from that phone is dropped behind a 200.
//
// So: refuse them at the door. This is a middleware and not a `required` field
// on the column because required would also make the three EXISTING rows
// unsaveable — and they hold the only copy of a phone number. They must stay
// patchable, because patching them is how they get adopted:
// claim_legacy.pb.js:73-84 sets `owner_ref` on `owner_id = <device uuid> &&
// owner_ref = ''`. That adoption runs through `e.app.save()` inside a hook, not
// through the router, so nothing here can block a rescue.
//
// PocketBase JSVM note, the one every file in this directory repeats because it
// has cost real time twice (password_reset.pb.js:23-26,
// audit_retention.pb.js:24-27): a handler CANNOT see anything declared outside
// its own body. Everything below lives inside the handler.
routerUse((e) => {
  const path = e.request.url.path;
  const method = e.request.method;
  const base = "/api/collections/owner_profile/records";
  if (path !== base && !path.startsWith(base + "/")) return e.next();
  if (method !== "POST" && method !== "PATCH") return e.next();

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) { body = {}; }

  // `owner_ref` is a maxSelect:1 relation, so a client may legitimately send it
  // either as an id or as a one-element array. Refusing the array form would
  // break an honest write to stop a dishonest one.
  const named = (raw) => {
    const value = Array.isArray(raw) ? (raw.length === 1 ? raw[0] : "") : raw;
    return typeof value === "string" && value.trim() !== "";
  };

  if (method === "POST") {
    if (named(body.owner_ref)) return e.next();
    // 400, not 403: this is a malformed record, not a permission problem, and
    // the sentence has to be usable by whoever reads it in a client log —
    // the iPhone's `upsertOwner` sends no owner_ref at all when it has no
    // account id yet (app/ios/.../AnticipyBackend.swift:223), which is how at
    // least some of the live orphans were born.
    return e.json(400, {
      error: "owner_profile needs an owner",
      detail: "owner_ref must name the account this profile belongs to; " +
        "a profile created without one can never be read back, because every " +
        "lookup in the product filters on owner_ref. Sign in first, then save.",
    });
  }

  // PATCH: only when it actually tries to blank the column. An update that
  // never mentions owner_ref is left alone — that is the ordinary case, and it
  // includes the adoption of a legacy row and every write to the three rows
  // already stranded in production.
  if ("owner_ref" in body && !named(body.owner_ref)) {
    return e.json(400, {
      error: "owner_profile needs an owner",
      detail: "clearing owner_ref would strand this profile: nothing can find " +
        "a profile that names no account.",
    });
  }
  return e.next();
});
