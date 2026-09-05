/**
 * src/llm.ts — POST /agent/llm, the model proxy.
 * backend/pb_hooks/agent_key.pb.js:65-422. CONTRACT.md §6.4.
 *
 * Every model call the browser agent makes goes through here. Until this was
 * ported the route answered 503 "llm proxy not yet ported", which on the
 * Cloudflare backend meant the hands could not make ONE model call. The port
 * mirrors the PocketBase hook line for line; where it deliberately differs,
 * the difference is written down beside the code and in the list below.
 *
 * ORDER OF REFUSALS (CONTRACT.md §6.4, rules 1-16), unchanged:
 *   credentials 400 → paired 403 → owner_ref 403 → hourly ceiling 429 →
 *   no key at all 503 → body JSON 400 → model allowlist 403 → provider for
 *   that model 503 → messages 1..40 400 → roles 400 → 900,000 chars 413 →
 *   provider answers.
 *
 * SECRETS AND VARS THIS READS (names only; values are `wrangler secret put`):
 *   GEMINI_API_KEY          direct Google. The hook's name (agent_key.pb.js:202)
 *                           and the name SECRETS.md:298 puts on anticipy-api.
 *   GOOGLE_API_KEY          accepted as an alias of the above — SECRETS.md:94
 *                           rotates GEMINI "as GOOGLE_API_KEY", and the first
 *                           draft of this file used that name.
 *   OPENROUTER_API_KEY      every non-Google model, and Google models too when
 *                           no Gemini key is bound (the hook's routing).
 *   ANTICIPY_BROWSER_MODEL  the two models a paired agent may spend through.
 *   ANTICIPY_VISION_MODEL   Defaults are the hook's (:207-208).
 *   LLM_PROVIDER_BASE       TEST ONLY. Points both provider URLs at a fake
 *                           provider so the contract suite can read what this
 *                           Worker put on the wire. Honoured ONLY for a loopback
 *                           host; anything else is ignored with a log line, so a
 *                           mis-set var can never send a vendor key to a
 *                           stranger's host. Never set it in wrangler.jsonc.
 *
 * THE METER. The brief for this port said "counted from the agent_llm_audit
 * rows"; the hook does not do that and neither does this. The hook counts on
 * the agents row itself (llm_hour + llm_calls, 1700000035_agent_llm_meter.js),
 * because an audit row exists only for a TAGGED certification run — counting
 * those would never reach the ceiling for an ordinary browser, which is the
 * runaway-loop case the ceiling exists for. One deliberate improvement: the
 * hook's read-modify-write can lose increments when one agent's calls overlap;
 * here the increment is a single atomic UPDATE, so every call is counted. The
 * 429 decision itself still reads the row the credential lookup already
 * fetched, exactly as the hook does.
 *
 * ┌──────────────────────────────────────────────────────────────────────┐
 * │ `timeout: 95` — agent_key.pb.js:337 and :389                          │
 * │                                                                      │
 * │ Both provider calls wait up to 95 SECONDS. That is a deliberate      │
 * │ ceiling on a slow model call, and fetch() has no timeout option, so  │
 * │ it is AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) below. Without it a   │
 * │ hung provider would hold the invocation open for as long as the      │
 * │ client stayed connected — a regression by omission.                  │
 * │                                                                      │
 * │ What Workers actually constrain, three different things:             │
 * │  1. CPU time — waiting on fetch() spends none. Not the constraint.   │
 * │  2. Subrequests — 1 provider call + a few D1 statements. Not close.  │
 * │  3. Wall clock — no fixed cap on the fetch handler while the client  │
 * │     is connected and I/O is pending. THIS IS THE OPEN QUESTION.      │
 * │                                                                      │
 * │ UNVERIFIED (2026-09-05), and nothing in this file settles it:        │
 * │  a. Whether Cloudflare's edge terminates a response that has NOT     │
 * │     STARTED after an interval shorter than 95 s. This handler cannot │
 * │     stream early — it must read the provider's whole JSON, translate │
 * │     it and finish the audit row — so a client-facing idle timeout    │
 * │     would bite before this AbortSignal ever fires. The spike is one  │
 * │     line: point the deployed Worker at a deliberately slow loopback  │
 * │     is impossible from the edge, so use a slow public echo and time  │
 * │     the failure. Not run.                                            │
 * │  b. The real providers. This port has been exercised against a fake  │
 * │     provider (scripts/fake_llm_provider.py) under `wrangler dev`     │
 * │     only. Google's and OpenRouter's real answers to these exact      │
 * │     bodies have not been observed from this Worker.                  │
 * │  c. What the edge does when the abort fires mid-body: the code maps  │
 * │     it to the same 502 the extension already retries                 │
 * │     (agent_loop.js modelFetch), which degrades throughput, not       │
 * │     correctness — but that mapping has been proven only in the      │
 * │     local runtime.                                                   │
 * │                                                                      │
 * │ If (a) bites, lower UPSTREAM_TIMEOUT_MS to the measured ceiling. It  │
 * │ is a named constant precisely so it can be lowered from a number.    │
 * └──────────────────────────────────────────────────────────────────────┘
 */
