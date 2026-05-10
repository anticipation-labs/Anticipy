import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

/**
 * GET/POST /api/extension/agent-config
 *
 * Single source of truth for the browser-agent's RUNTIME config:
 *   - system_prompt: the AGENT_SYSTEM_PROMPT the executor sees
 *   - lesson_distill_prompt: prompt for Reflexion lesson generation
 *   - rewrite_prompt: prompt for friendly-error rewrites
 *   - tier_order: list of LLM provider names in preference order
 *   - per_tier: { spacing_ms, max_tokens, temperature } per provider
 *   - feature_flags: optional toggles
 *
 * The extension's agent.js fetches this on each task start, caches for
 * 60s. Means I can iterate prompts and behavior server-side without ever
 * making the user reload the extension.
 *
 * Auth: X-Anticipy-Code header (same shape as the rest of the
 * extension routes). Service-role lookup verifies the access code.
 *
 * Rate-limited at 240/min per IP.
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Anticipy-Code",
} as const;

// ── The actual runtime configuration ─────────────────────────────────
//
// Edit these strings to change agent behavior in production. Push to
// Vercel; the extension picks it up within 60s automatically.

const SYSTEM_PROMPT = `Browser automation agent. ONE action per turn. JSON only.

Actions:
{"action":"navigate","url":"..."}
{"action":"click","selector":"...","text":"..."}
{"action":"type","selector":"...","text":"...","submit":true}
{"action":"force_type","selector":"...","text":"..."}
{"action":"canvas_type","text":"..."}
{"action":"canvas_pointer","x":N,"y":N}
{"action":"pierce_query","text":"..."}
{"action":"keypress","key":"...","selector":"..."}
{"action":"scroll","direction":"down|up","amount":N}
{"action":"wait_for","selector":"...","text":"...","timeout":N}
{"action":"dismiss_modal"}
{"action":"open_tab","url":"..."}
{"action":"switch_tab","tabId":N}
{"action":"extract","selector":"...","field":"..."}
{"action":"getPageState"}
{"action":"done","success":true|false,"message":"..."}

Rules:
- Read VISIBLE TEXT first. Answer usually there. Don't extract if not needed.
- Direct URL beats search-and-click. Wikipedia: en.wikipedia.org/wiki/X.
- type+submit:true for search boxes.
- After click that should navigate, check OBSERVED EFFECT next turn. If unchanged, pick different element.
- Multi-tab: extract A → open_tab B → extract B → done. Don't loiter on A.
- Login wall: done(success:false) with one-sentence reason.
- done.message MUST contain the actual answer (years, names, prices, headlines verbatim). Never "I found the answer."
- Final action must be done.

Output one action object. JSON only, no fences.`;

const LESSON_DISTILL_PROMPT_TEMPLATE = `You're distilling one GENERALIZED lesson from a browser-agent run.
Output one short lesson (<= 22 words) that would help a browser agent on ANY similar future task.

Rules:
- The lesson MUST be GENERALIZED — never name a specific site or URL.
- Talk about CATEGORIES of pages: encyclopedias, news sites, e-commerce, social, search engines, forms, video sites.
- The lesson must be ACTIONABLE: name a behavior to repeat (success) or avoid (failure).
- If nothing useful was learned, output the literal string: SKIP.

JSON only: {"lesson": "<the lesson, or 'SKIP'>"}`;

const REWRITE_PROMPT_TEMPLATE = `Rewrite this internal browser-agent error as ONE calm sentence (<= 22 words) for a non-technical user. No apologies, no jargon, no model names. Say what happened at a human level and what they could try.

INTERNAL: {ERROR}`;

const RUNTIME_CONFIG = {
  version: "2026-05-10-1",
  system_prompt: SYSTEM_PROMPT,
  lesson_distill_prompt_template: LESSON_DISTILL_PROMPT_TEMPLATE,
  rewrite_prompt_template: REWRITE_PROMPT_TEMPLATE,
  // Tier order: extension tries these in order, each with proactive
  // spacing. Cerebras Qwen3-235B (free 1M tok/day, ~250ms) is the
  // primary; Groq llama-3.3-70b (free 14400 RPD, but daily-token-limit
  // sensitive) is fallback; Kimi paid is last resort.
  tier_order: ["cerebras", "groq", "kimi"],
  per_tier: {
    cerebras: {
      spacing_ms: 2000,
      max_tokens: 2400,
      temperature: 0.1,
      timeout_ms: 20000,
    },
    groq: {
      spacing_ms: 2000,
      max_tokens: 2400,
      temperature: 0.1,
      timeout_ms: 20000,
    },
    kimi: {
      spacing_ms: 500,
      max_tokens: 2400,
      temperature: 0.1,
      timeout_ms: 30000,
    },
  },
  feature_flags: {
    verifier_enabled: true,
    critic_enabled: true,
    reflector_enabled: true,
    reflexion_distill_enabled: true,
    settle_enabled: true,
    settle_floor_ms: 400,
  },
} as const;


export async function POST(req: Request) {
  const ip = clientIp(req);
  const ipLimit = rateLimit(`agent-cfg:ip:${ip}`, 240, 60_000);
  if (!ipLimit.allowed) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429, headers: CORS_HEADERS });
  }

  const accessCode = (req.headers.get("X-Anticipy-Code") || "").trim();
  if (!accessCode) {
    return NextResponse.json({ error: "Missing X-Anticipy-Code" }, { status: 401, headers: CORS_HEADERS });
  }

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );
  const { data: user } = await supabase
    .from("engine_users")
    .select("id")
    .eq("access_code", accessCode)
    .single();
  if (!user) {
    return NextResponse.json({ error: "Invalid access code" }, { status: 401, headers: CORS_HEADERS });
  }

  // Cache headers — 30s server-side, extension also caches 60s. Total
  // propagation worst-case ~90s after a Vercel deploy.
  return NextResponse.json(RUNTIME_CONFIG, {
    headers: {
      ...CORS_HEADERS,
      "Cache-Control": "public, max-age=30, s-maxage=30",
    },
  });
}

export async function GET(req: Request) {
  return POST(req);
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS_HEADERS });
}
