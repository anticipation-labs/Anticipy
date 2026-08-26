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
//
// LANE 3 — "device_calendar" reaches the PHONE and nothing else.
//
// `research/2026-08-26-hands2-better-answer.md` §4 ("rung 0"): the worker queues
// a calendar job, the phone picks it up on the jobs poll it already runs every
// three seconds, EKEventStore executes it, and the phone writes status back on
// the channel it already writes status back on. No OAuth, no refresh token, no
// vendor — the app has held full calendar access since LifeContext.swift:43 and
// has never written a thing.
//
// The same section names the risk in the same breath, and it is the reason this
// block exists rather than a client-side lane filter: *"a device execution lane
// that does not route through the same gate is not a new hand, it is a hole in
// the gate."* So there are two kinds of leg below and they answer different
// questions.
//
// ROUTING — who may claim it, both directions. The browser is excluded from the
// poll and refused at the write, exactly as research is: an extension in the
// wild has no EventKit, so a device errand reaching one is an errand that burns
// its attempts in a browser tab. And the mirror is new: an OWNER SESSION may not
// claim a browser errand. The phone signs in with an account token
// (AnticipyBackend.swift:144), the extension carries a per-agent credential
// (background.js:38-39), and guard.pb.js:447-451 already scopes an account to
// its own rows — VERIFIED, not assumed: `recordOwner(collection, recordId) ===
// authId`. That scoping says which ROWS an account may touch. It has no opinion
// about which LANES, and the lane is the whole distinction here.
//
// The evidence is the credential the request actually carries, never a field in
// the body — the standing rule from side_trip.js:194-198 that the supervised
// lease above is built on. `claimed_by: "phone"` is a claimant asserting its own
// authority and is worth nothing.
//
// SHAPE — what a device errand must BE before it may be live, and this is the
// half that matters. It applies to every caller, the worker included, because it
// is a question about the row and not about who is writing it.
//
//   (a) It must carry a workflow_id. workflow_guard.pb.js:24 opens with
//       `if (!workflow) return e.next();` — a legacy row skips the ENTIRE
//       confirmation gate, silently and with no error anywhere. The browser lane
//       closes this in the client (`workflow_id!=""` in background.js
//       BROWSER_LANE); client code cannot be recalled, so this lane closes it
//       here.
//
//   (b) Its consequence must be "consequential", which is to say: it must be
//       held for a tap. Not because this file has an opinion about approval —
//       it has none, and deliberately contains no approval check of its own —
//       but because the other two values are both holes:
//
//       `read_only` carries an EXEMPTION. `NO_APPROVAL_NEEDED = ["read_only"]`
//       in workflow_guard waves such a row into queued and running with no
//       approval at all, and that exemption is EARNED, in that file's own words,
//       by extension/background.js `runSupervisedReadJob` failing any job whose
//       consequence !== "read_only" — "and nothing in that lane acts on the
//       world". A device lane exists precisely TO act on the world. It would
//       inherit the exemption and none of the backstop.
//
//       And the row arrives stamped that way for real, not in theory:
//       `is_consequential("put dinner with Sara Thursday 7pm on my calendar",
//       explicit=True)` returns FALSE today, because "put" is absent from
//       `_VERBS` and `explicit` short-circuits above the read-only fallback;
//       anticipy_core.py:3549 then mints Consequence.READ_ONLY. Say "schedule
//       dinner Thursday 7pm" and the identical act is held, because `schedul\w*`
//       IS in the list. The WORDING decides, which is Law 1's own complaint
//       about that list, and a gate cannot be built on it.
//
//       `reversible_local` is Shelf 2's act-and-tell, and a calendar write is
//       not admitted to it. `SHELF2_ACT_TYPES = ["local_draft"]`, reach
//       `local_store`, executor `anticipy_store`. Worse, EKEvent.eventIdentifier
//       is assigned BY EVENTKIT ON SAVE, so an undo that says "remove the event
//       whose identifier EventKit gave us" is exactly the shape the redesign
//       spec §6.1 excludes by name: "the undo needs a message id the provider
//       returned — a hole in the recipe, filled by the counterparty, after the
//       act." Admitting it would take a minted-id design ON the device and an
//       amendment to the admitted set. Neither exists (app/ios has no calendar
//       write at all today), so the answer is HELD, and this leg is what makes
//       that answer true rather than intended.
//
//       Anything else — "", a truncated write, a fourth enum, "constructor" —
//       is refused. Polarity is a floor: unrecognised is a rejection, never a
//       default.
//
// The shape legs fire only while the write leaves the row LIVE (queued or
// running), which is the same guard workflow_guard puts on its own legs and for
// the same recorded reason: a refusal on every write "blocks even the write that
// would park or fail it, so the row would hang until its lease expired". A
// malformed device errand must always still be failable.

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
  // NAMED FOR ITS ONE VERB, on purpose. The research §4 declines a general
  // "device lane for arbitrary work" in the same paragraph that recommends this
  // one, because the gate lives server-side and a second execution surface is
  // only as safe as the narrowest thing it can be asked to do. The scope is in
  // the lane string, so widening it is a rename somebody has to type.
  const DEVICE_LANE = "device_calendar";
  // The only consequence a device errand may wear while it is live. An
  // allowlist of one, and the one is the strictest — see the header for why
  // both of the other two are holes rather than options.
  const DEVICE_CONSEQUENCE = "consequential";
  const LIVE = ["queued", "running"];

  // Why a device errand is not safe to run, or "" when it is. Returns the
  // reason rather than a boolean so the refusal can say which leg failed —
  // a 403 that only says "no" is a 403 somebody works around.
  //
  // AN ARRAY WOULD BE AN OBJECT-AS-SET HAZARD if these were keyed lookups, so
  // they are not: `indexOf` has no prototype, and `{ read_only: 1 }[c]` is
  // truthy for "constructor" and every other inherited name. Same argument
  // workflow_guard.pb.js makes three times in its own file.
  const deviceShapeRefusal = (b, rec, wanted) => {
    // EVERY VALUE ON THE TABLE, and all of them have to pass.
    //
    // "body if present, else row" was the obvious spelling and it is the wrong
    // one: it lets a claimant re-declare what the job IS in the same breath as
    // claiming it — `{claimed_by: "phone", consequence: "consequential"}` on a
    // row minted read_only — which is the exact move the supervised lease above
    // refuses ("a claimant cannot mint its own permission in the same breath as
    // claiming"). Reading only the ROW has the mirror-image hole: the write
    // itself could be the thing that spoils the row, and the next claim would
    // be where it is noticed.
    //
    // So both are read and both must be right: the row says it, and this write
    // does not un-say it.
    const stated = (name) => {
      const out = [];
      if (rec) out.push(String(rec.getString(name) || "").trim());
      if (b[name] != null) out.push(String(b[name]).trim());
      return out;
    };
    // workflow_guard.pb.js:24 — `if (!workflow) return e.next();`. No workflow
    // id means the confirmation gate never runs on this row at all.
    const workflows = stated("workflow_id");
    if (!workflows.length || workflows.some((v) => !v)) {
      return "a calendar errand with no workflow skips the confirmation gate entirely";
    }
    const consequences = stated("consequence");
    const wrong = consequences.filter((v) => v !== wanted);
    if (!consequences.length || wrong.length) {
      const consequence = wrong.length ? wrong[0] : "";
      // Named separately because they fail for different reasons and the next
      // person needs to know which argument they are up against.
      if (consequence === "read_only") {
        return "read_only carries an approval exemption that is earned by a "
          + "backstop this lane does not have — a calendar write acts on the world";
      }
      if (consequence === "reversible_local") {
        return "Shelf 2 admits local_draft and nothing else; EventKit assigns "
          + "the event identifier on save, which is the undo shape §6.1 excludes";
      }
      return "a calendar errand must be held for a tap; this one says \""
        + consequence + "\"";
    }
    return "";
  };

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
        q.set("filter", "(" + filter + ") && lane != \"research\" && lane != \""
          + SUPERVISED_LANE + "\" && lane != \"" + DEVICE_LANE + "\"");
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
    // ONE READ OF THE ROW for every leg below. The shape legs need it whether
    // or not this write is a claim, so it can no longer live inside the claim
    // branch.
    let rec = null;
    try { rec = e.app.findRecordById("jobs", path.split("/").pop()); } catch (_) {}
    // NORMALISED ONCE, so every comparison below inherits it. Raw
    // `getString("lane")` against an exact-match literal let `Supervised_Read`
    // or ` research ` escape the research refusal and the lease requirement
    // at the same time - and `lane` was, until the guard fix that accompanies
    // this, a column the claimant could write itself.
    //
    // Read off the ROW and never off the body, for the same reason the
    // supervised lease is: a claimant that could name its own lane could name
    // its way out of every leg here in the same breath as claiming.
    const lane = (rec ? rec.getString("lane") : "").trim().toLowerCase();

    // ---- SHAPE. Every caller, the worker included: this is a question about
    // the row, not about who is writing it. Only while the write leaves the row
    // LIVE, so a malformed device errand can always still be parked or failed.
    if (lane === DEVICE_LANE) {
      const status = String(b["status"] != null ? b["status"]
        : (rec ? rec.getString("status") : ""));
      if (LIVE.indexOf(status) >= 0) {
        const why = deviceShapeRefusal(b, rec, DEVICE_CONSEQUENCE);
        if (why) {
          return e.json(403, {
            error: "that calendar errand is not safe to run yet",
            detail: why,
          });
        }
      }
    }

    const claims = ("claimed_by" in b) || b["status"] === "running";
    if (claims && !fromWorker) {
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
      // ---- ROUTING, both directions, and the superuser is neither hand.
      //
      // WHO IS ASKING, on the credential the request actually carries. The
      // phone signs in with an account token and sends nothing else
      // (AnticipyBackend.swift:144); the extension sends a per-agent
      // credential and never an account token (background.js:38-39,
      // test_config_base.mjs:197); the worker sends the service token and
      // never reaches here at all, because `!fromWorker` guards this whole
      // branch. So an account session on a claim is the phone, and it is the
      // only thing that is.
      //
      // POSITIVE LAW, not the absence of a header: "only an owner session may
      // claim a device errand" fails closed on anything unrecognised, where
      // "anything without an agent header is a phone" would have let a
      // tokenless local client through.
      //
      // A RUNTIME THAT WILL NOT ANSWER IS NOT A SUPERUSER. Reading a thrown
      // `hasSuperuserAuth` as `true` would hand every caller the exemption and
      // switch both legs off at once — one unanswered question and the lane
      // stops existing. This event surface has already differed from the types
      // file twice (test_hook_scope_trap.mjs), so it is not a theoretical
      // catch.
      //
      // THE SUPERUSER EXEMPTION IS SAID IN EXACTLY ONE PLACE — the `if
      // (!superuser)` below. `ownerSession` used to repeat it as `!!e.auth &&
      // !superuser`, which reads like belt and braces and is really dead
      // logic: `ownerSession` is only ever consulted inside that wrapper, so
      // no input can tell the two spellings apart. A mutation run found it
      // (that mutant survived every check), and a defence no test can
      // distinguish from its own absence is not a defence — it is a second
      // copy of a rule, waiting to disagree with the first. If these legs ever
      // move out of the wrapper, the wrapper moves with them.
      let superuser = false;
      try { superuser = e.hasSuperuserAuth(); } catch (_) { superuser = false; }
      const ownerSession = !!e.auth;
      // Placed AFTER the research leg on purpose: an owner session that stamps
      // `claimed_by: "worker-research"` walks past that leg's legacy belt, and
      // this is what catches it on the way out.
      if (!superuser) {
        if (lane === DEVICE_LANE && !ownerSession) {
          return e.json(403, {
            error: "a calendar errand happens on your phone, never in a browser",
          });
        }
        if (lane !== DEVICE_LANE && ownerSession) {
          return e.json(403, {
            error: "your phone does not run browser errands — it approves them",
          });
        }
      }
    }
    return e.next();
  }

  return e.next();
});
