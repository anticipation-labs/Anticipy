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
const LOCAL_ENGINE = "http://127.0.0.1:8731";

type LocalEngine = {
  live: boolean;
  detail: string;
  health?: Record<string, unknown>;
	  state?: {
	    key_ok?: boolean;
	    provisioned?: boolean;
	    onboarded?: boolean;
	    profile?: Record<string, unknown> | null;
	    total_questions?: number;
  };
};

type OnboardingTurn = { question: string; answer?: string };

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
  const [localEngine, setLocalEngine] = useState<LocalEngine>({
    live: false,
    detail:
      "Local engine not connected yet. Install and start Anticipy, then this page connects to 127.0.0.1:8731 from your browser.",
  });
	  const [setupBusy, setSetupBusy] = useState(false);
	  const [setupMsg, setSetupMsg] = useState<string | null>(null);
  const [onboardingTurns, setOnboardingTurns] = useState<OnboardingTurn[]>([]);
  const [onboardingAnswer, setOnboardingAnswer] = useState("");
  const [onboardingIndex, setOnboardingIndex] = useState(0);
  const [onboardingTotal, setOnboardingTotal] = useState(0);

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
  const [transcriptInput, setTranscriptInput] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [run, setRun] = useState<{
    proposal: string | null;
    transcript: string;
    engine_decision: string;
    stages: { name: string; real: boolean; gated: boolean; detail: string }[];
    gated?: boolean;
    reason?: string;
    pending?: Record<string, unknown> | null;
    action?: {
      status?: string;
      error?: string;
      question?: string;
      ran?: boolean;
      gated?: boolean;
      clarify?: boolean;
      evidence?: string;
    } | null;
  } | null>(null);

  const probeLocalEngine = useCallback(async () => {
    try {
      const r = await fetch(`${LOCAL_ENGINE}/health`, {
        cache: "no-store",
        mode: "cors",
      });
      if (!r.ok) throw new Error(`local engine ${r.status}`);
      const health = (await r.json()) as Record<string, unknown>;
      const stateResp = await fetch(`${LOCAL_ENGINE}/api/state`, {
        cache: "no-store",
        mode: "cors",
      });
	      let engineState = stateResp.ok
	        ? ((await stateResp.json()) as LocalEngine["state"])
	        : undefined;
	      if (session?.access_token && !engineState?.key_ok) {
	        const provision = await fetch(`${LOCAL_ENGINE}/api/provision`, {
	          method: "POST",
	          mode: "cors",
	          headers: { "Content-Type": "application/json" },
	          body: JSON.stringify({
	            auth_token: session.access_token,
	            site_url: window.location.origin,
	          }),
	        });
	        if (provision.ok) {
	          const refreshed = await fetch(`${LOCAL_ENGINE}/api/state`, {
	            cache: "no-store",
	            mode: "cors",
	          });
	          if (refreshed.ok) {
	            engineState = (await refreshed.json()) as LocalEngine["state"];
	          }
	        }
	      }
	      setLocalEngine({
        live: true,
        detail: `Connected to the local engine on ${LOCAL_ENGINE}.`,
        health,
        state: engineState,
      });
    } catch (e) {
      setLocalEngine({
        live: false,
        detail:
          "No local engine answered on 127.0.0.1:8731. The deployed app shell is loaded, but the user-device server is not connected.",
      });
    }
	  }, [session]);

  const postLocal = useCallback(
    async (path: string, body?: Record<string, unknown>) => {
      const r = await fetch(`${LOCAL_ENGINE}${path}`, {
        method: "POST",
        mode: "cors",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
      return r.json();
    },
    []
  );

	  const startLocalOnboarding = useCallback(async () => {
    setSetupBusy(true);
    setSetupMsg(null);
    try {
      const r = await fetch(`${LOCAL_ENGINE}/api/onboarding/start`, {
        cache: "no-store",
        mode: "cors",
      });
      if (!r.ok) throw new Error(`onboarding ${r.status}`);
      const j = await r.json();
      setOnboardingTurns([{ question: String(j.question || "") }]);
      setOnboardingIndex(Number(j.index || 0));
      setOnboardingTotal(Number(j.total || 0));
      setOnboardingAnswer("");
    } catch (e) {
      setSetupMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSetupBusy(false);
    }
  }, []);

  const sendLocalOnboardingAnswer = useCallback(async () => {
    const answer = onboardingAnswer.trim();
    if (!answer || !onboardingTurns.length) return;
    setSetupBusy(true);
    setSetupMsg(null);
    const nextTurns = onboardingTurns.map((t, i) =>
      i === onboardingTurns.length - 1 ? { ...t, answer } : t
    );
    setOnboardingTurns(nextTurns);
    setOnboardingAnswer("");
    try {
      const r = await postLocal("/api/onboarding/answer", { answer });
      if (r.done) {
        setOnboardingTurns([]);
        await probeLocalEngine();
        return;
      }
      setOnboardingTurns([
        ...nextTurns,
        { question: String(r.question || "") },
      ]);
      setOnboardingIndex(Number(r.index || nextTurns.length));
      setOnboardingTotal(Number(r.total || onboardingTotal));
    } catch (e) {
      setSetupMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSetupBusy(false);
    }
  }, [
    onboardingAnswer,
    onboardingTurns,
    onboardingTotal,
    postLocal,
    probeLocalEngine,
  ]);

  const doListen = useCallback(async () => {
    setRunning(true);
    setRun(null);
    try {
      const r = await fetch(`${LOCAL_ENGINE}/api/listen/start`, {
        method: "POST",
        mode: "cors",
      });
      const started = await r.json();
      const s = await fetch(`${LOCAL_ENGINE}/api/listen/status`, {
        cache: "no-store",
        mode: "cors",
      });
      const status = await s.json();
      setRun({
        proposal: status?.pending?.proposal ?? null,
        transcript: status?.recent?.[0]?.transcript ?? "",
        engine_decision: status?.recent?.[0]?.outcome ?? "",
        pending: status?.pending ?? null,
        stages: [
          {
            name: "localhost engine",
            real: Boolean(started?.on && !started?.error),
            gated: Boolean(started?.error),
            detail: started?.error
              ? String(started.error)
              : `listening=${Boolean(status?.on)} windows=${status?.windows ?? 0}`,
          },
        ],
        gated: Boolean(started?.error),
        reason: started?.error
          ? String(started.error)
          : "The local engine is listening. Proposals appear when the real rolling window hears or receives an authorized post-ASR transcript.",
      });
    } catch (e) {
      setRun({
        proposal: null,
        transcript: "",
        engine_decision: "",
        stages: [],
          gated: true,
          reason:
            "The browser could not reach the local engine on 127.0.0.1:8731. Honest state, not faked.",
      });
    } finally {
      setRunning(false);
    }
  }, []);

  const refreshLocalRun = useCallback(async (stageDetail: string) => {
    const s = await fetch(`${LOCAL_ENGINE}/api/listen/status`, {
      cache: "no-store",
      mode: "cors",
    });
    const status = await s.json();
    setRun({
      proposal: status?.pending?.proposal ?? null,
      transcript: status?.recent?.[0]?.transcript ?? "",
      engine_decision: status?.recent?.[0]?.outcome ?? "",
      pending: status?.pending ?? null,
      action: status?.acted ?? null,
      stages: [
        {
          name: "localhost engine",
          real: Boolean(status?.on && !status?.error),
          gated: Boolean(status?.error),
          detail: stageDetail || `listening=${Boolean(status?.on)} windows=${status?.windows ?? 0}`,
        },
      ],
      gated: Boolean(status?.error),
      reason: status?.error
        ? String(status.error)
        : "The local engine accepted the input and routed it through the real post-ASR pipeline.",
    });
  }, []);

  const doInjectTranscript = useCallback(async () => {
    const text = transcriptInput.trim();
    if (!text) return;
    setRunning(true);
    try {
      const started = await postLocal("/api/listen/start");
      if (started?.error) {
        throw new Error(String(started.error));
      }
      const injected = await postLocal("/api/listen/inject", { text });
      if (injected?.error) {
        throw new Error(String(injected.error));
      }
      await refreshLocalRun(
        `typed transcript -> ${String(injected?.source || "asr-transcript")} window=${injected?.window ?? "?"}`
      );
    } catch (e) {
      setRun({
        proposal: null,
        transcript: text,
        engine_decision: "",
        stages: [],
        gated: true,
        reason: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setRunning(false);
    }
  }, [postLocal, refreshLocalRun, transcriptInput]);

  const doUploadAudio = useCallback(async (file: File | null) => {
    if (!file) return;
    setUploadBusy(true);
    setRunning(true);
    try {
      const started = await postLocal("/api/listen/start");
      if (started?.error) {
        throw new Error(String(started.error));
      }
      const r = await fetch(`${LOCAL_ENGINE}/api/listen/upload`, {
        method: "POST",
        mode: "cors",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: await file.arrayBuffer(),
      });
      const uploaded = await r.json();
      if (!r.ok || uploaded?.error) {
        throw new Error(String(uploaded?.error || `upload ${r.status}`));
      }
      await refreshLocalRun(
        `audio upload -> ${String(uploaded?.source || "upload-asr")} bytes=${uploaded?.bytes ?? file.size}`
      );
    } catch (e) {
      setRun({
        proposal: null,
        transcript: "",
        engine_decision: "",
        stages: [],
        gated: true,
        reason: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setRunning(false);
      setUploadBusy(false);
    }
  }, [postLocal, refreshLocalRun]);

  const doAct = useCallback(async () => {
    setRunning(true);
    try {
      const acted = await postLocal("/api/act");
      setRun((prev) => ({
        proposal: prev?.proposal ?? null,
        transcript: prev?.transcript ?? "",
        engine_decision: prev?.engine_decision ?? "",
        pending: prev?.pending ?? null,
        action: acted,
        stages: [
          ...(prev?.stages ?? []),
          {
            name: "browser action",
            real: Boolean(acted?.ran),
            gated: Boolean(acted?.gated || acted?.error || acted?.clarify),
            detail: acted?.ran
              ? `status=${acted?.status || "SUCCESS"}`
              : String(acted?.question || acted?.error || acted?.status || "not run"),
          },
        ],
        gated: Boolean(acted?.gated || acted?.error || acted?.clarify),
        reason: acted?.ran
          ? String(acted?.evidence || "Action finished.")
          : String(acted?.question || acted?.error || "Action did not run."),
      }));
    } finally {
      setRunning(false);
    }
  }, [postLocal]);

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
    probeLocalEngine();
    const t = window.setInterval(probeLocalEngine, 4000);
    return () => window.clearInterval(t);
  }, [load, probeLocalEngine]);

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
              your attention.
            </Sub>
            <div
              className="mt-8 rounded-card border border-dark-border bg-dark-elevated px-6 py-5 max-w-[600px] fade-up"
              style={{ animationDelay: "180ms" }}
            >
              <p className="text-[12px] uppercase tracking-[0.18em] text-gold/80 mb-3">
                Install (the app is not yet Apple-notarized)
              </p>
              <p className="text-[13px] text-cream/55 leading-relaxed mb-2">
                Fastest, opens cleanly. Paste this one line into Terminal:
              </p>
              <code className="block rounded-md bg-dark border border-dark-border px-4 py-3 text-[12.5px] text-gold/90 select-all break-all">
                curl -fsSL https://www.anticipy.ai/install.sh | bash
              </code>
              <p className="mt-4 text-[13px] text-cream/55 leading-relaxed">
                Prefer no Terminal? Click Download, open the .dmg, drag
                Anticipy to Applications. If macOS says it is damaged, go to
                System Settings, Privacy and Security, scroll down, and click
                Open Anyway for Anticipy, then open it again.
              </p>
              <p className="mt-3 text-[11.5px] text-cream/30 leading-relaxed">
                This one-time step is the normal cost of an un-notarized build.
                The only way to remove it entirely for everyone is Apple
                notarization, which needs an Apple Developer account. That is
                honestly not done yet and is not faked.
              </p>
            </div>
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
            {!localEngine.live ? (
              <>
                <Statement>Install the Mac engine first.</Statement>
                <Sub>
                  The public app is connected to your private local engine.
                  Install Anticipy, then come back here and continue setup.
                </Sub>
                <div
                  className="mt-8 rounded-card border border-dark-border bg-dark-elevated px-6 py-5 max-w-[600px] fade-up"
                  style={{ animationDelay: "180ms" }}
                >
                  <p className="text-[13px] text-cream/55 leading-relaxed mb-2">
                    Paste this into Terminal:
                  </p>
                  <code className="block rounded-md bg-dark border border-dark-border px-4 py-3 text-[12.5px] text-gold/90 select-all break-all">
                    curl -fsSL https://www.anticipy.ai/install.sh | bash
                  </code>
                </div>
                <Primary onClick={probeLocalEngine}>Check connection</Primary>
              </>
	            ) : !localEngine.state?.key_ok ? (
	              <>
	                <Statement>Connecting your local engine.</Statement>
	                <Sub>
	                  Anticipy is signed in, but the browser has not finished
	                  handing that session to the Mac engine yet. No provider key
	                  is required from you.
	                </Sub>
	                <div
	                  className="mt-10 grid gap-3 max-w-[520px] fade-up"
	                  style={{ animationDelay: "180ms" }}
	                >
	                  {setupMsg && (
	                    <p className="text-[12.5px] text-gold/90 leading-relaxed">
	                      {setupMsg}
	                    </p>
	                  )}
	                  <button
	                    onClick={probeLocalEngine}
	                    disabled={setupBusy}
	                    className="rounded-pill px-8 py-4 text-[14px] font-medium bg-cream text-dark hover:bg-gold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
	                  >
	                    {setupBusy ? "Connecting" : "Try again"}
	                  </button>
	                </div>
	              </>
            ) : !localEngine.state?.onboarded ? (
              <>
                <Statement>
                  {onboardingTurns.length
                    ? "Tell Anticipy what matters."
                    : "Let's set you up."}
                </Statement>
                <Sub>
                  This is the real local onboarding flow. Your answers become
                  the profile Anticipy uses to resolve people, priorities, and
                  the do-not-touch list.
                </Sub>
                {!onboardingTurns.length ? (
                  <Primary onClick={startLocalOnboarding} disabled={setupBusy}>
                    {setupBusy ? "Starting" : "Begin onboarding"}
                  </Primary>
                ) : (
                  <div
                    className="mt-10 max-w-[680px] fade-up"
                    style={{ animationDelay: "180ms" }}
                  >
                    <div className="h-1 rounded-full bg-dark-border overflow-hidden mb-6">
                      <div
                        className="h-full bg-gold transition-all"
                        style={{
                          width: `${Math.max(
                            8,
                            Math.round(
                              (100 * onboardingIndex) /
                                Math.max(1, onboardingTotal)
                            )
                          )}%`,
                        }}
                      />
                    </div>
                    <div className="grid gap-3">
                      {onboardingTurns.map((turn, i) => (
                        <div key={i} className="grid gap-2">
                          <div className="rounded-card border border-dark-border bg-dark-elevated px-5 py-4 text-[14px] text-cream/85">
                            {turn.question}
                          </div>
                          {turn.answer && (
                            <div className="rounded-card bg-cream text-dark px-5 py-4 text-[14px] justify-self-end max-w-[88%]">
                              {turn.answer}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                    <textarea
                      aria-label="Onboarding answer"
                      value={onboardingAnswer}
                      onChange={(e) => setOnboardingAnswer(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          sendLocalOnboardingAnswer();
                        }
                      }}
                      rows={3}
                      placeholder="Type your answer"
                      className="mt-5 w-full rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream placeholder:text-cream/30 outline-none focus:border-gold/50 transition-colors"
                    />
                    {setupMsg && (
                      <p className="mt-3 text-[12.5px] text-gold/90 leading-relaxed">
                        {setupMsg}
                      </p>
                    )}
                    <button
                      onClick={sendLocalOnboardingAnswer}
                      disabled={setupBusy || !onboardingAnswer.trim()}
                      className="mt-4 rounded-pill px-8 py-4 text-[14px] font-medium bg-cream text-dark hover:bg-gold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {setupBusy ? "Thinking" : "Send"}
                    </button>
                  </div>
                )}
              </>
            ) : (
              <>
                <Statement>Anticipy knows the basics.</Statement>
                <Sub>
                  Your local profile is ready. Listening can now use that
                  profile to resolve people, objects, and off-limits areas.
                </Sub>
                <div
                  className="mt-10 rounded-card border border-dark-border bg-dark-elevated px-6 py-5 max-w-[620px] fade-up"
                  style={{ animationDelay: "180ms" }}
                >
                  <pre className="whitespace-pre-wrap text-[12px] leading-relaxed text-cream/65 overflow-auto max-h-[260px]">
                    {JSON.stringify(localEngine.state.profile, null, 2)}
                  </pre>
                </div>
                <Primary onClick={() => setView("listen")}>
                  Start listening
                </Primary>
              </>
            )}
          </div>
        )}

        {view === "listen" && (
          <div className="min-h-screen flex flex-col items-center justify-center text-center max-w-[680px] mx-auto py-28">
            {!localEngine.live ? (
              <>
                <Orb live={false} />
                <p className="mt-12 text-[13px] uppercase tracking-[0.24em] text-cream/40 fade-up">
                  Local engine not connected
                </p>
                <p
                  className="mt-4 text-[14px] text-cream/45 leading-relaxed fade-up max-w-[48ch]"
                  style={{ animationDelay: "120ms" }}
                >
                  {localEngine.detail}
                </p>
                <div
                  className="mt-8 rounded-card border border-dark-border bg-dark-elevated px-6 py-5 text-left w-full max-w-[600px] fade-up"
                  style={{ animationDelay: "180ms" }}
                >
                  <p className="text-[12px] uppercase tracking-[0.18em] text-gold/80 mb-3">
                    Install and start the Mac engine
                  </p>
                  <p className="text-[13px] text-cream/55 leading-relaxed mb-2">
                    Paste this into Terminal. It downloads Anticipy, installs
                    the app, clears quarantine, and starts the local engine.
                  </p>
                  <code className="block rounded-md bg-dark border border-dark-border px-4 py-3 text-[12.5px] text-gold/90 select-all break-all">
                    curl -fsSL https://www.anticipy.ai/install.sh | bash
                  </code>
                </div>
                <div className="flex flex-wrap items-center justify-center gap-3">
                  <Primary onClick={() => setView("download")}>
                    Install Anticipy
                  </Primary>
                  <Ghost onClick={probeLocalEngine}>Check again</Ghost>
                </div>
              </>
	            ) : !localEngine.state?.onboarded ? (
              <>
                <Orb live={false} />
                <p className="mt-12 text-[13px] uppercase tracking-[0.24em] text-gold/70 fade-up">
                  Finish setup first
                </p>
                <p
                  className="mt-4 text-[14px] text-cream/50 fade-up max-w-[48ch]"
                  style={{ animationDelay: "120ms" }}
                >
	                  The local engine is connected to your Anticipy account, but
	                  it needs your real onboarding profile before listening can be
	                  useful.
                </p>
                <Primary onClick={() => setView("onboarding")}>
                  Continue setup
                </Primary>
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
	                      <button
                          onClick={doAct}
                          disabled={running}
                          className="rounded-pill bg-cream text-dark px-7 py-3 text-[13px] font-medium hover:bg-gold transition-colors disabled:opacity-40"
                        >
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
                      {run.action && (
                        <p className="mt-4 text-[12px] text-cream/45 leading-relaxed">
                          Action: {String(run.action.status || run.action.error || run.action.question || "recorded")}.
                        </p>
                      )}
	                  </div>
	                )}
                  {run.action && run.proposal && (
                    <p className="mt-4 text-[12px] text-cream/45 leading-relaxed text-left">
                      Action: {String(run.action.status || run.action.error || run.action.question || "recorded")}.
                    </p>
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
	                {!running && (
                    <div className="mt-10 w-full max-w-[560px] grid gap-3 fade-up">
                      <Primary onClick={doListen}>Listen</Primary>
                      <div className="grid gap-3 rounded-card border border-dark-border bg-dark-elevated p-4 text-left">
                        <textarea
                          value={transcriptInput}
                          onChange={(e) => setTranscriptInput(e.target.value)}
                          placeholder="Paste a transcript"
                          className="min-h-[92px] rounded-md border border-dark-border bg-dark px-4 py-3 text-[13px] text-cream outline-none placeholder:text-cream/30"
                        />
                        <div className="flex flex-wrap gap-3">
                          <button
                            onClick={doInjectTranscript}
                            disabled={!transcriptInput.trim()}
                            className="rounded-pill bg-cream text-dark px-5 py-3 text-[13px] font-medium hover:bg-gold transition-colors disabled:opacity-40"
                          >
                            Run transcript
                          </button>
                          <label className="rounded-pill border border-dark-border text-cream/70 px-5 py-3 text-[13px] hover:text-cream transition-colors cursor-pointer">
                            {uploadBusy ? "Uploading..." : "Upload audio"}
                            <input
                              type="file"
                              accept="audio/*,.mp3,.wav,.m4a,.aiff"
                              className="hidden"
                              onChange={(e) => {
                                void doUploadAudio(e.target.files?.[0] ?? null);
                                e.currentTarget.value = "";
                              }}
                            />
                          </label>
                        </div>
                      </div>
                    </div>
                  )}
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
                  {localEngine.live
                    ? "Connected. Real proposals appear here as one calm list."
                    : "Nothing to show yet, honestly."}
              </p>
              <p className="mt-3 text-[13px] text-cream/45 leading-relaxed max-w-[54ch]">
                {localEngine.live
                  ? "The deployed app shell is connected to the local device engine."
                  : "Real history will appear here once the browser connects to the local engine."}
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
                ["Engine", localEngine.detail],
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
