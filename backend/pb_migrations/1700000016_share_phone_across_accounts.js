/// <reference path="../pb_data/types.d.ts" />

// One phone number may sit on several accounts.
//
// The unique index on owners.phone (1700000008) treated the number as an
// identity, but it never was one: email is the identity, and the number is a
// routing address. Texting still routes by owner_profile / the worker's own
// phone comparison, and password reset looks the account up by EMAIL before
// texting its number — so nothing that runs depends on this index. What it
// did do in practice was refuse every second account a person tried to make,
// with the app blaming the email for it.
migrate((app) => {
  const owners = app.findCollectionByNameOrId("owners");
  owners.indexes = (owners.indexes || [])
    .filter((i) => !i.includes("idx_owners_phone"))
    .concat(["CREATE INDEX `idx_owners_phone` ON `owners` (`phone`)"]);
  app.save(owners);
  console.log("owners.phone is no longer unique");
}, (app) => {
  const owners = app.findCollectionByNameOrId("owners");
  owners.indexes = (owners.indexes || [])
    .filter((i) => !i.includes("idx_owners_phone"))
    .concat(["CREATE UNIQUE INDEX `idx_owners_phone` ON `owners` (`phone`) WHERE `phone` != ''"]);
  app.save(owners);
});
