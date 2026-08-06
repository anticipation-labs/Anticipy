/// <reference path="../pb_data/types.d.ts" />

// How many times a job has been STARTED.
//
// The extension requeues any job that has been `running` for more than two
// minutes, so that a task is never lost to a crashed worker or a closed
// Chrome. It counts nothing while it does so, which means a job that cannot
// finish is not retried — it is retried forever.
//
// On 2026-08-06 that ran the same Priya email over and over: each attempt
// opened Gmail, typed into the address field, got nowhere, passed the two
// minute mark, and was handed straight back to the next sweep. Omar watched
// it happen about six times.
//
// Two minutes is also simply short for real work — a booking or a multi-site
// task exceeds it easily. The live worker is skipped via an in-memory set of
// active jobs, but a service-worker restart empties that set, so its own
// running job then looks abandoned to it.
//
// A counter is the honest fix: retrying is right, retrying without end is
// not. Optional and defaulting to unset, so every existing row reads as zero
// and nothing that runs today changes when this lands.
migrate((app) => {
  const c = app.findCollectionByNameOrId("jobs");
  if (!c.fields.getByName("attempts")) {
    c.fields.add(new Field({ name: "attempts", type: "number", required: false }));
  }
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("jobs");
    const f = c.fields.getByName("attempts");
    if (f) c.fields.removeById(f.id);
    app.save(c);
  } catch (e) { /* rollback best effort */ }
});
