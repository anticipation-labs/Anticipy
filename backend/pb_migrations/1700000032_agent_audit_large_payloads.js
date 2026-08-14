/// <reference path="../pb_data/types.d.ts" />

// Browser action prompts include a large accessibility map and screenshot
// metadata. Match the proxy's existing 900 KB request ceiling instead of the
// PocketBase text field's 5 KB default.
migrate((app) => {
  const audit = app.findCollectionByNameOrId("agent_llm_audit");
  for (const name of ["client_request_json", "provider_request_json",
    "provider_response_json", "client_response_json"]) {
    const field = audit.fields.getByName(name);
    if (field) field.max = 1000000;
  }
  const error = audit.fields.getByName("error");
  if (error) error.max = 10000;
  app.save(audit);
}, (app) => {
  try {
    const audit = app.findCollectionByNameOrId("agent_llm_audit");
    for (const name of ["client_request_json", "provider_request_json",
      "provider_response_json", "client_response_json", "error"]) {
      const field = audit.fields.getByName(name);
      if (field) field.max = 5000;
    }
    app.save(audit);
  } catch (_) {}
});
