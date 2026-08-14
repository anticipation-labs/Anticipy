/// <reference path="../pb_data/types.d.ts" />

// A short-lived, service-token-created correlation window ensures specialized
// calls (planner, verifier, recovery) are retained even when their prompt does
// not repeat the tagged goal. The proxy ignores expired/inactive sessions.
migrate((app) => {
  const audit = app.findCollectionByNameOrId("agent_llm_audit");
  if (!audit.fields.getByName("provider_model")) {
    audit.fields.add(new Field({ name: "provider_model", type: "text", required: false }));
    app.save(audit);
  }
  const sessions = new Collection({
    type: "base",
    name: "agent_audit_sessions",
    fields: [
      { name: "task_tag", type: "text", required: true, presentable: true },
      { name: "agent_id", type: "text", required: true },
      { name: "owner_ref", type: "text", required: true },
      { name: "active", type: "bool", required: true },
      { name: "expires_at", type: "date", required: true },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: [
      "CREATE INDEX idx_agent_audit_session_active ON agent_audit_sessions (agent_id, active, created)",
    ],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: "",
    deleteRule: null,
  });
  app.save(sessions);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("agent_audit_sessions")); } catch (_) {}
  try {
    const audit = app.findCollectionByNameOrId("agent_llm_audit");
    const field = audit.fields.getByName("provider_model");
    if (field) audit.fields.removeById(field.id);
    app.save(audit);
  } catch (_) {}
});
