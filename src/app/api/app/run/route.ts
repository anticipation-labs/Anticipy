import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

/**
 * POST /api/app/run
 *
 * The customer's "press Listen" goes here. This proxies to the REAL
 * engine's /journey/run, which runs the whole real pipeline (real
 * audio -> real ASR -> real frozen reasoning -> real proactive_day
 * -> real comms -> real frozen browser action -> a real proposal).
 *
 * No mocking. If the engine is not running this returns the honest
 * gated state so the UI shows the truth, never a faked proposal.
 */
export async function POST(req: Request) {
  const url = process.env.ENGINE_URL || process.env.NEXT_PUBLIC_ENGINE_URL;
  if (!url) {
    return NextResponse.json(
      {
        ok: false,
        gated: true,
        reason:
          "No engine configured for this origin. This is the honest " +
          "gated state, not a faked proposal.",
      },
      { status: 200 }
    );
  }
  let body: unknown = {};
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  try {
    const r = await fetch(`${url.replace(/\/$/, "")}/journey/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      // the real pipeline (TTS + ASR + LLM + browser action) is slow
      signal: AbortSignal.timeout(280_000),
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.ok ? 200 : 502 });
  } catch (e) {
    return NextResponse.json(
      {
        ok: false,
        gated: true,
        reason:
          "Engine unreachable or the run exceeded the limit. Honest " +
          "gated state, not a faked success: " +
          (e instanceof Error ? e.message : String(e)),
      },
      { status: 200 }
    );
  }
}
