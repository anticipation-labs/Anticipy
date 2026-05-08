/**
 * Centralized LLM cascade — Plan A → B → C → D.
 *
 * One callsite, four providers, equal capability tier. When Plan A
 * 429s, Plan B picks up. When Plan B 429s, Plan C. When Plan C 429s,
 * Plan D. Only after ALL FOUR fail does the function return "" or
 * throw — the cascade never silently degrades on a single-provider
 * outage.
 *
 *   Plan A — Gemini 2.5 Flash (1M ctx, primary speed/cost)
 *   Plan B — Groq llama-3.3-70b-versatile (128k ctx, 70B class)
 *   Plan C — Kimi moonshot-v1-128k (128k ctx, OpenAI-compat)
 *   Plan D — DeepSeek deepseek-chat (128k ctx, last-resort)
 *
 * Use this instead of `callGemini` directly anywhere a single-provider
 * outage would cause user-visible failure (intent extraction, gates,
 * memory extract, preference reasoning, etc.).
 *
 * The single `callGemini` import is preserved for paths that
 * SPECIFICALLY need Gemini (e.g., embedText, prompt-cached system
 * prompts that benefit from cachedContent's 5-min TTL — Groq / Kimi
 * / DeepSeek don't have an equivalent).
 */
import { callGemini } from "@/lib/gemini";
import { callGroq } from "@/lib/groq";
import { callKimi } from "@/lib/kimi";
// DeepSeek isn't yet wrapped in a callsite-style helper. Inlining the
// fetch keeps the dependency graph minimal and the cascade self-
// contained.

interface LlmMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface CascadeOptions {
  temperature?: number;
  max_tokens?: number;
  /** Stable cache key for Gemini's cachedContent. Other providers ignore. */
  cacheKey?: string;
  /** Force JSON output. Default true (matches existing call sites). */
  jsonOnly?: boolean;
}

interface CascadeResult {
  text: string;
  provider: "gemini" | "groq" | "kimi" | "deepseek" | "none";
  errors: Record<string, string>;
}

const DEEPSEEK_URL = "https://api.deepseek.com/chat/completions";

async function tryDeepSeek(
  messages: LlmMessage[],
  options: CascadeOptions
): Promise<string> {
  const key = process.env.DEEPSEEK_API_KEY;
  if (!key) throw new Error("DeepSeek key not configured");
  const resp = await fetch(DEEPSEEK_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
    },
    body: JSON.stringify({
      model: "deepseek-chat",
      messages,
      temperature: options.temperature ?? 0,
      max_tokens: options.max_tokens ?? 4096,
      ...(options.jsonOnly !== false
        ? { response_format: { type: "json_object" } }
        : {}),
    }),
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => String(resp.status));
    throw new Error(`DeepSeek ${resp.status}: ${body.substring(0, 200)}`);
  }
  const data = await resp.json();
  const content = data.choices?.[0]?.message?.content;
  if (!content) throw new Error("DeepSeek returned empty content");
  return content;
}

/**
 * Call the LLM cascade. Returns the first non-empty response from any
 * plan. Errors are collected per-plan; check `result.provider === "none"`
 * if you need to distinguish "all four failed" from a successful call.
 */
export async function callLlmCascade(
  messages: LlmMessage[],
  options: CascadeOptions = {}
): Promise<CascadeResult> {
  const errors: Record<string, string> = {};

  // Plan A — Gemini
  try {
    const text = await callGemini(messages, {
      temperature: options.temperature,
      max_tokens: options.max_tokens,
      cacheKey: options.cacheKey,
      jsonOnly: options.jsonOnly,
    });
    if (text) return { text, provider: "gemini", errors };
    errors.gemini = "empty response";
  } catch (err) {
    errors.gemini = err instanceof Error ? err.message.slice(0, 160) : String(err);
  }

  // Plan B — Groq
  try {
    const text = await callGroq(messages, {
      temperature: options.temperature,
      max_tokens: options.max_tokens,
      ...(options.jsonOnly !== false
        ? { response_format: { type: "json_object" } }
        : {}),
    });
    if (text) return { text, provider: "groq", errors };
    errors.groq = "empty response";
  } catch (err) {
    errors.groq = err instanceof Error ? err.message.slice(0, 160) : String(err);
  }

  // Plan C — Kimi
  try {
    const text = await callKimi(messages, {
      // Forces a deterministic temperature variant; kimi-k2.x requires
      // temp=1 which we don't want for gates/extracts.
      model: "moonshot-v1-128k",
      temperature: options.temperature ?? 0,
      max_tokens: options.max_tokens,
      ...(options.jsonOnly !== false
        ? { response_format: { type: "json_object" } }
        : {}),
    });
    if (text) return { text, provider: "kimi", errors };
    errors.kimi = "empty response";
  } catch (err) {
    errors.kimi = err instanceof Error ? err.message.slice(0, 160) : String(err);
  }

  // Plan D — DeepSeek
  try {
    const text = await tryDeepSeek(messages, options);
    if (text) return { text, provider: "deepseek", errors };
    errors.deepseek = "empty response";
  } catch (err) {
    errors.deepseek = err instanceof Error ? err.message.slice(0, 160) : String(err);
  }

  return { text: "", provider: "none", errors };
}

/**
 * Convenience wrapper that mirrors the original `callGemini` signature
 * (returns just the string). Lets existing callsites swap one identifier
 * with no other code change.
 */
export async function callLlm(
  messages: LlmMessage[],
  options: CascadeOptions = {}
): Promise<string> {
  const result = await callLlmCascade(messages, options);
  if (result.provider === "none") {
    console.warn(
      "[llm-cascade] all four providers failed:",
      Object.entries(result.errors)
        .map(([k, v]) => `${k}=${v}`)
        .join(" | ")
    );
  } else if (result.provider !== "gemini") {
    // Visibility: log when we fell off Plan A so quota patterns are
    // observable in production logs.
    console.warn(
      `[llm-cascade] fell to plan ${result.provider}:`,
      Object.entries(result.errors)
        .map(([k, v]) => `${k}=${v}`)
        .join(" | ")
    );
  }
  return result.text;
}
