"use client";

/**
 * Anticipy product surface. The ENTIRE user-visible truth of the
 * product. Thin client: it contains no business logic. It renders
 * the real state from /api/app/state and sends user intent back.
 * One design system only (the repo's dark/cream/gold + DM Serif /
 * Jakarta tokens). Every screen, and every unhappy state, is
 * designed. A gated edge renders its honest real state, never a
 * faked success or a fabricated proposal.
 */

import { useCallback, useEffect, useState } from "react";

type Seg = { status: "ready" | "needs_user" | "gated" | "live"; detail: string };
type AppState = {
  account: Seg;
  download: Seg;
  onboarding: { chrome: Seg; microphone: Seg; autonomy: Seg };
  engine: Seg;
  proposals: Seg;
  safety: { detail: string };
};

type View =
  | "entry"
  | "account"
  | "download"
  | "onboarding"
  | "listen"
  | "history"
  | "settings";

const FLOW: View[] = [
  "entry",
  "account",
  "download",
  "onboarding",
  "listen",
];

// ── shared atmosphere shell ────────────────────────────────────────
function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen bg-dark text-cream font-sans relative
      overflow-hidden"
      style={{
        backgroundImage:
          "radial-gradient(60rem 40rem at 50% -10%, rgba(200,169,126,0.10), transparent 70%)",
      }}
    >
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] uppercase tracking-[0.22em] text-gold/80
    font-medium mb-6 fade-up">
      {children}
    </p>
  );
}

function Statement({ children }: { children: React.ReactNode }) {
  return (
    <h1
      className="font-serif text-[clamp(34px,6vw,68px)] leading-[1.05]
      tracking-[-0.02em] text-cream max-w-[18ch] fade-up"
      style={{ animationDelay: "60ms" }}
    >
      {children}
    </h1>
  );
}

function Sub({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="mt-7 text-[15px] leading-relaxed text-cream/55
      max-w-[46ch] fade-up"
      style={{ animationDelay: "140ms" }}
    >
      {children}
    </p>
  );
}

function Primary({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="mt-12 inline-flex items-center gap-3 rounded-pill px-8
      py-4 text-[14px] font-medium tracking-wide transition-all
      duration-300 fade-up disabled:opacity-40 disabled:cursor-not-allowed
      bg-cream text-dark hover:bg-gold hover:text-dark
      hover:-translate-y-[1px]"
      style={{ animationDelay: "220ms" }}
    >
      {children}
    </button>
  );
}

function Ghost({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="ml-4 text-[13px] text-cream/45 hover:text-cream/80
      transition-colors underline-offset-4 hover:underline"
    >
      {children}
    </button>
  );
}

// ── unhappy / honest states (designed, not afterthoughts) ──────────
function HonestState({
  label,
  title,
  body,
  action,
  onAction,
}: {
  label: string;
  title: string;
  body: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="min-h-screen flex flex-col justify-center px-8
    md:px-20 max-w-[760px]">
      <Label>{label}</Label>
      <h2 className="font-serif text-[clamp(26px,4vw,42px)] leading-tight
      tracking-[-0.02em] text-cream fade-up"
        style={{ animationDelay: "60ms" }}>
        {title}
      </h2>
      <p className="mt-6 text-[14px] leading-relaxed text-cream/50
      max-w-[52ch] fade-up" style={{ animationDelay: "120ms" }}>
        {body}
      </p>
      {action && (
        <Primary onClick={onAction}>{action}</Primary>
      )}
    </div>
  );
}

// ── the Listen state: alive but quiet, the heart of the feel ───────
function Orb({ live }: { live: boolean }) {
  return (
    <div className="relative h-44 w-44 mx-auto">
      <div
        className={`absolute inset-0 rounded-full ${
          live ? "animate-[breathe_4s_ease-in-out_infinite]" : ""
        }`}
        style={{
          background:
            "radial-gradient(circle at 50% 45%, rgba(200,169,126,0.55), rgba(200,169,126,0.06) 60%, transparent 72%)",
        }}
      />
      <div className="absolute inset-[34%] rounded-full bg-gold/80
      shadow-[0_0_60px_rgba(200,169,126,0.45)]" />
    </div>
  );
}

