/// <reference path="../pb_data/types.d.ts" />

// The production lock on the data API. With ANTICIPY_SERVICE_TOKEN set, every
// collection read/write (and realtime subscription) requires the shared
// service token — the worker sends it from its env. Phones use account auth;
// browsers use a private per-agent credential. Neither client receives this
// server-wide secret. Without the env var nothing changes (local dev stays
// open).
//
// The one unauthenticated surface left is the pairing bootstrap, because a
// fresh device has no token yet:
//   - an agent may REGISTER itself (create an agents record, never pre-paired)
//   - a device may LOOK UP an agent/pendant by its pair code (counted and
//     refused past a ceiling — six digits is a guessable secret, see
//     `pairLookup` below)
//   - a device may CLAIM a not-yet-paired record (flip owner/paired once)
// Knowing the 6-digit code on screen is the proof of presence. An already
// paired record can never be re-claimed, and its code is no longer a way to
// read it either. The earlier version of this sentence said a paired record
// could not be re-read at all, which was never true and still isn't: a fresh
// app install finds its own paired agent by naming the high-entropy owner id
// it already holds, and a paired record's last_seen/browser stay tokenlessly
// writable (see the claim branch for why).
routerUse((e) => {
  const token = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  if (!token) return e.next();

  const path = e.request.url.path;
  const method = e.request.method;
  // Opening the SSE channel is harmless on its own (EventSource cannot send
  // headers); the POST that attaches subscriptions to it is what's guarded.
  const guarded =
    path.startsWith("/api/collections/") ||
    (path === "/api/realtime" && method !== "GET");
  if (!guarded) return e.next();

  if (e.request.header.get("X-Anticipy-Token") === token) return e.next();

  const agentsBase = "/api/collections/agents/records";
  const pendantsBase = "/api/collections/pendants/records";

  const body = () => {
    try { return e.requestInfo().body || {}; } catch (_) { return {}; }
  };
  const ownedList = (ownerRef) => {
    const filter = e.request.url.query().get("filter") || "";
    // `&&` can only narrow the owner set. `||` can widen it back out and is
    // never needed by the phone or extension.
    return filter.indexOf(`owner_ref="${ownerRef}"`) >= 0 && filter.indexOf("||") < 0;
  };
  const recordOwner = (collection, id) => {
    try { return e.app.findRecordById(collection, id).getString("owner_ref"); }
    catch (_) { return ""; }
  };

  // SIX DIGITS, AND NOBODY WAS COUNTING THE GUESSES.
  //
  // Both pair-code branches below — the signed-in one and the tokenless
  // bootstrap — answer "which record wears this code?" for anyone who asks,
  // and until now they answered it as often as they were asked. Six digits is
  // a million codes; a script walking them ten a second walks all of them in
  // a day, and a hit on a live code is somebody else's browser claimed
  // against the guesser's account (the attack traced in
  // tests/test_pairing_claim_guard.py). The anchored filter and the perPage
  // cap further down stop one request returning the whole table; neither of
  // them costs an attacker anything per attempt. This does.
  //
  // Same shape as password_reset.pb.js:16-19, the only other guessable
  // six-digit secret in the tree: count the FAILED attempts in a bounded
  // window and refuse once the ceiling is hit. A successful pairing spends
  // nothing, so an ordinary person is untouched — the code is on the screen in
  // front of them, the phone auto-submits at six digits, and a fumbled entry
  // costs one attempt out of ten.
  //
  // A hit on an ALREADY PAIRED record is a failure, not a pairing. Neither
  // claim path will re-claim one (both require paired to be false), so the
  // only thing a guesser gets from it is the row itself: owner id, owner_ref,
  // agent_id. That is also how the header of this file came to claim, wrongly,
  // that a paired record "can never be re-claimed or re-read without the
  // token" — the re-read half was untrue until this branch existed. Refusing
  // it costs the phone nothing: typing an already-paired code has always ended
  // as a thrown error there, because the claim that follows the lookup is
  // refused (AnticipyBackend.swift:399 -> .unreachable), and it means the
  // all-time set of minted codes is not worth walking. Only the codes on
  // screen right now are worth anything.
  //
  // A MISS still falls through to PocketBase, which answers an empty list.
  // The phone needs that to say "That code didn't match" instead of "I can't
  // reach Anticipy right now" (SettingsView.swift:270-284); telling somebody
  // their correct code is wrong, or their wrong code is an outage, is how they
  // give up. The refusal only appears at the ceiling.
  //
  // WHERE THE COUNTER LIVES: e.app.store(), PocketBase's own app-wide
  // key/value store, which is shared across the isolated hook runtimes —
  // measured on 0.30.4 against a local rig, set in one request and read in the
  // next. Not a collection: a row per guess is an attacker-driven disk fill
  // dressed as a defence, and the volume filling is already an outage this
  // service has had. Buckets are plain strings, "<windowStartMs>|<failures>",
  // because only exported primitives are safe to hand between runtimes.
  //
  // WHAT THE KEY IS WORTH: e.realIP() is the caller's address when a trusted
  // proxy header is configured and the connecting address otherwise, so behind
  // Railway's edge every caller currently shares one bucket. That
  // over-throttles rather than under-throttles — legitimate pairings never
  // spend it — and the second, larger all-callers ceiling covers the opposite
  // case: a configured trusted-proxy header is caller-controlled, so per-IP
  // buckets would be free to mint, and that ceiling is what still bounds the
  // walk. It also bounds how many keys this can leave in the store.
  //
  // HONEST SCOPE: this makes the walk slow and loud, it does not end it. The
  // code itself is permanent once minted (agent_auth.pb.js:19-25) and the
  // popup shows it until the install re-registers, so a patient attacker still
  // has a rate-limited walk against however many codes are live. The cure is a
  // code that expires with a popup that refreshes it, which is a change to the
  // pairing ceremony and not this.
  const pairLookup = (collection, code) => {
    const WINDOW_MS = 10 * 60 * 1000;
    const MAX_PER_IP = 10;
    const MAX_ALL = 60;
    const PREFIX = "anticipy_pair_fails:";
    const ALL_KEY = "anticipy_pair_fails_all";

    let store = null;
    try { store = e.app.store(); } catch (_) {}
    if (!store) {
      // Refusing is the honest failure. Serving lookups that nobody is
      // counting is the exact hole this closes, and a pairing that stops
      // working gets reported in minutes where a silently absent throttle
      // gets reported never.
      console.log("pair-code lookup: no app store to count guesses in — refusing");
      return e.json(503, {
        error: "pairing is briefly unavailable",
        detail: "the server cannot count pair code attempts right now",
      });
    }

    const now = Date.now();
    const bucket = (key) => {
      const raw = String(store.get(key) || "");
      const bar = raw.indexOf("|");
      const startedAt = bar > 0 ? parseInt(raw.slice(0, bar), 10) : 0;
      const fails = bar > 0 ? parseInt(raw.slice(bar + 1), 10) : 0;
      // A bucket that is missing, unparseable or older than the window starts
      // again from now. Fixed window, not sliding: one read and one write per
      // failed attempt, and a guesser cannot spend less by pacing himself.
      if (!startedAt || isNaN(startedAt) || isNaN(fails) || now - startedAt >= WINDOW_MS) {
        return { key: key, startedAt: now, fails: 0, rolled: true };
      }
      return { key: key, startedAt: startedAt, fails: fails, rolled: false };
    };

    let ip = "";
    try { ip = String(e.realIP() || ""); } catch (_) {}
    const mine = bucket(PREFIX + (ip || "unknown"));
    const all = bucket(ALL_KEY);
    if (mine.fails >= MAX_PER_IP || all.fails >= MAX_ALL) {
      return e.json(429, {
        error: "too many pair code attempts",
        detail: "wait a few minutes, then read the current code off the extension popup",
      });
    }

    let found = null;
    try {
      found = e.app.findFirstRecordByFilter(
        collection, "pair_code = {:code}", { code: code });
    } catch (_) {}
    if (found && !found.getBool("paired")) return e.next();

    // Two concurrent failures can read the same count and one increment is
    // lost. That costs a guess, not the ceiling, and the alternative is a lock
    // on the pairing path for a defence measured in tens.
    const spend = (b) => {
      try { store.set(b.key, String(b.startedAt) + "|" + (b.fails + 1)); } catch (_) {}
    };
    spend(mine);
    spend(all);
    // Stale per-IP buckets would otherwise sit in memory until the process
    // restarts. Swept only when the all-callers window has just rolled over,
    // so this walk happens at most once every ten minutes and never on the
    // path somebody pairing takes.
    if (all.rolled) {
      try {
        for (const k of Object.keys(store.getAll() || {})) {
          if (k.indexOf(PREFIX) !== 0 || k === mine.key) continue;
          if (bucket(k).rolled) store.remove(k);
        }
      } catch (_) {}
    }
    if (!found) return e.next();
    return e.json(403, {
      error: "that pair code is already paired",
      detail: "read the current code off the extension popup",
    });
  };

  // A Chrome install authenticates as one hidden random credential and may
  // touch only its own agent row and its owner's jobs. It never receives the
  // server-wide service token.
  const agentId = e.request.header.get("X-Anticipy-Agent-ID") || "";
  const agentToken = e.request.header.get("X-Anticipy-Agent-Token") || "";
  if (agentId) {
    // A CREDENTIAL THAT DOES NOT RESOLVE IS A REFUSAL, NOT A SHRUG.
    //
    // This branch was written as "can this credential do the narrow thing?"
    // and never as "was this credential valid?", so an empty lookup fell out
    // of `if (agent)` below and kept walking DOWN the ladder into the
    // anonymous branches. A wrong token, a revoked credential, a deleted
    // agent row and somebody guessing ids all reached the tokenless pairing
    // bootstrap at the bottom of this file and were handed the anonymous
    // surface: a FAILED authentication treated exactly like NO
    // authentication. Silently, too, which is the shape recorded at
    // HANDOFF.md:116-118 — an agent that looks alive while every real read
    // comes back 403, and nothing anywhere saying which of the two it was.
    //
    // So sending `X-Anticipy-Agent-ID` at all now COMMITS the caller to that
    // identity: it resolves, or the request ends here. Nothing changes for a
    // caller that sends no agent headers at all — a fresh unpaired install
    // holds no credential yet, and claiming one anonymously is the bootstrap's
    // whole reason to exist.
    let agent = null;
    // A token shorter than 40 characters cannot match any row: that is the
    // column's own minimum (pb_migrations/1700000026_agent_tokens.js:12). So
    // an id arriving with a short or missing token is not a second policy,
    // it is this same failed lookup with the query skipped.
    if (agentToken.length >= 40) {
      try {
        agent = e.app.findFirstRecordByFilter(
          "agents", "agent_id = {:id} && agent_token = {:token}",
          { id: agentId, token: agentToken });
      } catch (_) {}
    }
    if (agent) {
      const ownerRef = agent.getString("owner_ref");
      if (path === agentsBase + "/" + agent.id && method === "PATCH") {
        const allowed = { agent_token: 1, last_seen: 1, browser: 1 };
        if (Object.keys(body()).every((k) => allowed[k])) return e.next();
      }
      const jobsBase = "/api/collections/jobs/records";
      if (ownerRef && path === jobsBase && method === "GET" && ownedList(ownerRef)) {
        return e.next();
      }
      // EVIDENCE IS NOT WORK PRODUCT.
      //
      // This allowance exists so a Chrome install can report on the job it is
      // running: status, result, trace, the claim. It used to protect only
      // `owner_ref`, which meant the claimant could also write the two columns
      // that describe the world OUTSIDE this process - and therefore mint its
      // own authorisation:
      //
      //   {"watching_until": "<far future>"}  -> a read nobody is watching,
      //     because research_lane.pb.js believes that column is what the PHONE
      //     last wrote. It was one extra request away from being false.
      //   {"lane": ""} or {"lane": "Supervised_Read"}  -> removes the row from
      //     the lease check entirely (the comparison is exact-match), or
      //     launders a research job into browser-claimable work.
      //
      // That is the same shape as the `legacy_uuid` hole a prior audit found in
      // the delete endpoint: a client-authored value trusted as proof about the
      // world. A claimant may describe ITS OWN progress and nothing else.
      const EVIDENCE = { watching_until: 1, lane: 1, owner_ref: 1, owner: 1 };
      if (ownerRef && path.startsWith(jobsBase + "/")) {
        const id = path.split("/").pop();
        if (recordOwner("jobs", id) === ownerRef && (method === "GET" || method === "PATCH")) {
          const b = body();
          const writesEvidence = Object.keys(b).some((k) => EVIDENCE[k]);
          // `owner_ref` echoed back unchanged stays allowed: PocketBase clients
          // resend it, and refusing that breaks ordinary work for no gain.
          const echo = Object.keys(b).every(
            (k) => !EVIDENCE[k] || (k === "owner_ref" && b[k] === ownerRef));
          if (!writesEvidence || echo) return e.next();
        }
      }
      // NARRATION FROM A SUPERVISED READ, and only while it is supervised.
      //
      // A Chrome install could not write an event at all until now, which is
      // correct for everything except the one job kind whose whole output is
      // narration: `lane="supervised_read"` sends back `read_line` (one short
      // sentence in her voice) and `read_fact` (one distilled fact) so the
      // person watching sees what she is reading, as she reads it
      // (`design/day-zero.md` §2). Nothing else — no raw page text, no message
      // body, no subject line ever becomes a row here (LOCAL-FIRST.md:9-11:
      // only conclusions travel).
      //
      // Gated on the SAME evidence as the claim itself
      // (research_lane.pb.js): the named job must be this owner's, in that
      // lane, with `watching_until` still in the future. So the channel is
      // open only while somebody is actually watching, and closes itself
      // within thirty seconds of them looking away — an extension cannot
      // decide on its own that now is a good time to write "facts" into
      // somebody's memory. A flag would have been forgeable by the caller;
      // this is not (side_trip.js:194-198).
      //
      // `owner_ref` is REQUIRED, not merely permitted: the phone reads these
      // back filtered on its account, so an unowned narration row is a line
      // written about somebody that they can never see.
      const eventsBase = "/api/collections/events/records";
      if (ownerRef && path === eventsBase && method === "POST") {
        const b = body();
        const kind = String(b.kind || "");
        // ONE SENTENCE, NOT A PAGE. "Never the mailbox, never a message, never
        // an attachment" is the fourth line of `ContextSource.mail.promises`,
        // and the shape of breaking it is a `read_fact` carrying a pasted
        // message body. A distilled fact is a sentence; the page slice the
        // reader works from is ~5,000 characters (page_map.js:214-247), so a
        // cap here is the difference between the two. It is a mechanism for
        // one promise, not all of it: nothing server-side can tell a short
        // quote from a short conclusion.
        const text = String(b.text || "");
        if ((kind === "read_line" || kind === "read_fact") &&
            b.owner_ref === ownerRef && text.length > 0 && text.length <= 400) {
          let job = null;
          try { job = e.app.findRecordById("jobs", String(b.goal || "")); } catch (_) {}
          if (job && job.getString("owner_ref") === ownerRef &&
              job.getString("lane") === "supervised_read") {
            // Same date idiom as workflow_guard.pb.js:160-161; missing or
            // lapsed both fail closed.
            const rawUntil = job.getString("watching_until");
            const until = rawUntil ? new Date(rawUntil).getTime() : 0;
            if (until > Date.now()) return e.next();
          }
        }
      }
      return e.json(403, { error: "agent is not allowed to access that record" });
    }
    // A THROWN lookup and an EMPTY one are not the same event, and the code
    // above deliberately does not tell them apart: the throw is an
    // infrastructure failure, the empty result is a proven-bad credential.
    // They get the same answer because "I cannot prove this caller is who
    // they say" is a no either way, and a guard that fails open when the
    // database hiccups is a guard you open by making the database hiccup.
    console.log("guard: unrecognized agent credential from " + agentId);
    return e.json(403, { error: "agent credential is not recognized" });
  }

  // ---- the front door ----
  // The auth endpoints live UNDER /api/collections/, so the guard was gating
  // login itself: every attempt to sign in came back as this hook's own
  // {"error":"forbidden"} before PocketBase ever saw it. Caught on the local
  // rig, which is exactly what the rig is for — shipped, it would have made
  // accounts impossible to use while looking like a backend outage.
  // These endpoints ARE the way an unauthenticated person is supposed to
  // introduce themselves; PocketBase validates them itself.
  if (path.indexOf("/api/collections/owners/") === 0 &&
      /\/(auth-with-password|auth-with-oauth2|auth-with-otp|request-otp|auth-refresh|request-password-reset|confirm-password-reset|request-verification|confirm-verification|auth-methods)$/.test(path)) {
    return e.next();
  }
  // Signing UP is the other half of the front door, and it is a plain record
  // create on the owners collection — so the guard blocked it too, and a new
  // person could reach the login screen but never get an account. Who may
  // actually create one is the collection's own createRule, which is where
  // that decision belongs; this hook only stops the request being refused
  // before PocketBase ever considers it.
  if (method === "POST" && path === "/api/collections/owners/records") {
    return e.next();
  }

  // ---- the dashboard ----
  // This MUST stay ABOVE the owner branch. In PocketBase 0.30.4 the
  // load-auth-token middleware fills `e.auth` for ANY auth record, superusers
  // included (`hasSuperuserAuth()` is literally `e.auth != nil &&
  // e.auth.isSuperuser()`), so `if (e.auth)` below was true for a superuser
  // session and this allowance sat downstream of it, unreachable. What that
  // looked like: create the superuser from the `pbinstal` URL the boot log
  // prints, sign in fine (that request carries no token, so e.auth is null),
  // and the Admin UI's very next call — auth-refresh — comes back
  // {"error":"account is not allowed to access that collection"}, which the
  // UI reads as a dead session and bounces to the login screen. Provisioning
  // the missing superuser was never the piece that was missing; this ordering
  // was, and no amount of re-creating the account would have fixed it.
  try {
    if (e.hasSuperuserAuth()) return e.next();
  } catch (_) {}

  // ---- anyone who has actually signed in ----
  // A real account token is a BETTER credential than the shared secret, so it
  // passes here. This is strictly widening: nothing that worked before stops
  // working, and it is what lets clients migrate off the shared token one at a
  // time instead of all at once on a single terrifying afternoon.
  try {
    if (e.auth) {
      const authId = e.auth.id;
      // Auth collection operations on the person's own account.
      const ownersBase = "/api/collections/owners/records";
      if (path === ownersBase + "/" + authId) return e.next();

      const match = path.match(/^\/api\/collections\/(jobs|events|owner_profile|segments|agents|pendants)\/records(?:\/([^/]+))?$/);
      if (!match) return e.json(403, { error: "account is not allowed to access that collection" });
      const collection = match[1];
      const recordId = match[2] || "";
      const b = body();

      // Pair-code lookup is deliberately pre-owner. The subsequent claim is
      // allowed only onto the signed-in account and only while still unpaired.
      // Throttled like the tokenless one: signing up is open (the branch above
      // lets anyone create an owners record), so an account is not a cost an
      // enumerator would notice. Same anchors, same whole-filter match — the
      // only change is that the six digits are captured so the counter can
      // tell a pairing from a guess.
      if (!recordId && method === "GET" && (collection === "agents" || collection === "pendants")) {
        const filter = e.request.url.query().get("filter") || "";
        const pair = filter.match(/^\s*pair_code\s*=\s*"(\d{6})"\s*$/);
        if (pair) return pairLookup(collection, pair[1]);
      }
      if (recordId && method === "PATCH" && (collection === "agents" || collection === "pendants")) {
        let rec = null;
        try { rec = e.app.findRecordById(collection, recordId); } catch (_) {}
        // A claim that names no owner writes a record the extension can never
        // match a job against — the phone believes it paired while the browser
        // stays an orphan. That split-brain shipped once (2026-08-14, the
        // stranger run); blank owners are refused loudly instead.
        if (rec && !rec.getBool("paired") && b.paired === true && b.owner_ref === authId &&
            typeof b.owner === "string" && b.owner.trim() !== "") {
          return e.next();
        }
      }

      if (!recordId && method === "GET" && ownedList(authId)) return e.next();
      if (!recordId && method === "POST" && b.owner_ref === authId) return e.next();
      if (recordId && recordOwner(collection, recordId) === authId) {
        if (!b.owner_ref || b.owner_ref === authId) return e.next();
      }
      return e.json(403, { error: "record belongs to a different owner" });
    }
  } catch (_) {}

  // Superuser LOGIN itself must stay reachable or the dashboard locks out.
  // Reached only when e.auth is empty — i.e. the sign-in request itself, or a
  // session whose token has expired. An authenticated superuser was already
  // let through above; an authenticated OWNER falls to the branch above this
  // one and is refused there, which is why this line cannot become a way for
  // an ordinary account to read the _superusers collection.
  if (path.startsWith("/api/collections/_superusers/")) return e.next();

  // ---- pairing bootstrap (tokenless by necessity) ----
  // 1. Agent self-registration: a brand-new record, never born paired/owned.
  if (method === "POST" && path === agentsBase) {
    const b = e.requestInfo().body || {};
    if (!b["paired"] && !b["owner"]) return e.next();
    return e.json(403, { error: "forbidden" });
  }

  // 2. Pair-code lookup: a LIST that names the code it is looking for.
  //    (Without a pair_code filter the list would leak agent ids, and a
  //    paired agent id was historically part of /agent/key's lookup.)
  //
  //    THE FILTER MUST MATCH WHOLE. This was `.test()` against the raw filter,
  //    which matches a SUBSTRING — so appending anything to a legal-looking
  //    filter satisfied it and PocketBase then ran the caller's real query:
  //      ?filter=pair_code="000000" || id!=""&perPage=500
  //    That returned every agent row, paired ones included, to an anonymous
  //    caller — proven live against production on 2026-08-03. A paired
  //    Older builds let that leaked id reach /agent/key. The current route
  //    also requires the private per-agent token and returns model config,
  //    never the service token or OpenRouter credential. Anchoring remains a
  //    required independent defence against anonymous bulk enumeration.
  if (method === "GET" && (path === agentsBase || path === pendantsBase)) {
    const filter = e.request.url.query().get("filter") || "";
    // Page size is capped too: these branches exist to look ONE record up, so
    // a legitimate caller never needs a large page, and a cap means even a
    // future hole in the filter check cannot become a bulk export.
    const perPage = parseInt(e.request.url.query().get("perPage") || "30", 10);
    if (perPage > 50) return e.json(403, { error: "forbidden" });
    const pair = filter.match(/^\s*pair_code\s*=\s*"(\d{6})"\s*$/);
    if (pair) return pairLookup(path === agentsBase ? "agents" : "pendants", pair[1]);
    // A fresh app install needs its own paired agent back to bootstrap its
    // token; the owner id is a high-entropy device identifier, so naming it
    // is itself proof of ownership. Anchored, and restricted to the shape an
    // id actually has — no quotes, no operators, nothing to append to.
    if (/^\s*owner\s*=\s*"[A-Za-z0-9._-]{8,64}"\s*$/.test(filter)) return e.next();
    return e.json(403, { error: "forbidden" });
  }

  // 3. Claiming: flip owner/paired (agents also heartbeat last_seen/browser)
  //    on a record that is NOT yet paired. Once paired, OWNERSHIP can never be
  //    reassigned without the token.
  //    Honest scope: a paired record's last_seen/browser ARE still writable
  //    tokenlessly, because `touchesPairing` is false for them. That is a
  //    heartbeat timestamp and a user-agent string — the worst an anonymous
  //    caller achieves is making an agent look alive. The earlier comment here
  //    claimed nothing could touch a paired record at all, which was false.
  if (method === "PATCH" &&
      (path.startsWith(agentsBase + "/") || path.startsWith(pendantsBase + "/"))) {
    // `owner_ref` is in the allowed set because the iPhone app has ALWAYS sent
    // {owner, owner_ref, paired} when it claims a code. Without it, a claim
    // whose auth header was missing or stale hit this branch and died 403 —
    // silently, from the customer's point of view: the extension keeps
    // showing the code, the phone shows nothing, and no one can pair. Found
    // live on 2026-08-14 during the first real stranger day-zero run.
    // ...but owner_ref is NOT accepted here, because nothing on this path can
    // verify it. An unauthenticated caller could register their own agent,
    // then PATCH it with a VICTIM's owner_ref harvested by walking pair codes
    // (six digits, no rate limit) — and from that moment their browser is
    // authorized against the victim's account and receives the victim's jobs.
    // The signed-in claim above binds owner_ref === authId, which is the only
    // honest way to accept it; a claim arriving without a usable session must
    // fail LOUDLY rather than half-pair or, worse, pair to a stranger.
    const allowed = { owner: 1, paired: 1, last_seen: 1, browser: 1 };
    const b = e.requestInfo().body || {};
    const keys = Object.keys(b);
    const collection = path.startsWith(agentsBase) ? "agents" : "pendants";
    const id = path.split("/").pop();
    let rec = null;
    try { rec = e.app.findRecordById(collection, id); } catch (_) {}
    if ("owner_ref" in b) {
      return e.json(403, {
        error: "pair from the signed-in app",
        detail: "an owner_ref may only be claimed by the account it belongs to",
      });
    }
    if (rec && keys.length > 0 && keys.every((k) => allowed[k])) {
      const touchesPairing = "owner" in b || "paired" in b;
      // Same blank-owner ban as the signed-in claim path: a pairing flip that
      // names no owner creates the phone-paired/browser-orphaned split-brain.
      const namesOwner = typeof b.owner === "string" && b.owner.trim() !== "";
      if (!touchesPairing || (!rec.getBool("paired") && namesOwner)) return e.next();
    }
    return e.json(403, { error: "forbidden" });
  }

  return e.json(403, { error: "forbidden" });
});
