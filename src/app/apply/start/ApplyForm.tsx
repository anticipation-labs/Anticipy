"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ease } from "@/lib/animation";
import { LocationInput } from "@/components/apply/LocationInput";
import { VoiceInput } from "@/components/apply/VoiceInput";
import { Flash } from "@/components/apply/Flash";
import { useViewport } from "@/components/apply/useViewport";
import { suggestEmail } from "@/lib/email-check";
import { Tm } from "@/components/Tm";
import {
  ROLES,
  QUESTIONS,
  ROLE_LABEL,
  resolveQuestionSet,
  parseRoleParam,
  type RoleKey,
} from "../roles";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXT = /\.(pdf|doc|docx|png|jpe?g|webp|heic|heif|gif|mp4|mov)$/i;
const MIN_INPUT_PX = 16;

// 0 intro · 1 role · 2 you · 3..6 questions · 7 links+cv · 8 logistics
const LAST = 8;

const SAVE_KEY = "anticipy.apply.v1";
const SAVE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

interface Saved {
  t: number;
  screen: number;
  roles: RoleKey[];
  name: string;
  email: string;
  location: string;
  answers: Record<string, string>;
  links: string;
  availability: string;
  startDate: string;
  vancouver: string;
  workAuth: "yes" | "no" | "";
  spoken: string[];
}

/** Single-line fields: a rule under the text, gold on focus. */
const rule = (focused: boolean, invalid: boolean): React.CSSProperties => ({
  background: "transparent",
  border: "none",
  borderBottom: `1px solid ${invalid ? "var(--danger)" : focused ? "var(--accent)" : "var(--rule)"}`,
  color: "var(--ink)",
  padding: "10px 0 12px",
  fontSize: 18,
  width: "100%",
  outline: "none",
  transition: "border-color 220ms ease",
  fontFamily: "inherit",
  borderRadius: 0,
});

/**
 * Essay fields get a full visible border instead of a single rule.
 *
 * A bottom-rule textarea reads as a one-line input and people answer it like
 * one. A bordered box that can be dragged taller says "this is where the long
 * answer goes" without a word of instruction.
 */
const box = (focused: boolean, invalid: boolean): React.CSSProperties => ({
  background: "#FFFFFF",
  border: `1px solid ${invalid ? "var(--danger)" : focused ? "var(--accent)" : "var(--rule)"}`,
  borderRadius: 8,
  color: "var(--ink)",
  padding: "13px 14px",
  fontSize: MIN_INPUT_PX,
  lineHeight: 1.6,
  width: "100%",
  outline: "none",
  transition: "border-color 220ms ease",
  fontFamily: "inherit",
  resize: "vertical",
  display: "block",
});

function Q({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="font-serif ap-q"
      style={{
        fontSize: "clamp(23px, 3.1vw, 33px)",
        lineHeight: 1.16,
        letterSpacing: "-0.02em",
        margin: "0 0 10px",
        color: "var(--ink)",
      }}
    >
      {children}
    </h2>
  );
}

function Sub({ children }: { children: React.ReactNode }) {
  return (
    <p className="ap-sub" style={{ color: "var(--ink-2)", fontSize: 15, lineHeight: 1.6, margin: "0 0 24px", maxWidth: 540 }}>
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
          transition={{ duration: 0.2, ease }}
          style={{ color: "var(--danger)", fontSize: 13, marginTop: 8 }}
        >
          {msg}
        </motion.p>
      )}
    </AnimatePresence>
  );
}

function Choice({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="rounded-pill"
      style={{
        padding: "11px 22px",
        fontSize: 15,
        cursor: "pointer",
        background: active ? "var(--ink)" : "transparent",
        color: active ? "var(--paper)" : "var(--ink-2)",
        border: `1px solid ${active ? "var(--ink)" : "var(--rule)"}`,
        fontWeight: active ? 600 : 400,
        transition: "all 200ms ease",
        fontFamily: "inherit",
        textAlign: "left",
      }}
    >
      {children}
    </button>
  );
}

type Status = "idle" | "busy" | "done";

