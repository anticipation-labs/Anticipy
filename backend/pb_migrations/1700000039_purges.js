/// <reference path="../pb_data/types.d.ts" />

// A place for "this person asked to be forgotten" to survive being forgotten.
//
// Deleting somebody's data spans two systems. The rows live in PocketBase and
// can go synchronously; their MEMORY does not — it is a per-owner SQLite file
// on the brain's own volume (brain/supervisor.py:91-93,
// `<state root>/<owner_ref>/memory.db`), and PocketBase cannot reach it. So the
// request has to outlive the account row that made it, which means it cannot be
// a field on `owners` and it cannot be an `events` row either: both are deleted
// by the very operation that needs to be remembered.
//
// Hence a collection of its own, holding nothing but an id and a flag. It is
// deliberately NOT owner-scoped by relation — the owner is gone by the time the
// worker reads it, and a dangling relation would either block the delete or be
// nulled out and lose the only thing the row is for.
//
// Nothing in here is personal: an account id, a legacy uuid, and two
// timestamps. That is the point — the residue of a deletion must not itself be
// a copy of what was deleted.
migrate((app) => {
  const purges = new Collection({
    name: "purges",
    type: "base",
    // No public rules at all. Written by the delete endpoint under its own
    // authority and read by the worker's superuser client; a person asking to
    // be forgotten must not be able to list who else asked.
    listRule: null,
    viewRule: null,
    createRule: null,
    updateRule: null,
    deleteRule: null,
    fields: [
      { name: "owner_ref", type: "text", required: true },
      // The pre-accounts uuid, so the worker can also clear a state directory
      // written under the older naming.
      { name: "legacy_uuid", type: "text", required: false },
      // Set by the worker once the memory file is actually gone. Until then the
      // request is outstanding and will be retried, because a delete that
      // silently half-happened is worse than one that failed loudly.
      { name: "memory_purged", type: "bool", required: false },
      { name: "requested_at", type: "text", required: false },
      { name: "purged_at", type: "text", required: false },
    ],
    indexes: [
      "CREATE INDEX idx_purges_pending ON purges (memory_purged)",
    ],
  });
  app.save(purges);
  console.log("purges collection created: deletion requests outlive the account");
}, (app) => {
  const purges = app.findCollectionByNameOrId("purges");
  if (purges) app.delete(purges);
});
