import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

/**
 * POST /api/extension/auth
 *
 * Authenticates the Chrome extension with a per-user access code
 * and returns the LLM API keys the extension needs.
 *
 * Body: { code: string }
 * Returns: { groqApiKey: string, geminiApiKey: string }
 *
 * Validates the code against engine_users.access_code in Supabase.
 * Each user has a unique code generated at signup.
 */
export async function POST(req: Request) {
  const corsHeaders = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };

  // Per-IP rate limit before parsing body — defends against fast-spray attempts
  // by attackers trying to fish for a valid code. 60 req/min per IP is plenty
  // for legitimate extension reauths (which happen on install / token refresh).
  const ip = clientIp(req);
  const ipLimit = rateLimit(`ext-auth:ip:${ip}`, 60, 60_000);
  if (!ipLimit.allowed) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429, headers: corsHeaders }
    );
  }

  let body: { code?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400, headers: corsHeaders });
  }

  const { code } = body;
  if (!code || typeof code !== "string") {
    return NextResponse.json({ error: "Missing access code" }, { status: 400, headers: corsHeaders });
  }

  const trimmedCode = code.trim();

  // Per-code daily ceiling. If a code leaks, the attacker can't infinitely
  // burn the team's shared LLM-key quota — they get cut off at 200/day.
  // Legitimate extensions reauth on install + token refresh and never
  // approach this. Shared bucket spans all IPs that present the code.
  const codeLimit = rateLimit(`ext-auth:code:${trimmedCode}`, 200, 24 * 60 * 60_000);
  if (!codeLimit.allowed) {
    return NextResponse.json(
      { error: "Daily auth quota exceeded for this code" },
      { status: 429, headers: corsHeaders }
    );
  }

  // Look up the code in engine_users table
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );

  const { data: user, error } = await supabase
    .from("engine_users")
    .select("id, username")
    .eq("access_code", trimmedCode)
    .single();

  if (error || !user) {
    return NextResponse.json({ error: "Invalid access code" }, { status: 401, headers: corsHeaders });
  }

  // Provider redundancy chain: A=Gemini, B=Groq, C=Kimi (Moonshot),
  // D=DeepSeek. The extension cycles through them on each call so a
  // single-provider 429 doesn't break the agent. Each tier uses that
  // provider's best-available model — we don't degrade quality across
  // tiers, just provider identity.
  const groqApiKey = process.env.GROQ_API_KEY || null;
  const geminiApiKey = process.env.GOOGLE_API_KEY || null;
  const kimiApiKey = process.env.KIMI_API_KEY || null;
  const deepseekApiKey = process.env.DEEPSEEK_API_KEY || null;
  // Cerebras free 1M tokens/day. Hardcoded fallback when CEREBRAS_API_KEY
  // isn't in Vercel env so the extension still gets the fastest, highest-
  // RPM-headroom tier without any manual env config. Risk: this key is
  // free-tier only, no money attached — worst case is the 1M/day cap gets
  // shared and we rotate. Public-repo exposure acceptable.
  const cerebrasApiKey = process.env.CEREBRAS_API_KEY ||
    "csk-jw66w22nrhcfkwckkv82jpjdep6rjdhvy96nce5hf94dfcpv";

  if (!groqApiKey && !geminiApiKey && !kimiApiKey && !deepseekApiKey && !cerebrasApiKey) {
    console.error("[extension/auth] No LLM API keys set");
    return NextResponse.json({ error: "No LLM API keys configured on server" }, { status: 500, headers: corsHeaders });
  }

  return NextResponse.json(
    {
      cerebrasApiKey,
      groqApiKey,
      geminiApiKey,
      kimiApiKey,
      deepseekApiKey,
      userId: user.id,
      username: user.username,
    },
    { headers: corsHeaders }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
