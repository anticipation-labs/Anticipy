/// <reference path="../pb_data/types.d.ts" />

// Omi port 06 (reasoning bounds): how long one decision took and how many
// model calls it made, stamped by brain/worker.py beside the decision on
// every heard transcript row. overnight/is_the_decision_bounded.py reads
// both: heard_ms above the deadline plus one attempt, or heard_calls above
// the ceiling, is positive proof the deployed worker is not enforcing it.
//
// Additive and optional. Unmeasured rows — an echo ignored before hear(), a
// row from before this migration — carry neither, and the worker never
// writes 0 for "not measured". PocketBase reads an unset number as 0, so the
// gate treats 0/0 as unmeasured rather than as a free decision.
migrate((app) => {
  const c = app.findCollectionByNameOrId("events");
  if (!c.fields.getByName("heard_ms")) {
    c.fields.add(new Field({ name: "heard_ms", type: "number", required: false }));
  }
  if (!c.fields.getByName("heard_calls")) {
    c.fields.add(new Field({ name: "heard_calls", type: "number", required: false }));
  }
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("events");
    for (const name of ["heard_ms", "heard_calls"]) {
      const f = c.fields.getByName(name);
      if (f) c.fields.removeById(f.id);
    }
    app.save(c);
  } catch (e) { /* rollback best effort */ }
});
