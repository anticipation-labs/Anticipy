/// <reference path="../pb_data/types.d.ts" />

// THE DATABASE STOPS SAYING YES TO A PROFILE WITH NO OWNER.
//
// `owner_profile.createRule` has been `""` — anyone may create — since
// 1700000003, and `owner_ref` has been nullable by design since 1700000009 so
// pre-accounts clients kept working. The combination is how production reached
// 3 orphans out of 10 rows: a row whose `owner_ref` is `""` cannot be returned
// by ANY read in the product, because every one of them filters on the account
// (brain/worker.py `_latest_profile`, agent_key.pb.js:40,
// password_reset.pb.js:64). It is somebody's first name, email, phone and
// birthday, permanently unreadable, and it still occupies the three-row window
// sms.pb.js:166 uses to route an inbound text by number.
//
// A RULE, NOT `required`. Both were tried against pocketbase 0.30.4 on a
// scratch instance with an orphan row already present:
//   - `owner_ref.required = true` APPLIES fine, and then every write to an
//     existing empty row fails `validation_required: Cannot be blank` — even a
//     superuser patching only `phone`. Field validation runs on `app.save()`
//     too, so that reaches INSIDE hooks: it would freeze the three live rows,
//     which hold the only copy of a phone number, and make reconciliation
//     all-or-nothing instead of something a person can do in stages.
//   - `createRule` closes exactly the door the orphans came through (the API
//     create) and leaves those rows fully patchable — verified: adopting one by
//     PATCHing `owner_ref` onto it still returns 200 with the rule in place.
//
// Measured on 0.30.4 rather than assumed, because `!=` in PocketBase filters
// carries IS-NOT semantics and a NULL might have satisfied `!= ""`: a create
// with `owner_ref` MISSING and a create with `owner_ref: ""` are both refused
// 400; a create naming a real account still returns 200.
//
// Nothing is deleted and no existing row is touched. The three stranded rows
// stay exactly where they are — `POST /auth/claim` (claim_legacy.pb.js:73-84)
// adopts them onto the account whose `legacy_uuid` matches their `owner_id`,
// and that runs through `app.save()` inside a hook, which no API rule gates.
//
// backend/pb_hooks/owner_profile_owner.pb.js refuses the same write one layer
// up, with a sentence a client log can act on. This is the layer that survives
// a hook file being renamed, and it is enforced even for a caller holding the
// service token (that token is a header the guard checks, not a PocketBase
// identity, so rules still apply to it).
migrate((app) => {
  const c = app.findCollectionByNameOrId("owner_profile");
  c.createRule = '@request.body.owner_ref != ""';
  app.save(c);

  // Read it back through String(): these rule properties come back as a
  // Go-backed object, so `=== "…"` is false even when the rule is right —
  // 1700000013 lost time to exactly this and a migration that throws stops
  // PocketBase from booting at all.
  const after = app.findCollectionByNameOrId("owner_profile");
  const rule = after.createRule === null ? null : String(after.createRule);
  if (rule !== '@request.body.owner_ref != ""') {
    throw new Error("owner_profile still accepts an ownerless create; createRule=" +
      JSON.stringify(rule));
  }
  let orphans = 0;
  try {
    orphans = app.findRecordsByFilter("owner_profile", "owner_ref = ''", "", 0, 0).length;
  } catch (_) {}
  console.log("owner_profile now requires an owner on create; createRule =",
    JSON.stringify(rule), "— existing ownerless rows left intact:", orphans);
}, (app) => {
  const c = app.findCollectionByNameOrId("owner_profile");
  c.createRule = "";
  app.save(c);
});