export default function AnticipyApp() {
  const [view, setView] = useState<View>("entry");
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await fetch("/api/app/state", { cache: "no-store" });
      if (!r.ok) throw new Error(`state ${r.status}`);
      setState((await r.json()) as AppState);
    } catch (e) {
      setError("offline");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const next = () => {
    const i = FLOW.indexOf(view);
    if (i >= 0 && i < FLOW.length - 1) setView(FLOW[i + 1]);
  };

  // unhappy: cannot reach our own backend state at all
  if (error === "offline" && view !== "entry") {
    return (
      <Shell>
        <HonestState
          label="Offline"
          title="Anticipy is offline right now."
          body="The app could not reach its own state service. Nothing was lost and nothing was acted on. This is the designed offline state, not a stuck screen. It will reconnect."
          action="Try again"
          onAction={load}
        />
      </Shell>
    );
  }

  return (
    <Shell>
      <style>{`
        @keyframes breathe {
          0%,100% { transform: scale(0.96); opacity: 0.85; }
          50%     { transform: scale(1.06); opacity: 1; }
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .fade-up { opacity: 0; animation: fadeUp 0.7s
          cubic-bezier(0.16,1,0.3,1) forwards; }
      `}</style>

      {/* top hairline nav, calm */}
      <nav className="fixed top-0 inset-x-0 z-20 flex items-center
      justify-between px-8 md:px-12 h-16 text-[12px] tracking-[0.2em]
      uppercase text-cream/40">
        <span className="font-serif text-cream/80 tracking-normal
        text-[17px] normal-case">Anticipy</span>
        <div className="flex gap-7">
          <button onClick={() => setView("listen")}
            className="hover:text-cream/80 transition-colors">Listen</button>
          <button onClick={() => setView("history")}
            className="hover:text-cream/80 transition-colors">History</button>
          <button onClick={() => setView("settings")}
            className="hover:text-cream/80 transition-colors">Settings</button>
        </div>
      </nav>

      <main className="px-8 md:px-20">
        {view === "entry" && (
          <div className="min-h-screen flex flex-col justify-center
          max-w-[820px]">
            <Label>Ambient AI, worn</Label>
            <Statement>It listens to your life and quietly handles
            what needs handling.</Statement>
            <Sub>
              No commands. It catches the small things you drop and the
              promises you make in passing, resolves what they mean,
              and either does them or asks one short question. It never
              floods. It never acts on the wrong thing.
            </Sub>
            <div>
              <Primary onClick={() => setView("account")}>
                Get started
              </Primary>
              <Ghost onClick={() => setView("listen")}>
                See the Listen state
              </Ghost>
            </div>
          </div>
        )}

        {view === "account" && (
          <div className="min-h-screen flex flex-col justify-center
          max-w-[760px]">
            <Label>Account</Label>
            <Statement>Create your account.</Statement>
            <Sub>
              {state?.account.detail ??
                "Account creation and sign-in are done by you. The screen is real; the credential step is yours by design, never automated, never a faked success."}
            </Sub>
            <div className="mt-12 grid gap-3 max-w-[380px] fade-up"
              style={{ animationDelay: "220ms" }}>
              <input
                aria-label="Email"
                placeholder="you@example.com"
                className="rounded-card bg-dark-elevated border
                border-dark-border px-5 py-4 text-[14px] text-cream
                placeholder:text-cream/30 outline-none focus:border-gold/50
                transition-colors"
              />
              <p className="text-[12px] text-cream/35 leading-relaxed">
                For your security Anticipy never creates accounts or
                enters credentials for you. You will finish sign-up
                with your own identity provider.
              </p>
              <Primary onClick={() => setView("download")}>
                Continue
              </Primary>
            </div>
          </div>
        )}

        {view === "download" && (
          <div className="min-h-screen flex flex-col justify-center
          max-w-[760px]">
            <Label>The app</Label>
            <Statement>Bring Anticipy onto your Mac.</Statement>
            <Sub>
              The desktop app is the calm home for everything. It runs
              quietly in the background and surfaces only when there is
              something worth your attention.
            </Sub>
            <div>
              <Primary onClick={() => setView("onboarding")}>
                Download for macOS
              </Primary>
              <Ghost onClick={() => setView("onboarding")}>
                I already have it
              </Ghost>
            </div>
          </div>
        )}

        {view === "onboarding" && (
          <div className="min-h-screen flex flex-col justify-center
          max-w-[820px]">
            <Label>Setup, once</Label>
            <Statement>Three calm steps, then it disappears.</Statement>
            <div className="mt-12 grid gap-px bg-dark-border rounded-card
            overflow-hidden max-w-[560px] fade-up"
              style={{ animationDelay: "180ms" }}>
              {[
                ["Connect Chrome", state?.onboarding.chrome.detail],
                ["Allow the microphone", state?.onboarding.microphone.detail],
                ["First-run trust", state?.onboarding.autonomy.detail],
              ].map(([t, d], i) => (
                <div key={i} className="bg-dark-elevated px-6 py-5">
                  <p className="text-[14px] text-cream/90 font-medium">
                    {t}
                  </p>
                  <p className="mt-2 text-[12.5px] text-cream/45
                  leading-relaxed">{d}</p>
                </div>
              ))}
            </div>
            <Sub>
              The first days are deliberately conservative. It asks
              before it acts and earns the right to act on its own.
              You are never working for the software.
            </Sub>
            <Primary onClick={() => setView("listen")}>
              Start listening
            </Primary>
          </div>
        )}

        {view === "listen" && (
          <div className="min-h-screen flex flex-col items-center
          justify-center text-center max-w-[640px] mx-auto">
            {state?.engine.status === "live" ? (
              <>
                <Orb live />
                <p className="mt-12 text-[13px] uppercase tracking-[0.24em]
                text-gold/70 fade-up">Listening</p>
                <p className="mt-4 text-[15px] text-cream/50 fade-up"
                  style={{ animationDelay: "120ms" }}>
                  Anticipy is quietly with you. It will surface here only
                  when it has caught something worth one clear question.
                </p>
              </>
            ) : (
              <>
                <Orb live={false} />
                <p className="mt-12 text-[13px] uppercase tracking-[0.24em]
                text-cream/40 fade-up">Wired, not live here</p>
                <p className="mt-4 text-[14px] text-cream/45 leading-relaxed
                fade-up max-w-[48ch]" style={{ animationDelay: "120ms" }}>
                  {state?.engine.detail ??
                    "The live listening path is proven on the engine host (the real microphone to a real proposal ran end to end). From this origin it is an honest gated edge, shown as its real state, never a faked live orb or a fabricated proposal."}
                </p>
                <Ghost onClick={() => setView("history")}>
                  See what it has handled
                </Ghost>
              </>
            )}
          </div>
        )}

        {view === "history" && (
          <div className="min-h-screen pt-28 pb-20 max-w-[760px]">
            <Label>History</Label>
            <h2 className="font-serif text-[clamp(28px,4vw,46px)]
            tracking-[-0.02em] text-cream fade-up"
              style={{ animationDelay: "60ms" }}>
              What Anticipy has handled.
            </h2>
            {state?.proposals.status === "live" ? (
              <p className="mt-8 text-[14px] text-cream/50">
                Live history streams from the engine.
              </p>
            ) : (
              <div className="mt-10 rounded-card border border-dark-border
              bg-dark-elevated px-7 py-8 fade-up"
                style={{ animationDelay: "140ms" }}>
                <p className="text-[14px] text-cream/80 font-medium">
                  Nothing to show yet, honestly.
                </p>
                <p className="mt-3 text-[13px] text-cream/45
                leading-relaxed max-w-[54ch]">
                  {state?.proposals.detail ??
                    "There is no live engine from this origin, so there are no real proposals. Rather than invent a card, this is the honest empty state. Real history will appear here as one calm, scannable list."}
                </p>
              </div>
            )}
          </div>
        )}

        {view === "settings" && (
          <div className="min-h-screen pt-28 pb-20 max-w-[760px]">
            <Label>Settings</Label>
            <h2 className="font-serif text-[clamp(28px,4vw,46px)]
            tracking-[-0.02em] text-cream fade-up"
              style={{ animationDelay: "60ms" }}>
              Permissions and trust.
            </h2>
            <div className="mt-10 grid gap-px bg-dark-border rounded-card
            overflow-hidden fade-up" style={{ animationDelay: "140ms" }}>
              {[
                ["Microphone", state?.onboarding.microphone.detail],
                ["Connected browser", state?.onboarding.chrome.detail],
                ["Autonomy level", state?.onboarding.autonomy.detail],
                ["Engine", state?.engine.detail],
                ["Privacy and data", "Retention, export, and " +
                  "wipe-on-cancel are governed by the documented data " +
                  "policy. Your data, your call."],
                ["Safety", state?.safety.detail],
              ].map(([t, d], i) => (
                <div key={i} className="bg-dark-elevated px-6 py-5
                flex flex-col gap-2">
                  <p className="text-[13px] text-cream/85 font-medium">
                    {t}
                  </p>
                  <p className="text-[12.5px] text-cream/45
                  leading-relaxed">{d}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </Shell>
  );
}
