import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const dynamic = "force-dynamic";

/**
 * Read-only progress probe for a voice-onboarding call.
 *
 * Called by the local engine's /api/onboarding/voice_status which
 * surfaces the same shape to the desktop popover. Returns:
 *   {phase, question_index, question_total, answers, completed,
 *    dossier_fragment}.
 *
 * No auth: this exposes only the row's question progress (and the
 * raw answers the same engine that placed the call already has).
 * Anyone who knows the random call_sid can read it, which is the
 * same trust boundary Twilio uses.
 */

interface CallRow {
  status: string | null;
  question_index: number | null;
  question_total: number | null;
  answers: unknown;
  dossier_written: boolean | null;
  dossier_fragment?: unknown;
  error: string | null;
  placed_at: string;
  updated_at: string;
}

function phaseFromStatus(row: CallRow): string {
  if (row.error) return "error";
  if (row.dossier_written) return "completed";
  const s = (row.status || "").toLowerCase();
  if (s === "completed") return "completed";
  if (s === "failed" || s === "no-answer" || s === "busy" || s === "canceled") {
    return "error";
  }
  if ((row.question_index || 0) > 0) return "in_progress";
  if (s === "queued" || s === "ringing" || s === "initiated") {
    return "calling";
  }
  return "in_progress";
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const callSid = (url.searchParams.get("call_sid") || "").trim();
  const accountId = (url.searchParams.get("account_id") || "").trim();
  if (!callSid && !accountId) {
    return NextResponse.json(
      { ok: false, error: "call_sid or account_id required" },
      { status: 400 },
    );
  }
  let q = supabaseAdmin
    .from("anticipy_voice_onboarding_calls")
    .select(
      "status, question_index, question_total, answers, dossier_written, dossier_fragment, error, placed_at, updated_at, twilio_sid, account_id",
    )
    .order("placed_at", { ascending: false })
    .limit(1);
  if (callSid) {
    q = q.eq("twilio_sid", callSid);
  } else {
    q = q.eq("account_id", accountId);
  }
  const { data, error } = await q.maybeSingle();
  if (error) {
    console.error("[voice-onboarding-status] select failed", error);
    return NextResponse.json(
      { ok: false, error: "lookup failed" },
      { status: 500 },
    );
  }
  if (!data) {
    return NextResponse.json(
      {
        ok: true,
        phase: "calling",
        question_index: 0,
        question_total: 7,
        answers: [],
        completed: false,
      },
      { status: 200 },
    );
  }
  const row = data as CallRow;
  const phase = phaseFromStatus(row);
  return NextResponse.json({
    ok: true,
    phase,
    question_index: row.question_index ?? 0,
    question_total: row.question_total ?? 7,
    answers: Array.isArray(row.answers) ? row.answers : [],
    completed: !!row.dossier_written,
    dossier_fragment: row.dossier_fragment ?? null,
    error: row.error || null,
    updated_at: row.updated_at,
  });
}
