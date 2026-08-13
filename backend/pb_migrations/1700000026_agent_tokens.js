/// <reference path="../pb_data/types.d.ts" />

// A paired Chrome install is a tenant-scoped principal, not a bearer of the
// server's master service token.  The extension creates 256 bits of random
// material locally; PocketBase stores it as a hidden field and uses it only to
// authenticate that exact agent record.
migrate((app) => {
  const agents = app.findCollectionByNameOrId("agents");
  if (!agents.fields.getByName("agent_token")) {
    agents.fields.add(new Field({
      name: "agent_token", type: "text", required: false, hidden: true,
      min: 40, max: 200,
    }));
  }
  app.save(agents);
}, (app) => {
  try {
    const agents = app.findCollectionByNameOrId("agents");
    const field = agents.fields.getByName("agent_token");
    if (field) { agents.fields.removeById(field.id); app.save(agents); }
  } catch (_) {}
});
