/// <reference path="../pb_data/types.d.ts" />

// The same bounded meter the model proxy uses, for solves. Two fields on an
// existing row rather than a new table: the audit ledger already filled the
// 5GB volume once and took production down, and a per-call row would do it
// again given a loop.
migrate((app) => {
  const agents = app.findCollectionByNameOrId("agents");
  if (!agents.fields.getByName("solve_calls")) {
    agents.fields.add(new NumberField({ name: "solve_calls", min: 0 }));
  }
  if (!agents.fields.getByName("solve_hour")) {
    agents.fields.add(new TextField({ name: "solve_hour", max: 20 }));
  }
  app.save(agents);
}, (app) => {
  try {
    const agents = app.findCollectionByNameOrId("agents");
    for (const name of ["solve_calls", "solve_hour"]) {
      if (agents.fields.getByName(name)) agents.fields.removeByName(name);
    }
    app.save(agents);
  } catch (_) {}
});
