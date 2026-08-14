/// <reference path="../pb_data/types.d.ts" />

// Canonical workflow params intentionally retain the user's full task,
// authority text, plan, approval, and provenance. A real cart task crossed
// PocketBase's default 5 KB text ceiling (5,012 chars) and was rejected before
// Chrome could claim it. Give durable workflow envelopes practical headroom.
migrate((app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  const params = jobs.fields.getByName("params");
  if (params) params.max = 100000;
  app.save(jobs);
}, (app) => {
  try {
    const jobs = app.findCollectionByNameOrId("jobs");
    const params = jobs.fields.getByName("params");
    if (params) params.max = 5000;
    app.save(jobs);
  } catch (_) {}
});
