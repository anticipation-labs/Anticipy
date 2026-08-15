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
  if (!$os.getenv("GEMINI_API_KEY") && !$os.getenv("OPENROUTER_API_KEY")) {
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
  const startedAt = Date.now();
  // PocketBase serializes registered route callbacks independently; helpers
  // declared outside this callback are not in its lexical environment.
  const auditContent = (content) => {
    if (typeof content === "string") return content;
    if (!Array.isArray(content)) return content;
    return content.map((part) => {
      if (!part || part.type !== "image_url" || !part.image_url
          || typeof part.image_url.url !== "string") return part;
      const url = part.image_url.url;
      const comma = url.indexOf(",");
      const meta = comma >= 0 ? url.slice(0, comma) : "data:unknown;base64";
      const encoded = comma >= 0 ? url.slice(comma + 1) : url;
      return {
        type: "image_url",
        image_url: {
          url: meta + ",[IMAGE_BYTES_REDACTED]",
          sha256: $security.sha256(url),
          encoded_chars: encoded.length,
          approximate_bytes: Math.floor(encoded.length * 3 / 4),
        },
      };
    });
  };
  const auditMessages = (messages) => messages.map((message) => ({
    role: message.role,
    content: auditContent(message.content),
  }));
  const auditProviderPayload = (value) => {
    if (Array.isArray(value)) return value.map(auditProviderPayload);
    if (!value || typeof value !== "object") return value;
    if (value.inlineData && typeof value.inlineData.data === "string") {
      const data = value.inlineData.data;
      return {
        inlineData: {
          mimeType: String(value.inlineData.mimeType || "application/octet-stream"),
          data: "[IMAGE_BYTES_REDACTED]",
          sha256: $security.sha256(data),
          encoded_chars: data.length,
          approximate_bytes: Math.floor(data.length * 3 / 4),
        },
      };
    }
    const out = {};
    for (const key of Object.keys(value)) out[key] = auditProviderPayload(value[key]);
    return out;
  };
  const auditTaskTag = (messages) => {
    const all = JSON.stringify(auditMessages(messages));
    const match = all.match(/\[AUDIT:([A-Za-z0-9._:-]{3,100})\]/);
    return match ? match[1] : "";
  };
  const auditBegin = (app, taskTag, id, ownerRef, selectedModel, clientRequest) => {
    if (!taskTag) return null;
    try {
      const requestJSON = JSON.stringify(clientRequest);
      const rec = new Record(app.findCollectionByNameOrId("agent_llm_audit"));
      rec.set("task_tag", taskTag);
      rec.set("agent_id", id);
      rec.set("owner_ref", ownerRef);
      rec.set("model", selectedModel);
      rec.set("status", "started");
      rec.set("client_request_json", requestJSON);
      rec.set("request_sha256", $security.sha256(requestJSON));
      rec.set("proxy_version", "codex-black-box-v1");
      app.save(rec);
      return rec;
    } catch (err) {
      console.log("agent audit begin failed:", String(err));
      return null;
    }
  };
  const auditFinish = (app, rec, beganAt, fields) => {
    if (!rec) return;
    try {
      rec.set("duration_ms", Date.now() - beganAt);
      for (const key of Object.keys(fields || {})) {
        if (fields[key] !== undefined && fields[key] !== null) rec.set(key, fields[key]);
      }
      const response = String(fields && fields.client_response_json || "");
      if (response) rec.set("response_sha256", $security.sha256(response));
      app.save(rec);
    } catch (err) {
      console.log("agent audit finish failed:", String(err));
    }
  };
  const agentId = e.request.header.get("X-Anticipy-Agent-ID") || "";
  const agentToken = e.request.header.get("X-Anticipy-Agent-Token") || "";
  if (!agentId || agentToken.length < 40) {
    return e.json(400, { error: "agent credentials required" });
  }
  let agentRecord = null;
  try {
    agentRecord = e.app.findFirstRecordByFilter(
      "agents", "agent_id = {:id} && agent_token = {:token} && paired = true",
      { id: agentId, token: agentToken });
  } catch (_) {
    return e.json(403, { error: "not a paired agent" });
  }

  const geminiKey = $os.getenv("GEMINI_API_KEY") || "";
  const openrouterKey = $os.getenv("OPENROUTER_API_KEY") || "";
  if (!geminiKey && !openrouterKey) {
    return e.json(503, { error: "backend has no model configured" });
  }
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
  // A Google model can use Google's direct API. Every other selected model
  // must go through OpenRouter. Do not choose a provider merely because its
  // key exists: that previously made a DeepSeek request run on Gemini while
  // the client and audit request still said DeepSeek.
  const directGeminiModel = model.indexOf("google/") === 0
    ? model.slice("google/".length) : "";
  if (!directGeminiModel && !openrouterKey) {
    return e.json(503, { error: "requested model provider is not configured" });
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
  // Browser responses are compact JSON. Never let an omitted client cap turn
  // into the provider's 65k-token maximum: OpenRouter performs an
  // affordability check against that maximum before generating anything.
  const requestedMax = Number(body.max_tokens || 512);
  const boundedMax = Math.min(4096, Math.max(64,
    isFinite(requestedMax) ? Math.floor(requestedMax) : 512));
  const payload = { model: model, messages: messages, temperature: 0,
                    max_tokens: boundedMax };
  if (body.response_format && body.response_format.type === "json_object") {
    payload.response_format = { type: "json_object" };
  }
  const serialized = JSON.stringify(payload);
  if (serialized.length > 900000) return e.json(413, { error: "model request too large" });

  let taskTag = "";
  let audit = null;
  try {
    taskTag = auditTaskTag(messages);
    if (!taskTag) {
      const sessions = e.app.findRecordsByFilter(
        "agent_audit_sessions",
        "agent_id = {:id} && active = true",
        "-created", 1, 0, { id: agentId });
      const session = sessions && sessions[0];
      const expires = session ? new Date(session.getString("expires_at")).getTime() : 0;
      if (session && expires > Date.now()) taskTag = session.getString("task_tag");
    }
    audit = auditBegin(e.app, taskTag, agentId,
      agentRecord ? agentRecord.getString("owner_ref") : "", model, {
        model: model,
        messages: auditMessages(messages),
        temperature: 0,
        max_tokens: boundedMax,
        response_format: payload.response_format || null,
      });
  } catch (err) {
    // Certification evidence must never break ordinary execution.  The
    // explicit line makes a missing audit row diagnosable instead of silent.
    console.log("agent audit setup failed:", String(err));
  }

  try {
    // Use the direct Google endpoint only for an explicitly selected Google
    // model. OpenRouter receives the selected non-Google model unchanged.
    if (geminiKey && directGeminiModel) {
      let systemText = "";
      const contents = [];
      for (const message of messages) {
        if (message.role === "system") {
          if (typeof message.content === "string") systemText += (systemText ? "\n\n" : "") + message.content;
          continue;
        }
        const parts = [];
        if (typeof message.content === "string") {
          parts.push({ text: message.content });
        } else if (Array.isArray(message.content)) {
          for (const part of message.content) {
            if (part && part.type === "text" && typeof part.text === "string") {
              parts.push({ text: part.text });
            } else if (part && part.type === "image_url" && part.image_url &&
                       typeof part.image_url.url === "string") {
              const match = part.image_url.url.match(/^data:([^;,]+);base64,(.+)$/);
              if (match) parts.push({ inlineData: { mimeType: match[1], data: match[2] } });
            }
          }
        }
        if (parts.length) contents.push({ role: message.role === "assistant" ? "model" : "user", parts: parts });
      }
      if (!contents.length) return e.json(400, { error: "messages contain no usable content" });
      // Gemini 3's current API uses relative thinking levels. A legacy
      // numeric budget is accepted for compatibility but can be ignored in
      // surprising ways: live runs spent ~1,800 of a 2,048-token allowance
      // thinking, then truncated the actual JSON. Low is the supported level
      // for high-throughput agent actions; Gemini 2.x keeps its zero budget.
      const gemini3 = /^gemini-3(?:\.|-)/i.test(directGeminiModel);
      const generationConfig = {
        maxOutputTokens: boundedMax,
        thinkingConfig: gemini3
          ? { thinkingLevel: "low" }
          : { thinkingBudget: 0 },
      };
      // Gemini 3 is optimized for its default temperature; Google warns that
      // forcing a lower value can cause loops and degraded reasoning.
      if (!gemini3) generationConfig.temperature = 0;
      if (body.response_format && body.response_format.type === "json_object") {
        generationConfig.responseMimeType = "application/json";
      }
      const geminiPayload = { contents: contents, generationConfig: generationConfig };
      if (systemText) geminiPayload.systemInstruction = { parts: [{ text: systemText }] };
      const geminiSerialized = JSON.stringify(geminiPayload);
      const auditedGeminiSerialized = JSON.stringify(auditProviderPayload(geminiPayload));
      if (geminiSerialized.length > 900000) return e.json(413, { error: "model request too large" });
      const response = $http.send({
        url: "https://generativelanguage.googleapis.com/v1beta/models/"
          + encodeURIComponent(directGeminiModel) + ":generateContent",
        method: "POST",
        headers: {
          "x-goog-api-key": geminiKey,
          "Content-Type": "application/json",
        },
        body: geminiSerialized,
        timeout: 95,
      });
      if (!response.json) {
        const clientError = JSON.stringify({ error: "model returned no JSON" });
        auditFinish(e.app, audit, startedAt, { provider: "google", provider_model: directGeminiModel, status: "error",
          http_status: 502, provider_request_json: auditedGeminiSerialized,
          client_response_json: clientError, error: "model returned no JSON" });
        return e.json(502, { error: "model returned no JSON" });
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        const providerJSON = JSON.stringify(response.json);
        const clientError = JSON.stringify({ error: "model provider rejected request" });
        auditFinish(e.app, audit, startedAt, { provider: "google", provider_model: directGeminiModel, status: "error",
          http_status: response.statusCode, provider_request_json: auditedGeminiSerialized,
          provider_response_json: providerJSON, client_response_json: clientError,
          error: "model provider rejected request" });
        return e.json(response.statusCode, { error: "model provider rejected request" });
      }
      const candidates = response.json.candidates || [];
      const parts = candidates[0] && candidates[0].content && candidates[0].content.parts || [];
      const text = parts.map((part) => String(part && part.text || "")).join("");
      if (!text) {
        const providerJSON = JSON.stringify(response.json);
        const clientError = JSON.stringify({ error: "model returned no text" });
        auditFinish(e.app, audit, startedAt, { provider: "google", provider_model: directGeminiModel, status: "error",
          http_status: 502, provider_request_json: auditedGeminiSerialized,
          provider_response_json: providerJSON, client_response_json: clientError,
          error: "model returned no text" });
        return e.json(502, { error: "model returned no text" });
      }
      const clientResponse = {
        choices: [{ message: { content: text } }],
        model: directGeminiModel,
        provider: "google",
      };
      const providerJSON = JSON.stringify(response.json);
      const clientJSON = JSON.stringify(clientResponse);
      auditFinish(e.app, audit, startedAt, { provider: "google", provider_model: directGeminiModel, status: "ok",
        http_status: 200, provider_request_json: auditedGeminiSerialized,
        provider_response_json: providerJSON, client_response_json: clientJSON });
      return e.json(200, clientResponse);
    }
    const response = $http.send({
      url: "https://openrouter.ai/api/v1/chat/completions",
      method: "POST",
      headers: {
        "Authorization": "Bearer " + openrouterKey,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://anticipy.ai",
        "X-Title": "Anticipy Claude Version",
      },
      body: serialized,
      timeout: 95,
    });
    if (!response.json) {
      const clientError = JSON.stringify({ error: "model returned no JSON" });
      const auditedOpenrouter = JSON.stringify({ ...payload, messages: auditMessages(messages) });
      auditFinish(e.app, audit, startedAt, { provider: "openrouter", provider_model: model, status: "error",
        http_status: 502, provider_request_json: auditedOpenrouter,
        client_response_json: clientError, error: "model returned no JSON" });
      return e.json(502, { error: "model returned no JSON" });
    }
    const providerJSON = JSON.stringify(response.json);
    const auditedOpenrouter = JSON.stringify({ ...payload, messages: auditMessages(messages) });
    auditFinish(e.app, audit, startedAt, { provider: "openrouter",
      provider_model: String(response.json.model || model),
      status: response.statusCode >= 200 && response.statusCode < 300 ? "ok" : "error",
      http_status: response.statusCode, provider_request_json: auditedOpenrouter,
      provider_response_json: providerJSON, client_response_json: providerJSON,
      error: response.statusCode >= 200 && response.statusCode < 300
        ? "" : "model provider rejected request" });
    return e.json(response.statusCode, response.json);
  } catch (err) {
    const clientError = JSON.stringify({ error: "model proxy unavailable" });
    auditFinish(e.app, audit, startedAt, { status: "error", http_status: 502,
      client_response_json: clientError, error: String(err).slice(0, 1000) });
    return e.json(502, { error: "model proxy unavailable" });
  }
});
