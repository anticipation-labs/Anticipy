/// <reference path="../pb_data/types.d.ts" />

// Where a password-reset code lives while it is waiting to be used.
//
// The code itself is NEVER stored — only a SHA-256 of it. Anyone who can read
// this table (a backup, a leaked dump, a future hole) still cannot reset
// anybody's password, because what they have is a hash and the code has
// already left by SMS.
//
// Every rule is null: nothing outside the server may read, write or even list
// this. The reset hook reaches it through the app DAO, which bypasses rules by
// design; there is no client-facing path to it at all.
migrate((app) => {
  const owners = app.findCollectionByNameOrId("owners");
  const c = new Collection({
    type: "base",
    name: "password_resets",
    fields: [
      { name: "owner", type: "relation", required: true, collectionId: owners.id,
        cascadeDelete: true, maxSelect: 1 },
      { name: "code_hash", type: "text", required: true },
      // ISO8601 UTC. A code that is not used quickly is not a code any more.
      { name: "expires", type: "text", required: true },
      // Guessing a 6-digit code is 1-in-a-million per try, which is only true
      // if the tries are counted.
      { name: "attempts", type: "number", required: false },
      { name: "used", type: "bool", required: false },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: [
      "CREATE INDEX `idx_resets_owner` ON `password_resets` (`owner`)",
    ],
    listRule: null,
    viewRule: null,
    createRule: null,
    updateRule: null,
    deleteRule: null,
  });
  app.save(c);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("password_resets")); } catch (_) {}
});
