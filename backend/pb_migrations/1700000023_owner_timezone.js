/// <reference path="../pb_data/types.d.ts" />

// Where the owner actually is. Reported by their phone, never asked for.
//
// Two consumer bugs, one column:
//
//   1. The owner's timezone was a SERVER-WIDE constant — ANTICIPY_TZ, default
//      America/Vancouver (brain/llm.py). Every prompt is grounded with "right
//      now it is ...", so a second person onboarding from London would be told
//      Vancouver's time of day, and the quiet hours that stop her texting at
//      night would fire on somebody else's night. It worked only because there
//      has only ever been one user.
//
//   2. Nothing anywhere told her WHERE the owner is. now_line() carries the
//      time and no place, which is how "book dinner" became a booking in
//      Seattle for someone who lives in Vancouver.
//
// An IANA identifier carries both answers and costs the user nothing: no
// permission prompt, no typing, no location services. "America/Vancouver" is
// the clock AND the city.
//
// DELIBERATELY INERT, like 1700000009 and 1700000022: nullable, not required,
// no rule changes, no existing row touched. Old app builds keep writing
// profiles without it and keep working; the brain falls back to the server
// default exactly as it does today.
migrate((app) => {
  let c;
  try {
    c = app.findCollectionByNameOrId("owner_profile");
  } catch (_) {
    return;
  }
  if (c.fields.getByName("timezone")) return;
  c.fields.add(new Field({
    name: "timezone",
    type: "text",
    required: false,          // nullable: old clients write without it
  }));
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("owner_profile");
    const f = c.fields.getByName("timezone");
    if (f) { c.fields.removeById(f.id); app.save(c); }
  } catch (_) {}
});
