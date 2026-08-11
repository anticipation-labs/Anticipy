"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ease } from "@/lib/animation";
import { LocationInput } from "@/components/apply/LocationInput";
import { VoiceInput } from "@/components/apply/VoiceInput";
import { Flash } from "@/components/apply/Flash";
import { useViewport } from "@/components/apply/useViewport";
import { APPLY_BUTTON_CSS } from "@/components/apply/ApplyButton";
import { suggestEmail } from "@/lib/email-check";
import { Tm } from "@/components/Tm";
import {
  PAY_LINES,
  UGC_QUESTIONS,
  SOCIALS,
  PAYOUT_METHODS,
  AGREEMENTS,
  LINK_BASE,
  HANDLE_RULES,
  normalizeHandle,
  validateHandle,
} from "../program";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const MIN_INPUT_PX = 16;

// 0 intro · 1 you · 2 channels · 3..6 questions · 7 link · 8 paid + terms
const LAST = 8;
const FIRST_Q = 3;

const SAVE_KEY = "anticipy.ugc.v1";
const SAVE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

interface Saved {
  t: number;
  screen: number;
  name: string;
  email: string;
  location: string;
  socials: Record<string, string>;
  answers: Record<string, string>;
  handle: string;
  payoutMethod: string;
  payoutDetail: string;
  spoken: string[];
}

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
      }}
    >
      {children}
    </button>
  );
}

type Status = "idle" | "busy" | "done";
type HandleState = "idle" | "checking" | "free" | "taken" | "invalid";