import { json, newRecordId, pbNow, pbTime } from "./pb/wire.ts";

/** agent_key.pb.js:337,389. Kept as a named constant so it can be measured. */
export const UPSTREAM_TIMEOUT_MS = 95_000;

/** agent_key.pb.js:181. Generous for a session, fatal to a loop. */
export const HOURLY_CALL_CEILING = 400;

/**
 * agent_key.pb.js:231-241. 512, not 64, since 2026-09-05: the browser model
 * is a thinking model whose reasoning counts against max_tokens, and at 64 its
 * one-token verdicts came back cut off mid-word on 15 of 22 measured pages
 * (research/evals/login-wall-2026-09-05/FINDINGS.md). The extension floors at
 * the same number (MODEL_REPLY_FLOOR, extension/agent_loop.js); this is the
 * second lock on the same door, for any caller that is not the extension.
 * test/llm-proxy.test.ts pins the two numbers to each other.
 */
export const REPLY_FLOOR = 512;
export const REPLY_CEILING = 4096;

/** agent_key.pb.js:249,327 — the 900,000-character request ceiling. */
export const MAX_REQUEST_CHARS = 900_000;

/**
 * agent_key.pb.js:188-191. BYTE-IDENTICAL to CEILING_429_MARK in
 * extension/agent_loop.js: the extension's retry logic reads the 429 body and
 * stops retrying only when it finds this exact text. Any other 429 is
 * retried three times against a limit that has already tripped.
 */
export const CEILING_429_ERROR = "too many model calls in the last hour";
export const CEILING_429_DETAIL =
  "this browser hit its hourly limit; it resumes at the top of the hour";

/** agent_key.pb.js:207-208. */
export const DEFAULT_BROWSER_MODEL = "anthropic/claude-sonnet-4.6";
export const DEFAULT_VISION_MODEL = "google/gemini-2.5-flash";

/** The real hosts. LLM_PROVIDER_BASE may replace them for a loopback fake. */
export const GOOGLE_BASE = "https://generativelanguage.googleapis.com";
export const OPENROUTER_BASE = "https://openrouter.ai";

/** agent_key.pb.js:130. Kept verbatim so the two ledgers diff clean. */
const PROXY_VERSION = "codex-black-box-v1";

export interface LlmEnv {
  DB: D1Database;
  GEMINI_API_KEY?: string;
  GOOGLE_API_KEY?: string;
  OPENROUTER_API_KEY?: string;
  ANTICIPY_BROWSER_MODEL?: string;
  ANTICIPY_VISION_MODEL?: string;
  LLM_PROVIDER_BASE?: string;
}

/** The paired agents row the credential gate already fetched. NEVER echoed. */
export type AgentRow = Record<string, unknown>;

export interface ChatMessage { role: string; content: unknown }

interface OpenRouterPayload {
  model: string;
  messages: ChatMessage[];
  temperature: 0;
  max_tokens: number;
  response_format?: { type: "json_object" };
}

