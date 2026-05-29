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

function requestedViewFromUrl(): View | null {
  if (typeof window === "undefined") return null;
  const requested = new URLSearchParams(window.location.search).get("view");
  if (
    requested === "download" ||
    requested === "onboarding" ||
    requested === "listen" ||
    requested === "history" ||
    requested === "settings"
  ) {
    return requested;
  }
  return null;
}

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

type AudioDevice = {
  index: number;
  name: string;
  kind?: string;
  source_detail?: string;
  connection_type?: string;
  is_default?: boolean;
};

function isUsableAudioDevice(device: AudioDevice): boolean {
  return device.kind !== "virtual" && device.kind !== "unsupported";
}

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

function ProfileSummary({
  profile,
}: {
  profile?: Record<string, unknown> | null;
}) {
  if (!profile || typeof profile !== "object") {
    return (
      <p className="text-[13px] text-cream/55 leading-relaxed">
        Your profile is on this Mac. Listening will use it the moment a name
        comes up.
      </p>
    );
  }

  const name = typeof profile.name === "string" ? profile.name : "";
  const roleTitle =
    typeof profile.role_title === "string" ? profile.role_title : "";
  const peopleRaw = (profile.people && typeof profile.people === "object"
    ? (profile.people as Record<string, unknown>)
    : {}) as Record<string, unknown>;

  const stripEmail = (value: string): string => {
    const idx = value.indexOf("<");
    return idx >= 0 ? value.slice(0, idx).trim() : value.trim();
  };

  const peopleEntries = Object.entries(peopleRaw)
    .filter(([, v]) => typeof v === "string" && (v as string).trim().length > 0)
    .map(([role, v]) => ({ role, person: stripEmail(v as string) }));

  return (
    <div className="space-y-4 text-[13.5px] leading-relaxed">
      {(name || roleTitle) && (
        <p className="text-cream/85">
          {name && <span>{name}</span>}
          {name && roleTitle && <span className="text-cream/45">, </span>}
          {roleTitle && (
            <span className="text-cream/70">{roleTitle}</span>
          )}
          {"."}
        </p>
      )}

      {peopleEntries.length > 0 && (
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-cream/40 mb-2">
            People Anticipy knows
          </p>
          <ul className="space-y-1.5">
            {peopleEntries.map(({ role, person }) => (
              <li key={role} className="flex gap-3 text-cream/85">
                <span className="text-cream/45 min-w-[148px] capitalize">
                  {role}
                </span>
                <span>{person}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {peopleEntries.length === 0 && !name && !roleTitle && (
        <p className="text-cream/55">
          Your profile is on this Mac, ready for listening to use.
        </p>
      )}
    </div>
  );
}

export default function AnticipyApp() {
  const [view, setView] = useState<View>("account");
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

  const writeAuthStorageAliases = useCallback((sessionData: Session) => {
    try {
      const serialized = JSON.stringify({
        access_token: sessionData.access_token,
        refresh_token: sessionData.refresh_token,
        expires_at: sessionData.expires_at,
        user: {
          id: sessionData.user.id,
          email: sessionData.user.email,
        },
      });
      window.localStorage.setItem("sb-auth-token", serialized);
      window.localStorage.setItem("supabase.auth.token", serialized);
    } catch {
      // localStorage can be disabled. Supabase's own session write is still the source of truth.
    }
  }, []);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) writeAuthStorageAliases(data.session);
      setSession(data.session);
      setAuthReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => {
      if (s) writeAuthStorageAliases(s);
      setSession(s);
    });
    return () => sub.subscription.unsubscribe();
  }, [writeAuthStorageAliases]);

  const handoffAndRedirect = useCallback(
    async (sessionData: Session) => {
      writeAuthStorageAliases(sessionData);
      try {
        const mintResp = await fetch("/api/auth/handoff/mint", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${sessionData.access_token}`,
          },
          body: JSON.stringify({ refresh_token: sessionData.refresh_token }),
        });
        if (mintResp.ok) {
          const mint = (await mintResp.json()) as { token?: string };
          if (mint.token) {
            window.location.href = `/app/download?token=${encodeURIComponent(
              mint.token
            )}`;
            return;
          }
        }
      } catch {
        // mint unreachable; still navigate so the page advances honestly
      }
      window.location.href = "/app/download";
    },
    [writeAuthStorageAliases]
  );

  const submitAuth = useCallback(async () => {
    if (!email.trim()) {
      setAuthMsg("Enter your email to continue.");
      return;
    }
    if (password.length < 8) {
      setAuthMsg("Password must be at least 8 characters.");
      return;
    }
    setAuthBusy(true);
    setAuthMsg(null);
    try {
      if (mode === "signup") {
        // Server route uses the service role to create a confirmed
        // auth.users row and return a real session. This bypasses the
        // public email rate limit and never depends on Confirm Email.
        const resp = await fetch("/api/auth/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.trim(), password }),
        });
        const data = (await resp.json().catch(() => ({}))) as {
          access_token?: string | null;
          refresh_token?: string | null;
          user?: { id?: string; email?: string };
          error?: string;
        };
        if (!resp.ok) {
          setAuthMsg(data.error || "Signup failed.");
          return;
        }
        if (data.access_token && data.refresh_token) {
          const { data: setData, error: setErr } =
            await supabase.auth.setSession({
              access_token: data.access_token,
              refresh_token: data.refresh_token,
            });
          if (!setErr && setData.session) {
            await handoffAndRedirect(setData.session);
            return;
          }
        }
        // Row was created but session did not stick in the client.
        // Still navigate so the user sees the next step honestly.
        window.location.href = "/app/download";
      } else {
        const { data, error: e } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (e) setAuthMsg(e.message);
        else if (data.session) await handoffAndRedirect(data.session);
        else window.location.href = "/app/download";
      }
    } catch (err) {
      setAuthMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setAuthBusy(false);
    }
  }, [mode, email, password, handoffAndRedirect]);

  const logout = useCallback(async () => {
    await supabase.auth.signOut();
    setView("entry");
  }, []);

  // ── engine state + the real Listen round trip ───────────────────
  const [running, setRunning] = useState(false);
  const [transcriptInput, setTranscriptInput] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [audioDevices, setAudioDevices] = useState<AudioDevice[]>([]);
  const [selectedAudioDeviceIndex, setSelectedAudioDeviceIndex] =
    useState<number | null>(null);
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
      const audioResp = await fetch(`${LOCAL_ENGINE}/api/audio/devices`, {
        cache: "no-store",
        mode: "cors",
      });
      if (audioResp.ok) {
        const audio = (await audioResp.json()) as { devices?: AudioDevice[] };
        const devices = Array.isArray(audio.devices) ? audio.devices : [];
        setAudioDevices(devices);
        setSelectedAudioDeviceIndex((current) => {
          if (devices.some((d) => d.index === current)) return current;
          const preferred =
            devices.find((d) => d.kind === "builtin") ||
            devices.find((d) => d.is_default && isUsableAudioDevice(d)) ||
            devices.find((d) => isUsableAudioDevice(d)) ||
            devices[0];
          return preferred?.index ?? null;
        });
      }
	      // Supabase access tokens expire. The local Mac engine is the
	      // model client for the real action chain, so a one-time
	      // provision silently goes stale and the next Gmail/Calendar
	      // action fails with broker 401. While the public app is open,
	      // keep the localhost engine fresh with the current browser
	      // session token on every probe.
	      if (session?.access_token) {
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
      const selected = audioDevices.find(
        (d) => d.index === selectedAudioDeviceIndex
      );
      const isExternalPhysicalDevice =
        selected && selected.kind !== "builtin" && isUsableAudioDevice(selected);
      const sourceMode =
        isExternalPhysicalDevice
          ? "external_microphone"
          : "computer_microphone";
      const started = await postLocal("/api/listen/start", {
        ...(selected ? { device_index: selected.index } : {}),
        source_mode: sourceMode,
      });
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
            name: "Anticipy",
            real: Boolean(started?.on && !started?.error),
            gated: Boolean(started?.error),
            detail: started?.error
              ? String(started.error)
              : `Listening through ${String(started?.audio_device?.name || "your microphone")}.`,
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
  }, [audioDevices, postLocal, selectedAudioDeviceIndex]);

  const refreshLocalRun = useCallback(async (
    stageDetail: string,
    options?: { acceptedInput?: boolean }
  ) => {
    const s = await fetch(`${LOCAL_ENGINE}/api/listen/status`, {
      cache: "no-store",
      mode: "cors",
    });
    const status = await s.json();
    const acceptedInput = Boolean(options?.acceptedInput);
    setRun({
      proposal: status?.pending?.proposal ?? null,
      transcript: status?.recent?.[0]?.transcript ?? "",
      engine_decision: status?.recent?.[0]?.outcome ?? "",
      pending: status?.pending ?? null,
      action: status?.acted ?? null,
      stages: [
        {
          name: "Anticipy",
          real: Boolean((status?.on || acceptedInput) && !status?.error),
          gated: Boolean(status?.error),
          detail: stageDetail || (status?.on ? "Listening." : "Idle."),
        },
      ],
      gated: Boolean(status?.error),
      reason: status?.error
        ? String(status.error)
        : "The local engine accepted the input and routed it through the real post-ASR pipeline.",
    });
  }, []);

  const surfacePendingFromLocalEngine = useCallback(async () => {
    try {
      const s = await fetch(`${LOCAL_ENGINE}/api/listen/status`, {
        cache: "no-store",
        mode: "cors",
      });
      if (!s.ok) return;
      const status = await s.json();
      const pending = status?.pending;
      if (!pending?.proposal) return;
      setLocalEngine((prev) => ({
        ...prev,
        live: true,
        detail: `Connected to the local engine on ${LOCAL_ENGINE}.`,
        state: {
          ...(prev.state ?? {}),
          onboarded: prev.state?.onboarded ?? true,
        },
      }));
      setRun({
        proposal: pending.proposal ?? null,
        transcript: status?.recent?.[0]?.transcript ?? "",
        engine_decision: status?.recent?.[0]?.outcome ?? "",
        pending,
        action: status?.acted ?? null,
        stages: [
          {
            name: "Anticipy",
            real: true,
            gated: false,
            detail: "Heard something just now.",
          },
        ],
        gated: false,
        reason:
          "The local engine surfaced an action, ask, or decline from the real post-ASR pipeline.",
      });
      setView("listen");
    } catch {
      // The public shell must stay usable when the user-device engine is not running.
    }
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
        `audio upload -> ${String(uploaded?.source || "upload-asr")} bytes=${uploaded?.bytes ?? file.size}`,
        { acceptedInput: true }
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
  }, [refreshLocalRun]);

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

  const doDismiss = useCallback(async () => {
    await postLocal("/api/listen/dismiss");
    setRun(null);
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
  }, [load]);

  useEffect(() => {
    const requested = requestedViewFromUrl();
    if (requested) setView(requested);
  }, []);

  // Once a signed-in user has installed the public user-device engine,
  // /app should behave like the control surface, not keep showing the
  // installer. Keep account/entry quiet, but probe from Download too so
  // returning installed users land on Listen.
  useEffect(() => {
    const needsEngine =
      view === "onboarding" ||
      (view === "download" && Boolean(session)) ||
      view === "listen" ||
      view === "history" ||
      view === "settings";
    if (!needsEngine) return;
    probeLocalEngine();
    const t = window.setInterval(probeLocalEngine, 4000);
    return () => window.clearInterval(t);
  }, [view, session, probeLocalEngine]);

  useEffect(() => {
    if (
      authReady &&
      session &&
      view === "download" &&
      localEngine.live &&
      localEngine.state?.onboarded
    ) {
      setView("listen");
    }
  }, [
    authReady,
    session,
    view,
    localEngine.live,
    localEngine.state?.onboarded,
  ]);

  useEffect(() => {
    if (!authReady || !session) return;
    surfacePendingFromLocalEngine();
    const t = window.setInterval(surfacePendingFromLocalEngine, 2500);
    return () => window.clearInterval(t);
  }, [authReady, session, surfacePendingFromLocalEngine]);

  // session gate: a gated view with no real session sends you to auth,
  // and a fresh first-visit lands directly on the signup form
  useEffect(() => {
    if (authReady && !session && GATED.includes(view)) setView("account");
    if (authReady && !session && view === "entry") setView("account");
    if (authReady && session && view === "account") setView("download");
  }, [authReady, session, view]);

  if (error === "offline" && view !== "entry" && view !== "account") {
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

  const runDecline = Boolean(
    run?.pending?.["competent_decline"] || run?.pending?.["decline"]
  );

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
            <p className="mt-8 text-[12px] text-cream/35 leading-relaxed max-w-[54ch] fade-up">
              Mac install note: because this build is not Apple-notarized yet,
              Gatekeeper may show an unverified developer warning. The download
              step explains the one-time Open Anyway path before you install.
            </p>
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
              <label
                htmlFor="email"
                className="text-[11px] uppercase tracking-[0.18em] text-cream/45"
              >
                Email
              </label>
              <input
                aria-label="Email"
                id="email"
                name="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                className="rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream outline-none focus:border-gold/50 transition-colors"
              />
              <label
                htmlFor="password"
                className="mt-2 text-[11px] uppercase tracking-[0.18em] text-cream/45"
              >
                Password
              </label>
              <input
                aria-label="Password"
                id="password"
                name="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={
                  mode === "signup" ? "new-password" : "current-password"
                }
                className="rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream outline-none focus:border-gold/50 transition-colors"
              />
              {authMsg && (
                <p className="text-[12.5px] text-gold/90 leading-relaxed">
                  {authMsg}
                </p>
              )}
              <button
                type="submit"
                onClick={submitAuth}
                disabled={authBusy}
                className="mt-2 rounded-pill px-8 py-4 text-[14px] font-medium bg-cream text-dark hover:bg-gold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {authBusy
                  ? "One moment"
                  : mode === "signup"
                  ? "Get Anticipy"
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
              <p className="text-[11.5px] text-cream/30 leading-relaxed mt-2">
                Mac install note: Gatekeeper may show an unverified developer
                warning because this build is not Apple-notarized yet. The
                download step explains the one-time Open Anyway path.
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
                Anticipy to Applications. If macOS says it is from an
                unverified developer or that it is damaged, Gatekeeper is
                blocking the un-notarized build. Go to System Settings, Privacy
                and Security, scroll down, and click Open Anyway for Anticipy,
                then open it again.
              </p>
              <p className="mt-3 text-[11.5px] text-cream/30 leading-relaxed">
                This one-time step is the normal cost of an un-notarized build.
                The only way to remove it entirely for everyone is Apple
                notarization, which needs an Apple Developer account. That is
                honestly not done yet and is not faked.
              </p>
            </div>
            <div>
              <Primary href="/dl/Anticipy_1.0.0_aarch64.dmg">
                Download for macOS
              </Primary>
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
                      className="mt-5 w-full rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream outline-none focus:border-gold/50 transition-colors"
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
                  <ProfileSummary profile={localEngine.state.profile} />
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
            ) : run ? (
              <div className="w-full fade-up">
                {run.proposal && run.transcript ? (
                  <div className="rounded-card border border-dark-border bg-dark-elevated px-8 py-9 text-left">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-gold/80 mb-4">
                      {runDecline
                        ? "Cannot safely act"
                        : "Anticipy caught something"}
                    </p>
                    <p className="font-serif text-[clamp(20px,3vw,28px)] text-cream leading-snug">
                      {run.proposal}
                    </p>
                    <p className="mt-5 text-[12.5px] text-cream/45 leading-relaxed">
                      Heard: {run.transcript}. {run.engine_decision ? `Reasoning decision: ${run.engine_decision}.` : ""}
                    </p>
                    {runDecline ? (
                      <div className="mt-8 flex gap-3">
                        <button
                          onClick={doDismiss}
                          className="rounded-pill border border-dark-border text-cream/70 px-7 py-3 text-[13px] hover:text-cream transition-colors"
                        >
                          Dismiss
                        </button>
                      </div>
                    ) : (
	                    <div className="mt-8 flex gap-3">
	                      <button
                          onClick={doAct}
                          disabled={running}
                          className="rounded-pill bg-cream text-dark px-7 py-3 text-[13px] font-medium hover:bg-gold transition-colors disabled:opacity-40"
                        >
	                        Yes, do it
	                      </button>
	                      <button
                          onClick={doDismiss}
                          className="rounded-pill border border-dark-border text-cream/70 px-7 py-3 text-[13px] hover:text-cream transition-colors"
                        >
	                        No
	                      </button>
                    </div>
                    )}
                  </div>
	                ) : (
	                  <div className="rounded-card border border-dark-border bg-dark-elevated px-8 py-10 text-left">
	                    <p className="text-[11px] uppercase tracking-[0.22em] text-gold/80 mb-4">
	                      Welcome to Anticipy
	                    </p>
	                    <p className="font-serif text-[clamp(22px,3vw,30px)] text-cream leading-snug mb-2">
	                      Let&apos;s get to know you.
	                    </p>
	                    <p className="text-[13px] text-cream/55 leading-relaxed mb-7">
	                      Pick one. Takes about ten minutes. Anticipy gets sharper once it knows who you spend time with and what you&apos;re working on.
	                    </p>
	                    <div className="grid gap-3">
	                      <a href="/onboarding/call" className="rounded-card border border-dark-border bg-dark px-5 py-4 hover:border-gold transition-colors block">
	                        <p className="text-[14px] text-cream font-medium">Have Anticipy call you</p>
	                        <p className="text-[12px] text-cream/55 mt-1">Quick friend-style interview on your phone. Hands-free.</p>
	                      </a>
	                      <a href="/onboarding/audio" className="rounded-card border border-dark-border bg-dark px-5 py-4 hover:border-gold transition-colors block">
	                        <p className="text-[14px] text-cream font-medium">Drop in an MP3 of your day</p>
	                        <p className="text-[12px] text-cream/55 mt-1">If you already recorded yourself, give Anticipy that.</p>
	                      </a>
	                      <a href="/onboarding/chat" className="rounded-card border border-dark-border bg-dark px-5 py-4 hover:border-gold transition-colors block">
	                        <p className="text-[14px] text-cream font-medium">Type a short chat</p>
	                        <p className="text-[12px] text-cream/55 mt-1">Five quick questions in your browser. Five minutes.</p>
	                      </a>
	                    </div>
                      {run.action && (
                        <p className="mt-6 text-[12px] text-cream/45 leading-relaxed">
                          Last action: {String(run.action.status || run.action.error || run.action.question || "recorded")}.
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
                      <div className="grid gap-2 rounded-card border border-dark-border bg-dark-elevated p-4 text-left">
                        <label
                          htmlFor="audio-source"
                          className="text-[11px] uppercase tracking-[0.2em] text-gold/70"
                        >
                          Audio source
                        </label>
                        <select
                          id="audio-source"
                          value={selectedAudioDeviceIndex ?? ""}
                          onChange={(e) =>
                            setSelectedAudioDeviceIndex(
                              e.target.value === "" ? null : Number(e.target.value)
                            )
                          }
                          className="rounded-md border border-dark-border bg-dark px-4 py-3 text-[13px] text-cream outline-none"
                        >
                          {audioDevices.length === 0 && (
                            <option value="">Default microphone</option>
                          )}
                          {audioDevices.map((device) => (
                            <option key={`${device.index}-${device.name}`} value={device.index}>
                              {device.name} {device.kind ? `(${device.kind})` : ""}
                            </option>
                          ))}
                        </select>
                      </div>
	                      <Primary onClick={doListen}>Listen</Primary>
                      <div className="grid gap-3 rounded-card border border-dark-border bg-dark-elevated p-4 text-left">
                        <textarea
                          aria-label="Transcript"
                          value={transcriptInput}
                          onChange={(e) => setTranscriptInput(e.target.value)}
                          className="min-h-[92px] rounded-md border border-dark-border bg-dark px-4 py-3 text-[13px] text-cream outline-none"
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
                [
                  "Audio source",
                  audioDevices.find((d) => d.index === selectedAudioDeviceIndex)
                    ?.name || "Default microphone",
                ],
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
