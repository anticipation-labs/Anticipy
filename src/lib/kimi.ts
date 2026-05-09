/**
 * Server-side Kimi K2.6 client.
 *
 * Single model, single endpoint. NO multi-provider cascade — that was
 * fluff. Kimi K2.6 (Moonshot AI) is the agent backbone for the Anticipy
 * browser-agent team:
 *   - Native multimodal (we send screenshots when canvas/WebGL pages need them)
 *   - Agent-tuned for long-horizon coordination (4000-step pedigree)
 *   - $0.60 in / $0.95 out per 1M tokens
 *
 * Two surfaces:
 *   callKimi(messages, options)             — legacy: returns the raw text.
 *                                             Existing call sites still use this.
 *   callKimiRich({ system, messages, ... }) — returns { text, usage, raw }.
 *                                             Use this for the agent-team routes
 *                                             so we can track $ spend per call.
 *   callKimiJson<T>({ ... })                — JSON-mode + parse. Throws on bad JSON.
 */

const KIMI_API_KEY = process.env.KIMI_API_KEY!;
const KIMI_URL = "https://api.moonshot.ai/v1/chat/completions";
// K2.5 is the right engineering pick: same instruction-following as K2.6
// but with shorter reasoning_content output → ~40% fewer output tokens
// per call → ~16 tasks/$1 vs ~10 tasks/$1 on K2.6. Both require temp=1.
const KIMI_DEFAULT_MODEL = "kimi-k2.5";
const KIMI_DEFAULT_TEMPERATURE = 1.0;  // both K2.5 and K2.6 require temp=1

interface KimiMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export function kimiAvailable(): boolean {
  return Boolean(process.env.KIMI_API_KEY);
}

/**
 * Legacy entry point. Returns the assistant's text content directly.
 * Kept for backward compatibility with existing call sites in the repo.
 */
export async function callKimi(
  messages: KimiMessage[],
  options: {
    model?: string;
    temperature?: number;
    max_tokens?: number;
    response_format?: { type: string };
  } = {}
): Promise<string> {
  const {
    model = KIMI_DEFAULT_MODEL,
    temperature = 1,
    max_tokens = 4096,
    response_format,
  } = options;

  const body: Record<string, unknown> = {
    model,
    messages,
    temperature,
    max_tokens,
  };

  if (response_format) {
    body.response_format = response_format;
  }

  // 90-second timeout — Kimi K2.x is a reasoning model (~70s typical)
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90_000);

  const res = await fetch(KIMI_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${KIMI_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  });

  clearTimeout(timeout);

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Kimi error ${res.status}: ${err}`);
  }

  const data = await res.json();
  return data.choices[0]?.message?.content ?? "";
}

// ─── Rich call surface used by the agent-team routes ────────────────────

export interface KimiUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

export interface KimiCallResult {
  text: string;
  usage: KimiUsage;
  raw: any;
}

export interface KimiCallOptions {
  system?: string;
  messages: KimiMessage[];
  temperature?: number;
  maxTokens?: number;
  jsonMode?: boolean;
  /** Override the default K2.6 model (e.g. for vision-only requests) */
  model?: string;
}

export async function callKimiRich(opts: KimiCallOptions): Promise<KimiCallResult> {
  if (!process.env.KIMI_API_KEY) {
    throw new Error("KIMI_API_KEY missing");
  }

  const messages: KimiMessage[] = [];
  if (opts.system) messages.push({ role: "system", content: opts.system });
  for (const m of opts.messages) messages.push(m);

  const body: Record<string, unknown> = {
    model: opts.model ?? KIMI_DEFAULT_MODEL,
    messages,
    temperature: opts.temperature ?? KIMI_DEFAULT_TEMPERATURE,
    // K2.x is a reasoning model — it burns output tokens on
    // reasoning_content BEFORE writing actual content. Be generous with
    // max_tokens or you'll get empty content with finish_reason=length.
    // Caller can override; default 1200 leaves room for ~400 reasoning + ~800 content.
    max_tokens: opts.maxTokens ?? 1200,
  };
  if (opts.jsonMode) body.response_format = { type: "json_object" };

  // 60s timeout — agent-team calls are short (planner/verifier are quick)
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60_000);

  let resp: Response;
  try {
    resp = await fetch(KIMI_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${process.env.KIMI_API_KEY}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }

  if (!resp.ok) {
    const errText = await resp.text().catch(() => `status ${resp.status}`);
    throw new Error(`Kimi ${resp.status}: ${errText.substring(0, 240)}`);
  }
  const data = await resp.json();
  const text = data?.choices?.[0]?.message?.content ?? "";
  return { text, usage: data?.usage ?? {}, raw: data };
}

/**
 * Convenience: jsonMode=true plus parse. Tolerates ```json fences and
 * leading/trailing prose around the JSON object (small models occasionally
 * leak rationale).
 */
export async function callKimiJson<T = any>(opts: KimiCallOptions): Promise<T> {
  const { text } = await callKimiRich({ ...opts, jsonMode: true });
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
    throw new Error(`Kimi returned non-JSON: ${cleaned.substring(0, 240)}`);
  }
}

/** Estimated cost in USD. Input $0.60/M, output $0.95/M. */
export function kimiCostUsd(usage: KimiUsage): number {
  const inT = usage.prompt_tokens ?? 0;
  const outT = usage.completion_tokens ?? 0;
  return (inT * 0.6 + outT * 0.95) / 1_000_000;
}
