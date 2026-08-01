/// <reference path="../pb_data/types.d.ts" />

// Every booking, reservation and signup form asks the same four things:
// first name, last name, email, phone. Omar's live Cactus Club run reached
// the form and stopped — "I need your first name, last name, email address,
// and phone number to complete the reservation" — because she has no idea who
// he is. Knowing the owner is not a per-site feature; it is the identity that
// every form on the internet wants.
//
// Payment details are deliberately NOT here and never will be: page_map
// redacts card fields and the agent is forbidden to fill them.
migrate((app) => {
  const c = app.findCollectionByNameOrId("owner_profile");
  const add = [
    { name: "first_name", type: "text" },
    { name: "last_name", type: "text" },
    { name: "email", type: "text" },
  ];
  for (const f of add) {
    if (!c.fields.getByName(f.name)) {
      c.fields.add(new Field({ ...f, required: false }));
    }
  }
  app.save(c);
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("owner_profile");
    for (const n of ["first_name", "last_name", "email"]) {
      const f = c.fields.getByName(n);
      if (f) c.fields.removeById(f.id);
    }
    app.save(c);
  } catch (e) {}
});
