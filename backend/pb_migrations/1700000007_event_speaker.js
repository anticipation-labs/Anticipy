/// <reference path="../pb_data/types.d.ts" />

// Local speaker recognition (brief 09): the phone tags each transcript line
// with its LOCAL voice verdict — "owner" (matched his enrolled voiceprint),
// "other" (a different person's voice), or nothing (no verdict). Only this
// one word ever leaves the phone; the voice itself never does. The brain
// uses it as measured evidence of WHO SPOKE: "I'll get into it" in a
// friend's voice is the friend's promise, not the owner's.
//
// Additive and optional — old app builds simply never set it, and the
// brain's honesty wall treats a missing verdict as today's behaviour.
migrate((app) => {
  const c = app.findCollectionByNameOrId("events");
  if (!c.fields.getByName("speaker")) {
    c.fields.add(new Field({ name: "speaker", type: "text", required: false }));
  }
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("events");
    const f = c.fields.getByName("speaker");
    if (f) c.fields.removeById(f.id);
    app.save(c);
  } catch (e) { /* rollback best effort */ }
});
