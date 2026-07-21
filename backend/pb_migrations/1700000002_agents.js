/// <reference path="../pb_data/types.d.ts" />

// Browser-agent pairing + liveness.
// - agents: one row per browser extension install. The extension creates it
//   with a 6-digit pair_code; the iOS app claims it by writing `owner`.
//   `last_seen` is the extension's heartbeat — the app derives connection
//   health ("last seen 4s ago") from it.
// - jobs gain an `owner` column so work is scoped to the paired owner.
migrate((app) => {
  const agents = new Collection({
    type: "base",
    name: "agents",
    fields: [
      { name: "agent_id", type: "text", required: true, presentable: true },
      { name: "pair_code", type: "text", required: true },
      { name: "owner", type: "text", required: false },
      { name: "paired", type: "bool", required: false },
      { name: "last_seen", type: "date", required: false },
      { name: "browser", type: "text", required: false },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_agent ON agents (agent_id)"],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: "",
    deleteRule: "",
  });
  app.save(agents);

  const jobs = app.findCollectionByNameOrId("jobs");
  jobs.fields.add(new Field({ name: "owner", type: "text", required: false }));
  jobs.fields.add(new Field({ name: "claimed_by", type: "text", required: false }));
  jobs.fields.add(new Field({ name: "claimed_at", type: "date", required: false }));
  app.save(jobs);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("agents")); } catch (e) {}
  try {
    const jobs = app.findCollectionByNameOrId("jobs");
    for (const f of ["owner", "claimed_by", "claimed_at"]) {
      try { jobs.fields.removeByName(f); } catch (e) {}
    }
    app.save(jobs);
  } catch (e) {}
});
