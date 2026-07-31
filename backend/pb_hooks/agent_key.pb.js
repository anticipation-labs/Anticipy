/// <reference path="../pb_data/types.d.ts" />

// A PAIRED browser agent fetches its LLM key here after pairing, so the
// consumer setup never asks a human to copy-paste an API key. The gate is
// "your agent_id must belong to a paired agent record" — the same trust level
// as the rest of the dev-grade collection rules; tightening both together is
// the production-hardening task (locked rules + per-agent tokens).
routerAdd("GET", "/agent/key", (e) => {
  const agentId = e.request.url.query().get("agent_id") || "";
  if (!agentId) return e.json(400, { error: "agent_id required" });
  let rec;
  try {
    rec = e.app.findFirstRecordByFilter("agents", "agent_id = {:id} && paired = true", { id: agentId });
  } catch (_) {
    return e.json(403, { error: "not a paired agent" });
  }
  if (!rec) return e.json(403, { error: "not a paired agent" });
  const key = $os.getenv("OPENROUTER_API_KEY");
  if (!key) return e.json(503, { error: "backend has no key configured" });
  return e.json(200, { openrouter_key: key });
});
