/// <reference path="../pb_data/types.d.ts" />

// The research lane never reaches a browser (roadmap §6).
//
// Read-only goals are queued with lane="research" and run in the WORKER via
// Brave Search — the 2026-08-02 tab flood was every research job running in
// the owner's own Chrome. The 0.2.4 extension excludes the lane in its own
// claim filter, but extensions IN THE WILD (0.2.3 and older) poll with
//   status="queued" && (owner="…" || owner="")
// and would claim research work forever. Client code cannot be recalled;
// the server can refuse. Two layers, so one failing does not reopen the
// hole:
//
//   1. The claim POLL is rewritten: a jobs list filtering on
//      status="queued" without mentioning `lane` gets
//      `&& lane != "research"` appended, so old extensions never even SEE
//      research jobs — and never head-of-line block on work they may not
//      take.
//   2. The claim WRITE is refused: a PATCH stamping a claim (claimed_by, or
//      status="running") onto a research-lane job is 403'd unless it comes
//      from the worker. The 0.2.3 claim flow survives a refusal cleanly:
//      it reads the record back, sees its stamp missing, and walks away.
//
// "From the worker" = the X-Anticipy-Worker marker brain/pb.py sends on
// every request, or the worker's own claimant name. This is a ROUTING
// distinction, not a credential — the worker and the extension hold the
// same service token (guard.pb.js), so request shape is the only thing that
// can tell them apart, and spoofing it buys nothing an attacker holding the
// token could not already do.

routerUse((e) => {
  // Everything lives INSIDE the handler: PocketBase serializes hook
  // handlers into isolated VM contexts, so a top-level const is a
  // ReferenceError at request time — proven on a local 0.30.4 before this
  // shipped (the claim guard 400'd EVERY extension claim, browser lane
  // included, while the filter rewrite silently logged and did nothing).
  const QUEUED_POLL = /status\s*=\s*"queued"/;
  const MENTIONS_LANE = /\blane\b/;
  const WORKER_CLAIMANT = "worker-research";

  const path = e.request.url.path;
  const method = e.request.method;
  const fromWorker = !!e.request.header.get("X-Anticipy-Worker");

  // 1. The claim filter the server applies.
  if (method === "GET" && path === "/api/collections/jobs/records" && !fromWorker) {
    try {
      const q = e.request.url.query();
      const filter = q.get("filter") || "";
      if (QUEUED_POLL.test(filter) && !MENTIONS_LANE.test(filter)) {
        q.set("filter", "(" + filter + ") && lane != \"research\"");
        e.request.url.rawQuery = q.encode();
      }
    } catch (err) {
      // The rewrite failing must never take the jobs API down; layer 2
      // below still holds the actual invariant (nothing that isn't the
      // worker ever RUNS a research job).
      console.log("research_lane: filter rewrite failed:", err);
    }
    return e.next();
  }

  // 2. No browser may claim a research job.
  if (method === "PATCH" && path.startsWith("/api/collections/jobs/records/")) {
    let b = {};
    try { b = e.requestInfo().body || {}; } catch (_) { b = {}; }
    const claims = ("claimed_by" in b) || b["status"] === "running";
    if (claims && !fromWorker && b["claimed_by"] !== WORKER_CLAIMANT) {
      let rec = null;
      try { rec = e.app.findRecordById("jobs", path.split("/").pop()); } catch (_) {}
      if (rec && rec.getString("lane") === "research") {
        return e.json(403, { error: "research jobs run in the worker, never in a browser" });
      }
    }
    return e.next();
  }

  return e.next();
});