// ---------------------------------------------------------------------------
// Pure helpers. Exported so test/llm-proxy.test.ts can pin them with no
// network and no D1.
// ---------------------------------------------------------------------------

/** agent_key.pb.js:239-241, character for character. */
export function boundMaxTokens(raw: unknown): number {
  const requested = Number(raw || REPLY_FLOOR);
  return Math.min(REPLY_CEILING, Math.max(REPLY_FLOOR,
    Number.isFinite(requested) ? Math.floor(requested) : REPLY_FLOOR));
}

/** agent_key.pb.js:243-245 and :318-320 — only `json_object` passes through. */
export function wantsJsonObject(responseFormat: unknown): boolean {
  return !!responseFormat && typeof responseFormat === "object" &&
    (responseFormat as { type?: unknown }).type === "json_object";
}

/** agent_key.pb.js:207-208. */
export function enabledModels(env: Pick<LlmEnv, "ANTICIPY_BROWSER_MODEL" | "ANTICIPY_VISION_MODEL">) {
  return {
    browser: env.ANTICIPY_BROWSER_MODEL || DEFAULT_BROWSER_MODEL,
    vision: env.ANTICIPY_VISION_MODEL || DEFAULT_VISION_MODEL,
  };
}

/** agent_key.pb.js:202-203 — either name for the Google key, see header. */
export function providerKeys(env: Pick<LlmEnv, "GEMINI_API_KEY" | "GOOGLE_API_KEY" | "OPENROUTER_API_KEY">) {
  return {
    gemini: env.GEMINI_API_KEY || env.GOOGLE_API_KEY || "",
    openrouter: env.OPENROUTER_API_KEY || "",
  };
}

/**
 * The test-only override, and its seatbelt: a base that is not loopback is
 * ignored, because honouring it would send a vendor key wherever the var
 * points. Config validation, not meaning.
 */
export function providerBase(env: Pick<LlmEnv, "LLM_PROVIDER_BASE">, real: string): string {
  const raw = String(env.LLM_PROVIDER_BASE || "").trim().replace(/\/+$/, "");
  if (!raw) return real;
  let host = "";
  try { host = new URL(raw).hostname; } catch { host = ""; }
  if (host !== "127.0.0.1" && host !== "localhost" && host !== "[::1]") {
    console.log("agent/llm: LLM_PROVIDER_BASE ignored, not a loopback host:", raw.slice(0, 80));
    return real;
  }
  return raw;
}

/** agent_key.pb.js:303. A model-id check, not a meaning check. */
export function isGemini3(bareModel: string): boolean {
  return /^gemini-3(?:\.|-)/i.test(bareModel);
}

/**
 * agent_key.pb.js:298-314. Gemini 3 takes a relative thinking level and keeps
 * its default temperature; Gemini 2.x gets a zero budget and temperature 0.
 */
export function geminiGenerationConfig(
  bareModel: string, boundedMax: number, jsonObject: boolean,
): Record<string, unknown> {
  const gemini3 = isGemini3(bareModel);
  const cfg: Record<string, unknown> = {
    maxOutputTokens: boundedMax,
    thinkingConfig: gemini3 ? { thinkingLevel: "low" } : { thinkingBudget: 0 },
  };
  if (!gemini3) cfg.temperature = 0;
  if (jsonObject) cfg.responseMimeType = "application/json";
  return cfg;
}

