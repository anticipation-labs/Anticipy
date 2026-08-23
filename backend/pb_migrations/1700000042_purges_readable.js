/// <reference path="../pb_data/types.d.ts" />

// The worker could not read the queue it is the only consumer of.
//
// 1700000039 created `purges` with every rule `null`, which in PocketBase means
// SUPERUSER ONLY. The worker authenticates with the shared service token, not
// as a superuser, so its poll came back 403 on every pass:
//
//   purge queue unreadable (retrying): 403 Client Error: Forbidden for url:
//     /api/collections/purges/records?filter=memory_purged=false&perPage=50
//
// Measured on production 2026-08-22, immediately after the collection and its
// consumer shipped together for the first time: a hot retry loop, and — worse
// than the noise — a deletion request that is never honoured. Someone asks for
// their memory to be erased and the queue that would do it is unreadable.
//
// `""` is not "public". It is what jobs (1700000001:17) and every other
// worker-read collection already use, because guard.pb.js is the real gate: with
// ANTICIPY_SERVICE_TOKEN set it demands the token header on every
// /api/collections/* request and 403s anything without it. Making purges match
// puts this collection under exactly the same lock as the job queue rather than
// inventing a second, stricter posture that only had the effect of breaking the
// feature.
//
// Writes stay closed. Only `list` and `view` open, because the worker reads the
// queue and stamps rows through the same token-authenticated path everything
// else uses; nothing anonymous may create or delete a purge request.
migrate((app) => {
  const purges = app.findCollectionByNameOrId("purges");
  purges.listRule = "";
  purges.viewRule = "";
  app.save(purges);
  console.log("purges: list/view opened to the token gate so the worker can drain the queue");
}, (app) => {
  const purges = app.findCollectionByNameOrId("purges");
  purges.listRule = null;
  purges.viewRule = null;
  app.save(purges);
});
