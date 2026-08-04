/// <reference path="../pb_data/types.d.ts" />

// A person, finally.
//
// Until now this backend had no concept of a user: `owner` was a plain text
// column holding a UUID the phone invented for itself on first launch, and the
// only lock was one shared token every client received. That is why the phone
// could not read its own data until a browser was paired on a computer, why
// nothing could be scoped to a person, and why "delete everything about me"
// had nothing to delete against.
//
// This migration is DELIBERATELY INERT. It creates the collection and nothing
// else: no rules are tightened, no client is asked to authenticate, no existing
// row changes. A deploy of this file is a no-op for every running client, which
// is the whole point — the door is built long before anyone is asked to use a
// key. (Stage 4 of design/LOGIN-DESIGN-2026-08-03.md.)
migrate((app) => {
  const owners = new Collection({
    type: "auth",
    name: "owners",
    fields: [
      // PocketBase auto-injects password/tokenKey/emailVisibility/verified for
      // an auth collection; only the fields that are ours are declared here.
      { name: "email", type: "email", required: true },
      // E.164. A ROUTING ADDRESS, never a credential: US carriers may reassign
      // a disconnected number after ~45 days, so whoever inherits a recycled
      // number must never thereby inherit the account.
      { name: "phone", type: "text", required: false },
      // The UUID this person's phone generated before accounts existed. This is
      // what lets their existing jobs, profile and segments be claimed rather
      // than orphaned.
      { name: "legacy_uuid", type: "text", required: false },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: [
      'CREATE UNIQUE INDEX `idx_owners_phone` ON `owners` (`phone`) WHERE `phone` != \'\'',
      'CREATE UNIQUE INDEX `idx_owners_legacy` ON `owners` (`legacy_uuid`) WHERE `legacy_uuid` != \'\'',
      'CREATE UNIQUE INDEX `idx_owners_email` ON `owners` (`email`)',
    ],
    // Email + password: the thing people already know how to do, and the only
    // method that works without a mail transport in the image. One-time codes
    // and password reset both arrive by email, and this image has no way to
    // send one — so they stay off rather than shipping as dead buttons.
    passwordAuth: { enabled: true, identityFields: ["email"] },
    otp: { enabled: false },
    // "" = any record may authenticate. null would mean nobody can.
    authRule: "",
    // A person can only ever see and edit themselves.
    listRule: "id = @request.auth.id",
    viewRule: "id = @request.auth.id",
    createRule: "",   // anyone may sign themselves up; they still only see themselves
    updateRule: "id = @request.auth.id",
    deleteRule: null,
  });
  app.save(owners);
}, (app) => {
  // Reverse: nothing references this collection yet, so dropping it is clean.
  // Note for anyone reading this as a production rollback — it is NOT one.
  // Migrations auto-apply at container boot (`serve --migrationsDir`), so a
  // `migrate down` on Railway is undone by the next restart. The honest
  // position for this file is "irreversible in practice, harmless by
  // construction": it is additive and nothing reads it.
  try {
    app.delete(app.findCollectionByNameOrId("owners"));
  } catch (_) {}
});