/** agent_key.pb.js:271-294 — chat messages to Gemini `contents`. */
export function toGeminiContents(messages: ChatMessage[]): {
  systemText: string;
  contents: Array<{ role: "user" | "model"; parts: Array<Record<string, unknown>> }>;
} {
  let systemText = "";
  const contents: Array<{ role: "user" | "model"; parts: Array<Record<string, unknown>> }> = [];
  for (const message of messages) {
    if (message.role === "system") {
      if (typeof message.content === "string") {
        systemText += (systemText ? "\n\n" : "") + message.content;
      }
      continue;
    }
    const parts: Array<Record<string, unknown>> = [];
    if (typeof message.content === "string") {
      parts.push({ text: message.content });
    } else if (Array.isArray(message.content)) {
      for (const part of message.content as Array<Record<string, unknown> | null>) {
        if (part && part.type === "text" && typeof part.text === "string") {
          parts.push({ text: part.text });
        } else if (part && part.type === "image_url" && part.image_url &&
                   typeof (part.image_url as { url?: unknown }).url === "string") {
          const url = (part.image_url as { url: string }).url;
          const match = url.match(/^data:([^;,]+);base64,(.+)$/);
          if (match) parts.push({ inlineData: { mimeType: match[1], data: match[2] } });
        }
      }
    }
    if (parts.length) {
      contents.push({ role: message.role === "assistant" ? "model" : "user", parts });
    }
  }
  return { systemText, contents };
}

/**
 * agent_key.pb.js:359-380 — Gemini's answer in chat-completions shape, or null
 * when there is no text (the hook's 502 "model returned no text").
 *
 * The hook returns exactly {choices:[{message:{content}}], model, provider}.
 * This adds `finish_reason` and `usage` when Google reports them — additive
 * fields the extension ignores (it reads choices[0].message.content only) and
 * a certification reader wants. CONTRACT.md §6.4 records the superset.
 */
export function translateGemini(providerJson: unknown, bareModel: string): Record<string, unknown> | null {
  const j = (providerJson && typeof providerJson === "object" ? providerJson : {}) as Record<string, unknown>;
  const candidates = Array.isArray(j.candidates) ? j.candidates as Array<Record<string, unknown>> : [];
  const first = candidates[0] && typeof candidates[0] === "object" ? candidates[0] : null;
  const content = first && first.content && typeof first.content === "object"
    ? first.content as Record<string, unknown> : null;
  const parts = content && Array.isArray(content.parts) ? content.parts as Array<Record<string, unknown> | null> : [];
  const text = parts.map((part) => String((part && part.text) || "")).join("");
  if (!text) return null;

  const choice: Record<string, unknown> = { message: { content: text } };
  const finish = first && typeof first.finishReason === "string" ? first.finishReason : "";
  if (finish) {
    choice.finish_reason = finish === "STOP" ? "stop"
      : finish === "MAX_TOKENS" ? "length" : finish.toLowerCase();
  }
  const out: Record<string, unknown> = { choices: [choice], model: bareModel, provider: "google" };
  const usage = j.usageMetadata && typeof j.usageMetadata === "object"
    ? j.usageMetadata as Record<string, unknown> : null;
  if (usage) {
    out.usage = {
      prompt_tokens: Number(usage.promptTokenCount) || 0,
      completion_tokens: Number(usage.candidatesTokenCount) || 0,
      total_tokens: Number(usage.totalTokenCount) || 0,
    };
  }
  return out;
}

/** agent_key.pb.js:113-117. The tag a certification run plants in its prompt. */
export function taskTagOf(auditedMessagesJson: string): string {
  const match = auditedMessagesJson.match(/\[AUDIT:([A-Za-z0-9._:-]{3,100})\]/);
  return match ? match[1] : "";
}

/**
 * agent_key.pb.js:129-146 writes an `agent_llm_audit` row with a request and
 * response SHA-256, for EXPLICITLY TAGGED certification runs only — ordinary
 * customer calls are not retained (1700000030_agent_llm_audit.js:4-5).
 *
 * `$security.sha256` is a hex digest. WebCrypto's is the same primitive; this
 * is the drop-in.
 *
 * KEEP audit_retention's sweep. That table filled the 5GB Railway volume and
 * took production down (1700000037_backup_footprint.js:13-14). D1 has its own
 * ceiling and no volume alarm.
 */
