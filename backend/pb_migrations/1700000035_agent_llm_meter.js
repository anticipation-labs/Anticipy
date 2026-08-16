/// <reference path="../pb_data/types.d.ts" />

// A spend meter on the agent itself.
//
// /agent/llm authenticated a caller and then let it call forever. There was
// no counter, quota or rate limit anywhere, so one runaway loop — a bug as
// easily as an abuser — could drain the model balance in an hour, and the
// first symptom would be every genuine browser dying on provider 402s with
// nothing anywhere explaining why.
//
// The counter lives on the agent row rather than in a new table on purpose:
// the audit ledger already filled the 5GB volume once and took production
// down. Two fields on an existing row cannot grow.
migrate((app) => {
  const agents = app.findCollectionByNameOrId("agents");
  if (!agents.fields.getByName("llm_calls")) {
    agents.fields.add(new NumberField({ name: "llm_calls", min: 0 }));
  }
  if (!agents.fields.getByName("llm_hour")) {
    agents.fields.add(new TextField({ name: "llm_hour", max: 20 }));
  }
  app.save(agents);
}, (app) => {
  try {
    const agents = app.findCollectionByNameOrId("agents");
    for (const name of ["llm_calls", "llm_hour"]) {
      const f = agents.fields.getByName(name);
      if (f) agents.fields.removeByName(name);
    }
    app.save(agents);
  } catch (_) {}
});
