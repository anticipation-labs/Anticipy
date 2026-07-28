/// <reference path="../pb_data/types.d.ts" />

// events was created without autodate timestamps, so the app couldn't sort
// the feed chronologically. Add created/updated like the other collections.
migrate((app) => {
  const c = app.findCollectionByNameOrId("events");
  c.fields.add(new Field({ name: "created", type: "autodate", onCreate: true }));
  c.fields.add(new Field({ name: "updated", type: "autodate", onCreate: true, onUpdate: true }));
  app.save(c);
}, (app) => {
  const c = app.findCollectionByNameOrId("events");
  c.fields.removeByName("created");
  c.fields.removeByName("updated");
  app.save(c);
});
