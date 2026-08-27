/// <reference path="../pb_data/types.d.ts" />
//
// internal_todos.position — the founder's hand-ordering.
//
// "Make it so I can reorder them or drag and drop, like push them around
// my hand." A drag that only rearranges the DOM is a lie that lasts until
// the next reload, so the order is a real column.
//
// Float, not integer, deliberately: dropping a task between two others
// assigns the midpoint of its new neighbours, which makes a reorder ONE
// write instead of N. (The PATCH handler creates activity and notification
// rows, and the Railway volume has already been filled once by an activity
// ledger — a scheme that wrote every row on every drag would be that outage
// on a timer.) Midpoints halve toward zero, so the page re-spaces the whole
// list only when a gap collapses below a hair's width — rare, explicit, and
// the only time a drag writes more than one row.
//
// 0 means "never hand-ordered". The page sorts those by its default rules
// and floats them to the top, so a brand-new task is visible, not buried.
//
// Additive only, guarded, re-runnable; down() removes exactly this field.
migrate((app) => {
  const c = app.findCollectionByNameOrId("internal_todos");
  if (!c.fields.getByName("position")) {
    c.fields.add(new NumberField({ name: "position" }));
    app.save(c);
  }
}, (app) => {
  const c = app.findCollectionByNameOrId("internal_todos");
  if (c.fields.getByName("position")) {
    c.fields.removeByName("position");
    app.save(c);
  }
});
