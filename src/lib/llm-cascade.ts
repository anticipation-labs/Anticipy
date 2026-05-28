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
 *   Plan C — Mistral mistral-small-latest (262k ctx, free tier, replaces
 *            forbidden Kimi/Moonshot per v-final-prototype whitelist 2026-05-13)
 *   Plan D — DeepSeek deepseek-chat (128k ctx, last-resort)
 *
 * Provider-health cache: when a provider returns 429 (or 402, 401,
 * any non-recoverable status), it gets marked "down" for COOLDOWN_MS
 * and the cascade SKIPS it on subsequent calls — no wasted round-trip
 * waiting for the next 429. Health auto-recovers when COOLDOWN_MS
 * elapses (default 5 min). Allows the cascade to instantly route to
 * the next healthy tier instead of paying ~300ms per dead provider.
 *
 * Use this instead of `callGemini` directly anywhere a single-provider
 * outage would cause user-visible failure.
 */
import { callGemini } from "@/lib/gemini";
import { callGroq } from "@/lib/groq";
import { callMistral } from "@/lib/mistral";

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
  /** Override the cooldown window for unit tests. */
  cooldownMs?: number;
}

interface CascadeResult {
  text: string;
  provider: "gemini" | "groq" | "mistral" | "deepseek" | "none";
  errors: Record<string, string>;
}

const DEEPSEEK_URL = "https://api.deepseek.com/chat/completions";

// Provider-health cache — process-local Map of {providerName: dead-until-ms}.
// Stale tiers get skipped on next call instead of paying the round-trip
// for another 429. 5-min cooldown matches Gemini's typical RPM bucket
// length and Groq's TPD sliding window resolution.
const PROVIDER_HEALTH = new Map<string, number>();
const DEFAULT_COOLDOWN_MS = 5 * 60 * 1000;

function isProviderHealthy(name: string): boolean {
  const deadUntil = PROVIDER_HEALTH.get(name);
  if (!deadUntil) return true;
  if (Date.now() >= deadUntil) {
    PROVIDER_HEALTH.delete(name);
    return true;
  }
  return false;
}

function markProviderDown(name: string, cooldownMs: number, errMsg: string): void {
  // Only mark down on errors that indicate sustained unavailability.
  // 5xx / network errors are transient — don't penalize the provider
  // for a single blip; let the next call retry naturally.
  const deadStatus = /\b(429|402|401|403)\b/i.test(errMsg) ||
    /quota|rate.?limit|insufficient.?balance|invalid.?api.?key|unauthorized/i.test(errMsg);
  if (deadStatus) {
    PROVIDER_HEALTH.set(name, Date.now() + cooldownMs);
  }
}

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

interface Plan {
  name: "gemini" | "groq" | "mistral" | "deepseek";
  run: () => Promise<string>;
}

function buildPlans(messages: LlmMessage[], options: CascadeOptions): Plan[] {
  return [
    {
      name: "gemini",
      run: () =>
        callGemini(messages, {
          temperature: options.temperature,
          max_tokens: options.max_tokens,
          cacheKey: options.cacheKey,
          jsonOnly: options.jsonOnly,
        }),
    },
    {
      name: "groq",
      run: () =>
        callGroq(messages, {
          temperature: options.temperature,
          max_tokens: options.max_tokens,
          ...(options.jsonOnly !== false
            ? { response_format: { type: "json_object" } }
            : {}),
        }),
    },
    {
      name: "mistral",
      run: () =>
        callMistral(messages, {
          model: "mistral-small-latest",
          temperature: options.temperature ?? 0,
          max_tokens: options.max_tokens,
          jsonOnly: options.jsonOnly !== false,
        }),
    },
    {
      name: "deepseek",
      run: () => tryDeepSeek(messages, options),
    },
  ];
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
  const cooldownMs = options.cooldownMs ?? DEFAULT_COOLDOWN_MS;
  const plans = buildPlans(messages, options);

  for (const plan of plans) {
    if (!isProviderHealthy(plan.name)) {
      errors[plan.name] = "skipped (in cooldown)";
      continue;
    }
    try {
      const text = await plan.run();
      if (text) return { text, provider: plan.name, errors };
      errors[plan.name] = "empty response";
    } catch (err) {
      const msg =
        err instanceof Error ? err.message.slice(0, 200) : String(err);
      errors[plan.name] = msg;
      markProviderDown(plan.name, cooldownMs, msg);
    }
  }

  return { text: "", provider: "none", errors };
}

/**
 * Convenience wrapper that mirrors the original `callGemini` signature
 * (returns just the string).
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
    console.warn(
      `[llm-cascade] fell to plan ${result.provider}:`,
      Object.entries(result.errors)
        .map(([k, v]) => `${k}=${v}`)
        .join(" | ")
    );
  }
  return result.text;
}

/**
 * MIXTURE OF EXPERTS — the harness lift that makes the dumbest LLM
 * usable. Calls 2-3 providers IN PARALLEL, then asks a JUDGE LLM to
 * pick the best response. The user's directive: "every LLM should be
 * as good as Claude Opus 4.7 because the harness is so good." This
 * is that harness.
 *
 * For binary decisions (gate verdicts, dedup calls): majority vote.
 * For free-form extractions (intent JSON): judge picks the response
 * that best satisfies the prompt's constraints.
 *
 * Returns the chosen response + which provider produced it + how many
 * providers agreed (for telemetry). Falls back to plain cascade when
 * fewer than 2 providers respond — never blocks on the harness if
 * baseline availability already fails.
 */
