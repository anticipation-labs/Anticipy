"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createBrowserSupabaseClient } from "../../lib/supabase/client";
import { supabaseMissingMessage } from "../../lib/supabase/config";
import { FIXTURES, NAV_ITEMS, ONBOARDING_STAGES, SOURCE_TAGS, SOURCE_TRUTH_PATH } from "./sourceData";

// Hydration-safe debug gate. The old pattern `if (typeof window !== "undefined" && !pz-debug) return
// null` rendered on the SERVER (no window) but returned null on the CLIENT — a hydration mismatch that
// aborted React hydration and left every button dead. This renders null on the server AND the first
// client paint (so SSR HTML matches), then reveals only if body.pz-debug after mount.
function useDebugVisible() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try { setShow(document.body.classList.contains("pz-debug")); } catch { /* noop */ }
  }, []);
  return show;
}

// Humanize an engine-supplied title before it reaches the surface: drop implementation/vendor
// words, turn ASCII arrows into words, tidy whitespace — so a raw engine field can never render
// as developer text (UX_SPEC §4.8). Empty in → empty out; titles from the copy engine pass through.
const _IMPL_RE = /\b(arcade|openrouter|gemini|webvoyager|uvicorn|fastapi|supabase|localhost|cdp)\b/gi;
function humanTitle(text) {
  if (!text) return "";
  return String(text)
    .replace(/\s*->\s*/g, " then ")
    .replace(/\s*\([^)]*\)\s*$/g, (m) => (/\b(arcade|openrouter|gemini|webvoyager|twilio|cdp|supabase)\b/i.test(m) ? "" : m))
    .replace(_IMPL_RE, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,;:])/g, "$1")
    .trim();
}

// ── Conversation surface (2026-07-04) ─────────────────────────────────────────────────────────
// Anticipy talks BACK. The board's cards are the engine's real decisions; here we turn each one
// into a warm, plain-language message a person would actually text — the whole product is this
// back-and-forth, not a grid of dev cards. These helpers are pure presentation over the same
// engine fields (title / check-in / disposition); no engine logic changes.
function stripDot(text) {
  return String(text || "").replace(/\s*[.!?]+\s*$/, "").trim();
}

// One engine card -> the assistant's spoken reply + whether it needs a yes/no reaction.
//   do            -> a calm "Got it — I'm on it." (no chips; nothing to approve)
//   ask           -> the plan + the engine's own check-in line, with Go ahead / Not now chips
//   blocked/money -> the plan, flagged as needing an explicit yes, with chips
function assistantReplyForCard(card) {
  const title = stripDot(humanTitle(card.title)) || "I caught something for you";
  // Bug-3 (honest failure): a card the engine actually TRIED and could not finish — its status is a
  // terminal non-success and the board shows "Failed"/"Stopped" — must NEVER be narrated as "I'm on
  // it." These carry risk "do", so without this guard they fell straight through to the cheerful
  // on-it line below and lied about an action that errored. We report the snag honestly instead.
  // (A money/irreversible ask is disposition "blocked" with status "waiting" here — never "failed"
  // /"stopped" — so the money-yes branch below is left completely untouched.)
  if (card.status === "failed") {
    return { text: `I hit a snag on ${title} — want me to try again?`, chips: false, tone: "blocked" };
  }
  if (card.status === "stopped") {
    return { text: `I've stopped ${title}. Tell me if you want me to pick it back up.`, chips: false, tone: "do" };
  }
  // The owner said this one's finished ("I sent it already") — acknowledge the close, never re-nag.
  if (card.status === "done" || card.status === "completed") {
    return { text: `Nice — I've marked that one done: ${title}.`, chips: false, tone: "do" };
  }
  if (card.status === "superseded") {
    return { text: `Updated — I've swapped out the old version of ${title}.`, chips: false, tone: "do" };
  }
  if (card.risk === "blocked") {
    return {
      text: `${title}. That one can move money or can't easily be undone, so I'll wait for your yes — want me to go ahead?`,
      chips: true,
      tone: "blocked",
    };
  }
  if (card.risk === "ask" || card.askId) {
    const ask = (card.checkIn || "").trim() || "Okay for me to go ahead?";
    return { text: `${title}. ${ask}`, chips: true, tone: "ask" };
  }
  return { text: `Got it — ${title}. I'm on it.`, chips: false, tone: "do" };
}

let _threadSeq = 0;
function threadId() {
  _threadSeq += 1;
  return `m${Date.now().toString(36)}-${_threadSeq}`;
}

// A typed reply in the composer that is a short yes/no resolves the most recent waiting ask (the
// same as tapping a chip). Kept short-only so a real instruction ("make it shorter", "email Bob
// too") still flows to the brain as a new capture instead of being swallowed as an approval.
const YES_RE = /^\s*(y|yes+|yeah|yep|yup|ya|sure|ok|okay|kk?|go ahead|do it|please do|go for it|sounds good|send it|approve[d]?|yes please)\b/i;
const NO_RE = /^\s*(n|no+|nope|nah|not now|leave it|leave that|cancel|hold off|skip|don'?t|stop|not this one)\b/i;

// The ONLY engine statuses that count as a real terminal completion — the sole license for "Done ✓".
// Everything else (waiting/doing/recorded-for-later) means the work isn't finished, so we never
// claim it is. stopped/failed/declined are terminal but NOT success, so they're intentionally out.
const TERMINAL_DONE_STATUS = new Set(["done", "completed"]);

const EMPTY_PROFILE = {
  name: "",
  summary: "",
  phone: "",
  timezone: "America/Vancouver",
  trustDial: "Regular",
  textFirst: true,
  doNotTouch: "",
  people: [],
  roleContext: "",
  tools: [],
  openLoops: [],
  communicationStyle: "",
  rules: [],
  openQuestions: [],
  lastClarification: "",
};

const DEFAULT_SETTINGS = {
  autonomy: "Regular",
  confirmBefore: {
    money: true,
    sendToPerson: true,
    deleteOrShare: true,
    irreversible: true,
  },
  textCall: {
    textFirst: true,
    proofMirror: "coming_soon",
    phone: "",
  },
  listening: {
    browserMic: true,
    localMacMic: false,
    activeByDefault: false,
  },
  retention: {
    rawTranscriptDays: 7,
    promoteToMemory: "ask",
    redaction: "private-by-default",
  },
  browserHelper: {
    status: "checking",
  },
  security: {
    trustDial: "Regular",
    doNotTouch: "",
  },
};

const SHOW_FIXTURES = process.env.NEXT_PUBLIC_ANTICIPY_SHOW_FIXTURES === "1";

// Single-owner "open mode". While true (the pre-multi-user default) the board, onboarding, setup,
// and settings render without a Supabase session, so today's single-owner flow keeps working
// unchanged. At the multi-user deploy this flips off (NEXT_PUBLIC_ANTICIPY_APP_OPEN=0) in the SAME
// change that turns email login on, and the session gate in PhaseZeroApp takes effect. Only /welcome
// and /sign are ever public. Defaults OPEN so nothing breaks before that coordinated deploy.
const APP_OPEN = process.env.NEXT_PUBLIC_ANTICIPY_APP_OPEN !== "0";

const SCREEN_TITLES = {
  welcome: "Welcome",
  sign: "Sign in",
  setup: "Setup",
  board: "",
  memory: "Memory",
  settings: "Settings",
};

const JOURNEY_ITEMS = [
  { href: "/welcome", label: "Welcome", screens: ["welcome"] },
  { href: "/sign", label: "Sign", screens: ["sign"] },
  { href: "/onboarding/2", label: "You", screens: ["onboarding-2"] },
  { href: "/", label: "Listen", screens: ["board"] },
  { href: "/settings", label: "Settings", screens: ["settings"] },
];

const STATUS_COPY = {
  live: "Live",
  seeded: "Seeded",
  read_only: "Read-only",
  coming_soon: "Coming soon",
  ready: "Ready",
  listening: "Listening",
  stopped: "Stopped",
  unavailable: "Unavailable",
  permission_denied: "Permission denied",
  processing: "Processing",
  cards_created: "Cards created",
  no_task_created: "No task needed",
  observed: "Observed",
  understood: "Understood",
  needs_approval: "Needs approval",
  working: "Working",
  done: "Done",
  remembered: "Remembered",
  following_up: "Following up",
  blocked: "Blocked",
  failed: "Failed",
  ignored: "Ignored",
};

function humanStatus(value) {
  return STATUS_COPY[value] || value || "Seeded";
}

function isListeningStatus(data = {}) {
  return Boolean(data.running || data.listening);
}

// The signed-in user's Supabase access token, or "" when nobody is signed in. Every API call
// must carry it — the server routes a request WITH a user bearer to that user's OWN per-user
// core and a request without one to the owner core. Missing it here was the account-isolation
// leak: a signed-in user's board/profile/onboarding calls all landed on the shared owner brain.
async function sessionBearer() {
  try {
    const client = createBrowserSupabaseClient();
    if (!client) return "";
    const { data } = await client.auth.getSession();
    return data?.session?.access_token || "";
  } catch {
    return "";
  }
}

// The last few trace ids the server echoed back (x-anticipy-trace), newest first — one id per
// user action. Kept in sessionStorage so they survive board ↔ settings navigation; the trace
// view turns any of these into the full end-to-end replay of that action.
function recentTracesList() {
  try {
    return JSON.parse(sessionStorage.getItem("pz-recent-traces") || "[]");
  } catch {
    return [];
  }
}
function rememberTrace(url, response) {
  try {
    const trace = response?.headers?.get?.("x-anticipy-trace") || "";
    if (!trace) return;
    const rows = recentTracesList().filter((row) => row.trace !== trace);
    rows.unshift({ trace, url, at: new Date().toLocaleTimeString() });
    sessionStorage.setItem("pz-recent-traces", JSON.stringify(rows.slice(0, 12)));
  } catch { /* trace capture must never break a call */ }
}

async function jsonFetch(url, options = {}) {
  const bearer = await sessionBearer();
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "content-type": "application/json" }),
      ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
      ...(options.headers || {}),
    },
    credentials: "same-origin",
    cache: "no-store",
  });
  rememberTrace(url, response);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.message || data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function fixtureToCard(fixture) {
  return {
    id: fixture.id,
    category: fixture.category,
    title: fixture.caught,
    heard: fixture.heard,
    ignored: fixture.ignored,
    browserWork: fixture.browserWork,
    checkIn: fixture.checkIn,
    proof: fixture.proof,
    memory: fixture.memory,
    followUp: fixture.followUp,
    risk: fixture.risk,
    status: fixture.risk === "blocked" ? "blocked" : fixture.risk === "ask" ? "needs_approval" : "prepared",
    sourceTags: SOURCE_TAGS.slice(0, 5),
    mode: "seeded",
  };
}

// A1: pull the REAL browser receipt the engine landed on the card. control_core's
// _land_browser_result_on_card writes execution.proof = {type:"browser_receipt", url, answer,
// screenshot, screenshot_path}. We render the ACTUAL answer + URL + screenshot affordance from
// it instead of the old canned "Here's what I did." Only fields truly present are surfaced
// (honest proof — nothing invented).
function extractBrowserReceipt(card) {
  const receipt = card.execution?.proof;
  if (!receipt || typeof receipt !== "object" || receipt.type !== "browser_receipt") return null;
  const answer = typeof receipt.answer === "string" ? receipt.answer.trim() : "";
  const url = typeof receipt.url === "string" ? receipt.url.trim() : "";
  const screenshot = Boolean(receipt.screenshot);
  const screenshotPath = typeof receipt.screenshot_path === "string" ? receipt.screenshot_path.trim() : "";
  if (!answer && !url && !screenshot) return null;
  return { answer, url, screenshot, screenshotPath };
}

function normalizeEngineCard(card) {
  const gatewayTags = Array.isArray(card.gateway?.source_of_truth_tags)
    ? card.gateway.source_of_truth_tags
    : [];
  const browserReceipt = extractBrowserReceipt(card);
  return {
    id: card.id || card.ask_id || `engine-${Math.random().toString(16).slice(2)}`,
    // De-jargon (UI step 1): human-facing card copy, never engine internals. CANON/UI_FLOW law.
    category: card.disposition === "blocked" ? "Needs a yes" : card.status === "waiting" || card.disposition === "ask" ? "Waiting for you" : "On it",
    title: card.title || card.action || card.source_text || "Caught something for you.",
    heard: card.source_text || card.text || "",
    ignored: "",
    browserWork: card.args?.task_text || card.execution?.route || card.source_text || "",
    checkIn: card.status === "waiting" || card.disposition === "ask" ? "Okay for me to go ahead?" : "",
    // With a real browser receipt the structured render takes over; the string is only a fallback
    // for non-browser live cards (kept honest — no receipt means no fabricated answer).
    proof: browserReceipt ? "" : Array.isArray(card.proof) && card.proof.length ? "Here's what I did." : "",
    browserReceipt,
    memory: card.disposition === "remember" ? "I'll remember this." : "",
    followUp: card.status || card.disposition || "ready",
    risk: card.disposition === "blocked" || card.status === "blocked" ? "blocked" : card.disposition === "ask" || card.status === "waiting" ? "ask" : "do",
    status: card.status || "ready",
    askId: card.execution?.ask_id || card.ask_id || "",
    sourceTags: gatewayTags.length ? gatewayTags : ["ST-NO-FAKE-DONE", "OPS-BASIC-PLUMBING"],
    gatewayEventId: card.gateway_event_id || card.gateway?.event_id || "",
    browserGatewayEventId: card.browser_gateway_event_id || "",
    mode: "live",
    raw: card,
  };
}

