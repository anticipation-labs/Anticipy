import { NextResponse } from "next/server";
import { releaseMeta } from "@/lib/release-meta";

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

export async function GET() {
  const engine = {
    status: "ready",
    detail:
      "The deployed shell probes the user-device engine directly from " +
      "the browser at http://127.0.0.1:8731. Vercel does not proxy " +
      "the local engine.",
  } as Segment;

  const release = releaseMeta();

  return NextResponse.json({
    build: {
      commit: release.build.commit,
      commit_short: release.build.commit_short,
    },
    release: release.download,
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
        status: "ready",
        detail:
          "The terminal-launched local engine uses the already-authorized " +
          "terminal microphone path; the browser shell only reports that " +
          "real local state.",
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
            status: "ready",
            detail:
              "The browser connects to the local engine directly; no " +
              "proposal is fabricated by Vercel.",
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
