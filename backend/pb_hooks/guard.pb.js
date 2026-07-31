/// <reference path="../pb_data/types.d.ts" />

// Write guard for the dev-grade open collection rules.
//
// The collections ship with every rule "" (anyone), so an unauthenticated
// POST can queue a browser job that the owner's paired Chrome executes with
// his logged-in sessions, and an unauthenticated PATCH can flip a held job
// from awaiting_confirm to queued — straight through the confirmation gate.
// This requires a shared service token on every mutating request.
//
// ENFORCEMENT IS OPT-IN: it engages only when ANTICIPY_REQUIRE_TOKEN=1 AND
// ANTICIPY_SERVICE_TOKEN is set, so shipping it changes nothing until every
// client sends the header.
//
// TWO PocketBase JSVM RULES THIS FILE OBEYS (learned by taking production
// down for four minutes on 2026-07-31):
//   1. A hook handler runs in an ISOLATED runtime — it cannot see consts or
//      functions declared outside its own body. Everything lives inline, and
//      the duplication between the three handlers is deliberate.
//   2. `e.request` is undefined here; headers come from `e.requestInfo()`,
//      whose keys are lowercased with dashes as underscores.
// Verified locally against pocketbase 0.30.4 across the full matrix
// (disabled / no token / wrong token / right token / reads) before deploy.

onRecordCreateRequest((e) => {
  const guarded = ["jobs", "events", "agents"];
  const name = e.record ? e.record.collection().name : "";
  if (guarded.indexOf(name) === -1) { e.next(); return; }
  const want = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  if (!(want && $os.getenv("ANTICIPY_REQUIRE_TOKEN") === "1")) { e.next(); return; }
  let got = "";
  try { got = (e.requestInfo().headers || {})["x_anticipy_token"] || ""; } catch (err) { got = ""; }
  if (got !== want) { throw new BadRequestError("service token required"); }
  e.next();
});

onRecordUpdateRequest((e) => {
  const guarded = ["jobs", "events", "agents"];
  const name = e.record ? e.record.collection().name : "";
  if (guarded.indexOf(name) === -1) { e.next(); return; }
  const want = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  if (!(want && $os.getenv("ANTICIPY_REQUIRE_TOKEN") === "1")) { e.next(); return; }
  let got = "";
  try { got = (e.requestInfo().headers || {})["x_anticipy_token"] || ""; } catch (err) { got = ""; }
  if (got !== want) { throw new BadRequestError("service token required"); }
  e.next();
});

onRecordDeleteRequest((e) => {
  const guarded = ["jobs", "events", "agents"];
  const name = e.record ? e.record.collection().name : "";
  if (guarded.indexOf(name) === -1) { e.next(); return; }
  const want = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  if (!(want && $os.getenv("ANTICIPY_REQUIRE_TOKEN") === "1")) { e.next(); return; }
  let got = "";
  try { got = (e.requestInfo().headers || {})["x_anticipy_token"] || ""; } catch (err) { got = ""; }
  if (got !== want) { throw new BadRequestError("service token required"); }
  e.next();
});
