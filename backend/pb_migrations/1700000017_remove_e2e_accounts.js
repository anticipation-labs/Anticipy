/// <reference path="../pb_data/types.d.ts" />

// Clean up after myself — third pass.
//
// This session proved two things against production: that a shared phone
// number no longer blocks a second account (probe accounts at @example.com),
// and that a fresh account can pair a browser and complete a real job end to
// end (an account at @anticipy-test.dev). Those accounts are mine, not his,
// and deleting them needs the superuser rights only a migration has.
//
// Matched by PROVENANCE, exactly as 1700000015: only the two literal test
// domains this session used. Nothing is ever deleted for merely looking
// like test data.
migrate((app) => {
  const suffixes = ["@example.com", "@anticipy-test.dev"];
  let rows = [];
  try {
    rows = app.findRecordsByFilter(
      "owners", "email ~ '@example.com' || email ~ '@anticipy-test.dev'", "-created", 200, 0);
  } catch (err) {
    console.log("e2e cleanup: nothing to do (" + String(err) + ")");
    return;
  }
  let n = 0;
  for (const r of rows) {
    const email = String(r.getString("email") || "");
    if (!suffixes.some((s) => email.length > s.length && email.slice(-s.length) === s)) continue;
    try { app.delete(r); n++; } catch (err) {
      console.log("e2e cleanup: could not remove " + email + ": " + String(err));
    }
  }
  console.log("e2e cleanup: removed " + n + " of " + rows.length + " matched account(s)");
  if (rows.length > 0 && n === 0) {
    console.log("e2e cleanup: WARNING — matched " + rows.length + " but removed none");
  }
}, (app) => {
  // Nothing to restore — these were never his.
});
