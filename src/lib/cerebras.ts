/**
 * Server-side Cerebras client.
 *
 * Why Cerebras: free tier gives 1M tokens/day, 30 RPM, capable models
 * (Qwen3-235B, GLM-4.7, GPT-OSS 120B, Llama-3.1-8B). Latency on Qwen3-235B
 * is ~250ms — 5-10x faster than Moonshot v1-128k. Same instruction-
 * following quality on the agent-team's plan/verify/critic/reflect
 * prompts. Replaces Kimi as the primary model for the agent-team routes.
 *
 * Failover: when Cerebras 429s or errors, the route falls back to the
 * existing Kimi client (which has its own 429 handling). When Kimi is
 * also down, the route returns 502 — the extension already handles
 * that gracefully (verifier verdict = null, agent continues without
 * the verdict).
 *
 * Env: CEREBRAS_API_KEY
 */

const CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions";
const CEREBRAS_DEFAULT_MODEL = "qwen-3-235b-a22b-instruct-2507";
const CEREBRAS_DEFAULT_TEMPERATURE = 0.1;

interface CerebrasMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

// Hardcoded fallback when CEREBRAS_API_KEY isn't in Vercel env (we
// can't add env vars from code, and the user shouldn't need to). This
// No hardcoded fallback. A committed key is a live credential in every
// clone, fork and CI log of this repo, and "it is only free tier" stops
// being true the moment the account is upgraded or the quota is used as
// a denial-of-service against our own service.
const FALLBACK_KEY = "";

export function cerebrasAvailable(): boolean {
  return Boolean(process.env.CEREBRAS_API_KEY || FALLBACK_KEY);
}

export interface CerebrasUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

export interface CerebrasCallResult {
  text: string;
  usage: CerebrasUsage;
  raw: any;
}

export interface CerebrasCallOptions {
  system?: string;
  messages: CerebrasMessage[];
  temperature?: number;
  maxTokens?: number;
  jsonMode?: boolean;
  model?: string;
}

/**
 * Low-level Cerebras call. Throws on non-2xx. The 8192-token context
 * cap on free tier means callers should keep system+user under ~6K
 * tokens to leave room for output.
 */
export async function callCerebras(opts: CerebrasCallOptions): Promise<CerebrasCallResult> {
  const key = process.env.CEREBRAS_API_KEY || FALLBACK_KEY;
  if (!key) throw new Error("CEREBRAS_API_KEY missing");

  const messages: CerebrasMessage[] = [];
  if (opts.system) messages.push({ role: "system", content: opts.system });
  for (const m of opts.messages) messages.push(m);

  const body: Record<string, unknown> = {
    model: opts.model ?? CEREBRAS_DEFAULT_MODEL,
    messages,
    temperature: opts.temperature ?? CEREBRAS_DEFAULT_TEMPERATURE,
    max_tokens: opts.maxTokens ?? 1200,
  };
  if (opts.jsonMode) body.response_format = { type: "json_object" };

  // 30s upstream timeout — Cerebras typically responds in <1s, so a
  // 30s ceiling is generous and fits inside Vercel's 60s function deadline.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);

  let resp: Response;
  try {
    resp = await fetch(CEREBRAS_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${key}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }

  if (!resp.ok) {
    const errText = await resp.text().catch(() => `status ${resp.status}`);
    throw new Error(`Cerebras ${resp.status}: ${errText.substring(0, 240)}`);
  }
  const data = await resp.json();
  const text = data?.choices?.[0]?.message?.content ?? "";
  return { text, usage: data?.usage ?? {}, raw: data };
}

/** Convenience: jsonMode=true plus tolerant parse. */
export async function callCerebrasJson<T = any>(
  opts: CerebrasCallOptions
): Promise<T> {
  const { text } = await callCerebras({ ...opts, jsonMode: true });
  let cleaned = text.trim();
  cleaned = cleaned.replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start !== -1 && end !== -1 && end > start) {
    cleaned = cleaned.substring(start, end + 1);
  }
  try {
    return JSON.parse(cleaned) as T;
  } catch (e) {
    throw new Error(`Cerebras returned non-JSON: ${cleaned.substring(0, 240)}`);
  }
}

/** Cerebras free tier = $0. This always returns 0. Kept for API parity. */
export function cerebrasCostUsd(_usage: CerebrasUsage): number {
  return 0;
}
