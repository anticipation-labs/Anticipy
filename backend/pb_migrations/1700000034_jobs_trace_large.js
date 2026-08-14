/// <reference path="../pb_data/types.d.ts" />

// A sixty-step browser run with real URLs is routinely larger than the text
// field's 5 KB default.  Rejected trace writes were swallowed as best-effort,
// leaving the record frozen halfway through the run.  Retain two complete
// attempts plus recovery markers so the audit is actually post-hoc usable.
migrate((app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  const trace = jobs.fields.getByName("trace");
  if (trace) trace.max = 100000;
  app.save(jobs);
}, (app) => {
  try {
    const jobs = app.findCollectionByNameOrId("jobs");
    const trace = jobs.fields.getByName("trace");
    if (trace) trace.max = 5000;
    app.save(jobs);
  } catch (_) {}
});
