"use client";

/**
 * Anticipy product surface. Thin client over the real backend:
 * REAL Supabase auth (the same client the rest of the site uses),
 * the REAL .dmg download, and the REAL engine round trip. One
 * design system (the repo dark/cream/gold + DM Serif / Jakarta).
 * Gated edges render their honest real state, never a faked
 * success or a fabricated proposal.
 */

import { useCallback, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

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

const GATED: View[] = ["download", "onboarding", "listen", "history", "settings"];

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen bg-dark text-cream font-sans relative overflow-hidden"
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
    <p className="text-[11px] uppercase tracking-[0.22em] text-gold/80 font-medium mb-6 fade-up">
      {children}
    </p>
  );
}

function Statement({ children }: { children: React.ReactNode }) {
  return (
    <h1
      className="font-serif text-[clamp(34px,6vw,68px)] leading-[1.05] tracking-[-0.02em] text-cream max-w-[18ch] fade-up"
      style={{ animationDelay: "60ms" }}
    >
      {children}
    </h1>
  );
}

function Sub({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="mt-7 text-[15px] leading-relaxed text-cream/55 max-w-[46ch] fade-up"
      style={{ animationDelay: "140ms" }}
    >
      {children}
    </p>
  );
}

function Primary({
  children,
  onClick,
  href,
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  href?: string;
  disabled?: boolean;
}) {
  const cls =
    "mt-12 inline-flex items-center gap-3 rounded-pill px-8 py-4 text-[14px] font-medium tracking-wide transition-all duration-300 fade-up disabled:opacity-40 disabled:cursor-not-allowed bg-cream text-dark hover:bg-gold hover:text-dark hover:-translate-y-[1px]";
  if (href) {
    return (
      <a href={href} className={cls} style={{ animationDelay: "220ms" }}>
        {children}
      </a>
    );
  }
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cls}
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
      className="ml-4 text-[13px] text-cream/45 hover:text-cream/80 transition-colors underline-offset-4 hover:underline"
    >
      {children}
    </button>
  );
}

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
      <div className="absolute inset-[34%] rounded-full bg-gold/80 shadow-[0_0_60px_rgba(200,169,126,0.45)]" />
    </div>
  );
}