export async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** agent_key.pb.js:69-91 — image bytes never reach the ledger, their hash does. */
async function redactContent(content: unknown): Promise<unknown> {
  if (typeof content === "string" || !Array.isArray(content)) return content;
  return Promise.all(content.map(async (part: unknown) => {
    const p = part as { type?: unknown; image_url?: { url?: unknown } } | null;
    if (!p || p.type !== "image_url" || !p.image_url || typeof p.image_url.url !== "string") return part;
    const url = p.image_url.url;
    const comma = url.indexOf(",");
    const meta = comma >= 0 ? url.slice(0, comma) : "data:unknown;base64";
    const encoded = comma >= 0 ? url.slice(comma + 1) : url;
    return {
      type: "image_url",
      image_url: {
        url: meta + ",[IMAGE_BYTES_REDACTED]",
        sha256: await sha256Hex(url),
        encoded_chars: encoded.length,
        approximate_bytes: Math.floor(encoded.length * 3 / 4),
      },
    };
  }));
}

export async function redactMessages(messages: ChatMessage[]): Promise<ChatMessage[]> {
  return Promise.all(messages.map(async (m) => ({ role: m.role, content: await redactContent(m.content) })));
}

/** agent_key.pb.js:96-112 — the same redaction over Gemini's `inlineData`. */
export async function redactProviderPayload(value: unknown): Promise<unknown> {
  if (Array.isArray(value)) return Promise.all(value.map(redactProviderPayload));
  if (!value || typeof value !== "object") return value;
  const v = value as Record<string, unknown>;
  const inline = v.inlineData as { data?: unknown; mimeType?: unknown } | undefined;
  if (inline && typeof inline.data === "string") {
    const data = inline.data;
    return {
      inlineData: {
        mimeType: String(inline.mimeType || "application/octet-stream"),
        data: "[IMAGE_BYTES_REDACTED]",
        sha256: await sha256Hex(data),
        encoded_chars: data.length,
        approximate_bytes: Math.floor(data.length * 3 / 4),
      },
    };
  }
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(v)) out[key] = await redactProviderPayload(v[key]);
  return out;
}

// ---------------------------------------------------------------------------
// The audit ledger, on D1. agent_llm_audit is NOT in pb/schema.ts COLLECTIONS
// (it is never exposed over /api/collections), so this writes it directly.
// Failures are logged and never break execution — certification evidence
// must not take a customer's browser down (agent_key.pb.js:140-145, :158-160).
// ---------------------------------------------------------------------------

async function auditBegin(
  env: LlmEnv, taskTag: string, agentId: string, ownerRef: string,
  model: string, clientRequest: unknown,
): Promise<string | null> {
  if (!taskTag) return null;
  try {
    const requestJSON = JSON.stringify(clientRequest);
    const id = newRecordId();
    const now = pbNow();
    await env.DB.prepare(
      `INSERT INTO agent_llm_audit
         (id, created, updated, task_tag, agent_id, owner_ref, model, status,
          client_request_json, request_sha256, proxy_version)
       VALUES (?,?,?,?,?,?,?,?,?,?,?)`)
      .bind(id, now, now, taskTag, agentId, ownerRef, model, "started",
            requestJSON, await sha256Hex(requestJSON), PROXY_VERSION)
      .run();
    return id;
  } catch (err) {
    console.log("agent audit begin failed:", String(err));
    return null;
  }
}

/** The columns auditFinish may set — a fixed list, never a caller's key. */
const AUDIT_FINISH_COLUMNS = new Set([
  "provider", "provider_model", "status", "http_status",
  "provider_request_json", "provider_response_json", "client_response_json", "error",
]);

async function auditFinish(
  env: LlmEnv, id: string | null, beganAt: number, fields: Record<string, unknown>,
): Promise<void> {
  if (!id) return;
  try {
    const sets = ["duration_ms = ?", "updated = ?"];
    const vals: unknown[] = [Date.now() - beganAt, pbNow()];
    for (const key of Object.keys(fields)) {
      const v = fields[key];
      if (v === undefined || v === null || !AUDIT_FINISH_COLUMNS.has(key)) continue;
      sets.push(`${key} = ?`);
      vals.push(v);
    }
    const response = String(fields.client_response_json || "");
    if (response) {
      sets.push("response_sha256 = ?");
      vals.push(await sha256Hex(response));
    }
    vals.push(id);
    await env.DB.prepare(`UPDATE agent_llm_audit SET ${sets.join(", ")} WHERE id = ?`)
      .bind(...vals).run();
  } catch (err) {
    console.log("agent audit finish failed:", String(err));
  }
}

