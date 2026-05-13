/**
 * Claude (Anthropic) wrapper — same shape as gemini.ts / groq.ts / kimi.ts.
 *
 * Used as an escalation tier when the cheaper Gemini Flash primary returns
 * empty intents on a clearly-actionable transcript, or when 2 consecutive
 * Pro browser-agent calls fail. Gemini Flash stays the cheap default; Claude
 * fires only on the genuinely-hard tail.
 *
 * Why fetch and not @anthropic-ai/sdk: every other provider in this repo
 * uses fetch (gemini.ts / groq.ts / kimi.ts), and prompt caching only needs
 * the `cache_control: {type: "ephemeral"}` marker on a content block — no
 * SDK helpers required. Keeping the dep surface identical avoids bundle
 * bloat in the Vercel edge route.
 *
 * PROMPT CACHING — every call places the system prompt in a SINGLE text
 * block with `cache_control: {type: "ephemeral"}`. The first call writes
 * the cache (~1.25x input cost on those tokens); every subsequent call
 * within the 5-minute TTL reads it (~0.1x). For the analyze + gate path
 * the system prompts are ~3-4KB each and stable across calls, so caching
 * is the dominant cost lever. See shared/prompt-caching.md — the prefix
 * MUST be byte-identical (no timestamps, no UUIDs, deterministic key
 * order) or every request writes a fresh entry and reads nothing.
 *
 * Model defaults to claude-sonnet-4-5 (good intelligence/cost/latency
 * trade for our intent + gate workloads). Caller can override per call.
 */

// Read the key lazily — Next.js / Vercel set it at request time, but local
// scripts may load .env.local AFTER this module is imported (TypeScript
// hoists imports above runtime code). Function form means tests + the
// production routes both see the value when they actually call out.
function getApiKey(): string {
  return process.env.ANTHROPIC_API_KEY ?? "";
}
const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

export type ClaudeRole = "system" | "user" | "assistant";

export interface ClaudeMessage {
  role: ClaudeRole;
  content: string;
}

export interface ClaudeUsage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
}

export interface ClaudeOptions {
  /** Model alias. Default: claude-sonnet-4-5 (escalation tier). Use claude-opus-4-5 for the hardest steps. */
  model?: string;
  temperature?: number;
  max_tokens?: number;
  /**
   * Force JSON-only output. Adds a system-prompt suffix instructing
   * "respond with strict JSON" — the Anthropic API has no native
   * response_format toggle, so this is the supported pattern.
   */
  jsonOnly?: boolean;
  /**
   * Wall-clock timeout in ms before we abort the fetch. Defaults to
   * 60s — long enough for hard intent extractions on long transcripts,
   * short enough that a hung Anthropic call doesn't wedge an analyze
   * route.
   */
  timeoutMs?: number;
}

export interface ClaudeResult {
  text: string;
  usage: ClaudeUsage | null;
  /** True when ANTHROPIC_API_KEY is missing — caller can short-circuit silently. */
  unavailable: boolean;
}

/**
 * Returns true when the Anthropic API key is configured. Callers should
 * gate Claude escalation on this so the build never breaks if the env
 * var is missing on Vercel.
 */
export function claudeAvailable(): boolean {
  return getApiKey().length > 0;
}

/**
 * Low-level call returning the raw text plus usage info. Most callers want
 * `callClaude` (which throws on missing key + matches the gemini.ts shape).
 */
export async function callClaudeRaw(
  messages: ClaudeMessage[],
  options: ClaudeOptions = {}
): Promise<ClaudeResult> {
  if (!claudeAvailable()) {
    return { text: "", usage: null, unavailable: true };
  }
  const {
    model = "claude-sonnet-4-5",
    temperature = 0.0,
    max_tokens = 4096,
    jsonOnly = false,
    timeoutMs = 60_000,
  } = options;

  // Anthropic separates system from messages. We collapse all system-role
  // entries into a single cached block so prompt-caching keys on a single
  // stable prefix. JSON-only suffix is appended at a STABLE position
  // inside the same block — adding/removing it across calls invalidates
  // the cache, so the suffix is part of the cached prefix when it's on,
  // and absent when it's off. Either way, byte-identical across calls
  // with the same options.
  const systemText = messages
    .filter((m) => m.role === "system")
    .map((m) => m.content)
    .join("\n\n");

  const jsonSuffix = jsonOnly
    ? '\n\nResponse format: Return STRICT JSON only — no markdown, no prose, no preamble. Start with "{" and end with "}".'
    : "";

  const systemBlocks = systemText
    ? [
        {
          type: "text" as const,
          text: systemText + jsonSuffix,
          // Cache the system prompt — it's the largest stable input across
          // gate / intent / agent calls. Reads are ~0.1x input cost.
          cache_control: { type: "ephemeral" as const },
        },
      ]
    : [];

  // Convert the conversational messages, dropping system entries (already
  // folded into systemBlocks above). Anthropic requires alternating
  // user/assistant; consecutive same-role messages are merged.
  const apiMessages: Array<{ role: "user" | "assistant"; content: string }> = [];
  for (const m of messages) {
    if (m.role === "system") continue;
    const lastIdx = apiMessages.length - 1;
    const role: "user" | "assistant" = m.role === "assistant" ? "assistant" : "user";
    if (lastIdx >= 0 && apiMessages[lastIdx].role === role) {
      apiMessages[lastIdx] = {
        role,
        content: apiMessages[lastIdx].content + "\n\n" + m.content,
      };
    } else {
      apiMessages.push({ role, content: m.content });
    }
  }
  if (apiMessages.length === 0) {
    // Anthropic requires at least one message — synthesize a minimal user
    // turn from the system prompt. Should never happen in practice; the
    // analyze + gate paths always pass a user message.
    apiMessages.push({ role: "user", content: "Proceed." });
  }

  const body: Record<string, unknown> = {
    model,
    max_tokens,
    temperature,
    messages: apiMessages,
  };
  if (systemBlocks.length > 0) body.system = systemBlocks;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(ANTHROPIC_URL, {
      method: "POST",
      headers: {
        "x-api-key": getApiKey(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const errBody = await res.text().catch(() => "");
    throw new Error(`Claude error ${res.status}: ${errBody.substring(0, 240)}`);
  }

  const data = (await res.json()) as {
    content?: Array<{ type: string; text?: string }>;
    usage?: ClaudeUsage;
  };

  // Anthropic returns content as an array of blocks; we join only the
  // text-typed ones. thinking/tool_use blocks (if ever added later) are
  // ignored by callers that just want the response text.
  const text = (data.content ?? [])
    .filter((b) => b.type === "text" && typeof b.text === "string")
    .map((b) => b.text as string)
    .join("");

  return {
    text,
    usage: data.usage ?? null,
    unavailable: false,
  };
}

/**
 * Drop-in replacement for callGemini / callGroq — returns the response
 * text or throws on error / missing key. Use callClaudeRaw when the
 * caller needs usage info or wants to silently skip on missing key.
 */
export async function callClaude(
  messages: ClaudeMessage[],
  options: ClaudeOptions = {}
): Promise<string> {
  const out = await callClaudeRaw(messages, options);
  if (out.unavailable) {
    throw new Error("Claude unavailable: ANTHROPIC_API_KEY not set");
  }
  if (!out.text || out.text.trim().length === 0) {
    throw new Error("Claude returned empty response");
  }
  return out.text;
}
