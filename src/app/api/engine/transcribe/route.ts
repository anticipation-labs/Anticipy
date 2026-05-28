import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { requireSupabaseUser } from "@/lib/require-auth";

export const dynamic = "force-dynamic";

// Deepgram is on the v-final-prototype forbidden-provider list (2026-05-13).
// The audio-upload (FormData) branch of this route used to call
// transcribeAudio from src/lib/deepgram. It now returns 503 with a clear
// message so callers can route audio through the local engine (Mistral
// voxtral-mini ASR or Parakeet TDT 0.6B on the user's Mac).
// The JSON-segments branch (pre-transcribed text from a streaming client)
// stays fully functional below.

// Cap the number of segments stored from the JSON path so a misbehaving
// client can't insert millions of rows in a single request.
const MAX_SEGMENTS_PER_REQUEST = 10_000;

async function assertOwnsSession(
  sessionId: string,
  userId: string
): Promise<boolean> {
  const { data } = await supabaseAdmin
    .from("anticipy_sessions")
    .select("user_id")
    .eq("id", sessionId)
    .single();
  if (!data) return false;
  // Legacy rows may have null user_id — treat those as owned-by-anyone-authed
  return !data.user_id || data.user_id === userId;
}

export async function POST(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const contentType = req.headers.get("content-type") || "";

    // JSON path: store pre-transcribed segments from streaming
    if (contentType.includes("application/json")) {
      const { sessionId, segments } = await req.json();
      if (!sessionId || typeof sessionId !== "string") {
        return NextResponse.json({ error: "Missing sessionId" }, { status: 400 });
      }
      if (!Array.isArray(segments) || segments.length === 0) {
        return NextResponse.json({ ok: true });
      }
      if (segments.length > MAX_SEGMENTS_PER_REQUEST) {
        return NextResponse.json(
          { error: "Too many segments in a single request." },
          { status: 413 }
        );
      }
      if (!(await assertOwnsSession(sessionId, user.id))) {
        return NextResponse.json({ error: "Session not found" }, { status: 404 });
      }

      const { error: insertError } = await supabaseAdmin
        .from("anticipy_transcripts")
        .insert(segments.map((s: Record<string, unknown>) => ({
          session_id: sessionId,
          speaker_id: s.speaker_id ?? 0,
          start_time: s.start_time ?? 0,
          end_time: s.end_time ?? 0,
          text: typeof s.text === "string" ? s.text.slice(0, 5000) : "",
          is_final: true,
        })));

      if (insertError) {
        console.error("Supabase insert error:", insertError);
      }

      return NextResponse.json({ ok: true, stored: segments.length });
    }

    // FormData (audio-upload) path — RETIRED 2026-05-13 along with Deepgram.
    // Callers should stream pre-transcribed segments via the JSON path above
    // using the local engine's ASR (Mistral voxtral-mini or Parakeet TDT).
    return NextResponse.json(
      {
        error:
          "Audio upload retired. Use the local engine for transcription and POST pre-transcribed segments to this route as application/json.",
        retired_on: "2026-05-13",
      },
      { status: 503 }
    );
  } catch (err) {
    console.error("Transcribe error:", err);
    return NextResponse.json(
      { error: "Transcription failed. Please try again." },
      { status: 500 }
    );
  }
}
