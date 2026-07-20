/// <reference path="../pb_data/types.d.ts" />

// Action jobs queue: brain -> extension.
migrate((app) => {
  const jobs = new Collection({
    type: "base",
    name: "jobs",
    fields: [
      { name: "goal", type: "text", required: true },
      { name: "params", type: "text", required: false }, // JSON payload
      { name: "status", type: "text", required: true },  // queued|running|awaiting_confirm|done|failed
      { name: "result", type: "text", required: false },
      { name: "device_id", type: "text", required: false },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: "",
    deleteRule: "",
  });
  app.save(jobs);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("jobs")); } catch (e) {}
});
