"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ease } from "@/lib/animation";
import { CalendarEmbed } from "./CalendarEmbed";
import { LocationInput } from "./LocationInput";
import { VoiceInput } from "./VoiceInput";
import { Flash } from "./Flash";
import { suggestEmail } from "@/lib/email-check";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const URL_RE = /^https?:\/\/[^\s.]+\.[^\s]{2,}$/i;
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXT = /\.(pdf|doc|docx|png|jpe?g|webp|heic|heif|gif|mp4|mov)$/i;

type Status = "idle" | "submitting" | "success";
type Errors = Partial<Record<string, string>>;

/** One thing per screen. There is no third thing. */
const SCREENS = [
  "Who you are",
  "Where you are",
  "The first thing",
  "Anything else",
  "The second thing",
  "Anything else",
  "Anything to show",
] as const;

const rule = (focused: boolean, invalid: boolean): React.CSSProperties => ({
  background: "transparent",
  border: "none",
  borderBottom: `1px solid ${invalid ? "#C97E7E" : focused ? "var(--gold)" : "var(--dark-border)"}`,
  color: "var(--text-on-dark)",
  padding: "10px 0 12px",
  fontSize: 18,
  width: "100%",
  outline: "none",
  transition: "border-color 260ms ease",
  fontFamily: "inherit",
  borderRadius: 0,
});

function Q({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="font-serif"
      style={{
        fontSize: "clamp(27px, 3.8vw, 40px)",
        lineHeight: 1.14,
        letterSpacing: "-0.02em",
        margin: "0 0 12px",
        color: "var(--text-on-dark)",
      }}
    >
      {children}
    </h2>
  );
}

function Sub({ children }: { children: React.ReactNode }) {
  return (
    <p
      style={{
        color: "var(--text-on-dark-muted)",
        fontSize: 15,
        lineHeight: 1.65,
        margin: "0 0 32px",
        maxWidth: 520,
      }}
    >
      {children}
    </p>
  );
}

function Err({ msg }: { msg?: string }) {
  return (
    <AnimatePresence>
      {msg && (
        <motion.p
          role="alert"
          initial={{ opacity: 0, y: -3 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22, ease }}
          style={{ color: "#C97E7E", fontSize: 13, marginTop: 9 }}
        >
          {msg}
        </motion.p>
      )}
    </AnimatePresence>
  );
}

