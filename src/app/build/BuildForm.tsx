"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ease } from "@/lib/animation";
import { CalendarEmbed } from "./CalendarEmbed";
import { LocationInput } from "./LocationInput";
import { VoiceInput } from "./VoiceInput";
import { Flash } from "./Flash";
import { useViewport } from "./useViewport";
import { suggestEmail } from "@/lib/email-check";
import { Tm } from "@/components/Tm";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const URL_RE = /^https?:\/\/[^\s.]+\.[^\s]{2,}$/i;
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXT = /\.(pdf|doc|docx|png|jpe?g|webp|heic|heif|gif|mp4|mov)$/i;

/** Screen 0 is the intro and carries no progress. */
const STEPS = ["You", "Where", "The work", "More", "Proof"] as const;

/**
 * Progress fill, front-loaded on purpose.
 *
 * A 32-experiment meta-analysis found linear progress bars have no effect on
 * dropout, fast-to-slow bars cut it by about 20%, and slow-to-fast bars raise
 * the odds of dropout by 1.56x. A naive "20% per screen" bar is a slow-to-fast
 * bar in disguise here, because screen 3 carries most of the actual work — the
 * bar would stall exactly where the effort is. These values move quickly early
 * and slow as the remaining work shrinks.
 */
const FILL = [0.3, 0.55, 0.76, 0.9, 1];

/** iOS zooms the page when a focused input is under 16px, which breaks a fixed layout. */
const MIN_INPUT_PX = 16;

const rule = (focused: boolean, invalid: boolean): React.CSSProperties => ({
  background: "transparent",
  border: "none",
  borderBottom: `1px solid ${invalid ? "#C97E7E" : focused ? "var(--gold)" : "var(--dark-border)"}`,
  color: "var(--text-on-dark)",
  padding: "10px 0 12px",
  fontSize: 18,
  width: "100%",
  outline: "none",
  transition: "border-color 220ms ease",
  fontFamily: "inherit",
  borderRadius: 0,
});

function Q({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="font-serif ap-q"
      style={{
        fontSize: "clamp(25px, 3.4vw, 36px)",
        lineHeight: 1.14,
        letterSpacing: "-0.02em",
        margin: "0 0 10px",
        color: "var(--text-on-dark)",
      }}
    >
      {children}
    </h2>
  );
}

function Sub({ children }: { children: React.ReactNode }) {
  return (
    <p className="ap-sub" style={{ color: "var(--text-on-dark-muted)", fontSize: 15, lineHeight: 1.6, margin: "0 0 26px", maxWidth: 520 }}>
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
          style={{ color: "#C97E7E", fontSize: 13, marginTop: 8 }}
        >
          {msg}
        </motion.p>
      )}
    </AnimatePresence>
  );
}

