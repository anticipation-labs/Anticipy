/**
 * Per-provider isolation smoke test for the 4-tier LLM cascade.
 *
 * Goal: prove that EACH provider (Gemini, Groq, Kimi, DeepSeek) can carry
 * the load alone — not just that the cascade compiles. The production
 * cascade smoke test only proves "whichever plan is up answered"; this
 * script isolates each plan and calls it directly, so we know any one of
 * them is sufficient as a fallback for the others.
 *
 * For each provider we issue a tiny intent-extraction-shaped prompt and
 * verify:
 *   - the call resolves without throwing
 *   - the response is valid JSON
 *   - the JSON contains an `action` field (matches the tiny system spec)
 *
 * The script reports a per-provider table:
 *   provider | ok | latency_ms | model_used | error_msg
 *
 * Run standalone:
 *   npx tsx scripts/smoke_per_provider.ts
 *
 * Exit code: 0 if at least one provider works; 1 if all four fail.
 *
 * Permanent artifact — safe to wire into CI once test keys are provisioned.
 */
import { readFileSync, existsSync } from "fs";

// Load .env.local BEFORE importing any module that may capture
// process.env at load time. Dynamic imports below are gated on this.
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && !process.env[m[1]]) {
      process.env[m[1]] = m[2].replace(/^"|"$/g, "");
    }
  }
}

// Tiny system prompt (~1KB) modeled on the agent intent-extraction shape.
// Small enough to keep token cost trivial; specific enough that a working
// model emits the same JSON schema across all four providers.
const TINY_AGENT_SYSTEM = `You are a browser action agent. The user describes a task they want \
performed on a real website. Return STRICT JSON ONLY with the following schema:

{
  "action": "navigate" | "click" | "type" | "extract" | "search",
  "target": "<url-or-element-description>",
  "intent": "<one-sentence-restatement-of-what-the-user-wants>"
}

Rules:
- Output JSON only. No markdown fences, no commentary, no trailing prose.
- "action" MUST be one of the five literal values above.
- For information-retrieval requests like "find the headline on bbc.com", \
the action is "extract" and the target is the URL.
- For shopping or query requests, the action is "search".
- For pure navigation, the action is "navigate".
- Be deterministic: the same input MUST produce the same output.

Example:
Input: "Find the top story on hacker news"
Output: {"action":"extract","target":"https://news.ycombinator.com","intent":"retrieve the top story headline"}`;

const USER_MSG = "Find the headline on bbc.com";

interface ProviderResult {
  provider: "gemini" | "groq" | "kimi" | "deepseek";
  ok: boolean;
  latency_ms: number;
  model_used: string;
  raw_len: number;
  error_msg: string | null;
  /** Truncated parsed shape, useful for eyeballing in the report. */
  parsed_action: string | null;
}

function nowMs(): number {
  return Date.now();
}

function tryParseAction(text: string): { action: string | null; raw: unknown } {
  if (!text || !text.trim()) return { action: null, raw: null };
  // Strip markdown fences in case a model wrapped JSON despite instructions.
  const cleaned = text
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();
  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    // Try widest object substring extraction.
    const start = cleaned.indexOf("{");
    const end = cleaned.lastIndexOf("}");
    if (start < 0 || end <= start) return { action: null, raw: null };
    try {
      parsed = JSON.parse(cleaned.slice(start, end + 1));
    } catch {
      return { action: null, raw: null };
    }
  }
  if (!parsed || typeof parsed !== "object") return { action: null, raw: parsed };
  const obj = parsed as Record<string, unknown>;
  const action = typeof obj.action === "string" ? obj.action : null;
  return { action, raw: parsed };
}

async function probeGemini(): Promise<ProviderResult> {
  const start = nowMs();
  const model = "gemini-2.5-flash";
  try {
    const { callGemini } = await import("../src/lib/gemini");
    const resp = await callGemini(
      [
        { role: "system", content: TINY_AGENT_SYSTEM },
        { role: "user", content: USER_MSG },
      ],
      { temperature: 0, max_tokens: 256 }
    );
    const { action } = tryParseAction(resp);
    const ok = !!action;
    return {
      provider: "gemini",
      ok,
      latency_ms: nowMs() - start,
      model_used: model,
      raw_len: resp.length,
      error_msg: ok ? null : `parse failed; raw=${resp.slice(0, 120).replace(/\s+/g, " ")}`,
      parsed_action: action,
    };
  } catch (e) {
    return {
      provider: "gemini",
      ok: false,
      latency_ms: nowMs() - start,
      model_used: model,
      raw_len: 0,
      error_msg: e instanceof Error ? e.message.slice(0, 200) : String(e).slice(0, 200),
      parsed_action: null,
    };
  }
}

async function probeGroq(): Promise<ProviderResult> {
  const start = nowMs();
  const model = "llama-3.3-70b-versatile";
  try {
    const { callGroq } = await import("../src/lib/groq");
    const resp = await callGroq(
      [
        { role: "system", content: TINY_AGENT_SYSTEM },
        { role: "user", content: USER_MSG },
      ],
      {
        temperature: 0,
        max_tokens: 256,
        response_format: { type: "json_object" },
      }
    );
    const { action } = tryParseAction(resp);
    const ok = !!action;
    return {
      provider: "groq",
      ok,
      latency_ms: nowMs() - start,
      model_used: model,
      raw_len: resp.length,
      error_msg: ok ? null : `parse failed; raw=${resp.slice(0, 120).replace(/\s+/g, " ")}`,
      parsed_action: action,
    };
  } catch (e) {
    return {
      provider: "groq",
      ok: false,
      latency_ms: nowMs() - start,
      model_used: model,
      raw_len: 0,
      error_msg: e instanceof Error ? e.message.slice(0, 200) : String(e).slice(0, 200),
      parsed_action: null,
    };
  }
}

