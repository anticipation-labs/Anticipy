/// <reference path="../pb_data/types.d.ts" />

// Pendants participate in the same tenant boundary as phones and browsers.
migrate((app) => {
  const owners = app.findCollectionByNameOrId("owners");
  const pendants = app.findCollectionByNameOrId("pendants");
  if (!pendants.fields.getByName("owner_ref")) {
    pendants.fields.add(new Field({
      name: "owner_ref", type: "relation", required: false,
      collectionId: owners.id, cascadeDelete: true, maxSelect: 1,
    }));
  }
  app.save(pendants);
}, (app) => {
  try {
    const pendants = app.findCollectionByNameOrId("pendants");
    const field = pendants.fields.getByName("owner_ref");
    if (field) { pendants.fields.removeById(field.id); app.save(pendants); }
  } catch (_) {}
});
