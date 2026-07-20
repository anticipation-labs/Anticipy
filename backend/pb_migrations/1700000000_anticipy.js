/// <reference path="../pb_data/types.d.ts" />

// Anticipy pairing backend schema.
// - pendants: one row per physical device, carries a short pair_code + owner link
// - events:   transcript lines + brain decisions streamed app <-> extension
migrate((app) => {
  const pendants = new Collection({
    type: "base",
    name: "pendants",
    fields: [
      { name: "device_id", type: "text", required: true, presentable: true },
      { name: "name", type: "text", required: false },
      { name: "pair_code", type: "text", required: true },
      { name: "owner", type: "text", required: false },
      { name: "paired", type: "bool", required: false },
      { name: "battery", type: "number", required: false },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_device ON pendants (device_id)"],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: "",
    deleteRule: "",
  });
  app.save(pendants);

  const events = new Collection({
    type: "base",
    name: "events",
    fields: [
      { name: "device_id", type: "text", required: true },
      { name: "kind", type: "text", required: true }, // transcript | decision | action | confirm
      { name: "text", type: "text", required: false },
      { name: "decision", type: "text", required: false }, // ignore|act|ask
      { name: "goal", type: "text", required: false },
      { name: "needs_confirmation", type: "bool", required: false },
    ],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: "",
    deleteRule: "",
  });
  app.save(events);
}, (app) => {
  for (const n of ["events", "pendants"]) {
    try { app.delete(app.findCollectionByNameOrId(n)); } catch (e) {}
  }
});
