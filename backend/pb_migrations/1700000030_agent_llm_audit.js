/// <reference path="../pb_data/types.d.ts" />

// Append-only evidence for explicitly tagged browser-agent certification runs.
// Normal customer model calls are not retained.  The proxy creates records
// internally only when an exact prompt contains [AUDIT:<run>:<task>].
migrate((app) => {
  const c = new Collection({
    type: "base",
    name: "agent_llm_audit",
    fields: [
      { name: "task_tag", type: "text", required: true, presentable: true },
      { name: "agent_id", type: "text", required: true },
      { name: "owner_ref", type: "text", required: true },
      { name: "model", type: "text", required: true },
      { name: "provider", type: "text", required: false },
      { name: "status", type: "text", required: true },
      { name: "http_status", type: "number", required: false },
      { name: "duration_ms", type: "number", required: false },
      { name: "request_sha256", type: "text", required: false },
      { name: "response_sha256", type: "text", required: false },
      { name: "client_request_json", type: "text", required: true },
      { name: "provider_request_json", type: "text", required: false },
      { name: "provider_response_json", type: "text", required: false },
      { name: "client_response_json", type: "text", required: false },
      { name: "error", type: "text", required: false },
      { name: "proxy_version", type: "text", required: true },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: [
      "CREATE INDEX idx_agent_llm_audit_task_created ON agent_llm_audit (task_tag, created)",
      "CREATE INDEX idx_agent_llm_audit_agent_created ON agent_llm_audit (agent_id, created)",
    ],
    // The global guard still requires ANTICIPY_SERVICE_TOKEN.  These rules
    // let the service-token audit exporter read records through the API.
    listRule: "",
    viewRule: "",
    createRule: null,
    updateRule: null,
    deleteRule: null,
  });
  app.save(c);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("agent_llm_audit")); } catch (_) {}
});
