/// <reference path="../pb_data/types.d.ts" />

// POST /me/phone/remove   Authorization: <owner account token>
//
// Remove the phone as a routing address everywhere the signed-in account can
// still be found. `owners.phone` is the sign-up seed; once owner_profile exists
// its newest row is canonical, but leaving either copy behind can still power
// password recovery, inbound-SMS routing, or a stale client mirror. This route
// clears the account seed and EVERY profile row in one transaction.
//
// Everything lives inside the handler because PocketBase's pooled JSVM does
// not preserve file-scope bindings when a registered callback runs later.
routerAdd("POST", "/me/phone/remove", (e) => {
  const auth = e.auth;
  if (!auth) {
    return e.json(401, { ok: false, message: "Sign in first." });
  }

  let collectionName = "";
  try { collectionName = String(auth.collection().name || ""); } catch (_) {}
  if (collectionName !== "owners") {
    return e.json(403, {
      ok: false,
      message: "Only an account can remove its own phone number.",
    });
  }

  const ref = String(auth.id || "").trim();
  if (!ref) {
    return e.json(400, { ok: false, message: "No account on that token." });
  }

  let clearedProfiles = 0;
  try {
    e.app.runInTransaction((txApp) => {
      const owner = txApp.findRecordById("owners", ref);
      const legacy = String(owner.getString("legacy_uuid") || "").trim();
      owner.set("phone", "");
      txApp.save(owner);

      // claim_legacy historically swallowed an individual profile save
      // failure. Such a row remains ownerless but is still safely attributable
      // when its owner_id is this account's unique legacy UUID (or the account
      // ref used as the fresh-profile fallback). Revocation must cover that
      // residue too, or an old number remains routable after a 200 response.
      const ownership = legacy
        ? "(owner_ref = {:ref} || (owner_ref = '' && (owner_id = {:ref} || owner_id = {:legacy})))"
        : "(owner_ref = {:ref} || (owner_ref = '' && owner_id = {:ref}))";
      const ownershipParams = { ref: ref, legacy: legacy };

      const pageSize = 200;
      let offset = 0;
      while (true) {
        const profiles = txApp.findRecordsByFilter(
          "owner_profile", ownership, "id", pageSize, offset,
          ownershipParams);
        for (const profile of profiles) {
          profile.set("phone", "");
          txApp.save(profile);
          clearedProfiles++;
        }
        if (profiles.length < pageSize) break;
        offset += profiles.length;
      }

      // Prove the transaction's own view before commit. A refused save or an
      // incomplete page throws here and rolls every change back together.
      const ownerCheck = txApp.findRecordById("owners", ref);
      if (String(ownerCheck.getString("phone") || "").trim()) {
        throw new Error("owner phone remained after removal");
      }
      const profileCheck = txApp.findRecordsByFilter(
        "owner_profile", "(" + ownership + ") && phone != ''", "id", 1, 0,
        ownershipParams);
      if (profileCheck.length > 0) {
        throw new Error("a profile phone remained after removal");
      }
    });
  } catch (err) {
    console.log("phone remove: transaction rolled back: " + err);
    return e.json(500, {
      ok: false,
      message: "I couldn't verify that every copy was removed, so the change was not completed.",
    });
  }

  // Verify through the normal app again after commit. This catches a future
  // transaction/runtime regression before the client is told it can start
  // fresh. Unknown is failure; it is never interpreted as an empty phone.
  try {
    const owner = e.app.findRecordById("owners", ref);
    const legacy = String(owner.getString("legacy_uuid") || "").trim();
    const ownership = legacy
      ? "(owner_ref = {:ref} || (owner_ref = '' && (owner_id = {:ref} || owner_id = {:legacy})))"
      : "(owner_ref = {:ref} || (owner_ref = '' && owner_id = {:ref}))";
    if (String(owner.getString("phone") || "").trim()) {
      throw new Error("committed owner phone is not empty");
    }
    const profiles = e.app.findRecordsByFilter(
      "owner_profile", "(" + ownership + ") && phone != ''", "id", 1, 0,
      { ref: ref, legacy: legacy });
    if (profiles.length > 0) {
      throw new Error("committed profile phone is not empty");
    }
  } catch (err) {
    console.log("phone remove: post-commit verification failed: " + err);
    return e.json(500, {
      ok: false,
      message: "The server could not verify the removal. Refresh your account before relying on it.",
    });
  }

  console.log("phone remove: cleared account seed and " + clearedProfiles +
              " profile row(s)");
  return e.json(200, {
    ok: true,
    phone: "",
    clearedProfiles: clearedProfiles,
  });
});