// ---------------------------------------------------------------------------
// The one outbound call.
// ---------------------------------------------------------------------------

/**
 * `json` is null when the provider's body was not JSON — the hook's
 * `!response.json`. A timeout or a transport failure THROWS, exactly as
 * $http.send did, so the outer catch answers "model proxy unavailable".
 */
async function callProvider(
  url: string, headers: Record<string, string>, serialized: string,
): Promise<{ status: number; json: unknown }> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: serialized,
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  });
  let parsed: unknown = null;
  try {
    parsed = await res.json();
  } catch (err) {
    if (err instanceof SyntaxError) parsed = null;   // a body that is not JSON
    else throw err;                                  // an abort mid-body
  }
  return { status: res.status, json: parsed };
}

// ---------------------------------------------------------------------------
// The route. routes/agent.ts has already done rules 1 and 2 (credentials and
// the paired lookup) and hands over the row it found.
// ---------------------------------------------------------------------------

export async function llmProxy(
  req: Request, env: LlmEnv, agent: AgentRow, startedAt: number = Date.now(),
): Promise<Response> {
  const agentId = String(agent.agent_id ?? "");

  // Rule 3. A paired agent must belong to a REAL ACCOUNT. Without this the
  // endpoint was an open LLM proxy billed to us: register (no credential
  // needed), self-pair, loop forever. agent_key.pb.js:167-174.
  const ownerRef = String(agent.owner_ref ?? "").trim();
  if (!ownerRef) {
    return json(403, { error: "this agent is not attached to an account" });
  }

  // Rule 4. And a real account still may not spend without limit. One runaway
  // loop — a bug as easily as an abuser — could drain the balance in an hour.
  // The meter's own failure never blocks real work (agent_key.pb.js:197-200):
  // a fail-open on the BUDGET, not on authorisation.
  try {
    const hourNow = new Date().toISOString().slice(0, 13);   // YYYY-MM-DDTHH
    const storedHour = String(agent.llm_hour ?? "");
    const used = storedHour === hourNow ? (Number(agent.llm_calls) || 0) : 0;
    if (used >= HOURLY_CALL_CEILING) {
      console.log("agent/llm: hourly ceiling hit for", agentId, "at", used);
      return json(429, { error: CEILING_429_ERROR, detail: CEILING_429_DETAIL });
    }
    // One atomic statement: a stored hour that is not this hour restarts the
    // count at 1, otherwise it steps. The hook read-modify-wrote and could lose
    // a step when one browser's calls overlapped; this cannot.
    await env.DB.prepare(
      `UPDATE agents
          SET llm_calls = CASE WHEN llm_hour = ?1 THEN llm_calls + 1 ELSE 1 END,
              llm_hour = ?1, updated = ?2
        WHERE id = ?3`)
      .bind(hourNow, pbNow(), String(agent.id ?? "")).run();
  } catch (err) {
    console.log("agent/llm: meter unavailable:", String(err).slice(0, 120));
  }

  // Rule 5.
  const keys = providerKeys(env);
  if (!keys.gemini && !keys.openrouter) {
    return json(503, { error: "backend has no model configured" });
  }

  // Rule 6. PocketBase's requestInfo().body is a map: not-JSON and a JSON
  // array both fail to become one. An empty body is an empty map.
  let body: Record<string, unknown>;
  try {
    const text = await req.text();
    const parsed: unknown = text.trim() ? JSON.parse(text) : {};
    if (parsed === null) body = {};
    else if (typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("not an object");
    else body = parsed as Record<string, unknown>;
  } catch {
    return json(400, { error: "valid JSON required" });
  }

  // Rule 7. A compromised extension token can spend only through the two
  // server-selected models.
  const models = enabledModels(env);
  const model = String(body.model || "");
  if (model !== models.browser && model !== models.vision) {
    return json(403, { error: "model is not enabled for browser agents" });
  }

  // Rule 8. A Google model can use Google's direct API; every other model must
  // go through OpenRouter. Do not choose a provider merely because its key
  // exists: that previously made a DeepSeek request run on Gemini while the
  // client and the audit row still said DeepSeek (agent_key.pb.js:212-219).
  const directGeminiModel = model.startsWith("google/") ? model.slice("google/".length) : "";
  if (!directGeminiModel && !keys.openrouter) {
    return json(503, { error: "requested model provider is not configured" });
  }

  // Rules 9 and 10.
  const rawMessages = body.messages;
  if (!Array.isArray(rawMessages) || rawMessages.length < 1 || rawMessages.length > 40) {
    return json(400, { error: "messages must contain 1 to 40 items" });
  }
  const messages: ChatMessage[] = rawMessages.map((message: unknown) => {
    const m = message as { role?: unknown; content?: unknown } | null;
    return { role: String((m && m.role) || ""), content: m ? m.content : undefined };
  });
  if (messages.some((m) => !["system", "user", "assistant"].includes(m.role))) {
    return json(400, { error: "unsupported message role" });
  }

  // Browser responses are compact JSON. Never let an omitted client cap turn
  // into the provider's 65k-token maximum: OpenRouter performs an
  // affordability check against that maximum before generating anything.
  const boundedMax = boundMaxTokens(body.max_tokens);
  const jsonObject = wantsJsonObject(body.response_format);
  const payload: OpenRouterPayload = { model, messages, temperature: 0, max_tokens: boundedMax };
  if (jsonObject) payload.response_format = { type: "json_object" };
  const serialized = JSON.stringify(payload);

  // Rule 11.
  if (serialized.length > MAX_REQUEST_CHARS) return json(413, { error: "model request too large" });

  // The ledger, for a tagged run only. agent_key.pb.js:251-275.
  let audit: string | null = null;
  let auditedMessages: ChatMessage[] = messages;
  try {
    auditedMessages = await redactMessages(messages);
    let taskTag = taskTagOf(JSON.stringify(auditedMessages));
    if (!taskTag) {
      const session = await env.DB.prepare(
        `SELECT task_tag, expires_at FROM agent_audit_sessions
          WHERE agent_id = ? AND active = 1
          ORDER BY created DESC LIMIT 1`)
        .bind(agentId).first<{ task_tag: string; expires_at: string }>();
      if (session && pbTime(session.expires_at) > Date.now()) {
        taskTag = String(session.task_tag || "");
      }
    }
    audit = await auditBegin(env, taskTag, agentId, ownerRef, model, {
      model,
      messages: auditedMessages,
      temperature: 0,
      max_tokens: boundedMax,
      response_format: payload.response_format || null,
    });
  } catch (err) {
    // Certification evidence must never break ordinary execution. The
    // explicit line makes a missing audit row diagnosable instead of silent.
    console.log("agent audit setup failed:", String(err));
  }

  try {
    // Use the direct Google endpoint only for an explicitly selected Google
    // model. OpenRouter receives the selected non-Google model unchanged.
    if (keys.gemini && directGeminiModel) {
      const { systemText, contents } = toGeminiContents(messages);
      // Rule 12.
      if (!contents.length) return json(400, { error: "messages contain no usable content" });
      const generationConfig = geminiGenerationConfig(directGeminiModel, boundedMax, jsonObject);
      const geminiPayload: Record<string, unknown> = { contents, generationConfig };
      if (systemText) geminiPayload.systemInstruction = { parts: [{ text: systemText }] };
      const geminiSerialized = JSON.stringify(geminiPayload);
      const auditedGeminiSerialized = JSON.stringify(await redactProviderPayload(geminiPayload));
      if (geminiSerialized.length > MAX_REQUEST_CHARS) return json(413, { error: "model request too large" });

      const response = await callProvider(
        providerBase(env, GOOGLE_BASE) + "/v1beta/models/"
          + encodeURIComponent(directGeminiModel) + ":generateContent",
        { "x-goog-api-key": keys.gemini },
        geminiSerialized,
      );
      // Rule 13.
      if (!response.json) {
        const clientError = JSON.stringify({ error: "model returned no JSON" });
        await auditFinish(env, audit, startedAt, {
          provider: "google", provider_model: directGeminiModel, status: "error",
          http_status: 502, provider_request_json: auditedGeminiSerialized,
          client_response_json: clientError, error: "model returned no JSON",
        });
        return json(502, { error: "model returned no JSON" });
      }
      // Rule 14.
      if (response.status < 200 || response.status >= 300) {
        const providerJSON = JSON.stringify(response.json);
        const clientError = JSON.stringify({ error: "model provider rejected request" });
        await auditFinish(env, audit, startedAt, {
          provider: "google", provider_model: directGeminiModel, status: "error",
          http_status: response.status, provider_request_json: auditedGeminiSerialized,
          provider_response_json: providerJSON, client_response_json: clientError,
          error: "model provider rejected request",
        });
        return json(response.status, { error: "model provider rejected request" });
      }
      // Rule 15.
      const clientResponse = translateGemini(response.json, directGeminiModel);
      if (!clientResponse) {
        const providerJSON = JSON.stringify(response.json);
        const clientError = JSON.stringify({ error: "model returned no text" });
        await auditFinish(env, audit, startedAt, {
          provider: "google", provider_model: directGeminiModel, status: "error",
          http_status: 502, provider_request_json: auditedGeminiSerialized,
          provider_response_json: providerJSON, client_response_json: clientError,
          error: "model returned no text",
        });
        return json(502, { error: "model returned no text" });
      }
      const providerJSON = JSON.stringify(response.json);
      const clientJSON = JSON.stringify(clientResponse);
      await auditFinish(env, audit, startedAt, {
        provider: "google", provider_model: directGeminiModel, status: "ok",
        http_status: 200, provider_request_json: auditedGeminiSerialized,
        provider_response_json: providerJSON, client_response_json: clientJSON,
      });
      return json(200, clientResponse);
    }

    const response = await callProvider(
      providerBase(env, OPENROUTER_BASE) + "/api/v1/chat/completions",
      {
        "Authorization": "Bearer " + keys.openrouter,
        "HTTP-Referer": "https://anticipy.ai",
        "X-Title": "Anticipy",
      },
      serialized,
    );
    const auditedOpenrouter = JSON.stringify({ ...payload, messages: auditedMessages });
    // Rule 13.
    if (!response.json) {
      const clientError = JSON.stringify({ error: "model returned no JSON" });
      await auditFinish(env, audit, startedAt, {
        provider: "openrouter", provider_model: model, status: "error",
        http_status: 502, provider_request_json: auditedOpenrouter,
        client_response_json: clientError, error: "model returned no JSON",
      });
      return json(502, { error: "model returned no JSON" });
    }
    // OpenRouter's own JSON, returned verbatim with OpenRouter's own status —
    // including a non-2xx, which is why rule 14 has no OpenRouter twin.
    const providerJSON = JSON.stringify(response.json);
    const ok = response.status >= 200 && response.status < 300;
    const providerModel = (response.json as { model?: unknown }).model;
    await auditFinish(env, audit, startedAt, {
      provider: "openrouter",
      provider_model: String(providerModel || model),
      status: ok ? "ok" : "error",
      http_status: response.status, provider_request_json: auditedOpenrouter,
      provider_response_json: providerJSON, client_response_json: providerJSON,
      error: ok ? "" : "model provider rejected request",
    });
    return json(response.status, response.json);
  } catch (err) {
    // Rule 16. A timeout, a transport failure, a status the Response
    // constructor refuses: all the same class of event to the caller, and the
    // extension's retry path covers it unchanged.
    const clientError = JSON.stringify({ error: "model proxy unavailable" });
    await auditFinish(env, audit, startedAt, {
      status: "error", http_status: 502,
      client_response_json: clientError, error: String(err).slice(0, 1000),
    });
    return json(502, { error: "model proxy unavailable" });
  }
}
