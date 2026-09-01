/// <reference path="../../../backend/pb_data/types.d.ts" />

// Small production-shaped schema for the exact-PocketBase owner-profile gate.
// The ids make the second row the deterministic `-updated,-created,-id` winner
// even when both records land inside the same millisecond.
migrate((app) => {
  const owners = new Collection({
    type: "auth",
    name: "owners",
    fields: [
      { name: "email", type: "email", required: true },
      { name: "phone", type: "text", required: false },
      { name: "legacy_uuid", type: "text", required: false },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_test_owner_email ON owners (email)"],
    passwordAuth: { enabled: true, identityFields: ["email"] },
    authRule: "",
    listRule: "id = @request.auth.id",
    viewRule: "id = @request.auth.id",
    createRule: "",
    updateRule: "id = @request.auth.id",
    deleteRule: null,
  });
  app.save(owners);

  const profiles = new Collection({
    type: "base",
    name: "owner_profile",
    fields: [
      { name: "owner_id", type: "text", required: true },
      { name: "phone", type: "text" },
      { name: "name", type: "text" },
      { name: "first_name", type: "text" },
      { name: "last_name", type: "text" },
      { name: "email", type: "text" },
      { name: "birthday", type: "text" },
      { name: "facts", type: "text" },
      { name: "timezone", type: "text" },
      {
        name: "owner_ref",
        type: "relation",
        collectionId: owners.id,
        cascadeDelete: true,
        maxSelect: 1,
      },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: "",
    deleteRule: "",
  });
  app.save(profiles);

  const seededOwner = new Record(owners);
  seededOwner.set("email", "seed@example.com");
  seededOwner.set("phone", "+16045550001");
  seededOwner.set("legacy_uuid", "seed-device");
  seededOwner.setPassword("password12345");
  app.save(seededOwner);

  const oldProfile = new Record(profiles);
  oldProfile.setRaw("id", "profileaaa00001");
  oldProfile.set("owner_id", "seed-device");
  oldProfile.set("owner_ref", seededOwner.id);
  oldProfile.set("phone", "+16045550001");
  oldProfile.set("email", "old@example.com");
  oldProfile.set("first_name", "Old");
  app.save(oldProfile);

  const newProfile = new Record(profiles);
  newProfile.setRaw("id", "profilezzz00002");
  newProfile.set("owner_id", "seed-device");
  newProfile.set("owner_ref", seededOwner.id);
  newProfile.set("phone", "");
  newProfile.set("email", "");
  newProfile.set("first_name", "Newest");
  app.save(newProfile);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("owner_profile")); } catch (_) {}
  try { app.delete(app.findCollectionByNameOrId("owners")); } catch (_) {}
});