export function UgcForm() {
  useViewport();

  const [ready, setReady] = useState(false);
  const [screen, setScreen] = useState(0);
  const [flashing, setFlashing] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [emailFix, setEmailFix] = useState<string | null>(null);
  const [location, setLocation] = useState("");
  const [socials, setSocials] = useState<Record<string, string>>({});
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [handle, setHandle] = useState("");
  const [handleState, setHandleState] = useState<HandleState>("idle");
  const [handleMsg, setHandleMsg] = useState<string | null>(null);
  const [payoutMethod, setPayoutMethod] = useState("");
  const [payoutDetail, setPayoutDetail] = useState("");
  const [agreed, setAgreed] = useState<Record<string, boolean>>({});
  const [spoken, setSpoken] = useState<Set<string>>(new Set());
  const [honeypot, setHoneypot] = useState("");

  const startedAt = useRef(0);
  const paneRef = useRef<HTMLDivElement>(null);

  // ── Restore ───────────────────────────────────────────────────────
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
      /* unusable storage — start clean */
    }
    if (restored) {
      setName(restored.name || "");
      setEmail(restored.email || "");
      setLocation(restored.location || "");
      setSocials(restored.socials || {});
      setAnswers(restored.answers || {});
      setHandle(restored.handle || "");
      setPayoutMethod(restored.payoutMethod || "");
      setPayoutDetail(restored.payoutDetail || "");
      setSpoken(new Set(restored.spoken || []));
    }
    const start = restored ? Math.min(Math.max(restored.screen ?? 0, 0), LAST) : 0;
    setScreen(start);
    setReady(true);
    window.history.replaceState({ ugcStep: start }, "");
  }, []);

  const save = useCallback(() => {
    if (!ready) return;
    const payload: Saved = {
      t: Date.now(),
      screen,
      name,
      email,
      location,
      socials,
      answers,
      handle,
      payoutMethod,
      payoutDetail,
      spoken: Array.from(spoken),
    };
    try {
      window.localStorage.setItem(SAVE_KEY, JSON.stringify(payload));
    } catch {
      /* private mode — autosave is a convenience, never a blocker */
    }
  }, [ready, screen, name, email, location, socials, answers, handle, payoutMethod, payoutDetail, spoken]);

  useEffect(() => {
    save();
  }, [screen, save]);

  useEffect(() => {
    const onPop = (e: PopStateEvent) => {
      const step = (e.state as { ugcStep?: number } | null)?.ugcStep;
      if (typeof step === "number") {
        setErrors({});
        setScreen(step);
      }
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

  // ── Live handle availability ──────────────────────────────────────
  // Debounced, and every response is checked against the value still in the
  // box — a slow reply for an earlier keystroke must not overwrite the
  // verdict for what the creator has actually typed.
  useEffect(() => {
    if (screen !== 7) return;
    const h = normalizeHandle(handle);
    if (!h) {
      setHandleState("idle");
      setHandleMsg(null);
      return;
    }
    const invalid = validateHandle(h);
    if (invalid) {
      setHandleState("invalid");
      setHandleMsg(invalid);
      return;
    }
    setHandleState("checking");
    setHandleMsg(null);
    const ctrl = new AbortController();
    const t = window.setTimeout(async () => {
      try {
        const res = await fetch(`/api/ugc?handle=${encodeURIComponent(h)}`, { signal: ctrl.signal });
        const data = await res.json();
        if (normalizeHandle(handle) !== h) return;
        if (data.available === true) {
          setHandleState("free");
          setHandleMsg(null);
        } else if (data.available === false) {
          setHandleState("taken");
          setHandleMsg(data.error || "That link is already taken.");
        } else {
          setHandleState("idle");
          setHandleMsg(null);
        }
      } catch {
        // Aborted or offline. Leave it unresolved rather than claiming free.
        setHandleState("idle");
      }
    }, 400);
    return () => {
      ctrl.abort();
      window.clearTimeout(t);
    };
  }, [handle, screen]);

  const setAnswer = useCallback(
    (id: string, v: string) => setAnswers((a) => ({ ...a, [id]: v })),
    []
  );
  const bind = (k: string) => ({
    onFocus: () => setFocus(k),
    onBlur: () => {
      setFocus((f) => (f === k ? null : f));
      save();
    },
  });

  const validate = (s: number) => {
    const e: Partial<Record<string, string>> = {};
    if (s === 1) {
      if (!name.trim()) e.name = "Required.";
      if (!email.trim()) e.email = "Required.";
      else if (!EMAIL_RE.test(email.trim())) e.email = "That doesn't look right.";
      if (!location.trim()) e.location = "Required.";
    }
    if (s === 2 && !SOCIALS.some((x) => (socials[x.id] || "").trim())) {
      e.socials = "Add at least one — we need somewhere to check the view count.";
    }
    if (s >= FIRST_Q && s <= FIRST_Q + 3) {
      const q = UGC_QUESTIONS[s - FIRST_Q];
      const optional = s === FIRST_Q + 3;
      if (q && !optional && !(answers[q.id] || "").trim()) e[q.id] = "This one we need.";
    }
    if (s === 7) {
      const h = normalizeHandle(handle);
      const bad = validateHandle(h);
      if (!h) e.handle = "Pick your link.";
      else if (bad) e.handle = bad;
      else if (handleState === "taken") e.handle = "That link is already taken.";
    }
    if (s === 8) {
      if (!payoutMethod) e.payoutMethod = "Pick one.";
      if (!payoutDetail.trim()) e.payoutDetail = "Required — this is where the money goes.";
      if (!agreed.disclosure) e.disclosure = "Required.";
      if (!agreed.rights) e.rights = "Required.";
    }
    return e;
  };

  const go = (next: number) => {
    setFlashing(true);
    window.history.pushState({ ugcStep: next }, "");
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

  const back = () => window.history.back();

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Enter") return;
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "TEXTAREA" && !(e.metaKey || e.ctrlKey)) return;
    e.preventDefault();
    advance();
  };

  const submit = async () => {
    setServerError(null);
    setStatus("busy");
    const fd = new FormData();
    fd.set("name", name.trim());
    fd.set("email", email.trim());
    fd.set("location", location.trim());
    for (const s of SOCIALS) fd.set(s.id, (socials[s.id] || "").trim());
    fd.set(
      "answers",
      JSON.stringify(UGC_QUESTIONS.map((q) => ({ id: q.id, answer: (answers[q.id] || "").trim() })))
    );
    fd.set("handle", normalizeHandle(handle));
    fd.set("payoutMethod", payoutMethod);
    fd.set("payoutDetail", payoutDetail.trim());
    fd.set("agreedDisclosure", agreed.disclosure ? "yes" : "no");
    fd.set("agreedRights", agreed.rights ? "yes" : "no");
    fd.set("spokenFields", Array.from(spoken).join(","));
    fd.set("startedAt", String(startedAt.current));
    fd.set("company", honeypot);

    const p = new URLSearchParams(window.location.search);
    fd.set("utmSource", p.get("utm_source") ?? "");
    fd.set("utmMedium", p.get("utm_medium") ?? "");
    fd.set("utmCampaign", p.get("utm_campaign") ?? "");
    fd.set("referrer", document.referrer || "");
    fd.set("landingPath", window.location.pathname + window.location.search);

    try {
      const res = await fetch("/api/ugc", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setStatus("idle");
        setServerError(data.error || "Something went wrong. Try again.");
        // A link taken between choosing it and submitting sends them back to
        // the one screen that can fix it, rather than stranding them here.
        if (Array.isArray(data.fields) && data.fields.includes("handle")) {
          setErrors({ handle: data.error });
          setHandleState("taken");
          go(7);
        }
        return;
      }
      try {
        window.localStorage.removeItem(SAVE_KEY);
      } catch {
        /* nothing to do */
      }
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
    <div className="ap-brand" style={{ marginBottom: screen === 0 ? 32 : 26 }}>
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
    const link = `${LINK_BASE}${normalizeHandle(handle)}`;
    return (
      <div style={shell}>
        <Flash active={flashing} />
        <div style={{ ...inner, marginTop: 40, marginBottom: 40 }}>
          <motion.div
            initial={{ scaleX: 0 }} animate={{ scaleX: 1 }}
            transition={{ duration: 0.8, ease, delay: 0.05 }}
            style={{ height: 2, background: "var(--accent)", transformOrigin: "left", marginBottom: 26 }}
          />
          <h2 className="font-serif" style={{ fontSize: "clamp(27px, 3.8vw, 40px)", lineHeight: 1.12, letterSpacing: "-0.02em", margin: 0, color: "var(--ink)" }}>
            You&apos;re in. Here&apos;s your link.
          </h2>

          <p className="ugc-link" style={{ fontFamily: "var(--mono)", fontSize: "clamp(18px, 3vw, 26px)", color: "var(--ink)", margin: "24px 0 0", wordBreak: "break-all" }}>
            {link}
          </p>
          <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--ink-2)", margin: "12px 0 0" }}>
            It&apos;s live now. Put it in your bio before you post anything —
            a video without it earns the flat fee and nothing else.
          </p>

          <div style={{ height: 1, background: "var(--rule)", margin: "30px 0 26px" }} />

          <h3 className="font-serif" style={{ fontSize: 21, letterSpacing: "-0.015em", margin: "0 0 14px", color: "var(--ink)" }}>
            Go make the first one
          </h3>
          <ol className="ugc-steps">
            <li><span>01</span><span>Film it. Anything you&apos;d actually watch to the end.</span></li>
            <li><span>02</span><span>Post it, tag <strong>@anticipy</strong>, and label it as an ad.</span></li>
            <li><span>03</span><span>Send me the link. At 1,000 views I pay the $25.</span></li>
          </ol>

          <p style={{ fontSize: 14, lineHeight: 1.7, color: "var(--ink-2)", margin: "26px 0 0" }}>
            A copy of all this is in your inbox. Reply to it any time — it
            reaches Omar directly.
          </p>
        </div>
      </div>
    );
  }

  const q = screen >= FIRST_Q && screen <= FIRST_Q + 3 ? UGC_QUESTIONS[screen - FIRST_Q] : null;
  const stepLabel = ["", "You", "Channels", "1 of 4", "2 of 4", "3 of 4", "4 of 4", "Your link", "Getting paid"][screen];
  const FILL = [0, 0.16, 0.3, 0.44, 0.56, 0.67, 0.77, 0.88, 1];
  const cleanHandle = normalizeHandle(handle);

  return (
    <div style={shell} onKeyDown={onKeyDown}>
      <Flash active={flashing} />
      <style dangerouslySetInnerHTML={{ __html: `
        ${APPLY_BUTTON_CSS}
        .ap-inner textarea::placeholder, .ap-inner input::placeholder { color: #9A948A; }
        .ugc-pay { list-style: none; margin: 26px 0 0; padding: 0; display: grid; gap: 14px; }
        .ugc-pay li { display: grid; grid-template-columns: 62px 1fr; gap: 16px; align-items: baseline; }
        .ugc-pay b { font-family: var(--mono); font-size: 19px; color: var(--ink); font-weight: 600; }
        .ugc-pay span { font-size: 15px; line-height: 1.55; color: var(--ink-2); }
        .ugc-pay strong { color: var(--ink); font-weight: 600; }
        .ugc-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
        .ugc-steps li { display: flex; gap: 16px; font-size: 15.5px; line-height: 1.6; color: var(--ink); }
        .ugc-steps li span:first-child { font-family: var(--mono); font-size: 11.5px; color: var(--accent-ink); padding-top: 4px; flex-shrink: 0; }
        .ugc-agree { display: flex; gap: 13px; align-items: flex-start; cursor: pointer; padding: 14px; border: 1px solid var(--rule); border-radius: 10px; background: #FFF; transition: border-color 160ms ease; }
        .ugc-agree:hover { border-color: var(--accent); }
        .ugc-agree input { margin: 3px 0 0; width: 17px; height: 17px; flex-shrink: 0; accent-color: var(--ink); }
        .ugc-agree b { display: block; font-size: 15px; font-weight: 600; color: var(--ink); margin-bottom: 4px; }
        .ugc-agree em { display: block; font-style: normal; font-size: 13px; line-height: 1.55; color: var(--ink-2); }
        @media (max-height: 560px) {
          .ap-inner { padding-top: 14px !important; padding-bottom: 14px !important; }
          .ap-brand { margin-bottom: 14px !important; }
          .ap-q { font-size: 20px !important; margin-bottom: 6px !important; }
          .ap-sub { margin-bottom: 14px !important; font-size: 14px !important; }
          .ap-inner textarea { max-height: 22vh !important; }
        }
        @media (max-width: 430px) {
          .ap-inner { padding-top: 18px !important; padding-bottom: 18px !important; }
          .ap-sub { margin-bottom: 16px !important; }
          .ugc-pay li { grid-template-columns: 56px 1fr; gap: 12px; }
        }
      ` }} />

      <div style={inner} className="ap-inner">
        {brand}

        {screen > 0 && (
          <div style={{ marginBottom: 28 }}>
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
                <p className="tracking-wide-label" style={{ fontFamily: "var(--mono)", fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--accent-ink)", margin: "0 0 14px" }}>
                  Anticipy UGC Creator
                </p>
                <h1 className="font-serif" style={{ fontSize: "clamp(30px, 5vw, 52px)", lineHeight: 1.04, letterSpacing: "-0.03em", margin: 0, color: "var(--ink)" }}>
                  Make videos. Get paid twice.
                </h1>
                <ul className="ugc-pay">
                  {PAY_LINES.map((l) => (
                    <li key={l.label}>
                      <b>{l.amount}</b>
                      <span><strong>{l.label}</strong> — {l.detail}</span>
                    </li>
                  ))}
                </ul>
                <p style={{ fontSize: 14.5, lineHeight: 1.7, color: "var(--ink-2)", margin: "24px 0 0" }}>
                  You&apos;ll pick your own link at the end. Takes about five
                  minutes, and your answers save as you go.
                </p>
              </>
            )}

            {screen === 1 && (
              <>
                <Q>First — who are you?</Q>
                <Sub>Name, email, and where you are.</Sub>
                <div style={{ display: "grid", gap: 22 }}>
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

            {screen === 2 && (
              <>
                <Q>Where do you post?</Q>
                <Sub>
                  At least one. We check view counts here, so it has to be
                  somewhere we can actually find the video.
                </Sub>
                <div style={{ display: "grid", gap: 18 }}>
                  {SOCIALS.map((s) => (
                    <div key={s.id}>
                      <span className="tracking-wide-label" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--ink-2)", display: "block", marginBottom: 4 }}>
                        {s.label}
                      </span>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                        {s.prefix && <span style={{ fontSize: 18, color: "var(--ink-2)" }}>{s.prefix}</span>}
                        <input
                          value={socials[s.id] || ""}
                          onChange={(e) => {
                            setSocials((p) => ({ ...p, [s.id]: e.target.value }));
                            setErrors((p) => ({ ...p, socials: undefined }));
                          }}
                          placeholder={s.placeholder}
                          aria-label={s.label}
                          style={rule(focus === s.id, false)}
                          {...bind(s.id)}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <Err msg={errors.socials} />
              </>
            )}

            {q && (
              <>
                <Q>{q.q}</Q>
                {q.hint && <Sub>{q.hint}</Sub>}
                <textarea
                  value={answers[q.id] || ""}
                  onChange={(e) => setAnswer(q.id, e.target.value)}
                  rows={5}
                  placeholder={q.placeholder}
                  aria-label={q.q}
                  style={{ ...box(focus === q.id, !!errors[q.id]), maxHeight: "34vh" }}
                  {...bind(q.id)}
                />
                <VoiceInput onText={(t) => { setAnswer(q.id, (answers[q.id] ? answers[q.id] + " " : "") + t); setSpoken((s) => new Set(s).add(q.id)); }} />
                <Err msg={errors[q.id]} />
              </>
            )}

            {screen === 7 && (
              <>
                <Q>Choose your link.</Q>
                <Sub>
                  This is what goes in your bio, and it&apos;s how every signup
                  and sale gets credited to you. Pick something you&apos;d be
                  happy saying out loud.
                </Sub>
                <div style={{ display: "flex", alignItems: "baseline", gap: 2, flexWrap: "wrap" }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 17, color: "var(--ink-2)" }}>{LINK_BASE}</span>
                  <input
                    value={handle}
                    onChange={(e) => { setHandle(e.target.value); setErrors((p) => ({ ...p, handle: undefined })); }}
                    placeholder="yourname"
                    aria-label="Your link"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    style={{
                      ...rule(focus === "handle", !!errors.handle || handleState === "taken"),
                      fontFamily: "var(--mono)",
                      fontSize: 17,
                      width: "auto",
                      minWidth: 160,
                      flex: 1,
                    }}
                    {...bind("handle")}
                  />
                </div>
                <p style={{ fontSize: 13, marginTop: 10, minHeight: 20, color: handleState === "free" ? "#2E6B4F" : handleState === "taken" || handleState === "invalid" ? "var(--danger)" : "var(--ink-2)" }}>
                  {handleState === "checking" && "Checking…"}
                  {handleState === "free" && `Yours: ${LINK_BASE}${cleanHandle}`}
                  {(handleState === "taken" || handleState === "invalid") && handleMsg}
                  {handleState === "idle" &&
                    (cleanHandle && !validateHandle(cleanHandle)
                      ? `Your link: ${LINK_BASE}${cleanHandle}`
                      : HANDLE_RULES.help)}
                </p>
                <Err msg={errors.handle} />
              </>
            )}

            {screen === 8 && (
              <>
                <Q>Last bit — getting paid.</Q>
                <Sub>And two things to agree to, both in plain English.</Sub>
                <div style={{ display: "grid", gap: 20 }}>
                  <div>
                    <span className="tracking-wide-label" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--ink-2)", display: "block", marginBottom: 8 }}>
                      How should we pay you?
                    </span>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {PAYOUT_METHODS.map((m) => (
                        <Choice key={m} active={payoutMethod === m} onClick={() => { setPayoutMethod(m); setErrors((p) => ({ ...p, payoutMethod: undefined })); }}>{m}</Choice>
                      ))}
                    </div>
                    <Err msg={errors.payoutMethod} />
                  </div>
                  <div>
                    <input
                      value={payoutDetail}
                      onChange={(e) => setPayoutDetail(e.target.value)}
                      placeholder={payoutMethod === "Interac e-Transfer" ? "Email for e-Transfer" : "Email on that account"}
                      aria-label="Payout account"
                      style={rule(focus === "payoutDetail", !!errors.payoutDetail)}
                      {...bind("payoutDetail")}
                    />
                    <Err msg={errors.payoutDetail} />
                  </div>

                  {Object.values(AGREEMENTS).map((a) => (
                    <div key={a.id}>
                      <label className="ugc-agree">
                        <input
                          type="checkbox"
                          checked={!!agreed[a.id]}
                          onChange={(e) => {
                            setAgreed((p) => ({ ...p, [a.id]: e.target.checked }));
                            setErrors((p) => ({ ...p, [a.id]: undefined }));
                          }}
                        />
                        <span>
                          <b>{a.label}</b>
                          <em>{a.detail}</em>
                        </span>
                      </label>
                      <Err msg={errors[a.id]} />
                    </div>
                  ))}
                </div>
              </>
            )}
          </motion.div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20, marginTop: 28, position: "relative", zIndex: 1 }}>
          <button
            type="button" onClick={advance} disabled={status === "busy"}
            data-cta-id={screen === LAST ? "ugc_submit" : `ugc_screen_${screen}`}
            data-cta-location="final_cta" data-cta-type="contact" data-cta-style="primary"
            className="rounded-pill"
            style={{
              background: "var(--ink)", color: "var(--paper)", border: "none",
              padding: screen === 0 ? "16px 34px" : "13px 32px",
              fontSize: screen === 0 ? 16.5 : 15, fontWeight: 600,
              cursor: status === "busy" ? "default" : "pointer",
              opacity: status === "busy" ? 0.6 : 1, fontFamily: "inherit", transition: "opacity 90ms ease",
            }}
          >
            {status === "busy" ? "Sending…" : screen === LAST ? "Get my link" : screen === 0 ? "Start — it takes 5 minutes" : "Continue"}
          </button>
          {screen > 0 && status !== "busy" && (
            <button type="button" onClick={back}
              style={{ background: "none", border: "none", color: "var(--ink-2)", fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>
              Back
            </button>
          )}
        </div>

        {screen === 0 && (
          <p style={{ fontSize: 12.5, color: "var(--ink-2)", margin: "16px 0 0" }}>
            Your answers save automatically.
          </p>
        )}

        {/* Honeypot — hidden from sight and from assistive tech, off the tab
            order, so only a form-filling bot ever reaches it. */}
        <div aria-hidden="true" style={{ position: "absolute", left: -9999, top: -9999, width: 1, height: 1, overflow: "hidden" }}>
          <label htmlFor="ugc-company">Company</label>
          <input id="ugc-company" name="company" type="text" tabIndex={-1} autoComplete="off" value={honeypot} onChange={(e) => setHoneypot(e.target.value)} />
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
