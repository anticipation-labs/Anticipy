/// <reference path="../pb_data/types.d.ts" />

// The browser agent's step-by-step trace. "What did it actually click?" was
// unanswerable after a run — the loop's history lived only in worker memory.
// The extension writes it here as it works, so every run is auditable.
migrate((app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  if (!jobs.fields.getByName("trace")) {
    jobs.fields.add(new Field({ name: "trace", type: "text", required: false }));
  }
  app.save(jobs);
}, (app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  const f = jobs.fields.getByName("trace");
  if (f) { jobs.fields.removeByName("trace"); app.save(jobs); }
});
