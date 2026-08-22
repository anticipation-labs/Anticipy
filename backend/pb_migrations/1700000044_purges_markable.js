/// <reference path="../pb_data/types.d.ts" />

// The worker can read the purge queue and erase the memory, and then cannot say
// so. This is the second half of the bug 1700000042 half-fixed.
//
// That migration opened `list` and `view` and left a comment claiming "writes
// stay closed... the worker reads the queue and stamps rows through the same
// token-authenticated path". Those two clauses contradict each other: stamping
// IS a write. `updateRule` stayed `null` — superuser only — so the drain ran to
// completion and died on the last line:
//
//   purge mark failed for lcab1bl9gra5t9a (harmless, will retry): 403 Client
//     Error: Forbidden for url: /api/collections/purges/records/0otud8y9ip2o9j8
//
// Measured on production 2026-08-22 by actually deleting an account rather than
// by reading the code: the same row 403'd on every pass, forever. "Harmless,
// will retry" is true of a transient failure and false of a permissions rule —
// nothing about the next attempt differs, so this is an unbounded loop of the
// same shape as the notify loop fixed earlier the same day.
//
// It is worse than a loop. supervisor.py:243 `continue`s past a failed mark, so
// the row stays memory_purged=false and the queue never empties: every later
// pass re-walks a deletion that is already done, and the product can never tell
// anyone their erasure completed. The privacy promise is exactly the thing left
// unstamped.
//
// `""` is the same posture as list/view and as jobs (1700000001:17): not public.
// guard.pb.js demands ANTICIPY_SERVICE_TOKEN on every /api/collections/* request
// and 403s anything without it, so this opens the stamp to the worker and to
// nothing else. create and delete stay `null` on purpose — a purge request may
// only be born inside account_delete.pb.js, where the account is verified, and
// nothing should ever be able to erase the evidence that an erasure was asked
// for.
migrate((app) => {
  const purges = app.findCollectionByNameOrId("purges");
  purges.updateRule = "";
  app.save(purges);

  // Read it back. A rule that did not land is invisible until the next delete,
  // and 1700000013:35-40 documents that these are Go-backed objects whose
  // fields need String() before they can be compared or logged.
  const fresh = app.findCollectionByNameOrId("purges");
  const landed = String(fresh.updateRule === null ? "null" : fresh.updateRule);
  if (landed !== "") {
    throw new Error("purges.updateRule did not land; got " + landed);
  }
  console.log("purges: update opened to the token gate so a finished purge can be stamped");
}, (app) => {
  const purges = app.findCollectionByNameOrId("purges");
  purges.updateRule = null;
  app.save(purges);
});
