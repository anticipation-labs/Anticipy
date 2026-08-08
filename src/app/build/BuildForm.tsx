"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ease } from "@/lib/animation";
import { CalendarEmbed } from "./CalendarEmbed";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const URL_RE = /^https?:\/\/[^\s.]+\.[^\s]{2,}$/i;
const MAX_RESUME_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXT = /\.(pdf|doc|docx)$/i;

const THING_PROMPT =
  "What did you build, what did you personally own, and where can we see it?";

type Errors = Partial<Record<string, string>>;
type Status = "idle" | "submitting" | "success" | "error";

const STEPS = ["You", "The work", "Résumé", "One last thing"] as const;

/**
 * Editorial field chrome: a bottom rule rather than a box.
 *
 * Boxed inputs on a near-black page read as a form; a baseline rule reads as
 * writing on a page, which is the register the rest of the site is in. The
 * rule is the only thing that moves on focus, and it moves to gold — the same
 * single accent the site spends everywhere else.
 */
const field = (focused: boolean, invalid: boolean): React.CSSProperties => ({
  background: "transparent",
  border: "none",
  borderBottom: `1px solid ${
    invalid ? "#C97E7E" : focused ? "var(--gold)" : "var(--dark-border)"
  }`,
  color: "var(--text-on-dark)",
  padding: "10px 0 12px",
  fontSize: 18,
  width: "100%",
  outline: "none",
  transition: "border-color 260ms ease",
  fontFamily: "inherit",
  borderRadius: 0,
});

