/// <reference path="../pb_data/types.d.ts" />

// ONE DURABLE PROMISE, AT MOST ONE ACTIVE WORKFLOW — IN STORAGE.
//
// The worker already checks before creating, but two processes can both read
// "none" before either writes. A language model cannot solve that race and a
// wording comparison would only make the identity unstable. `commitment_key`
// is a SHA-256 of tenant id + integer memory-node id. The partial unique index
// applies only while work is live, so cancelled/failed/completed history stays
// auditable and a genuinely retried promise can get a new workflow later.
migrate((app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  if (!jobs.fields.getByName("commitment_key")) {
    jobs.fields.add(new Field({
      name: "commitment_key", type: "text", required: false, max: 64,
    }));
  }
  jobs.indexes = (jobs.indexes || [])
    .filter((index) => !String(index).includes("idx_jobs_active_commitment"))
    .concat([
      "CREATE UNIQUE INDEX `idx_jobs_active_commitment` " +
      "ON `jobs` (`commitment_key`) WHERE `commitment_key` != '' " +
      "AND `status` IN ('awaiting_confirm','queued','running','needs_user')",
    ]);
  app.save(jobs);

  const fresh = app.findCollectionByNameOrId("jobs");
  const landed = (fresh.indexes || []).some(
    (index) => String(index).includes("idx_jobs_active_commitment") &&
      String(index).includes("CREATE UNIQUE INDEX") &&
      String(index).includes("awaiting_confirm") &&
      String(index).includes("needs_user"));
  if (!landed) throw new Error("active commitment identity index did not land");
}, (app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  jobs.indexes = (jobs.indexes || [])
    .filter((index) => !String(index).includes("idx_jobs_active_commitment"));
  const field = jobs.fields.getByName("commitment_key");
  if (field) jobs.fields.removeById(field.id);
  app.save(jobs);
});