export function BuildForm() {
  const [screen, setScreen] = useState(0);
  const [flashing, setFlashing] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [emailFix, setEmailFix] = useState<string | null>(null);
  const [location, setLocation] = useState("");
  const [thing1, setThing1] = useState("");
  const [thing1Extra, setThing1Extra] = useState("");
  const [thing2, setThing2] = useState("");
  const [thing2Extra, setThing2Extra] = useState("");
  const [resumeLink, setResumeLink] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [spoken, setSpoken] = useState<Set<string>>(new Set());

  const fileRef = useRef<HTMLInputElement>(null);
  const startedAt = useRef(0);
  const paneRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  useEffect(() => {
    if (status === "success") return;
    const t = window.setTimeout(() => {
      paneRef.current?.querySelector<HTMLElement>("input, textarea")?.focus();
    }, 420);
    return () => window.clearTimeout(t);
  }, [screen, status]);

  const bind = (k: string) => ({
    onFocus: () => setFocus(k),
    onBlur: () => setFocus((f) => (f === k ? null : f)),
  });

  const validate = useCallback(
    (s: number): Errors => {
      const e: Errors = {};
      if (s === 0) {
        if (!name.trim()) e.name = "Required.";
        if (!email.trim()) e.email = "Required.";
        else if (!EMAIL_RE.test(email.trim()))
          e.email = "That doesn't look like an email address.";
      }
      if (s === 1 && !location.trim()) e.location = "Required.";
      if (s === 2 && !thing1.trim()) e.thing1 = "Tell us one thing you built.";
      if (s === 4 && !thing2.trim()) e.thing2 = "One more.";
      if (s === 6 && resumeLink.trim() && !URL_RE.test(resumeLink.trim()))
        e.resumeLink = "That doesn't look like a link.";
      return e;
    },
    [name, email, location, thing1, thing2, resumeLink]
  );

  /** Advance with the flash between screens. */
  const advance = () => {
    const e = validate(screen);
    setErrors(e);
    if (Object.keys(e).length) return;

    if (screen < SCREENS.length - 1) {
      setFlashing(true);
      // Swap the screen mid-flash so the change is hidden inside the beat
      // rather than competing with it.
      window.setTimeout(() => setScreen((s) => s + 1), 150);
      window.setTimeout(() => setFlashing(false), 360);
    } else {
      void submit();
    }
  };

  const back = () => {
    setErrors({});
    setFlashing(true);
    window.setTimeout(() => setScreen((s) => Math.max(0, s - 1)), 150);
    window.setTimeout(() => setFlashing(false), 360);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Enter") return;
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "TEXTAREA" && !(e.metaKey || e.ctrlKey)) return;
    // The location combobox handles its own Enter and stops propagation of
    // the default; if it bubbles here the list was closed.
    e.preventDefault();
    advance();
  };

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const next: File[] = [];
    let rejected = "";
    for (const f of Array.from(list)) {
      if (!ALLOWED_EXT.test(f.name)) {
        rejected = "Some files were the wrong type.";
        continue;
      }
      if (f.size > MAX_FILE_BYTES) {
        rejected = "Some files were over 10 MB.";
        continue;
      }
      next.push(f);
    }
    setErrors((p) => ({ ...p, files: rejected || undefined }));
    setFiles((prev) => [...prev, ...next].slice(0, 6));
  };

  const markSpoken = (k: string) => setSpoken((s) => new Set(s).add(k));

  const submit = async () => {
    setServerError(null);
    setStatus("submitting");

    const fd = new FormData();
    fd.set("name", name.trim());
    fd.set("email", email.trim());
    fd.set("location", location.trim());
    fd.set("thing1", thing1.trim());
    fd.set("thing1Extra", thing1Extra.trim());
    fd.set("thing2", thing2.trim());
    fd.set("thing2Extra", thing2Extra.trim());
    fd.set("resumeLink", resumeLink.trim());
    fd.set("spokenFields", Array.from(spoken).join(","));
    fd.set("startedAt", String(startedAt.current));
    fd.set("company", "");
    files.forEach((f) => fd.append("files", f));

    const qs = new URLSearchParams(window.location.search);
    fd.set("utmSource", qs.get("utm_source") ?? "");
    fd.set("utmMedium", qs.get("utm_medium") ?? "");
    fd.set("utmCampaign", qs.get("utm_campaign") ?? "");
    fd.set("referrer", document.referrer || "");
    fd.set("landingPath", window.location.pathname);

    try {
      const res = await fetch("/api/applications", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setStatus("idle");
        setServerError(data.error || "Something went wrong. Try again.");
        return;
      }
      setFlashing(true);
      window.setTimeout(() => setStatus("success"), 160);
      window.setTimeout(() => setFlashing(false), 380);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      setStatus("idle");
      setServerError("Network error. Try again.");
    }
  };

  // ── Success ──────────────────────────────────────────────────
  if (status === "success") {
    return (
      <>
        <Flash active={flashing} />
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, ease }}
        >
          <motion.div
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.85, ease, delay: 0.1 }}
            style={{ height: 1, background: "var(--gold)", transformOrigin: "left", marginBottom: 32 }}
          />
          <motion.h2
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease, delay: 0.28 }}
            className="font-serif"
            style={{
              fontSize: "clamp(28px, 4vw, 42px)",
              lineHeight: 1.15,
              letterSpacing: "-0.02em",
              margin: 0,
            }}
          >
            Got it. If the work is a fit, Omar will reach out.
          </motion.h2>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease, delay: 0.5 }}
          >
            <p style={{ color: "var(--text-on-dark)", fontSize: 17, lineHeight: 1.75, margin: "22px 0 0", maxWidth: 560 }}>
              You just wrote up two things you actually built. That earns more
              than a form reply.
            </p>
            <p style={{ color: "var(--text-on-dark-muted)", fontSize: 16, lineHeight: 1.75, margin: "14px 0 0", maxWidth: 560 }}>
              Below is Omar&apos;s own calendar — the founder, not a recruiter
              and not a screening round. Take the earliest slot that works.
            </p>
            <CalendarEmbed />
          </motion.div>
        </motion.div>
      </>
    );
  }

  const last = screen === SCREENS.length - 1;

  return (
    <div onKeyDown={onKeyDown}>
      <Flash active={flashing} />

      {/* Progress */}
      <div style={{ marginBottom: 44 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 11 }}>
          <span className="tracking-wide-label" style={{ fontSize: 11, textTransform: "uppercase", color: "var(--gold)" }}>
            {String(screen + 1).padStart(2, "0")} — {SCREENS[screen]}
          </span>
          <span style={{ fontSize: 11, color: "#5A5A5A" }}>{String(SCREENS.length).padStart(2, "0")}</span>
        </div>
        <div style={{ height: 1, background: "var(--dark-border)", position: "relative" }}>
          <motion.div
            animate={{ scaleX: (screen + 1) / SCREENS.length }}
            initial={false}
            transition={{ duration: 0.55, ease }}
            style={{ position: "absolute", inset: 0, background: "var(--gold)", transformOrigin: "left" }}
          />
        </div>
      </div>

      <div style={{ position: "relative", minHeight: 300 }}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={screen}
            ref={paneRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease }}
          >
            {screen === 0 && (
              <>
                <Q>First — who are you?</Q>
                <Sub>Name and email. That&apos;s the whole screen.</Sub>
                <div style={{ display: "grid", gap: 30 }}>
                  <div>
                    <input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Your name"
                      autoComplete="name"
                      aria-label="Your name"
                      style={rule(focus === "name", !!errors.name)}
                      {...bind("name")}
                    />
                    <Err msg={errors.name} />
                  </div>
                  <div>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        setEmailFix(null);
                      }}
                      onBlur={() => {
                        setFocus(null);
                        // Catch the typo before they submit — this is where
                        // nearly all of the real-world win is. An MX check
                        // would not help: gmial.com has a live MX record.
                        const s = suggestEmail(email.trim());
                        setEmailFix(s);
                      }}
                      onFocus={() => setFocus("email")}
                      placeholder="Email"
                      autoComplete="email"
                      aria-label="Email"
                      style={rule(focus === "email", !!errors.email)}
                    />
                    <Err msg={errors.email} />
                    {emailFix && (
                      <button
                        type="button"
                        onClick={() => {
                          setEmail(emailFix);
                          setEmailFix(null);
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--gold)",
                          fontSize: 13,
                          padding: "10px 0 0",
                          cursor: "pointer",
                          fontFamily: "inherit",
                        }}
                      >
                        Did you mean {emailFix}?
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}

            {screen === 1 && (
              <>
                <Q>Where are you?</Q>
                <Sub>Start typing — we&apos;ll find it.</Sub>
                <LocationInput
                  value={location}
                  onChange={(v) => {
                    setLocation(v);
                    setErrors((p) => ({ ...p, location: undefined }));
                  }}
                  invalid={!!errors.location}
                  onEnterWhenClosed={advance}
                />
                <Err msg={errors.location} />
              </>
            )}

            {screen === 2 && (
              <>
                <Q>Tell us about one thing you built.</Q>
                <Sub>
                  What was it, what was actually yours, and where can we see it?
                  Type it, or press the button and just talk.
                </Sub>
                <textarea
                  value={thing1}
                  onChange={(e) => setThing1(e.target.value)}
                  rows={6}
                  aria-label="One thing you built"
                  style={{ ...rule(focus === "t1", !!errors.thing1), fontSize: 16, lineHeight: 1.65, resize: "vertical" }}
                  {...bind("t1")}
                />
                <VoiceInput
                  onText={(t) => {
                    setThing1((v) => (v ? `${v} ${t}` : t));
                    markSpoken("thing1");
                  }}
                />
                <Err msg={errors.thing1} />
              </>
            )}

            {screen === 3 && (
              <>
                <Q>Anything else about it?</Q>
                <Sub>Optional. Skip if you said it all.</Sub>
                <textarea
                  value={thing1Extra}
                  onChange={(e) => setThing1Extra(e.target.value)}
                  rows={5}
                  aria-label="Anything else about the first thing"
                  style={{ ...rule(focus === "t1x", false), fontSize: 16, lineHeight: 1.65, resize: "vertical" }}
                  {...bind("t1x")}
                />
                <VoiceInput
                  onText={(t) => {
                    setThing1Extra((v) => (v ? `${v} ${t}` : t));
                    markSpoken("thing1Extra");
                  }}
                />
              </>
            )}

            {screen === 4 && (
              <>
                <Q>And one more.</Q>
                <Sub>A second thing you built. Same question.</Sub>
                <textarea
                  value={thing2}
                  onChange={(e) => setThing2(e.target.value)}
                  rows={6}
                  aria-label="A second thing you built"
                  style={{ ...rule(focus === "t2", !!errors.thing2), fontSize: 16, lineHeight: 1.65, resize: "vertical" }}
                  {...bind("t2")}
                />
                <VoiceInput
                  onText={(t) => {
                    setThing2((v) => (v ? `${v} ${t}` : t));
                    markSpoken("thing2");
                  }}
                />
                <Err msg={errors.thing2} />
              </>
            )}

            {screen === 5 && (
              <>
                <Q>Anything else about that one?</Q>
                <Sub>Optional again.</Sub>
                <textarea
                  value={thing2Extra}
                  onChange={(e) => setThing2Extra(e.target.value)}
                  rows={5}
                  aria-label="Anything else about the second thing"
                  style={{ ...rule(focus === "t2x", false), fontSize: 16, lineHeight: 1.65, resize: "vertical" }}
                  {...bind("t2x")}
                />
                <VoiceInput
                  onText={(t) => {
                    setThing2Extra((v) => (v ? `${v} ${t}` : t));
                    markSpoken("thing2Extra");
                  }}
                />
              </>
            )}

            {screen === 6 && (
              <>
                <Q>Anything to show us?</Q>
                <Sub>
                  Photos, a video, a résumé, a link. Completely optional — the
                  two answers above matter more than any of it.
                </Sub>

                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp,.heic,.heif,.gif,.mp4,.mov"
                  onChange={(e) => addFiles(e.target.files)}
                  style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
                />
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  style={{
                    ...rule(false, !!errors.files),
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    cursor: "pointer",
                    textAlign: "left",
                    fontSize: 16,
                    color: "var(--text-on-dark-muted)",
                  }}
                >
                  <span>{files.length ? `${files.length} file${files.length > 1 ? "s" : ""}` : "Photos, video, PDF — up to 10 MB each"}</span>
                  <span style={{ color: "var(--gold)", fontSize: 13 }}>Add</span>
                </button>
                <Err msg={errors.files} />

                {files.length > 0 && (
                  <ul style={{ listStyle: "none", padding: 0, margin: "14px 0 0" }}>
                    {files.map((f, i) => (
                      <li
                        key={`${f.name}-${i}`}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          fontSize: 13,
                          color: "var(--text-on-dark-muted)",
                          padding: "7px 0",
                        }}
                      >
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
                        <button
                          type="button"
                          onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}
                          style={{ background: "none", border: "none", color: "#6A6A6A", cursor: "pointer", fontSize: 13, fontFamily: "inherit" }}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <div style={{ marginTop: 28 }}>
                  <input
                    value={resumeLink}
                    onChange={(e) => setResumeLink(e.target.value)}
                    placeholder="…or paste a link"
                    inputMode="url"
                    aria-label="A link to your work"
                    style={rule(focus === "link", !!errors.resumeLink)}
                    {...bind("link")}
                  />
                  <Err msg={errors.resumeLink} />
                </div>
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 22,
          marginTop: 40,
          paddingTop: 24,
          borderTop: "1px solid var(--dark-border)",
        }}
      >
        <button
          type="button"
          onClick={advance}
          disabled={status === "submitting"}
          data-cta-id={last ? "build_submit" : `build_screen_${screen + 1}`}
          data-cta-location="final_cta"
          data-cta-type="contact"
          data-cta-style="primary"
          className="rounded-pill"
          style={{
            background: "var(--gold)",
            color: "var(--dark)",
            border: "none",
            padding: "14px 34px",
            fontSize: 15,
            fontWeight: 600,
            cursor: status === "submitting" ? "default" : "pointer",
            opacity: status === "submitting" ? 0.6 : 1,
            fontFamily: "inherit",
          }}
        >
          {status === "submitting" ? "Sending…" : last ? "Show us what you built" : "Continue"}
        </button>

        {screen > 0 && status !== "submitting" && (
          <button
            type="button"
            onClick={back}
            style={{ background: "none", border: "none", color: "var(--text-on-dark-muted)", fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}
          >
            Back
          </button>
        )}

        {(screen === 3 || screen === 5) && (
          <button
            type="button"
            onClick={advance}
            style={{ background: "none", border: "none", color: "#5A5A5A", fontSize: 14, cursor: "pointer", marginLeft: "auto", fontFamily: "inherit" }}
          >
            Skip
          </button>
        )}
      </div>

      <AnimatePresence>
        {serverError && (
          <motion.p
            role="alert"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25, ease }}
            style={{ color: "#C97E7E", fontSize: 14, marginTop: 18 }}
          >
            {serverError}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
