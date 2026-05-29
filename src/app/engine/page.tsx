"use client";

import { useState, useRef, useCallback, useEffect, type FormEvent } from "react";
import { supabase } from "@/lib/supabase";
import type { Session } from "@supabase/supabase-js";

// ─── Types ────────────────────────────────────────────────────────────────────

interface TranscriptSegment {
  speaker_id: number;
  start_time: number;
  end_time: number;
  text: string;
}

interface Intent {
  id: string;
  action_type: string;
  confidence: number;
  importance: string;
  summary_for_user: string;
  evidence_quote: string;
  parameters: Record<string, unknown>;
}

// Check-in data — the proactive engine sets status='awaiting_user' and
// puts a yes/no question in execution_result when it's about to do
// something it wants the wearer to confirm. default_after_timeout (yes/no)
// tells us what to do if the wearer doesn't respond inside CHECKIN_WINDOW_MS.
interface CheckIn {
  intentId: string;
  question: string;
  defaultAfterTimeout: "yes" | "no";
  // Wall-clock ms when this check-in was first surfaced — used to drive the
  // countdown ring without re-rendering the whole page each tick.
  startedAt: number;
  // True once the user clicked yes/no/auto-resolved. Keeps the card visible
  // briefly with a confirmation state instead of yanking it from the DOM.
  resolved: null | "accept" | "reject" | "auto_proceed";
}

const CHECKIN_WINDOW_MS = 30_000;

type EngineState =
  | "idle"
  | "recording"
  | "processing"
  | "transcribing"
  | "analyzing"
  | "done"
  | "error";

type AuthMode = "signin" | "signup" | "reset";

// ─── Constants ────────────────────────────────────────────────────────────────

const SPEAKER_COLORS = [
  "#C8A97E",
  "#7C9CBF",
  "#9B8EC4",
  "#7EBF8A",
  "#BF7E7E",
];

// Map any raw/technical error string into a calm, user-facing one-liner.
// Investors should never see "fetch failed", "401 Unauthorized", model names,
// JSON, stack traces, or session IDs.
function friendlyError(raw: unknown): string {
  const msg =
    raw instanceof Error
      ? raw.message
      : typeof raw === "string"
        ? raw
        : "";
  const lower = msg.toLowerCase();

  if (!msg) return "Hmm, that didn't go through. Give it another sec and try again.";
  if (lower.includes("sign in")) return "Please sign in again to continue.";
  if (
    lower.includes("permission") ||
    lower.includes("notallowed") ||
    lower.includes("not allowed") ||
    lower.includes("getusermedia")
  )
    return "Microphone access is blocked. Allow the mic in your browser and try again.";
  if (lower.includes("no speech")) return "We didn't catch any speech. Try speaking a bit closer to the mic.";
  if (
    lower.includes("network") ||
    lower.includes("fetch") ||
    lower.includes("failed to fetch") ||
    lower.includes("offline")
  )
    return "Network hiccup. Check your connection and try again.";
  if (lower.includes("rate") || lower.includes("429"))
    return "Lots of activity right now. Try again in a moment.";
  if (lower.includes("unauthorized") || lower.includes("401") || lower.includes("403"))
    return "Your session expired. Please sign in again.";
  if (lower.includes("transcription dropped") || lower.includes("dropped"))
    return "We're still recording. Finish and we'll process the audio.";
  // Anything else: don't leak it.
  return "Something didn't go through. Give it another sec and try again.";
}

const IMPORTANCE_STYLES: Record<
  string,
  { bg: string; border: string; label: string }
