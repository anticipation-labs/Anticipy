"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ease } from "@/lib/animation";

const BOOKING_URL = "https://calendar.app.google/s97HJuvexjobnwgu9";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const MAX_RESUME_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXT = /\.(pdf|doc|docx)$/i;

const THING_PROMPT =
  "What did you build, what did you personally own, and where can we see it?";

type State = "idle" | "submitting" | "success" | "error";
type Errors = Partial<Record<string, string>>;

/** Shared field chrome. Borders go gold on focus — the only colour the page spends. */
const fieldStyle: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--dark-border)",
  color: "var(--text-on-dark)",
  borderRadius: 10,
  padding: "13px 16px",
  fontSize: 15,
  width: "100%",
  outline: "none",
  transition: "border-color 220ms ease, background-color 220ms ease",
  fontFamily: "inherit",
};

function Label({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label
      htmlFor={htmlFor}
      className="text-[11px] uppercase tracking-wide-label"
      style={{ color: "var(--text-on-dark-muted)", display: "block", marginBottom: 9 }}
    >
      {children}
    </label>
  );
}

function FieldError({ id, msg }: { id: string; msg?: string }) {
  return (
    <AnimatePresence>
      {msg && (
        <motion.p
          id={id}
          role="alert"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25, ease }}
          style={{ color: "#C97E7E", fontSize: 13, marginTop: 7 }}
        >
          {msg}
        </motion.p>
      )}
    </AnimatePresence>
  );
}

