/// <reference path="../pb_data/types.d.ts" />

// Where the owner's own details live, so nobody has to hand-edit a server
// environment variable to make texting work. Before this, the owner's phone
// number existed ONLY as ANTICIPY_OWNER_PHONE typed into Railway by hand —
// which meant a second person could never onboard themselves.
migrate((app) => {
  const c = new Collection({
    type: "base",
    name: "owner_profile",
    fields: [
      { name: "owner_id", type: "text", required: true },
      { name: "phone", type: "text", required: false },   // E.164
      { name: "name", type: "text", required: false },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: "",
    deleteRule: "",
  });
  app.save(c);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("owner_profile")); } catch (e) {}
});
