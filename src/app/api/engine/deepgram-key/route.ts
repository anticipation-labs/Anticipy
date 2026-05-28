import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * GET /api/engine/deepgram-key — RETIRED 2026-05-13.
 *
 * Deepgram is on the v-final-prototype forbidden-provider list. This route
 * used to mint a short-lived Deepgram token for browser-side WebSocket
 * streaming; it now returns 503 with a clear message so callers can switch
 * to the local engine's ASR (Mistral voxtral-mini server-side, or Parakeet
 * TDT 0.6B v3 on the user's Mac via the v-final-prototype proactive engine).
 *
 * Kept as a stub (instead of deleted) so the /engine page and any cached
 * extension build that still polls this endpoint get a structured refusal
 * rather than a 404. Once the page-level transcription path is fully wired
 * to the local engine, this route can be removed.
 */
export async function GET() {
  return NextResponse.json(
    {
      error:
        "Deepgram retired. Server-side transcription should route through the local engine (Mistral voxtral-mini or local Parakeet).",
      retired_on: "2026-05-13",
    },
    { status: 503 }
  );
}
