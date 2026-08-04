/// <reference path="../pb_data/types.d.ts" />

// Let people actually sign up on a database where `owners` already exists.
//
// The divergence this fixes, and it is the same shape as 1700000011: an earlier
// deploy created `owners` with `createRule: null` — nobody may create an
// account — because at that point login was not the plan. 1700000008 was later
// corrected so a FRESH database gets it right, but a migration that has already
// run never runs again, so production kept the closed rule. Result, measured
// against production: the login screen worked, password auth reported itself
// enabled, and every attempt to sign up came back 403 from PocketBase.
//
// The lesson worth keeping: correcting a migration only fixes databases that
// have not applied it yet. Anything already live needs its own forward step.
//
// Self-verifying, because "signup is broken" is otherwise indistinguishable
// from "the guard refused it" from the outside.
migrate((app) => {
  const owners = app.findCollectionByNameOrId("owners");

  // Anyone may sign themselves up. They still only ever see themselves —
  // listRule/viewRule/updateRule are unchanged and scoped to the account.
  owners.createRule = "";

  // Email is the identity, so it must be present and unique.
  const email = owners.fields.getByName("email");
  if (email) { email.required = true; }
  owners.indexes = (owners.indexes || [])
    .filter((i) => !i.includes("idx_owners_email"))
    .concat(["CREATE UNIQUE INDEX `idx_owners_email` ON `owners` (`email`)"]);

  app.save(owners);

  // Compare through String(). These rule properties come back as a Go-backed
  // OBJECT wrapping the value, not a JS primitive — so `=== ""` is false even
  // when the rule really is the empty string and signup really does work. The
  // first version of this check used ===, threw on a migration that had in
  // fact succeeded, and PocketBase refuses to boot when a migration throws:
  // it would have taken the backend down to protect against nothing.
  const after = app.findCollectionByNameOrId("owners");
  const rule = after.createRule === null ? null : String(after.createRule);
  if (rule !== "") {
    throw new Error("signup is still closed after the migration; createRule=" + JSON.stringify(rule));
  }
  console.log("signup enabled; createRule =", JSON.stringify(rule));
}, (app) => {
  const owners = app.findCollectionByNameOrId("owners");
  owners.createRule = null;
  app.save(owners);
});
