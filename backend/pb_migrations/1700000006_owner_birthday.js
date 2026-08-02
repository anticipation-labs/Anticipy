/// <reference path="../pb_data/types.d.ts" />

// Restaurant checkouts ask for a birthday (SevenRooms does, for perks), as do
// airlines, pharmacies and anything age-gated. It belongs with the rest of the
// identity every form wants — not as a Cactus Club special case.
//
// Still deliberately absent, permanently: anything that can spend money.
migrate((app) => {
  const c = app.findCollectionByNameOrId("owner_profile");
  if (!c.fields.getByName("birthday")) {
    c.fields.add(new Field({ name: "birthday", type: "text", required: false })); // YYYY-MM-DD
  }
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("owner_profile");
    const f = c.fields.getByName("birthday");
    if (f) { c.fields.removeById(f.id); app.save(c); }
  } catch (e) {}
});