export function BuildForm() {
  const [state, setState] = useState<State>("idle");
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [workAuth, setWorkAuth] = useState<"yes" | "no" | "">("");
  const startedAt = useRef<number>(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);

  // Timestamp for the server's time-to-complete check. A real applicant
  // cannot write three considered paragraphs in four seconds.
  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    setErrors((p) => ({ ...p, resume: undefined }));
    if (!f) {
      setFileName(null);
      return;
    }
    if (!ALLOWED_EXT.test(f.name)) {
      setErrors((p) => ({ ...p, resume: "PDF, DOC or DOCX only." }));
      e.target.value = "";
      setFileName(null);
      return;
    }
    if (f.size > MAX_RESUME_BYTES) {
      setErrors((p) => ({ ...p, resume: "That file is over 10 MB." }));
      e.target.value = "";
      setFileName(null);
      return;
    }
    setFileName(f.name);
  };

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setServerError(null);

    const fd = new FormData(e.currentTarget);
    const next: Errors = {};
    const need = (k: string, msg: string) => {
      if (!String(fd.get(k) ?? "").trim()) next[k] = msg;
    };

    need("name", "Required.");
    need("location", "Required — city and country.");
    need("thing1", "Required.");
    need("thing2", "Required.");
    need("thing3", "Required.");

    const email = String(fd.get("email") ?? "").trim();
    if (!email) next.email = "Required.";
    else if (!EMAIL_RE.test(email)) next.email = "That doesn't look like an email address.";

    if (workAuth !== "yes" && workAuth !== "no") next.workAuthorized = "Required.";

    setErrors(next);
    if (Object.keys(next).length) {
      // Move focus to the first problem rather than leaving the person to
      // hunt for it — the form is long enough that a silent error is lost.
      const first = Object.keys(next)[0];
      formRef.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
      return;
    }

    fd.set("startedAt", String(startedAt.current));
    fd.set("workAuthorized", workAuth);

    // Attribution, read at submit time so a visitor who lands with UTMs and
    // navigates around still carries them.
    const qs = new URLSearchParams(window.location.search);
    fd.set("utmSource", qs.get("utm_source") ?? "");
    fd.set("utmMedium", qs.get("utm_medium") ?? "");
    fd.set("utmCampaign", qs.get("utm_campaign") ?? "");
    fd.set("referrer", document.referrer || "");
    fd.set("landingPath", window.location.pathname);

    setState("submitting");
    try {
      const res = await fetch("/api/applications", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setState("error");
        setServerError(data.error || "Something went wrong. Try again.");
        return;
      }
      setState("success");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      setState("error");
      setServerError("Network error. Try again.");
    }
  };

  // ── Success ──────────────────────────────────────────────────
  if (state === "success") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease }}
        style={{ paddingTop: 40 }}
      >
        {/* A single hairline drawing itself in. Restraint reads as confidence;
            a checkmark or confetti would read as a template. */}
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
          transition={{ duration: 0.7, ease, delay: 0.35 }}
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
          transition={{ duration: 0.7, ease, delay: 0.6 }}
        >
          <p
            style={{
              color: "var(--text-on-dark-muted)",
              fontSize: 16,
              lineHeight: 1.7,
              margin: "22px 0 30px",
              maxWidth: 520,
            }}
          >
            You don&apos;t have to wait for that. This is Omar&apos;s own
            calendar — not a screening call, not a recruiter. Take a slot and
            talk to him directly.
          </p>

          <a
            href={BOOKING_URL}
            target="_blank"
            rel="noopener noreferrer"
            data-cta-id="build_book_call"
            data-cta-location="final_cta"
            data-cta-type="contact"
            data-cta-style="primary"
            className="rounded-pill"
            style={{
              display: "inline-block",
              background: "var(--gold)",
              color: "var(--dark)",
              padding: "14px 32px",
              fontSize: 15,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            Book time with Omar
          </a>
        </motion.div>
      </motion.div>
    );
  }

  // ── Form ─────────────────────────────────────────────────────
  const things: Array<["thing1" | "thing2" | "thing3", string]> = [
    ["thing1", "Thing 1"],
    ["thing2", "Thing 2"],
    ["thing3", "Thing 3"],
  ];

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate style={{ marginTop: 8 }}>
      {/* Honeypot. Hidden from sight and from assistive tech; bots fill it. */}
      <div aria-hidden="true" style={{ position: "absolute", left: "-9999px", opacity: 0, height: 0, overflow: "hidden" }}>
        <label htmlFor="company">Company</label>
        <input id="company" name="company" type="text" tabIndex={-1} autoComplete="off" />
      </div>

      <div style={{ display: "grid", gap: 26 }}>
        <div>
          <Label htmlFor="name">Name</Label>
          <input
            id="name"
            name="name"
            type="text"
            autoComplete="name"
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? "err-name" : undefined}
            style={fieldStyle}
            onFocus={(e) => (e.currentTarget.style.borderColor = "var(--gold)")}
            onBlur={(e) => (e.currentTarget.style.borderColor = "var(--dark-border)")}
          />
          <FieldError id="err-name" msg={errors.name} />
        </div>

        <div>
          <Label htmlFor="email">Email</Label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? "err-email" : undefined}
            style={fieldStyle}
            onFocus={(e) => (e.currentTarget.style.borderColor = "var(--gold)")}
            onBlur={(e) => (e.currentTarget.style.borderColor = "var(--dark-border)")}
          />
          <FieldError id="err-email" msg={errors.email} />
        </div>

        <div>
          <Label htmlFor="location">Location</Label>
          <input
            id="location"
            name="location"
            type="text"
            placeholder="City, country"
            autoComplete="address-level2"
            aria-invalid={!!errors.location}
            aria-describedby={errors.location ? "err-location" : undefined}
            style={fieldStyle}
            onFocus={(e) => (e.currentTarget.style.borderColor = "var(--gold)")}
            onBlur={(e) => (e.currentTarget.style.borderColor = "var(--dark-border)")}
          />
          <FieldError id="err-location" msg={errors.location} />
        </div>

        <div
          style={{
            borderTop: "1px solid var(--dark-border)",
            paddingTop: 30,
            marginTop: 6,
          }}
        >
          <p style={{ fontSize: 16, lineHeight: 1.7, color: "var(--text-on-dark)", margin: 0 }}>
            Show us the three best things you&apos;ve built. Photos, video,
            GitHub, schematics, demos or shipped products—anything real.
          </p>
        </div>

        {things.map(([key, label]) => (
          <div key={key}>
            <Label htmlFor={key}>{label}</Label>
            <p
              style={{
                color: "var(--text-on-dark-muted)",
                fontSize: 14,
                lineHeight: 1.6,
                margin: "0 0 10px",
              }}
            >
              {THING_PROMPT}
            </p>
            <textarea
              id={key}
              name={key}
              rows={5}
              aria-invalid={!!errors[key]}
              aria-describedby={errors[key] ? `err-${key}` : undefined}
              style={{ ...fieldStyle, resize: "vertical", lineHeight: 1.65 }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--gold)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--dark-border)")}
            />
            <FieldError id={`err-${key}`} msg={errors[key]} />
          </div>
        ))}

        <div>
          <Label htmlFor="resume">Résumé — optional</Label>
          <input
            ref={fileRef}
            id="resume"
            name="resume"
            type="file"
            accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={onFileChange}
            style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            style={{
              ...fieldStyle,
              textAlign: "left",
              cursor: "pointer",
              color: fileName ? "var(--text-on-dark)" : "var(--text-on-dark-muted)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 14,
            }}
          >
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {fileName ?? "PDF, DOC or DOCX — up to 10 MB"}
            </span>
            <span style={{ color: "var(--gold)", fontSize: 13, flexShrink: 0 }}>
              {fileName ? "Replace" : "Choose file"}
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
                padding: "8px 0 0",
                cursor: "pointer",
                textDecoration: "underline",
              }}
            >
              Remove
            </button>
          )}
          <FieldError id="err-resume" msg={errors.resume} />
        </div>

        <div>
          <Label htmlFor="workAuthorized">
            Are you legally able to work where you live?
          </Label>
          <div style={{ display: "flex", gap: 10 }}>
            {(["yes", "no"] as const).map((v) => {
              const active = workAuth === v;
              return (
                <button
                  key={v}
                  type="button"
                  name={v === "yes" ? "workAuthorized" : undefined}
                  onClick={() => {
                    setWorkAuth(v);
                    setErrors((p) => ({ ...p, workAuthorized: undefined }));
                  }}
                  aria-pressed={active}
                  className="rounded-pill"
                  style={{
                    flex: "0 0 auto",
                    minWidth: 104,
                    padding: "11px 26px",
                    fontSize: 15,
                    cursor: "pointer",
                    background: active ? "var(--gold)" : "transparent",
                    color: active ? "var(--dark)" : "var(--text-on-dark-muted)",
                    border: `1px solid ${active ? "var(--gold)" : "var(--dark-border)"}`,
                    fontWeight: active ? 600 : 400,
                    transition: "all 220ms ease",
                    fontFamily: "inherit",
                  }}
                >
                  {v === "yes" ? "Yes" : "No"}
                </button>
              );
            })}
          </div>
          <FieldError id="err-workAuthorized" msg={errors.workAuthorized} />
        </div>

        <div style={{ marginTop: 8 }}>
          <button
            type="submit"
            disabled={state === "submitting"}
            data-cta-id="build_submit"
            data-cta-location="final_cta"
            data-cta-type="contact"
            data-cta-style="primary"
            className="rounded-pill"
            style={{
              background: "var(--gold)",
              color: "var(--dark)",
              border: "none",
              padding: "15px 36px",
              fontSize: 15,
              fontWeight: 600,
              cursor: state === "submitting" ? "default" : "pointer",
              opacity: state === "submitting" ? 0.6 : 1,
              transition: "opacity 220ms ease",
              fontFamily: "inherit",
            }}
          >
            {state === "submitting" ? "Sending…" : "Show us what you built"}
          </button>

          <AnimatePresence>
            {serverError && (
              <motion.p
                role="alert"
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25, ease }}
                style={{ color: "#C97E7E", fontSize: 14, marginTop: 16 }}
              >
                {serverError}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </div>
    </form>
  );
}
