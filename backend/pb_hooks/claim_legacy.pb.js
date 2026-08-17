/// <reference path="../pb_data/types.d.ts" />

// POST /auth/claim   { "legacy_uuid": "…" }   Authorization: <account token>
//
// Adopt the rows a person made BEFORE accounts existed onto the account they
// just created, so signing up does not look like losing everything.
//
// Two different kinds of row, and they are claimed on different evidence:
//
//   jobs, owner_profile, segments, agents — carry an `owner` column holding
//   the UUID the phone generated for itself. Matching that against the
//   caller's own `legacy_uuid` is real evidence: only the device that made
//   those rows knows the value, and it was recorded on the account at sign-up.
//
//   `agents` was missing from this list until 2026-08-05, and the symptom was
//   ugly: the Chrome extension said "Paired with your iPhone" and showed a
//   completed booking, while the phone said "Chrome not linked", and neither
//   reloading nor re-installing the extension could reconcile them. Both were
//   telling the truth. agents.owner is written ONCE, at pairing; the phone
//   looks the row up BY that id; and the id rotates (a reset in Settings, a
//   second account from the same device, a reinstall). Every other table got
//   carried across on sign-in and this one silently did not.
//
//   That 08-05 change did NOT work and was reported as though it had. The
//   filter below reads `owner_ref = ''`, and 1700000009 never gave `agents` an
//   owner_ref column — so the query threw, the throw was swallowed by the
//   try/catch, and the loop claimed nothing at all for two days. Fixed by
//   1700000022, which adds the column. This line only does something once that
//   migration has actually run on the instance being talked to.
//
//   events — have NEVER had an owner column (see 1700000009), so there is no
//   evidence on the row at all. They are therefore claimed ONLY when this is
//   the single account on the whole instance, i.e. the pre-accounts era had
//   exactly one person and it is unambiguous whose words those were. With two
//   or more accounts the honest answer is to leave them unowned and invisible
//   rather than hand one person another person's transcripts — which is the
//   bug this whole change exists to fix, seen for real: a brand-new account
//   opened the app onto someone else's spoken sentences.
routerAdd("POST", "/auth/claim", (e) => {
  const auth = e.auth;
  if (!auth) return e.json(401, { ok: false, message: "Sign in first." });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const legacy = String(body.legacy_uuid || "").trim();

  // The uuid has to be the one recorded ON THIS ACCOUNT at sign-up, or the
  // paragraph above is a lie: it called the uuid evidence "because it was
  // recorded on the account at sign-up" and then never once read that record.
  // The value is not a secret either — agents.owner IS the phone's uuid, and
  // guard.pb.js's deliberately anonymous pair-code lookup hands the whole row
  // out to anyone who guesses a six-digit code. So the attack was: read a
  // stranger's uuid off a pair code, sign up a throwaway account, POST it
  // here, and every legacy row moved — including the owner_profile carrying
  // that person's first name, last name, email, phone and birthday. It did
  // not stop at reading, either: sms.pb.js resolves an inbound number through
  // owner_profile BEFORE owners, so from that moment every "yes, go ahead"
  // the real owner texted from their own phone was filed under the stranger
  // and released into the stranger's browser. owners.legacy_uuid is UNIQUE
  // (idx_owners_legacy, 1700000008) and the app posts back the same value it
  // registered, so equality against the recorded one is the entire test —
  // and an account with nothing recorded can claim nothing.
  const recorded = String(auth.getString("legacy_uuid") || "").trim();
  if (legacy && legacy !== recorded) {
    console.log("claim: refused " + legacy + " for " + auth.id + " (not this account's device)");
    return e.json(403, { ok: false, message: "That device isn't on this account." });
  }

  const claimed = { jobs: 0, owner_profile: 0, segments: 0, agents: 0, events: 0 };

  // 1. Rows that can prove they are this person's.
  if (legacy.length >= 8) {
    for (const table of ["jobs", "owner_profile", "segments", "agents"]) {
      try {
        const field = table === "owner_profile" ? "owner_id" : "owner";
        const rows = e.app.findRecordsByFilter(
          table, field + " = {:u} && owner_ref = ''", "-created", 500, 0, { u: legacy });
        for (const r of rows) {
          r.set("owner_ref", auth.id);
          try { e.app.save(r); claimed[table]++; } catch (_) {}
        }
      } catch (_) {}
    }
  }

  // 2. Transcripts, only when there is no one else it could belong to.
  try {
    const owners = e.app.findRecordsByFilter("owners", "id != ''", "-created", 2, 0);
    if (owners && owners.length === 1 && owners[0].id === auth.id) {
      const rows = e.app.findRecordsByFilter(
        "events", "owner_ref = ''", "-created", 2000, 0);
      for (const r of rows) {
        r.set("owner_ref", auth.id);
        try { e.app.save(r); claimed.events++; } catch (_) {}
      }
    }
  } catch (_) {}

  console.log("claim: " + JSON.stringify(claimed) + " for " + auth.id);
  return e.json(200, { ok: true, claimed: claimed });
});