function shortId(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function formatGatewayTime(ts) {
  if (!ts) return "";
  try {
    return new Date(Number(ts) * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

function StatusPill({ value }) {
  return <span className={`pz-pill pz-pill-${value}`}>{humanStatus(value)}</span>;
}

// De-jargon (UI step 1, 2026-07-02): engine-internal source tags (ST-*/OPS-*) must never reach a
// human surface — CANON/UI_FLOW law "zero jargon". Rendered only under ?debug.
function SourceTagList({ tags = SOURCE_TAGS.slice(0, 4) }) {
  const _dbgVisible = useDebugVisible();
  if (!_dbgVisible) return null;
  return (
    <div className="pz-tags pz-dev-tags" aria-label="Source truth tags" data-source-tags={tags.join(" ")}>
      {tags.map((tag) => (
        <span key={tag}>{tag}</span>
      ))}
    </div>
  );
}

function AppShell({ screen, children, profile, session, engineState }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const currentTitle = SCREEN_TITLES[screen] || "Anticipy";
  return (
    <main className="pz">
      <header className="pz-appbar">
        <a className="pz-brand" href="/welcome" aria-label="Anticipy welcome">
          <span>A</span>
          <strong>Anticipy</strong>
        </a>
        <div className="pz-appbar-center">
          <span className={`pz-dot ${engineState.ok ? "ok" : ""}`} />
          <span>{engineState.ok ? "ready" : "setting up"}</span>
        </div>
        <button className="pz-menu-button" type="button" onClick={() => setMenuOpen(true)} aria-label="Open navigation">
          <span />
          <span />
        </button>
      </header>
      {menuOpen ? (
        <div className="pz-drawer" role="dialog" aria-modal="true" aria-label="Anticipy menu">
          <button className="pz-drawer-backdrop" type="button" onClick={() => setMenuOpen(false)} aria-label="Close menu" />
          <nav className="pz-drawer-panel" aria-label="Phase Zero routes">
            <div className="pz-drawer-head">
              <strong>Move around</strong>
              <button type="button" onClick={() => setMenuOpen(false)}>Close</button>
            </div>
            {NAV_ITEMS.map((item) => {
              // S3 §3.5: any onboarding-* screen lights the single "Onboarding" destination.
              const isOnboarding = screen.startsWith("onboarding");
              const current =
                (screen === "board" && item.href === "/") ||
                (isOnboarding && item.href.startsWith("/onboarding")) ||
                (!isOnboarding && item.href !== "/onboarding/2" && item.href.includes(screen));
              return (
                <a key={item.href} className={current ? "active" : ""} href={item.href}>
                  <span>{item.label}</span>
                  <small>{item.href === "/" ? "Listen" : item.href}</small>
                </a>
              );
            })}
          </nav>
        </div>
      ) : null}
      <section className="pz-main">
        {screen !== "board" ? (
          <header className="pz-top" aria-label={currentTitle}>
            <div>
              <span className="pz-kicker">Vibe your life.</span>
              <h1>{currentTitle}</h1>
            </div>
            <div className="pz-user">
              <span>{session?.user?.email || profile.email || profile.name || "You"}</span>
            </div>
          </header>
        ) : null}
        {children}
        <JourneyRail screen={screen} />
      </section>
    </main>
  );
}

function JourneyRail({ screen }) {
  // Removed from the calm surface (UI step 1): the progress rail is dev-chrome. Debug-only.
  const _dbgVisible = useDebugVisible();
  if (!_dbgVisible) return null;
  return (
    <nav className="pz-journey" aria-label="Anticipy journey">
      {JOURNEY_ITEMS.map((item) => {
        const active = item.screens.includes(screen);
        return (
          <a key={item.href} className={active ? "active" : ""} href={item.href}>
            <span />
            <small>{item.label}</small>
          </a>
        );
      })}
    </nav>
  );
}

function WelcomeScreen() {
  return (
    <main className="pz-land">
      <header className="pz-land-bar">
        <span className="pz-land-wordmark">Anticipy</span>
        <a className="pz-land-cta pz-land-cta-sm" href="/sign">Come in</a>
      </header>

      <section className="pz-land-hero">
        <div className="pz-land-glow" aria-hidden="true" />
        <span className="pz-land-kicker">Vibe your life.</span>
        <h1>I listen to your day and quietly handle the small stuff.</h1>
        <p className="pz-land-sub">
          I draft — you approve. I never send anything without you.
        </p>
        <div className="pz-land-hero-actions">
          <a className="pz-land-cta pz-land-cta-xl" href="/sign">Come in</a>
          <span className="pz-land-hint">Takes about a minute.</span>
        </div>
      </section>

      <section className="pz-land-moment">
        <h2 className="pz-land-h2">One small moment, handled.</h2>
        <div className="pz-land-phone" role="img" aria-label="Example text from Anticipy asking about a school pickup">
          <div className="pz-land-phone-head">
            <span className="pz-land-avatar">A</span>
            <strong>Anticipy</strong>
            <time>2:41 PM</time>
          </div>
          <p className="pz-land-heard">Earlier, on a call, you were asked: &quot;can you get Leila after school?&quot;</p>
          <p className="pz-land-bubble">
            Leila needs pickup at 3:15 — I checked the drive, 11 minutes. It&apos;s on your calendar — I&apos;ve got it, or you this time?
          </p>
          <div className="pz-land-chips">
            <span className="pz-land-chip" aria-hidden="true">I&apos;ve got it</span>
            <span className="pz-land-chip" aria-hidden="true">I&apos;ll go</span>
          </div>
        </div>
        <p className="pz-land-moment-note">
          It heard the ask, checked the drive, and put it on the calendar — then asked. That&apos;s the whole product.
        </p>
      </section>

      <footer className="pz-land-foot">Anticipy — Vibe your life.</footer>
    </main>
  );
}

function PendantVisual({ active = false }) {
  return (
    <div className={`pz-pendant ${active ? "active" : ""}`} aria-hidden="true">
      <div className="pz-pendant-chain" />
      <div className="pz-pendant-body">
        <span />
      </div>
      <div className="pz-pendant-ring one" />
      <div className="pz-pendant-ring two" />
    </div>
  );
}

function SourceTruthStrip() {
  // The "Source of truth: <path>" strip is pure dev-chrome (UI step 1). Debug-only.
  const _dbgVisible = useDebugVisible();
  if (!_dbgVisible) return null;
  return (
    <section className="pz-source-strip">
      <div>
        <strong>Source of truth</strong>
        <p>{SOURCE_TRUTH_PATH}</p>
      </div>
      <SourceTagList />
    </section>
  );
}

function MiniPanel({ title, text, children }) {
  return (
    <article className="pz-panel">
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </article>
  );
}

function SignScreen({ auth, setAuth }) {
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const supabase = auth.client;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (!supabase) throw new Error(supabaseMissingMessage());
      const result = mode === "signup"
        ? await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${window.location.origin}/auth/confirm?next=/setup` },
        })
        : await supabase.auth.signInWithPassword({ email, password });
      if (result.error) throw result.error;
      const session = result.data?.session || null;
      setAuth((current) => ({ ...current, session }));
      setMessage(mode === "signup" && !session ? "Check your email to confirm, then come back here." : "You are signed in.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    setAuth((current) => ({ ...current, session: null }));
  }

  return (
    <section className="pz-form-shell pz-form-single">
      <form className="pz-panel pz-form" onSubmit={submit}>
        <p className="pz-form-lead">{auth.session ? "You are in." : "Come in."}</p>
        <p className="pz-form-sub">One account, everywhere. That's it.</p>
        <span className="pz-only-debug">
          {auth.configured ? <StatusPill value="live" /> : <StatusPill value="unavailable" />}
        </span>
        <label>
          <span>Email</span>
          <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" />
        </label>
        <label>
          <span>Password</span>
          <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} />
        </label>
        <button className="pz-button primary" type="submit" disabled={busy || !email || !password}>
          {busy ? "Working..." : mode === "signin" ? "Sign in" : "Create account"}
        </button>
        <button className="pz-link-button" type="button" onClick={() => setMode(mode === "signin" ? "signup" : "signin")}>
          {mode === "signin" ? "Create an account" : "I already have an account"}
        </button>
        {auth.session ? (
          <button className="pz-link-button" type="button" onClick={signOut}>Sign out</button>
        ) : null}
        {message ? <p className="pz-note">{message}</p> : null}
      </form>
    </section>
  );
}

// The cloud that runs your Anticipy. Pairing binds THIS Chrome to your own account there, so the
// helper acts as you and only you — the per-user "hands" the hosted product needs at scale.
const CLOUD_ENGINE = "https://engine-production-eb43.up.railway.app";

function SetupScreen({ engineState, listenStatus, refreshEngine, refreshListenStatus }) {
  // Pairing UX (B12): drive the already-built per-user pairing handshake from the setup step.
  //   idle -> pairing -> sent (helper accepted; wait for it to connect)
  //                    -> fallback (helper not reachable on this page; show the code to paste)
  //                    -> disabled (per-user hands flag off; mint 404s — soft, never a crash)
  //                    -> error   (something transient; invite a retry)
  const [pairState, setPairState] = useState("idle");
  const [pairCode, setPairCode] = useState("");
  const paired = engineState.extensionConnected;

  // Keep the latest refreshEngine without re-arming the poll every parent render.
  const refreshRef = useRef(refreshEngine);
  refreshRef.current = refreshEngine;

  // While we're waiting for the just-paired Chrome to phone home, quietly re-check readiness so
  // "Chrome paired ✓" appears on its own — no "Check again" tap required. Stops once connected.
  useEffect(() => {
    if (paired) return undefined;
    if (pairState !== "sent" && pairState !== "fallback") return undefined;
    const timer = setInterval(() => { try { refreshRef.current?.(); } catch { /* noop */ } }, 2500);
    return () => clearInterval(timer);
  }, [pairState, paired]);

  async function pairThisChrome() {
    setPairState("pairing");
    // The mint proxy binds the code to the signed-in caller via their Supabase bearer, so send it.
    let token = "";
    try {
      const client = createBrowserSupabaseClient();
      if (client) {
        const { data } = await client.auth.getSession();
        token = data?.session?.access_token || "";
      }
    } catch { /* not signed in / local — the engine falls back to owner, or 404s below */ }

    let code = "";
    try {
      const res = await fetch("/api/pairing/mint", {
        credentials: "same-origin",
        cache: "no-store",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.status === 404) { setPairState("disabled"); return; } // per-user hands not switched on
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.code) { setPairState("error"); return; }
      code = data.code;
    } catch {
      setPairState("error");
      return;
    }
    setPairCode(code);

    // content.js drops a hidden marker carrying the helper's id when it's loaded on this page.
    let extId = "";
    try { extId = document.getElementById("anticipy-ext-id")?.dataset?.id || ""; } catch { extId = ""; }
    const runtime = (typeof window !== "undefined" && window.chrome) ? window.chrome.runtime : null;

    if (extId && runtime?.sendMessage) {
      // Hand the signed code straight to the loaded helper — it claims it and binds to your account.
      try {
        runtime.sendMessage(
          extId,
          { type: "pair_device", signed: true, pairing_code: code, engine_http: CLOUD_ENGINE },
          (response) => {
            const failed = runtime.lastError || !response || !response.ok;
            if (failed) { setPairState("fallback"); return; }
            setPairState("sent");
            try { refreshRef.current?.(); } catch { /* noop */ }
          },
        );
      } catch {
        setPairState("fallback");
      }
    } else {
      // Helper isn't reachable on this page — show the code so it can be pasted into the helper.
      setPairState("fallback");
    }
  }

  return (
    <div className="pz-scene">
      <section className="pz-stage-hero pz-stage-minimal">
        <StatusPill value={engineState.ok ? "live" : "unavailable"} />
        <h2>Let&rsquo;s get you set up.</h2>
        <p>Two quick things, then I can start.</p>
        <div className="pz-readiness-list">
          <ReadinessRow label="Browser helper" ok={paired} text={paired ? "Connected" : "Not connected yet"} />
          <ReadinessRow label="Listening" ok={listenStatus.status !== "unavailable"} text={humanStatus(listenStatus.status || "read_only")} />
        </div>
        {!paired ? (
          <div className="pz-setup-helper">
            <p className="pz-setup-helper-lead">
              Add the browser helper — it lets me work inside the Chrome you already use.
              Nothing sends without your okay.
            </p>
            <a className="pz-button primary" href="/anticipy-chrome-extension.zip" download>
              Download the browser helper (.zip)
            </a>
            <ol className="pz-setup-steps">
              <li>Unzip the file you just downloaded.</li>
              <li>Open your browser&rsquo;s extensions page.</li>
              <li>Turn on &ldquo;Developer mode&rdquo; (top-right toggle).</li>
              <li>Click &ldquo;Load unpacked&rdquo; and pick the unzipped folder.</li>
              <li>The Anticipy icon appears in your toolbar.</li>
            </ol>
            <div className="pz-pair-block">
              <p className="pz-setup-helper-lead">
                Loaded it already? Link this Chrome to your account so I work as you &mdash; and only you.
              </p>
              <button
                className="pz-button primary"
                onClick={pairThisChrome}
                disabled={pairState === "pairing"}
                type="button"
              >
                {pairState === "pairing" ? "Linking…" : "Pair this Chrome to your account"}
              </button>
              {pairState === "sent" ? (
                <p className="pz-pair-note">Linking this Chrome to you&hellip; this only takes a moment.</p>
              ) : null}
              {pairState === "disabled" ? (
                <p className="pz-pair-note">Account linking isn&rsquo;t switched on yet &mdash; the steps above have you set for now.</p>
              ) : null}
              {pairState === "error" ? (
                <p className="pz-pair-note">That didn&rsquo;t go through. Give it another try in a moment.</p>
              ) : null}
              {pairState === "fallback" ? (
                <div className="pz-pair-fallback">
                  <p className="pz-pair-note">
                    Almost there. Open the Anticipy helper in your toolbar and paste these two lines:
                  </p>
                  <span className="pz-pair-label">Your code</span>
                  <code className="pz-pair-code">{pairCode}</code>
                  <span className="pz-pair-label">Where to connect</span>
                  <code className="pz-pair-code">{CLOUD_ENGINE}</code>
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="pz-pair-done">Chrome paired &#10003;</p>
        )}
        <div className="pz-actions pz-actions-simple pz-actions-in-card">
          <a className="pz-button primary pz-button-xl" href="/onboarding/2">Continue</a>
          <button className="pz-button ghost" onClick={() => { refreshEngine(); refreshListenStatus(); }} type="button">Check again</button>
        </div>
      </section>
    </div>
  );
}

function ReadinessRow({ label, ok, text }) {
  return (
    <div className="pz-readiness-row">
      <span className={`pz-dot ${ok ? "ok" : ""}`} />
      <strong>{label}</strong>
      <small>{text}</small>
    </div>
  );
}

function OnboardingScreen({ screen, profile, setProfile, saveProfile, saveOnboarding, onboarding, engineState }) {
  const stage = ONBOARDING_STAGES.find((item) => item.route.endsWith(`/${screen.split("-").pop()}`)) ||
    ONBOARDING_STAGES.find((item) => item.route === "/onboarding/basics") ||
    ONBOARDING_STAGES[0];

  if (screen === "onboarding-2") {
    return (
      <div className="pz-scene">
        <section className="pz-form-shell pz-onboarding-card">
          <div className="pz-panel pz-form-intro">
            <StatusPill value="live" />
            <h2>Tell me three simple things.</h2>
            <p>Your name, one sentence about you, and where I should slow down before acting.</p>
          </div>
          <ProfileBasicsForm profile={profile} setProfile={setProfile} saveProfile={saveProfile} />
        </section>
        <OnboardingTimeline onboarding={onboarding} activeRoute="/onboarding/2" />
      </div>
    );
  }

  const isReadLayer = ["/onboarding/3", "/onboarding/5", "/onboarding/7"].includes(stage.route);
  // UI_SPEC step 6: the final onboarding stage IS the confirm-mirror (formerly the standalone
  // /great screen), folded in here so onboarding ends by POSTing /api/onboard/complete and
  // landing the owner on Main (/). No separate /great or /done screens anymore.
  const isFinalStage = stage.route === ONBOARDING_STAGES[ONBOARDING_STAGES.length - 1].route;
  if (isFinalStage) {
    return <OnboardingFinalStage profile={profile} setProfile={setProfile} saveProfile={saveProfile} />;
  }

  return (
    <div className="pz-scene">
      <section className="pz-stage-hero pz-stage-minimal">
        <StatusPill value={isReadLayer ? "live" : stage.status} />
        <h2>{stage.title}</h2>
        <p>{stage.copy}</p>
        <div className="pz-actions pz-actions-simple">
          <button
            className="pz-button ghost"
            type="button"
            onClick={() => saveOnboarding({ currentStep: stage.route, statusByStep: { ...(onboarding.statusByStep || {}), [stage.route]: "reviewed" } })}
          >
            Mark done
          </button>
          <a className="pz-button primary pz-button-xl" href={nextOnboardingHref(stage.route)}>Next</a>
        </div>
      </section>
      {isReadLayer ? <AccountReadStage deep={stage.route !== "/onboarding/3"} engineState={engineState} /> : null}
      <OnboardingTimeline onboarding={onboarding} activeRoute={stage.route} />
    </div>
  );
}

// A live "Anticipy reads your world" stage: per-service allow toggles (the engine's
// consent gate — nothing is read until the owner allows it), then a real scan through
// the paired Chrome extension. Layer 1 = broad logged-in discovery (/onboard/scan);
// Layer 2/3 = content deep read (/onboard/deep-scan).
function AccountReadStage({ deep = false, engineState }) {
  const [services, setServices] = useState([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [message, setMessage] = useState("");
  // FIX-03: during a scan, poll the engine's onboarding marker so the pill shows REAL live progress
  // (a heartbeat straight from the engine) instead of a static decoration. GET /api/onboard/status.
  const [scanProgress, setScanProgress] = useState(null);

  useEffect(() => {
    jsonFetch("/api/onboard/permissions")
      .then((data) => setServices(Array.isArray(data.services) ? data.services : []))
      .catch(() => setServices([]));
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    let alive = true;
    let polls = 0;
    setScanProgress({ polls: 0, complete: false });
    const tick = async () => {
      try {
        const status = await jsonFetch("/api/onboard/status");
        if (!alive) return;
        polls += 1;
        setScanProgress({ polls, complete: Boolean(status.onboarding_complete) });
      } catch {
        /* keep the last known progress; the scan message still narrates what happened */
      }
    };
    tick();
    const id = setInterval(tick, 2500);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [busy]);

  async function toggle(service, allowed) {
    setServices((current) => current.map((s) => (s.service === service ? { ...s, allowed } : s)));
    try {
      const data = await jsonFetch("/api/onboard/permissions", {
        method: "POST",
        body: JSON.stringify({ service, allowed }),
      });
      if (Array.isArray(data.services)) setServices(data.services);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  async function runScan() {
    setBusy(true);
    setMessage("");
    setResult(null);
    try {
      let data;
      if (deep) {
        // FIX-03 (2026-07-02): "Go deeper" now runs the REAL 4-layer loop first — the genuine
        // scroll+read of your logged-in accounts that expands into the systems it discovers
        // (FIX-11). If the loop can't run (no debuggable Chrome), it says so honestly and we
        // fall back to the shallow extension snapshot rather than pretending.
        data = await jsonFetch("/api/onboard/loop", { method: "POST", body: "{}" });
        if (data && data.ok === false) {
          const reason = data.reason || "the deep read isn't available yet";
          const fallback = await jsonFetch("/api/onboard/deep-scan", { method: "POST", body: "{}" });
          setResult(fallback);
          setMessage(`${reason} — using the quick read instead. ${fallback.note || ""}`.trim());
          return;
        }
        setResult(data);
        const read = (data.layers || []).flatMap((l) => l.scraped || []);
        const grew = (data.layers || []).flatMap((l) => l.discovered || []);
        const bits = [];
        if (read.length) bits.push(`read ${[...new Set(read)].length} place${read.length === 1 ? "" : "s"} across ${data.layers.length} pass${data.layers.length === 1 ? "" : "es"}`);
        if (grew.length) bits.push(`followed your world into ${grew.join(", ")}`);
        setMessage(data.confirm_prompt || (bits.length ? `Done — ${bits.join("; ")}.` : "Done."));
      } else {
        data = await jsonFetch("/api/onboard_scan", { method: "POST", body: JSON.stringify({ wait: true, timeout_s: 90 }) });
        setResult(data);
        setMessage(data.note || (data.triggered ? "Reading started in your Chrome." : "Your browser helper is not connected yet."));
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  const anyAllowed = services.some((s) => s.allowed);
  const discovered = Array.isArray(result?.discovered) ? result.discovered : [];

  return (
    <section className="pz-panel pz-form">
      <div className="pz-panel-head">
        <div>
          <h3>{deep ? "Where I go deeper" : "What I may read"}</h3>
          <p>Nothing is read until you allow it. Reading is read-only — no sending, no spending.</p>
        </div>
        {busy ? (
          <span className="pz-pill pz-pill-working" aria-live="polite">
            {scanProgress?.complete ? "Saved" : "Reading your world…"}
            {scanProgress?.polls ? ` (${scanProgress.polls})` : ""}
          </span>
        ) : (
          <StatusPill value={engineState?.extensionConnected ? "live" : "unavailable"} />
        )}
      </div>
      {services.map((service) => (
        <label key={service.service} className="pz-check">
          <input
            type="checkbox"
            checked={Boolean(service.allowed)}
            onChange={(event) => toggle(service.service, event.target.checked)}
          />{" "}
          {service.label} <small>— {service.why}</small>
        </label>
      ))}
      {!services.length ? <p className="pz-note">Could not load the allow list. Is the engine running?</p> : null}
      {!engineState?.extensionConnected ? (
        <p className="pz-note">
          Browser helper is not connected. <a href="/setup">Get the helper</a> so I can read through your own Chrome.
        </p>
      ) : null}
      <button className="pz-button primary" type="button" onClick={runScan} disabled={busy || !anyAllowed}>
        {busy ? "Reading your world…" : deep ? "Go deeper" : "Read my accounts"}
      </button>
      {message ? <p className="pz-note">{message}</p> : null}
      {discovered.length ? (
        <ul className="pz-list">
          {discovered.map((item, index) => (
            <li key={`disc-${index}`}>
              {item.name || item.service || "Service"}: {item.logged_in || item.status === "logged_in" ? "signed in — I can read it" : "needs sign-in"}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function nextOnboardingHref(route) {
  const index = ONBOARDING_STAGES.findIndex((stage) => stage.route === route);
  if (index < 0 || index === ONBOARDING_STAGES.length - 1) return "/";
  return ONBOARDING_STAGES[index + 1].route;
}

function ProfileBasicsForm({ profile, setProfile, saveProfile }) {
  // Saving must be VISIBLE: the button reflects in-flight state and a confirmation line appears
  // after the engine round-trip, so pressing Save never feels like a dead button.
  const [saveState, setSaveState] = useState("idle");
  const [saveError, setSaveError] = useState("");

  function patch(next) {
    setProfile((current) => ({ ...current, ...next }));
  }

  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    // Three simple things only. Phone / timezone / the how-much-should-I-do setting live in Settings
    // now, so we keep any existing values via ...profile instead of wiping them from this form.
    const next = {
      ...profile,
      name: String(form.get("name") || ""),
      summary: String(form.get("summary") || ""),
      doNotTouch: String(form.get("doNotTouch") || ""),
    };
    setProfile(next);
    setSaveState("saving");
    setSaveError("");
    try {
      await saveProfile(next);
      setSaveState("saved");
    } catch (error) {
      setSaveState("error");
      setSaveError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <form className="pz-panel pz-form" onSubmit={submit}>
      <label>
        <span>Your name</span>
        <input
          name="name"
          value={profile.name || ""}
          onChange={(event) => patch({ name: event.target.value })}
          placeholder="What should I call you?"
        />
      </label>
      <label>
        <span>About you</span>
        <small className="pz-note">One sentence — who you are and what you&rsquo;re juggling right now.</small>
        <input
          name="summary"
          value={profile.summary || ""}
          onChange={(event) => patch({ summary: event.target.value })}
          placeholder="e.g. Founder of a small studio, always mid-launch."
        />
      </label>
      <label>
        <span>Things I should always check with you first</span>
        <small className="pz-note">Where I should slow down and ask before acting — money, certain people, anything you&rsquo;d hate me to get wrong.</small>
        <textarea
          name="doNotTouch"
          value={profile.doNotTouch || ""}
          onChange={(event) => patch({ doNotTouch: event.target.value })}
          placeholder="Example: always ask before emailing a client, or before spending money."
        />
      </label>
      <div className="pz-form-submit-row">
        <button className="pz-button primary" type="submit" disabled={saveState === "saving"}>
          {saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved ✓" : "Save"}
        </button>
        <a className="pz-button ghost" href="/onboarding/3">Next</a>
      </div>
      {saveState === "saved" ? <p className="pz-note">Got it — I&rsquo;ll remember that. Press Next when you&rsquo;re ready.</p> : null}
      {saveState === "error" ? <p className="pz-note">That didn&rsquo;t save: {saveError || "something went wrong"}. Try again.</p> : null}
    </form>
  );
}

function OnboardingTimeline({ onboarding, activeRoute }) {
  // Only user-facing stages (visible === true) reach the surface — the internal LAYER/CALL pipeline
  // steps stay hidden. Codenames become a plain "Step X of N", and every status runs through
  // humanStatus() so a raw enum ("seeded" / "coming_soon" / "read_only") can never render.
  const steps = ONBOARDING_STAGES.filter((stage) => stage.visible === true);
  if (!steps.length) return null;
  return (
    <section className="pz-timeline">
      {steps.map((stage, index) => (
        <a key={stage.route} className={`pz-timeline-step ${activeRoute === stage.route ? "active" : ""}`} href={stage.route}>
          <span>{`Step ${index + 1} of ${steps.length}`}</span>
          <small>{humanStatus(onboarding.statusByStep?.[stage.route] || stage.status)}</small>
        </a>
      ))}
    </section>
  );
}

// The real learned memory, straight from the engine's four drawers. Used on the
// Great screen (what onboarding actually learned) and the Memory screen.
function useMemoryDrawers() {
  const [drawers, setDrawers] = useState(null);
  const [error, setError] = useState("");
  async function reload() {
    try {
      const data = await jsonFetch("/api/memory/drawers");
      setDrawers(data.drawers || null);
      setError("");
    } catch (err) {
      setDrawers(null);
      setError(err instanceof Error ? err.message : String(err));
    }
  }
  useEffect(() => { reload(); }, []);
  return { drawers, error, reload };
}

function drawerTexts(drawer, { activeOnly = true } = {}) {
  const items = Array.isArray(drawer?.recent) ? drawer.recent : [];
  return items
    .filter((item) => !activeOnly || !item.status || ["active", "open"].includes(item.status))
    .map((item) => item.text)
    .filter(Boolean);
}

// S5 — per-person DOSSIERS, surfaced from REAL memory. The engine's people-discovery +
// dossier synthesis tags each learned fact with the person it is about (MemoryItem.people;
// see onboarding/dossier.py write_dossier_to_memory). Group the real drawer items by person
// so the user can review the dossier Anticipy actually built for each person who matters.
// Nothing is invented: a person only appears when a real, learned fact names them, and the
// empty state is honest.
function peopleDossiers(drawers) {
  const byPerson = new Map();
  for (const drawer of [drawers?.profile, drawers?.derived, drawers?.history]) {
    const items = Array.isArray(drawer?.recent) ? drawer.recent : [];
    for (const item of items) {
      const text = String(item?.text || "").trim();
      if (!text) continue;
      const names = Array.isArray(item?.people) ? item.people : [];
      for (const raw of names) {
        const name = String(raw || "").trim();
        if (!name) continue;
        if (!byPerson.has(name)) byPerson.set(name, new Set());
        byPerson.get(name).add(text);
      }
    }
  }
  return [...byPerson.entries()]
    .map(([name, facts]) => ({ name, facts: [...facts] }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function PeopleDossierSection({ drawers }) {
  const people = peopleDossiers(drawers);
  return (
    <section className="pz-people-dossiers">
      <h3 className="pz-people-dossiers-head">People I know about ({people.length})</h3>
      {people.length ? (
        <div className="pz-grid two">
          {people.map((person) => (
            <article key={person.name} className="pz-panel pz-dossier-card">
              <h4>{person.name}</h4>
              <ul className="pz-list">
                {person.facts.map((fact, index) => (
                  <li key={`${person.name}-${index}`}>{fact}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      ) : (
        <p className="pz-note">No people yet — as I read your world, everyone who matters gets their own dossier here.</p>
      )}
    </section>
  );
}

function LearnedMemoryPanel({ drawers, error, onResolveLoop }) {
  if (error) return <p className="pz-note">I could not read memory: {error}</p>;
  if (!drawers) return <p className="pz-note">Reading what I learned…</p>;
  return (
    <div className="pz-dossier">
      <PeopleDossierSection drawers={drawers} />
      <section className="pz-grid two pz-memory-grid">
        <ProfileSection title={`Facts I learned (${drawers.profile?.count || 0})`} items={drawerTexts(drawers.profile)} />
        <ProfileSection title={`What I inferred — never promoted (${drawers.derived?.count || 0})`} items={drawerTexts(drawers.derived)} />
        <OpenLoopsSection drawer={drawers.open_loops} onResolveLoop={onResolveLoop} />
        <ProfileSection title={`Recent history (${drawers.history?.count || 0})`} items={drawerTexts(drawers.history).slice(-6)} />
      </section>
    </div>
  );
}

// Open loops, each with a "Resolve" action (FIX-05). Resolve POSTs /api/memory/resolve-loop
// -> engine /memory/open-loops/resolve {id,status:"done"}, then reloads the drawers so the loop
// drops off. The button only shows when a reload callback is wired (the Settings/onboarding
// memory panels); read-only renders degrade to the plain list.
function OpenLoopsSection({ drawer, onResolveLoop }) {
  const [busyId, setBusyId] = useState("");
  const items = (Array.isArray(drawer?.recent) ? drawer.recent : [])
    .filter((item) => !item.status || ["active", "open"].includes(item.status));
  async function resolveLoop(id) {
    if (!id || busyId) return;
    setBusyId(id);
    try {
      await jsonFetch("/api/memory/resolve-loop", { method: "POST", body: JSON.stringify({ id, status: "done" }) });
      if (onResolveLoop) await onResolveLoop();
    } catch {
      /* leave the loop open; the next drawer read shows the honest state */
    } finally {
      setBusyId("");
    }
  }
  return (
    <article className="pz-panel">
      <h3>{`Open loops (${drawer?.count || 0})`}</h3>
      <ul className="pz-list">
        {items.length ? items.map((item, index) => (
          <li key={item.id || `loop-${index}`} className="pz-loop-row">
            <span>{item.text}</span>
            {onResolveLoop && item.id ? (
              <button
                type="button"
                className="pz-button subtle"
                onClick={() => resolveLoop(item.id)}
                disabled={busyId === item.id}
              >
                {busyId === item.id ? "Resolving…" : "Resolve"}
              </button>
            ) : null}
          </li>
        )) : <li>Nothing confirmed yet.</li>}
      </ul>
    </article>
  );
}

// The onboarding-final "does this feel right?" check is a CALM confirmation, not a database view.
// It shows who Anticipy knows (per-person dossiers, or the honest 0-state) and a SUMMARY of what
// it's already tracking — a count plus the top few — never the full backlog with Resolve buttons.
// The full, editable lists live on the board and in Settings (LearnedMemoryPanel), not here.
function OnboardingDossierSummary({ drawers, error }) {
  if (error) return <p className="pz-note">I could not read what I learned: {error}</p>;
  if (!drawers) return <p className="pz-note">Reading what I learned…</p>;
  const loops = (Array.isArray(drawers.open_loops?.recent) ? drawers.open_loops.recent : [])
    .filter((l) => !l.status || ["active", "open", "waiting"].includes(l.status));
  const loopCount = drawers.open_loops?.count || 0;
  const topLoops = loops.map((l) => l.text).filter(Boolean).slice(0, 3);
  const moreCount = Math.max(0, loopCount - topLoops.length);
  const historyCount = drawers.history?.count || 0;
  return (
    <div className="pz-dossier pz-dossier-calm">
      <PeopleDossierSection drawers={drawers} />
      <section className="pz-panel pz-tracking-summary">
        <h3>{loopCount
          ? `${loopCount} thing${loopCount === 1 ? "" : "s"} I'm already tracking`
          : "Nothing to track yet"}</h3>
        {topLoops.length ? (
          <>
            <ul className="pz-list">
              {topLoops.map((text, index) => <li key={`track-${index}`}>{text}</li>)}
            </ul>
            <p className="pz-note">
              {moreCount
                ? `…and ${moreCount} more. You can see and resolve everything on your board.`
                : "You can see and resolve these on your board anytime."}
            </p>
          </>
        ) : (
          <p className="pz-note">As your day goes, I'll quietly catch the things you mean to do and start tracking them here.</p>
        )}
        {historyCount ? (
          <p className="pz-note">I've also noted {historyCount} moment{historyCount === 1 ? "" : "s"} from what you shared.</p>
        ) : null}
      </section>
    </div>
  );
}

// FIX-05: the memory recall/search surface. One box asks the engine "what do you know relevant
// to X" (POST /api/memory/recall -> /memory/recall, the hybrid retriever) and renders the ranked
// hits; the live backlog (/api/memory/open-loops) and recent history (/api/memory/history) load
// from their own dedicated read routes. Pure display — nothing here writes memory or acts.
function MemoryRecallPanel() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [loops, setLoops] = useState(null);
  const [history, setHistory] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await jsonFetch("/api/memory/open-loops?limit=20");
        setLoops(Array.isArray(data.loops) ? data.loops : []);
      } catch { setLoops([]); }
    })();
    (async () => {
      try {
        const data = await jsonFetch("/api/memory/history");
        setHistory(Array.isArray(data.items) ? data.items : []);
      } catch { setHistory([]); }
    })();
  }, []);

  async function runSearch(event) {
    event.preventDefault();
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    setSearchError("");
    try {
      const data = await jsonFetch("/api/memory/recall", { method: "POST", body: JSON.stringify({ query: q }) });
      setResult(data);
    } catch (err) {
      setResult(null);
      setSearchError(err instanceof Error ? err.message : String(err));
    } finally {
      setSearching(false);
    }
  }

  const hits = Array.isArray(result?.items) ? result.items : [];
  const bestPct = Math.round((Number(result?.top_relevance) || 0) * 100);
  return (
    <section className="pz-panel pz-form pz-memory-recall">
      <h3>Search what I know</h3>
      <p className="pz-note">Ask by meaning — &ldquo;what did I say about the dentist?&rdquo; — and I search memory. Read-only: nothing here acts.</p>
      <form className="pz-recall-form" onSubmit={runSearch}>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="What do you know about…"
          aria-label="Search memory"
        />
        <button className="pz-button subtle" type="submit" disabled={searching || !query.trim()}>
          {searching ? "Searching…" : "Search"}
        </button>
      </form>
      {searchError ? <p className="pz-note">I could not search memory: {searchError}</p> : null}
      {result ? (
        hits.length ? (
          <ul className="pz-list">
            {hits.map((item, index) => (
              <li key={`recall-${index}`}>{item.text}</li>
            ))}
          </ul>
        ) : (
          <p className="pz-note">Nothing relevant surfaced (closest match {bestPct}%).</p>
        )
      ) : null}
      <div className="pz-grid two pz-memory-grid">
        <article className="pz-panel">
          <h3>Open loops I&rsquo;m tracking ({loops ? loops.length : 0})</h3>
          <ul className="pz-list">
            {loops === null ? <li>Reading the backlog…</li>
              : loops.length ? loops.map((item, index) => <li key={item.id || `ol-${index}`}>{item.text}</li>)
              : <li>Nothing open right now.</li>}
          </ul>
        </article>
        <article className="pz-panel">
          <h3>Recent history</h3>
          <ul className="pz-list">
            {history === null ? <li>Reading history…</li>
              : history.length ? history.slice(-8).map((item, index) => <li key={`hist-${index}`}>{item.text}</li>)
              : <li>Nothing recorded yet.</li>}
          </ul>
        </article>
      </div>
    </section>
  );
}

