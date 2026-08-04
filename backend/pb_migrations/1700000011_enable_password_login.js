/// <reference path="../pb_data/types.d.ts" />

// Turn password login on for a database where `owners` ALREADY EXISTS —
// production, which created it in an earlier deploy with login switched off.
//
// This is a separate file from 1700000008 for a measured reason. On a real
// 0.30.4 rig, a collection created and re-configured in the SAME boot does not
// keep its auth-config change: identityFields persisted, `enabled` was silently
// dropped, and nothing was logged. The result would have been a collection that
// names its identity field and refuses every login — "we shipped login" with
// login not working. Editing an already-existing collection on a later boot
// works, which is exactly production's situation.
//
// 1700000008 now creates the collection correctly, so on a fresh database this
// file is a no-op that simply passes its own check.
//
// It VERIFIES ITSELF and throws, because this failure is silent by nature.

migrate((app) => {
  const owners = app.findCollectionByNameOrId("owners");
  owners.passwordAuth.enabled = true;
  owners.passwordAuth.identityFields = ["email"];
  owners.otp.enabled = false;
  app.save(owners);
  const after = app.findCollectionByNameOrId("owners");
  if (!after.passwordAuth.enabled) {
    throw new Error("password login did not persist");
  }
  console.log("PASSWORD LOGIN ENABLED:", JSON.stringify(after.passwordAuth));
}, (app) => {
  const owners = app.findCollectionByNameOrId("owners");
  owners.passwordAuth.enabled = false;
  app.save(owners);
});
