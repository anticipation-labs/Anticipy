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
  if (method === "GET" && (path === agentsBase || path === pendantsBase)) {
    const filter = e.request.url.query().get("filter") || "";
    if (/pair_code\s*=\s*"\d{6}"/.test(filter)) return e.next();
    // A fresh app install needs its own paired agent back to bootstrap its
    // token; the owner id is a high-entropy device identifier, so naming it
    // is itself proof of ownership.
    if (/owner\s*=\s*"[^"]{8,}"/.test(filter)) return e.next();
    return e.json(403, { error: "forbidden" });
  }

  // 3. Claiming: flip owner/paired (agents also heartbeat last_seen/browser)
  //    on a record that is NOT yet paired. Once paired, only the token
  //    (or the dashboard) can touch it again.
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