// FIX-08: the remembered-list review panel. Reads the INERT remember-list
// (/api/memory/remembered — on no loop, carrying no trigger field), lets the owner preview
// EXACTLY what a line would do without doing it (/api/memory/remembered/dryrun, or the whole
// day at once via /api/memory/remembered/dryrun-day), and approve ONE line
// (/api/memory/remembered/approve). Approve is default-deny at the engine: it runs only the
// whitelisted reversible intents and hands everything else back. This panel triggers nothing on
// its own — every write is an explicit owner tap, and dry-run/day-preview execute nothing.
function RememberedReviewPanel() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [previews, setPreviews] = useState({});
  const [day, setDay] = useState(null);
  const [dayBusy, setDayBusy] = useState(false);

  async function reload() {
    try {
      const data = await jsonFetch("/api/memory/remembered?limit=50");
      setRows(Array.isArray(data.remembered) ? data.remembered : []);
      setError("");
    } catch (err) {
      setRows([]);
      setError(err instanceof Error ? err.message : String(err));
    }
  }
  useEffect(() => { reload(); }, []);

  function describe(preview) {
    if (!preview) return "";
    if (preview.error) return `I could not preview that: ${preview.error}`;
    if (preview.approved) return "Done — I ran this one.";
    if (preview.approved === false && preview.reason) return `Handed back to you: ${preview.reason}`;
    if (preview.would_execute) return preview.would_do || "Ready to run once your accounts are connected.";
    if (preview.handback) return `I would hand this back for you — nothing runs on its own.`;
    return "Nothing runs automatically for this one.";
  }

  async function dryRun(id) {
    if (!id || busyId) return;
    setBusyId(`dry-${id}`);
    try {
      const data = await jsonFetch("/api/memory/remembered/dryrun", { method: "POST", body: JSON.stringify({ line_id: id }) });
      setPreviews((current) => ({ ...current, [id]: data }));
    } catch (err) {
      setPreviews((current) => ({ ...current, [id]: { error: err instanceof Error ? err.message : String(err) } }));
    } finally {
      setBusyId("");
    }
  }

  async function approve(id) {
    if (!id || busyId) return;
    setBusyId(`go-${id}`);
    try {
      const data = await jsonFetch("/api/memory/remembered/approve", { method: "POST", body: JSON.stringify({ line_id: id }) });
      setPreviews((current) => ({ ...current, [id]: data }));
      await reload();
    } catch (err) {
      setPreviews((current) => ({ ...current, [id]: { error: err instanceof Error ? err.message : String(err) } }));
    } finally {
      setBusyId("");
    }
  }

  async function previewDay() {
    if (dayBusy) return;
    setDayBusy(true);
    try {
      const data = await jsonFetch("/api/memory/remembered/dryrun-day?limit=50");
      setDay(data);
    } catch {
      setDay({ error: true });
    } finally {
      setDayBusy(false);
    }
  }

  return (
    <section className="pz-panel pz-form pz-remembered-review">
      <div className="pz-remembered-head">
        <h3>Remembered — review before I act</h3>
        <button type="button" className="pz-button subtle" onClick={previewDay} disabled={dayBusy}>
          {dayBusy ? "Previewing…" : "Preview my day"}
        </button>
      </div>
      <p className="pz-note">These are things I&rsquo;m holding for you. Nothing here runs until you approve it, and I&rsquo;ll only ever run safe, reversible steps — everything else I hand back.</p>
      {day ? (
        <p className="pz-note">
          {day.error
            ? "I could not preview the day just now."
            : `Of ${day.count || 0} held, ${day.would_execute_count || 0} would run on their own once connected — the rest I&rsquo;d hand back.`}
        </p>
      ) : null}
      {error ? <p className="pz-note">I could not read the remembered list: {error}</p> : null}
      {rows === null ? <p className="pz-note">Reading what I&rsquo;m holding…</p> : null}
      {rows && rows.length === 0 ? <p className="pz-note">Nothing held right now.</p> : null}
      <ul className="pz-list">
        {(rows || []).map((row, index) => {
          const id = row.id != null ? String(row.id) : "";
          const preview = previews[id];
          return (
            <li key={id || `rmb-${index}`} className="pz-remembered-row">
              <span>{row.text}</span>
              <div className="pz-remembered-actions">
                <button
                  type="button"
                  className="pz-button subtle"
                  onClick={() => dryRun(id)}
                  disabled={!id || busyId === `dry-${id}`}
                >
                  {busyId === `dry-${id}` ? "Checking…" : "Preview"}
                </button>
                <button
                  type="button"
                  className="pz-button subtle"
                  onClick={() => approve(id)}
                  disabled={!id || busyId === `go-${id}`}
                >
                  {busyId === `go-${id}` ? "Working…" : "Approve"}
                </button>
              </div>
              {preview ? <small className="pz-remembered-preview">{describe(preview)}</small> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// The folded final onboarding stage (formerly the standalone /great screen). It mirrors back
// what onboarding learned, then "Looks right" persists the durable onboarding-done marker
// (POST /api/onboard/complete) and lands the owner on Main (/). UI_SPEC step 6.
function OnboardingFinalStage({ profile, setProfile, saveProfile }) {
  const [clarification, setClarification] = useState(profile.lastClarification || "");
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState("");
  const { drawers, error: drawersError } = useMemoryDrawers();
  // FIX-4.5: the old ProfileBuiltPanel called /api/onboarding/profile with sources:[] (the UI never
  // has source URLs), so it ALWAYS rendered a dead 0-fact scaffold competing with the real dossier.
  // Removed. LearnedMemoryPanel (/memory/drawers) below is the single, honest source of truth — it
  // shows only what the engine actually learned (You / People / Tools / Open loops), or empty.

  useEffect(() => {
    setClarification(profile.lastClarification || "");
  }, [profile.lastClarification]);

  // "Looks right" persists the durable onboarding-done marker on the engine, then moves on.
  async function confirmDossier() {
    setConfirmBusy(true);
    setConfirmMessage("");
    try {
      const data = await jsonFetch("/api/onboard/complete", { method: "POST", body: JSON.stringify({ complete: true }) });
      if (data.error) throw new Error(data.error);
      window.location.href = "/";
    } catch (err) {
      setConfirmMessage(err instanceof Error ? err.message : String(err));
      setConfirmBusy(false);
    }
  }

  async function submitClarification(event) {
    event.preventDefault();
    const next = {
      ...profile,
      lastClarification: clarification,
      openQuestions: profile.openQuestions || [],
    };
    setProfile(next);
    await saveProfile(next);
  }

  return (
    <div className="pz-scene">
      <section className="pz-stage-hero pz-stage-minimal">
        <StatusPill value="live" />
        <h2>Does this feel right?</h2>
        <p>This is the last quiet check before Anticipy starts helping from the board.</p>
      </section>
      {/* S5: "What you told me" is a single honest confirmation of the CUSTOM PROFILE the user
          stated (name/summary/trust/guardrails) — these are also pushed into the engine "You"
          drawer by saveProfile (FIX-4.4). The old 4-column pz-profile-summary rendered People /
          Tools / Open-loops from the (now-empty, FIX-4.1) LOCAL store, a dead scaffold competing
          with the real learned dossier below. Removed per §3.6 + §5#3: the engine-backed
          LearnedMemoryPanel (with per-person dossiers) is the ONE dossier surface. */}
      <section className="pz-profile-you">
        <ProfileSection title="What you told me" items={[
          profile.name ? `You go by ${profile.name}.` : "Your name — not set yet.",
          profile.summary ? profile.summary : "A sentence about you — not set yet.",
          profile.doNotTouch
            ? `I'll always check with you first before: ${profile.doNotTouch}`
            : "I'll ask before anything that involves money or is hard to undo.",
        ]} />
      </section>
      <OnboardingDossierSummary drawers={drawers} error={drawersError} />
      <form className="pz-panel pz-form" onSubmit={submitClarification}>
        <h3>Anything to fix?</h3>
        <p className="pz-note">One note is enough. This saves back into memory.</p>
        <label>
          <span>Correction</span>
          <textarea
            value={clarification}
            onChange={(event) => setClarification(event.target.value)}
            placeholder="Example: always ask before contacting Marcus, and watch Dana's reference-call loop."
          />
        </label>
        <button className="pz-button primary" type="submit">Save</button>
      </form>
      <div className="pz-actions pz-actions-simple">
        <a className="pz-button ghost" href="/onboarding/7">Back</a>
        <button className="pz-button primary pz-button-xl" type="button" onClick={confirmDossier} disabled={confirmBusy}>
          {confirmBusy ? "Saving…" : "Looks right"}
        </button>
      </div>
      {confirmMessage ? <p className="pz-note">{confirmMessage}</p> : null}
    </div>
  );
}

// FIX-4.5: ProfileBuiltPanel removed — it always sent sources:[] and so always rendered an empty
// 0-fact scaffold, a dead surface competing with the real learned dossier (LearnedMemoryPanel →
// /memory/drawers). One dossier surface, and it only ever shows what the engine truly learned.

function ProfileSection({ title, items, wide = false }) {
  return (
    <article className={`pz-panel ${wide ? "wide" : ""}`}>
      <h3>{title}</h3>
      <ul className="pz-list">
        {(items && items.length ? items : ["Nothing confirmed yet."]).map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </article>
  );
}

function PendingAsksPanel({ pendingAsks, onResolve }) {
  if (!pendingAsks || pendingAsks.length === 0) return null;
  return (
    <section className="pz-pending-asks" aria-label="Waiting for your yes">
      <h3>Waiting for your yes</h3>
      {pendingAsks.map((ask) => (
        <article key={ask.ask_id} className="pz-pending-ask">
          <div>
            <strong>{humanTitle(ask.action || "")}</strong>
            {ask.reason ? <p>{humanTitle(ask.reason)}</p> : null}
          </div>
          <div className="pz-pending-actions">
            <button type="button" onClick={() => onResolve(ask.ask_id, true)}>Yes, go ahead</button>
            <button type="button" className="pz-ghost" onClick={() => onResolve(ask.ask_id, false)}>Not this one</button>
          </div>
        </article>
      ))}
    </section>
  );
}

// THE BOARD — a calm grouped vertical list (replaces the old Tinder swipe-stack). Cards are
// glanceable status objects grouped into "Needs a yes" / "Waiting for you" / "On it", not a
// decision queue: no drag, no off-screen throw. Every action still fires a REAL engine mutation
// (resolveCard=/api/resolve, stopCard=/api/owner/stop, allowAutonomy=/api/owner/autonomy,
// saveComment=/api/tasks/comments) — the /api/owner/cards reload the handlers trigger is the truth.
// Rows expand as an accordion (one open at a time); keyboard-first (Up/Down move, Enter expand,
// Y/N confirm/deny). The bleed-through bug is gone by construction: a flat list has no stack.
const BOARD_SECTIONS = [
  { category: "Needs a yes", token: "blocked" },
  { category: "Waiting for you", token: "ask" },
  { category: "On it", token: "do" },
];

function ChevronIcon({ open }) {
  return (
    <svg className={`pz-row-chevron${open ? " open" : ""}`} width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M8 10l4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 12.5l4.4 4.4L19 7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function closeRowMenu(event) {
  const menu = event.currentTarget.closest("details");
  if (menu) menu.open = false;
}

function CardBoard({ cards, comments, textMirror, sortMode, setSortMode, resolveCard, stopCard, allowAutonomy, saveComment }) {
  const [handled, setHandled] = useState(() => new Set());
  const [exiting, setExiting] = useState({});
  const [openId, setOpenId] = useState("");
  const headerRefs = useRef({});
  // Bug-4: commit() now AWAITS the engine resolve before retiring, so a rapid double-tap could fire
  // two resolves in the await window (the exiting[] guard hasn't been set yet). This tracks the ids
  // mid-commit so a second tap is ignored until the first settles.
  const committingRef = useRef(new Set());

  const sorted = useMemo(() => {
    const copy = [...cards];
    if (sortMode === "needs_approval") copy.sort((a, b) => Number(b.risk === "ask") - Number(a.risk === "ask"));
    if (sortMode === "source") copy.sort((a, b) => a.category.localeCompare(b.category));
    if (sortMode === "newest") copy.reverse();
    return copy;
  }, [cards, sortMode]);

  const live = useMemo(() => sorted.filter((card) => !handled.has(card.id)), [sorted, handled]);

  // A card the engine dropped after its action no longer needs a slot in `handled` — prune stale
  // ids so the set never leaks (and a re-created card id can reappear honestly).
  useEffect(() => {
    setHandled((current) => {
      if (current.size === 0) return current;
      const liveIds = new Set(sorted.map((card) => card.id));
      let changed = false;
      const next = new Set();
      current.forEach((id) => { if (liveIds.has(id)) next.add(id); else changed = true; });
      return changed ? next : current;
    });
  }, [sorted]);

  // Group by card.category into the three sections; anything unexpected falls to a calm "Resting"
  // tail so no card is ever silently dropped. Empty sections don't render.
  const sections = useMemo(() => {
    const groups = BOARD_SECTIONS.map((section) => ({ ...section, items: [] }));
    const extra = [];
    live.forEach((card) => {
      const hit = groups.find((group) => group.category === card.category);
      if (hit) hit.items.push(card);
      else extra.push(card);
    });
    if (extra.length) groups.push({ category: "Resting", token: "calm", items: extra });
    return groups.filter((group) => group.items.length);
  }, [live]);

  const flatOrder = useMemo(() => sections.flatMap((section) => section.items.map((card) => card.id)), [sections]);

  function retire(cardId) {
    setHandled((current) => {
      if (current.has(cardId)) return current;
      const next = new Set(current);
      next.add(cardId);
      return next;
    });
    setOpenId((open) => (open === cardId ? "" : open));
  }

  // Deny stops an in-flight opt-out chore (/api/owner/stop) when there is one, otherwise it declines
  // the ask (/api/resolve approved:false) — the exact routing the old swipe-left used.
  function denyAction(card) {
    const raw = card.raw || {};
    const optOut = Boolean(raw.execution?.opt_out || raw.args?.opt_out);
    const inFlight = !["stopped", "done", "failed", "blocked"].includes(card.status);
    if (stopCard && optOut && inFlight) return stopCard(card);
    return resolveCard(card, false);
  }

  // One commit path for buttons and keys. Bug-4: the row must retire ONLY when the engine mutation
  // genuinely landed. The old code fired the resolve WITHOUT awaiting and always retired + animated
  // out — so a failed /api/resolve silently dismissed the card as if it had gone through. Now we
  // await the outcome and, on a real failure, LEAVE the card in place (resolveCard has already
  // flipped its text-mirror to "failed", so the row honestly shows it didn't go through) and let the
  // poll re-sync. Local dismisses (no ask_id "On it" cards, fire-and-forget stops, autonomy) still
  // retire, since there is no engine resolve that can fail for them.
  async function commit(card, kind) {
    if (exiting[card.id] || committingRef.current.has(card.id)) return;
    committingRef.current.add(card.id);
    let retireOk = true;
    try {
      if (kind === "autonomy") {
        const ok = typeof window !== "undefined" && window.confirm("Let me do things like this without asking first?");
        if (!ok) return;
        try { await allowAutonomy(card); } catch { /* reload behind is the truth */ }
      } else if (kind === "confirm") {
        // "Go ahead" only renders on a card with a real ask_id, so this ALWAYS drives a live
        // /api/resolve — retire only if that resolve actually returned success.
        try { retireOk = await resolveCard(card, true); }
        catch { retireOk = false; }
      } else {
        // Deny: a card WITH an ask_id declines it for real (retire only on a genuine decline); a
        // no-ask "On it"/stop card is a local dismiss / fire-and-forget stop, which always retires.
        try {
          const result = await denyAction(card);
          retireOk = card.askId ? Boolean(result) : true;
        } catch {
          retireOk = !card.askId;
        }
      }
    } finally {
      committingRef.current.delete(card.id);
    }
    if (!retireOk) return;
    const exitKind = kind === "deny" ? "deny" : "confirm";
    setExiting((current) => ({ ...current, [card.id]: exitKind }));
    window.setTimeout(() => retire(card.id), 260);
  }

  function focusRow(id) {
    headerRefs.current[id]?.focus();
  }

  function onRowKey(event, card) {
    const idx = flatOrder.indexOf(card.id);
    if (event.key === "ArrowDown") { event.preventDefault(); focusRow(flatOrder[Math.min(idx + 1, flatOrder.length - 1)]); }
    else if (event.key === "ArrowUp") { event.preventDefault(); focusRow(flatOrder[Math.max(idx - 1, 0)]); }
    else if (event.key === "y" || event.key === "Y") { event.preventDefault(); commit(card, "confirm"); }
    else if (event.key === "n" || event.key === "N") { event.preventDefault(); commit(card, "deny"); }
  }

  const total = live.length;

  return (
    <section className="pz-board" aria-label="Your day">
      <header className="pz-board-head">
        <div>
          <span className="pz-board-kicker">Vibe your life.</span>
          <h3 className="pz-board-title">Your day</h3>
        </div>
        <select
          className="pz-board-order"
          value={sortMode}
          onChange={(event) => setSortMode(event.target.value)}
          aria-label="Order your day"
        >
          <option value="priority">Priority</option>
          <option value="needs_approval">Needs approval</option>
          <option value="source">Source</option>
          <option value="newest">Newest</option>
        </select>
      </header>

      {total ? (
        sections.map((section) => (
          <div className="pz-board-section" key={section.category}>
            <p className="pz-board-section-label">
              {section.category}
              <span className="pz-board-section-count" aria-hidden="true">· {section.items.length}</span>
            </p>
            <ul className="pz-board-list">
              {section.items.map((card, index) => (
                <CardRow
                  key={card.id}
                  card={card}
                  token={section.token}
                  index={index}
                  comment={comments[card.id] || ""}
                  mirror={textMirror[card.id]?.status || "coming_soon"}
                  expanded={openId === card.id}
                  exiting={exiting[card.id]}
                  onToggle={() => setOpenId((open) => (open === card.id ? "" : card.id))}
                  headerRef={(el) => { if (el) headerRefs.current[card.id] = el; else delete headerRefs.current[card.id]; }}
                  onKey={(event) => onRowKey(event, card)}
                  onConfirm={() => commit(card, "confirm")}
                  onDeny={() => commit(card, "deny")}
                  onAutonomy={() => commit(card, "autonomy")}
                  onNote={(note) => saveComment(card.id, note)}
                />
              ))}
            </ul>
          </div>
        ))
      ) : (
        <div className="pz-board-empty">
          <span className="pz-board-empty-mark" aria-hidden="true"><CheckIcon /></span>
          <p className="pz-board-empty-title">Nothing needs you right now.</p>
          <p className="pz-board-empty-sub">I'm listening. I'll surface things as they come.</p>
        </div>
      )}
    </section>
  );
}

function CardRow({ card, token, index, comment, mirror, expanded, exiting, onToggle, headerRef, onKey, onConfirm, onDeny, onAutonomy, onNote }) {
  const [note, setNote] = useState(comment || "");
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteSaved, setNoteSaved] = useState(false);

  useEffect(() => { setNote(comment || ""); }, [comment]);

  const raw = card.raw || {};
  const optOut = Boolean(raw.execution?.opt_out || raw.args?.opt_out);
  const inFlight = !["stopped", "done", "failed", "blocked"].includes(card.status);
  const denyLabel = optOut && inFlight ? "Stop" : "Not now";
  const isDoing = token === "do";
  const tsValue = [raw.created_at, raw.created, raw.ts, raw.timestamp].find((value) => typeof value === "number" && Number.isFinite(value));
  const time = tsValue ? formatGatewayTime(tsValue) : "";
  const statusWord = isDoing ? humanStatus(card.status === "prepared" ? "working" : card.status) : "";

  async function sendNote() {
    setNoteSaved(false);
    try { await onNote(note); setNoteSaved(true); } catch { /* stays open so the note isn't lost */ }
  }

  return (
    <li className={`pz-row${exiting ? ` is-exiting is-exiting-${exiting}` : ""}`} style={{ "--row-index": index }}>
      <div className="pz-row-card" data-token={token}>
        <div className="pz-row-line">
          {isDoing ? (
            <button
              type="button"
              className={`pz-row-check${exiting === "confirm" ? " is-filled" : ""}`}
              onClick={onConfirm}
              aria-label="Mark done"
            >
              <span className="pz-row-check-mark"><CheckIcon /></span>
            </button>
          ) : (
            <span className={`pz-row-dot pz-dot-${token}`} aria-hidden="true" />
          )}
          <button
            type="button"
            className="pz-row-head"
            onClick={onToggle}
            onKeyDown={onKey}
            aria-expanded={expanded}
            ref={headerRef}
          >
            <span className="pz-row-title">{humanTitle(card.title)}</span>
            <span className="pz-row-tail">
              {time ? <time className="pz-row-meta">{time}</time> : statusWord ? <span className="pz-row-meta">{statusWord}</span> : null}
              <ChevronIcon open={expanded} />
            </span>
          </button>
        </div>
        {card.heard ? <p className="pz-row-heard">“{card.heard}”</p> : null}
        <div className={`pz-row-drawer${expanded ? " open" : ""}`}>
          <div className="pz-row-drawer-inner">
            {card.checkIn ? <p className="pz-row-checkin">{card.checkIn}</p> : null}
            <details className="pz-proof-details">
              <summary>Proof</summary>
              <dl className="pz-task-detail">
                <div><dt>Heard</dt><dd>{card.heard || "—"}</dd></div>
                <div><dt>Browser work</dt><dd>{card.browserWork || "—"}</dd></div>
                <div><dt>Proof</dt><dd>{card.browserReceipt ? <BrowserReceipt receipt={card.browserReceipt} /> : (card.proof || "—")}</dd></div>
                <div><dt>Memory</dt><dd>{card.memory || "—"}</dd></div>
              </dl>
              <p className="pz-row-mirror">Text mirror: {humanStatus(mirror)}</p>
              <SourceTagList tags={card.sourceTags} />
            </details>
            {noteOpen ? (
              <div className="pz-row-note">
                {/* FIX-4.3 (honest copy): this note is saved LOCALLY on the card, for you — it is not
                    fed to the brain as a correction/feedback signal (there is no engine feedback route
                    yet), so the copy must not imply the assistant learns or changes behavior from it. */}
                <textarea
                  value={note}
                  onChange={(event) => { setNote(event.target.value); setNoteSaved(false); }}
                  placeholder="A private note kept on this card — just for you."
                  aria-label="Private note for this card"
                />
                <div className="pz-row-note-row">
                  <button type="button" className="pz-button subtle" onClick={() => setNoteOpen(false)}>Close</button>
                  <button type="button" className="pz-button ghost" onClick={sendNote} disabled={!note.trim()}>{noteSaved ? "Saved" : "Save note"}</button>
                </div>
              </div>
            ) : null}
            <div className="pz-row-actions">
              {/* FIX-4.2: "Go ahead" APPROVES a real engine ask (/api/resolve). Show it only when the
                  card actually has an askId — never on an "On it" chore (checkbox instead) or a non-ask
                  status card, where it would just no-op. No button pretends to close what it can't. */}
              {isDoing || !card.askId ? null : (
                <button type="button" className="pz-button primary" onClick={onConfirm}>Go ahead</button>
              )}
              <button type="button" className="pz-button ghost" onClick={onDeny}>{denyLabel}</button>
              <details className="pz-row-more">
                <summary className="pz-row-more-trigger" aria-label="More actions">⋯</summary>
                <div className="pz-row-more-menu" role="menu">
                  <button type="button" role="menuitem" onClick={(event) => { closeRowMenu(event); onAutonomy(); }}>Always okay to do this</button>
                  <button type="button" role="menuitem" onClick={(event) => { closeRowMenu(event); setNoteOpen(true); }}>Note</button>
                </div>
              </details>
            </div>
          </div>
        </div>
      </div>
    </li>
  );
}

// The conversational quick-reply chips that sit under an assistant bubble that's waiting on you.
// Tapping one posts as YOUR line in the thread AND fires the real engine resolve — the "…" opens
// the one honest extra: stop asking for this kind of thing (raises the real autonomy gate).
function QuickReplyChips({ onGoAhead, onNotNow, onAlways }) {
  return (
    <div className="pz-chat-chips" role="group" aria-label="Reply">
      <button type="button" className="pz-chat-chip primary" onClick={onGoAhead}>Go ahead</button>
      <button type="button" className="pz-chat-chip" onClick={onNotNow}>Not now</button>
      <details className="pz-chat-more">
        <summary className="pz-chat-more-trigger" aria-label="More replies">…</summary>
        <div className="pz-chat-more-menu" role="menu">
          <button
            type="button"
            role="menuitem"
            onClick={(event) => { const d = event.currentTarget.closest("details"); if (d) d.open = false; onAlways(); }}
          >
            Go ahead — and stop asking for these
          </button>
        </div>
      </details>
    </div>
  );
}

// THE CONVERSATION — the primary surface. An ongoing thread of chat bubbles: your lines on the
// right, the assistant's warm replies on the left, each grown from a real engine card. A waiting
// ask carries inline Go ahead / Not now chips; a chip only shows while its ask is genuinely still
// open (engine truth), so a reaction made anywhere clears it honestly. Auto-scrolls to newest.
function ConversationThread({ thread, cards, listenState, onResolve, onAlways }) {
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread]);

  // A chip shows while its ask is still open. We decide that from the SOURCE CARD's own state, not
  // from /pending or an ask_id: many real ask cards (generic confirms, create-and-print) carry no
  // ask_id and never appear in /pending, yet still need Go ahead / Not now. So the chips ride on
  // message.chips (this bubble was born from an ask/blocked card) and hide only once the ask is
  // genuinely settled — locally, when you react (message.resolved), OR by engine truth, when the
  // source card reaches a terminal state (resolved elsewhere, e.g. via SMS, or auto-run). We key
  // that terminal check on the card id, which every ask card has.
  const settledCardIds = useMemo(() => {
    const set = new Set();
    (cards || []).forEach((card) => {
      if (card.id && ["done", "completed", "stopped", "failed", "declined", "ignored"].includes(card.status)) {
        set.add(card.id);
      }
    });
    return set;
  }, [cards]);

  const resting = listenState === "listening" || listenState === "processing";

  if (!thread.length) {
    return (
      <section className="pz-chat" aria-label="Your conversation">
        <div className="pz-chat-rest">
          <span className={`pz-chat-rest-orb${resting ? " active" : ""}`} aria-hidden="true" />
          <p className="pz-chat-rest-word">{resting ? "I'm listening…" : "I'm here."}</p>
          <p className="pz-chat-rest-sub">
            Tell me what's on your plate — say it, type it, or drop a recording. I'll catch what
            needs doing and check in with you before I act.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="pz-chat" aria-label="Your conversation">
      <div className="pz-chat-thread">
        {thread.map((message) => {
          const showChips = message.role === "assistant" && message.chips && !message.resolved
            && !(message.cardId && settledCardIds.has(message.cardId));
          return (
            <div className={`pz-chat-turn ${message.role}`} key={message.id}>
              <div className={`pz-chat-bubble ${message.role}${message.tone ? ` tone-${message.tone}` : ""}`}>
                {message.text}
              </div>
              {showChips ? (
                <QuickReplyChips
                  onGoAhead={() => onResolve(message, true, "Go ahead")}
                  onNotNow={() => onResolve(message, false, "Not now")}
                  onAlways={() => onAlways(message)}
                />
              ) : null}
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
    </section>
  );
}

// The main surface is now a CONVERSATION. The composer (OneInput) stays pinned below it as the
// chat input. Everything the board used to front-and-center — the pending-ask list, the card
// board, the "do it on the web" hand, the proactive controls, the listening debug — is preserved
// but tucked into a quiet, collapsed "Things I'm tracking" drawer. The talk-back is the product.
function MainScreen(props) {
  return (
    <div className="pz-scene pz-chat-scene">
      <ConversationThread
        thread={props.thread}
        cards={props.cards}
        listenState={props.listenState}
        onResolve={props.conversationResolve}
        onAlways={props.conversationAutonomy}
      />
      <OneInput {...props} />
      <details className="pz-tracking">
        <summary className="pz-tracking-summary">
          <span>Things I&apos;m tracking</span>
          <span className="pz-tracking-hint" aria-hidden="true">tap to open</span>
        </summary>
        <div className="pz-tracking-body">
          <PendingAsksPanel pendingAsks={props.pendingAsks} onResolve={props.resolvePending} />
          <CardBoard {...props} />
          <WebActionPanel {...props} />
          <BoardActionsPanel {...props} />
          <ActiveListeningPanel {...props} />
        </div>
      </details>
    </div>
  );
}

// "Ask me to do something online" — the direct hand. The user types a real-world task and I run it on THEIR own
// logged-in browser (the connected Chrome helper), then land a judge-verified receipt. This is the
// board's front door to the connected-Chrome path (/api/browser/run -> engine /agent/run); it never
// spends, checks out, or signs in on its own.
function WebActionPanel({ webTask, setWebTask, webBusy, webReceipt, runWebTask, engineState }) {
  const connected = Boolean(engineState?.extensionConnected);
  return (
    <section className="pz-webaction" aria-label="Ask me to do something online">
      <div className="pz-webaction-head">
        <h3 className="pz-webaction-title">Ask me to do something online</h3>
        <p className="pz-webaction-sub">Tell me a real-world task and I'll handle it in your own logged-in browser, then tell you what I found.</p>
      </div>
      <div className="pz-webaction-row">
        <input
          className="pz-webaction-input"
          type="text"
          value={webTask}
          onChange={(event) => setWebTask(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") runWebTask(); }}
          placeholder="e.g. find my last order and start a return"
          aria-label="What should I do on the web?"
        />
        <button
          type="button"
          className="pz-button primary pz-webaction-go"
          onClick={runWebTask}
          disabled={webBusy || !webTask.trim()}
        >
          {webBusy ? "On it…" : "Do it"}
        </button>
      </div>
      {!connected ? (
        <p className="pz-note">Connect the Chrome helper from Setup to run this on your logged-in browser.</p>
      ) : null}
      {webReceipt ? (
        <p className={`pz-note ${webReceipt.ok ? "pz-note-ok" : "pz-note-warn"}`}>{webReceipt.text}</p>
      ) : null}
    </section>
  );
}

// The board's proactive controls. "Anticipate now" (FIX-07) runs one derive pass so the assistant
// gets ahead of unspoken needs on demand; "Send my digest now" (FIX-14) flushes the day's quiet
// items as one message. Each POSTs its existing proxy and shows an honest receipt in place.
function BoardActionsPanel({ runDerive, deriveBusy, deriveReceipt, runDigest, digestBusy, digestReceipt }) {
  // "Anticipate now" / "Send my digest now" are manual cron/loop triggers — internal ops, not
  // consumer controls (a person never hand-runs a derive pass or flushes the digest; that's
  // automatic). Hidden from the board and revealed only under ?debug, matching SourceTagList.
  const _dbgVisible = useDebugVisible();
  if (!_dbgVisible) return null;
  return (
    <section className="pz-board-actions" aria-label="Proactive controls">
      <div className="pz-board-actions-row">
        <button
          type="button"
          className="pz-button primary"
          onClick={runDerive}
          disabled={deriveBusy}
        >
          {deriveBusy ? "Thinking ahead…" : "Anticipate now"}
        </button>
        <button
          type="button"
          className="pz-button ghost"
          onClick={runDigest}
          disabled={digestBusy}
        >
          {digestBusy ? "Sending…" : "Send my digest now"}
        </button>
      </div>
      {deriveReceipt ? (
        <p className={`pz-note ${deriveReceipt.ok ? "pz-note-ok" : "pz-note-warn"}`}>{deriveReceipt.text}</p>
      ) : null}
      {digestReceipt ? (
        <p className={`pz-note ${digestReceipt.ok ? "pz-note-ok" : "pz-note-warn"}`}>{digestReceipt.text}</p>
      ) : null}
    </section>
  );
}

function OneInput({
  intakeText,
  setIntakeText,
  submitTranscript,
  ingestBusy,
  ingestMessage,
  selectedFile,
  setSelectedFile,
  uploadFile,
  listenState,
  startBrowserListening,
  stopBrowserListening,
}) {
  const fileRef = useRef(null);
  const active = listenState === "listening" || listenState === "processing";
  return (
    <section className="pz-oneinput" aria-label="Say it, type it, or drop a recording">
      <div className="pz-oneinput-row">
        <button
          type="button"
          className={`pz-oneinput-icon pz-oneinput-mic ${active ? "active" : ""}`}
          onClick={active ? stopBrowserListening : startBrowserListening}
          aria-label={active ? "Stop talking" : "Talk to me"}
        >
          <span aria-hidden="true">🎙</span>
        </button>
        <textarea
          className="pz-oneinput-text"
          value={intakeText}
          onChange={(event) => setIntakeText(event.target.value)}
          placeholder="Say it, type it, or drop a recording — I'll catch the task."
        />
        <button
          type="button"
          className="pz-oneinput-icon pz-oneinput-clip"
          onClick={() => fileRef.current?.click()}
          aria-label="Attach a recording or transcript"
        >
          <span aria-hidden="true">📎</span>
        </button>
        <input
          ref={fileRef}
          type="file"
          className="pz-oneinput-file"
          accept=".txt,.md,.vtt,.srt,.json,.csv,.mp3,.m4a,.wav,.aac,.flac,.ogg"
          onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
        />
        <button
          type="button"
          className="pz-button primary pz-oneinput-send"
          onClick={selectedFile ? uploadFile : submitTranscript}
          disabled={ingestBusy || (!selectedFile && !intakeText.trim())}
        >
          {ingestBusy ? "Reading…" : "Send"}
        </button>
      </div>
      {selectedFile ? <p className="pz-note pz-oneinput-filenote">Ready to read: {selectedFile.name}</p> : null}
      {ingestMessage ? <p className="pz-note">{ingestMessage}</p> : null}
    </section>
  );
}

// A1: the browser receipt, rendered honestly — the actual answer the agent read back, the URL it
// landed on, and a screenshot affordance (the captured-flag + its path when the engine saved one).
// No route serves the image, so we surface where it is rather than a link that would 404.
function BrowserReceipt({ receipt }) {
  if (!receipt) return null;
  return (
    <div className="pz-receipt">
      {receipt.answer ? <p className="pz-receipt-answer">{receipt.answer}</p> : null}
      {receipt.url ? (
        <a className="pz-receipt-url" href={receipt.url} target="_blank" rel="noreferrer">{receipt.url}</a>
      ) : null}
      {receipt.screenshot ? (
        <span className="pz-receipt-shot" title={receipt.screenshotPath || undefined}>
          Screenshot captured
          {receipt.screenshotPath ? <code>{receipt.screenshotPath}</code> : null}
        </span>
      ) : null}
    </div>
  );
}

function stateWord(listenState) {
  switch (listenState) {
    case "listening":
      return "Listening.";
    case "processing":
      return "Thinking.";
    case "working":
    case "cards_created":
      return "Acting.";
    default:
      return "Resting.";
  }
}

function ActiveListeningPanel({
  listenState,
  liveTranscript,
  interimTranscript,
  listenMessage,
  listenStatus,
  startBrowserListening,
  stopBrowserListening,
  startLocalListening,
  stopLocalListening,
  refreshListenStatus,
}) {
  const active = listenState === "listening" || listenState === "processing";
  return (
    <section className="pz-listen pz-listen-collapsed">
      <button
        className={`pz-listen-orb-button ${active ? "active" : ""}`}
        type="button"
        onClick={active ? stopBrowserListening : startBrowserListening}
        aria-label={active ? "Stop listening" : "Start listening"}
      >
        <span className="pz-listen-orb" />
      </button>
      <p className="pz-listen-word" aria-live="polite">{stateWord(listenState)}</p>
      <div className="pz-only-debug pz-listen-debug">
        <div className="pz-listen-controls">
          <button className="pz-button primary" type="button" onClick={active ? stopBrowserListening : startBrowserListening}>
            {active ? "Stop" : "Start"}
          </button>
          <button className="pz-button ghost" type="button" onClick={isListeningStatus(listenStatus) ? stopLocalListening : startLocalListening}>
            {isListeningStatus(listenStatus) ? "Stop Mac" : "Mac mic"}
          </button>
          <button className="pz-button subtle" type="button" onClick={refreshListenStatus}>Status</button>
        </div>
        <div className="pz-listen-meta">
          <StatusPill value={listenState} />
          <span>Local mic: {isListeningStatus(listenStatus) ? "running" : listenStatus.status || "unknown"}</span>
        </div>
        {listenMessage ? <p className="pz-note">{listenMessage}</p> : null}
        {(liveTranscript.length || interimTranscript) ? (
          <div className="pz-transcript">
            {liveTranscript.map((line, index) => <p key={`${line}-${index}`}>{line}</p>)}
            {interimTranscript ? <p className="interim">{interimTranscript}</p> : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}

// RIGHT-TO-DELETE, gated like the money hard-stop: the engine only wipes when the
// exact confirm phrase is typed. Default-deny — anything else touches nothing.
function ForgetMePanel({ onDeleted }) {
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function forgetMe() {
    setBusy(true);
    setMessage("");
    try {
      const data = await jsonFetch("/api/memory/forget-me", {
        method: "POST",
        body: JSON.stringify({ confirm: phrase }),
      });
      if (data.deleted) {
        setMessage(`Done. ${data.removed} memory rows removed.`);
        setPhrase("");
        if (onDeleted) onDeleted();
      } else {
        setMessage(`Nothing was deleted. Type exactly: ${data.confirm_phrase || "DELETE MY DATA"}`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="pz-panel pz-form">
      <h3>Delete everything I know.</h3>
      <p className="pz-note">Irreversible. Type <strong>DELETE MY DATA</strong> to confirm — anything else deletes nothing.</p>
      <label>
        <span>Confirm phrase</span>
        <input value={phrase} onChange={(event) => setPhrase(event.target.value)} placeholder="DELETE MY DATA" />
      </label>
      <button className="pz-button ghost" type="button" onClick={forgetMe} disabled={busy || !phrase.trim()}>
        {busy ? "Deleting…" : "Forget me"}
      </button>
      {message ? <p className="pz-note">{message}</p> : null}
    </section>
  );
}

// The same readiness checklist /connect uses, shown read-only in Settings so the owner can see
// at a glance what each connected app is actually allowed to do. Presence/absence of config only,
// never a secret value; the internal apple_signing release step is hidden (as it is on /connect).
function AppPermissionsPanel() {
  const [caps, setCaps] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    (async () => {
      try {
        const data = await jsonFetch("/api/readiness");
        const list = (Array.isArray(data.capabilities) ? data.capabilities : [])
          .filter((cap) => cap.capability !== "apple_signing");
        setCaps(list);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, []);
  if (error) return <p className="pz-note">I could not read app permissions right now: {error}</p>;
  if (!caps) return <p className="pz-note">Checking what each app can do…</p>;
  if (!caps.length) return <p className="pz-note">Nothing connected yet. Connect your accounts and they show up here.</p>;
  return (
    <ul className="pz-perm-list">
      {caps.map((cap) => (
        <li className="pz-perm-row" key={cap.capability}>
          <div>
            <strong>{cap.label}</strong>
            <small>{cap.what_to_do}</small>
          </div>
          <span className={`pz-pill pz-pill-${cap.status === "live" ? "live" : "coming_soon"}`}>
            {cap.status === "live" ? "Connected" : "Not connected"}
          </span>
        </li>
      ))}
    </ul>
  );
}

// The comms-line mock/live toggle — Omar's ask: one button in Settings to flip it. Reads the REAL
// engine mode (not a local display store) and flips it in place. Test mode keeps everything on this
// machine; live lets the assistant text and call for real. Going live still needs the credentials +
// phone configured — when they're missing the label says so and the line stays safe, so the button
// flips the intent honestly without ever fabricating a live line out of thin config.
function ChannelModePanel() {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setState(await jsonFetch("/api/channels/mode"));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, []);

  async function flip() {
    if (busy || !state) return;
    setBusy(true);
    const next = state.mode === "live" ? "mock" : "live";
    try {
      setState(await jsonFetch("/api/channels/mode", { method: "POST", body: JSON.stringify({ mode: next }) }));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="pz-note">I could not read the line status right now: {error}</p>;
  if (!state) return <p className="pz-note">Checking the line…</p>;
  const isLive = state.mode === "live";
  return (
    <div className="pz-channel-mode">
      <div className="pz-perm-row">
        <div>
          <strong>{isLive ? "Live — I can text and call you for real." : "Test mode — nothing real leaves this machine."}</strong>
          <small>{state.label || (isLive ? "Live line active" : "Safe by default")}</small>
        </div>
        <span className={`pz-pill pz-pill-${isLive ? "live" : "coming_soon"}`}>{isLive ? "Live" : "Test"}</span>
      </div>
      <button className="pz-button ghost" type="button" onClick={flip} disabled={busy}>
        {busy ? "Switching…" : isLive ? "Switch to test mode" : "Switch to live"}
      </button>
    </div>
  );
}

function SettingsScreen({ settings, setSettings, saveSettings }) {
  // Memory drawers (facts / inferred / open loops / history) + the forget-me control fold in here
  // from the retired /memory screen (UI_SPEC step 8). One reload() refreshes both after a wipe.
  const { drawers, error: drawersError, reload } = useMemoryDrawers();
  // FIX-18: "Run a tick" — one deterministic watcher pass (same path the scheduler would take).
  const [tickBusy, setTickBusy] = useState(false);
  const [tickMessage, setTickMessage] = useState("");
  async function runTick() {
    if (tickBusy) return;
    setTickBusy(true);
    setTickMessage("");
    try {
      const data = await jsonFetch("/api/trigger/tick", { method: "POST" });
      const fired = Array.isArray(data.fired) ? data.fired.length : 0;
      setTickMessage(fired
        ? `Ran a tick — ${fired} thing${fired === 1 ? "" : "s"} fired.`
        : "Ran a tick — nothing to fire right now.");
    } catch {
      setTickMessage("I couldn't run a tick just now. Try again in a moment.");
    } finally {
      setTickBusy(false);
    }
  }
  // FIX-04 (2026-07-02): the dropdown used to write ONLY a local display store — the engine's
  // real autonomy gate never heard about it. Now: read the real mode on mount, POST on change.
  const AUTONOMY_TO_ENGINE = { Limited: "limited", Regular: "regular", "Full-Send": "full_send" };
  const ENGINE_TO_AUTONOMY = { limited: "Limited", regular: "Regular", full_send: "Full-Send" };
  useEffect(() => {
    (async () => {
      try {
        const data = await jsonFetch("/api/owner/autonomy");
        const label = ENGINE_TO_AUTONOMY[data.mode];
        if (label) setSettings((current) => ({ ...current, autonomy: label }));
      } catch { /* engine offline: the local label stands until it isn't */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function syncAutonomy(label) {
    patch("autonomy", label);
    const mode = AUTONOMY_TO_ENGINE[label];
    if (!mode) return;
    try {
      await jsonFetch("/api/owner/autonomy", { method: "POST", body: JSON.stringify({ mode }) });
    } catch { /* the mount read shows the honest engine state next visit */ }
  }
  function patch(path, value) {
    setSettings((current) => {
      const next = structuredCloneSafe(current);
      const parts = path.split(".");
      let target = next;
      for (const part of parts.slice(0, -1)) {
        if (!target[part] || typeof target[part] !== "object") target[part] = {};
        target = target[part];
      }
      target[parts[parts.length - 1]] = value;
      return next;
    });
  }

  return (
    <form className="pz-scene pz-settings-scene" onSubmit={(event) => { event.preventDefault(); saveSettings(); }}>
      <section className="pz-stage-hero pz-stage-minimal pz-page-intro">
        <StatusPill value="live" />
        <h2>Settings.</h2>
        <p>Choose what I can hear, remember, and do. Anything sensitive stays ask-first.</p>
      </section>
      <section className="pz-settings-list">
        <details className="pz-settings-group" open>
          <summary>
            <span>Autonomy and security</span>
            <small>{settings.autonomy || "Regular"}</small>
          </summary>
          <div className="pz-settings-body">
          <label>
            <span>Autonomy</span>
            <select value={settings.autonomy || "Regular"} onChange={(event) => syncAutonomy(event.target.value)}>
              <option>Limited</option>
              <option>Regular</option>
              <option>Full-Send</option>
            </select>
          </label>
          <label className="pz-check"><input type="checkbox" checked={Boolean(settings.confirmBefore?.money)} onChange={(event) => patch("confirmBefore.money", event.target.checked)} /> Money always asks</label>
          <label className="pz-check"><input type="checkbox" checked={Boolean(settings.confirmBefore?.sendToPerson)} onChange={(event) => patch("confirmBefore.sendToPerson", event.target.checked)} /> Sending to people asks</label>
          <label className="pz-check"><input type="checkbox" checked={Boolean(settings.confirmBefore?.irreversible)} onChange={(event) => patch("confirmBefore.irreversible", event.target.checked)} /> Irreversible work asks</label>
          {/* FIX-4.6 (honesty): the autonomy dial above is a live engine gate. The always-ask guards
              below are recorded preferences only — the engine's money/irreversible hard-stops are
              always on regardless and cannot be turned off here, so no toggle claims a gate it can't drive. */}
          <p className="pz-note">The autonomy dial is live. The always-ask guards are recorded preferences — sensitive actions (money, anything irreversible) always ask first no matter what, and can't be switched off here.</p>
          </div>
        </details>
        <details className="pz-settings-group">
          <summary>
            <span>Listening</span>
            <small>{settings.listening?.browserMic ? "On" : "Off"}</small>
          </summary>
          <div className="pz-settings-body">
          <label className="pz-check"><input type="checkbox" checked={Boolean(settings.listening?.browserMic)} onChange={(event) => patch("listening.browserMic", event.target.checked)} /> Browser mic enabled</label>
          <label className="pz-check"><input type="checkbox" checked={Boolean(settings.listening?.localMacMic)} onChange={(event) => patch("listening.localMacMic", event.target.checked)} /> Local Mac mic enabled</label>
          <label className="pz-check"><input type="checkbox" checked={Boolean(settings.listening?.activeByDefault)} onChange={(event) => patch("listening.activeByDefault", event.target.checked)} /> Start active by default</label>
          {/* FIX-4.6 (honesty): recorded preferences, not live switches — the mic is actually started
              and stopped from the board and Setup, so ticking these here doesn't open or silence a mic. */}
          <p className="pz-note">Recorded preferences. The mic is started and stopped from the board and Setup — these don't open or silence a live mic on their own.</p>
          </div>
        </details>
        <details className="pz-settings-group">
          <summary>
            <span>Text and call</span>
            <small>{settings.textCall?.textFirst ? "Text first" : "App first"}</small>
          </summary>
          <div className="pz-settings-body">
          <label className="pz-check"><input type="checkbox" checked={Boolean(settings.textCall?.textFirst)} onChange={(event) => patch("textCall.textFirst", event.target.checked)} /> Text first</label>
          <label>
            <span>Phone</span>
            <input value={settings.textCall?.phone || ""} onChange={(event) => patch("textCall.phone", event.target.value)} />
          </label>
          <p className="pz-note">Text mirror: {humanStatus(settings.textCall?.proofMirror || "coming_soon")}.</p>
          </div>
        </details>
        <details className="pz-settings-group">
          <summary>
            <span>Live actions</span>
            <small>Test or live</small>
          </summary>
          <div className="pz-settings-body">
            <p className="pz-note">Test mode keeps everything on this machine — nothing real is sent. Switch to live and I can text and call you for real. Anything sensitive still asks first.</p>
            <ChannelModePanel />
          </div>
        </details>
        <details className="pz-settings-group">
          <summary>
            <span>Retention and privacy</span>
            <small>{settings.retention?.rawTranscriptDays || 7} days</small>
          </summary>
          <div className="pz-settings-body">
          <label>
            <span>Raw transcript days</span>
            <input type="number" min="1" max="90" value={settings.retention?.rawTranscriptDays || 7} onChange={(event) => patch("retention.rawTranscriptDays", Number(event.target.value))} />
          </label>
          <label>
            <span>Promote to memory</span>
            <select value={settings.retention?.promoteToMemory || "ask"} onChange={(event) => patch("retention.promoteToMemory", event.target.value)}>
              <option value="ask">Ask first</option>
              <option value="automatic">Automatic when high confidence</option>
              <option value="manual">Manual only</option>
            </select>
          </label>
          {/* FIX-4.6 (honesty): recorded preferences — retention/promotion aren't yet wired into the
              engine, so these describe intent rather than enforce a rule. Marked display-only, not faked. */}
          <p className="pz-note">Recorded preferences — retention and promotion aren't wired into the engine yet, so these describe intent rather than enforce it.</p>
          </div>
        </details>
        <details className="pz-settings-group">
          <summary>
            <span>What each app can do</span>
            <small>Permissions</small>
          </summary>
          <div className="pz-settings-body pz-settings-body-wide">
            <p className="pz-note">The same connections your accounts hand me. Read-only here — connect or change them from the setup flow. Nothing sensitive ever runs without your okay.</p>
            <AppPermissionsPanel />
          </div>
        </details>
        <details className="pz-settings-group" id="memory" open>
          <summary>
            <span>Memory</span>
            <small>What I know</small>
          </summary>
          <div className="pz-settings-body pz-settings-body-wide">
            <p className="pz-note">This is my real memory — the facts, inferences, open loops, and history I hold. Anything wrong gets corrected here.</p>
            <LearnedMemoryPanel drawers={drawers} error={drawersError} onResolveLoop={reload} />
            <MemoryRecallPanel />
            <RememberedReviewPanel />
            <TraceViewPanel />
            <ForgetMePanel onDeleted={reload} />
          </div>
        </details>
      </section>
      <div className="pz-actions pz-actions-simple">
        <button className="pz-button primary pz-button-xl" type="submit">Save settings</button>
        <button className="pz-button ghost" type="button" onClick={runTick} disabled={tickBusy}>
          {tickBusy ? "Running…" : "Run a tick"}
        </button>
        {/* FIX-16: the Mac app download — a plain GET link straight at the download route. */}
        <a className="pz-button ghost" href="/api/download/anticipy-execute">Download the Mac app</a>
        <a className="pz-button ghost" href="/">Back to assistant</a>
      </div>
      {tickMessage ? <p className="pz-note">{tickMessage}</p> : null}
    </form>
  );
}

// The trace view: pick (or paste) one action's trace id and see everything it did, end to end —
// every engine step written under that id. Silent drops become visible here instead of invisible.
function TraceViewPanel() {
  const [traceId, setTraceId] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState([]);
  useEffect(() => { setRecent(recentTracesList()); }, []);

  async function loadTrace(id) {
    const target = (id || traceId).trim();
    if (!target || busy) return;
    setBusy(true);
    setTraceId(target);
    try {
      const data = await jsonFetch(`/api/trace/${encodeURIComponent(target)}`);
      setResult(data);
      setError("");
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="pz-panel">
      <h3>Trace one action</h3>
      <p className="pz-note">Every call carries one trace id, end to end. Pick a recent one (or paste an id) and I show every step that action took — nothing gets to drop silently.</p>
      {recent.length ? (
        <ul className="pz-list">
          {recent.slice(0, 6).map((row) => (
            <li key={row.trace}>
              <button className="pz-button subtle" type="button" onClick={() => loadTrace(row.trace)}>
                {row.at} — {row.url.replace("/api/", "")} — {row.trace.slice(0, 8)}…
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <form className="pz-recall-form" onSubmit={(event) => { event.preventDefault(); loadTrace(); }}>
        <input
          value={traceId}
          onChange={(event) => setTraceId(event.target.value)}
          placeholder="Trace id…"
          aria-label="Trace id"
        />
        <button className="pz-button subtle" type="submit" disabled={busy || !traceId.trim()}>
          {busy ? "Reading…" : "Show the steps"}
        </button>
      </form>
      {error ? <p className="pz-note">I could not read that trace: {error}</p> : null}
      {result ? (
        result.entries?.length ? (
          <ul className="pz-list">
            {result.entries.map((entry, index) => (
              <li key={`tr-${index}`}>{entry.summary}</li>
            ))}
          </ul>
        ) : (
          <p className="pz-note">No engine steps recorded under that id — the action never reached the engine, or it predates the trace log.</p>
        )
      ) : null}
    </section>
  );
}

function structuredCloneSafe(value) {
  return JSON.parse(JSON.stringify(value || {}));
}

export default function PhaseZeroApp({ screen = "board" }) {
  const [auth, setAuth] = useState({ configured: false, client: null, session: null });
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [onboarding, setOnboarding] = useState({ currentStep: "welcome", statusByStep: {} });
  const [engineState, setEngineState] = useState({ ok: false, label: "engine unchecked", extensionConnected: false });
  const [listenStatus, setListenStatus] = useState({ status: "unknown", running: false });
  const [listenState, setListenState] = useState("ready");
  const [listenMessage, setListenMessage] = useState("");
  const [liveTranscript, setLiveTranscript] = useState([]);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [intakeText, setIntakeText] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [ingestBusy, setIngestBusy] = useState(false);
  const [ingestMessage, setIngestMessage] = useState("");
  const [engineCards, setEngineCards] = useState([]);
  const [pendingAsks, setPendingAsks] = useState([]);
  const [gatewayEvents, setGatewayEvents] = useState([]);
  const [comments, setComments] = useState({});
  const [textMirror, setTextMirror] = useState({});
  const [sortModeState, setSortModeState] = useState("priority");
  const [webTask, setWebTask] = useState("");
  const [webBusy, setWebBusy] = useState(false);
  const [webReceipt, setWebReceipt] = useState(null);
  const [deriveBusy, setDeriveBusy] = useState(false);
  const [deriveReceipt, setDeriveReceipt] = useState(null);
  const [digestBusy, setDigestBusy] = useState(false);
  const [digestReceipt, setDigestReceipt] = useState(null);
  const [thread, setThread] = useState([]);
  const seededRef = useRef(false);
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);

  // Debug toggle: engine internals (source tags, the Live-circuit telemetry panel) stay hidden for
  // the consumer unless ?debug=1 or localStorage anticipy_debug=1 is set. Client-only (no SSR mismatch).
  useEffect(() => {
    try {
      const on = new URLSearchParams(window.location.search).has("debug")
        || window.localStorage.getItem("anticipy_debug") === "1";
      document.body.classList.toggle("pz-debug", on);
    } catch (_) {}
  }, []);

  const cards = useMemo(() => {
    const live = engineCards.map(normalizeEngineCard);
    return SHOW_FIXTURES ? [...live, ...FIXTURES.map(fixtureToCard)] : live;
  }, [engineCards]);

  // ── Conversation transcript ────────────────────────────────────────────────────────────────
  // The thread is the live session's back-and-forth. It's appended to as things happen (you talk,
  // the assistant replies, you react, it reports back). The engine cards remain the source of
  // truth for what's actually pending; the thread is the human-readable surface over them.
  function appendMessages(input) {
    const list = (Array.isArray(input) ? input : [input]).filter(Boolean);
    if (!list.length) return;
    const stamped = list.map((message) => ({ id: threadId(), ...message }));
    setThread((current) => [...current, ...stamped]);
  }

  function appendUserLine(text) {
    const clean = String(text || "").trim();
    if (clean) appendMessages({ role: "user", text: clean });
  }

  // Turn the cards the engine just made into the assistant's spoken replies — one warm bubble per
  // actionable card. A vent / ignored line makes NO card and therefore NO bubble: silence is the
  // correct answer to a vent (the cardinal-sin rule, surfaced as calm quiet).
  //
  // Idempotent by card id: the dedupe runs INSIDE the state updater against the LIVE thread (not a
  // closed-over snapshot), so this can be called from every path that learns about a card — the
  // ingest response, the authoritative board reconcile after a send, and the on-load seed — without
  // ever voicing the same card twice or dropping one to a stale-closure race. A card already voiced
  // (its id is on an assistant bubble) is skipped; a brand-new card is appended.
  function appendCardReplies(rawCards) {
    const candidates = (Array.isArray(rawCards) ? rawCards : [])
      .filter((card) => card && card.disposition !== "ignore" && card.status !== "ignored")
      .map(normalizeEngineCard)
      .map((card) => {
        const reply = assistantReplyForCard(card);
        return {
          id: threadId(),
          role: "assistant",
          text: reply.text,
          tone: reply.tone,
          chips: reply.chips,
          cardId: card.id,
          askId: card.askId,
        };
      });
    if (!candidates.length) return;
    setThread((current) => {
      // Dedupe against the LIVE thread (not a closed-over snapshot) so calling this from every path
      // that learns of a card — ingest response, board reconcile, on-load seed — is race-free and
      // never voices the same card twice. Also collapse same-card duplicates within this batch.
      const voiced = new Set(
        current.filter((m) => m.role === "assistant" && m.cardId).map((m) => m.cardId),
      );
      const fresh = [];
      for (const bubble of candidates) {
        if (bubble.cardId && voiced.has(bubble.cardId)) continue;
        if (bubble.cardId) voiced.add(bubble.cardId);
        fresh.push(bubble);
      }
      return fresh.length ? [...current, ...fresh] : current;
    });
  }

  // The most recent assistant bubble still waiting on a yes/no — what a typed "yes"/"no" resolves.
  // Gated on the bubble being an unresolved ask (chips + not yet reacted to), NOT on it carrying an
  // ask_id: create-and-print / generic confirm asks expose no ask_id on the card, and requiring one
  // here was why "yes go ahead" fell through to /owner/ingest as a brand-new task and did nothing.
  function activePendingAsk() {
    for (let i = thread.length - 1; i >= 0; i -= 1) {
      const message = thread[i];
      if (message.role === "assistant" && message.chips && !message.resolved) return message;
    }
    return null;
  }

  // A reaction, as a conversation turn: it posts as YOUR line, fires the real engine resolve
  // (/api/resolve via resolveCard) using ONLY this bubble's own ask_id, then the assistant answers
  // honestly. Two hard rules keep this money-safe: (1) we NEVER borrow an unrelated ask from
  // /pending — approving THIS bubble may only resolve THIS bubble's ask, never someone else's
  // (possibly irreversible) one; (2) we NEVER say "Done ✓" without a REAL terminal completion — a
  // resolve that only records an approval, or that we couldn't honestly match, is told as such.
  async function conversationResolve(message, approved, label) {
    if (!message) return;
    appendUserLine(label || (approved ? "Go ahead" : "Not now"));
    // This bubble's OWN ask_id (from its source card) is the only ask this reaction may resolve.
    // If the card exposes none, we do NOT reach into /pending for a different ask.
    const askId = message.askId || "";

    // "Not now" — decline just this one. There's nothing to over-claim; close it warmly.
    if (!approved) {
      setThread((current) => current.map((item) => (item.id === message.id ? { ...item, resolved: true } : item)));
      await resolveCard({ id: message.cardId, askId }, false);
      appendMessages({ role: "assistant", text: "Okay, I'll leave that one.", tone: "do" });
      return;
    }

    // Approve, but this bubble has NO ask_id we can honestly match to a real engine ask. Do NOT fake
    // a "Done ✓", and do NOT grab an unrelated /pending ask (that's how the wrong — maybe
    // irreversible — thing got approved). Record it honestly and leave the ask open (chips stay) so
    // it can still be resolved for real once the engine exposes an ask_id for it.
    if (!askId) {
      // FIX: approving a browse/research ask in chat must actually LAUNCH the hands, not just
      // record the yes. This runs ONLY this bubble's own task text through the same judge-verified
      // connected-Chrome path as the web box (/api/browser/run -> engine /agent/run) — it never
      // borrows another ask, and money/irreversible actions stay behind the engine's hard stops.
      const sourceCard = cards.find((item) => item.id === message.cardId);
      const task = String(sourceCard?.browserWork || sourceCard?.title || "").trim();
      if (task) {
        setThread((current) => current.map((item) => (item.id === message.id ? { ...item, resolved: true } : item)));
        appendMessages({ role: "assistant", text: "On it — doing that in your Chrome now…", tone: "do" });
        try {
          const data = await jsonFetch("/api/browser/run", { method: "POST", body: JSON.stringify({ task }) });
          const done = Boolean(data.task_succeeded);
          const answer = String(data.answer || "").trim();
          if (done && answer) {
            appendMessages({ role: "assistant", text: `Here's what I found: ${answer.slice(0, 500)}`, tone: "do" });
          } else if (done) {
            appendMessages({ role: "assistant", text: "Done — I finished that on the web. ✓", tone: "do" });
          } else {
            appendMessages({ role: "assistant", text: "I couldn't finish that one on the site — it's still on your list.", tone: "do" });
          }
          await loadCards();
        } catch (_error) {
          appendMessages({ role: "assistant", text: "I couldn't reach the web helper just now — it's still on your list.", tone: "do" });
        }
        return;
      }
      appendMessages({
        role: "assistant",
        text: "I've got that down — I'll check with you before anything actually goes out.",
        tone: "do",
      });
      return;
    }

    // A real ask_id for THIS bubble: resolve it for real, optimistically clearing its chips.
    setThread((current) => current.map((item) => (item.id === message.id ? { ...item, resolved: true } : item)));
    appendMessages({ role: "assistant", text: "On it…", tone: "do" });
    const ok = await resolveCard({ id: message.cardId, askId }, true);
    // A resolve we actually SENT that came back with an error must not pretend it worked.
    if (!ok) {
      appendMessages({ role: "assistant", text: "I hit a snag doing that one — it's still on your list.", tone: "do" });
      return;
    }
    // The resolve succeeded. "Done ✓" is reserved for a REAL terminal completion: a landed browser
    // receipt, or a card the engine has moved to a done/completed state. If the resolve only RECORDED
    // the approval (the engine executes it asynchronously, e.g. money/irreversible actions), we
    // promise a real close instead of claiming one — so "Done ✓" is impossible without a receipt or
    // a terminal-done card.
    try {
      const data = await jsonFetch("/api/owner/cards?limit=50");
      const rawCard = (Array.isArray(data.cards) ? data.cards : []).find((card) => (card.id || card.ask_id) === message.cardId);
      const fresh = rawCard ? normalizeEngineCard(rawCard) : null;
      if (fresh?.browserReceipt?.answer) {
        appendMessages({ role: "assistant", text: `Here's what I found: ${fresh.browserReceipt.answer}`, tone: "do" });
        return;
      }
      if (fresh && TERMINAL_DONE_STATUS.has(fresh.status)) {
        appendMessages({ role: "assistant", text: "Done — taken care of. ✓", tone: "do" });
        return;
      }
    } catch {
      /* the tracking drawer still carries the honest state */
    }
    appendMessages({ role: "assistant", text: "On it — I'll let you know the moment it's done.", tone: "do" });
  }

  // The "…" reply: approve AND opt this kind of thing out of ask-first (raises the real autonomy
  // gate via allowAutonomy). Fully reversible from Settings; never touches the money hard-stop.
  async function conversationAutonomy(message) {
    if (!message) return;
    appendUserLine("Go ahead — and stop asking me for these.");
    setThread((current) => current.map((item) => (item.id === message.id ? { ...item, resolved: true } : item)));
    // Only ever resolve THIS bubble's own ask (same money-safe rule as conversationResolve): use the
    // source card's ask_id when it has one, and never borrow an unrelated /pending ask. With no
    // ask_id, allowAutonomy still raises the real autonomy gate (the honest part of this gesture) and
    // simply skips the per-ask resolve — it never approves a different, possibly irreversible, ask.
    const askId = message.askId || "";
    await allowAutonomy({ id: message.cardId, askId });
    appendMessages({
      role: "assistant",
      text: "Got it — I'll take care of these without asking from now on. You can change that anytime in settings.",
      tone: "do",
    });
  }

  // Seed the thread once, on load, from any asks already waiting on you — so a returning user drops
  // straight back into the conversation with their open questions (and chips) rather than a blank
  // slate. A truly fresh user has no waiting asks, so the calm "I'm here." resting state stays.
  useEffect(() => {
    if (seededRef.current || thread.length) return;
    if (!engineCards.length) return;
    // Bug-5: never re-seed an ask that's already been answered. A declined ask keeps its disposition
    // ("ask"/"blocked") even after you say "Not now" — only its STATUS goes terminal ("declined") —
    // so the disposition test alone re-added it on every reload. Excluding terminal statuses up front
    // means a declined (or done/stopped/failed) ask stays gone once resolved, in-band or out.
    const TERMINAL_STATUS = ["done", "completed", "stopped", "failed", "declined", "ignored"];
    const waiting = engineCards.filter((card) => card
      && card.disposition !== "ignore"
      && !TERMINAL_STATUS.includes(card.status)
      && (card.disposition === "ask" || card.disposition === "blocked" || card.status === "waiting" || card.status === "blocked"));
    if (!waiting.length) return;
    seededRef.current = true;
    appendCardReplies(waiting);
  }, [engineCards, thread.length]);

  useEffect(() => {
    const client = createBrowserSupabaseClient();
    setAuth((current) => ({ ...current, configured: Boolean(client), client }));
    if (!client) return undefined;
    let active = true;
    client.auth.getSession().then(({ data }) => {
      if (active) setAuth((current) => ({ ...current, session: data.session || null }));
    });
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      setAuth((current) => ({ ...current, session: session || null }));
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    refreshAll();
    return () => stopBrowserListening();
  }, []);

  // Bug-2: keep the board LIVE. refreshAll ran only once on mount, so a card the engine raised
  // proactively never appeared until a manual reload, and an ask resolved out-of-band (e.g. by SMS)
  // kept showing its Go ahead / Not now chips forever — the settled-card check drives off the cards
  // prop, which was frozen at mount. Poll the authoritative engine every ~16s (skipped while the tab
  // is hidden, guarded against overlap, cleared on unmount) so proactively-raised cards show up and
  // terminal statuses re-sync so already-answered asks stop offering a reaction. Pure reads only.
  useEffect(() => {
    let inFlight = false;
    const tick = async () => {
      if (inFlight) return;
      if (typeof document !== "undefined" && document.hidden) return;
      inFlight = true;
      try { await refreshAll(); } finally { inFlight = false; }
    };
    const id = setInterval(tick, 16000);
    return () => clearInterval(id);
  }, []);

  async function refreshAll() {
    await ensureLocalOwnerSession();
    await Promise.allSettled([
      loadProfile(),
      loadSettings(),
      loadOnboarding(),
      refreshEngine(),
      refreshListenStatus(),
      loadCards(),
      loadPending(),
      loadGatewayEvents(),
      loadTaskState(),
    ]);
  }

  async function ensureLocalOwnerSession() {
    if (!["localhost", "127.0.0.1", "::1"].includes(window.location.hostname)) return;
    try {
      await fetch("/api/phase-zero/local-owner-session", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch {
      // The normal engine/status calls below will render the honest unavailable states.
    }
  }

  // Map the engine's durable profile record (snake_case) onto the UI profile shape.
  function profileFromEngine(p, base = EMPTY_PROFILE) {
    const src = p || {};
    return {
      ...base,
      name: src.name || "",
      summary: src.summary || "",
      phone: src.phone || "",
      timezone: src.timezone || base.timezone || EMPTY_PROFILE.timezone,
      trustDial: src.trust_dial || base.trustDial || EMPTY_PROFILE.trustDial,
      doNotTouch: src.always_ask || "",
      lastClarification: src.last_clarification || "",
    };
  }

  async function loadProfile() {
    // Read the stated basics from the ENGINE's durable profile drawer (survives serverless + the
    // brain reads it) — NOT the old ephemeral local-file store where a fresh user's basics vanished.
    const data = await jsonFetch("/api/owner/profile");
    setProfile(profileFromEngine(data.profile, EMPTY_PROFILE));
  }

  async function saveProfile(nextProfile = profile) {
    const source = { ...EMPTY_PROFILE, ...(nextProfile || {}) };
    // Persist the stated basics to the ENGINE's durable, brain-visible profile drawer. The
    // confirmation screen ("What you told me") reads them straight back from here, so what a user
    // tells Anticipy in onboarding now actually survives and the assistant learns it.
    const data = await jsonFetch("/api/owner/profile", {
      method: "POST",
      body: JSON.stringify({
        name: (source.name || "").trim(),
        summary: (source.summary || "").trim(),
        phone: (source.phone || "").trim(),
        timezone: source.timezone || "",
        trust_dial: source.trustDial || "",
        always_ask: (source.doNotTouch || "").trim(),
        last_clarification: (source.lastClarification || "").trim(),
      }),
    });
    setProfile(profileFromEngine(data.profile, source));
  }

  async function loadSettings() {
    const data = await jsonFetch("/api/settings");
    setSettings({ ...DEFAULT_SETTINGS, ...(data.settings || {}) });
  }

  async function saveSettings() {
    const data = await jsonFetch("/api/settings", {
      method: "POST",
      body: JSON.stringify({ settings }),
    });
    setSettings({ ...DEFAULT_SETTINGS, ...(data.settings || {}) });
  }

  async function loadOnboarding() {
    const data = await jsonFetch("/api/onboarding/state");
    setOnboarding(data.onboarding || { currentStep: "welcome", statusByStep: {} });
  }

  async function saveOnboarding(next) {
    const data = await jsonFetch("/api/onboarding/state", {
      method: "POST",
      body: JSON.stringify({ onboarding: next }),
    });
    setOnboarding(data.onboarding || next);
  }

  async function refreshEngine() {
    try {
      const data = await jsonFetch("/api/status");
      setEngineState({
        ok: data.engine === "ok",
        label: data.engine === "ok" ? "engine ready" : "engine degraded",
        extensionConnected: Boolean(data.extension_connected),
      });
    } catch {
      setEngineState({ ok: false, label: "engine unavailable", extensionConnected: false });
    }
  }

  async function refreshListenStatus() {
    try {
      const data = await jsonFetch("/api/listen/status");
      const running = isListeningStatus(data);
      setListenStatus({ ...data, running, status: running ? "listening" : data.status || "stopped" });
    } catch {
      setListenStatus({ status: "unavailable", running: false, listening: false });
    }
  }

  // Returns the freshly-loaded cards (not just setState) so callers can reconcile against the
  // AUTHORITATIVE board — the durable record is the source of truth, and a send's live reply is
  // driven off it, not only off the ingest response (which can race-return an empty cards list
  // even though the card was persisted). Null on a failed load so a caller can tell "no board"
  // apart from "board is genuinely empty".
  async function loadCards() {
    try {
      const data = await jsonFetch("/api/owner/cards?limit=50");
      const list = Array.isArray(data.cards) ? data.cards : [];
      setEngineCards(list);
      return list;
    } catch {
      setEngineCards([]);
      return null;
    }
  }

  // FIX-06 (2026-07-02): the app could RESOLVE asks but never LISTED them — the
  // "waiting for your yes" room was invisible. This is the read half of that loop.
  async function loadPending() {
    try {
      const data = await jsonFetch("/api/pending");
      setPendingAsks(Array.isArray(data.pending) ? data.pending : []);
    } catch {
      setPendingAsks([]);
    }
  }

  async function resolvePending(askId, approved) {
    try {
      await jsonFetch("/api/resolve", {
        method: "POST",
        body: JSON.stringify({ ask_id: askId, approved }),
      });
    } catch {
      /* the reload below shows the honest state either way */
    }
    await Promise.allSettled([loadPending(), loadCards(), loadGatewayEvents()]);
  }

  async function loadGatewayEvents() {
    try {
      const data = await jsonFetch("/api/proactive/gateway?limit=30");
      setGatewayEvents(Array.isArray(data.events) ? data.events : []);
    } catch {
      setGatewayEvents([]);
    }
  }

  async function loadTaskState() {
    const [commentData, mirrorData, sortData] = await Promise.all([
      jsonFetch("/api/tasks/comments"),
      jsonFetch("/api/tasks/text-mirror"),
      jsonFetch("/api/tasks/sort"),
    ]);
    setComments(commentData.comments || {});
    setTextMirror(mirrorData.textMirror || {});
    setSortModeState(sortData.sort?.mode || "priority");
  }

  async function setSortMode(mode) {
    setSortModeState(mode);
    await jsonFetch("/api/tasks/sort", { method: "POST", body: JSON.stringify({ mode }) });
  }

  async function saveComment(taskId, comment) {
    const data = await jsonFetch("/api/tasks/comments", {
      method: "POST",
      body: JSON.stringify({ taskId, comment }),
    });
    setComments(data.comments || {});
  }

  async function setMirror(taskId, status) {
    const data = await jsonFetch("/api/tasks/text-mirror", {
      method: "POST",
      body: JSON.stringify({ taskId, status }),
    });
    setTextMirror(data.textMirror || {});
  }

  async function submitTranscript() {
    const typed = intakeText.trim();
    if (!typed) return;

    // A short "yes"/"no" typed into the composer resolves the most recent waiting ask — the same
    // as tapping its chip. A real instruction (more than a few words) always flows to the brain.
    const active = activePendingAsk();
    const shortReply = typed.split(/\s+/).length <= 5;
    if (active && shortReply && YES_RE.test(typed)) {
      setIntakeText("");
      await conversationResolve(active, true, typed);
      return;
    }
    if (active && shortReply && NO_RE.test(typed)) {
      setIntakeText("");
      await conversationResolve(active, false, typed);
      return;
    }

    setIngestBusy(true);
    setIngestMessage("");
    appendUserLine(typed);
    // Snapshot the cards already on the board so the reconcile below can tell a card THIS send just
    // created apart from the ones already there (returning users carry many). id OR ask_id — a card
    // may key on either.
    const priorIds = new Set((engineCards || []).map((c) => c && (c.id || c.ask_id)).filter(Boolean));
    try {
      const data = await jsonFetch("/api/owner/ingest", {
        method: "POST",
        body: JSON.stringify({
          text: typed,
          source: "phase_zero_text",
          execute_actions: true,
          meta: { ui: "phase_zero" },
        }),
      });
      setIngestMessage("");
      setIntakeText("");
      // 1) Voice whatever the ingest response returned (deduped by card id inside appendCardReplies).
      const responseCards = Array.isArray(data.cards) ? data.cards : [];
      if (responseCards.length) setEngineCards(responseCards);
      appendCardReplies(responseCards);
      // 2) AUTHORITATIVE RECONCILE — the durable board is the source of truth, so drive the live reply
      // off it too, not only off the ingest response. The response's `cards` list can race-return
      // empty even when the card WAS persisted (the exact "no bubble live, but it's there after a
      // reload" bug). Reload the board and voice any card that appeared with THIS send but wasn't in
      // the response — scoped to genuinely new ids so a returning user's older cards are never
      // re-voiced, and deduped so a card already voiced in step 1 is never doubled.
      const board = await loadCards();
      const newlyAppeared = (Array.isArray(board) ? board : []).filter((c) => {
        const id = c && (c.id || c.ask_id);
        return id && !priorIds.has(id);
      });
      appendCardReplies(newlyAppeared);
    } catch (_error) {
      // Never leave the thread on dead silence, and never leak a raw "Request failed: N". Degrade
      // warmly right in the conversation, the same way runWebTask/runDerive already do. Only the
      // ingest fetch itself can land here — loadCards/loadGatewayEvents each swallow their own errors.
      setIngestMessage("");
      appendMessages({
        role: "assistant",
        text: "I'm having trouble reaching my brain for a second — mind trying that again?",
        tone: "do",
      });
    } finally {
      setIngestBusy(false);
    }
    // Telemetry refresh is best-effort and self-swallowing; kept out of the try so a gateway hiccup
    // can never masquerade as an ingest failure once the reply has already landed.
    await loadGatewayEvents();
  }

  async function uploadFile() {
    if (!selectedFile) return;
    setIngestBusy(true);
    setIngestMessage("");
    appendUserLine(`Sent a recording to read${selectedFile?.name ? `: ${selectedFile.name}` : ""}.`);
    const priorIds = new Set((engineCards || []).map((c) => c && (c.id || c.ask_id)).filter(Boolean));
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      form.append("source", "phase_zero_upload");
      form.append("execute_actions", "true");
      const data = await jsonFetch("/api/owner/upload", { method: "POST", body: form });
      setIngestMessage("");
      setSelectedFile(null);
      // Same authoritative-reconcile as the typed send: voice the response cards, then voice any card
      // that appeared on the durable board with this upload but wasn't in the response (deduped).
      const responseCards = Array.isArray(data.cards) ? data.cards : [];
      if (responseCards.length) setEngineCards(responseCards);
      appendCardReplies(responseCards);
      const board = await loadCards();
      const newlyAppeared = (Array.isArray(board) ? board : []).filter((c) => {
        const id = c && (c.id || c.ask_id);
        return id && !priorIds.has(id);
      });
      appendCardReplies(newlyAppeared);
    } catch (_error) {
      // Warm degradation instead of dead silence or a raw "Request failed: N".
      setIngestMessage("");
      appendMessages({
        role: "assistant",
        text: "I couldn't quite catch that recording — mind sending it again?",
        tone: "do",
      });
    } finally {
      setIngestBusy(false);
    }
    await loadGatewayEvents();
  }

  // "Do it on the web": POST the task to /api/browser/run -> engine /agent/run (the connected
  // Chrome). /agent/run returns a JUDGE-verified outcome, so I only say "done" when the judge
  // blessed it — a walled/unverified run is handed back honestly, never faked as complete.
  async function runWebTask() {
    const task = webTask.trim();
    if (!task || webBusy) return;
    setWebBusy(true);
    setWebReceipt(null);
    try {
      const data = await jsonFetch("/api/browser/run", {
        method: "POST",
        body: JSON.stringify({ task }),
      });
      const done = Boolean(data.task_succeeded);
      const answer = String(data.answer || "").trim();
      if (done && answer) {
        setWebReceipt({ ok: true, text: `Here's what I found: ${answer.slice(0, 500)}` });
      } else if (done) {
        setWebReceipt({ ok: true, text: "Done — I finished that on the web." });
      } else {
        setWebReceipt({ ok: false, text: "I couldn't finish that one on the site. Want me to try again, or take it from here?" });
      }
      await loadCards();
      await loadGatewayEvents();
    } catch (_error) {
      setWebReceipt({ ok: false, text: "I couldn't reach the web helper just now. Try again in a moment." });
    } finally {
      setWebBusy(false);
    }
  }

  // "Anticipate now" (FIX-07): one derive pass — the engine reads its world (memory, open loops,
  // calendar), derives at most two UNSPOKEN needs, acts browser-only, and texts. A quiet day
  // returns {"derived": []} and lands nothing. POST /api/derive -> engine /derive/tick.
  async function runDerive() {
    if (deriveBusy) return;
    setDeriveBusy(true);
    setDeriveReceipt(null);
    try {
      const data = await jsonFetch("/api/derive", { method: "POST" });
      const derived = Array.isArray(data.derived) ? data.derived : [];
      setDeriveReceipt(derived.length
        ? { ok: true, text: `I got ahead of ${derived.length} thing${derived.length === 1 ? "" : "s"} for you.` }
        : { ok: true, text: "Quiet right now — nothing worth getting ahead of." });
      await loadCards();
      await loadGatewayEvents();
    } catch {
      setDeriveReceipt({ ok: false, text: "I couldn't run that just now. Try again in a moment." });
    } finally {
      setDeriveBusy(false);
    }
  }

  // "Send my digest now" (FIX-14/NF10): deliver the day's accumulated non-urgent items as ONE
  // message and clear the queue. A quiet day returns {sent:false}. POST /api/digest -> /digest/deliver.
  async function runDigest() {
    if (digestBusy) return;
    setDigestBusy(true);
    setDigestReceipt(null);
    try {
      const data = await jsonFetch("/api/digest", { method: "POST" });
      setDigestReceipt(data.sent
        ? { ok: true, text: `Sent — your ${data.count || ""} quiet item${data.count === 1 ? "" : "s"} went out as one note.`.replace("  ", " ") }
        : { ok: true, text: "Nothing to send yet — I'll gather the day's quiet items for the next digest." });
      await loadGatewayEvents();
    } catch {
      setDigestReceipt({ ok: false, text: "I couldn't send the digest just now. Try again in a moment." });
    } finally {
      setDigestBusy(false);
    }
  }

  // STOP for an in-flight "On it — you can stop me" chore (FIX-06b): halt the reversible chore and
  // flip the card to stopped. POST /api/owner/stop -> engine /owner/stop. Reversible chores only;
  // an unknown/finished card no-ops honestly.
  async function stopOwnerCard(card) {
    if (!card?.id) return;
    try {
      await jsonFetch("/api/owner/stop", { method: "POST", body: JSON.stringify({ card_id: card.id }) });
    } catch {
      /* the reload below shows the honest state either way */
    }
    await Promise.allSettled([loadCards(), loadGatewayEvents()]);
  }

  async function resolveCard(card, approved) {
    if (card.askId) {
      try {
        await jsonFetch("/api/resolve", {
          method: "POST",
          body: JSON.stringify({ ask_id: card.askId, approved }),
        });
        // Reload pending too so a resolved ask's chips clear everywhere the app reads engine truth.
        await loadCards();
        await loadPending();
        await loadGatewayEvents();
        return true;
      } catch {
        await setMirror(card.id, "failed");
        return false;
      }
    }
    // FIX-4.2 (no fake success): a card with no askId has NO engine ask to approve or deny — it is
    // a status object ("On it"/informational/resting). Clearing it is a LOCAL dismiss only (the row
    // retires from view via CardBoard.commit -> retire); we deliberately write NO engine or text-
    // mirror state here, so the button never fakes a close it didn't do. The old else-branch wrote a
    // fabricated "coming_soon" mirror — a silent no-op dressed as success. That lie is gone, and the
    // board also hides the "Go ahead" primary on non-ask cards (see CardRow), so no button lies.
    // Returning false lets the conversation path tell success (real resolve) from a no-op dismiss.
    return false;
  }

  // A6 swipe deck — "Allow autonomy" on a card = the owner opting this class of work OUT of
  // ask-first. It raises the REAL engine autonomy gate (POST /api/owner/autonomy full_send — the
  // same gate the Settings dropdown drives, FIX-04), and when the card is a waiting ask it approves
  // that ask in the same gesture so the deck advances honestly. Fully reversible from Settings; it
  // never bypasses the money/irreversible hard-stop, which stays ask-first at any autonomy level.
  async function allowAutonomy(card) {
    try {
      await jsonFetch("/api/owner/autonomy", { method: "POST", body: JSON.stringify({ mode: "full_send" }) });
      if (card?.askId) {
        await jsonFetch("/api/resolve", { method: "POST", body: JSON.stringify({ ask_id: card.askId, approved: true }) });
      }
    } catch {
      /* the reload below shows the honest state either way */
    }
    await Promise.allSettled([loadCards(), loadPending(), loadGatewayEvents()]);
  }

  // FIX-12: close the wall-handoff loop from the board. A connected-Chrome run that paused on a
  // login/verification wall hands back (and texts you); once you've cleared the wall in your own
  // browser, "Continue" resumes from the now-unblocked page. POST /api/agent/resume -> engine
  // /agent/resume. It never types credentials, clears the wall, spends, or checks out.
  async function continueCard(card) {
    const raw = card.raw || {};
    const args = raw.args || {};
    const task = String(args.task_text || card.heard || card.title || "").trim();
    const startUrl = String(card.browserReceipt?.url || args.start_url || "").trim();
    if (!task || !startUrl) return;
    try {
      await jsonFetch("/api/agent/resume", {
        method: "POST",
        body: JSON.stringify({ task, start_url: startUrl }),
      });
    } catch {
      /* the reload below shows the honest state either way */
    }
    await Promise.allSettled([loadCards(), loadGatewayEvents()]);
  }

  async function startLocalListening() {
    try {
      await jsonFetch("/api/listen/start", { method: "POST" });
      await refreshListenStatus();
      await loadGatewayEvents();
    } catch {
      setListenStatus({ status: "unavailable", running: false, listening: false });
    }
  }

  async function stopLocalListening() {
    try {
      await jsonFetch("/api/listen/stop", { method: "POST" });
      await refreshListenStatus();
      await loadGatewayEvents();
    } catch {
      setListenStatus({ status: "unavailable", running: false, listening: false });
    }
  }

  async function startBrowserListening() {
    setListenMessage("");
    setLiveTranscript([]);
    setInterimTranscript("");
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setListenState("unavailable");
        setListenMessage("This browser cannot open the microphone.");
        return;
      }
      const { ws_url: wsUrl } = await jsonFetch("/api/listen/stream");
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true },
      });
      mediaStreamRef.current = stream;
      const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => setListenState("listening");
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "transcript") {
          if (msg.is_final && msg.transcript?.trim()) {
            setLiveTranscript((current) => [...current, msg.transcript.trim()]);
            setInterimTranscript("");
          } else {
            setInterimTranscript(msg.transcript || "");
          }
        }
        if (msg.type === "processing") setListenState("processing");
        if (msg.type === "ingest_result") {
          const result = msg.result || {};
          const responseCards = Array.isArray(result.cards) ? result.cards : [];
          const priorIds = new Set((engineCards || []).map((c) => c && (c.id || c.ask_id)).filter(Boolean));
          if (responseCards.length) setEngineCards(responseCards);
          setListenState(responseCards.length ? "cards_created" : "no_task_created");
          // Voice the response cards, then reconcile off the authoritative board — same guard the
          // typed/upload sends use, so a race-empty voice ingest still lands the reply live (deduped).
          appendCardReplies(responseCards);
          loadCards().then((board) => {
            const newlyAppeared = (Array.isArray(board) ? board : []).filter((c) => {
              const id = c && (c.id || c.ask_id);
              return id && !priorIds.has(id);
            });
            if (newlyAppeared.length) {
              appendCardReplies(newlyAppeared);
              setListenState((cur) => (cur === "no_task_created" ? "cards_created" : cur));
            }
          });
          loadGatewayEvents();
        }
        if (msg.type === "ingest_error" || msg.type === "error") {
          setListenState("unavailable");
          setListenMessage(msg.error || msg.message || "Listening failed.");
        }
      };
      ws.onerror = () => {
        setListenState("unavailable");
        setListenMessage("I could not reach the listening stream.");
        stopBrowserListening();
      };
      ws.onclose = () => setListenState((current) => current === "listening" ? "stopped" : current);
      processor.onaudioprocess = (audioEvent) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        const float32 = audioEvent.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i += 1) {
          int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32768));
        }
        ws.send(int16.buffer);
      };
      source.connect(processor);
      processor.connect(audioContext.destination);
    } catch (error) {
      stopBrowserListening();
      const message = error instanceof Error ? error.message : String(error);
      setListenState(message.toLowerCase().includes("permission") ? "permission_denied" : "unavailable");
      setListenMessage(message);
    }
  }

  function stopBrowserListening() {
    if (wsRef.current) {
      try { wsRef.current.close(); } catch {}
      wsRef.current = null;
    }
    if (audioContextRef.current) {
      try { audioContextRef.current.close(); } catch {}
      audioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    setListenState("stopped");
  }

  const commonProps = {
    auth,
    setAuth,
    profile,
    setProfile,
    settings,
    setSettings,
    pendingAsks,
    resolvePending,
    thread,
    conversationResolve,
    conversationAutonomy,
    onboarding,
    engineState,
    listenStatus,
    listenState,
    listenMessage,
    liveTranscript,
    interimTranscript,
    intakeText,
    setIntakeText,
    selectedFile,
    setSelectedFile,
    ingestBusy,
    ingestMessage,
    cards,
    gatewayEvents,
    comments,
    textMirror,
    sortMode: sortModeState,
    setSortMode,
    webTask,
    setWebTask,
    webBusy,
    webReceipt,
    runWebTask,
    deriveBusy,
    deriveReceipt,
    runDerive,
    digestBusy,
    digestReceipt,
    runDigest,
    stopCard: stopOwnerCard,
    saveProfile,
    saveSettings,
    saveOnboarding,
    refreshEngine,
    refreshListenStatus,
    loadGatewayEvents,
    submitTranscript,
    uploadFile,
    saveComment,
    resolveCard,
    allowAutonomy,
    continueCard,
    startBrowserListening,
    stopBrowserListening,
    startLocalListening,
    stopLocalListening,
  };

  // Welcome is a standalone landing page (its own <main className="pz-land">). It must NOT be
  // wrapped in AppShell — that re-adds the appbar + the pz-top "Vibe your life." H1 + the journey
  // rail around a page that already has its own bar, i.e. the double-chrome bug. UI_SPEC step 2.
  if (screen === "welcome") return <WelcomeScreen />;

  // SESSION GATE (multi-user). Only /welcome and /sign are public. Every other surface — the board,
  // onboarding, setup, settings — holds a real person's data, so without an authenticated Supabase
  // session we render the sign-in screen instead of the protected surface. APP_OPEN preserves today's
  // single-owner flow and flips off at the multi-user deploy (see the constant near the top).
  const gated = !APP_OPEN && !auth.session && screen !== "sign";

  let content = null;
  if (gated) content = <SignScreen {...commonProps} />;
  else if (screen === "sign") content = <SignScreen {...commonProps} />;
  else if (screen === "setup") content = <SetupScreen {...commonProps} />;
  else if (screen.startsWith("onboarding")) content = <OnboardingScreen screen={screen} {...commonProps} />;
  else if (screen === "settings") content = <SettingsScreen {...commonProps} />;
  else content = <MainScreen {...commonProps} />;

  return (
    <AppShell screen={screen} profile={profile} session={auth.session} engineState={engineState}>
      {content}
    </AppShell>
  );
}
