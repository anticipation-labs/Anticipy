/// <reference path="../pb_data/types.d.ts" />

// Delivery lanes for jobs (roadmap §6): "" = the browser lane (the paired
// extension, behind the confirmation gate), "research" = the worker's
// server-side research arm. A column rather than a status, so the existing
// status machine (queued/running/awaiting_confirm/…) works identically in
// both lanes and every guard written against statuses keeps holding.
migrate((app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  jobs.fields.add(new Field({ name: "lane", type: "text", required: false }));
  app.save(jobs);
}, (app) => {
  try {
    const jobs = app.findCollectionByNameOrId("jobs");
    jobs.fields.removeByName("lane");
    app.save(jobs);
  } catch (e) {}
});
