/// <reference path="../pb_data/types.d.ts" />

// Write guard for the dev-grade open collection rules.
//
// The collections ship with all rules "" (anyone), which means an
// unauthenticated POST can queue a browser job that the owner's paired Chrome
// executes with his logged-in sessions, and an unauthenticated PATCH can flip
// a held job from awaiting_confirm to queued — walking straight through the
// confirmation gate. This hook requires a shared service token on every
// mutating request to jobs/events/agents.
//
// ENFORCEMENT IS OPT-IN: it only engages when ANTICIPY_REQUIRE_TOKEN=1 AND a
// token is configured. Deploying it disabled changes nothing, so the running
// system (an installed iOS build, an unreloaded extension) cannot be broken
// by shipping it. Flip the env var once every client sends the header.
const GUARDED = ["jobs", "events", "agents"];

function tokenRequired() {
  return $os.getenv("ANTICIPY_REQUIRE_TOKEN") === "1" && !!$os.getenv("ANTICIPY_SERVICE_TOKEN");
}

function authorized(e) {
  if (!tokenRequired()) return true;
  // A signed-in superuser (the admin UI) is always allowed.
  try { if (e.auth && e.auth.isSuperuser && e.auth.isSuperuser()) return true; } catch (_) {}
  const want = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  let got = "";
  try { got = e.request.header.get("X-Anticipy-Token") || ""; } catch (_) {}
  return got === want;
}

function guard(e) {
  const name = e.record ? e.record.collection().name : "";
  if (GUARDED.indexOf(name) !== -1 && !authorized(e)) {
    throw new BadRequestError("service token required");
  }
  e.next();
}

onRecordCreateRequest((e) => guard(e));
onRecordUpdateRequest((e) => guard(e));
onRecordDeleteRequest((e) => guard(e));
