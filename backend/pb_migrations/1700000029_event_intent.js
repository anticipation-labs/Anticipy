/// <reference path="../pb_data/types.d.ts" />

// Typed messages are addressed directly to Anticipy; microphone transcripts
// are ambient speech. Persist that distinction through offline buffering and
// worker restarts instead of asking the model to guess from identical text.
migrate((app) => {
  const events = app.findCollectionByNameOrId("events");
  if (!events.fields.getByName("explicit")) {
    events.fields.add(new Field({ name: "explicit", type: "bool", required: false }));
    app.save(events);
  }
}, (app) => {
  try {
    const events = app.findCollectionByNameOrId("events");
    const field = events.fields.getByName("explicit");
    if (field) events.fields.removeById(field.id);
    app.save(events);
  } catch (_) {}
});
