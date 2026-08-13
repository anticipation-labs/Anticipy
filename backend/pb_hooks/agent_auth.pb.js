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
  try {
    e.app.findFirstRecordByFilter("agents", "agent_id = {:id}", { id: agentId });
    return e.json(409, { error: "agent already registered" });
  } catch (_) {}
  try {
    const token = $security.randomStringWithAlphabet(64, alphabet);
    let pairCode = "";
    for (let i = 0; i < 20 && !pairCode; i++) {
      const candidate = $security.randomStringWithAlphabet(6, "0123456789");
      try { e.app.findFirstRecordByFilter("agents", "pair_code = {:code}", { code: candidate }); }
      catch (_) { pairCode = candidate; }
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
