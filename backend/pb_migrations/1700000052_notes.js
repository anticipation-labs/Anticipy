/// <reference path="../pb_data/types.d.ts" />
//
// internal_notes — a plain notes page for HQ. Shared by the whole team on
// purpose: three people don't need private notebooks inside their own
// dashboard, they need one place where "the wifi password at the studio" and
// "how we talk about pricing" stop living in chat scrollback. Anyone can
// edit (updated_by says who touched it last); deleting stays with the
// creator or an admin, same as everything else here.
//
// All-null API rules — every touch goes through the hook routes.
migrate((app) => {
  try { app.findCollectionByNameOrId("internal_notes"); return; } catch (_) {}
  const c = new Collection({ type: "base", name: "internal_notes", fields: [
    { name: "title",      type: "text", max: 200 },
    { name: "body",       type: "text", max: 50000 },
    { name: "track",      type: "text", max: 32 },
    { name: "created_by", type: "text", max: 32 },
    { name: "updated_by", type: "text", max: 32 },
    { name: "created",    type: "autodate", onCreate: true },
    { name: "updated",    type: "autodate", onCreate: true, onUpdate: true },
  ], indexes: [] });
  app.save(c);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("internal_notes")); } catch (_) {}
});
