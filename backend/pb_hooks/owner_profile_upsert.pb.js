/// <reference path="../pb_data/types.d.ts" />

// POST /me/profile/upsert   Authorization: <owner account token>
//
// One authenticated, partial write in; one complete canonical profile out.
//
// Settings saves identity details and the phone independently. Those requests
// can be in flight together, and the old client path made each one do a list
// followed by either POST or PATCH. Two first writes could therefore both see
// no row and create two different partial profiles. Later reads picked whichever
// row happened to be newest, so a person's name or phone appeared to vanish.
//
// This route makes the read, merge, save, duplicate cleanup, and verification
// one database transaction. The unique partial index installed by
// 1700000054_owner_profile_canonical.js is the storage-level backstop for two
// simultaneous first writers. Omitted fields preserve the canonical row; an
// explicit empty string is a real value and clears that field. Account values
// seed only the first profile, because once a profile exists its empty phone or
// email is authoritative and must not resurrect the sign-up-era copy.
//
// Everything lives inside the handler because PocketBase's pooled JSVM does
// not preserve file-scope bindings when a registered callback runs later.
routerAdd("POST", "/me/profile/upsert", (e) => {
  const auth = e.auth;
  if (!auth) {
    return e.json(401, { ok: false, message: "Sign in first." });
  }

  let collectionName = "";
  try { collectionName = String(auth.collection().name || ""); } catch (_) {}
  if (collectionName !== "owners") {
    return e.json(403, {
      ok: false,
      message: "Only an account can update its own profile.",
    });
  }

  const ref = String(auth.id || "").trim();
  if (!ref) {
    return e.json(400, { ok: false, message: "No account on that token." });
  }

  let body;
  try {
    body = e.requestInfo().body;
  } catch (_) {
    return e.json(400, { ok: false, message: "The profile update was unreadable." });
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return e.json(400, { ok: false, message: "The profile update must be an object." });
  }

  const editable = [
    "phone", "name", "first_name", "last_name", "email", "birthday",
    "facts", "timezone",
  ];
  const allowed = {
    phone: true,
    name: true,
    first_name: true,
    last_name: true,
    email: true,
    birthday: true,
    facts: true,
    timezone: true,
  };
  for (const key of Object.keys(body)) {
    if (!allowed[key]) {
      return e.json(400, {
        ok: false,
        message: "That field is not part of the owner profile.",
      });
    }
    if (typeof body[key] !== "string") {
      return e.json(400, {
        ok: false,
        message: "Profile fields must be text.",
      });
    }
  }

  const has = (key) => Object.prototype.hasOwnProperty.call(body, key);
  let canonicalID = "";
  let removedDuplicates = 0;

  try {
    e.app.runInTransaction((txApp) => {
      // This account read is part of the same transaction too. A failed read
      // is unknown state and aborts; it is never converted into empty seeds.
      const owner = txApp.findRecordById("owners", ref);

      // findRecordsByFilter returns [] for a known absence and throws for an
      // unknown read. That distinction is why this must not use a catch around
      // findFirstRecordByFilter: "not found" and "the DB could not answer"
      // would otherwise both fall into create.
      const profiles = txApp.findRecordsByFilter(
        "owner_profile", "owner_ref = {:ref}", "-updated,-created,-id", 0, 0,
        { ref: ref });

      let canonical;
      if (profiles.length > 0) {
        canonical = profiles[0];
        // The newest row is authoritative for EVERY field, including an empty
        // phone written by the removal flow. Older nonempty duplicates never
        // value-merge back into it.
        for (let i = 1; i < profiles.length; i++) {
          txApp.delete(profiles[i]);
          removedDuplicates++;
        }
      } else {
        canonical = new Record(txApp.findCollectionByNameOrId("owner_profile"));
        // Seed every same-named text field from the account on the first write.
        // Today owners has email and phone; this also remains correct if a
        // future account migration adds another canonical identity field.
        for (const field of editable) {
          canonical.set(field, String(owner.getString(field) || ""));
        }
      }

      // Ownership is derived only from the authenticated token. owner_id is a
      // legacy device linkage, not authority; retain an existing value, then
      // prefer the account's recorded legacy UUID and finally the account id
      // so this required structural field is never blank on a fresh profile.
      canonical.set("owner_ref", ref);
      const existingOwnerID = String(canonical.getString("owner_id") || "").trim();
      const accountOwnerID = String(owner.getString("legacy_uuid") || "").trim();
      canonical.set("owner_id", existingOwnerID || accountOwnerID || ref);

      // Presence, not truthiness, is the contract. `""` clears; omission keeps
      // the current row (or the account seed on the first row).
      for (const field of editable) {
        if (has(field)) canonical.set(field, body[field]);
      }
      txApp.save(canonical);
      canonicalID = String(canonical.id || "");
      if (!canonicalID) throw new Error("saved profile has no id");

      const check = txApp.findRecordsByFilter(
        "owner_profile", "owner_ref = {:ref}", "-updated,-created,-id", 2, 0,
        { ref: ref });
      if (check.length !== 1 || String(check[0].id || "") !== canonicalID) {
        throw new Error("owner profile did not resolve to one canonical row");
      }
      for (const field of editable) {
        if (has(field) && String(check[0].getString(field) || "") !== body[field]) {
          throw new Error("owner profile field did not persist: " + field);
        }
      }
    });
  } catch (err) {
    console.log("owner profile upsert: transaction rolled back: " + err);
    return e.json(500, {
      ok: false,
      message: "I couldn't verify the complete profile, so nothing was reported as saved.",
    });
  }

  // Read through the normal app after commit. A concurrent partial writer may
  // legitimately have changed a field this request omitted, so verification
  // pins uniqueness and this request's explicit fields, then returns the latest
  // complete row rather than a stale pre-commit snapshot.
  let saved;
  try {
    const rows = e.app.findRecordsByFilter(
      "owner_profile", "owner_ref = {:ref}", "-updated,-created,-id", 2, 0,
      { ref: ref });
    if (rows.length !== 1 || String(rows[0].id || "") !== canonicalID) {
      throw new Error("committed profile is not uniquely canonical");
    }
    saved = rows[0];
    for (const field of editable) {
      if (has(field) && String(saved.getString(field) || "") !== body[field]) {
        throw new Error("committed profile field disagrees: " + field);
      }
    }
  } catch (err) {
    console.log("owner profile upsert: post-commit verification failed: " + err);
    return e.json(500, {
      ok: false,
      message: "The server could not verify the saved profile. Refresh before relying on it.",
    });
  }

  const profile = {
    id: String(saved.id || ""),
    owner_ref: String(saved.getString("owner_ref") || ""),
    owner_id: String(saved.getString("owner_id") || ""),
  };
  for (const field of editable) {
    profile[field] = String(saved.getString(field) || "");
  }

  return e.json(200, {
    ok: true,
    profile: profile,
    removedDuplicates: removedDuplicates,
  });
});
