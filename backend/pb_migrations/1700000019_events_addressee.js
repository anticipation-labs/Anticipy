/// <reference path="../pb_data/types.d.ts" />

// Roadmap §7.1: every triaged transcript line now records WHO the owner was
// judged to be talking to (assistant | person | dictation | self, or empty
// when unclassified). The decision alone could not explain a misfire — a
// dictated line that produced "On it" looked identical to a real ask. With
// the addressee stamped beside the decision, every misclassification is
// auditable straight from the event record.
migrate((app) => {
  const c = app.findCollectionByNameOrId("events");
  c.fields.add(new Field({ name: "addressee", type: "text", required: false }));
  app.save(c);
}, (app) => {
  const c = app.findCollectionByNameOrId("events");
  c.fields.removeByName("addressee");
  app.save(c);
});
