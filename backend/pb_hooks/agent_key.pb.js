/// <reference path="../pb_data/types.d.ts" />

// A PAIRED browser agent fetches its server-controlled model configuration
// here after pairing. The vendor key never leaves this backend. The presented
// id and private per-agent token must resolve to one paired record; collection
// access is independently owner-scoped by guard.pb.js.
routerAdd("GET", "/agent/key", (e) => {
  const agentId = e.request.url.query().get("agent_id") || "";
  const agentToken = e.request.header.get("X-Anticipy-Agent-Token") || "";
  if (!agentId || agentToken.length < 40) return e.json(400, { error: "agent credentials required" });
  let rec;
  try {
    rec = e.app.findFirstRecordByFilter(
      "agents", "agent_id = {:id} && agent_token = {:token} && paired = true",
      { id: agentId, token: agentToken });
  } catch (_) {
    return e.json(403, { error: "not a paired agent" });
  }
  if (!rec) return e.json(403, { error: "not a paired agent" });
  const ownerRef = rec.getString("owner_ref");
  if (!ownerRef) {
    return e.json(409, { error: "paired agent has no canonical owner; pair it again from the signed-in app" });
  }
  if (!$os.getenv("OPENROUTER_API_KEY")) {
    return e.json(503, { error: "backend has no model configured" });
  }
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
    const p = e.app.findFirstRecordByFilter(
      "owner_profile", "owner_ref = {:owner}", { owner: ownerRef });
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
    llm_proxy: true,
    owner_ref: ownerRef,
    owner: owner,
    model: model,
    // Used only when the text map is not enough and a screenshot is sent.
    vision_model: $os.getenv("ANTICIPY_VISION_MODEL") || "google/gemini-2.5-flash",
  });
});

// Model calls are proxied for paired agents. A compromised extension token
// can spend only through the two server-selected models and cannot reveal or
// reuse the long-lived OpenRouter credential anywhere else.
routerAdd("POST", "/agent/llm", (e) => {
  const agentId = e.request.header.get("X-Anticipy-Agent-ID") || "";
  const agentToken = e.request.header.get("X-Anticipy-Agent-Token") || "";
  if (!agentId || agentToken.length < 40) {
    return e.json(400, { error: "agent credentials required" });
  }
  try {
    e.app.findFirstRecordByFilter(
      "agents", "agent_id = {:id} && agent_token = {:token} && paired = true",
      { id: agentId, token: agentToken });
  } catch (_) {
    return e.json(403, { error: "not a paired agent" });
  }

  const key = $os.getenv("OPENROUTER_API_KEY") || "";
  if (!key) return e.json(503, { error: "backend has no model configured" });
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {
    return e.json(400, { error: "valid JSON required" });
  }
  const browserModel = $os.getenv("ANTICIPY_BROWSER_MODEL") || "anthropic/claude-sonnet-4.6";
  const visionModel = $os.getenv("ANTICIPY_VISION_MODEL") || "google/gemini-2.5-flash";
  const model = String(body.model || "");
  if (model !== browserModel && model !== visionModel) {
    return e.json(403, { error: "model is not enabled for browser agents" });
  }
  if (!Array.isArray(body.messages) || body.messages.length < 1 || body.messages.length > 40) {
    return e.json(400, { error: "messages must contain 1 to 40 items" });
  }
  const messages = body.messages.map((message) => ({
    role: String(message && message.role || ""),
    content: message && message.content,
  }));
  if (messages.some((message) => !["system", "user", "assistant"].includes(message.role))) {
    return e.json(400, { error: "unsupported message role" });
  }
  const payload = { model: model, messages: messages, temperature: 0 };
  if (body.response_format && body.response_format.type === "json_object") {
    payload.response_format = { type: "json_object" };
  }
  const serialized = JSON.stringify(payload);
  if (serialized.length > 900000) return e.json(413, { error: "model request too large" });

  try {
    const response = $http.send({
      url: "https://openrouter.ai/api/v1/chat/completions",
      method: "POST",
      headers: {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://anticipy.ai",
        "X-Title": "Anticipy Codex Version",
      },
      body: serialized,
      timeout: 95,
    });
    if (!response.json) return e.json(502, { error: "model returned no JSON" });
    return e.json(response.statusCode, response.json);
  } catch (_) {
    return e.json(502, { error: "model proxy unavailable" });
  }
});
