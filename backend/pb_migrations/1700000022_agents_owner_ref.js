/// <reference path="../pb_data/types.d.ts" />

// Give `agents` the owner_ref column every other claimable table already has.
//
// 1700000009 added owner_ref to jobs, events, owner_profile and segments. It
// did NOT add it to agents. On 2026-08-05 `agents` was added to the claim loop
// in pb_hooks/claim_legacy.pb.js — which filters on `owner_ref = ''` and then
// writes `owner_ref`. With no such column the filter throws, the throw is
// swallowed by the surrounding try/catch, and the loop has been silently
// claiming nothing ever since. It was reported as fixed. It was not fixed.
//
// The symptom it is meant to end is real and was seen twice: the Chrome
// extension says "Paired with your iPhone" and shows a completed booking while
// the phone says "Chrome not linked", and neither reloading nor reinstalling
// the extension reconciles them. Both are telling the truth — agents.owner is
// written ONCE at pairing, the phone looks the row up BY that id, and the id
// rotates on a Settings reset, a reinstall, or a second account from the same
// device. Every other table got carried across at sign-in; this one could not.
//
// DELIBERATELY INERT, exactly like 1700000009: nullable, not required, no rule
// changes, no existing row touched. Old clients keep writing agents rows with
// no owner_ref and keep working. Nothing reads it until a person signs in and
// calls /auth/claim.
migrate((app) => {
  const owners = app.findCollectionByNameOrId("owners");
  let c;
  try {
    c = app.findCollectionByNameOrId("agents");
  } catch (_) {
    return;                     // no agents collection here: nothing to do
  }
  if (c.fields.getByName("owner_ref")) return;
  c.fields.add(new Field({
    name: "owner_ref",
    type: "relation",
    required: false,            // nullable: old clients write without it
    collectionId: owners.id,
    cascadeDelete: true,        // deleting a person really deletes their data
    maxSelect: 1,
  }));
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("agents");
    const f = c.fields.getByName("owner_ref");
    if (f) { c.fields.removeById(f.id); app.save(c); }
  } catch (_) {}
});
