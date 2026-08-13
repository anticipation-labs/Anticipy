/// <reference path="../pb_data/types.d.ts" />

// Stable provider ids make inbound delivery idempotent. Twilio retries a
// webhook when a response is slow or lost; without this field, one text can
// become two owner commands and execute the same approval twice.
migrate((app) => {
  const events = app.findCollectionByNameOrId("events");
  if (!events.fields.getByName("external_event_id")) {
    events.fields.add(new Field({
      name: "external_event_id", type: "text", required: false,
    }));
  }
  events.indexes = (events.indexes || [])
    .filter((i) => !i.includes("idx_events_external_event"))
    .concat([
      "CREATE UNIQUE INDEX `idx_events_external_event` ON `events` (`external_event_id`) WHERE `external_event_id` != ''"
    ]);
  app.save(events);
}, (app) => {
  try {
    const events = app.findCollectionByNameOrId("events");
    events.indexes = (events.indexes || [])
      .filter((i) => !i.includes("idx_events_external_event"));
    const field = events.fields.getByName("external_event_id");
    if (field) events.fields.removeById(field.id);
    app.save(events);
  } catch (_) {}
});
