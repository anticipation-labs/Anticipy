/// <reference path="../pb_data/types.d.ts" />

// STEP 1 of the capture architecture (see CAPTURE-ARCHITECTURE.md).
//
// A conversation stops being "however long a recognizer happened to live" and
// becomes a ROW that stays open with a rolling last_speech_at. A dropped
// Bluetooth link, a backgrounded app, or a recognizer swap then cannot end a
// conversation — only real silence can.
//
// Everything here is ADDITIVE and nullable: an app build that knows nothing
// about segments keeps posting exactly as it does today.
migrate((app) => {
  const segments = new Collection({
    type: "base",
    name: "segments",
    fields: [
      { name: "owner", type: "text", required: false },
      { name: "status", type: "text", required: true },        // open | closed
      { name: "started_at", type: "text", required: false },   // ISO8601 capture time
      { name: "last_speech_at", type: "text", required: false },
      { name: "ended_at", type: "text", required: false },
      { name: "turn_count", type: "number", required: false },
      { name: "word_count", type: "number", required: false },
      { name: "summary", type: "text", required: false },
      { name: "entities", type: "text", required: false },     // JSON array
      { name: "parent_segment", type: "text", required: false },
      { name: "triaged_through_seq", type: "number", required: false },
      { name: "dirty", type: "bool", required: false },
      { name: "supersedes", type: "text", required: false },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: "",
    deleteRule: "",
  });
  app.save(segments);

  // Additive fields on events. capture_* is the ONLY clock any boundary
  // decision may use — arrival time shatters store-and-forward backlog into
  // false conversations (Omi #6551), and our pendant is store-and-forward.
  const events = app.findCollectionByNameOrId("events");
  const add = [
    { name: "capture_started_at", type: "text" },
    { name: "capture_ended_at", type: "text" },
    { name: "gap_before_ms", type: "number" },
    { name: "seq", type: "number" },
    { name: "boot_id", type: "text" },
    { name: "source", type: "text" },       // phone | pendant
    { name: "backfill", type: "bool" },
    { name: "segment", type: "text" },      // owning segment id
  ];
  for (const f of add) {
    if (!events.fields.getByName(f.name)) {
      events.fields.add(new Field({ ...f, required: false }));
    }
  }
  app.save(events);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("segments")); } catch (e) {}
  try {
    const events = app.findCollectionByNameOrId("events");
    for (const n of ["capture_started_at", "capture_ended_at", "gap_before_ms",
                     "seq", "boot_id", "source", "backfill", "segment"]) {
      const f = events.fields.getByName(n);
      if (f) events.fields.removeById(f.id);
    }
    app.save(events);
  } catch (e) {}
});