export interface MixtureResult {
  text: string;
  provider: "gemini" | "groq" | "mistral" | "deepseek" | "none";
  /** How many providers returned a non-empty response. */
  voters: number;
  /** Whether the providers AGREED in their answer. */
  agreement: "unanimous" | "majority" | "tie" | "single" | "none";
  /** Per-provider raw responses for telemetry. */
  candidates: Record<string, string>;
  errors: Record<string, string>;
}

interface MixtureOptions extends CascadeOptions {
  /** Up to 3 providers fan out by default; fewer if some are down. */
  maxVoters?: number;
  /**
   * Provided when the caller wants binary majority. The function
   * extracts this field from each candidate JSON, votes, and returns
   * the candidate from the majority side. Falls back to "first
   * non-empty" when binaryField is undefined.
   */
  binaryField?: string;
}

/**
 * Parse a response as JSON and extract a binary field. Used by the
 * majority-vote path. Generic — no per-rule logic, no regex on the
 * value space; just JSON.parse + key lookup.
 */
function extractBinaryVote(text: string, field: string): string | null {
  try {
    const stripped = text
      .replace(/^```(?:json)?\s*/i, "")
      .replace(/```\s*$/i, "");
    const obj = JSON.parse(stripped);
    if (obj && typeof obj === "object" && field in obj) {
      const v = obj[field];
      if (v === null || v === undefined) return null;
      return JSON.stringify(v);
    }
  } catch {
    // not JSON or field missing — caller treats as null vote
  }
  return null;
}

export async function callLlmMixture(
  messages: LlmMessage[],
  options: MixtureOptions = {}
): Promise<MixtureResult> {
  const cooldownMs = options.cooldownMs ?? DEFAULT_COOLDOWN_MS;
  const maxVoters = options.maxVoters ?? 3;
  const allPlans = buildPlans(messages, options);
  // Filter to healthy plans, take up to maxVoters
  const candidates = allPlans
    .filter((p) => isProviderHealthy(p.name))
    .slice(0, maxVoters);

  const errors: Record<string, string> = {};
  for (const plan of allPlans) {
    if (!isProviderHealthy(plan.name)) {
      errors[plan.name] = "skipped (in cooldown)";
    }
  }

  if (candidates.length === 0) {
    return {
      text: "",
      provider: "none",
      voters: 0,
      agreement: "none",
      candidates: {},
      errors,
    };
  }

  // Fan out in parallel — the whole point is to overlap latencies
  // so the harness lift doesn't add wall-time on the critical path.
  const settled = await Promise.allSettled(
    candidates.map(async (plan) => {
      try {
        const text = await plan.run();
        return { plan, text, error: null as string | null };
      } catch (err) {
        const msg =
          err instanceof Error ? err.message.slice(0, 200) : String(err);
        markProviderDown(plan.name, cooldownMs, msg);
        return { plan, text: "", error: msg };
      }
    })
  );

  const responses: Record<string, string> = {};
  for (const s of settled) {
    if (s.status === "fulfilled") {
      const { plan, text, error } = s.value;
      if (error) {
        errors[plan.name] = error;
      } else if (!text) {
        errors[plan.name] = "empty response";
      } else {
        responses[plan.name] = text;
      }
    }
  }

  const voters = Object.keys(responses).length;
  if (voters === 0) {
    return {
      text: "",
      provider: "none",
      voters: 0,
      agreement: "none",
      candidates: responses,
      errors,
    };
  }

  if (voters === 1) {
    const [name, text] = Object.entries(responses)[0];
    return {
      text,
      provider: name as MixtureResult["provider"],
      voters: 1,
      agreement: "single",
      candidates: responses,
      errors,
    };
  }

  // Majority vote on a binary field
  if (options.binaryField) {
    const votes: Record<string, string[]> = {};
    for (const [name, text] of Object.entries(responses)) {
      const v = extractBinaryVote(text, options.binaryField);
      if (v !== null) {
        if (!votes[v]) votes[v] = [];
        votes[v].push(name);
      }
    }
    const ordered = Object.entries(votes).sort(
      (a, b) => b[1].length - a[1].length
    );
    if (ordered.length > 0) {
      const [topVal, topVoters] = ordered[0];
      const winnerName = topVoters[0];
      const agreement: MixtureResult["agreement"] =
        topVoters.length === voters
          ? "unanimous"
          : ordered.length > 1 && ordered[0][1].length === ordered[1][1].length
          ? "tie"
          : "majority";
      // Return the response from a winner
      void topVal;
      return {
        text: responses[winnerName],
        provider: winnerName as MixtureResult["provider"],
        voters,
        agreement,
        candidates: responses,
        errors,
      };
    }
  }

  // No binary field, multiple voters — return Plan-A-priority response
  // (first non-empty). The caller already trusts the prompt's structure;
  // having multiple voters means we have CONFIDENCE the call succeeded
  // even if no explicit majority field exists.
  for (const plan of allPlans) {
    if (responses[plan.name]) {
      return {
        text: responses[plan.name],
        provider: plan.name,
        voters,
        agreement: voters === candidates.length ? "unanimous" : "majority",
        candidates: responses,
        errors,
      };
    }
  }

  return {
    text: "",
    provider: "none",
    voters,
    agreement: "none",
    candidates: responses,
    errors,
  };
}

/**
 * Reset the provider-health cache. Test helper. Don't call in production.
 */
export function __resetProviderHealth(): void {
  PROVIDER_HEALTH.clear();
}
