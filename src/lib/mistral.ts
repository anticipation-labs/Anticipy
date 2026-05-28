// Mistral La Plateforme client. OpenAI-compatible chat completions.
//
// Replaces src/lib/{claude,kimi}.ts in the v-final-prototype provider
// whitelist (2026-05-13). mistral-small-latest is the workhorse — 262K
// ctx, vision+tools+reasoning, free tier (~1 req/sec) — and matches the
// engine's role chain primary for the critic role.

const MISTRAL_API_KEY = process.env.MISTRAL_API_KEY!;
const MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions";

interface MistralMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export function mistralAvailable(): boolean {
  return Boolean(process.env.MISTRAL_API_KEY);
}

export async function callMistral(
  messages: MistralMessage[],
  options: {
    model?: string;
    temperature?: number;
    max_tokens?: number;
    response_format?: { type: string };
    jsonOnly?: boolean;
  } = {}
): Promise<string> {
  const {
    model = "mistral-small-latest",
    temperature = 0.0,
    max_tokens = 4096,
    response_format,
    jsonOnly,
  } = options;

  const body: Record<string, unknown> = {
    model,
    messages,
    temperature,
    max_tokens,
  };

  if (response_format) {
    body.response_format = response_format;
  } else if (jsonOnly) {
    body.response_format = { type: "json_object" };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  let res: Response;
  try {
    res = await fetch(MISTRAL_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${MISTRAL_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }

  if (!res.ok) {
    const err = await res.text().catch(() => `status ${res.status}`);
    throw new Error(`Mistral ${res.status}: ${err.substring(0, 240)}`);
  }

  const data = await res.json();
  return data?.choices?.[0]?.message?.content ?? "";
}

// ── Rich call surface (parity with groq.ts) ──────────────────────────────

export interface MistralCallOptions {
  system?: string;
  messages: MistralMessage[];
  temperature?: number;
  maxTokens?: number;
  jsonMode?: boolean;
  model?: string;
}

export async function callMistralRich(
  opts: MistralCallOptions
): Promise<{ text: string; usage: unknown; raw: unknown }> {
  const key = process.env.MISTRAL_API_KEY;
  if (!key) throw new Error("MISTRAL_API_KEY missing");
  const messages: MistralMessage[] = [];
  if (opts.system) messages.push({ role: "system", content: opts.system });
  for (const m of opts.messages) messages.push(m);
  const body: Record<string, unknown> = {
    model: opts.model ?? "mistral-small-latest",
    messages,
    temperature: opts.temperature ?? 0.0,
    max_tokens: opts.maxTokens ?? 1200,
  };
  if (opts.jsonMode) body.response_format = { type: "json_object" };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  let resp: Response;
  try {
    resp = await fetch(MISTRAL_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${key}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
  if (!resp.ok) {
    const errText = await resp.text().catch(() => `status ${resp.status}`);
    throw new Error(`Mistral ${resp.status}: ${errText.substring(0, 240)}`);
  }
  const data = await resp.json();
  const text = data?.choices?.[0]?.message?.content ?? "";
  return { text, usage: data?.usage ?? {}, raw: data };
}

export async function callMistralJson<T = unknown>(
  opts: MistralCallOptions
): Promise<T> {
  const { text } = await callMistralRich({ ...opts, jsonMode: true });
  let cleaned = text.trim();
  cleaned = cleaned
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start !== -1 && end !== -1 && end > start) {
    cleaned = cleaned.substring(start, end + 1);
  }
  try {
    return JSON.parse(cleaned) as T;
  } catch {
    throw new Error(`Mistral returned non-JSON: ${cleaned.substring(0, 240)}`);
  }
}
