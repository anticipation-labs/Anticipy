/// <reference path="../pb_data/types.d.ts" />

// Fresh extension install. The hidden credential is created by the server,
// returned exactly once, and never appears in a collection response.
routerAdd("POST", "/agent/register", (e) => {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const agentId = String(body.agent_id || "").trim();
  if (!/^[A-Za-z0-9._-]{20,100}$/.test(agentId)) {
    return e.json(400, { error: "valid agent_id required" });
  }
  // AN EXCEPTION IS NOT AN ANSWER.
  //
  // Both lookups below used to ask "does this exist?" by calling
  // findFirstRecordByFilter and reading the THROW as "no". That conflates the
  // two things a query can do when it does not return a row: find nothing,
  // which is the answer we want, and fail, which is not an answer at all. It
  // is the same shape as the guard's fall-through fixed alongside this — a
  // failed lookup treated as a pass — and here it had teeth on the pair code:
  // a transient DB error made the candidate look free, and `pair_code` carries
  // NO unique index (only agent_id does, pb_migrations/1700000002_agents.js),
  // so a duplicate SAVES. Two browsers then wear one code and the phone claims
  // whichever row the lookup happens to return first, pairing somebody to a
  // browser that is not theirs.
  //
  // findRecordsByFilter answers with a VALUE: an empty array is "nothing
  // matched", and a throw stays what it always was, a failure. So a database
  // hiccup now refuses the registration instead of quietly minting a collision
  // — and a collision is the one outcome here that cannot be undone by
  // retrying, because the code goes on somebody's screen.
  const existing = (filter, params) =>
    e.app.findRecordsByFilter("agents", filter, "", 1, 0, params) || [];
  try {
    if (existing("agent_id = {:id}", { id: agentId }).length) {
      return e.json(409, { error: "agent already registered" });
    }
  } catch (err) {
    // Previously this throw fell through into registration, and only the
    // unique index on agent_id turned the duplicate into a 500 by accident.
    console.log("agent registration: agent_id lookup failed:", String(err));
    return e.json(503, { error: "could not check the agent id right now" });
  }
  try {
    const token = $security.randomStringWithAlphabet(64, alphabet);
    let pairCode = "";
    for (let i = 0; i < 20 && !pairCode; i++) {
      const candidate = $security.randomStringWithAlphabet(6, "0123456789");
      if (!existing("pair_code = {:code}", { code: candidate }).length) {
        pairCode = candidate;
      }
    }
    if (!pairCode) throw new Error("could not allocate a pair code");
    const record = new Record(e.app.findCollectionByNameOrId("agents"));
    record.set("agent_id", agentId);
    record.set("agent_token", token);
    record.set("pair_code", pairCode);
    record.set("paired", false);
    record.set("browser", String(body.browser || "").slice(0, 500));
    record.set("last_seen", new Date().toISOString());
    e.app.save(record);
    return e.json(200, {
      id: record.id,
      agent_id: agentId,
      agent_token: token,
      pair_code: record.getString("pair_code"),
    });
  } catch (err) {
    console.log("agent registration failed:", String(err));
    return e.json(500, { error: "agent registration failed" });
  }
});

// One-release bridge for installs that were paired before private agent
// credentials existed. They already hold the old service token. The backend
// writes the hidden field and the next /agent/key response causes the client
// to erase that master token permanently.
routerAdd("POST", "/agent/upgrade-credential", (e) => {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  const service = $os.getenv("ANTICIPY_SERVICE_TOKEN") || "";
  if (!service || e.request.header.get("X-Anticipy-Token") !== service) {
    return e.json(403, { error: "upgrade not authorized" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const recordId = String(body.record_id || "");
  const agentId = String(body.agent_id || "");
  let record = null;
  try { record = e.app.findRecordById("agents", recordId); } catch (_) {}
  if (!record || record.getString("agent_id") !== agentId) {
    return e.json(404, { error: "agent not found" });
  }
  const token = record.getString("agent_token")
    || $security.randomStringWithAlphabet(64, alphabet);
  record.set("agent_token", token);
  e.app.save(record);
  return e.json(200, { agent_token: token });
});