export function BuildForm() {
  useViewport();

  const [screen, setScreen] = useState(0); // 0 = intro, 1..5 = steps
  const [flashing, setFlashing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [emailFix, setEmailFix] = useState<string | null>(null);
  const [location, setLocation] = useState("");
  const [thing1, setThing1] = useState("");
  const [thing2, setThing2] = useState("");
  const [link, setLink] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [spoken, setSpoken] = useState<Set<string>>(new Set());

  const fileRef = useRef<HTMLInputElement>(null);
  const startedAt = useRef(0);
  const paneRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  // Focus the first field of each step — but never on the intro, and never on
  // touch, where forcing the keyboard open on arrival is hostile and also
  // resizes the viewport before the person has read the question.
  useEffect(() => {
    if (done || screen === 0) return;
    const coarse = window.matchMedia?.("(pointer: coarse)").matches;
    if (coarse) return;
    const t = window.setTimeout(() => {
      paneRef.current?.querySelector<HTMLElement>("input, textarea")?.focus();
    }, 300);
    return () => window.clearTimeout(t);
  }, [screen, done]);

  const bind = (k: string) => ({
    onFocus: () => setFocus(k),
    onBlur: () => setFocus((f) => (f === k ? null : f)),
  });

  const validate = useCallback(
    (s: number) => {
      const e: Partial<Record<string, string>> = {};
      if (s === 1) {
        if (!name.trim()) e.name = "Required.";
        if (!email.trim()) e.email = "Required.";
        else if (!EMAIL_RE.test(email.trim())) e.email = "That doesn't look right.";
      }
      if (s === 2 && !location.trim()) e.location = "Required.";
      if (s === 3 && !thing1.trim()) e.thing1 = "This one we need.";
      if (s === 5 && link.trim() && !URL_RE.test(link.trim())) e.link = "That doesn't look like a link.";
      return e;
    },
    [name, email, location, thing1, link]
  );

  /** 260ms cut; the screen swaps at 90ms, underneath the flash. */
  const go = (next: number) => {
    setFlashing(true);
    window.setTimeout(() => setScreen(next), 90);
    window.setTimeout(() => setFlashing(false), 280);
  };

  const advance = () => {
    const e = validate(screen);
    setErrors(e);
    if (Object.keys(e).length) return;
    if (screen < STEPS.length) go(screen + 1);
    else void submit();
  };

  const back = () => {
    setErrors({});
    go(Math.max(0, screen - 1));
  };

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
    setBusy(true);
    const fd = new FormData();
    fd.set("name", name.trim());
    fd.set("email", email.trim());
    fd.set("location", location.trim());
    fd.set("thing1", thing1.trim());
    fd.set("thing1Extra", "");
    // The second thing is optional now. The API still requires a non-empty
    // thing2, so an unanswered screen sends an explicit marker rather than a
    // blank that would read as a validation failure.
    fd.set("thing2", thing2.trim() || "(not provided)");
    fd.set("thing2Extra", "");
    fd.set("resumeLink", link.trim());
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
        setBusy(false);
        setServerError(data.error || "Something went wrong. Try again.");
        return;
      }
      setFlashing(true);
      window.setTimeout(() => { setDone(true); setBusy(false); }, 100);
      window.setTimeout(() => setFlashing(false), 300);
    } catch {
      setBusy(false);
      setServerError("Network error. Try again.");
    }
  };

  // ── Screen shell ─────────────────────────────────────────────
  // height is the MEASURED viewport, and the panel scrolls internally rather
  // than being clipped. `overflow:hidden` alone would fit the screen and fail
  // WCAG reflow the moment somebody zooms — content would be unreachable.
  // Here nothing scrolls in the normal case, and in the degraded ones (zoom,
  // keyboard open, short landscape) it becomes a scrollable panel instead.
  const shell: React.CSSProperties = {
    height: "var(--app-h, 100dvh)",
    overflowY: "auto",
    overflowX: "hidden",
    display: "flex",
    flexDirection: "column",
    padding: "0 24px",
    WebkitOverflowScrolling: "touch",
  };
  // Auto margins rather than justify-content:center — centring with
  // justify-content makes overflow unreachable above the fold.
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

  // ── Done ─────────────────────────────────────────────────────
  if (done) {
    return (
      <div style={{ ...shell, overflowY: "auto" }}>
        <Flash active={flashing} />

      {/* On a short viewport — a phone held sideways, or a small laptop with
          the keyboard open — the default rhythm pushes Continue below the
          fold. The panel already degrades to scrolling rather than clipping,
          but having to hunt for the button is still bad. These rules tighten
          the spacing so the whole screen fits instead. !important because the
          values they override are inline styles. */}
      <style>{`
        @media (max-height: 560px) {
          .ap-inner { padding-top: 14px !important; padding-bottom: 14px !important; }
          .ap-brand { margin-bottom: 14px !important; }
          .ap-q { font-size: 21px !important; margin-bottom: 6px !important; }
          .ap-sub { margin-bottom: 16px !important; font-size: 14px !important; }
          .ap-inner textarea { max-height: 22vh !important; }
        }
        @media (max-height: 430px) {
          .ap-q { font-size: 18px !important; }
          .ap-sub { display: none !important; }
        }
      `}</style>
        <div style={{ ...inner, marginTop: 40, marginBottom: 40 }}>
          <motion.div
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.8, ease, delay: 0.05 }}
            style={{ height: 1, background: "var(--gold)", transformOrigin: "left", marginBottom: 28 }}
          />
          <motion.h2
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease, delay: 0.2 }}
            className="font-serif"
            style={{ fontSize: "clamp(27px, 3.8vw, 40px)", lineHeight: 1.14, letterSpacing: "-0.02em", margin: 0 }}
          >
            Your application really stood out from the pile.
          </motion.h2>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease, delay: 0.38 }}
          >
            <p style={{ color: "var(--text-on-dark)", fontSize: 17, lineHeight: 1.7, margin: "18px 0 0", maxWidth: 560 }}>
              Here&apos;s Omar&apos;s personal calendar — the founder, not a
              recruiter and not a screening round. Take the first slot you can.
            </p>
            <CalendarEmbed />
          </motion.div>
        </div>
      </div>
    );
  }

  const last = screen === STEPS.length;

  return (
    <div style={shell} onKeyDown={onKeyDown}>
      <Flash active={flashing} />

      <div style={inner} className="ap-inner">
        {/* Wordmark — the only chrome. */}
        <div className="ap-brand" style={{ marginBottom: screen === 0 ? 40 : 30 }}>
          <a
            href="/"
            className="font-serif"
            style={{ fontSize: 19, color: "var(--gold)", textDecoration: "none", letterSpacing: "0.02em" }}
          >
            Anticipy
            <Tm />
          </a>
        </div>

        {screen > 0 && (
          <div style={{ marginBottom: 34 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
              <span className="tracking-wide-label" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--gold)" }}>
                {STEPS[screen - 1]}
              </span>
              <span style={{ fontSize: 10.5, color: "#5A5A5A" }}>
                {screen} / {STEPS.length}
              </span>
            </div>
            <div style={{ height: 1, background: "var(--dark-border)", position: "relative" }}>
              <motion.div
                animate={{ scaleX: FILL[screen - 1] }}
                initial={false}
                transition={{ duration: 0.32, ease, delay: 0.12 }}
                style={{ position: "absolute", inset: 0, background: "var(--gold)", transformOrigin: "left" }}
              />
            </div>
          </div>
        )}

        {/* Deliberately NOT AnimatePresence with mode="wait". That gates the
            next screen on the previous one's EXIT animation finishing, so
            anything which stalls that animation leaves the form frozen with
            the old question on screen and no fields — observed directly in a
            backgrounded tab, where animation frames pause. Keying a plain
            motion.div swaps immediately and replays the entry fade, and the
            flash covers the change anyway, so the exit was buying nothing. */}
        <div>
          <motion.div
            key={screen}
            ref={paneRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.14, ease }}
          >
            {screen === 0 && (
              <>
                <h1
                  className="font-serif"
                  style={{
                    fontSize: "clamp(32px, 5.4vw, 58px)",
                    lineHeight: 1.06,
                    letterSpacing: "-0.03em",
                    margin: 0,
                    color: "var(--text-on-dark)",
                  }}
                >
                  Built something that shouldn&apos;t have worked?
                </h1>
                <p style={{ fontSize: "clamp(16px, 2vw, 19px)", lineHeight: 1.6, color: "var(--text-on-dark)", margin: "22px 0 0", maxWidth: 560 }}>
                  Anticipy is looking for one hardware + software builder to own
                  a tiny connected product from board to factory.
                </p>
                <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--text-on-dark-muted)", margin: "18px 0 0", maxWidth: 560 }}>
                  You&apos;re probably right for this if you&apos;ve personally
                  designed custom electronics, written embedded firmware,
                  connected hardware to phones, and fixed the ugly problems that
                  appear when a prototype becomes a manufactured product. We
                  don&apos;t care about school or titles. We care about what you
                  built and what was actually yours.
                </p>
              </>
            )}

            {screen === 1 && (
              <>
                <Q>First — who are you?</Q>
                <Sub>Name and email. That&apos;s the whole screen.</Sub>
                <div style={{ display: "grid", gap: 26 }}>
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
                      onChange={(e) => { setEmail(e.target.value); setEmailFix(null); }}
                      onFocus={() => setFocus("email")}
                      onBlur={() => { setFocus(null); setEmailFix(suggestEmail(email.trim())); }}
                      placeholder="Email"
                      autoComplete="email"
                      aria-label="Email"
                      style={rule(focus === "email", !!errors.email)}
                    />
                    <Err msg={errors.email} />
                    {emailFix && (
                      <button
                        type="button"
                        onClick={() => { setEmail(emailFix); setEmailFix(null); }}
                        style={{ background: "none", border: "none", color: "var(--gold)", fontSize: 13, padding: "9px 0 0", cursor: "pointer", fontFamily: "inherit" }}
                      >
                        Did you mean {emailFix}?
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}

            {screen === 2 && (
              <>
                <Q>Where are you?</Q>
                <Sub>Start typing — we&apos;ll find it.</Sub>
                <LocationInput
                  value={location}
                  onChange={(v) => { setLocation(v); setErrors((p) => ({ ...p, location: undefined })); }}
                  invalid={!!errors.location}
                  onEnterWhenClosed={advance}
                />
                <Err msg={errors.location} />
              </>
            )}

            {screen === 3 && (
              <>
                <Q>Tell us a bit more about what you built.</Q>
                <Sub>
                  What was it, what was actually yours, and where can we see it?
                  Type it, or press the button and just talk — we&apos;ll write
                  it down for you.
                </Sub>
                <textarea
                  value={thing1}
                  onChange={(e) => setThing1(e.target.value)}
                  rows={5}
                  aria-label="What you built"
                  style={{ ...rule(focus === "t1", !!errors.thing1), fontSize: MIN_INPUT_PX, lineHeight: 1.6, resize: "none", maxHeight: "32vh", overflowY: "auto" }}
                  {...bind("t1")}
                />
                <VoiceInput onText={(t) => { setThing1((v) => (v ? `${v} ${t}` : t)); setSpoken((s) => new Set(s).add("thing1")); }} />
                <Err msg={errors.thing1} />
              </>
            )}

            {screen === 4 && (
              <>
                <Q>Anything else you&apos;ve built you&apos;d like to tell us about?</Q>
                <Sub>Optional. If not, just skip.</Sub>
                <textarea
                  value={thing2}
                  onChange={(e) => setThing2(e.target.value)}
                  rows={5}
                  aria-label="Anything else you built"
                  style={{ ...rule(focus === "t2", false), fontSize: MIN_INPUT_PX, lineHeight: 1.6, resize: "none", maxHeight: "32vh", overflowY: "auto" }}
                  {...bind("t2")}
                />
                <VoiceInput onText={(t) => { setThing2((v) => (v ? `${v} ${t}` : t)); setSpoken((s) => new Set(s).add("thing2")); }} />
              </>
            )}

            {screen === 5 && (
              <>
                <Q>Got anything that shows it working?</Q>
                <Sub>
                  A photo of the board, a GitHub repo, a video of the thing
                  running, a schematic, a PDF. Whatever proves it was real.
                  Optional — what you wrote matters more.
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
                  style={{ ...rule(false, !!errors.files), display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", textAlign: "left", fontSize: MIN_INPUT_PX, color: "var(--text-on-dark-muted)" }}
                >
                  <span>{files.length ? `${files.length} file${files.length > 1 ? "s" : ""}` : "Photos, video, PDF"}</span>
                  <span style={{ color: "var(--gold)", fontSize: 13 }}>Add</span>
                </button>
                <Err msg={errors.files} />

                {files.length > 0 && (
                  <ul style={{ listStyle: "none", padding: 0, margin: "12px 0 0", maxHeight: "18vh", overflowY: "auto" }}>
                    {files.map((f, i) => (
                      <li key={`${f.name}-${i}`} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--text-on-dark-muted)", padding: "6px 0" }}>
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
                        <button type="button" onClick={() => setFiles((p) => p.filter((_, j) => j !== i))} style={{ background: "none", border: "none", color: "#6A6A6A", cursor: "pointer", fontSize: 13, fontFamily: "inherit" }}>Remove</button>
                      </li>
                    ))}
                  </ul>
                )}

                <div style={{ marginTop: 22 }}>
                  <input
                    value={link}
                    onChange={(e) => setLink(e.target.value)}
                    placeholder="…or paste a link"
                    inputMode="url"
                    aria-label="A link to your work"
                    style={rule(focus === "link", !!errors.link)}
                    {...bind("link")}
                  />
                  <Err msg={errors.link} />
                </div>
              </>
            )}
          </motion.div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20, marginTop: 32 }}>
          <button
            type="button"
            onClick={advance}
            disabled={busy}
            data-cta-id={last ? "build_submit" : `build_screen_${screen}`}
            data-cta-location="final_cta"
            data-cta-type="contact"
            data-cta-style="primary"
            className="rounded-pill"
            style={{
              background: "var(--gold)",
              color: "var(--dark)",
              border: "none",
              padding: "13px 32px",
              fontSize: 15,
              fontWeight: 600,
              cursor: busy ? "default" : "pointer",
              opacity: busy ? 0.6 : 1,
              fontFamily: "inherit",
              transition: "opacity 90ms ease",
            }}
          >
            {busy ? "Sending…" : last ? "Show us what you built" : screen === 0 ? "Start" : "Continue"}
          </button>

          {screen > 0 && !busy && (
            <button type="button" onClick={back} style={{ background: "none", border: "none", color: "var(--text-on-dark-muted)", fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>
              Back
            </button>
          )}

          {(screen === 4 || (screen === 5 && !files.length && !link.trim())) && (
            <button type="button" onClick={advance} style={{ background: "none", border: "none", color: "#5A5A5A", fontSize: 14, cursor: "pointer", marginLeft: "auto", fontFamily: "inherit" }}>
              Skip
            </button>
          )}
        </div>

        <AnimatePresence>
          {serverError && (
            <motion.p role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ color: "#C97E7E", fontSize: 14, marginTop: 14 }}>
              {serverError}
            </motion.p>
          )}
        </AnimatePresence>

        {screen === 0 && (
          <p style={{ fontSize: 12.5, lineHeight: 1.65, color: "#5A5A5A", margin: "34px 0 0", maxWidth: 560 }}>
            Initial paid engagement: US$3,000–$4,000/month, depending on scope
            and availability. A longer-term founding-team position may include
            equity.
          </p>
        )}
      </div>
    </div>
  );
}
