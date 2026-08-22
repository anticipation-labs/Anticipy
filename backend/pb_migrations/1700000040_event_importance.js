/// <reference path="../pb_data/types.d.ts" />

// How much a seeded fact matters, carried on the event that seeds it.
//
// The day-zero interview asks six questions and they are not equal. A boundary —
// "never touch anything to do with my bank" — has to outrank the thing it is a
// boundary on, because recall is ranked (`brain/memory.py` sorts profile facts on
// importance x recency, half-life 30 days) and a briefing takes the top ten. A
// boundary that falls off the end of that list is a boundary she forgets.
//
// `InterviewQuestion.importance` already encodes this on the phone, with 5 for
// who-matters, what-you-do and never-touch. It had no way to travel: `pushEvent`
// sent kind/text/source, and `ingest_profile_events` hard-coded `importance=4`
// for everything. So the field, the comment defending it, and the test asserting
// it were all inert — nothing downstream could observe the value.
//
// Nullable on purpose. Every event written before this migration, and every
// event that is not a profile seed, simply has no importance, and the worker
// reads a missing value as 4 — which is what a calendar or contacts import is
// worth anyway.
migrate((app) => {
  const events = app.findCollectionByNameOrId("events");
  events.fields.add(new NumberField({
    name: "importance",
    required: false,
    min: 1,
    max: 5,
  }));
  app.save(events);
  console.log("events.importance added: seeded facts can carry their own weight");
}, (app) => {
  const events = app.findCollectionByNameOrId("events");
  const field = events.fields.getByName("importance");
  if (field) {
    events.fields.removeById(field.id);
    app.save(events);
  }
});
