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
  // The browser click-loop's brain is server-controlled: raising quality for
  // every paired agent is one env change, no extension update. Sonnet-class
  // by default — the cheap tier navigates fine but fumbles last-mile
  // precision (dropdowns, date pickers), proven live 2026-07-31.
  const model = $os.getenv("ANTICIPY_BROWSER_MODEL") || "anthropic/claude-sonnet-4.6";
  // The write token rides along so a paired agent can keep writing once the
  // guard hook is switched on — no extension update needed at flip time.
  // Who the owner is, so a booking or signup form can actually be completed.
  // Every such form asks the same four things; stopping at them is not a
  // per-site problem to solve one site at a time.
  let owner = null;
  try {
    const p = e.app.findFirstRecordByFilter("owner_profile", "id != ''", {});
    if (p) {
      owner = {
        first_name: p.getString("first_name"),
        last_name: p.getString("last_name"),
        email: p.getString("email"),
        phone: p.getString("phone"),
        birthday: p.getString("birthday"),
        facts: p.getString("facts"),
      };
    }
  } catch (_) { owner = null; }
  return e.json(200, {
    openrouter_key: key,
    owner: owner,
    model: model,
    // Used only when the text map is not enough and a screenshot is sent.
    vision_model: $os.getenv("ANTICIPY_VISION_MODEL") || "google/gemini-2.5-flash",
    service_token: $os.getenv("ANTICIPY_SERVICE_TOKEN") || "",
  });
});