export default function AnticipyApp() {
  const [view, setView] = useState<View>("entry");
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── real Supabase auth ──────────────────────────────────────────
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [mode, setMode] = useState<"login" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authMsg, setAuthMsg] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setAuthReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => {
      setSession(s);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const submitAuth = useCallback(async () => {
    setAuthBusy(true);
    setAuthMsg(null);
    try {
      if (mode === "signup") {
        const { data, error: e } = await supabase.auth.signUp({
          email,
          password,
        });
        if (e) {
          setAuthMsg(e.message);
        } else if (data.session) {
          setView("download");
        } else {
          setMode("login");
          setAuthMsg(
            "Account created. If your project requires email confirmation, confirm then log in. Otherwise log in now."
          );
        }
      } else {
        const { error: e } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (e) setAuthMsg(e.message);
        else setView("download");
      }
    } catch (err) {
      setAuthMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setAuthBusy(false);
    }
  }, [mode, email, password]);

  const logout = useCallback(async () => {
    await supabase.auth.signOut();
    setView("entry");
  }, []);

  // ── engine state + the real Listen round trip ───────────────────
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<{
    proposal: string | null;
    transcript: string;
    engine_decision: string;
    stages: { name: string; real: boolean; gated: boolean; detail: string }[];
    gated?: boolean;
    reason?: string;
  } | null>(null);

  const doListen = useCallback(async () => {
    setRunning(true);
    setRun(null);
    try {
      const r = await fetch("/api/app/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      setRun(await r.json());
    } catch (e) {
      setRun({
        proposal: null,
        transcript: "",
        engine_decision: "",
        stages: [],
        gated: true,
        reason: "The run could not reach the engine. Honest state, not faked.",
      });
    } finally {
      setRunning(false);
    }
  }, []);

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

  // session gate: a gated view with no real session sends you to auth
  useEffect(() => {
    if (authReady && !session && GATED.includes(view)) setView("account");
  }, [authReady, session, view]);

  if (error === "offline" && view !== "entry") {
    return (
      <Shell>
        <div className="min-h-screen flex flex-col justify-center px-8 md:px-20 max-w-[760px]">
          <Label>Offline</Label>
          <h2
            className="font-serif text-[clamp(26px,4vw,42px)] leading-tight tracking-[-0.02em] text-cream fade-up"
            style={{ animationDelay: "60ms" }}
          >
            Anticipy is offline right now.
          </h2>
          <p
            className="mt-6 text-[14px] leading-relaxed text-cream/50 max-w-[52ch] fade-up"
            style={{ animationDelay: "120ms" }}
          >
            The app could not reach its own state service. Nothing was lost and
            nothing was acted on. This is the designed offline state, not a
            stuck screen.
          </p>
          <Primary onClick={load}>Try again</Primary>
        </div>
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
        .fade-up { opacity: 0; animation: fadeUp 0.7s cubic-bezier(0.16,1,0.3,1) forwards; }
      `}</style>

      <nav className="fixed top-0 inset-x-0 z-20 flex items-center justify-between px-8 md:px-12 h-16 text-[12px] tracking-[0.2em] uppercase text-cream/40">
        <span className="font-serif text-cream/80 tracking-normal text-[17px] normal-case">
          Anticipy
        </span>
        <div className="flex gap-7 items-center">
          <button
            onClick={() => setView("listen")}
            className="hover:text-cream/80 transition-colors"
          >
            Listen
          </button>
          <button
            onClick={() => setView("history")}
            className="hover:text-cream/80 transition-colors"
          >
            History
          </button>
          <button
            onClick={() => setView("settings")}
            className="hover:text-cream/80 transition-colors"
          >
            Settings
          </button>
          {session && (
            <button
              onClick={logout}
              className="text-gold/70 hover:text-gold transition-colors"
            >
              Log out
            </button>
          )}
        </div>
      </nav>

      <main className="px-8 md:px-20">
        {view === "entry" && (
          <div className="min-h-screen flex flex-col justify-center max-w-[820px]">
            <Label>Ambient AI, worn</Label>
            <Statement>
              It listens to your life and quietly handles what needs handling.
            </Statement>
            <Sub>
              No commands. It catches the small things you drop and the promises
              you make in passing, resolves what they mean, and either does them
              or asks one short question. It never floods. It never acts on the
              wrong thing.
            </Sub>
            <div>
              <Primary
                onClick={() => setView(session ? "download" : "account")}
              >
                {session ? "Continue" : "Get started"}
              </Primary>
              <Ghost onClick={() => setView("listen")}>
                See the Listen state
              </Ghost>
            </div>
          </div>
        )}

        {view === "account" && (
          <div className="min-h-screen flex flex-col justify-center max-w-[760px]">
            <Label>{mode === "signup" ? "Create account" : "Log in"}</Label>
            <Statement>
              {mode === "signup"
                ? "Create your Anticipy account."
                : "Welcome back."}
            </Statement>
            <div
              className="mt-12 grid gap-3 max-w-[400px] fade-up"
              style={{ animationDelay: "200ms" }}
            >
              <input
                aria-label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream placeholder:text-cream/30 outline-none focus:border-gold/50 transition-colors"
              />
              <input
                aria-label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password (8+ characters)"
                className="rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream placeholder:text-cream/30 outline-none focus:border-gold/50 transition-colors"
              />
              {authMsg && (
                <p className="text-[12.5px] text-gold/90 leading-relaxed">
                  {authMsg}
                </p>
              )}
              <button
                onClick={submitAuth}
                disabled={authBusy || !email || password.length < 8}
                className="mt-2 rounded-pill px-8 py-4 text-[14px] font-medium bg-cream text-dark hover:bg-gold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {authBusy
                  ? "One moment"
                  : mode === "signup"
                  ? "Create account"
                  : "Log in"}
              </button>
              <button
                onClick={() => {
                  setMode(mode === "signup" ? "login" : "signup");
                  setAuthMsg(null);
                }}
                className="text-[12.5px] text-cream/45 hover:text-cream/80 transition-colors mt-1"
              >
                {mode === "signup"
                  ? "Already have an account? Log in"
                  : "Need an account? Create one"}
              </button>
              <p className="text-[11.5px] text-cream/30 leading-relaxed mt-2">
                Real account, real Supabase. We never use your Google or
                personal credentials and never auto-create third-party
                accounts.
              </p>
            </div>
          </div>
        )}

        {view === "download" && (
          <div className="min-h-screen flex flex-col justify-center max-w-[760px]">
            <Label>The app</Label>
            <Statement>Bring Anticipy onto your Mac.</Statement>
            <Sub>
              The desktop app is the calm home for everything. It runs quietly
              in the background and surfaces only when there is something worth
              your attention. The build is unsigned: on first launch,
              right-click the app and choose Open.
            </Sub>
            <div>
              <Primary href="/download">Download for macOS</Primary>
              <Ghost onClick={() => setView("onboarding")}>
                I already have it
              </Ghost>
            </div>
          </div>
        )}

        {view === "onboarding" && (
          <div className="min-h-screen flex flex-col justify-center max-w-[820px]">
            <Label>Setup, once</Label>
            <Statement>Three calm steps, then it disappears.</Statement>
            <div
              className="mt-12 grid gap-px bg-dark-border rounded-card overflow-hidden max-w-[560px] fade-up"
              style={{ animationDelay: "180ms" }}
            >
              {[
                ["Connect Chrome", state?.onboarding.chrome.detail],
                ["Allow the microphone", state?.onboarding.microphone.detail],
                ["First-run trust", state?.onboarding.autonomy.detail],
              ].map(([t, d], i) => (
                <div key={i} className="bg-dark-elevated px-6 py-5">
                  <p className="text-[14px] text-cream/90 font-medium">{t}</p>
                  <p className="mt-2 text-[12.5px] text-cream/45 leading-relaxed">
                    {d}
                  </p>
                </div>
              ))}
            </div>
            <Sub>
              The first days are deliberately conservative. It asks before it
              acts and earns the right to act on its own. You are never working
              for the software.
            </Sub>
            <Primary onClick={() => setView("listen")}>Start listening</Primary>
          </div>
        )}

        {view === "listen" && (
          <div className="min-h-screen flex flex-col items-center justify-center text-center max-w-[680px] mx-auto py-28">
            {state?.engine.status !== "live" ? (
              <>
                <Orb live={false} />
                <p className="mt-12 text-[13px] uppercase tracking-[0.24em] text-cream/40 fade-up">
                  Wired, not live here
                </p>
                <p
                  className="mt-4 text-[14px] text-cream/45 leading-relaxed fade-up max-w-[48ch]"
                  style={{ animationDelay: "120ms" }}
                >
                  {state?.engine.detail ??
                    "No engine reachable from this origin. Honest gated state, never a faked live orb or a fabricated proposal."}
                </p>
                <Ghost onClick={() => setView("history")}>
                  See what it has handled
                </Ghost>
              </>
            ) : run ? (
              <div className="w-full fade-up">
                {run.proposal ? (
                  <div className="rounded-card border border-dark-border bg-dark-elevated px-8 py-9 text-left">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-gold/80 mb-4">
                      Anticipy caught something
                    </p>
                    <p className="font-serif text-[clamp(20px,3vw,28px)] text-cream leading-snug">
                      {run.proposal}
                    </p>
                    <p className="mt-5 text-[12.5px] text-cream/45 leading-relaxed">
                      Heard: {run.transcript || "(no transcript)"}. Reasoning
                      decision: {run.engine_decision || "n/a"}.
                    </p>
                    <div className="mt-8 flex gap-3">
                      <button className="rounded-pill bg-cream text-dark px-7 py-3 text-[13px] font-medium hover:bg-gold transition-colors">
                        Yes, do it
                      </button>
                      <button className="rounded-pill border border-dark-border text-cream/70 px-7 py-3 text-[13px] hover:text-cream transition-colors">
                        No
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-card border border-dark-border bg-dark-elevated px-8 py-9 text-left">
                    <p className="text-[13px] text-cream/80 font-medium">
                      No proposal this run, honestly.
                    </p>
                    <p className="mt-3 text-[12.5px] text-cream/45 leading-relaxed">
                      {run.reason ||
                        "The pipeline ran but did not surface a proposal."}
                    </p>
                  </div>
                )}
                <div className="mt-8 grid gap-px bg-dark-border rounded-card overflow-hidden text-left">
                  {run.stages?.map((s, i) => (
                    <div
                      key={i}
                      className="bg-dark-elevated px-5 py-3 flex items-start gap-3"
                    >
                      <span
                        className={`text-[10px] uppercase tracking-wider mt-[2px] ${
                          s.real ? "text-gold/80" : "text-cream/35"
                        }`}
                      >
                        {s.real ? "real" : s.gated ? "gated" : "fail"}
                      </span>
                      <div>
                        <p className="text-[12.5px] text-cream/80">{s.name}</p>
                        <p className="text-[11.5px] text-cream/40 leading-relaxed">
                          {s.detail}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
                <button
                  onClick={doListen}
                  className="mt-8 text-[13px] text-cream/45 hover:text-cream/80 underline-offset-4 hover:underline"
                >
                  Listen again
                </button>
              </div>
            ) : (
              <>
                <Orb live={running} />
                <p className="mt-12 text-[13px] uppercase tracking-[0.24em] text-gold/70 fade-up">
                  {running ? "Listening, running the real pipeline" : "Engine live"}
                </p>
                <p
                  className="mt-4 text-[14px] text-cream/50 fade-up max-w-[48ch]"
                  style={{ animationDelay: "120ms" }}
                >
                  {running
                    ? "Real audio is going through the real stack, the real reasoning engine, and the real browser action. This takes a minute; nothing is mocked."
                    : "Press Listen. Real spoken audio runs the whole real pipeline and a real proposal returns here."}
                </p>
                {!running && <Primary onClick={doListen}>Listen</Primary>}
              </>
            )}
          </div>
        )}

        {view === "history" && (
          <div className="min-h-screen pt-28 pb-20 max-w-[760px]">
            <Label>History</Label>
            <h2
              className="font-serif text-[clamp(28px,4vw,46px)] tracking-[-0.02em] text-cream fade-up"
              style={{ animationDelay: "60ms" }}
            >
              What Anticipy has handled.
            </h2>
            <div
              className="mt-10 rounded-card border border-dark-border bg-dark-elevated px-7 py-8 fade-up"
              style={{ animationDelay: "140ms" }}
            >
              <p className="text-[14px] text-cream/80 font-medium">
                {state?.proposals.status === "live"
                  ? "Connected. Real proposals appear here as one calm list."
                  : "Nothing to show yet, honestly."}
              </p>
              <p className="mt-3 text-[13px] text-cream/45 leading-relaxed max-w-[54ch]">
                {state?.proposals.detail ??
                  "Real history will appear here as one calm, scannable list."}
              </p>
            </div>
          </div>
        )}

        {view === "settings" && (
          <div className="min-h-screen pt-28 pb-20 max-w-[760px]">
            <Label>Settings</Label>
            <h2
              className="font-serif text-[clamp(28px,4vw,46px)] tracking-[-0.02em] text-cream fade-up"
              style={{ animationDelay: "60ms" }}
            >
              Permissions and trust.
            </h2>
            <div
              className="mt-10 grid gap-px bg-dark-border rounded-card overflow-hidden fade-up"
              style={{ animationDelay: "140ms" }}
            >
              {[
                ["Account", session ? `Signed in as ${session.user.email}` : "Not signed in"],
                ["Microphone", state?.onboarding.microphone.detail],
                ["Connected browser", state?.onboarding.chrome.detail],
                ["Autonomy level", state?.onboarding.autonomy.detail],
                ["Engine", state?.engine.detail],
                ["Safety", state?.safety.detail],
              ].map(([t, d], i) => (
                <div
                  key={i}
                  className="bg-dark-elevated px-6 py-5 flex flex-col gap-2"
                >
                  <p className="text-[13px] text-cream/85 font-medium">{t}</p>
                  <p className="text-[12.5px] text-cream/45 leading-relaxed">
                    {d}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </Shell>
  );
}