async function probeKimi(): Promise<ProviderResult> {
  const start = nowMs();
  // Match the cascade's pinned 128k variant — k2.5 has the temp=1
  // restriction so the cascade pins moonshot-v1-128k instead.
  const model = "moonshot-v1-128k";
  try {
    const { callKimi } = await import("../src/lib/kimi");
    const resp = await callKimi(
      [
        { role: "system", content: TINY_AGENT_SYSTEM },
        { role: "user", content: USER_MSG },
      ],
      {
        model,
        temperature: 0,
        max_tokens: 256,
        response_format: { type: "json_object" },
      }
    );
    const { action } = tryParseAction(resp);
    const ok = !!action;
    return {
      provider: "kimi",
      ok,
      latency_ms: nowMs() - start,
      model_used: model,
      raw_len: resp.length,
      error_msg: ok ? null : `parse failed; raw=${resp.slice(0, 120).replace(/\s+/g, " ")}`,
      parsed_action: action,
    };
  } catch (e) {
    return {
      provider: "kimi",
      ok: false,
      latency_ms: nowMs() - start,
      model_used: model,
      raw_len: 0,
      error_msg: e instanceof Error ? e.message.slice(0, 200) : String(e).slice(0, 200),
      parsed_action: null,
    };
  }
}

async function probeDeepSeek(): Promise<ProviderResult> {
  const start = nowMs();
  const model = "deepseek-chat";
  const url = "https://api.deepseek.com/chat/completions";
  const key = process.env.DEEPSEEK_API_KEY;
  if (!key) {
    return {
      provider: "deepseek",
      ok: false,
      latency_ms: 0,
      model_used: model,
      raw_len: 0,
      error_msg: "DEEPSEEK_API_KEY not set",
      parsed_action: null,
    };
  }
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: "system", content: TINY_AGENT_SYSTEM },
          { role: "user", content: USER_MSG },
        ],
        temperature: 0,
        max_tokens: 256,
        response_format: { type: "json_object" },
      }),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return {
        provider: "deepseek",
        ok: false,
        latency_ms: nowMs() - start,
        model_used: model,
        raw_len: 0,
        error_msg: `HTTP ${res.status}: ${body.slice(0, 200)}`,
        parsed_action: null,
      };
    }
    const data = (await res.json()) as {
      choices?: Array<{ message?: { content?: string } }>;
    };
    const content = data.choices?.[0]?.message?.content ?? "";
    const { action } = tryParseAction(content);
    const ok = !!action;
    return {
      provider: "deepseek",
      ok,
      latency_ms: nowMs() - start,
      model_used: model,
      raw_len: content.length,
      error_msg: ok ? null : `parse failed; raw=${content.slice(0, 120).replace(/\s+/g, " ")}`,
      parsed_action: action,
    };
  } catch (e) {
    return {
      provider: "deepseek",
      ok: false,
      latency_ms: nowMs() - start,
      model_used: model,
      raw_len: 0,
      error_msg: e instanceof Error ? e.message.slice(0, 200) : String(e).slice(0, 200),
      parsed_action: null,
    };
  }
}

function pad(s: string, n: number): string {
  if (s.length >= n) return s.slice(0, n);
  return s + " ".repeat(n - s.length);
}

function printReport(results: ProviderResult[]): void {
  console.log("");
  console.log("=== Per-provider cascade isolation smoke ===");
  console.log("");
  console.log(
    `${pad("provider", 10)}  ${pad("ok", 5)}  ${pad("ms", 7)}  ${pad("model", 28)}  ${pad("action", 12)}  error`
  );
  console.log("-".repeat(110));
  for (const r of results) {
    console.log(
      `${pad(r.provider, 10)}  ${pad(r.ok ? "PASS" : "FAIL", 5)}  ${pad(
        String(r.latency_ms),
        7
      )}  ${pad(r.model_used, 28)}  ${pad(r.parsed_action ?? "-", 12)}  ${
        r.error_msg ?? ""
      }`
    );
  }
  console.log("");
  const passed = results.filter((r) => r.ok).length;
  console.log(`Summary: ${passed}/${results.length} providers passed.`);
  for (const r of results) {
    if (!r.ok) {
      console.log(
        `  - ${r.provider} FAILED: ${r.error_msg ?? "unknown"}`
      );
    }
  }
}

async function main(): Promise<void> {
  // Run providers in parallel — each is an independent network call to a
  // different host, so wall-clock is bounded by the slowest (Kimi).
  const results = await Promise.all([
    probeGemini(),
    probeGroq(),
    probeKimi(),
    probeDeepSeek(),
  ]);
  printReport(results);
  // Exit non-zero only if NONE of the providers worked. Per-provider
  // failures (e.g., DeepSeek out of credits) are expected and reported,
  // not fatal — the cascade can survive any single-provider outage.
  const anyOk = results.some((r) => r.ok);
  process.exit(anyOk ? 0 : 1);
}

main().catch((e) => {
  console.error("smoke_per_provider crashed:", e);
  process.exit(2);
});
