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

const SYSTEM_PROMPT = `Browser agent. JSON only. Hard limit: 2 LLM calls per task. ALWAYS try this 2-step pattern first.

STEP 1: navigate to the most-likely direct URL.
STEP 2: done with the answer read from VISIBLE TEXT.

Actions:
{"action":"navigate","url":"..."}
{"action":"done","success":true|false,"message":"..."}

Examples:
Task: "year Python was released"
  {"action":"navigate","url":"https://en.wikipedia.org/wiki/Python_(programming_language)"}
  {"action":"done","success":true,"message":"Python was first released in 1991."}

Task: "capital of France"
  {"action":"navigate","url":"https://en.wikipedia.org/wiki/France"}
  {"action":"done","success":true,"message":"The capital of France is Paris."}

Task: "Taj Mahal: who built it and when"
  {"action":"navigate","url":"https://en.wikipedia.org/wiki/Taj_Mahal"}
  {"action":"done","success":true,"message":"Built by Mughal emperor Shah Jahan, completed around 1648."}

After navigate, the agent context shows you the page's VISIBLE TEXT. Read it carefully — the answer is in there. Quote actual values verbatim (years, names, prices). NEVER respond "I found the answer" or similar.

If the page didn't load or the answer isn't visible, you have ONE more shot: a click or extract action. Then done. Three total max.

Login wall / blocked: done(success:false,message:"reason").

Output ONE action object. No fences. No prose.`;

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
  version: "2026-05-13-v7",
  system_prompt: SYSTEM_PROMPT,
  lesson_distill_prompt_template: LESSON_DISTILL_PROMPT_TEMPLATE,
  rewrite_prompt_template: REWRITE_PROMPT_TEMPLATE,
  // Tier order: extension tries these in order, each with proactive
  // spacing. Cerebras Qwen3-235B (free 1M tok/day, ~250ms) is the
  // primary; Groq llama-3.3-70b (free 14400 RPD, but daily-token-limit
  // sensitive) is fallback; Mistral mistral-small-latest (free, 262K ctx)
  // is third-tier. Kimi removed 2026-05-13 per v-final-prototype whitelist.
  //
  // Extension v7+ reads per_tier[name].spacing_ms at runtime — bumping
  // these values here propagates within 60s without an extension reload.
  // This is how we fix the "30 RPM burst" pattern that killed the 0/35
  // benchmark without forcing the user to reload at chrome://extensions.
  tier_order: ["cerebras", "groq", "mistral"],
  per_tier: {
    cerebras: {
      // 30 RPM ceiling = 2000ms is mathematical, but in practice Cerebras
      // measures against a sliding window with clock drift, so 2000ms hits
      // 429 spikes. 2500ms (~24 RPM) keeps the burst pattern out of the
      // throttled zone. v7 default; iterate if 429 still spikes.
      spacing_ms: 2500,
      max_tokens: 2400,
      temperature: 0.1,
      timeout_ms: 20000,
    },
    groq: {
      // Groq is mostly daily-token-limited (TPD), not RPM. 2000ms is
      // comfortable; bumping doesn't help since the bottleneck is tokens.
      spacing_ms: 2000,
      max_tokens: 2400,
      temperature: 0.1,
      timeout_ms: 20000,
    },
    mistral: {
      // La Plateforme free tier is ~1 req/sec. 1200ms keeps us safely
      // under that without leaving headroom on the table.
      spacing_ms: 1200,
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
