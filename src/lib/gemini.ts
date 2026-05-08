/**
 * Gemini client wrapper with two free-tier-friendly upgrades layered on top
 * of the previous minimal `callGemini`:
 *
 *   1. Prompt-cache hooks. Gemini supports server-side prompt caching via the
 *      `cachedContents` API. Large system prompts (intent extractor, gate,
 *      memory extractor, agent) are reused across many calls; caching them
 *      knocks ~90% off the input-token cost on cache hits. We expose
 *      `cacheKey` on the call options — callers pass a stable key (e.g.
 *      "intent-system-v3") and we maintain a per-key in-memory pointer to
 *      the cached resource. Cache lifetime defaults to 5 minutes (Gemini's
 *      minimum TTL); on miss we transparently re-create.
 *   2. JSON-repair helper. Flash sometimes truncates a JSON tail or wraps
 *      output in stray prose. `parseJsonWithRepair` first tries `JSON.parse`,
 *      then strips fences / extracts the largest `{...}` substring, and as
 *      a last resort dispatches a tiny Flash repair call ("here is the
 *      malformed JSON, return strictly valid JSON only"). All callers that
 *      previously did `JSON.parse(...)` inside a try/catch should switch to
 *      this helper to recover gracefully instead of silently dropping
 *      content.
 *
 * Backwards compatible: callers that don't pass `cacheKey` get exactly the
 * pre-existing single-call behavior. The cache is best-effort — on any cache
 * API failure we fall through to the uncached path.
 */

const GOOGLE_API_KEY = process.env.GOOGLE_API_KEY ?? "";
const GEMINI_MODEL = "gemini-2.5-flash";
const GEMINI_BASE = `https://generativelanguage.googleapis.com/v1beta`;
const GEMINI_GENERATE_URL = `${GEMINI_BASE}/models/${GEMINI_MODEL}:generateContent?key=${GOOGLE_API_KEY}`;
const GEMINI_CACHE_URL = `${GEMINI_BASE}/cachedContents?key=${GOOGLE_API_KEY}`;

// Minimum content size Gemini will cache (varies by model; conservative floor).
// Below this we skip caching — the API rejects tiny payloads with 400.
const MIN_CACHE_CONTENT_CHARS = 4096;
// Gemini's documented minimum TTL is 5 minutes; we use that.
const DEFAULT_CACHE_TTL_SECONDS = 300;

interface GeminiMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface CacheEntry {
  name: string; // e.g. "cachedContents/abcd1234"
  expiresAt: number; // ms
}

const CACHE_REGISTRY = new Map<string, CacheEntry>();
let lastUsageMetadata: Record<string, unknown> | null = null;

/**
 * Read the most recent Gemini call's usageMetadata block. Useful for
 * verifying cache hit rate (`cachedContentTokenCount`). Best-effort —
 * not all responses include the field.
 */
export function lastGeminiUsage(): Record<string, unknown> | null {
  return lastUsageMetadata;
}

async function ensureCachedSystemPrompt(
  cacheKey: string,
  systemMsg: string
): Promise<string | null> {
  if (!cacheKey || !systemMsg) return null;
  if (systemMsg.length < MIN_CACHE_CONTENT_CHARS) return null;

  const now = Date.now();
  const existing = CACHE_REGISTRY.get(cacheKey);
  if (existing && existing.expiresAt > now + 5_000) {
    return existing.name;
  }

  try {
    const res = await fetch(GEMINI_CACHE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: `models/${GEMINI_MODEL}`,
        systemInstruction: { parts: [{ text: systemMsg }] },
        // Gemini insists on at least one non-empty content block; a
        // tiny placeholder satisfies the API without skewing output.
        contents: [
          { role: "user", parts: [{ text: "_" }] },
        ],
        ttl: `${DEFAULT_CACHE_TTL_SECONDS}s`,
      }),
    });
    if (!res.ok) {
      // Soft-fail: 4xx (e.g. content too small after all, model mismatch)
      // logged once and we fall through to the uncached path.
      const body = await res.text().catch(() => "");
      console.warn(
        `[gemini-cache] create failed ${res.status}: ${body.substring(0, 200)}`
      );
      return null;
    }
    const data = (await res.json()) as { name?: string };
    if (!data.name) return null;
    CACHE_REGISTRY.set(cacheKey, {
      name: data.name,
      // Slight safety margin so the next call doesn't hit a just-expired
      // cache. Gemini's TTL is best-effort, not exact.
      expiresAt: now + DEFAULT_CACHE_TTL_SECONDS * 1000 - 15_000,
    });
    return data.name;
  } catch (err) {
    console.warn(
      "[gemini-cache] create exception; falling through to uncached:",
      err instanceof Error ? err.message : err
    );
    return null;
  }
}

