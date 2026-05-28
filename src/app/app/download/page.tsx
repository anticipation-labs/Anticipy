"use client";

import { useEffect, useState } from "react";

/**
 * /app/download
 *
 * Landing target after signup. US-007 wires the redirect with a one-time
 * handoff token in the query string. US-009 turns this into the real
 * download surface: a single Download for Mac button on Apple Silicon,
 * three numbered install steps, and a small Already-installed deep link
 * that opens anticipy://session?token=<handoff_token> for the Mac app.
 *
 * Intel Macs see an Apple Silicon only message instead of the button.
 * arm64 detection is best-effort: high-entropy userAgentData when the
 * browser supports it, falling back to a Mac userAgent heuristic.
 */
type Arch = "unknown" | "arm64" | "intel";

type UADataNavigator = Navigator & {
  userAgentData?: {
    platform?: string;
    getHighEntropyValues?: (hints: string[]) => Promise<{
      architecture?: string;
      platform?: string;
    }>;
  };
};

async function detectArch(): Promise<Arch> {
  if (typeof navigator === "undefined") return "unknown";
  const ua = navigator.userAgent || "";
  const isMac = /Macintosh|Mac OS X/i.test(ua);
  if (!isMac) return "unknown";

  const nav = navigator as UADataNavigator;
  if (nav.userAgentData?.getHighEntropyValues) {
    try {
      const hints = await nav.userAgentData.getHighEntropyValues([
        "architecture",
      ]);
      if (hints.architecture) {
        if (hints.architecture === "arm") return "arm64";
        if (hints.architecture === "x86") return "intel";
      }
    } catch {
      // fall through to UA heuristic
    }
  }

  if (/Intel/i.test(ua)) {
    return "intel";
  }
  return "arm64";
}

export default function AppDownloadPage() {
  const [token, setToken] = useState<string>("");
  const [arch, setArch] = useState<Arch>("unknown");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("token") ?? "");
  }, []);

  useEffect(() => {
    let cancelled = false;
    void detectArch().then((a) => {
      if (!cancelled) setArch(a);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const deepLink = token ? `anticipy://session?token=${token}` : "";
  const isIntel = arch === "intel";

  return (
    <div className="min-h-screen bg-dark text-cream px-8 md:px-20 py-24 font-sans">
      <p className="text-[11px] uppercase tracking-[0.22em] text-gold/80 font-medium mb-6">
        The app
      </p>
      <h1 className="font-serif text-[clamp(28px,5vw,52px)] leading-[1.1] tracking-[-0.02em] max-w-[18ch]">
        Bring Anticipy onto your Mac.
      </h1>
      <p className="mt-7 text-[15px] leading-relaxed text-cream/55 max-w-[46ch]">
        Download the installer, drag Anticipy to Applications, double click.
        That is the full setup.
      </p>
      <p className="mt-4 text-[13px] leading-relaxed text-cream/45 max-w-[56ch]">
        If macOS says Anticipy is from an unverified developer or that it is
        damaged, Gatekeeper is blocking the un-notarized build. Open System
        Settings, Privacy and Security, then click Open Anyway for Anticipy.
      </p>

      {isIntel ? (
        <div
          className="mt-12 max-w-[560px] rounded-card border border-dark-border bg-dark-elevated px-6 py-5"
          data-testid="intel-unsupported"
        >
          <p className="text-[12px] uppercase tracking-[0.18em] text-gold/80 mb-3">
            Apple Silicon only
          </p>
          <p className="text-[14px] text-cream/75 leading-relaxed">
            Anticipy ships an Apple Silicon (arm64) build today. Intel Macs are
            not supported. If you have an M1 or later, open this page on that
            machine to download.
          </p>
        </div>
      ) : (
        <a
          href="/dl/Anticipy_1.0.0_aarch64.dmg"
          download="Anticipy_1.0.0_aarch64.dmg"
          data-testid="download-button"
          className="mt-12 inline-flex items-center gap-3 rounded-pill px-8 py-4 text-[14px] font-medium bg-cream text-dark hover:bg-gold transition-colors"
        >
          Download Anticipy for Mac
        </a>
      )}

      {!isIntel && (
        <ol
          className="mt-10 max-w-[560px] grid gap-4 text-[14px] text-cream/75 leading-relaxed"
          data-testid="install-steps"
        >
          <li className="flex gap-4">
            <span className="text-gold/80 font-mono text-[12px] mt-[3px]">
              01
            </span>
            <span>
              Drag <span className="text-cream">Anticipy</span> from the .dmg
              window to <span className="text-cream">Applications</span>.
            </span>
          </li>
          <li className="flex gap-4">
            <span className="text-gold/80 font-mono text-[12px] mt-[3px]">
              02
            </span>
            <span>
              Open <span className="text-cream">Applications</span> and double
              click <span className="text-cream">Anticipy</span>.
            </span>
          </li>
          <li className="flex gap-4">
            <span className="text-gold/80 font-mono text-[12px] mt-[3px]">
              03
            </span>
            <span>
              The first launch shows a macOS warning. Click{" "}
              <span className="text-cream">Open</span>. macOS remembers, and
              you will not see it again.
            </span>
          </li>
        </ol>
      )}

      {token && (
        <div className="mt-12 max-w-[560px]">
          <p className="text-[12px] uppercase tracking-[0.18em] text-cream/45 mb-3">
            Already installed
          </p>
          <a
            href={deepLink}
            data-testid="deep-link"
            className="text-[13px] text-gold/90 underline-offset-4 hover:underline break-all"
          >
            Open Anticipy
          </a>
          <p
            className="mt-3 text-[12px] text-cream/35 break-all"
            data-testid="handoff-token"
          >
            {token}
          </p>
        </div>
      )}
    </div>
  );
}
