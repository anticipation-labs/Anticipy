/// <reference path="../pb_data/types.d.ts" />

// SOMEWHERE FOR A PICTURE TO LIVE.
//
// `workflow_guard.pb.js:202-211` refuses to mark ANY job done without a
// receipt whose `verified` is true and whose `evidence` array is non-empty.
// The server has been enforcing that for weeks. What it enforces is a list of
// STRINGS — `url:…`, `title:…`, `page:<hash>`, `facts:…`, `proof:…`
// (extension/agent_loop.js:1728-1748) — an audit index, not something a person
// reads and believes. The browser already takes a real picture
// (extension/agent_loop.js:105-143: a half-scale, quality-45 JPEG, hard-capped
// at 400 KB) and throws it away after one model call.
//
// So "act -> evidence -> done-text WITH PHOTO" was never blocked on Twilio's
// `MediaUrl` parameter, which is what everyone assumed. It was blocked on
// there being nowhere in this product for an image byte to live: zero
// `type: "file"` fields across all 44 prior migrations, and therefore no URL
// for `MediaUrl` to point at. This collection is that place, and nothing more
// than that place.
//
// WHY POCKETBASE'S OWN FILE FIELD AND NOT A BLOB STORE. Files written through
// a file field land under `--dir`, which `backend/start.sh:15` sets to
// `/pb_data` — the attached Railway volume, the same disk `data.db` has
// survived every redeploy on. Container filesystems on Railway are ephemeral;
// this one is not, and the whole product already bets on that. Object storage
// would be a new vendor, a new credential and a monthly bill for a feature
// that is one screenshot per completed errand.
//
// WHAT THAT COSTS, HONESTLY. That volume is 5 GB, it filled once, and
// PocketBase could not open its database: "disk I/O error", crash loop, hard
// outage (audit_retention.pb.js:3-11; `backend/start.sh` exists because of
// it). Worse for images specifically: PocketBase zips pb_data — storage
// included — into /pb_data/backups, on the same volume it is a snapshot of,
// and keeps two (1700000037_backup_footprint.js, which cut it from seven for
// exactly this reason). Peak footprint is therefore THREE copies of every
// stored byte: two kept plus the one being written. Nothing reclaims them
// either, so a snapshot taken while this table was oversized pins that size
// for the next two days and a restart cannot undo it. Hence the two ceilings
// below and the sweep in `evidence.pb.js` — a cap written only in a design
// note is a cap that does not exist.
//
// WHY UPDATE AND DELETE ARE SUPERUSER-ONLY. `share_expires` on this row is
// what makes a public URL live or dead (evidence.pb.js). A caller who can
// PATCH it can mint itself a permanent public link to somebody's booking
// confirmation. `create`/`view`/`list` are `""` — the same posture as `jobs`
// (1700000001_jobs.js:17): not public, gated by guard.pb.js, which now knows
// this collection by name. Erasure happens through account_delete.pb.js and
// the sweep, both of which run as superuser and bypass rules.
migrate((app) => {
  const evidence = new Collection({
    type: "base",
    name: "evidence",
    fields: [
      // Owner scoping is not optional here the way it is on older rows. This
      // is the densest thing the product will ever store about somebody — a
      // photograph of a page they were logged into — and an unowned one is a
      // picture nobody can see and nobody can erase.
      { name: "owner_ref", type: "text", required: true },
      // The job whose receipt this proves.
      { name: "job", type: "text", required: true },
      // Bound to the exact effect the receipt names, so a picture of one
      // action can never be attached to a different one. workflow_guard
      // already refuses a receipt whose effect_key disagrees with the row;
      // this keeps the picture on the same leash.
      { name: "effect_key", type: "text", required: false },
      {
        name: "image", type: "file", required: false,
        maxSelect: 1,
        // The extension's own screenshot ceiling (agent_loop.js:129). Any
        // other number means a capture that succeeded in Chrome fails at the
        // door for a reason nobody can see from either side.
        maxSize: 400000,
        // An evidence host that accepts arbitrary files is a file host.
        mimeTypes: ["image/jpeg", "image/png"],
      },
      // Empty means NO PUBLIC URL EXISTS. Set only by POST /evidence/share,
      // service token only, minutes at a time.
      { name: "share_expires", type: "date", required: false },
      // Counts fetches through the public door only. Expiry alone leaves a
      // leaked URL an unlimited download for the length of the window.
      { name: "fetches", type: "number", required: false },
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    listRule: "",
    viewRule: "",
    createRule: "",
    updateRule: null,
    deleteRule: null,
  });
  evidence.indexes = [
    "CREATE INDEX `idx_evidence_owner` ON `evidence` (`owner_ref`)",
    "CREATE INDEX `idx_evidence_job` ON `evidence` (`job`)",
  ];
  app.save(evidence);

  // Read it back. 1700000044_purges_markable.js:39-47 — a rule that did not
  // land is invisible until the next real request, and the failure this one
  // would hide is "the picture is public forever", not "the picture is
  // missing".
  const fresh = app.findCollectionByNameOrId("evidence");
  const image = fresh.fields.getByName("image");
  // `type` is a METHOD on the Go-backed field object, not a property. Reading
  // it as `image.type` yields the function itself, `String()` of that is its
  // source text, and the comparison can NEVER be true — so this check failed on
  // a field that had landed perfectly. Verified against pocketbase 0.30.4 on a
  // scratch instance: the stored field is
  //   {"name":"image","id":"file3309110367","maxSize":400000,
  //    "mimeTypes":["image/jpeg","image/png"]}
  // an `id` prefixed `file`, which is exactly what was being asserted.
  //
  // This is why the evidence host has NEVER been live. The migration threw on
  // every boot, PocketBase refuses to start when a migration throws, and the
  // collection therefore did not exist in production — so `/evidence/share`
  // answered PocketBase's own 404 and everyone read that as "not deployed yet".
  // 1700000013:35-40 already recorded that these are Go-backed objects needing
  // String() before comparison; what it did not say is that some of their
  // members are methods, and String() of a method is not an error, it is a
  // plausible-looking string that never matches.
  if (!image || String(image.type()) !== "file") {
    throw new Error("evidence.image did not land as a file field; got type=" +
      (image ? String(image.type()) : "no field"));
  }
  const landed = (rule) => String(rule === null || rule === undefined ? "null" : rule);
  if (landed(fresh.updateRule) !== "null" || landed(fresh.deleteRule) !== "null") {
    throw new Error("evidence must not be editable or erasable through the API; got update=" +
      landed(fresh.updateRule) + " delete=" + landed(fresh.deleteRule));
  }
  console.log("evidence: a place a receipt photo can live, capped at 400KB, share window closed by default");
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("evidence")); } catch (_) {}
});
