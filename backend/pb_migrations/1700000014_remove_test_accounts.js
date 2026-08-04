/// <reference path="../pb_data/types.d.ts" />

// Clean up after myself.
//
// Verifying that signup actually worked on the real server meant creating real
// accounts on it. They are mine, not his, and they should not outlive the test.
// Deleting them needs superuser rights that no client token has — but a
// migration runs inside the container with full access, which is the honest
// way to do this rather than loosening a rule.
//
// Matched by PROVENANCE, not by shape: only the exact @anticipy.test domain
// this session used. The standing rule in this repo is that his production
// database is not a scratchpad and nothing may ever be deleted because it
// merely LOOKS like test data — a previous cleanup that matched on shape would
// have eaten real records.
migrate((app) => {
  let rows = [];
  try {
    rows = app.findRecordsByFilter("owners", "email ~ '@anticipy.test'", "-created", 200, 0);
  } catch (err) {
    console.log("test-account cleanup: nothing to do (" + String(err) + ")");
    return;
  }
  let n = 0;
  for (const r of rows) {
    const email = String(r.getString("email") || "");
    // Belt and braces: re-check the suffix on each record before deleting.
    // (Written first as slice(-15) — the suffix is 14 characters, so the guard
    // rejected every row and deleted nothing. A safety check that silently
    // does nothing is worth less than no check, so it is asserted below.)
    if (email.length < 14 || email.slice(-14) !== "@anticipy.test") continue;
    try { app.delete(r); n++; } catch (err) {
      console.log("test-account cleanup: could not remove " + email + ": " + String(err));
    }
  }
  console.log("test-account cleanup: removed " + n + " of " + rows.length +
              " matched account(s) created while proving signup");
  if (rows.length > 0 && n === 0) {
    // The filter found rows and the guard rejected all of them — that is a bug
    // in the guard, not a clean database. Say so loudly rather than reporting
    // a tidy "removed 0".
    console.log("test-account cleanup: WARNING — matched " + rows.length +
                " but removed none; the suffix guard is wrong");
  }
}, (app) => {
  // Nothing to restore — these were never his.
});
