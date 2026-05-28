import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { embedText, voyageAvailable, padVectorTo, vectorToPg } from "@/lib/voyage";

export const dynamic = "force-dynamic";

/**
 * POST /api/engine/trajectory
 *
 * Persists one browser-agent run trace from the Chrome extension. Called
 * from `BrowserAgent.run()`'s finally block. Auth is the same access-code
 * the extension uses for /api/extension/auth — we re-verify here so a
 * leaked code can't write trajectories under a different user.
 *
 * Body:
 *   {
 *     intent_id?: uuid,
 *     domain: string,            // hostname extracted from the start URL
 *     task_summary: string,      // intent.summary_for_user (the original ask)
 *     steps: object[],           // { action, result, signalDiff, timestamp } per step
 *     outcome: "success"|"partial"|"fail"|"aborted",
 *     outcome_message?: string,
 *     total_steps: number,
 *     duration_ms: number,
 *     cost_usd?: number          // when the agent tracks LLM cost (future)
 *   }
 *
 * Auth header:
 *   X-Anticipy-Code: <user's per-user access code>
 *
 * Returns:
 *   200 { id }            — trajectory row id
 *   401 { error }         — missing or invalid access code
 *   400 { error }         — malformed payload
 *   429 { error }         — rate-limited
 *   503 { error }         — Supabase hiccup (degrades cleanly; the agent
 *                           continues; we just lose this one trace)
 */
export async function POST(req: Request) {
  const corsHeaders = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Anticipy-Code",
  };

  // Rate limit per-IP — 240/min is plenty for an extension that fires
  // once per task, but defends against a leaked code spamming us.
  const ip = clientIp(req);
  const ipLimit = rateLimit(`trajectory:ip:${ip}`, 240, 60_000);
  if (!ipLimit.allowed) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429, headers: corsHeaders }
    );
  }

  const accessCode = (req.headers.get("X-Anticipy-Code") || "").trim();
  if (!accessCode) {
    return NextResponse.json(
      { error: "Missing X-Anticipy-Code" },
      { status: 401, headers: corsHeaders }
    );
  }

  // Per-code rate limit too — 600/day is way more than any sane wearer
  // generates (a heavy day might be 50-100 tasks).
  const codeLimit = rateLimit(`trajectory:code:${accessCode}`, 600, 24 * 60 * 60_000);
  if (!codeLimit.allowed) {
    return NextResponse.json(
      { error: "Daily trajectory quota exceeded for this code" },
      { status: 429, headers: corsHeaders }
    );
  }

  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400, headers: corsHeaders }
    );
  }

  const {
    intent_id,
    domain,
    task_summary,
    steps,
    outcome,
    outcome_message,
    total_steps,
    duration_ms,
    cost_usd,
  } = body || {};

  // Lightweight validation — bounce obviously malformed payloads before
  // burning a Supabase round-trip on them.
  if (typeof domain !== "string" || !domain.trim() ||
      typeof task_summary !== "string" || !task_summary.trim() ||
      !Array.isArray(steps) ||
      typeof outcome !== "string" ||
      !["success", "partial", "fail", "aborted"].includes(outcome)) {
    return NextResponse.json(
      { error: "Malformed payload" },
      { status: 400, headers: corsHeaders }
    );
  }
  // Bound the step count so a runaway agent can't write a 10-MB row.
  if (steps.length > 200) {
    return NextResponse.json(
      { error: "Too many steps (max 200)" },
      { status: 400, headers: corsHeaders }
    );
  }

  // Resolve access_code → user_id via the same engine_users table the
  // extension auth path uses. Service-role required to bypass RLS for the
  // lookup.
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );

  const { data: user, error: lookupErr } = await supabase
    .from("engine_users")
    .select("id")
    .eq("access_code", accessCode)
    .single();

  if (lookupErr || !user) {
    return NextResponse.json(
      { error: "Invalid access code" },
      { status: 401, headers: corsHeaders }
    );
  }

  // Insert the trajectory FIRST (with no embedding). Then, only for
  // successful trajectories, embed the task_summary via Voyage and update
  // the row in-place. Successful traces are the only ones the Planner
  // retrieves as RAG examples; embedding failed/aborted traces would be
  // wasted compute and risk poisoning future plans.
  const { data: row, error: insertErr } = await supabase
    .from("engine_trajectories")
    .insert({
      user_id: user.id,
      intent_id: intent_id ?? null,
      domain: domain.toLowerCase().trim(),
      task_summary: task_summary.substring(0, 2000),
      steps,
      outcome,
      outcome_message: outcome_message ? String(outcome_message).substring(0, 2000) : null,
      total_steps: Math.max(0, Math.min(200, Number(total_steps) || 0)),
      duration_ms: typeof duration_ms === "number" ? duration_ms : null,
      cost_usd: typeof cost_usd === "number" ? cost_usd : null,
    })
    .select("id")
    .single();

  if (insertErr || !row) {
    console.error("[engine/trajectory] insert failed:", insertErr);
    return NextResponse.json(
      { error: "Failed to persist trajectory" },
      { status: 503, headers: corsHeaders }
    );
  }

  // RAG corpus enrichment. Only embed `success` rows (others would mislead
  // the planner). Best-effort — if Voyage hiccups, the row exists without
  // an embedding and just doesn't get picked up by retrieval. Doesn't fail
  // the request.
  if (outcome === "success" && voyageAvailable()) {
    try {
      const { vector } = await embedText(task_summary.substring(0, 2000));
      const padded = padVectorTo(vector, 768);
      const pgVec = vectorToPg(padded);
      await supabase
        .from("engine_trajectories")
        .update({ task_embedding: pgVec })
        .eq("id", row.id);
    } catch (e: any) {
      console.warn(`[engine/trajectory] embedding skipped (non-fatal): ${e?.message || e}`);
    }
  }

  return NextResponse.json({ id: row.id }, { headers: corsHeaders });
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Anticipy-Code",
    },
  });
}
