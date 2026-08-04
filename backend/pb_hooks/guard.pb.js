/// <reference path="../pb_data/types.d.ts" />

// The production lock on the data API. With ANTICIPY_SERVICE_TOKEN set, every
// collection read/write (and realtime subscription) requires the shared
// service token — the worker sends it from its env, and the extension and the
// phone receive it through /agent/key once their agent is paired. Without the
// env var nothing changes (local dev stays open).
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

  // ---- anyone who has actually signed in ----
  // A real account token is a BETTER credential than the shared secret, so it
  // passes here. This is strictly widening: nothing that worked before stops
  // working, and it is what lets clients migrate off the shared token one at a
  // time instead of all at once on a single terrifying afternoon.
  try {
    if (e.auth) return e.next();
  } catch (_) {}

  // The dashboard and any properly authenticated superuser session.
  try {
    if (e.hasSuperuserAuth()) return e.next();
  } catch (_) {}

  // Superuser login itself must stay reachable or the dashboard locks out.
  if (path.startsWith("/api/collections/_superusers/")) return e.next();

  // ---- pairing bootstrap (tokenless by necessity) ----
  const agentsBase = "/api/collections/agents/records";
  const pendantsBase = "/api/collections/pendants/records";

  // 1. Agent self-registration: a brand-new record, never born paired/owned.
  if (method === "POST" && path === agentsBase) {
    const b = e.requestInfo().body || {};
    if (!b["paired"] && !b["owner"]) return e.next();
    return e.json(403, { error: "forbidden" });
  }

  // 2. Pair-code lookup: a LIST that names the code it is looking for.
  //    (Without a pair_code filter the list would leak agent ids, and a
  //    paired agent id is what /agent/key trusts.)
  //
  //    THE FILTER MUST MATCH WHOLE. This was `.test()` against the raw filter,
  //    which matches a SUBSTRING — so appending anything to a legal-looking
  //    filter satisfied it and PocketBase then ran the caller's real query:
  //      ?filter=pair_code="000000" || id!=""&perPage=500
  //    That returned every agent row, paired ones included, to an anonymous
  //    caller — proven live against production on 2026-08-03. A paired
  //    agent_id is the ONLY thing /agent/key checks, and it answers with the
  //    service token, the OpenRouter key and the owner's name, email, phone
  //    and birthday. Anchored, the injection has nowhere to live.
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
    const allowed = { owner: 1, paired: 1, last_seen: 1, browser: 1 };
    const b = e.requestInfo().body || {};
    const keys = Object.keys(b);
    const collection = path.startsWith(agentsBase) ? "agents" : "pendants";
    const id = path.split("/").pop();
    let rec = null;
    try { rec = e.app.findRecordById(collection, id); } catch (_) {}
    if (rec && keys.length > 0 && keys.every((k) => allowed[k])) {
      const touchesPairing = "owner" in b || "paired" in b;
      if (!touchesPairing || !rec.getBool("paired")) return e.next();
    }
    return e.json(403, { error: "forbidden" });
  }

  return e.json(403, { error: "forbidden" });
});
