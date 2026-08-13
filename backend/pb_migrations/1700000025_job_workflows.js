/// <reference path="../pb_data/types.d.ts" />

// Durable workflow identity and authority for every new Anticipy job.
//
// The old row had only goal/status/result.  That could not answer which
// version was approved, whether two executors were acting concurrently, or
// what evidence justified "done".  Every field remains optional while old
// clients drain; workflow_guard.pb.js applies the strict law whenever a row
// carries workflow_id.
migrate((app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  const fields = [
    ["workflow_id", "text"],
    ["workflow_version", "number"],
    ["workflow_state", "text"],
    ["consequence", "text"],
    ["lineage_key", "text"],
    ["effect_key", "text"],
    ["scope_digest", "text"],
    ["approval", "text"],
    ["receipt", "text"],
    ["reconciliation", "text"],
    ["lease_token", "text"],
    ["lease_until", "date"],
    ["source_event_ids", "text"],
    ["effect_uncertain", "bool"],
  ];
  for (const [name, type] of fields) {
    if (!jobs.fields.getByName(name)) {
      jobs.fields.add(new Field({ name, type, required: false }));
    }
  }
  jobs.indexes = (jobs.indexes || []).filter((i) => !i.includes("idx_jobs_workflow"));
  jobs.indexes.push(
    "CREATE UNIQUE INDEX `idx_jobs_workflow` ON `jobs` (`workflow_id`) WHERE `workflow_id` != ''"
  );
  app.save(jobs);
}, (app) => {
  try {
    const jobs = app.findCollectionByNameOrId("jobs");
    jobs.indexes = (jobs.indexes || []).filter((i) => !i.includes("idx_jobs_workflow"));
    for (const name of ["workflow_id", "workflow_version", "workflow_state",
      "consequence", "lineage_key", "effect_key", "approval", "receipt",
      "reconciliation", "scope_digest", "lease_token", "lease_until",
      "source_event_ids", "effect_uncertain"]) {
      const field = jobs.fields.getByName(name);
      if (field) jobs.fields.removeById(field.id);
    }
    app.save(jobs);
  } catch (_) {}
});
