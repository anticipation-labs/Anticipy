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
//   - a device may LOOK UP an agent/pendant by its short-lived pair code
//   - a device may CLAIM a not-yet-paired record (flip owner/paired once)
// Knowing the 6-digit code on screen is the proof of presence; a record that
// is already paired can never be re-claimed or re-read without the token.
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

  // A Chrome install authenticates as one hidden random credential and may
  // touch only its own agent row and its owner's jobs. It never receives the
  // server-wide service token.
  const agentId = e.request.header.get("X-Anticipy-Agent-ID") || "";
  const agentToken = e.request.header.get("X-Anticipy-Agent-Token") || "";
  if (agentId && agentToken.length >= 40) {
    let agent = null;
    try {
      agent = e.app.findFirstRecordByFilter(
        "agents", "agent_id = {:id} && agent_token = {:token}",
        { id: agentId, token: agentToken });
    } catch (_) {}
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
      if (ownerRef && path.startsWith(jobsBase + "/")) {
        const id = path.split("/").pop();
        if (recordOwner("jobs", id) === ownerRef && (method === "GET" || method === "PATCH")) {
          const b = body();
          if (!b.owner_ref || b.owner_ref === ownerRef) return e.next();
        }
      }
      return e.json(403, { error: "agent is not allowed to access that record" });
    }
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
      if (!recordId && method === "GET" && (collection === "agents" || collection === "pendants")) {
        const filter = e.request.url.query().get("filter") || "";
        if (/^\s*pair_code\s*=\s*"\d{6}"\s*$/.test(filter)) return e.next();
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
    if (/^\s*pair_code\s*=\s*"\d{6}"\s*$/.test(filter)) return e.next();
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
