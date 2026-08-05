/// <reference path="../pb_data/types.d.ts" />

// Two columns that let the brain stop guessing when a conversation ended.
//
// spoken_at — WHEN HE SAID IT, ISO-8601 UTC, stamped by the phone at the
//   moment the line finishes. Until now the events table carried no capture
//   time at all: the only timestamp was PocketBase's own `created`, which is
//   when the network delivered the row. The phone buffers (offline,
//   backgrounded, no signal, a call holding the mic) and then flushes a
//   lump, so a single conversation reached the brain looking like a burst of
//   unrelated fragments seconds apart. Omi ships this exact bug against the
//   same class of pendant (their issue #6551).
//
// parent_line — the id of the earlier event this line CARRIES ON FROM, or
//   its own id when it starts something new. A conversation stops being a
//   span of time and becomes a connected component of these pointers, which
//   is how email threading has worked since 1997 (In-Reply-To) and how the
//   chat-disentanglement benchmarks have defined the task since 2019.
//   Jones & Klinkner (CIKM 2008) swept timeout length across its whole range
//   on hand-labelled data and found any timer caps at 70% precision; there is
//   no number to tune, which is why this is a pointer and not a constant.
//
// Both are TEXT, optional, and read by nothing today. Plain text rather than
// a relation for parent_line on purpose: a self-link is the "new thread"
// answer, and a relation pointing at its own record is awkward to express
// and easy for a strict validator to reject at exactly the wrong moment.
//
// Additive and reversible. Old app builds set neither, and the brain treats
// a missing value as the behaviour it had before these existed — capture
// order falls back to arrival order, and grouping falls back to the
// segmenter. Nothing that runs today changes when this lands.
migrate((app) => {
  const c = app.findCollectionByNameOrId("events");
  if (!c.fields.getByName("spoken_at")) {
    c.fields.add(new Field({ name: "spoken_at", type: "text", required: false }));
  }
  if (!c.fields.getByName("parent_line")) {
    c.fields.add(new Field({ name: "parent_line", type: "text", required: false }));
  }
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("events");
    for (const name of ["spoken_at", "parent_line"]) {
      const f = c.fields.getByName(name);
      if (f) c.fields.removeById(f.id);
    }
    app.save(c);
  } catch (e) { /* rollback best effort */ }
});
