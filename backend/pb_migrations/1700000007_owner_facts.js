/// <reference path="../pb_data/types.d.ts" />

// Whatever she has learned about him, as free-form key/value.
//
// The mistake this replaces: adding a column per field a form might ask for.
// birthday, then passport number, then dietary restriction, then loyalty
// number, then seat preference — a treadmill with no end, and each step needs
// an app release. Instead she ASKS when she does not know, and remembers the
// answer here under whatever key it was about. Nothing to pre-program.
//
// Payment details are never stored here and the agent may never fill them.
migrate((app) => {
  const c = app.findCollectionByNameOrId("owner_profile");
  if (!c.fields.getByName("facts")) {
    c.fields.add(new Field({ name: "facts", type: "text", required: false })); // JSON object
  }
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("owner_profile");
    const f = c.fields.getByName("facts");
    if (f) { c.fields.removeById(f.id); app.save(c); }
  } catch (e) {}
});
