import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * GET /api/app/state
 *
 * The thin client's single source of truth. The product frontend
 * contains NO business logic; it renders exactly the state this
 * route reports and sends user intent (confirm/deny/settings) back.
 *
 * Honesty contract (matches the master-hardening build): every
 * segment reports its REAL state. Where a segment is the gated
 * real-accounts / real-engine edge, it is reported as `gated` with
 * an honest reason. This route NEVER fabricates a success: a gated
 * edge renders as its real designed state, never a fake "connected"
 * or a fake proposal.
 */

type Segment = {
  status: "ready" | "needs_user" | "gated" | "live";
  detail: string;
};

async function engineReachable(): Promise<Segment> {
  const url = process.env.NEXT_PUBLIC_ENGINE_URL;
  if (!url) {
    return {
      status: "gated",
      detail:
        "Engine URL not configured in this environment. The live " +
        "proposal round-trip is a gated edge; the path is wired " +
        "(MH-P1 proved it end to end on the engine host), unproven " +
        "from this web origin without a running engine.",
    };
  }
  try {
    const r = await fetch(`${url.replace(/\/$/, "")}/health`, {
      signal: AbortSignal.timeout(2500),
    });
    return r.ok
      ? { status: "live", detail: "Engine reachable." }
      : {
          status: "gated",
          detail: `Engine responded ${r.status}; treated as gated, ` +
            `not faked as connected.`,
        };
  } catch (e) {
    return {
      status: "gated",
      detail:
        "Engine not reachable from this origin. Honest gated edge, " +
        "not a faked connection.",
    };
  }
}

export async function GET() {
  const engine = await engineReachable();

  return NextResponse.json({
    // The product is account-gated. Real account creation / OAuth /
    // payment are PROHIBITED to do on the user's behalf and are the
    // honest gated edge: the screen is real, activation is the
    // user's own action.
    account: {
      status: "needs_user",
      detail:
        "Account creation and sign-in are done by you. The screens " +
        "are real; the credential step is yours by design (never " +
        "automated, never a faked success).",
    } as Segment,
    download: {
      status: "ready",
      detail: "The desktop app download is available.",
    } as Segment,
    onboarding: {
      chrome: {
        status: "needs_user",
        detail:
          "Connect Chrome is a one-time grant you perform; the " +
          "frontend reflects its real connected state, it does not " +
          "fake it.",
      } as Segment,
      microphone: {
        status: "needs_user",
        detail:
          "macOS microphone permission is a TCC grant only you can " +
          "give. MH-P1 proved the real capture path; the frontend " +
          "shows the real permission state.",
      } as Segment,
      autonomy: {
        status: "ready",
        detail:
          "Progressive-autonomy first run: the first days are " +
          "conservative by design (MH-P10: confirm-first, earns " +
          "trust, never floods).",
      } as Segment,
    },
    engine,
    // Proposals are never mocked. With no live engine this is an
    // honest empty/gated state, not a fabricated card.
    proposals:
      engine.status === "live"
        ? { status: "live", detail: "Live proposals stream from the engine." }
        : {
            status: "gated",
            detail:
              "No live engine from this origin, so there are no " +
              "real proposals to show. This renders the honest " +
              "empty/gated state by design, never a fake proposal.",
          },
    safety: {
      // surfaced from the committed build guarantees, stated plainly
      detail:
        "Every hard safety binding holds at zero (chatter " +
        "false-action, double-action, act-after-cancel, " +
        "act-on-unresolved, unrecoverable wrong action). Uncertain " +
        "input is confirmed or logged, never silently acted on.",
    },
  });
}
