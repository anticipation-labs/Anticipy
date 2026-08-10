"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ease } from "@/lib/animation";

type State = "idle" | "recording" | "working" | "error";

/**
 * "Or just talk" — records, transcribes server-side, appends the text.
 *
 * Deliberately NOT the browser's SpeechRecognition API. That is dead in
 * Firefox, unreliable in continuous mode on iOS, auto-stops after ~15s of
 * silence, and ships the audio to Google or Apple regardless — so it is
 * neither the compatible option nor the private one.
 *
 * Two iOS-specific details that otherwise produce silent failures:
 *  - `timeslice` on start() so chunks accumulate as they arrive. Safari has a
 *    long-standing bug where relying on the final ondataavailable at stop()
 *    yields an empty blob.
 *  - Format is negotiated, preferring webm/opus (Safari 18.4+ supports it).
 *    Older Safari falls back to fragmented MP4, which the server routes to a
 *    different transcriber because Whisper truncates it to the first few
 *    seconds while still reporting success.
 *
 * The transcript lands in the same editable textarea, so the applicant
 * proofreads it. That is why raw accuracy matters less here than latency.
 */
export function VoiceInput({
  onText,
  disabled,
}: {
  onText: (text: string) => void;
  disabled?: boolean;
}) {
  const [state, setState] = useState<State>("idle");
  const [msg, setMsg] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (state !== "recording") return;
    const t = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, [state]);

  // Release the microphone if this unmounts mid-recording — otherwise the
  // browser keeps showing a recording indicator on a screen that is gone.
  useEffect(
    () => () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    },
    []
  );

  const pickMime = (): string => {
    const prefs = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/aac",
    ];
    for (const m of prefs) {
      if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(m)) return m;
    }
    return "";
  };

  const start = async () => {
    setMsg(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setState("error");
      setMsg("This browser can't record. Type it instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = pickMime();
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => void send(rec.mimeType || mime || "audio/webm");
      // 1s timeslice — see the iOS note above.
      rec.start(1000);
      recRef.current = rec;
      setSeconds(0);
      setState("recording");
    } catch {
      setState("error");
      setMsg("Microphone access was blocked. You can type instead.");
    }
  };

  const stop = () => {
    recRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setState("working");
  };

  const send = async (mime: string) => {
    const blob = new Blob(chunksRef.current, { type: mime });
    chunksRef.current = [];
    if (blob.size < 1200) {
      setState("idle");
      setMsg("That was too short to hear.");
      return;
    }
    try {
      const fd = new FormData();
      fd.set("audio", blob, mime.includes("mp4") ? "a.m4a" : "a.webm");
      const res = await fetch("/api/transcribe", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.text) {
        setState("error");
        setMsg(data.error || "Couldn't transcribe that. Type it instead.");
        return;
      }
      onText(data.text as string);
      setState("idle");
      setMsg(null);
    } catch {
      setState("error");
      setMsg("Network problem. Type it instead.");
    }
  };

  const label =
    state === "recording"
      ? `Stop · ${String(Math.floor(seconds / 60)).padStart(1, "0")}:${String(seconds % 60).padStart(2, "0")}`
      : state === "working"
        ? "Transcribing…"
        : "Or just talk";

  return (
    <div style={{ marginTop: 12 }}>
      <button
        type="button"
        disabled={disabled || state === "working"}
        onClick={state === "recording" ? stop : start}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 9,
          background: "transparent",
          border: `1px solid ${state === "recording" ? "var(--danger)" : "var(--rule)"}`,
          color: state === "recording" ? "var(--danger)" : "var(--ink-2)",
          borderRadius: 100,
          padding: "8px 16px",
          fontSize: 13,
          cursor: state === "working" ? "default" : "pointer",
          fontFamily: "inherit",
          transition: "all 200ms ease",
        }}
      >
        {state === "recording" ? (
          <motion.span
            animate={{ opacity: [1, 0.25, 1] }}
            transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
            style={{ width: 8, height: 8, borderRadius: 99, background: "var(--danger)" }}
          />
        ) : (
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 99,
              background: "var(--ink-2)",
              opacity: 0.6,
            }}
          />
        )}
        {label}
      </button>

      <AnimatePresence>
        {msg && (
          <motion.p
            initial={{ opacity: 0, y: -3 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22, ease }}
            style={{ color: "var(--ink-2)", fontSize: 12, marginTop: 8 }}
          >
            {msg}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