export async function callGemini(
  messages: GeminiMessage[],
  options: {
    temperature?: number;
    max_tokens?: number;
    /**
     * When set, Gemini's prompt-cache is used for the system prompt. The
     * key should be stable per-prompt-version (e.g. "intent-system-v3").
     * Different keys point to different cached payloads. Cache misses
     * fall through to the standard call transparently.
     */
    cacheKey?: string;
    /**
     * Force JSON output mime type. Default true (matches the original
     * implementation). Pass false for free-form text completions.
     */
    jsonOnly?: boolean;
  } = {}
): Promise<string> {
  const {
    temperature = 0.0,
    max_tokens = 8192,
    cacheKey,
    jsonOnly = true,
  } = options;

  const systemMsg = messages.find((m) => m.role === "system")?.content ?? "";
  const userMsgs = messages.filter((m) => m.role !== "system");

  const cachedContent = cacheKey
    ? await ensureCachedSystemPrompt(cacheKey, systemMsg)
    : null;

  const body: Record<string, unknown> = {
    contents: userMsgs.map((m) => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.content }],
    })),
    generationConfig: {
      temperature,
      maxOutputTokens: max_tokens,
      ...(jsonOnly ? { responseMimeType: "application/json" } : {}),
    },
  };

  if (cachedContent) {
    // When using a cached system prompt, the live request must NOT include
    // the system_instruction field — the cache supplies it. Including both
    // returns 400.
    body.cachedContent = cachedContent;
  } else {
    body.system_instruction = { parts: [{ text: systemMsg }] };
  }

  const res = await fetch(GEMINI_GENERATE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.text();
    // If the cache reference 404s (it can expire mid-call), drop the entry
    // and signal the caller via a typed error so we can retry uncached.
    if (cachedContent && (res.status === 404 || res.status === 400)) {
      CACHE_REGISTRY.delete(cacheKey!);
    }
    throw new Error(`Gemini error ${res.status}: ${err.substring(0, 200)}`);
  }

  const data = await res.json();
  lastUsageMetadata = (data && data.usageMetadata) || null;
  return data.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
}

/**
 * Best-effort JSON parse with three escalating recovery strategies:
 *
 *   1. Strict `JSON.parse` on the trimmed input — covers the common case.
 *   2. Strip ```json fences and re-parse — Flash occasionally adds them
 *      despite responseMimeType=application/json.
 *   3. Extract the largest `{...}` or `[...]` substring and parse that —
 *      handles trailing prose / cut-off footers.
 *   4. (Optional, expensive) one-shot Flash repair: ask Gemini to echo
 *      back the same content but as strict JSON. Capped at 1024 tokens
 *      so cost stays trivial (~$0.00003).
 *
 * Returns `null` on irrecoverable failure. Caller decides whether `null`
 * means fail-open / fail-empty.
 */
export async function parseJsonWithRepair<T = unknown>(
  raw: string,
  options: { allowLLMRepair?: boolean; debugLabel?: string } = {}
): Promise<T | null> {
  const text = (raw || "").trim();
  if (!text) return null;

  // 1) strict
  try {
    return JSON.parse(text) as T;
  } catch {
    /* fall through */
  }

  // 2) strip fences
  const fenceStripped = text
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();
  if (fenceStripped !== text) {
    try {
      return JSON.parse(fenceStripped) as T;
    } catch {
      /* fall through */
    }
  }

  // 3) substring extraction. Try the widest object first, then array.
  for (const [open, close] of [
    ["{", "}"],
    ["[", "]"],
  ] as const) {
    const start = fenceStripped.indexOf(open);
    const end = fenceStripped.lastIndexOf(close);
    if (start >= 0 && end > start) {
      const slice = fenceStripped.slice(start, end + 1);
      try {
        return JSON.parse(slice) as T;
      } catch {
        /* fall through */
      }
    }
  }

  // 4) ask Flash to repair. Cheap last resort; only used when caller asks.
  if (!options.allowLLMRepair) return null;
  try {
    const repaired = await callGemini(
      [
        {
          role: "system",
          content:
            "You are a strict JSON repair tool. The input is supposed to be a single JSON object or array but is malformed (truncated, has stray prose, or wrapped in fences). Return ONLY valid JSON — no commentary, no fences, no extra fields. If the input is irrecoverably broken, return {}.",
        },
        { role: "user", content: text.slice(0, 8000) },
      ],
      { temperature: 0.0, max_tokens: 1024, jsonOnly: true }
    );
    return JSON.parse(repaired.trim()) as T;
  } catch (err) {
    if (options.debugLabel) {
      console.warn(
        `[json-repair:${options.debugLabel}] LLM repair failed:`,
        err instanceof Error ? err.message : err
      );
    }
    return null;
  }
}
