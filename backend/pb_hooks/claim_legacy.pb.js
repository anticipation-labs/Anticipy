/// <reference path="../pb_data/types.d.ts" />

// POST /auth/claim   { "legacy_uuid": "…" }   Authorization: <account token>
//
// Adopt the rows a person made BEFORE accounts existed onto the account they
// just created, so signing up does not look like losing everything.
//
// Two different kinds of row, and they are claimed on different evidence:
//
//   jobs, owner_profile, segments — carry an `owner` column holding the UUID
//   the phone generated for itself. Matching that against the caller's own
//   `legacy_uuid` is real evidence: only the device that made those rows knows
//   the value, and it was recorded on the account at sign-up.
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

  const claimed = { jobs: 0, owner_profile: 0, segments: 0, events: 0 };

  // 1. Rows that can prove they are this person's.
  if (legacy.length >= 8) {
    for (const table of ["jobs", "owner_profile", "segments"]) {
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