function useFocusRing() {
  const [focused, setFocused] = useState<string | null>(null);
  return {
    focused,
    bind: (name: string) => ({
      onFocus: () => setFocused(name),
      onBlur: () => setFocused((f) => (f === name ? null : f)),
    }),
  };
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

function Question({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="font-serif"
      style={{
        fontSize: "clamp(26px, 3.6vw, 38px)",
        lineHeight: 1.15,
        letterSpacing: "-0.02em",
        margin: "0 0 10px",
        color: "var(--text-on-dark)",
      }}
    >
      {children}
    </h2>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return (
    <p
      style={{
        color: "var(--text-on-dark-muted)",
        fontSize: 15,
        lineHeight: 1.65,
        margin: "0 0 34px",
        maxWidth: 520,
      }}
    >
      {children}
    </p>
  );
}

export function BuildForm() {
  const [step, setStep] = useState(0);
  const [dir, setDir] = useState(1);
  const [status, setStatus] = useState<Status>("idle");
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const { focused, bind } = useFocusRing();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [location, setLocation] = useState("");
  const [geoLabel, setGeoLabel] = useState<string | null>(null);
  const [things, setThings] = useState(["", "", ""]);
  const [resumeLink, setResumeLink] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [workAuth, setWorkAuth] = useState<"yes" | "no" | "">("");

  const fileRef = useRef<HTMLInputElement>(null);
  const startedAt = useRef(0);
  const stepRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    startedAt.current = Date.now();
    // Suggest a location from the edge headers. Failure is silent — this is a
    // convenience, and a broken suggestion must never block the field.
    fetch("/api/geo")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.label) setGeoLabel(d.label);
      })
      .catch(() => {});
  }, []);

  // Move focus to the new step's first control so the keyboard stays usable
  // and screen readers announce the change.
  useEffect(() => {
    if (status === "success") return;
    const t = window.setTimeout(() => {
      stepRef.current
        ?.querySelector<HTMLElement>("input, textarea, button[data-choice]")
        ?.focus();
    }, 380);
    return () => window.clearTimeout(t);
  }, [step, status]);

  const validate = useCallback(
    (s: number): Errors => {
      const e: Errors = {};
      if (s === 0) {
        if (!name.trim()) e.name = "Required.";
        if (!email.trim()) e.email = "Required.";
        else if (!EMAIL_RE.test(email.trim()))
          e.email = "That doesn't look like an email address.";
        if (!location.trim()) e.location = "Required — city and country.";
      }
      if (s === 1) {
        things.forEach((t, i) => {
          if (!t.trim()) e[`thing${i + 1}`] = "Required.";
        });
      }
      if (s === 2 && resumeLink.trim() && !URL_RE.test(resumeLink.trim())) {
        e.resumeLink = "That doesn't look like a link.";
      }
      if (s === 3 && workAuth !== "yes" && workAuth !== "no") {
        e.workAuthorized = "Required.";
      }
      return e;
    },
    [name, email, location, things, resumeLink, workAuth]
  );

  const advance = () => {
    const e = validate(step);
    setErrors(e);
    if (Object.keys(e).length) return;
    if (step < STEPS.length - 1) {
      setDir(1);
      setStep((s) => s + 1);
    } else {
      void submit();
    }
  };

  const back = () => {
    setErrors({});
    setDir(-1);
    setStep((s) => Math.max(0, s - 1));
  };

  const submit = async () => {
    setServerError(null);
    setStatus("submitting");

    const fd = new FormData();
    fd.set("name", name.trim());
    fd.set("email", email.trim());
    fd.set("location", location.trim());
    fd.set("thing1", things[0].trim());
    fd.set("thing2", things[1].trim());
    fd.set("thing3", things[2].trim());
    fd.set("workAuthorized", workAuth);
    fd.set("resumeLink", resumeLink.trim());
    fd.set("startedAt", String(startedAt.current));
    fd.set("company", ""); // honeypot, left empty by real people

    const f = fileRef.current?.files?.[0];
    if (f) fd.set("resume", f);

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
        setStatus("error");
        setServerError(data.error || "Something went wrong. Try again.");
        return;
      }
      setStatus("success");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      setStatus("error");
      setServerError("Network error. Try again.");
    }
  };

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    setErrors((p) => ({ ...p, resume: undefined }));
    if (!f) return setFileName(null);
    if (!ALLOWED_EXT.test(f.name)) {
      setErrors((p) => ({ ...p, resume: "PDF, DOC or DOCX only." }));
      e.target.value = "";
      return setFileName(null);
    }
    if (f.size > MAX_RESUME_BYTES) {
      setErrors((p) => ({ ...p, resume: "That file is over 10 MB." }));
      e.target.value = "";
      return setFileName(null);
    }
    setFileName(f.name);
  };

  // Enter advances, except inside a textarea where it must insert a newline.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Enter") return;
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "TEXTAREA" && !(e.metaKey || e.ctrlKey)) return;
    e.preventDefault();
    advance();
  };

  // ── Success ──────────────────────────────────────────────────
  if (status === "success") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease }}
      >
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.9, ease, delay: 0.15 }}
          style={{
            height: 1,
            background: "var(--gold)",
            transformOrigin: "left",
            marginBottom: 34,
          }}
        />
        <motion.h2
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease, delay: 0.32 }}
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
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease, delay: 0.58 }}
        >
          {/*
            Copy passes one test: every sentence must be true of literally
            everyone who reaches this screen, still true after that person is
            rejected, and about what the APPLICANT DID or what WE WILL DO —
            never a comparative judgement of their quality.

            "Your application really stood out" fails all three. This screen
            renders in milliseconds, so no human has read anything; an instant
            *evaluation* is a lie with a timestamp, and this audience reasons
            about latency for a living. The phrase is also verbatim in dozens
            of published recruiting-template libraries they have each received
            hundreds of times, and it is the exact wording engineers quote on
            Blind as the insult they remember after a rejection.

            The status signal comes from the costly, verifiable thing instead:
            the founder's own calendar, bookable now. Under the persuasion-
            knowledge model a recognised-but-CREDIBLE tactic raises regard for
            the messenger rather than lowering it — and giving away the CEO's
            calendar is expensive in a way a compliment is not.
          */}
          <p
            style={{
              color: "var(--text-on-dark)",
              fontSize: 17,
              lineHeight: 1.75,
              margin: "24px 0 0",
              maxWidth: 560,
            }}
          >
            You just wrote three accounts of things you actually built. That
            earns more than a form reply.
          </p>
          <p
            style={{
              color: "var(--text-on-dark-muted)",
              fontSize: 16,
              lineHeight: 1.75,
              margin: "16px 0 0",
              maxWidth: 560,
            }}
          >
            Below is Omar&apos;s own calendar — the founder, not a recruiter
            and not a screening round. Pick a time and talk to the person who
            makes the decision.
          </p>

          <CalendarEmbed />
        </motion.div>
      </motion.div>
    );
  }

  const isLast = step === STEPS.length - 1;

  return (
    <div onKeyDown={onKeyDown}>
      {/* Progress: a rule that fills. Four dots would read as a wizard. */}
      <div style={{ marginBottom: 46 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: 12,
          }}
        >
          <span
            className="tracking-wide-label"
            style={{ fontSize: 11, textTransform: "uppercase", color: "var(--gold)" }}
          >
            {String(step + 1).padStart(2, "0")} — {STEPS[step]}
          </span>
          <span style={{ fontSize: 11, color: "#5A5A5A" }}>
            {String(STEPS.length).padStart(2, "0")}
          </span>
        </div>
        <div style={{ height: 1, background: "var(--dark-border)", position: "relative" }}>
          <motion.div
            animate={{ scaleX: (step + 1) / STEPS.length }}
            initial={false}
            transition={{ duration: 0.7, ease }}
            style={{
              position: "absolute",
              inset: 0,
              background: "var(--gold)",
              transformOrigin: "left",
            }}
          />
        </div>
      </div>

      <div style={{ position: "relative", minHeight: 340 }}>
        <AnimatePresence mode="wait" initial={false} custom={dir}>
          <motion.div
            key={step}
            ref={stepRef}
            custom={dir}
            initial={{ opacity: 0, x: dir * 26 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: dir * -26 }}
            transition={{ duration: 0.42, ease }}
          >
            {/* ── 1. You ─────────────────────────────────── */}
            {step === 0 && (
              <>
                <Question>First, who are you?</Question>
                <Hint>Three quick things, then we get to the work.</Hint>

                <div style={{ display: "grid", gap: 30 }}>
                  <div>
                    <input
                      name="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Your name"
                      autoComplete="name"
                      aria-label="Your name"
                      aria-invalid={!!errors.name}
                      style={field(focused === "name", !!errors.name)}
                      {...bind("name")}
                    />
                    <Err msg={errors.name} />
                  </div>
                  <div>
                    <input
                      name="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="Email"
                      autoComplete="email"
                      aria-label="Email"
                      aria-invalid={!!errors.email}
                      style={field(focused === "email", !!errors.email)}
                      {...bind("email")}
                    />
                    <Err msg={errors.email} />
                  </div>
                  <div>
                    <input
                      name="location"
                      value={location}
                      onChange={(e) => setLocation(e.target.value)}
                      placeholder="City, country"
                      autoComplete="address-level2"
                      aria-label="Location"
                      aria-invalid={!!errors.location}
                      style={field(focused === "location", !!errors.location)}
                      {...bind("location")}
                    />
                    <Err msg={errors.location} />
                    {geoLabel && location.trim() !== geoLabel && (
                      <button
                        type="button"
                        onClick={() => {
                          setLocation(geoLabel);
                          setErrors((p) => ({ ...p, location: undefined }));
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
                        Use {geoLabel}
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* ── 2. The work ────────────────────────────── */}
            {step === 1 && (
              <>
                <Question>Show us the three best things you&apos;ve built.</Question>
                <Hint>
                  Photos, video, GitHub, schematics, demos or shipped
                  products—anything real. {THING_PROMPT}
                </Hint>

                <div style={{ display: "grid", gap: 30 }}>
                  {[0, 1, 2].map((i) => (
                    <div key={i}>
                      <span
                        className="tracking-wide-label"
                        style={{
                          fontSize: 11,
                          textTransform: "uppercase",
                          color: "var(--text-on-dark-muted)",
                          display: "block",
                          marginBottom: 6,
                        }}
                      >
                        Thing {i + 1}
                      </span>
                      <textarea
                        name={`thing${i + 1}`}
                        value={things[i]}
                        onChange={(e) =>
                          setThings((t) => t.map((v, j) => (j === i ? e.target.value : v)))
                        }
                        rows={3}
                        aria-label={`Thing ${i + 1}`}
                        aria-invalid={!!errors[`thing${i + 1}`]}
                        style={{
                          ...field(focused === `thing${i}`, !!errors[`thing${i + 1}`]),
                          fontSize: 16,
                          lineHeight: 1.6,
                          resize: "vertical",
                        }}
                        {...bind(`thing${i}`)}
                      />
                      <Err msg={errors[`thing${i + 1}`]} />
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* ── 3. Résumé ──────────────────────────────── */}
            {step === 2 && (
              <>
                <Question>Got a résumé?</Question>
                <Hint>
                  Completely optional — the work above matters more. But if
                  you&apos;ve got one, we&apos;d still like to see it. Upload a
                  file or paste a link.
                </Hint>

                <div style={{ display: "grid", gap: 26 }}>
                  <div>
                    <input
                      ref={fileRef}
                      type="file"
                      accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                      onChange={onFile}
                      style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
                    />
                    <button
                      type="button"
                      onClick={() => fileRef.current?.click()}
                      style={{
                        ...field(false, !!errors.resume),
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: 16,
                        cursor: "pointer",
                        textAlign: "left",
                        fontSize: 16,
                        color: fileName ? "var(--text-on-dark)" : "var(--text-on-dark-muted)",
                      }}
                    >
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {fileName ?? "PDF, DOC or DOCX — up to 10 MB"}
                      </span>
                      <span style={{ color: "var(--gold)", fontSize: 13, flexShrink: 0 }}>
                        {fileName ? "Replace" : "Upload"}
                      </span>
                    </button>
                    {fileName && (
                      <button
                        type="button"
                        onClick={() => {
                          if (fileRef.current) fileRef.current.value = "";
                          setFileName(null);
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--text-on-dark-muted)",
                          fontSize: 13,
                          padding: "9px 0 0",
                          cursor: "pointer",
                          textDecoration: "underline",
                          fontFamily: "inherit",
                        }}
                      >
                        Remove
                      </button>
                    )}
                    <Err msg={errors.resume} />
                  </div>

                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 14,
                      color: "#4A4A4A",
                      fontSize: 12,
                      textTransform: "uppercase",
                      letterSpacing: "0.12em",
                    }}
                  >
                    <span style={{ flex: 1, height: 1, background: "var(--dark-border)" }} />
                    or
                    <span style={{ flex: 1, height: 1, background: "var(--dark-border)" }} />
                  </div>

                  <div>
                    <input
                      name="resumeLink"
                      value={resumeLink}
                      onChange={(e) => setResumeLink(e.target.value)}
                      placeholder="https://…  LinkedIn, personal site, anything"
                      inputMode="url"
                      aria-label="Link to your résumé"
                      aria-invalid={!!errors.resumeLink}
                      style={field(focused === "resumeLink", !!errors.resumeLink)}
                      {...bind("resumeLink")}
                    />
                    <Err msg={errors.resumeLink} />
                  </div>
                </div>
              </>
            )}

            {/* ── 4. Work authorisation ──────────────────── */}
            {step === 3 && (
              <>
                <Question>Are you legally able to work where you live?</Question>
                <Hint>Last one. Then you&apos;re done.</Hint>

                <div style={{ display: "flex", gap: 12 }}>
                  {(["yes", "no"] as const).map((v) => {
                    const active = workAuth === v;
                    return (
                      <button
                        key={v}
                        type="button"
                        data-choice
                        onClick={() => {
                          setWorkAuth(v);
                          setErrors((p) => ({ ...p, workAuthorized: undefined }));
                        }}
                        aria-pressed={active}
                        className="rounded-pill"
                        style={{
                          minWidth: 118,
                          padding: "13px 30px",
                          fontSize: 15,
                          cursor: "pointer",
                          background: active ? "var(--gold)" : "transparent",
                          color: active ? "var(--dark)" : "var(--text-on-dark-muted)",
                          border: `1px solid ${active ? "var(--gold)" : "var(--dark-border)"}`,
                          fontWeight: active ? 600 : 400,
                          transition: "all 240ms ease",
                          fontFamily: "inherit",
                        }}
                      >
                        {v === "yes" ? "Yes" : "No"}
                      </button>
                    );
                  })}
                </div>
                <Err msg={errors.workAuthorized} />
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* ── Controls ──────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 22,
          marginTop: 44,
          paddingTop: 26,
          borderTop: "1px solid var(--dark-border)",
        }}
      >
        <button
          type="button"
          onClick={advance}
          disabled={status === "submitting"}
          data-cta-id={isLast ? "build_submit" : `build_step_${step + 1}`}
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
            transition: "opacity 220ms ease",
            fontFamily: "inherit",
          }}
        >
          {status === "submitting"
            ? "Sending…"
            : isLast
              ? "Show us what you built"
              : "Continue"}
        </button>

        {step > 0 && status !== "submitting" && (
          <button
            type="button"
            onClick={back}
            style={{
              background: "none",
              border: "none",
              color: "var(--text-on-dark-muted)",
              fontSize: 14,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Back
          </button>
        )}

        {step === 2 && !fileName && !resumeLink.trim() && (
          <button
            type="button"
            onClick={() => {
              setDir(1);
              setStep(3);
            }}
            style={{
              background: "none",
              border: "none",
              color: "#5A5A5A",
              fontSize: 14,
              cursor: "pointer",
              marginLeft: "auto",
              fontFamily: "inherit",
            }}
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
