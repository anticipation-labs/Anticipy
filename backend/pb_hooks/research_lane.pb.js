/// <reference path="../pb_data/types.d.ts" />

// Which lanes a browser may claim, and on what evidence (roadmap §6).
//
// LANE 1 — "research" NEVER reaches a browser.
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
//      status="queued" without mentioning `lane` gets the excluded lanes
//      appended, so old extensions never even SEE that work — and never
//      head-of-line block on jobs they may not take.
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
//
// LANE 2 — "supervised_read" reaches a browser ONLY while somebody is watching.
//
// A supervised read is the one read-only job that is SUPPOSED to run in the
// owner's own Chrome, because being watched is the entire product argument
// (`design/day-zero.md` §2): you open your mail, she reads it once in the front
// window, and you see every line of it happen. So it is an exemption from the
// rule above — and an exemption is only worth what its evidence is worth.
//
// THE EVIDENCE MAY NOT BE A FLAG. `side_trip.js:194-198` settled this for the
// inbox side trip and it decides this too: a flag "is something another process
// set, and 'another process decided I may read your inbox' is exactly the
// sentence this product cannot afford to be true." A boolean in the params, a
// header, a body field — every one of them is satisfiable by whatever is doing
// the claiming, which makes the guard decorative. There is deliberately no
// escape hatch below that reads the request body.
//
// So the evidence is `jobs.watching_until`: a timestamp the phone pushes to
// now + 30s every ten seconds, and ONLY while `SupervisedReadView` is on screen
// with the scene phase `.active`. Nothing but a foregrounded app in somebody's
// hand can keep it in the future. Background the app, lock the phone, or swipe
// the view away and this branch starts refusing within thirty seconds — the
// read stops itself, and nobody had to remember to stop it.
//
// Deliberately re-checked on EVERY claiming PATCH, not once at the start:
// `claims` is also true for status="running", so the extension's own progress
// updates are refused the moment the lease lapses. Same shape as the
// `stoppedNow()` re-check before irreversible actions (agent_loop.js:5211) —
// permission that was true a minute ago is not permission now.

routerUse((e) => {
  // Everything lives INSIDE the handler: PocketBase serializes hook
  // handlers into isolated VM contexts, so a top-level const is a
  // ReferenceError at request time — proven on a local 0.30.4 before this
  // shipped (the claim guard 400'd EVERY extension claim, browser lane
  // included, while the filter rewrite silently logged and did nothing).
  const QUEUED_POLL = /status\s*=\s*"queued"/;
  const MENTIONS_LANE = /\blane\b/;
  const WORKER_CLAIMANT = "worker-research";
  // The one lane a browser may claim WITHOUT a workflow behind it, and only
  // against a live watch lease. Named once rather than spelled twice below,
  // because the filter rewrite and the claim refusal have to agree — the
  // extension's two copies of the same lane clause drifted exactly this way
  // (background.js:60-73).
  const SUPERVISED_LANE = "supervised_read";

  const path = e.request.url.path;
  const method = e.request.method;
  // AUTHENTICATED, not merely self-declared. `brain/pb.py:21-22` says it in so
  // many words - "It is a ROUTING marker, not a credential; the service token
  // is what authenticates" - and this hook was reading the marker alone. Any
  // client that sets one header switched the whole lane-and-lease block off,
  // and `extension/tests/test_config_base.mjs:197` pins that the extension
  // never sends the service token, so nothing legitimate is lost by demanding
  // it. Same check as agent_auth.pb.js:52-53 and guard.pb.js:30.
  //
  // With no ANTICIPY_SERVICE_TOKEN configured (local rig), fall back to the
  // marker: there is no secret to prove and no guard to bypass.
  const serviceToken = $os.getenv("ANTICIPY_SERVICE_TOKEN") || "";
  const marker = !!e.request.header.get("X-Anticipy-Worker");
  const fromWorker = serviceToken
    ? (marker && e.request.header.get("X-Anticipy-Token") === serviceToken)
    : marker;

  // 1. The claim filter the server applies.
  if (method === "GET" && path === "/api/collections/jobs/records" && !fromWorker) {
    try {
      const q = e.request.url.query();
      const filter = q.get("filter") || "";
      if (QUEUED_POLL.test(filter) && !MENTIONS_LANE.test(filter)) {
        q.set("filter", "(" + filter + ") && lane != \"research\" && lane != \"" + SUPERVISED_LANE + "\"");
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

  // 2. What a browser may claim, and on what evidence.
  if (method === "PATCH" && path.startsWith("/api/collections/jobs/records/")) {
    let b = {};
    try { b = e.requestInfo().body || {}; } catch (_) { b = {}; }
    const claims = ("claimed_by" in b) || b["status"] === "running";
    if (claims && !fromWorker) {
      let rec = null;
      try { rec = e.app.findRecordById("jobs", path.split("/").pop()); } catch (_) {}
      // NORMALISED ONCE, so both comparisons below inherit it. Raw
      // `getString("lane")` against an exact-match literal let `Supervised_Read`
      // or ` research ` escape the research refusal and the lease requirement
      // at the same time - and `lane` was, until the guard fix that accompanies
      // this, a column the claimant could write itself.
      const lane = (rec ? rec.getString("lane") : "").trim().toLowerCase();
      // The claimant NAME is honoured for research and nothing else. It is a
      // legacy belt for a worker build that predates the X-Anticipy-Worker
      // marker, and it is a body field — which is to say, a flag. Extending it
      // to the supervised lane would have handed every reader a one-line
      // bypass of the whole lease (`claimed_by: "worker-research"` and it may
      // read your mail unwatched), which is precisely the failure
      // side_trip.js:194-198 refuses. The worker does not run supervised reads
      // anyway: they exist to happen in the browser you are watching.
      if (lane === "research" && b["claimed_by"] !== WORKER_CLAIMANT) {
        return e.json(403, { error: "research jobs run in the worker, never in a browser" });
      }
      if (lane === SUPERVISED_LANE) {
        // Read the lease off the ROW, never off the request. The hook runs
        // before the update lands, so `rec` is what the PHONE last wrote —
        // a claimant cannot mint its own permission in the same breath as
        // claiming (guard.pb.js:71-77 lets the agent credential PATCH its
        // owner's job; this is what judges that PATCH).
        //
        // Date idiom copied from workflow_guard.pb.js:160-161, which reads
        // `lease_until` the same way: getString on a date column, then
        // new Date(). Missing, unparseable and past all take the same path
        // on purpose — this fails CLOSED, because failing open means reading
        // somebody's mail while they are not there.
        const rawUntil = rec ? rec.getString("watching_until") : "";
        const until = rawUntil ? new Date(rawUntil).getTime() : 0;
        if (!(until > Date.now())) {
          return e.json(403, {
            error: "a read nobody is watching is not a supervised read — open the app and stay on the screen",
          });
        }
      }
    }
    return e.next();
  }

  return e.next();
});
