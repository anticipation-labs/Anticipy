/**
 * /api/engine/auto-proceed
 *
 * The check-in flow renders a 30-second countdown ring on awaiting_user
 * intents. When the timeout fires client-side, the page POSTs here and
 * we flip the intent to status='auto_proceeded' using the row's
 * default_after_timeout ('yes' for reversible/low-stakes, 'no' for
 * irreversible). Auto-proceed is itself a learning signal — we record it
 * into anticipy_preferences with signal='auto_proceed'.
 *
 * If default_after_timeout='yes', we also kick the same execution path
 * the confirm endpoint uses so the agent runs the action. If 'no', the
 * intent is treated as user-declined.
 */
import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { executeAction } from "@/lib/execute-action";
import { requireSupabaseUser } from "@/lib/require-auth";
import { recordPreferenceSignal } from "@/lib/preference-record";
import { buildUserProfile } from "@/lib/meta-monitor";
import { embedAndStoreIntent } from "@/lib/episode-recall";
import { rateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const authedUser = await requireSupabaseUser(req);
  if (!authedUser) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Per-user limit. Each call may execute an action (web side effects).
  // 120/hr is generous: even a chatty user typically auto-proceeds at
  // most a handful of intents per minute and the timeout itself is 30s.
  const userLimit = rateLimit(`auto-proceed:user:${authedUser.id}`, 120, 60 * 60_000);
  if (!userLimit.allowed) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429 }
    );
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  const intentId =
    typeof (body as { intentId?: unknown }).intentId === "string"
      ? (body as { intentId: string }).intentId
      : "";
  if (!intentId) {
    return NextResponse.json(
      { error: "Missing intentId" },
      { status: 400 }
    );
  }

  // Pull the intent + session ownership in one round-trip-pair. We need to
  // verify the wearer owns the underlying session before we let them flip
  // the row's status.
  const { data: intent, error: fetchErr } = await supabaseAdmin
    .from("anticipy_intents")
    .select("*")
    .eq("id", intentId)
    .single();
  if (fetchErr || !intent) {
    return NextResponse.json({ error: "Intent not found" }, { status: 404 });
  }

  const { data: sess } = await supabaseAdmin
    .from("anticipy_sessions")
    .select("user_id")
    .eq("id", intent.session_id)
    .single();
  if (
    !sess ||
    (sess.user_id && sess.user_id !== authedUser.id)
  ) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  // Only auto-proceed from the awaiting_user state. Anything else means a
  // human (or another timer) already resolved this — be idempotent.
  if (intent.status !== "awaiting_user" && intent.status !== "pending") {
    return NextResponse.json(
      { ok: true, alreadyResolved: true, status: intent.status },
      { status: 200 }
    );
  }

  const fallbackRaw =
    typeof intent.default_after_timeout === "string"
      ? intent.default_after_timeout.trim().toLowerCase()
      : "no";
  // Default to "no" for safety when the field is missing — auto-proceeding
  // an action without a clear default risks irreversible side effects.
  const fallback = fallbackRaw === "yes" ? "yes" : "no";

  // Atomic flip: only move from awaiting_user/pending → auto_proceeded.
  const { data: updated, error: updErr } = await supabaseAdmin
    .from("anticipy_intents")
    .update({ status: "auto_proceeded" })
    .eq("id", intentId)
    .in("status", ["awaiting_user", "pending"])
    .select("id");
  if (updErr) {
    return NextResponse.json(
      { error: "Failed to update intent" },
      { status: 500 }
    );
  }
  if (!updated || updated.length === 0) {
    // Lost the race — someone else (yes/no/another timer) won. Idempotent.
    return NextResponse.json(
      { ok: true, alreadyResolved: true },
      { status: 200 }
    );
  }

  // Record the auto-proceed signal so future intent extraction can learn
  // which kinds of actions the wearer leaves untouched. Awaited because
  // Vercel kills the lambda the moment we return the response — a
  // fire-and-forget here loses the row.
  try {
    await recordPreferenceSignal(
      authedUser.id,
      {
        action_type: intent.action_type ?? null,
        summary_for_user: intent.summary_for_user ?? null,
        evidence_quote: intent.evidence_quote ?? null,
      },
      "auto_proceed"
    );
    // Meta-monitor profile rebuild — auto_proceed is a real signal too
    // (the user could have stepped in to skip and chose not to).
    try {
      await buildUserProfile(authedUser.id);
    } catch (err) {
      console.warn(
        "[auto-proceed] buildUserProfile failed (non-fatal):",
        err instanceof Error ? err.message : err
      );
    }
    // Episode embedding (same as /confirm): persist a Gemini vector over
    // the now-terminal intent so future /analyze calls can vector-recall
    // it. The status flip above this block already moved the row to
    // 'auto_proceeded', which is one of the terminal statuses
    // embedAndStoreIntent expects.
    try {
      await embedAndStoreIntent(intentId);
    } catch (err) {
      console.warn(
        "[auto-proceed] embedAndStoreIntent failed (non-fatal):",
        err instanceof Error ? err.message : err
      );
    }
  } catch (err) {
    console.warn(
      "[auto-proceed] recordPreferenceSignal threw unexpectedly:",
      err instanceof Error ? err.message : err
    );
  }

  // If the default is "yes" (reversible/low-stakes), run the action like
  // the confirm endpoint would. If "no", we stop here — auto_proceeded
  // with default 'no' is functionally a silent skip.
  let executionMessage = "";
  let executed = false;
  if (fallback === "yes") {
    try {
      const result = await executeAction(intent);
      executed = true;
      await supabaseAdmin
        .from("anticipy_intents")
        .update({ status: result.success ? "executed" : "failed" })
        .eq("id", intentId);
      await supabaseAdmin.from("anticipy_actions").insert({
        intent_id: intentId,
        status: result.success ? "success" : "failed",
        result: result.data,
        external_id: result.externalId,
      });
      executionMessage = result.message ?? "";
    } catch (err) {
      console.warn(
        "[auto-proceed] executeAction failed:",
        err instanceof Error ? err.message : err
      );
    }
  }

  return NextResponse.json({
    ok: true,
    intentId,
    fallback,
    executed,
    executionMessage,
  });
}
