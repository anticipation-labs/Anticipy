/// <reference path="../pb_data/types.d.ts" />

// ONE PROFILE ROW PER ACCOUNT, ENFORCED BY SQLITE.
//
// The app deliberately saves phone and identity details as independent partial
// writes. Before /me/profile/upsert, both performed list-then-create client-side,
// so simultaneous first saves could make two owner_profile rows. Every reader
// then chose `-updated`, which made whichever request finished last the whole
// truth and appeared to erase the other half of the person's profile.
//
// Preserve the exact newest row for each owner_ref, including explicit empty
// fields, and remove only older duplicates. Do not value-merge: an older phone
// must never resurrect after the newest canonical row intentionally cleared it.
// PocketBase runs all migration callbacks in a DB transaction; if any delete,
// index creation, or verification below throws, both cleanup and schema change
// roll back together and the migration is not marked applied.
migrate((app) => {
  const rows = app.findRecordsByFilter(
    "owner_profile", "owner_ref != ''", "-updated,-created,-id", 0, 0);
  const groups = Object.create(null);
  for (const row of rows) {
    const ref = String(row.getString("owner_ref") || "").trim();
    if (!ref) continue;
    const key = "owner:" + ref;
    if (!groups[key]) groups[key] = [];
    groups[key].push(row);
  }

  let removed = 0;
  for (const key of Object.keys(groups)) {
    const owned = groups[key];
    // Query order is newest first, with created/id as deterministic ties.
    // owned[0] stays byte-for-byte authoritative; only older rows are removed.
    for (let i = 1; i < owned.length; i++) {
      app.delete(owned[i]);
      removed++;
    }
  }

  const profiles = app.findCollectionByNameOrId("owner_profile");
  profiles.indexes = (profiles.indexes || [])
    .filter((index) => !String(index).includes("idx_owner_profile_owner_ref"))
    .concat([
      "CREATE UNIQUE INDEX `idx_owner_profile_owner_ref` " +
      "ON `owner_profile` (`owner_ref`) WHERE `owner_ref` != ''",
    ]);
  app.save(profiles);

  // Verify both sides using this transaction's view: the data is unique and
  // the schema carries the storage-level race barrier. Unknown reads throw and
  // abort rather than allowing the migration to claim success.
  const check = app.findRecordsByFilter(
    "owner_profile", "owner_ref != ''", "-updated,-created,-id", 0, 0);
  const seen = Object.create(null);
  for (const row of check) {
    const ref = String(row.getString("owner_ref") || "").trim();
    if (seen[ref]) throw new Error("duplicate owner_profile remained for " + ref);
    seen[ref] = true;
  }
  const fresh = app.findCollectionByNameOrId("owner_profile");
  const landed = (fresh.indexes || []).some(
    (index) => String(index).includes("idx_owner_profile_owner_ref") &&
      String(index).includes("CREATE UNIQUE INDEX"));
  if (!landed) {
    throw new Error("owner_profile owner_ref unique index did not land");
  }

  console.log("owner_profile: kept newest canonical row per account, removed " +
    removed + " duplicate(s), and made owner_ref unique");
}, (app) => {
  const profiles = app.findCollectionByNameOrId("owner_profile");
  profiles.indexes = (profiles.indexes || [])
    .filter((index) => !String(index).includes("idx_owner_profile_owner_ref"));
  app.save(profiles);
});
