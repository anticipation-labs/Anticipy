import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { callClaudeRaw, claudeAvailable } from "@/lib/claude";
import { rateLimit, clientIp } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

/**
 * POST /api/extension/llm-proxy
 *
 * Server-side proxy for Claude calls from the Chrome extension.
 * The extension cannot hit api.anthropic.com directly: Anthropic does
 * not send Access-Control-Allow-Origin for browser origins, so a CORS
 * preflight from a chrome-extension:// page is rejected. This route
 * relays the call from a same-origin server context.
 *
 * Auth: the extension passes the access_code it already uses for
 *   /api/extension/auth. The code is validated against engine_users
 *   before we burn an Anthropic call. Same auth shape as the rest of
 *   the extension routes — no new credentials to ship.
 *
 * Body shape:
 *   { code: string,
 *     systemPrompt: string,
 *     userMessage: string,
 *     model?: string,            // default claude-sonnet-4-5
 *     maxTokens?: number,        // default 4096
 *     temperature?: number,      // default 0.0
 *     jsonOnly?: boolean }       // default true
 *
 * Response: { ok: true, text: string, usage: ... } or { error: string }.
 *
 * Notes:
 *  - We intentionally do NOT accept arbitrary Anthropic params (e.g.
 *    tools, system arrays). The agent only needs single-turn JSON
 *    responses, and a narrower contract is easier to lock down.
 *  - On missing ANTHROPIC_API_KEY, returns 503 so the extension can
 *    cleanly fall back to its existing Gemini Pro escalation.
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
} as const;

interface ProxyBody {
  code?: string;
  systemPrompt?: string;
  userMessage?: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
  jsonOnly?: boolean;
}

export async function POST(req: Request) {
  // Per-IP burst limit before any work. Each call burns Anthropic credits;
  // 30/min per IP is well above any legitimate per-user agent loop and well
  // below what a malicious caller could use to drain quota.
  const ip = clientIp(req);
  const ipLimit = rateLimit(`ext-llm:ip:${ip}`, 30, 60_000);
  if (!ipLimit.allowed) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429, headers: CORS_HEADERS }
    );
  }

  if (!claudeAvailable()) {
    return NextResponse.json(
      { error: "Claude not configured on this deployment" },
      { status: 503, headers: CORS_HEADERS }
    );
  }

  let body: ProxyBody;
  try {
    body = (await req.json()) as ProxyBody;
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400, headers: CORS_HEADERS }
    );
  }

  const code = typeof body.code === "string" ? body.code.trim() : "";
  const systemPrompt =
    typeof body.systemPrompt === "string" ? body.systemPrompt : "";
  const userMessage =
    typeof body.userMessage === "string" ? body.userMessage : "";
  if (!code || !systemPrompt || !userMessage) {
    return NextResponse.json(
      { error: "Missing code, systemPrompt, or userMessage" },
      { status: 400, headers: CORS_HEADERS }
    );
  }

  // Same auth shape as /api/extension/auth — validate the access_code
  // against engine_users so this proxy isn't an open relay to Anthropic.
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );
  const { data: user, error: lookupErr } = await supabase
    .from("engine_users")
    .select("id")
    .eq("access_code", code)
    .single();
  if (lookupErr || !user) {
    return NextResponse.json(
      { error: "Invalid access code" },
      { status: 401, headers: CORS_HEADERS }
    );
  }

  // Per-code daily ceiling. Each Claude call costs real money; a leaked
  // access code can't burn unlimited credits. 1000/day is generous for a
  // genuinely active user (agent loops average 10-30 calls/task) and
  // bounded enough to be visible on a finance dashboard if hit.
  const codeLimit = rateLimit(`ext-llm:code:${code}`, 1000, 24 * 60 * 60_000);
  if (!codeLimit.allowed) {
    return NextResponse.json(
      { error: "Daily LLM quota exceeded for this code" },
      { status: 429, headers: CORS_HEADERS }
    );
  }

  const model = typeof body.model === "string" ? body.model : "claude-sonnet-4-5";
  const maxTokens = typeof body.maxTokens === "number" ? body.maxTokens : 4096;
  const temperature =
    typeof body.temperature === "number" ? body.temperature : 0.0;
  const jsonOnly = body.jsonOnly !== false; // default true for the agent path

  try {
    const out = await callClaudeRaw(
      [
        { role: "system", content: systemPrompt },
        { role: "user", content: userMessage },
      ],
      { model, max_tokens: maxTokens, temperature, jsonOnly }
    );
    if (out.unavailable) {
      return NextResponse.json(
        { error: "Claude unavailable" },
        { status: 503, headers: CORS_HEADERS }
      );
    }
    return NextResponse.json(
      { ok: true, text: out.text, usage: out.usage },
      { headers: CORS_HEADERS }
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.warn("[extension/llm-proxy] Claude call failed:", msg);
    return NextResponse.json(
      { error: msg.substring(0, 240) },
      { status: 502, headers: CORS_HEADERS }
    );
  }
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS_HEADERS });
}
