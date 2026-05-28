"use client";

/**
 * Cold-start onboarding path 3c: show me your life.
 *
 * The wearer drags an audio recording of their day into the dropzone.
 * The browser streams the file to the local Mac engine, which runs
 * parakeet-mlx locally (audio never leaves the device) at
 * chunk_duration=120s, overlap_duration=15s and then asks the broker
 * to extract a UserProfile from the transcript. The page renders
 * exactly what the engine reports back: no fabricated success.
 *
 * Brand: same charcoal / cream / gold and the same serif headers as
 * src/app/onboarding/chat. No glass, no purple.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

const LOCAL_ENGINE = "http://127.0.0.1:8731";

type Phase =
  | "welcome"
  | "preflight"
  | "uploading"
  | "transcribing"
  | "extracting"
  | "done"
  | "error";

type AudioProfile = {
  name?: string;
  role_title?: string;
  people?: Record<string, string>;
  do_not_touch?: string[];
  recurring_topics?: string[];
  well_populated?: boolean;
};

export default function OnboardingAudioPage() {
  const [phase, setPhase] = useState<Phase>("welcome");
  const [statusLine, setStatusLine] = useState<string>("");
  const [errorLine, setErrorLine] = useState<string>("");
  const [profile, setProfile] = useState<AudioProfile | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [transcriptChars, setTranscriptChars] = useState<number>(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    // Eager session check so the page can tell the wearer if they need
    // to sign in before the local engine will be reachable.
    (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        if (!data.session) {
          setStatusLine("Sign in on the main page first so the engine knows who you are.");
        }
      } catch {
        // The page is usable without auth; the engine will surface its
        // own error if a session is required.
      }
    })();
  }, []);

  const submitFile = useCallback(async (file: File) => {
    setErrorLine("");
    setProfile(null);
    setTranscriptChars(0);
    setPhase("preflight");
    setStatusLine("Asking the engine if it is ready for a long recording.");
    try {
      const probe = await fetch(`${LOCAL_ENGINE}/health`, { cache: "no-store" });
      if (!probe.ok) {
        throw new Error("The local engine on this Mac is not reachable.");
      }
    } catch (e) {
      setPhase("error");
      setErrorLine(
        "Open Anticipy on this Mac first so the local engine is running, then try again.",
      );
      return;
    }
    setPhase("uploading");
    setStatusLine("Sending your audio to the engine on this Mac.");
    try {
      const res = await fetch(`${LOCAL_ENGINE}/api/onboarding/from_audio`, {
        method: "POST",
        headers: {
          "Content-Type":
            file.type && file.type.length > 0 ? file.type : "audio/mpeg",
        },
        body: file,
      });
      const data: {
        ok?: boolean;
        error?: string;
        profile?: AudioProfile;
        transcript_chars?: number;
      } = await res.json();
      if (!res.ok || !data.ok) {
        setPhase("error");
        setErrorLine(
          data?.error || "The engine could not finish extracting a profile.",
        );
        return;
      }
      setPhase("done");
      setProfile(data.profile || null);
      setTranscriptChars(data.transcript_chars || 0);
      setStatusLine("");
    } catch (e) {
      setPhase("error");
      setErrorLine(
        e instanceof Error ? e.message : "Upload failed for an unknown reason.",
      );
    }
  }, []);

  const onPick = useCallback(() => {
    inputRef.current?.click();
  }, []);

  return (
    <div
      className="min-h-screen font-sans"
      style={{
        backgroundColor: "#0C0C0C",
        color: "#F5F0EB",
        backgroundImage:
          "radial-gradient(60rem 40rem at 50% -10%, rgba(200,169,126,0.10), transparent 70%)",
      }}
    >
      <main className="px-8 md:px-20 py-12 max-w-[820px] mx-auto">
        <p
          className="text-xs uppercase tracking-[0.26em] mb-4"
          style={{ color: "#C8A97E" }}
        >
          Onboarding
        </p>
        <h1
          className="text-4xl md:text-5xl leading-tight tracking-tight"
          style={{ fontFamily: "var(--font-dm-serif), Georgia, serif" }}
        >
          Show me your life.
        </h1>
        <p
          className="mt-6 text-base leading-relaxed max-w-[42rem]"
          style={{ color: "rgba(245,240,235,0.62)" }}
        >
          Drag in an audio recording of your day, up to twenty-four hours.
          Anticipy transcribes it on this Mac with parakeet-mlx in chunks of
          two minutes that overlap fifteen seconds, then writes a structured
          profile so it can resolve who you mean later. The audio never leaves
          your device.
        </p>

        <div
          role="button"
          tabIndex={0}
          onClick={onPick}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onPick();
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f) submitFile(f);
          }}
          className="mt-10 cursor-pointer rounded-2xl border border-dashed px-8 py-12 text-center transition"
          style={{
            borderColor: dragOver ? "#C8A97E" : "rgba(245,240,235,0.18)",
            backgroundColor: dragOver
              ? "rgba(200,169,126,0.06)"
              : "rgba(245,240,235,0.02)",
          }}
        >
          <p
            className="text-base"
            style={{ color: "rgba(245,240,235,0.85)" }}
          >
            Drop an audio file here or click to pick one.
          </p>
          <p
            className="mt-3 text-xs"
            style={{ color: "rgba(245,240,235,0.40)" }}
          >
            MP3, WAV, AIFF, M4A, FLAC are all fine. Up to twenty-four hours.
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="audio/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) submitFile(f);
          }}
        />

        {(phase === "preflight" ||
          phase === "uploading" ||
          phase === "transcribing" ||
          phase === "extracting") && (
          <p
            className="mt-8 text-sm leading-relaxed"
            style={{ color: "rgba(245,240,235,0.55)" }}
          >
            Listening to your week. {statusLine}
          </p>
        )}

        {phase === "error" && (
          <p
            className="mt-8 text-sm leading-relaxed"
            style={{ color: "#C98A6E" }}
          >
            {errorLine}
          </p>
        )}

        {phase === "done" && profile && (
          <div
            className="mt-10 rounded-2xl p-6"
            style={{
              backgroundColor: "rgba(245,240,235,0.04)",
              border: "1px solid rgba(245,240,235,0.10)",
            }}
          >
            <p
              className="text-xs uppercase tracking-[0.22em]"
              style={{ color: "#C8A97E" }}
            >
              Your profile
            </p>
            <h2
              className="mt-2 text-2xl"
              style={{ fontFamily: "var(--font-dm-serif), Georgia, serif" }}
            >
              {profile.name
                ? `Good to meet you, ${profile.name.split(" ")[0]}.`
                : "Good to meet you."}
            </h2>
            <p
              className="mt-2 text-xs"
              style={{ color: "rgba(245,240,235,0.45)" }}
            >
              Transcribed {transcriptChars.toLocaleString()} characters from
              the recording. Stored on this Mac, used to resolve who you mean.
            </p>
            {profile.people && Object.keys(profile.people).length > 0 && (
              <ul className="mt-6 space-y-2 text-sm">
                {Object.entries(profile.people).map(([k, v]) => (
                  <li key={k}>
                    <span style={{ color: "rgba(245,240,235,0.55)" }}>
                      {k}
                    </span>{" "}
                    <span style={{ color: "#F5F0EB" }}>{v}</span>
                  </li>
                ))}
              </ul>
            )}
            {profile.do_not_touch && profile.do_not_touch.length > 0 && (
              <p
                className="mt-6 text-xs"
                style={{ color: "rgba(245,240,235,0.55)" }}
              >
                Do not touch: {profile.do_not_touch.join(", ")}.
              </p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