export function ApplyForm() {
  useViewport();

  // Everything below the fold of this component depends on localStorage and
  // the query string, neither of which exists during the server render. The
  // form stays hidden for one frame rather than rendering the intro screen and
  // then jumping — which is what somebody arriving from a role page would see.
  const [ready, setReady] = useState(false);
  const [screen, setScreen] = useState(0);
  const [entryScreen, setEntryScreen] = useState(0);
  const [flashing, setFlashing] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);

  const [roles, setRoles] = useState<RoleKey[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [emailFix, setEmailFix] = useState<string | null>(null);
  const [location, setLocation] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [links, setLinks] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [availability, setAvailability] = useState("");
  const [startDate, setStartDate] = useState("");
  const [vancouver, setVancouver] = useState("");
  const [workAuth, setWorkAuth] = useState<"yes" | "no" | "">("");
  const [spoken, setSpoken] = useState<Set<string>>(new Set());
  const [honeypot, setHoneypot] = useState("");

  const fileRef = useRef<HTMLInputElement>(null);
  const startedAt = useRef(0);
  const paneRef = useRef<HTMLDivElement>(null);

  const questionSet = resolveQuestionSet(roles);
  const qs = questionSet ? QUESTIONS[questionSet] : [];

  // ── Restore, then decide where to start ───────────────────────────
  useEffect(() => {
    startedAt.current = Date.now();

    let restored: Saved | null = null;
    try {
      const raw = window.localStorage.getItem(SAVE_KEY);
      if (raw) {
        const s = JSON.parse(raw) as Saved;
        if (s && typeof s.t === "number" && Date.now() - s.t < SAVE_MAX_AGE_MS) restored = s;
        else window.localStorage.removeItem(SAVE_KEY);
      }
    } catch {
      /* corrupt or unavailable storage — start clean rather than fail */
    }

    if (restored) {
      setRoles(Array.isArray(restored.roles) ? restored.roles : []);
      setName(restored.name || "");
      setEmail(restored.email || "");
      setLocation(restored.location || "");
      setAnswers(restored.answers || {});
      setLinks(restored.links || "");
      setAvailability(restored.availability || "");
      setStartDate(restored.startDate || "");
      setVancouver(restored.vancouver || "");
      setWorkAuth(restored.workAuth || "");
      setSpoken(new Set(restored.spoken || []));
    }

    // A role in the URL is an explicit choice made one click ago, so it wins
    // over whatever was saved, and it skips the intro and role screens.
    const fromUrl = parseRoleParam(new URLSearchParams(window.location.search).get("role"));
    let start = restored ? Math.min(Math.max(restored.screen ?? 0, 0), LAST) : 0;
    if (fromUrl) {
      setRoles([fromUrl]);
      if (start < 2) start = 2;
    }

    setEntryScreen(start);
    setScreen(start);
    setReady(true);
    window.history.replaceState({ apStep: start }, "");
  }, []);

  // ── Autosave ──────────────────────────────────────────────────────
  // Files are deliberately not persisted: a File cannot be serialised, and
  // silently "restoring" a filename with no bytes behind it would be worse
  // than asking for the upload again.
  const save = useCallback(() => {
    if (!ready) return;
    const payload: Saved = {
      t: Date.now(),
      screen,
      roles,
      name,
      email,
      location,
      answers,
      links,
      availability,
      startDate,
      vancouver,
      workAuth,
      spoken: Array.from(spoken),
    };
    try {
      window.localStorage.setItem(SAVE_KEY, JSON.stringify(payload));
    } catch {
      /* private mode or quota — autosave is a convenience, never a blocker */
    }
  }, [ready, screen, roles, name, email, location, answers, links, availability, startDate, vancouver, workAuth, spoken]);

  // On step change.
  useEffect(() => {
    save();
  }, [screen, save]);

  const clearSave = () => {
    try {
      window.localStorage.removeItem(SAVE_KEY);
    } catch {
      /* nothing to do */
    }
  };

  // ── Browser back moves one step, never off the page ───────────────
  useEffect(() => {
    const onPop = (e: PopStateEvent) => {
      const step = (e.state as { apStep?: number } | null)?.apStep;
      if (typeof step === "number") {
        setErrors({});
        setScreen(step);
      }
      // No apStep means this entry predates the wizard — let the browser
      // navigate, which returns them to the role page they came from.
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (!ready || status === "done" || screen === 0) return;
    if (window.matchMedia?.("(pointer: coarse)").matches) return;
    const t = window.setTimeout(() => {
      paneRef.current?.querySelector<HTMLElement>("input, textarea")?.focus();
    }, 300);
    return () => window.clearTimeout(t);
  }, [screen, status, ready]);

  const set = useCallback((id: string, v: string) => setAnswers((a) => ({ ...a, [id]: v })), []);
  const bind = (k: string) => ({
    onFocus: () => setFocus(k),
    onBlur: () => {
      setFocus((f) => (f === k ? null : f));
      save(); // on blur
    },
  });

  const toggleRole = (key: RoleKey) => {
    setErrors((p) => ({ ...p, roles: undefined }));
    setRoles((prev) => {
      const role = ROLES.find((r) => r.key === key)!;
      // Growth is a different job, not a variant of the engineering one — so
      // it never combines. The engineering roles do.
      if (role.family === "growth") return prev.includes(key) ? [] : [key];
      const withoutGrowth = prev.filter((k) => ROLES.find((r) => r.key === k)?.family === "engineering");
      return withoutGrowth.includes(key)
        ? withoutGrowth.filter((k) => k !== key)
        : [...withoutGrowth, key];
    });
  };

  const validate = (s: number) => {
    const e: Partial<Record<string, string>> = {};
    if (s === 1 && !roles.length) e.roles = "Pick at least one.";
    if (s === 2) {
      if (!name.trim()) e.name = "Required.";
      if (!email.trim()) e.email = "Required.";
      else if (!EMAIL_RE.test(email.trim())) e.email = "That doesn't look right.";
      if (!location.trim()) e.location = "Required.";
    }
    if (s >= 3 && s <= 6) {
      const q = qs[s - 3];
      if (q && !(answers[q.id] || "").trim()) e[q.id] = "This one we need.";
    }
    if (s === 8) {
      if (!availability.trim()) e.availability = "Required.";
      if (workAuth !== "yes" && workAuth !== "no") e.workAuth = "Required.";
      if (!vancouver) e.vancouver = "Required.";
    }
    return e;
  };

  const go = (next: number) => {
    setFlashing(true);
    window.history.pushState({ apStep: next }, "");
    window.setTimeout(() => setScreen(next), 90);
    window.setTimeout(() => setFlashing(false), 280);
  };

  const advance = () => {
    const e = validate(screen);
    setErrors(e);
    if (Object.keys(e).length) return;
    save();
    if (screen < LAST) go(screen + 1);
    else void submit();
  };

  // Routed through history so the in-page control and the browser control are
  // the same action, and history cannot grow one entry per Back click.
  const back = () => window.history.back();

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Enter") return;
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "TEXTAREA" && !(e.metaKey || e.ctrlKey)) return;
    e.preventDefault();
    advance();
  };

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const next: File[] = [];
    let bad = "";
    for (const f of Array.from(list)) {
      if (!ALLOWED_EXT.test(f.name)) { bad = "Some files were the wrong type."; continue; }
      if (f.size > MAX_FILE_BYTES) { bad = "Some files were over 10 MB."; continue; }
      next.push(f);
    }
    setErrors((p) => ({ ...p, files: bad || undefined }));
    setFiles((p) => [...p, ...next].slice(0, 6));
  };

  const submit = async () => {
    setServerError(null);
    setStatus("busy");
    const fd = new FormData();
    fd.set("sourceForm", "apply");
    fd.set("roles", roles.join(","));
    fd.set("questionSet", questionSet ?? "");
    fd.set("name", name.trim());
    fd.set("email", email.trim());
    fd.set("location", location.trim());
    fd.set(
      "answers",
      JSON.stringify(qs.map((q) => ({ id: q.id, question: q.q, answer: (answers[q.id] || "").trim() })))
    );
    fd.set("links", links.trim());
    fd.set("availability", availability.trim());
    fd.set("startDate", startDate.trim());
    fd.set("vancouver", vancouver);
    fd.set("workAuthorized", workAuth);
    fd.set("spokenFields", Array.from(spoken).join(","));
    fd.set("startedAt", String(startedAt.current));
    fd.set("company", honeypot);
    files.forEach((f) => fd.append("files", f));

    const p = new URLSearchParams(window.location.search);
    fd.set("utmSource", p.get("utm_source") ?? "");
    fd.set("utmMedium", p.get("utm_medium") ?? "");
    fd.set("utmCampaign", p.get("utm_campaign") ?? "");
    fd.set("referrer", document.referrer || "");
    fd.set("landingPath", window.location.pathname + window.location.search);

    try {
      const res = await fetch("/api/applications", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setStatus("idle");
        setServerError(data.error || "Something went wrong. Try again.");
        return;
      }
      clearSave();
      setFlashing(true);
      window.setTimeout(() => setStatus("done"), 100);
      window.setTimeout(() => setFlashing(false), 300);
    } catch {
      setStatus("idle");
      setServerError("Network error. Try again.");
    }
  };

  const shell: React.CSSProperties = {
    height: "var(--app-h, 100dvh)",
    overflowY: "auto",
    overflowX: "hidden",
    display: "flex",
    flexDirection: "column",
    padding: "0 24px",
    WebkitOverflowScrolling: "touch",
  };
  const inner: React.CSSProperties = {
    width: "100%",
    maxWidth: 620,
    marginLeft: "auto",
    marginRight: "auto",
    marginTop: "auto",
    marginBottom: "auto",
    paddingTop: 28,
    paddingBottom: 28,
  };

  const brand = (
    <div className="ap-brand" style={{ marginBottom: screen === 0 ? 36 : 26 }}>
      <a href="/" className="font-serif" style={{ fontSize: 19, color: "var(--ink)", textDecoration: "none", letterSpacing: "0.01em" }}>
        Anticipy<Tm />
      </a>
    </div>
  );

  if (!ready) {
    return (
      <div style={shell}>
        <div style={inner} className="ap-inner">{brand}</div>
      </div>
    );
  }

  if (status === "done") {
    return (
      <div style={shell}>
        <Flash active={flashing} />
        <div style={{ ...inner, marginTop: 40, marginBottom: 40 }}>
          <motion.div
            initial={{ scaleX: 0 }} animate={{ scaleX: 1 }}
            transition={{ duration: 0.8, ease, delay: 0.05 }}
            style={{ height: 1, background: "var(--accent)", transformOrigin: "left", marginBottom: 28 }}
          />
          <motion.h2
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease, delay: 0.2 }}
            className="font-serif"
            style={{ fontSize: "clamp(27px, 3.8vw, 40px)", lineHeight: 1.14, letterSpacing: "-0.02em", margin: 0 }}
          >
            Your application really stood out from the pile.
          </motion.h2>
          <motion.div
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease, delay: 0.38 }}
          >
            <p style={{ color: "var(--ink)", fontSize: 17, lineHeight: 1.7, margin: "18px 0 0", maxWidth: 560 }}>
              It&apos;s in Omar&apos;s inbox — not a queue, not a recruiter, not
              a screening tool. He reads every one himself and replies to the
              ones he wants to talk to.
            </p>
            <p style={{ color: "var(--ink-2)", fontSize: 15, lineHeight: 1.7, margin: "16px 0 0", maxWidth: 560 }}>
              A copy of your answers is on its way to you. Replying to that
              email reaches him directly.
            </p>
          </motion.div>
        </div>
      </div>
    );
  }

  const q = screen >= 3 && screen <= 6 ? qs[screen - 3] : null;
  const stepLabel = ["", "Role", "You", "1 of 4", "2 of 4", "3 of 4", "4 of 4", "Links", "Logistics"][screen];
  const FILL = [0, 0.18, 0.34, 0.5, 0.63, 0.74, 0.84, 0.93, 1];

  return (
    <div style={shell} onKeyDown={onKeyDown}>
      <Flash active={flashing} />
      <style dangerouslySetInnerHTML={{ __html: `
        @media (max-height: 560px) {
          .ap-inner { padding-top: 14px !important; padding-bottom: 14px !important; }
          .ap-brand { margin-bottom: 14px !important; }
          .ap-q { font-size: 20px !important; margin-bottom: 6px !important; }
          .ap-sub { margin-bottom: 14px !important; font-size: 14px !important; }
          .ap-inner textarea { max-height: 22vh !important; }
        }
        @media (max-height: 430px) { .ap-q { font-size: 17px !important; } .ap-sub { display: none !important; } }
        @media (max-width: 430px) {
          .ap-inner { padding-top: 18px !important; padding-bottom: 18px !important; }
          .ap-fields { gap: 15px !important; }
          .ap-sub { margin-bottom: 16px !important; }
        }
        .ap-inner textarea::placeholder { color: #9A948A; }
      ` }} />

      <div style={inner} className="ap-inner">
        {brand}

        {screen > 0 && (
          <div style={{ marginBottom: 30 }}>
            {/* One indicator: a label and the bar it fills. There is no second
                numeric counter — two of them competing was just noise. */}
            <div style={{ marginBottom: 10 }}>
              <span className="tracking-wide-label" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--accent-ink)" }}>
                {stepLabel}
              </span>
            </div>
            <div style={{ height: 1, background: "var(--rule)", position: "relative" }}>
              <motion.div
                animate={{ scaleX: FILL[screen] }} initial={false}
                transition={{ duration: 0.32, ease, delay: 0.12 }}
                style={{ position: "absolute", inset: 0, background: "var(--accent)", transformOrigin: "left" }}
              />
            </div>
          </div>
        )}

        {/* The location combobox drops its listbox out of this pane and over
            the button row below. Framer's animated pane forms its own stacking
            context, so the listbox's own z-index cannot reach past it — these
            two z-indexes are what keep the suggestions clickable. */}
        <div style={{ position: "relative", zIndex: 2 }}>
          <motion.div
            key={screen}
            ref={paneRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.14, ease }}
          >
            {screen === 0 && (
              <>
                <h1 className="font-serif" style={{ fontSize: "clamp(30px, 5vw, 54px)", lineHeight: 1.07, letterSpacing: "-0.03em", margin: 0, color: "var(--ink)" }}>
                  Come build the thing.
                </h1>
                <p style={{ fontSize: "clamp(16px, 2vw, 19px)", lineHeight: 1.6, color: "var(--ink)", margin: "20px 0 0", maxWidth: 560 }}>
                  Anticipy is a pendant that listens while you talk and does the
                  things you mention. I&apos;m hiring four people to build it
                  with me, and this is the whole application.
                </p>
                <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--ink-2)", margin: "16px 0 0", maxWidth: 560 }}>
                  No cover letter, no resume. I read every one myself.
                </p>
              </>
            )}

            {screen === 1 && (
              <>
                <Q>Which role are you here for?</Q>
                <Sub>
                  Pick more than one engineering role if both fit — we&apos;ll
                  ask the combined questions.
                </Sub>
                <div style={{ display: "grid", gap: 10 }}>
                  {ROLES.map((r) => (
                    <Choice key={r.key} active={roles.includes(r.key)} onClick={() => toggleRole(r.key)}>
                      {r.label}
                    </Choice>
                  ))}
                </div>
                <Err msg={errors.roles} />
              </>
            )}

            {screen === 2 && (
              <>
                {roles.length > 0 && (
                  <div style={{ marginBottom: 14, display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13.5, color: "var(--ink-2)" }}>
                      {roles.map((r) => ROLE_LABEL[r]).join(" + ")}
                    </span>
                    <button
                      type="button"
                      onClick={() => go(1)}
                      style={{ background: "none", border: "none", padding: 0, color: "var(--accent-ink)", fontSize: 13, cursor: "pointer", fontFamily: "inherit", textDecoration: "underline", textUnderlineOffset: 3 }}
                    >
                      change role
                    </button>
                  </div>
                )}
                <Q>First — who are you?</Q>
                <Sub>Name, email, and where you are.</Sub>
                <div className="ap-fields" style={{ display: "grid", gap: 22 }}>
                  <div>
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" aria-label="Your name" style={rule(focus === "name", !!errors.name)} {...bind("name")} />
                    <Err msg={errors.name} />
                  </div>
                  <div>
                    <input
                      type="email" value={email}
                      onChange={(e) => { setEmail(e.target.value); setEmailFix(null); }}
                      onFocus={() => setFocus("email")}
                      onBlur={() => { setFocus(null); setEmailFix(suggestEmail(email.trim())); save(); }}
                      placeholder="Email" autoComplete="email" aria-label="Email"
                      style={rule(focus === "email", !!errors.email)}
                    />
                    <Err msg={errors.email} />
                    {emailFix && (
                      <button type="button" onClick={() => { setEmail(emailFix); setEmailFix(null); }}
                        style={{ background: "none", border: "none", color: "var(--accent-ink)", fontSize: 13, padding: "8px 0 0", cursor: "pointer", fontFamily: "inherit" }}>
                        Did you mean {emailFix}?
                      </button>
                    )}
                  </div>
                  <div>
                    <LocationInput
                      value={location}
                      onChange={(v) => { setLocation(v); setErrors((p) => ({ ...p, location: undefined })); }}
                      invalid={!!errors.location}
                      onEnterWhenClosed={advance}
                    />
                    <Err msg={errors.location} />
                  </div>
                </div>
              </>
            )}

            {q && (
              <>
                <Q>{q.q}</Q>
                {q.hint && <Sub>{q.hint}</Sub>}
                <textarea
                  value={answers[q.id] || ""}
                  onChange={(e) => set(q.id, e.target.value)}
                  rows={5}
                  placeholder={q.placeholder}
                  aria-label={q.q}
                  style={{ ...box(focus === q.id, !!errors[q.id]), maxHeight: "34vh" }}
                  {...bind(q.id)}
                />
                <VoiceInput onText={(t) => { set(q.id, (answers[q.id] ? answers[q.id] + " " : "") + t); setSpoken((s) => new Set(s).add(q.id)); }} />
                <Err msg={errors[q.id]} />
              </>
            )}

            {screen === 7 && (
              <>
                <Q>Where can we see your work?</Q>
                <Sub>
                  Portfolio, GitHub, website, LinkedIn, social channels — paste
                  whatever is relevant, one per line. Résumé optional.
                </Sub>
                <textarea
                  value={links}
                  onChange={(e) => setLinks(e.target.value)}
                  rows={4}
                  placeholder={"https://github.com/you\nhttps://yoursite.com\nhttps://tiktok.com/@you"}
                  aria-label="Relevant links"
                  style={{ ...box(focus === "links", false), maxHeight: "26vh" }}
                  {...bind("links")}
                />
                <div style={{ marginTop: 20 }}>
                  <input ref={fileRef} type="file" multiple
                    accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp,.heic,.heif,.gif,.mp4,.mov"
                    onChange={(e) => addFiles(e.target.files)}
                    style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />
                  <button type="button" onClick={() => fileRef.current?.click()}
                    style={{ ...rule(false, !!errors.files), display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", textAlign: "left", fontSize: MIN_INPUT_PX, color: "var(--ink-2)" }}>
                    <span>{files.length ? `${files.length} file${files.length > 1 ? "s" : ""}` : "Résumé or work samples — optional"}</span>
                    <span style={{ color: "var(--accent-ink)", fontSize: 13 }}>Add</span>
                  </button>
                  <Err msg={errors.files} />
                  {files.length > 0 && (
                    <ul style={{ listStyle: "none", padding: 0, margin: "10px 0 0", maxHeight: "14vh", overflowY: "auto" }}>
                      {files.map((f, i) => (
                        <li key={`${f.name}-${i}`} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--ink-2)", padding: "5px 0" }}>
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
                          <button type="button" onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}
                            style={{ background: "none", border: "none", color: "var(--ink-2)", cursor: "pointer", fontSize: 13, fontFamily: "inherit" }}>Remove</button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}

            {screen === 8 && (
              <>
                <Q>Last bit — the practical stuff.</Q>
                <Sub>Four quick answers and you&apos;re done.</Sub>
                <div className="ap-fields" style={{ display: "grid", gap: 22 }}>
                  <div>
                    <span className="tracking-wide-label" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--ink-2)", display: "block", marginBottom: 6 }}>
                      Current availability
                    </span>
                    <input value={availability} onChange={(e) => setAvailability(e.target.value)}
                      placeholder="Full-time, part-time, contract, 3 days a week…" aria-label="Current availability"
                      style={rule(focus === "avail", !!errors.availability)} {...bind("avail")} />
                    <Err msg={errors.availability} />
                  </div>
                  <div>
                    <span className="tracking-wide-label" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--ink-2)", display: "block", marginBottom: 6 }}>
                      Possible start date
                    </span>
                    <input value={startDate} onChange={(e) => setStartDate(e.target.value)}
                      placeholder="Immediately, 2 weeks, October…" aria-label="Possible start date"
                      style={rule(focus === "start", false)} {...bind("start")} />
                  </div>
                  <div>
                    <span className="tracking-wide-label" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--ink-2)", display: "block", marginBottom: 8 }}>
                      Can you work from Vancouver, or travel when it matters?
                    </span>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {["Based in Vancouver", "Can relocate", "Can travel", "Remote only"].map((v) => (
                        <Choice key={v} active={vancouver === v} onClick={() => { setVancouver(v); setErrors((p) => ({ ...p, vancouver: undefined })); }}>{v}</Choice>
                      ))}
                    </div>
                    <Err msg={errors.vancouver} />
                  </div>
                  <div>
                    <span className="tracking-wide-label" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--ink-2)", display: "block", marginBottom: 8 }}>
                      Are you legally allowed to work, and old enough to do so where you live?
                    </span>
                    <div style={{ display: "flex", gap: 8 }}>
                      {(["yes", "no"] as const).map((v) => (
                        <Choice key={v} active={workAuth === v} onClick={() => { setWorkAuth(v); setErrors((p) => ({ ...p, workAuth: undefined })); }}>
                          {v === "yes" ? "Yes" : "No"}
                        </Choice>
                      ))}
                    </div>
                    <Err msg={errors.workAuth} />
                  </div>
                </div>
              </>
            )}
          </motion.div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20, marginTop: 30, position: "relative", zIndex: 1 }}>
          <button
            type="button" onClick={advance} disabled={status === "busy"}
            data-cta-id={screen === LAST ? "apply_submit" : `apply_screen_${screen}`}
            data-cta-location="final_cta" data-cta-type="contact" data-cta-style="primary"
            className="rounded-pill"
            style={{
              background: "var(--ink)", color: "var(--paper)", border: "none",
              padding: "13px 32px", fontSize: 15, fontWeight: 600,
              cursor: status === "busy" ? "default" : "pointer",
              opacity: status === "busy" ? 0.6 : 1, fontFamily: "inherit", transition: "opacity 90ms ease",
            }}
          >
            {status === "busy" ? "Sending…" : screen === LAST ? "Send it" : screen === 0 ? "Start" : "Continue"}
          </button>
          {screen > entryScreen && status !== "busy" && (
            <button type="button" onClick={back}
              style={{ background: "none", border: "none", color: "var(--ink-2)", fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>
              Back
            </button>
          )}
        </div>

        {screen === entryScreen && (
          <p style={{ fontSize: 12.5, color: "var(--ink-2)", margin: "16px 0 0" }}>
            Your answers save automatically.
          </p>
        )}

        {/* Honeypot. Hidden from sight AND from assistive tech, off the tab
            order, and never autofilled — so no human can reach it, while a
            form-filling bot sets it and is silently discarded server-side. */}
        <div aria-hidden="true" style={{ position: "absolute", left: -9999, top: -9999, width: 1, height: 1, overflow: "hidden" }}>
          <label htmlFor="ap-company">Company</label>
          <input
            id="ap-company" name="company" type="text" tabIndex={-1}
            autoComplete="off" value={honeypot}
            onChange={(e) => setHoneypot(e.target.value)}
          />
        </div>

        <AnimatePresence>
          {serverError && (
            <motion.p role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              style={{ color: "var(--danger)", fontSize: 14, marginTop: 14 }}>
              {serverError}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
