/// <reference path="../pb_data/types.d.ts" />

// Give every row a place to record whose it is.
//
// `events` is the important one: it has NEVER had an owner column
// (1700000000_anticipy.js), which is why one person's transcripts could not be
// separated from another's even in principle, and why the phone's feed had to
// ask for "everything" and hope.
//
// A RELATION, not a text field, for two reasons: the database itself then
// guarantees the id points at a real person, and `cascadeDelete` makes "delete
// everything about me" a property of the schema rather than a script somebody
// has to remember to run.
//
// DELIBERATELY INERT, like 1700000008: every column is nullable, nothing is
// required, no rule changes, no existing row is touched. Old clients keep
// writing rows with no owner_ref and keep working. (Stage 5 of
// design/LOGIN-DESIGN-2026-08-03.md.)
migrate((app) => {
  const owners = app.findCollectionByNameOrId("owners");
  for (const name of ["jobs", "events", "owner_profile", "segments"]) {
    let c;
    try { c = app.findCollectionByNameOrId(name); } catch (_) { continue; }
    if (c.fields.getByName("owner_ref")) continue;
    c.fields.add(new Field({
      name: "owner_ref",
      type: "relation",
      required: false,          // nullable: old clients write without it
      collectionId: owners.id,
      cascadeDelete: true,      // deleting a person really deletes their data
      maxSelect: 1,
    }));
    app.save(c);
  }
}, (app) => {
  for (const name of ["jobs", "events", "owner_profile", "segments"]) {
    try {
      const c = app.findCollectionByNameOrId(name);
      const f = c.fields.getByName("owner_ref");
      if (f) { c.fields.removeById(f.id); app.save(c); }
    } catch (_) {}
  }
});