> = {
  critical: {
    bg: "rgba(239,68,68,0.1)",
    border: "rgba(239,68,68,0.3)",
    label: "CRITICAL",
  },
  important: {
    bg: "rgba(251,146,60,0.1)",
    border: "rgba(251,146,60,0.3)",
    label: "Important",
  },
  standard: {
    bg: "rgba(200,169,126,0.1)",
    border: "rgba(200,169,126,0.3)",
    label: "Standard",
  },
  low: {
    bg: "rgba(138,138,138,0.08)",
    border: "rgba(138,138,138,0.2)",
    label: "Low",
  },
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function EnginePage() {
  // ── Auth state ──────────────────────────────────────────────────────────────
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authMode, setAuthMode] = useState<AuthMode>("signin");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);
  const [resetSent, setResetSent] = useState(false);
  // True when the user just clicked a password-reset email link. Supabase
  // signs them in with a temporary recovery session, but they must call
  // updateUser({ password }) before the new password takes effect.
  const [recoveryMode, setRecoveryMode] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [recoveryUpdated, setRecoveryUpdated] = useState(false);

  // ── Setup state ─────────────────────────────────────────────────────────────
  // Persist setup-card dismissal across reloads so returning users don't see
  // the same onboarding card every time.
  const [setupDismissed, setSetupDismissedState] = useState(false);
  const setSetupDismissed = useCallback((v: boolean) => {
    setSetupDismissedState(v);
    try {
      if (typeof window !== "undefined") {
        if (v) localStorage.setItem("anticipy_setup_dismissed", "1");
        else localStorage.removeItem("anticipy_setup_dismissed");
      }
    } catch { /* localStorage may be blocked (private mode) */ }
  }, []);
  useEffect(() => {
    try {
      if (typeof window !== "undefined" && localStorage.getItem("anticipy_setup_dismissed") === "1") {
        setSetupDismissedState(true);
      }
    } catch { /* localStorage may be blocked */ }
  }, []);

  // ── Engine state ────────────────────────────────────────────────────────────
  const [state, setState] = useState<EngineState>("idle");
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [intents, setIntents] = useState<Intent[]>([]);
  const [error, setError] = useState("");
  const [duration, setDuration] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [manualTranscript, setManualTranscript] = useState("");
  const [liveText, setLiveText] = useState("");
  const [calendarConnected, setCalendarConnected] = useState(false);
  // Tracks per-intent UI state for the in-page confirm flow. Independent of
  // server-side status — purely for showing optimistic feedback after click.
  const [intentDecisions, setIntentDecisions] = useState<Record<string, "yes" | "no" | "loading">>({});

  // Clarification loop: when the agent runs an intent and ends with a
  // success:false done() that includes a question (e.g. "where are you flying
  // from / to?"), the extension PATCHes execution_result to that question and
  // status to "failed". A Realtime subscription below fires on that update and
  // pushes a {intentId, question, parameters} entry into followUps so the UI
  // can render a chat-style question + answer input under the original action.
  interface FollowUp {
    intentId: string;
    actionType: string;
    summary: string;
    question: string;
    parameters: Record<string, unknown>;
    answer: string;
    submitting: boolean;
    answered: boolean;
  }
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  // Tracks intent IDs we've already created a follow-up for, so we don't
  // double-render if Realtime fires repeatedly on the same row.
  const seenFollowUpsRef = useRef<Set<string>>(new Set());

  // Check-in cards: surfaced when an intent flips to status='awaiting_user'.
  // Each card runs a 30s countdown and auto-resolves to defaultAfterTimeout.
  const [checkIns, setCheckIns] = useState<CheckIn[]>([]);
  // Force a re-render once per second so the countdown ring updates. We
  // intentionally don't re-derive from setCheckIns — the timer is just for
  // visual progress, not data.
  const [, setNowTick] = useState(0);
  useEffect(() => {
    if (checkIns.length === 0) return;
    const t = setInterval(() => setNowTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [checkIns.length]);
  const seenCheckInsRef = useRef<Set<string>>(new Set());

  // Browser / extension capability flags. Computed once on mount.
  // unsupportedReason !== null → render a clean "open this on your laptop
  // with Chrome" full-page block instead of the broken record/extension flow.
  const [unsupportedReason, setUnsupportedReason] = useState<null | "mobile" | "browser">(null);
  // Set true as soon as the content script pings us — used to know whether
  // to show the "looks like the extension isn't running" toast on confirm.
  const [extensionDetected, setExtensionDetected] = useState(false);
  // Subtle inline toast (ephemeral, never blocks). Single source of truth so
  // we never stack technical errors on top of each other.
  const [toast, setToast] = useState<{ kind: "info" | "warn"; text: string } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const showToast = useCallback(
    (text: string, kind: "info" | "warn" = "info", ms = 5000) => {
      setToast({ kind, text });
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      toastTimerRef.current = setTimeout(() => setToast(null), ms);
    },
    []
  );

  // Per-intent agent progress, updated from anticipy_intents Realtime UPDATE
  // events. Surfaces "Anticipy is working on this..." with the latest hint
  // (current step / execution_result) so the page never goes silent during
  // the 10-90s agent run.
  type IntentStatus = "running" | "done" | "failed";
  interface IntentProgress {
    status: IntentStatus;
    message: string;
    updatedAt: number;
  }
  const [intentProgress, setIntentProgress] = useState<Record<string, IntentProgress>>({});

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordedMimeRef = useRef<string>("");
  const sessionIdRef = useRef<string>("");
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const autoAnalyzeTimerRef = useRef<ReturnType<typeof setInterval>>();
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);
  const dgSocketRef = useRef<WebSocket | null>(null);
  const liveSegmentsRef = useRef<TranscriptSegment[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  // Tracks whether Deepgram disconnected mid-recording. If true on stop,
  // we fall back to batch transcription so no audio is silently lost.
  const dgDroppedRef = useRef(false);

  // ── Auth effects ────────────────────────────────────────────────────────────

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setAuthLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      setSession(session);
      if (session) setAuthLoading(false);
      // Recovery sessions are signed-in sessions with a single privileged
      // operation: changing the password. Surface a "set new password" form
      // instead of dropping the user straight into the engine UI.
      if (event === "PASSWORD_RECOVERY") {
        setRecoveryMode(true);
        setRecoveryUpdated(false);
        setAuthError("");
      }
    });
    return () => subscription.unsubscribe();
  }, []);

  // Check calendar status — pass the auth token so the server can scope the
  // lookup to *this* user (tokens are keyed by email).
  useEffect(() => {
    if (!session) return;
    fetch("/api/auth/google/status", {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then((r) => r.json())
      .then((d) => setCalendarConnected(!!d.connected))
      .catch(() => setCalendarConnected(false));
  }, [session]);

  // Realtime: listen for intent rows flipping to status='failed' with a
  // question-shaped execution_result. That's how the extension/agent signals
  // "I need more info to do this task" — surface the question to the wearer
  // and let them answer in-line.
  //
  // We subscribe to ALL UPDATEs on anticipy_intents, then filter client-side
  // to rows belonging to intents we KNOW about (the user just generated them
  // in this tab — id is in the `intents` state). That avoids leaking other
  // users' rows even though there's currently no RLS on the table — we never
  // act on a row we didn't originate from this session.
  useEffect(() => {
    if (!session) return;
    const channel = supabase
      .channel("anticipy_intents_followups")
      .on(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "postgres_changes" as any,
        { event: "UPDATE", schema: "public", table: "anticipy_intents" },
        (payload: { new: Record<string, unknown> }) => {
          const row = payload.new ?? {};
          const id = String(row.id ?? "");
          const status = String(row.status ?? "");
          const execResult = String(row.execution_result ?? "").trim();
          if (!id || status !== "failed" || !execResult) return;
          // A question is the only kind of failure we want to prompt on. We
          // detect it heuristically: contains "?" OR starts with a wh-word.
          // The LLM produces these naturally; this just filters out
          // bare-fail strings like "Could not log in".
          const looksLikeQuestion =
            execResult.includes("?") ||
            /^(what|where|when|which|who|how|do|does|did|is|are|can|could|should|would)\b/i.test(
              execResult
            );
          if (!looksLikeQuestion) return;
          if (seenFollowUpsRef.current.has(id)) return;
          // Only surface follow-ups for intents we originated from this tab.
          // If the intent is in our local list, it's ours.
          setIntents((prevIntents) => {
            const match = prevIntents.find((i) => i.id === id);
            if (!match) return prevIntents;
            seenFollowUpsRef.current.add(id);
            setFollowUps((prev) =>
              prev.some((f) => f.intentId === id)
                ? prev
                : [
                    ...prev,
                    {
                      intentId: id,
                      actionType: match.action_type,
                      summary: match.summary_for_user,
                      question: execResult,
                      parameters: match.parameters || {},
                      answer: "",
                      submitting: false,
                      answered: false,
                    },
                  ]
            );
            return prevIntents;
          });
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [session]);

  // Realtime: surface check-in cards when an intent flips to
  // status='awaiting_user'. The proactive engine writes the yes/no question
  // into execution_result and the safe default ('yes'/'no') into
  // default_after_timeout. We only act on intents we KNOW about (originated
  // from this tab) to avoid leaking other users' rows.
  useEffect(() => {
    if (!session) return;
    const channel = supabase
      .channel("anticipy_intents_checkins")
      .on(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "postgres_changes" as any,
        { event: "UPDATE", schema: "public", table: "anticipy_intents" },
        (payload: { new: Record<string, unknown> }) => {
          const row = payload.new ?? {};
          const id = String(row.id ?? "");
          const status = String(row.status ?? "");
          const execResult = String(row.execution_result ?? "").trim();
          const dft = String(row.default_after_timeout ?? "").trim().toLowerCase();
          if (!id || status !== "awaiting_user" || !execResult) return;
          if (seenCheckInsRef.current.has(id)) return;
          // Only surface check-ins for intents we originated from this tab.
          setIntents((prevIntents) => {
            const match = prevIntents.find((i) => i.id === id);
            if (!match) return prevIntents;
            seenCheckInsRef.current.add(id);
            setCheckIns((prev) =>
              prev.some((c) => c.intentId === id)
                ? prev
                : [
                    ...prev,
                    {
                      intentId: id,
                      question: execResult,
                      defaultAfterTimeout: dft === "yes" ? "yes" : "no",
                      startedAt: Date.now(),
                      resolved: null,
                    },
                  ]
            );
            return prevIntents;
          });
        }
      )
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [session]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (autoAnalyzeTimerRef.current) clearInterval(autoAnalyzeTimerRef.current);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (dgSocketRef.current) dgSocketRef.current.close();
      if (audioCtxRef.current) audioCtxRef.current.close();
    };
  }, []);

  // One-time capability check: refuse the broken flow on mobile / Safari /
  // Firefox so the investor isn't pushed into a record-then-fail trap. Pure
  // detection, no logic side-effects.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const ua = navigator.userAgent || "";
    const isMobile = /Mobi|Android|iPhone|iPad|iPod/i.test(ua);
    // Chromium-based desktop browsers expose chrome.runtime when extensions
    // can run. We check mime support too — Firefox doesn't expose chrome.* and
    // Safari doesn't support audio/webm.
    const hasChromeRuntime =
      typeof (window as unknown as { chrome?: { runtime?: unknown } }).chrome !==
        "undefined" &&
      !!(window as unknown as { chrome?: { runtime?: unknown } }).chrome?.runtime;
    const supportsRecorder =
      typeof MediaRecorder !== "undefined" &&
      (MediaRecorder.isTypeSupported("audio/webm") ||
        MediaRecorder.isTypeSupported("audio/mp4"));
    if (isMobile) {
      setUnsupportedReason("mobile");
    } else if (!hasChromeRuntime || !supportsRecorder) {
      setUnsupportedReason("browser");
    }
  }, []);

  // Listen for the extension's content-script handshake. The content script
  // posts {source:"anticipy_ext", type:"present"} after install. If we get
  // it within a couple seconds of an intent we KNOW we sent, we mark the
  // extension as detected — used to suppress the install CTA and to power
  // the "extension isn't running" toast on confirm.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onMsg = (e: MessageEvent) => {
      const d = e.data;
      if (d && typeof d === "object" && d.source === "anticipy_ext") {
        setExtensionDetected(true);
      }
    };
    window.addEventListener("message", onMsg);
    // Fallback: a globals-set tag may already be in place from the content
    // script that ran on first paint.
    try {
      const g = window as unknown as { __anticipy_ext_installed__?: boolean };
      if (g.__anticipy_ext_installed__) setExtensionDetected(true);
    } catch { /* ignore */ }
    return () => window.removeEventListener("message", onMsg);
  }, []);

  // Realtime: surface live agent progress for intents we originated this
  // session. Same channel as the follow-up listener, but a separate
  // postgres_changes filter so we keep the two concerns clean.
  useEffect(() => {
    if (!session) return;
    const channel = supabase
      .channel("anticipy_intents_progress")
      .on(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "postgres_changes" as any,
        { event: "UPDATE", schema: "public", table: "anticipy_intents" },
        (payload: { new: Record<string, unknown> }) => {
          const row = payload.new ?? {};
          const id = String(row.id ?? "");
          const status = String(row.status ?? "");
          const execResult = String(row.execution_result ?? "").trim();
          if (!id) return;
          // Only track intents we know about — never act on someone else's row.
          let known = false;
          setIntents((prev) => {
            known = prev.some((i) => i.id === id);
            return prev;
          });
          if (!known) return;
          let mapped: IntentStatus | null = null;
          let msg = "";
          if (status === "executed") {
            mapped = "done";
            msg = execResult || "Done.";
          } else if (status === "failed") {
            mapped = "failed";
            msg = execResult || "I couldn't finish that one.";
          } else if (status === "confirmed" || status === "running") {
            mapped = "running";
            msg = execResult || "Working on it...";
          }
          if (!mapped) return;
          setIntentProgress((prev) => ({
            ...prev,
            [id]: { status: mapped!, message: msg, updatedAt: Date.now() },
          }));
        }
      )
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [session]);

  // ── Auth handlers ───────────────────────────────────────────────────────────

  const handleAuth = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setAuthError("");
      setAuthSubmitting(true);

      try {
        if (authMode === "reset") {
          const redirectTo =
            typeof window !== "undefined"
              ? `${window.location.origin}/engine`
              : undefined;
          const { error } = await supabase.auth.resetPasswordForEmail(
            authEmail,
            redirectTo ? { redirectTo } : undefined
          );
          if (error) {
            setAuthError("Couldn't send the reset link. Double-check the email and try again.");
          } else {
            setResetSent(true);
          }
        } else if (authMode === "signup") {
          const { error, data } = await supabase.auth.signUp({
            email: authEmail,
            password: authPassword,
          });
          if (error) {
            const lower = error.message.toLowerCase();
            if (lower.includes("already") || lower.includes("registered")) {
              setAuthError("That email is already registered. Try signing in instead.");
            } else if (lower.includes("password")) {
              setAuthError("Password needs to be at least 8 characters.");
            } else {
              setAuthError("Couldn't create the account. Try again in a moment.");
            }
          } else if (!data.session) {
            setAuthSuccess(true);
          }
        } else {
          const { error } = await supabase.auth.signInWithPassword({
            email: authEmail,
            password: authPassword,
          });
          if (error) {
            setAuthError("Incorrect email or password.");
          }
        }
      } finally {
        setAuthSubmitting(false);
      }
    },
    [authMode, authEmail, authPassword]
  );

  const handleSignOut = useCallback(async () => {
    await supabase.auth.signOut();
    reset();
    setSetupDismissed(false);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSetNewPassword = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setAuthError("");
      setAuthSubmitting(true);
      try {
        const { error } = await supabase.auth.updateUser({
          password: newPassword,
        });
        if (error) {
          setAuthError("Couldn't update your password. Try again in a moment.");
        } else {
          setRecoveryUpdated(true);
          setNewPassword("");
        }
      } finally {
        setAuthSubmitting(false);
      }
    },
    [newPassword]
  );

  const exitRecoveryMode = useCallback(async () => {
    // Drop the recovery session — the user is now expected to sign in
    // normally with their new password.
    await supabase.auth.signOut();
    setRecoveryMode(false);
    setRecoveryUpdated(false);
    setNewPassword("");
    setAuthMode("signin");
    setAuthEmail("");
    setAuthPassword("");
  }, []);

  // ── Engine handlers ─────────────────────────────────────────────────────────

  // Tear down all recording resources and null refs so a fresh recording can be started cleanly.
  // Safe to call multiple times.
  const cleanupRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = undefined;
    }
    if (autoAnalyzeTimerRef.current) {
      clearInterval(autoAnalyzeTimerRef.current);
      autoAnalyzeTimerRef.current = undefined;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = 0;
    }
    if (processorRef.current) {
      try { processorRef.current.disconnect(); } catch { /* already disconnected */ }
      processorRef.current = null;
    }
    if (dgSocketRef.current) {
      try {
        if (dgSocketRef.current.readyState === WebSocket.OPEN) {
          dgSocketRef.current.close();
        }
      } catch { /* already closed */ }
      dgSocketRef.current = null;
    }
    if (mediaRecorderRef.current) {
      try {
        if (mediaRecorderRef.current.state !== "inactive") {
          mediaRecorderRef.current.stop();
        }
      } catch { /* already stopped */ }
      mediaRecorderRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => {
        try { t.stop(); } catch { /* already stopped */ }
      });
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      try {
        if (audioCtxRef.current.state !== "closed") {
          audioCtxRef.current.close();
        }
      } catch { /* already closed */ }
      audioCtxRef.current = null;
    }
    analyserRef.current = null;
    chunksRef.current = [];
  }, []);

  const startRecording = useCallback(async () => {
    // Defensive: ensure any prior session's resources are fully torn down before opening new ones
    cleanupRecording();
    try {
      setError("");
      setSegments([]);
      setIntents([]);
      setDuration(0);
      setLiveText("");
      liveSegmentsRef.current = [];
      dgDroppedRef.current = false;

      const { data: { session: authSession } } = await supabase.auth.getSession();
      if (!authSession) throw new Error("Sign in required");
      const authHeaders = { Authorization: `Bearer ${authSession.access_token}` };

      const sessionRes = await fetch("/api/engine/session", {
        method: "POST",
        headers: authHeaders,
      });
      if (!sessionRes.ok) throw new Error("network");
      const sessionData = await sessionRes.json();
      sessionIdRef.current = sessionData.sessionId;

      const keyRes = await fetch("/api/engine/deepgram-key", { headers: authHeaders });
      if (!keyRes.ok) throw new Error("network");
      const keyData = await keyRes.json();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 },
      });
      streamRef.current = stream;

      // Older Safari rejects non-default sample rates; fall back to the
      // browser default and let the streaming endpoint resample.
      let audioCtx: AudioContext;
      try {
        audioCtx = new AudioContext({ sampleRate: 16000 });
      } catch {
        audioCtx = new AudioContext();
      }
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateLevel = () => {
        analyser.getByteFrequencyData(dataArray);
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
        setAudioLevel(avg / 128);
        animFrameRef.current = requestAnimationFrame(updateLevel);
      };
      updateLevel();

      const dgParams = new URLSearchParams({
        model: "nova-3",
        diarize: "true",
        punctuate: "true",
        language: "en",
        smart_format: "true",
        interim_results: "true",
        endpointing: "300",
        encoding: "linear16",
        sample_rate: "16000",
        channels: "1",
      });

      const dgWs = new WebSocket(
        `wss://api.deepgram.com/v1/listen?${dgParams}`,
        ["token", keyData.key]
      );
      dgSocketRef.current = dgWs;

      dgWs.onopen = () => {
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;
        source.connect(processor);
        processor.connect(audioCtx.destination);

        processor.onaudioprocess = (e) => {
          if (dgWs.readyState !== WebSocket.OPEN) return;
          const inputData = e.inputBuffer.getChannelData(0);
          const int16 = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            const s = Math.max(-1, Math.min(1, inputData[i]));
            int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          dgWs.send(int16.buffer);
        };
      };

      dgWs.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "Results" && msg.channel) {
            const alt = msg.channel.alternatives?.[0];
            if (!alt) return;

            const isFinal = msg.is_final;
            const transcript = alt.transcript;

            if (isFinal && transcript) {
              const words = alt.words || [];
              if (words.length > 0) {
                let current: TranscriptSegment | null = null;
                const newSegments: TranscriptSegment[] = [];

                for (const w of words) {
                  if (!current || current.speaker_id !== (w.speaker ?? 0)) {
                    if (current) newSegments.push(current);
                    current = {
                      speaker_id: w.speaker ?? 0,
                      start_time: w.start,
                      end_time: w.end,
                      text: w.punctuated_word || w.word,
                    };
                  } else {
                    current.end_time = w.end;
                    current.text += " " + (w.punctuated_word || w.word);
                  }
                }
                if (current) newSegments.push(current);

                liveSegmentsRef.current = [...liveSegmentsRef.current, ...newSegments];
                setSegments([...liveSegmentsRef.current]);
              }
              setLiveText("");
            } else if (transcript) {
              setLiveText(transcript);
            }
          }
        } catch {
          // Ignore parse errors
        }
      };

      dgWs.onerror = () => {
        // Don't surface a scary error. Recording continues — audio chunks
        // are buffered and will be batch-transcribed on stop. Stay quiet
        // and let the on-screen state remain "Listening...".
        dgDroppedRef.current = true;
      };

      dgWs.onclose = (e) => {
        // Code 1000 = normal close (we initiated it on stopRecording).
        // Anything else mid-recording is unexpected — but the MediaRecorder
        // is still capturing, so we keep going and will fall back to
        // batch transcription when the user hits stop.
        if (e.code !== 1000 && mediaRecorderRef.current?.state === "recording") {
          dgDroppedRef.current = true;
        }
      };

      // Pick the first MIME type the browser actually supports. Chrome / Edge
      // do webm/opus. Safari refuses webm entirely and only does mp4.
      const supportedMime = (
        ["audio/webm;codecs=opus", "audio/webm", "audio/mp4;codecs=mp4a.40.2", "audio/mp4"]
          .find((m) => MediaRecorder.isTypeSupported(m))
      ) || "";
      const recorder = new MediaRecorder(stream, {
        mimeType: supportedMime || undefined,
      });
      // Remember it so the batch-transcribe upload uses the right Content-Type
      // and filename. Hardcoding audio/webm here breaks Safari uploads.
      recordedMimeRef.current = supportedMime || recorder.mimeType || "audio/webm";
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.start(1000);
      mediaRecorderRef.current = recorder;
      setState("recording");

      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        setDuration(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);

      // Auto-analyze every 30 seconds so intents surface live during recording
      autoAnalyzeTimerRef.current = setInterval(async () => {
        const currentSegments = liveSegmentsRef.current;
        if (currentSegments.length === 0) return;
        const transcriptStr = currentSegments
          .map((s) => `[Speaker ${s.speaker_id}]: ${s.text}`)
          .join("\n");
        try {
          const { data: { session: s } } = await supabase.auth.getSession();
          if (!s) return;
          const res = await fetch("/api/engine/analyze", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${s.access_token}`,
            },
            body: JSON.stringify({
              sessionId: sessionIdRef.current,
              transcript: transcriptStr,
              timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
              isFinal: false,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            if (data.intents?.length) {
              setIntents((prev) => {
                const existingIds = new Set(prev.map((i) => i.id));
                const newOnes = data.intents.filter((i: Intent) => !existingIds.has(i.id));
                return newOnes.length > 0 ? [...prev, ...newOnes] : prev;
              });
            }
          }
        } catch {
          // Non-fatal — next tick will retry
        }
      }, 30_000);
    } catch (err) {
      setError(friendlyError(err));
      setState("error");
      cleanupRecording();
      // If we already created a session row, mark it ended so it doesn't sit
      // in "recording" status forever and confuse the analyze isFinal guard.
      const orphanedSessionId = sessionIdRef.current;
      if (orphanedSessionId) {
        sessionIdRef.current = "";
        try {
          const { data: { session: authSession } } = await supabase.auth.getSession();
          if (authSession) {
            fetch("/api/engine/session", {
              method: "PATCH",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${authSession.access_token}`,
              },
              body: JSON.stringify({ sessionId: orphanedSessionId, status: "ended" }),
            }).catch(() => { /* best-effort */ });
          }
        } catch { /* best-effort */ }
      }
    }
  }, [cleanupRecording]);

  const stopRecording = useCallback(async () => {
    if (!mediaRecorderRef.current) return;

    setState("processing");
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = undefined;
    }
    if (autoAnalyzeTimerRef.current) {
      clearInterval(autoAnalyzeTimerRef.current);
      autoAnalyzeTimerRef.current = undefined;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = 0;
    }
    setAudioLevel(0);
    setLiveText("");

    if (dgSocketRef.current && dgSocketRef.current.readyState === WebSocket.OPEN) {
      try {
        dgSocketRef.current.send(JSON.stringify({ type: "CloseStream" }));
      } catch { /* socket may have closed mid-call */ }
      await new Promise((r) => setTimeout(r, 1000));
      try { dgSocketRef.current.close(); } catch { /* already closed */ }
    }
    dgSocketRef.current = null;

    if (processorRef.current) {
      try { processorRef.current.disconnect(); } catch { /* already disconnected */ }
      processorRef.current = null;
    }

    const recorder = mediaRecorderRef.current;
    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      try {
        if (recorder.state !== "inactive") recorder.stop();
        else resolve();
      } catch {
        resolve();
      }
    });
    mediaRecorderRef.current = null;

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => {
        try { t.stop(); } catch { /* already stopped */ }
      });
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      try {
        if (audioCtxRef.current.state !== "closed") {
          await audioCtxRef.current.close();
        }
      } catch { /* already closed */ }
      audioCtxRef.current = null;
    }
    analyserRef.current = null;

    const finalSegments = liveSegmentsRef.current;
    // If Deepgram dropped mid-recording, prefer batch transcription so the
    // post-drop audio isn't silently lost. We have the full audio in chunksRef.
    const useBatchTranscribe =
      finalSegments.length === 0 ||
      (dgDroppedRef.current && chunksRef.current.length > 0);

    const { data: { session: authSession } } = await supabase.auth.getSession();
    const authToken = authSession?.access_token;

    if (useBatchTranscribe) {
      setState("transcribing");
      try {
        if (!authToken) throw new Error("Sign in required");
        // Use the actual recorded MIME so Safari (mp4) doesn't get re-tagged
        // as webm — that breaks server-side decode.
        const recordedMime = recordedMimeRef.current || "audio/webm";
        const audioBlob = new Blob(chunksRef.current, { type: recordedMime });
        const ext = recordedMime.includes("mp4") ? "mp4" : "webm";
        const formData = new FormData();
        formData.append("audio", audioBlob, `recording.${ext}`);
        formData.append("sessionId", sessionIdRef.current);

        const transcribeRes = await fetch("/api/engine/transcribe", {
          method: "POST",
          headers: { Authorization: `Bearer ${authToken}` },
          body: formData,
        });
        if (!transcribeRes.ok) throw new Error("network");
        const transcribeData = await transcribeRes.json();

        if (!transcribeData.segments?.length) {
          setState("done");
          setError("We didn't catch any speech. Try speaking a bit closer to the mic.");
          return;
        }

        setSegments(transcribeData.segments);
        await analyzeTranscript(transcribeData.transcript);
      } catch (err) {
        setError(friendlyError(err));
        setState("error");
      }
      return;
    }

    const rows = finalSegments.map((s) => ({
      session_id: sessionIdRef.current,
      speaker_id: s.speaker_id,
      start_time: s.start_time,
      end_time: s.end_time,
      text: s.text,
      is_final: true,
    }));

    if (authToken) {
      fetch("/api/engine/transcribe", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ sessionId: sessionIdRef.current, segments: rows }),
      }).catch(() => {});
    }

    const transcriptStr = finalSegments
      .map((s) => `[Speaker ${s.speaker_id}]: ${s.text}`)
      .join("\n");

    await analyzeTranscript(transcriptStr);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const analyzeTranscript = useCallback(async (transcript: string) => {
    setState("analyzing");
    try {
      const { data: { session: authSession } } = await supabase.auth.getSession();
      if (!authSession) throw new Error("Sign in required");
      const analyzeRes = await fetch("/api/engine/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authSession.access_token}`,
        },
        body: JSON.stringify({
          sessionId: sessionIdRef.current,
          transcript,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }),
      });
      if (!analyzeRes.ok) throw new Error("network");
      const analyzeData = await analyzeRes.json();

      setIntents((prev) => {
        const existingIds = new Set(prev.map((i) => i.id));
        const newOnes = (analyzeData.intents ?? []).filter((i: Intent) => !existingIds.has(i.id));
        return newOnes.length > 0 ? [...prev, ...newOnes] : prev;
      });
      // Clear any stale error from earlier in the recording (e.g. a Deepgram
      // drop) — the analysis succeeded so the prior warning is no longer
      // accurate, otherwise the "Done." state would render with a stale
      // "transcription dropped" message.
      setError("");
      setState("done");
    } catch (err) {
      setError(friendlyError(err));
      setState("error");
    }
  }, []);

  const analyzeManualTranscript = useCallback(async () => {
    if (!manualTranscript.trim()) return;

    setError("");
    setSegments([]);
    setIntents([]);
    setState("processing");

    try {
      const { data: { session: authSession } } = await supabase.auth.getSession();
      if (!authSession) throw new Error("Sign in required");
      const sessionRes = await fetch("/api/engine/session", {
        method: "POST",
        headers: { Authorization: `Bearer ${authSession.access_token}` },
      });
      if (!sessionRes.ok) throw new Error("network");
      const sessionData = await sessionRes.json();
      sessionIdRef.current = sessionData.sessionId;

      const lines = manualTranscript.trim().split("\n");
      const parsedSegments: TranscriptSegment[] = [];
      let time = 0;
      for (const line of lines) {
        const match = line.match(/^\[?(?:Speaker\s*)?(\d+)\]?:\s*(.+)/i);
        if (match) {
          parsedSegments.push({
            speaker_id: parseInt(match[1]),
            start_time: time,
            end_time: time + 2,
            text: match[2].trim(),
          });
          time += 2;
        } else if (line.trim()) {
          parsedSegments.push({
            speaker_id: 0,
            start_time: time,
            end_time: time + 2,
            text: line.trim(),
          });
          time += 2;
        }
      }
      setSegments(parsedSegments);

      await analyzeTranscript(manualTranscript);
    } catch (err) {
      setError(friendlyError(err));
      setState("error");
    }
  }, [manualTranscript, analyzeTranscript]);

  const reset = useCallback(() => {
    cleanupRecording();
    setState("idle");
    setSegments([]);
    setIntents([]);
    setIntentDecisions({});
    setError("");
    setDuration(0);
    setAudioLevel(0);
    setLiveText("");
    setManualTranscript("");
    liveSegmentsRef.current = [];
    sessionIdRef.current = "";
    chunksRef.current = [];
  }, [cleanupRecording]);

  // In-page intent confirmation. Hits the same /api/engine/confirm endpoint
  // the email links use, so the wire stays unchanged.
  const decideIntent = useCallback(
    async (intentId: string, action: "yes" | "no") => {
      // Synchronously gate against double-clicks before any await so a
      // racy second tap can't slip past the React-state flip.
      let alreadyLoading = false;
      setIntentDecisions((prev) => {
        if (prev[intentId] === "loading") {
          alreadyLoading = true;
          return prev;
        }
        return { ...prev, [intentId]: "loading" };
      });
      if (alreadyLoading) return;

      // Optimistically seed the progress card so the page never goes silent
      // between "Yes, do it" and the first Realtime UPDATE from the agent.
      if (action === "yes") {
        setIntentProgress((prev) => ({
          ...prev,
          [intentId]: {
            status: "running",
            message: "Sending to your extension...",
            updatedAt: Date.now(),
          },
        }));
      }

      try {
        const res = await fetch(
          `/api/engine/confirm?intentId=${encodeURIComponent(intentId)}&action=${action}`,
          { method: "GET" }
        );
        // The endpoint returns HTML, not JSON. We only care about ok-ness:
        // any 2xx means the decision was recorded (or the intent was already
        // handled, which is also fine for the user).
        if (!res.ok && res.status !== 404 && res.status !== 410) {
          throw new Error("Confirm failed");
        }
        setIntentDecisions((prev) => ({ ...prev, [intentId]: action }));

        // If we never heard from the extension, give it ~6 seconds and then
        // surface a friendly toast instead of letting the page sit silent.
        if (action === "yes" && !extensionDetected) {
          window.setTimeout(() => {
            setIntentProgress((prev) => {
              const cur = prev[intentId];
              // Only show toast if we're still in the optimistic placeholder
              // (no real agent UPDATE has arrived).
              if (cur && cur.message === "Sending to your extension...") {
                showToast(
                  "Looks like the extension isn't running. Install or open Chrome and try again.",
                  "warn",
                  6500
                );
              }
              return prev;
            });
          }, 6000);
        }
      } catch {
        // Reset so the user can retry — no scary error toast, but a friendly
        // inline retry hint.
        setIntentDecisions((prev) => {
          const next = { ...prev };
          delete next[intentId];
          return next;
        });
        setIntentProgress((prev) => {
          const next = { ...prev };
          delete next[intentId];
          return next;
        });
        showToast("That didn't go through. Tap to try again.", "warn", 5000);
      }
    },
    [extensionDetected, showToast]
  );

  // Clarification loop: wearer typed an answer to the agent's follow-up
  // question. POST it to /api/engine/analyze with `answers_intent_id` set to
  // the prior failed intent — the server merges the prior parameters with the
  // new answer, re-extracts, and emits a fresh intent with missing_slots
  // empty. The extension picks it up via Realtime and re-runs the task.
  const submitFollowUp = useCallback(
    async (intentId: string) => {
      const fu = followUps.find((f) => f.intentId === intentId);
      if (!fu || !fu.answer.trim() || fu.submitting || fu.answered) return;

      setFollowUps((prev) =>
        prev.map((f) =>
          f.intentId === intentId ? { ...f, submitting: true } : f
        )
      );

      try {
        const { data: { session: authSession } } = await supabase.auth.getSession();
        if (!authSession) throw new Error("Sign in required");
        const authHeaders = {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authSession.access_token}`,
        };

        // Spin up a fresh session for the follow-up — the original one is
        // typically already "ended" since it produced a final analysis.
        const sessionRes = await fetch("/api/engine/session", {
          method: "POST",
          headers: authHeaders,
        });
        if (!sessionRes.ok) throw new Error("network");
        const sessionData = await sessionRes.json();
        const followUpSessionId = sessionData.sessionId;

        // Frame the wearer's reply as an explicit answer to the prior
        // question. Including the question in the transcript gives the LLM
        // unambiguous context even if it ignores priorIntent block.
        const transcriptStr =
          `[Anticipy asked the wearer: "${fu.question}"]\n` +
          `[Wearer answers: "${fu.answer.trim()}"]`;

        const analyzeRes = await fetch("/api/engine/analyze", {
          method: "POST",
          headers: authHeaders,
          body: JSON.stringify({
            sessionId: followUpSessionId,
            transcript: transcriptStr,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            answers_intent_id: fu.intentId,
          }),
        });
        if (!analyzeRes.ok) throw new Error("network");
        const analyzeData = await analyzeRes.json();

        // Pick up the newly emitted intent so the wearer sees the merged task
        // appear in the "Ready to run" list (extension also picks it up via
        // Realtime broadcast, independently).
        const newOnes: Intent[] = analyzeData.intents ?? [];
        if (newOnes.length > 0) {
          setIntents((prev) => {
            const existingIds = new Set(prev.map((i) => i.id));
            const filtered = newOnes.filter((i) => !existingIds.has(i.id));
            return filtered.length > 0 ? [...prev, ...filtered] : prev;
          });
        }

        setFollowUps((prev) =>
          prev.map((f) =>
            f.intentId === intentId
              ? { ...f, submitting: false, answered: true }
              : f
          )
        );
      } catch (err) {
        // Keep the input usable so the wearer can retry — never surface raw
        // network or model errors.
        console.warn("Follow-up submit failed:", err);
        setFollowUps((prev) =>
          prev.map((f) =>
            f.intentId === intentId ? { ...f, submitting: false } : f
          )
        );
        setError(friendlyError(err));
      }
    },
    [followUps]
  );

  // Resolve a check-in: 'yes' / 'no' from the wearer, or 'auto' when the
  // 30s countdown elapses. 'yes' / 'no' route through /api/engine/confirm
  // (same path as the standard confirm flow — keeps preference recording
  // and execution unified). 'auto' POSTs /api/engine/auto-proceed which
  // flips the row to auto_proceeded and obeys default_after_timeout.
  const resolveCheckIn = useCallback(
    async (intentId: string, action: "yes" | "no" | "auto") => {
      let alreadyResolved = false;
      setCheckIns((prev) => {
        const cur = prev.find((c) => c.intentId === intentId);
        if (!cur || cur.resolved) {
          alreadyResolved = true;
          return prev;
        }
        const resolved =
          action === "yes" ? "accept" : action === "no" ? "reject" : "auto_proceed";
        return prev.map((c) =>
          c.intentId === intentId ? { ...c, resolved } : c
        );
      });
      if (alreadyResolved) return;

      try {
        if (action === "yes" || action === "no") {
          const res = await fetch(
            `/api/engine/confirm?intentId=${encodeURIComponent(intentId)}&action=${action}`,
            { method: "GET" }
          );
          if (!res.ok && res.status !== 404 && res.status !== 410) {
            throw new Error("confirm failed");
          }
        } else {
          const { data: { session: authSession } } = await supabase.auth.getSession();
          if (!authSession) throw new Error("Sign in required");
          await fetch("/api/engine/auto-proceed", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${authSession.access_token}`,
            },
            body: JSON.stringify({ intentId }),
          });
        }
      } catch (err) {
        console.warn("Check-in resolve failed:", err);
        showToast("Couldn't update that check-in. Try again.", "warn", 5000);
      }
    },
    [showToast]
  );

  // Auto-resolve check-ins whose 30s window elapsed without the wearer
  // clicking yes/no. We keep this in a separate effect (not the tick
  // re-render effect above) so the call only fires once per check-in.
  useEffect(() => {
    if (checkIns.length === 0) return;
    const t = setInterval(() => {
      const now = Date.now();
      checkIns
        .filter(
          (c) =>
            c.resolved === null && now - c.startedAt >= CHECKIN_WINDOW_MS
        )
        .forEach((c) => resolveCheckIn(c.intentId, "auto"));
    }, 500);
    return () => clearInterval(t);
  }, [checkIns, resolveCheckIn]);

  const formatDuration = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  // ── Loading ─────────────────────────────────────────────────────────────────

  if (authLoading) {
    return (
      <div
        style={{
          background: "var(--dark)",
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          className="animate-spin"
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            border: "2px solid var(--dark-border)",
            borderTopColor: "var(--gold)",
          }}
        />
      </div>
    );
  }

  // ── Unsupported environment ─────────────────────────────────────────────────
  // Mobile + Safari/Firefox can't run the extension or (in Safari's case) the
  // mic recorder. Show a clean full-page note instead of the broken flow.

  if (unsupportedReason) {
    const isMobile = unsupportedReason === "mobile";
    return (
      <div
        style={{
          background: "var(--dark)",
          minHeight: "100vh",
          color: "var(--text-on-dark)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px 24px",
        }}
      >
        <a
          href="/"
          className="font-serif"
          style={{
            fontSize: 26,
            color: "var(--text-on-dark)",
            textDecoration: "none",
            marginBottom: 32,
          }}
        >
          Anticipy
        </a>
        <div
          style={{
            maxWidth: 460,
            width: "100%",
            background: "var(--dark-elevated)",
            border: "1px solid var(--dark-border)",
            borderRadius: 16,
            padding: 32,
            textAlign: "center",
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: "50%",
              background: "rgba(200,169,126,0.12)",
              border: "1px solid rgba(200,169,126,0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 20px",
              color: "var(--gold)",
            }}
            aria-hidden
          >
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <rect x="3" y="4" width="16" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 19h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
          <h1
            className="font-serif"
            style={{ fontSize: 22, fontWeight: 400, marginBottom: 12, lineHeight: 1.35 }}
          >
            {isMobile
              ? "Open this on your laptop with Chrome."
              : "Anticipy needs Google Chrome."}
          </h1>
          <p
            style={{
              fontSize: 14,
              color: "var(--text-on-dark-muted)",
              fontWeight: 300,
              lineHeight: 1.65,
              marginBottom: 20,
            }}
          >
            {isMobile
              ? "The agent runs inside a Chrome extension on your real desktop browser. Pop this link open on your Mac or PC to take the demo."
              : "The agent runs inside a Chrome extension. Open this page in Chrome on desktop to record, see actions, and let Anticipy run them for you."}
          </p>
          <a
            href="https://www.google.com/chrome/"
            target="_blank"
            rel="noreferrer"
            style={{
              display: "inline-block",
              padding: "10px 24px",
              background: "var(--gold)",
              color: "var(--dark)",
              borderRadius: 100,
              fontSize: 13,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            Get Chrome
          </a>
        </div>
        <p style={{ marginTop: 32, fontSize: 12, color: "rgba(255,255,255,0.2)" }}>
          &copy; 2026 Anticipy
        </p>
      </div>
    );
  }

  // ── Password recovery screen ────────────────────────────────────────────────
  // Surfaces after the user clicks the reset email and Supabase emits a
  // PASSWORD_RECOVERY event. The session technically exists at this point,
  // but we want to force a password change before continuing.

  if (recoveryMode) {
    return (
      <div
        style={{
          background: "var(--dark)",
          minHeight: "100vh",
          color: "var(--text-on-dark)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "48px 24px 24px",
        }}
      >
        <a
          href="/"
          className="font-serif"
          style={{
            fontSize: 26,
            color: "var(--text-on-dark)",
            textDecoration: "none",
            marginBottom: 48,
          }}
        >
          Anticipy
        </a>

        <div
          style={{
            maxWidth: 420,
            width: "100%",
            margin: "auto 0",
            paddingTop: 24,
            paddingBottom: 24,
          }}
        >
          <div
            style={{
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              borderRadius: 16,
              padding: 28,
            }}
          >
            {recoveryUpdated ? (
              <div style={{ textAlign: "center", padding: "8px 0" }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: "50%",
                    background: "rgba(76,175,80,0.12)",
                    border: "1px solid rgba(76,175,80,0.25)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    margin: "0 auto 16px",
                    fontSize: 20,
                    color: "#4CAF50",
                  }}
                >
                  ✓
                </div>
                <h2 style={{ fontSize: 17, fontWeight: 600, marginBottom: 8 }}>
                  Password updated
                </h2>
                <p
                  style={{
                    fontSize: 14,
                    color: "var(--text-on-dark-muted)",
                    fontWeight: 300,
                    lineHeight: 1.6,
                    marginBottom: 20,
                  }}
                >
                  Your new password is set. Sign in again to continue.
                </p>
                <button
                  onClick={exitRecoveryMode}
                  style={{
                    width: "100%",
                    padding: "11px",
                    background: "var(--gold)",
                    color: "var(--dark)",
                    border: "none",
                    borderRadius: 100,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Back to sign in
                </button>
              </div>
            ) : (
              <>
                <h2
                  className="font-serif"
                  style={{
                    fontSize: 22,
                    fontWeight: 400,
                    marginBottom: 8,
                    textAlign: "center",
                  }}
                >
                  Set a new password
                </h2>
                <p
                  style={{
                    fontSize: 13,
                    color: "var(--text-on-dark-muted)",
                    fontWeight: 300,
                    lineHeight: 1.6,
                    marginBottom: 20,
                    textAlign: "center",
                  }}
                >
                  Choose a new password for{" "}
                  <strong style={{ color: "var(--text-on-dark)" }}>
                    {session?.user.email}
                  </strong>
                  .
                </p>
                <form onSubmit={handleSetNewPassword}>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="New password (8+ characters)"
                    required
                    minLength={8}
                    autoComplete="new-password"
                    autoFocus
                    style={{
                      width: "100%",
                      padding: "10px 12px",
                      background: "rgba(255,255,255,0.05)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 8,
                      color: "var(--text-on-dark)",
                      fontSize: 14,
                      outline: "none",
                      boxSizing: "border-box",
                      marginBottom: 12,
                    }}
                  />
                  {authError && (
                    <p
                      style={{
                        fontSize: 13,
                        color: "#ef4444",
                        marginBottom: 12,
                      }}
                    >
                      {authError}
                    </p>
                  )}
                  <button
                    type="submit"
                    disabled={authSubmitting || newPassword.length < 8}
                    style={{
                      width: "100%",
                      padding: "11px",
                      background: "var(--gold)",
                      color: "var(--dark)",
                      border: "none",
                      borderRadius: 100,
                      fontSize: 14,
                      fontWeight: 600,
                      cursor:
                        authSubmitting || newPassword.length < 8
                          ? "not-allowed"
                          : "pointer",
                      opacity:
                        authSubmitting || newPassword.length < 8 ? 0.6 : 1,
                      transition: "opacity 0.2s",
                    }}
                  >
                    {authSubmitting ? "…" : "Update password"}
                  </button>
                </form>
                <button
                  type="button"
                  onClick={exitRecoveryMode}
                  style={{
                    width: "100%",
                    marginTop: 12,
                    background: "none",
                    border: "none",
                    color: "var(--text-on-dark-muted)",
                    fontSize: 12,
                    cursor: "pointer",
                    textDecoration: "underline",
                  }}
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>

        <p
          style={{
            marginTop: 32,
            fontSize: 12,
            color: "rgba(255,255,255,0.2)",
          }}
        >
          &copy; 2026 Anticipy
        </p>
      </div>
    );
  }

  // ── Auth screen ─────────────────────────────────────────────────────────────

  if (!session) {
    return (
      <div
        style={{
          background: "var(--dark)",
          minHeight: "100vh",
          color: "var(--text-on-dark)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "48px 24px 24px",
        }}
      >
        {/* Logo */}
        <a
          href="/"
          className="font-serif"
          style={{
            fontSize: 26,
            color: "var(--text-on-dark)",
            textDecoration: "none",
            marginBottom: 48,
          }}
        >
          Anticipy
        </a>

        <div
          style={{
            maxWidth: 420,
            width: "100%",
            margin: "auto 0",
            paddingTop: 24,
            paddingBottom: 24,
          }}
        >
          {/* Tagline */}
          <div style={{ textAlign: "center", marginBottom: 36 }}>
            <h1
              className="font-serif"
              style={{
                fontSize: "clamp(22px, 4vw, 28px)",
                fontWeight: 400,
                marginBottom: 12,
                lineHeight: 1.3,
              }}
            >
              Your AI that acts, not just answers.
            </h1>
            <p
              style={{
                fontSize: 15,
                color: "var(--text-on-dark-muted)",
                fontWeight: 300,
                lineHeight: 1.7,
              }}
            >
              Sign in to record a conversation, see the actions Anticipy
              picks up, and connect the Chrome extension that runs them for you.
            </p>
          </div>

          {/* Auth card */}
          <div
            style={{
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              borderRadius: 16,
              padding: 28,
            }}
          >
            {authSuccess || resetSent ? (
              /* Email confirmation / reset link sent */
              <div style={{ textAlign: "center", padding: "8px 0" }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: "50%",
                    background: "rgba(200,169,126,0.12)",
                    border: "1px solid rgba(200,169,126,0.25)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    margin: "0 auto 16px",
                    fontSize: 20,
                    color: "var(--gold)",
                  }}
                >
                  ✓
                </div>
                <h2
                  style={{
                    fontSize: 17,
                    fontWeight: 600,
                    marginBottom: 8,
                  }}
                >
                  Check your email
                </h2>
                <p
                  style={{
                    fontSize: 14,
                    color: "var(--text-on-dark-muted)",
                    fontWeight: 300,
                    lineHeight: 1.6,
                    marginBottom: 20,
                  }}
                >
                  {resetSent ? (
                    <>
                      We sent a password reset link to{" "}
                      <strong style={{ color: "var(--text-on-dark)" }}>
                        {authEmail}
                      </strong>
                      . Click it to choose a new password.
                    </>
                  ) : (
                    <>
                      We sent a confirmation link to{" "}
                      <strong style={{ color: "var(--text-on-dark)" }}>
                        {authEmail}
                      </strong>
                      . Click it to activate your account, then come back here.
                    </>
                  )}
                </p>
                <button
                  onClick={() => {
                    setAuthSuccess(false);
                    setResetSent(false);
                    setAuthMode("signin");
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--gold)",
                    fontSize: 13,
                    cursor: "pointer",
                    textDecoration: "underline",
                  }}
                >
                  Back to sign in
                </button>
              </div>
            ) : (
              <>
                {/* Tab toggle */}
                <div
                  style={{
                    display: "flex",
                    gap: 4,
                    marginBottom: 24,
                    background: "rgba(255,255,255,0.04)",
                    padding: 4,
                    borderRadius: 10,
                  }}
                >
                  {(["signin", "signup"] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => {
                        setAuthMode(mode);
                        setAuthError("");
                      }}
                      style={{
                        flex: 1,
                        padding: "8px",
                        borderRadius: 7,
                        border: "none",
                        cursor: "pointer",
                        fontSize: 13,
                        fontWeight: 500,
                        transition: "all 0.15s",
                        background:
                          authMode === mode ? "var(--dark)" : "transparent",
                        color:
                          authMode === mode
                            ? "var(--text-on-dark)"
                            : "var(--text-on-dark-muted)",
                        boxShadow:
                          authMode === mode
                            ? "0 1px 4px rgba(0,0,0,0.4)"
                            : "none",
                      }}
                    >
                      {mode === "signin" ? "Sign in" : "Create account"}
                    </button>
                  ))}
                </div>

                {/* Form */}
                <form onSubmit={handleAuth}>
                  <div style={{ marginBottom: 10 }}>
                    <input
                      type="email"
                      value={authEmail}
                      onChange={(e) => setAuthEmail(e.target.value)}
                      placeholder="Email"
                      required
                      autoComplete="email"
                      style={{
                        width: "100%",
                        padding: "10px 12px",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: 8,
                        color: "var(--text-on-dark)",
                        fontSize: 14,
                        outline: "none",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>
                  {authMode !== "reset" && (
                    <div style={{ marginBottom: 16 }}>
                      <input
                        type="password"
                        value={authPassword}
                        onChange={(e) => setAuthPassword(e.target.value)}
                        placeholder={
                          authMode === "signup"
                            ? "Password (8+ characters)"
                            : "Password"
                        }
                        required
                        minLength={8}
                        autoComplete={
                          authMode === "signup"
                            ? "new-password"
                            : "current-password"
                        }
                        style={{
                          width: "100%",
                          padding: "10px 12px",
                          background: "rgba(255,255,255,0.05)",
                          border: "1px solid rgba(255,255,255,0.1)",
                          borderRadius: 8,
                          color: "var(--text-on-dark)",
                          fontSize: 14,
                          outline: "none",
                          boxSizing: "border-box",
                        }}
                      />
                    </div>
                  )}
                  {authMode === "signin" && (
                    <div style={{ textAlign: "right", marginBottom: 12 }}>
                      <button
                        type="button"
                        onClick={() => {
                          setAuthMode("reset");
                          setAuthError("");
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--text-on-dark-muted)",
                          fontSize: 12,
                          cursor: "pointer",
                          padding: 0,
                          textDecoration: "underline",
                        }}
                      >
                        Forgot password?
                      </button>
                    </div>
                  )}
                  {authMode === "reset" && (
                    <div style={{ marginBottom: 12 }}>
                      <button
                        type="button"
                        onClick={() => {
                          setAuthMode("signin");
                          setAuthError("");
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--text-on-dark-muted)",
                          fontSize: 12,
                          cursor: "pointer",
                          padding: 0,
                          textDecoration: "underline",
                        }}
                      >
                        ← Back to sign in
                      </button>
                    </div>
                  )}
                  {authMode !== "signin" && authMode !== "reset" && (
                    <div style={{ marginBottom: authError ? 10 : 4 }} />
                  )}
                  {authError && (
                    <p
                      style={{
                        fontSize: 13,
                        color: "#ef4444",
                        marginBottom: 12,
                      }}
                    >
                      {authError}
                    </p>
                  )}
                  <button
                    type="submit"
                    disabled={authSubmitting}
                    style={{
                      width: "100%",
                      padding: "11px",
                      background: "var(--gold)",
                      color: "var(--dark)",
                      border: "none",
                      borderRadius: 100,
                      fontSize: 14,
                      fontWeight: 600,
                      cursor: authSubmitting ? "not-allowed" : "pointer",
                      opacity: authSubmitting ? 0.7 : 1,
                      transition: "opacity 0.2s",
                    }}
                  >
                    {authSubmitting
                      ? "…"
                      : authMode === "signin"
                        ? "Sign in"
                        : authMode === "signup"
                          ? "Create account"
                          : "Send reset link"}
                  </button>
                </form>
              </>
            )}
          </div>

          {/* Hint */}
          {!authSuccess && (
            <p
              style={{
                textAlign: "center",
                marginTop: 20,
                fontSize: 13,
                color: "var(--text-on-dark-muted)",
                fontWeight: 300,
                lineHeight: 1.6,
              }}
            >
              After signing in, you&apos;ll get the native bridge download and
              daemon install steps.
            </p>
          )}
        </div>

        {/* Footer */}
        <p
          style={{
            marginTop: 32,
            fontSize: 12,
            color: "rgba(255,255,255,0.2)",
          }}
        >
          &copy; 2026 Anticipy
        </p>
      </div>
    );
  }

  // ── Engine UI (authenticated) ───────────────────────────────────────────────

  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--dark)", color: "var(--text-on-dark)" }}
    >
      {/* Header */}
      <header
        className="sticky top-0 z-50 px-6 py-4"
        style={{
          background: "rgba(12,12,12,0.85)",
          backdropFilter: "blur(20px)",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div className="max-w-container mx-auto flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3 min-w-0">
            <a href="/" className="font-serif text-[22px] shrink-0">
              Anticipy
            </a>
            <span
              className="text-[11px] font-light tracking-wide-label uppercase px-2 py-0.5 rounded-pill shrink-0"
              style={{
                color: "var(--gold)",
                background: "rgba(200,169,126,0.08)",
                border: "1px solid rgba(200,169,126,0.2)",
              }}
            >
              Engine
            </span>
          </div>
          <div className="flex items-center gap-3 flex-wrap justify-end">
            {setupDismissed && (
              <button
                onClick={() => setSetupDismissed(false)}
                className="text-[12px] px-3 py-1.5 rounded-pill transition-all"
                style={{
                  background: "rgba(200,169,126,0.08)",
                  color: "var(--gold)",
                  border: "1px solid rgba(200,169,126,0.2)",
                  cursor: "pointer",
                }}
                title="Show setup card again"
              >
                Setup
              </button>
            )}
            {!calendarConnected && (
              <a
                href={`/api/auth/google?token=${encodeURIComponent(session.access_token)}`}
                className="text-[12px] px-3 py-1.5 rounded-pill transition-all"
                style={{
                  background: "rgba(200,169,126,0.1)",
                  color: "var(--gold)",
                  border: "1px solid rgba(200,169,126,0.2)",
                  textDecoration: "none",
                }}
              >
                Connect Calendar
              </a>
            )}
            {calendarConnected && (
              <span
                className="text-[12px] flex items-center gap-1.5"
                style={{ color: "#4CAF50" }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "#4CAF50",
                    display: "inline-block",
                  }}
                />
                Calendar linked
              </span>
            )}
            <span
              className="text-[12px] truncate max-w-[180px]"
              style={{ color: "var(--text-on-dark-muted)" }}
              title={session.user.email}
            >
              {session.user.email}
            </span>
            <button
              onClick={handleSignOut}
              style={{
                background: "none",
                border: "none",
                color: "var(--text-on-dark-muted)",
                fontSize: 12,
                cursor: "pointer",
                padding: 0,
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Setup card */}
      {!setupDismissed && (
        <div
          className="px-6 py-4"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
        >
          <div className="max-w-container mx-auto">
            <div
              className="rounded-card p-5"
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid rgba(200,169,126,0.15)",
              }}
            >
              {/* Card header */}
              <div
                className="flex items-center justify-between"
                style={{ marginBottom: 20 }}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span
                    className="text-[11px] uppercase tracking-wide-label"
                    style={{ color: "var(--gold)" }}
                  >
                    Get the extension
                  </span>
                  <span
                    className="text-[11px]"
                    style={{ color: "var(--text-on-dark-muted)" }}
                  >
                    · ~3 minutes · runs in your Chrome
                  </span>
                </div>
                <button
                  onClick={() => setSetupDismissed(true)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-on-dark-muted)",
                    fontSize: 12,
                    cursor: "pointer",
                    padding: "2px 6px",
                  }}
                >
                  Dismiss
                </button>
              </div>

              {/* Steps */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                  gap: 16,
                }}
              >
                {/* Step 1 */}
                <div
                  style={{
                    padding: "14px 16px",
                    borderRadius: 10,
                    background: "rgba(76,175,80,0.06)",
                    border: "1px solid rgba(76,175,80,0.15)",
                  }}
                >
                  <div
                    className="flex items-center gap-2"
                    style={{ marginBottom: 8 }}
                  >
                    <span
                      style={{
                        width: 20,
                        height: 20,
                        borderRadius: "50%",
                        background: "rgba(76,175,80,0.2)",
                        border: "1px solid rgba(76,175,80,0.4)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 11,
                        color: "#4CAF50",
                        flexShrink: 0,
                      }}
                    >
                      ✓
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: "#4CAF50",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                      }}
                    >
                      Signed in
                    </span>
                  </div>
                  <p
                    style={{
                      fontSize: 13,
                      fontWeight: 500,
                      marginBottom: 3,
                    }}
                  >
                    You&apos;re all set
                  </p>
                  <p
                    style={{
                      fontSize: 12,
                      color: "var(--text-on-dark-muted)",
                      fontWeight: 300,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={session.user.email}
                  >
                    {session.user.email}
                  </p>
                </div>

                {/* Step 2 */}
                <div
                  style={{
                    padding: "14px 16px",
                    borderRadius: 10,
                    background: "rgba(200,169,126,0.05)",
                    border: "1px solid rgba(200,169,126,0.15)",
                  }}
                >
                  <div
                    className="flex items-center gap-2"
                    style={{ marginBottom: 8 }}
                  >
                    <span
                      style={{
                        width: 20,
                        height: 20,
                        borderRadius: "50%",
                        background: "rgba(200,169,126,0.15)",
                        border: "1px solid rgba(200,169,126,0.3)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 11,
                        color: "var(--gold)",
                        flexShrink: 0,
                        fontWeight: 600,
                      }}
                    >
                      2
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: "var(--gold)",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                      }}
                    >
                      Download
                    </span>
                  </div>
                  <p
                    style={{
                      fontSize: 13,
                      fontWeight: 500,
                      marginBottom: 10,
                    }}
                  >
                    Get the native bridge
                  </p>
                  <div className="flex items-center gap-2">
                    <a
                      href="/anticipy-extension-v6.zip?v=20260523-v6"
                      download="anticipy-extension-v6.zip"
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "6px 12px",
                        background: "var(--gold)",
                        color: "var(--dark)",
                        borderRadius: 100,
                        fontSize: 12,
                        fontWeight: 600,
                        textDecoration: "none",
                      }}
                    >
                      <svg
                        width="11"
                        height="11"
                        viewBox="0 0 11 11"
                        fill="none"
                      >
                        <path
                          d="M5.5 1v6M2.5 5l3 3 3-3M1 10h9"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      Download v6 bridge
                    </a>
                    <a
                      href="/engine/extension"
                      style={{
                        fontSize: 12,
                        color: "var(--text-on-dark-muted)",
                        textDecoration: "none",
                      }}
                    >
                      Install guide →
                    </a>
                  </div>
                </div>

                {/* Step 3 */}
                <div
                  style={{
                    padding: "14px 16px",
                    borderRadius: 10,
                    background: "rgba(200,169,126,0.05)",
                    border: "1px solid rgba(200,169,126,0.15)",
                  }}
                >
                  <div
                    className="flex items-center gap-2"
                    style={{ marginBottom: 8 }}
                  >
                    <span
                      style={{
                        width: 20,
                        height: 20,
                        borderRadius: "50%",
                        background: "rgba(200,169,126,0.15)",
                        border: "1px solid rgba(200,169,126,0.3)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 11,
                        color: "var(--gold)",
                        flexShrink: 0,
                        fontWeight: 600,
                      }}
                    >
                      3
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: "var(--gold)",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                      }}
                    >
                      Bridge
                    </span>
                  </div>
                  <p
                    style={{
                      fontSize: 13,
                      fontWeight: 500,
                      marginBottom: 8,
                    }}
                  >
                    Run the daemon installer
                  </p>
                  <code
                    style={{
                      display: "inline-block",
                      padding: "5px 10px",
                      background: "rgba(0,0,0,0.3)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 6,
                      fontSize: 12,
                      fontFamily: "monospace",
                      color: "var(--text-on-dark)",
                    }}
                  >
                    bash ~/Downloads/anticipy-v6/DAEMON-INSTALLER/install.sh
                  </code>
                  <p
                    style={{
                      fontSize: 11,
                      color: "var(--text-on-dark-muted)",
                      marginTop: 8,
                      fontWeight: 300,
                    }}
                  >
                    Then load anticipy-v6/EXTENSION-LOAD-THIS-IN-CHROME in
                    Chrome. The popup should say daemon connected.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <main className="max-w-container mx-auto px-6 py-12">
        {/* 30-second Quick Start — only when fully idle and no work has happened */}
        {state === "idle" && segments.length === 0 && intents.length === 0 && (
          <div className="max-w-2xl mx-auto mb-12">
            <div
              className="rounded-card"
              style={{
                background: "rgba(200,169,126,0.04)",
                border: "1px solid rgba(200,169,126,0.15)",
                padding: "20px 24px",
              }}
            >
              <div
                className="text-[11px] uppercase tracking-wide-label mb-3"
                style={{ color: "var(--gold)" }}
              >
                30-second quick start
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                  gap: 14,
                }}
              >
                {[
                  { n: "1", t: "Install daemon", s: "One-time, on this Mac." },
                  { n: "2", t: "Load bridge folder", s: "In your real Chrome." },
                  { n: "3", t: "Press the gold dot, talk", s: "We'll find the actions." },
                ].map((step) => (
                  <div key={step.n} className="flex items-start gap-3">
                    <span
                      style={{
                        width: 22,
                        height: 22,
                        borderRadius: "50%",
                        background: "rgba(200,169,126,0.15)",
                        border: "1px solid rgba(200,169,126,0.35)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 11,
                        fontWeight: 600,
                        color: "var(--gold)",
                        flexShrink: 0,
                      }}
                    >
                      {step.n}
                    </span>
                    <div>
                      <p className="text-[13px] font-medium" style={{ marginBottom: 2 }}>
                        {step.t}
                      </p>
                      <p
                        className="text-[12px] font-light"
                        style={{ color: "var(--text-on-dark-muted)" }}
                      >
                        {step.s}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Record section */}
        <div className="text-center mb-16">
          <h1
            className="font-serif text-section tracking-tight-section mb-4"
            style={{ color: "var(--text-on-dark)" }}
          >
            {state === "idle" && "Start a conversation."}
            {state === "recording" && "Listening..."}
            {(state === "processing" || state === "transcribing") &&
              "Processing..."}
            {state === "analyzing" && "Finding actions..."}
            {state === "done" && "Done."}
            {state === "error" && "Let's try that again."}
          </h1>
          <p
            className="text-[15px] font-light max-w-md mx-auto mb-10"
            style={{ color: "var(--text-on-dark-muted)" }}
          >
            {state === "idle" &&
              "Press record and have a real conversation. Anticipy listens, transcribes, and surfaces every actionable moment."}
            {state === "recording" &&
              (intents.length === 0 && duration >= 30
                ? `Recording ${formatDuration(duration)} · listening for actions`
                : `Recording ${formatDuration(duration)}`)}
            {state === "transcribing" &&
              "Cleaning up your audio..."}
            {state === "analyzing" &&
              "Looking for things you can act on..."}
            {state === "done" && intents.length > 0 &&
              `${intents.length} action${intents.length !== 1 ? "s" : ""} ready. Confirm the ones you want to run.`}
            {state === "done" && intents.length === 0 &&
              "No clear actions in this one. Try a conversation with plans, tasks, or follow-ups."}
            {state === "error" && (error || "Something didn't go through. Give it another sec and try again.")}
          </p>

          {/* Record button — one color per state, subtle audio-reactive ring */}
          {(state === "idle" || state === "recording") && (
            <button
              onClick={state === "idle" ? startRecording : stopRecording}
              aria-label={state === "idle" ? "Start recording" : "Stop recording"}
              className="relative mx-auto block transition-all duration-300"
              style={{
                width: 120,
                height: 120,
                borderRadius: "50%",
                background:
                  state === "recording"
                    ? "rgba(200,169,126,0.18)"
                    : "rgba(200,169,126,0.1)",
                border: `2px solid var(--gold)`,
                cursor: "pointer",
              }}
            >
              {/* Audio-reactive halo (subtle) */}
              <div
                className="absolute inset-0 rounded-full transition-all duration-300 pointer-events-none"
                style={{
                  background:
                    state === "recording"
                      ? `rgba(200,169,126,${0.08 + audioLevel * 0.18})`
                      : "transparent",
                  transform: `scale(${1 + audioLevel * 0.12})`,
                }}
              />
              <div className="absolute inset-0 flex items-center justify-center">
                {state === "recording" ? (
                  // Square stop icon
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 4,
                      background: "var(--gold)",
                    }}
                  />
                ) : (
                  // Solid gold dot — single subtle breathing animation
                  <div
                    className="anticipy-pulse"
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: "50%",
                      background: "var(--gold)",
                    }}
                  />
                )}
              </div>
            </button>
          )}

          {/* Processing — single dot pulse, no spinner clutter */}
          {(state === "processing" ||
            state === "transcribing" ||
            state === "analyzing") && (
            <div className="flex justify-center" aria-live="polite">
              <div
                className="anticipy-pulse"
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  background: "var(--gold)",
                }}
              />
            </div>
          )}

          {/* Done / Error — graceful retry, never a blank screen */}
          {(state === "done" || state === "error") && (
            <button
              onClick={reset}
              className="px-8 py-3 rounded-pill text-[15px] font-medium transition-all"
              style={{ background: "var(--gold)", color: "var(--dark)" }}
            >
              {state === "error" ? "Try again" : "New recording"}
            </button>
          )}

          {/* Friendly soft notice — only show as a quiet line, not red, when in done state */}
          {state === "done" && error && (
            <p
              className="mt-4 text-[13px] font-light"
              style={{ color: "var(--text-on-dark-muted)" }}
            >
              {error}
            </p>
          )}
        </div>

        <style jsx>{`
          @keyframes anticipy-pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.55; transform: scale(0.92); }
          }
          :global(.anticipy-pulse) {
            animation: anticipy-pulse 1.6s ease-in-out infinite;
          }
        `}</style>

        {/* Live transcript during recording — always rendered so the page
            never looks broken in the 1-3s before Deepgram returns its first
            segment. Empty state shows a reassuring placeholder. */}
        {state === "recording" && (
          <div className="max-w-2xl mx-auto mb-8">
            <h2
              className="text-[13px] font-light tracking-wide-label uppercase mb-4"
              style={{ color: "var(--text-on-dark-muted)" }}
            >
              Live Transcript
            </h2>
            <div
              className="rounded-card p-6 space-y-3 max-h-[300px] overflow-y-auto"
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
              }}
            >
              {segments.length === 0 && !liveText ? (
                <div className="flex items-center gap-3" style={{ opacity: 0.7 }}>
                  <span
                    className="anticipy-pulse"
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: "var(--gold)",
                      flexShrink: 0,
                    }}
                  />
                  <span
                    className="text-[14px] font-light"
                    style={{ color: "var(--text-on-dark-muted)" }}
                  >
                    Listening for speech...
                  </span>
                </div>
              ) : (
                <>
                  {segments.map((seg, i) => (
                    <div key={i}>
                      <span
                        className="text-[12px] font-medium mr-2"
                        style={{
                          color: SPEAKER_COLORS[seg.speaker_id % SPEAKER_COLORS.length],
                        }}
                      >
                        {seg.speaker_id === 0 ? "You" : `Speaker ${seg.speaker_id + 1}`}
                      </span>
                      <span className="text-[15px] font-light">{seg.text}</span>
                    </div>
                  ))}
                  {liveText && (
                    <div style={{ opacity: 0.5 }}>
                      <span className="text-[15px] font-light italic">{liveText}</span>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {/* Manual transcript */}
        {state === "idle" && (
          <div className="max-w-2xl mx-auto mb-16">
            <div
              className="rounded-card p-6"
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
              }}
            >
              <p
                className="text-[13px] font-light mb-3 tracking-wide-label uppercase"
                style={{ color: "var(--text-on-dark-muted)" }}
              >
                Or paste a transcript
              </p>
              <textarea
                value={manualTranscript}
                onChange={(e) => setManualTranscript(e.target.value)}
                placeholder={`[Speaker 0]: Hey, want to grab lunch Tuesday?\n[Speaker 1]: Yeah noon works. Sushi place sound good?\n[Speaker 0]: Perfect, let's do it.`}
                rows={6}
                className="w-full bg-transparent text-[15px] font-light resize-none outline-none"
                style={{ color: "var(--text-on-dark)", border: "none" }}
              />
              {manualTranscript.trim() && (
                <button
                  onClick={analyzeManualTranscript}
                  className="mt-4 px-6 py-2.5 rounded-pill text-[14px] font-medium"
                  style={{ background: "var(--gold)", color: "var(--dark)" }}
                >
                  Analyze Conversation
                </button>
              )}
            </div>
          </div>
        )}

        {/* Live intents during recording (from 30s auto-analyze) */}
        {state === "recording" && intents.length > 0 && (
          <div className="max-w-2xl mx-auto mb-8">
            <h2
              className="text-[13px] font-light tracking-wide-label uppercase mb-4"
              style={{ color: "var(--gold)" }}
            >
              Actions detected
            </h2>
            <div className="space-y-3">
              {intents.map((intent) => {
                const style = IMPORTANCE_STYLES[intent.importance] ?? IMPORTANCE_STYLES.low;
                return (
                  <div
                    key={intent.id}
                    className="rounded-card p-4"
                    style={{ background: style.bg, border: `1px solid ${style.border}` }}
                  >
                    <p className="text-[14px] font-medium">{intent.summary_for_user}</p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Results */}
        {state !== "recording" &&
          (segments.length > 0 || intents.length > 0) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 max-w-5xl mx-auto">
              {segments.length > 0 && (
                <div>
                  <h2
                    className="text-[13px] font-light tracking-wide-label uppercase mb-4"
                    style={{ color: "var(--text-on-dark-muted)" }}
                  >
                    Transcript
                  </h2>
                  <div
                    className="rounded-card p-6 space-y-3 max-h-[500px] overflow-y-auto"
                    style={{
                      background: "var(--dark-elevated)",
                      border: "1px solid var(--dark-border)",
                    }}
                  >
                    {segments.map((seg, i) => (
                      <div key={i}>
                        <span
                          className="text-[12px] font-medium mr-2"
                          style={{
                            color:
                              SPEAKER_COLORS[
                                seg.speaker_id % SPEAKER_COLORS.length
                              ],
                          }}
                        >
                          {seg.speaker_id === 0 ? "You" : `Speaker ${seg.speaker_id + 1}`}
                        </span>
                        <span className="text-[15px] font-light">
                          {seg.text}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {intents.length > 0 && (
                <div>
                  <h2
                    className="text-[13px] font-light tracking-wide-label uppercase mb-4"
                    style={{ color: "var(--gold)" }}
                  >
                    Ready to run
                  </h2>
                  <div className="space-y-4">
                    {intents.map((intent) => {
                      const style =
                        IMPORTANCE_STYLES[intent.importance] ??
                        IMPORTANCE_STYLES.low;
                      const decision = intentDecisions[intent.id];
                      const followUp = followUps.find(
                        (f) => f.intentId === intent.id
                      );
                      const checkIn = checkIns.find(
                        (c) => c.intentId === intent.id
                      );
                      const progress = intentProgress[intent.id];
                      const confPct =
                        typeof intent.confidence === "number"
                          ? Math.round(intent.confidence * 100)
                          : null;
                      return (
                        <div
                          key={intent.id}
                          className="rounded-card"
                          style={{
                            background: style.bg,
                            border: `1px solid ${style.border}`,
                            padding: 22,
                          }}
                        >
                          {/* Subtle importance label tag — investor sees WHY
                              the card is tinted instead of just the color. */}
                          <div
                            className="flex items-center gap-2"
                            style={{ marginBottom: 12 }}
                          >
                            <span
                              className="text-[10px] uppercase tracking-wide-label font-semibold px-2 py-0.5 rounded-pill"
                              style={{
                                color: style.border.replace(/0\.\d+\)$/, "0.95)"),
                                background: style.bg,
                                border: `1px solid ${style.border}`,
                                letterSpacing: "0.08em",
                              }}
                            >
                              {style.label}
                            </span>
                            {confPct !== null && (
                              <span
                                className="text-[10px] uppercase tracking-wide-label"
                                style={{
                                  color: "var(--text-on-dark-muted)",
                                  letterSpacing: "0.08em",
                                }}
                              >
                                via voice · {confPct}%
                              </span>
                            )}
                          </div>
                          {/* The natural-language summary is the hero — single
                              clean line, no ellipsis truncation. */}
                          <p
                            className="font-serif"
                            style={{
                              fontSize: 19,
                              lineHeight: 1.4,
                              fontWeight: 400,
                              marginBottom: 14,
                              color: "var(--text-on-dark)",
                              wordBreak: "break-word",
                            }}
                          >
                            {intent.summary_for_user}
                          </p>
                          <p
                            className="text-[13px] font-light italic"
                            style={{
                              color: "var(--text-on-dark-muted)",
                              marginBottom: 18,
                              wordBreak: "break-word",
                            }}
                          >
                            &ldquo;{intent.evidence_quote}&rdquo;
                          </p>

                          {/* Check-in card: rendered when the agent flips
                              status='awaiting_user' on this intent. Yes/No +
                              30s countdown ring; on timeout we POST
                              /api/engine/auto-proceed which honors
                              default_after_timeout. */}
                          {checkIn && (() => {
                            const elapsed = Date.now() - checkIn.startedAt;
                            const remainingMs = Math.max(
                              0,
                              CHECKIN_WINDOW_MS - elapsed
                            );
                            const remainingSec = Math.ceil(remainingMs / 1000);
                            const fraction = Math.max(
                              0,
                              Math.min(1, remainingMs / CHECKIN_WINDOW_MS)
                            );
                            // SVG ring: r=14, circumference 2*pi*14 ~= 87.96
                            const C = 2 * Math.PI * 14;
                            const dash = (1 - fraction) * C;
                            const fallbackLabel =
                              checkIn.defaultAfterTimeout === "yes"
                                ? "We'll go ahead if you don't reply."
                                : "We'll skip it if you don't reply.";
                            return (
                              <div
                                data-testid={`checkin-${intent.id}`}
                                className="rounded-card"
                                style={{
                                  background: "rgba(200,169,126,0.07)",
                                  border: "1px solid rgba(200,169,126,0.32)",
                                  padding: 16,
                                  marginBottom: 14,
                                }}
                              >
                                <div className="flex items-center justify-between flex-wrap gap-3 mb-2">
                                  <div
                                    className="text-[11px] uppercase tracking-wide-label"
                                    style={{ color: "var(--gold)" }}
                                  >
                                    Check in · {remainingSec}s
                                  </div>
                                  {checkIn.resolved === null && (
                                    <svg
                                      width={32}
                                      height={32}
                                      aria-hidden="true"
                                    >
                                      <circle
                                        cx={16}
                                        cy={16}
                                        r={14}
                                        fill="none"
                                        stroke="rgba(200,169,126,0.2)"
                                        strokeWidth={2}
                                      />
                                      <circle
                                        cx={16}
                                        cy={16}
                                        r={14}
                                        fill="none"
                                        stroke="var(--gold)"
                                        strokeWidth={2}
                                        strokeLinecap="round"
                                        strokeDasharray={C}
                                        strokeDashoffset={dash}
                                        transform="rotate(-90 16 16)"
                                        style={{
                                          transition:
                                            "stroke-dashoffset 1s linear",
                                        }}
                                      />
                                    </svg>
                                  )}
                                </div>
                                <p
                                  className="text-[14px]"
                                  style={{
                                    color: "var(--text-on-dark)",
                                    marginBottom: 6,
                                    lineHeight: 1.45,
                                  }}
                                >
                                  {checkIn.question}
                                </p>
                                <p
                                  className="text-[12px] font-light"
                                  style={{
                                    color: "var(--text-on-dark-muted)",
                                    marginBottom: 12,
                                  }}
                                >
                                  {fallbackLabel}
                                </p>
                                {checkIn.resolved === null ? (
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <button
                                      type="button"
                                      onClick={() =>
                                        resolveCheckIn(intent.id, "yes")
                                      }
                                      className="rounded-pill text-[13px] font-semibold px-4 py-2"
                                      style={{
                                        background: "var(--gold)",
                                        color: "var(--dark)",
                                        border: "none",
                                        cursor: "pointer",
                                        minWidth: 80,
                                      }}
                                    >
                                      Yes
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() =>
                                        resolveCheckIn(intent.id, "no")
                                      }
                                      className="rounded-pill text-[13px] font-medium px-4 py-2"
                                      style={{
                                        background: "transparent",
                                        color: "var(--text-on-dark-muted)",
                                        border:
                                          "1px solid rgba(255,255,255,0.18)",
                                        cursor: "pointer",
                                        minWidth: 80,
                                      }}
                                    >
                                      No
                                    </button>
                                  </div>
                                ) : (
                                  <div
                                    className="text-[13px]"
                                    style={{
                                      color: "var(--text-on-dark-muted)",
                                    }}
                                  >
                                    {checkIn.resolved === "accept"
                                      ? "Confirmed."
                                      : checkIn.resolved === "reject"
                                        ? "Skipped."
                                        : "Time's up. Using default."}
                                  </div>
                                )}
                              </div>
                            );
                          })()}

                          {/* Follow-up question rendered inline when the
                              extension's agent reported it needs more info. */}
                          {followUp && !followUp.answered && (
                            <div
                              data-testid={`followup-${intent.id}`}
                              className="rounded-card"
                              style={{
                                background: "rgba(200,169,126,0.07)",
                                border: "1px solid rgba(200,169,126,0.28)",
                                padding: 16,
                                marginBottom: 14,
                              }}
                            >
                              <div
                                className="text-[11px] uppercase tracking-wide-label mb-2"
                                style={{ color: "var(--gold)" }}
                              >
                                Anticipy
                              </div>
                              <p
                                className="text-[14px]"
                                style={{
                                  color: "var(--text-on-dark)",
                                  marginBottom: 12,
                                  lineHeight: 1.45,
                                }}
                              >
                                {followUp.question}
                              </p>
                              <form
                                onSubmit={(e) => {
                                  e.preventDefault();
                                  submitFollowUp(intent.id);
                                }}
                              >
                                <div className="flex items-center gap-2 flex-wrap">
                                  <input
                                    type="text"
                                    value={followUp.answer}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      setFollowUps((prev) =>
                                        prev.map((f) =>
                                          f.intentId === intent.id
                                            ? { ...f, answer: v }
                                            : f
                                        )
                                      );
                                    }}
                                    placeholder="Type your answer…"
                                    disabled={followUp.submitting}
                                    autoFocus
                                    style={{
                                      flex: 1,
                                      minWidth: 0,
                                      padding: "10px 12px",
                                      background: "rgba(0,0,0,0.25)",
                                      border: "1px solid rgba(255,255,255,0.12)",
                                      borderRadius: 8,
                                      color: "var(--text-on-dark)",
                                      fontSize: 14,
                                      outline: "none",
                                    }}
                                  />
                                  <button
                                    type="submit"
                                    disabled={
                                      followUp.submitting ||
                                      !followUp.answer.trim()
                                    }
                                    className="px-4 py-2 rounded-pill text-[13px] font-semibold"
                                    style={{
                                      background: "var(--gold)",
                                      color: "var(--dark)",
                                      border: "none",
                                      cursor:
                                        followUp.submitting ||
                                        !followUp.answer.trim()
                                          ? "not-allowed"
                                          : "pointer",
                                      opacity:
                                        followUp.submitting ||
                                        !followUp.answer.trim()
                                          ? 0.6
                                          : 1,
                                      minWidth: 70,
                                    }}
                                  >
                                    {followUp.submitting ? "…" : "Send"}
                                  </button>
                                </div>
                              </form>
                            </div>
                          )}

                          {followUp && followUp.answered && (
                            <div
                              className="rounded-card text-[13px]"
                              style={{
                                background: "rgba(76,175,80,0.08)",
                                border: "1px solid rgba(76,175,80,0.22)",
                                padding: "10px 14px",
                                marginBottom: 14,
                                color: "#9DD49F",
                              }}
                            >
                              Got it. I&rsquo;ll try again with that.
                            </div>
                          )}

                          {/* Two-button decision row, or post-decision state */}
                          {decision === "yes" ? (
                            (() => {
                              const status = progress?.status ?? "running";
                              const dotColor =
                                status === "done"
                                  ? "#4CAF50"
                                  : status === "failed"
                                    ? "#ef4444"
                                    : "var(--gold)";
                              const headline =
                                status === "done"
                                  ? "Done."
                                  : status === "failed"
                                    ? "Couldn't finish that one."
                                    : "Anticipy is working on this...";
                              return (
                                <div
                                  className="rounded-card"
                                  style={{
                                    background: "rgba(0,0,0,0.18)",
                                    border: "1px solid rgba(255,255,255,0.07)",
                                    padding: "14px 16px",
                                  }}
                                >
                                  <div className="flex items-center gap-3">
                                    <span
                                      className={status === "running" ? "anticipy-pulse" : ""}
                                      style={{
                                        width: 10,
                                        height: 10,
                                        borderRadius: "50%",
                                        background: dotColor,
                                        flexShrink: 0,
                                      }}
                                    />
                                    <p
                                      className="text-[13px]"
                                      style={{ color: "var(--text-on-dark)", fontWeight: 500 }}
                                    >
                                      {headline}
                                    </p>
                                  </div>
                                  {progress?.message &&
                                    progress.message !== "Sending to your extension..." && (
                                      <p
                                        className="text-[12px] font-light"
                                        style={{
                                          color: "var(--text-on-dark-muted)",
                                          marginTop: 6,
                                          paddingLeft: 22,
                                          lineHeight: 1.45,
                                          wordBreak: "break-word",
                                        }}
                                      >
                                        {progress.message}
                                      </p>
                                    )}
                                </div>
                              );
                            })()
                          ) : decision === "no" ? (
                            <div
                              className="text-[13px]"
                              style={{ color: "var(--text-on-dark-muted)" }}
                            >
                              Skipped.
                            </div>
                          ) : (
                            <div className="flex items-center gap-3 flex-wrap">
                              <button
                                onClick={() => decideIntent(intent.id, "yes")}
                                disabled={decision === "loading"}
                                className="rounded-pill transition-all"
                                style={{
                                  padding: "12px 28px",
                                  background: "var(--gold)",
                                  color: "var(--dark)",
                                  border: "none",
                                  fontSize: 15,
                                  fontWeight: 600,
                                  letterSpacing: "0.01em",
                                  cursor: decision === "loading" ? "wait" : "pointer",
                                  opacity: decision === "loading" ? 0.7 : 1,
                                  minWidth: 140,
                                  boxShadow: "0 1px 0 rgba(255,255,255,0.06) inset",
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.filter = "brightness(1.08)";
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.filter = "";
                                }}
                              >
                                {decision === "loading" ? "…" : "Yes, do it"}
                              </button>
                              <button
                                onClick={() => decideIntent(intent.id, "no")}
                                disabled={decision === "loading"}
                                className="rounded-pill transition-all"
                                style={{
                                  padding: "12px 24px",
                                  background: "transparent",
                                  color: "var(--text-on-dark-muted)",
                                  border: "1px solid rgba(255,255,255,0.18)",
                                  fontSize: 15,
                                  fontWeight: 500,
                                  cursor: decision === "loading" ? "wait" : "pointer",
                                  minWidth: 100,
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                                  e.currentTarget.style.color = "var(--text-on-dark)";
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.background = "transparent";
                                  e.currentTarget.style.color = "var(--text-on-dark-muted)";
                                }}
                              >
                                Skip
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Extension-not-installed CTA — only when we haven't
                      heard from the content script. If the extension IS
                      installed, this whole block is gone — clean. */}
                  {!extensionDetected && (
                    <div
                      className="mt-5 rounded-card flex items-start gap-3"
                      style={{
                        background: "rgba(200,169,126,0.05)",
                        border: "1px solid rgba(200,169,126,0.18)",
                        padding: "14px 16px",
                      }}
                    >
                      <span
                        style={{
                          fontSize: 16,
                          lineHeight: 1,
                          color: "var(--gold)",
                          marginTop: 2,
                        }}
                      >
                        ◆
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[13px] font-medium" style={{ marginBottom: 4 }}>
                          No Chrome extension yet?
                        </p>
                        <p
                          className="text-[12px] font-light"
                          style={{ color: "var(--text-on-dark-muted)", marginBottom: 8 }}
                        >
                          Install it once and confirmed actions will run in your real browser.
                        </p>
                        <div className="flex items-center gap-3 flex-wrap">
                          <a
                            href="/anticipy-extension-v6.zip?v=20260523-v6"
                            download="anticipy-extension-v6.zip"
                            className="text-[12px] font-semibold px-3 py-1.5 rounded-pill"
                            style={{
                              background: "var(--gold)",
                              color: "var(--dark)",
                              textDecoration: "none",
                            }}
                          >
                            Install bridge
                          </a>
                          <a
                            href="/engine/extension"
                            className="text-[12px]"
                            style={{
                              color: "var(--text-on-dark-muted)",
                              textDecoration: "none",
                            }}
                          >
                            Install guide →
                          </a>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

      </main>

      {/* Footer */}
      <footer
        className="px-6 py-8 mt-20"
        style={{ borderTop: "1px solid var(--dark-border)" }}
      >
        <div className="max-w-container mx-auto flex items-center justify-between">
          <p className="text-[13px]" style={{ color: "var(--text-on-dark-muted)" }}>
            &copy; 2026 Anticipy.
          </p>
          <div className="flex items-center gap-4">
            <a
              href="/engine/extension"
              className="text-[13px]"
              style={{ color: "var(--text-on-dark-muted)", textDecoration: "none" }}
            >
              Extension guide
            </a>
            <a
              href="/anticipy-extension-v6.zip?v=20260523-v6"
              download="anticipy-extension-v6.zip"
              className="text-[13px]"
              style={{ color: "var(--gold)", textDecoration: "none" }}
            >
              Download bridge
            </a>
          </div>
        </div>
      </footer>

      {/* Toast — single source of polite, ephemeral feedback. Never shows
          raw error strings; copy is curated upstream via showToast. */}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "fixed",
            left: "50%",
            bottom: 28,
            transform: "translateX(-50%)",
            zIndex: 60,
            maxWidth: "min(560px, calc(100vw - 32px))",
            background: "rgba(20,20,20,0.96)",
            border: `1px solid ${
              toast.kind === "warn"
                ? "rgba(200,169,126,0.45)"
                : "rgba(255,255,255,0.12)"
            }`,
            color: "var(--text-on-dark)",
            borderRadius: 14,
            padding: "12px 18px",
            fontSize: 13,
            lineHeight: 1.5,
            boxShadow: "0 8px 32px rgba(0,0,0,0.55)",
            backdropFilter: "blur(20px)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background:
                toast.kind === "warn" ? "var(--gold)" : "rgba(255,255,255,0.5)",
              flexShrink: 0,
            }}
          />
          <span style={{ flex: 1 }}>{toast.text}</span>
          <button
            onClick={() => setToast(null)}
            aria-label="Dismiss"
            style={{
              background: "none",
              border: "none",
              color: "var(--text-on-dark-muted)",
              cursor: "pointer",
              fontSize: 16,
              padding: "0 4px",
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
