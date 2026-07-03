"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createBrowserSupabaseClient } from "../../lib/supabase/client";
import { supabaseMissingMessage } from "../../lib/supabase/config";
import { FIXTURES, NAV_ITEMS, ONBOARDING_STAGES, SOURCE_TAGS, SOURCE_TRUTH_PATH } from "./sourceData";

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

const SCREEN_TITLES = {
  welcome: "Welcome",
  sign: "Sign in",
  setup: "Setup",
  great: "Great",
  done: "Done",
  board: "",
  mp3: "MP3 upload",
  "go-to": "Go-To",
  memory: "Memory",
  settings: "Settings",
};

const JOURNEY_ITEMS = [
  { href: "/welcome", label: "Welcome", screens: ["welcome"] },
  { href: "/sign", label: "Sign", screens: ["sign"] },
  { href: "/onboarding/2", label: "You", screens: ["onboarding-2"] },
  { href: "/", label: "Listen", screens: ["board"] },
  { href: "/go-to", label: "Review", screens: ["go-to"] },
  { href: "/memory", label: "Memory", screens: ["memory", "settings"] },
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

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "content-type": "application/json" }),
      ...(options.headers || {}),
    },
    credentials: "same-origin",
    cache: "no-store",
  });
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

function normalizeEngineCard(card) {
  const gatewayTags = Array.isArray(card.gateway?.source_of_truth_tags)
    ? card.gateway.source_of_truth_tags
    : [];
  return {
    id: card.id || card.ask_id || `engine-${Math.random().toString(16).slice(2)}`,
    // De-jargon (UI step 1): human-facing card copy, never engine internals. CANON/UI_FLOW law.
    category: card.disposition === "blocked" ? "Needs a yes" : card.status === "waiting" || card.disposition === "ask" ? "Waiting for you" : "On it",
    title: card.title || card.action || card.source_text || "Caught something for you.",
    heard: card.source_text || card.text || "",
    ignored: "",
    browserWork: card.execution?.route || card.action || "",
    checkIn: card.status === "waiting" || card.disposition === "ask" ? "Okay for me to go ahead?" : "",
    proof: Array.isArray(card.proof) && card.proof.length ? "Here's what I did." : "",
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
  if (typeof window !== "undefined" && !document.body.classList.contains("pz-debug")) return null;
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
              const current = (screen === "board" && item.href === "/") || item.href.includes(screen);
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
  if (typeof window !== "undefined" && !document.body.classList.contains("pz-debug")) return null;
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
  if (typeof window !== "undefined" && !document.body.classList.contains("pz-debug")) return null;
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
        <h2>{auth.session ? "You are in." : "Come in."}</h2>
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

function SetupScreen({ engineState, listenStatus, refreshEngine, refreshListenStatus }) {
  return (
    <div className="pz-scene">
      <section className="pz-stage-hero pz-stage-minimal">
        <StatusPill value={engineState.ok ? "live" : "unavailable"} />
        <h2>Let&rsquo;s get you set up.</h2>
        <p>Two quick things, then I can start.</p>
        <div className="pz-readiness-list">
          <ReadinessRow label="Browser helper" ok={engineState.extensionConnected} text={engineState.extensionConnected ? "Connected" : "Not connected yet"} />
          <ReadinessRow label="Listening" ok={listenStatus.status !== "unavailable"} text={humanStatus(listenStatus.status || "read_only")} />
        </div>
        {!engineState.extensionConnected ? (
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
          </div>
        ) : null}
      </section>
      <div className="pz-actions pz-actions-simple">
        <a className="pz-button primary pz-button-xl" href="/connect">Continue</a>
        <button className="pz-button ghost" onClick={() => { refreshEngine(); refreshListenStatus(); }} type="button">Check again</button>
      </div>
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
            <SourceTagList tags={stage.sourceTags} />
          </div>
          <ProfileBasicsForm profile={profile} setProfile={setProfile} saveProfile={saveProfile} />
        </section>
        <OnboardingTimeline onboarding={onboarding} activeRoute="/onboarding/2" />
      </div>
    );
  }

  const isReadLayer = ["/onboarding/3", "/onboarding/5", "/onboarding/7"].includes(stage.route);

  return (
    <div className="pz-scene">
      <section className="pz-stage-hero pz-stage-minimal">
        <StatusPill value={isReadLayer ? "live" : stage.status} />
        <h2>{stage.title}</h2>
        <p>{stage.copy}</p>
        <SourceTagList tags={stage.sourceTags} />
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

  useEffect(() => {
    jsonFetch("/api/onboard/permissions")
      .then((data) => setServices(Array.isArray(data.services) ? data.services : []))
      .catch(() => setServices([]));
  }, []);

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
        <StatusPill value={engineState?.extensionConnected ? "live" : "unavailable"} />
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
  if (index < 0 || index === ONBOARDING_STAGES.length - 1) return "/great";
  return ONBOARDING_STAGES[index + 1].route;
}

function ProfileBasicsForm({ profile, setProfile, saveProfile }) {
  function patch(next) {
    setProfile((current) => ({ ...current, ...next }));
  }

  function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = {
      ...profile,
      name: String(form.get("name") || ""),
      summary: String(form.get("summary") || ""),
      phone: String(form.get("phone") || ""),
      timezone: String(form.get("timezone") || "America/Vancouver"),
      trustDial: String(form.get("trustDial") || "Regular"),
      doNotTouch: String(form.get("doNotTouch") || ""),
    };
    setProfile(next);
    saveProfile(next);
  }

  return (
    <form className="pz-panel pz-form" onSubmit={submit}>
      <label>
        <span>Name</span>
        <input name="name" value={profile.name || ""} onChange={(event) => patch({ name: event.target.value })} />
      </label>
      <label>
        <span>One-sentence summary</span>
        <input name="summary" value={profile.summary || ""} onChange={(event) => patch({ summary: event.target.value })} />
      </label>
      <label>
        <span>Phone</span>
        <input name="phone" value={profile.phone || ""} onChange={(event) => patch({ phone: event.target.value })} />
      </label>
      <label>
        <span>Timezone</span>
        <input name="timezone" value={profile.timezone || ""} onChange={(event) => patch({ timezone: event.target.value })} />
      </label>
      <label>
        <span>Trust dial</span>
        <select name="trustDial" value={profile.trustDial || "Regular"} onChange={(event) => patch({ trustDial: event.target.value })}>
          <option>Regular</option>
          <option>Limited</option>
          <option>Full-Send</option>
        </select>
      </label>
      <label>
        <span>Always ask before</span>
        <textarea name="doNotTouch" value={profile.doNotTouch || ""} onChange={(event) => patch({ doNotTouch: event.target.value })} />
      </label>
      <div className="pz-form-submit-row">
        <button className="pz-button primary" type="submit">Save</button>
        <a className="pz-button ghost" href="/onboarding/3">Next</a>
      </div>
    </form>
  );
}

function OnboardingTimeline({ onboarding, activeRoute }) {
  return (
    <section className="pz-timeline">
      {ONBOARDING_STAGES.map((stage) => (
        <a key={stage.route} className={`pz-timeline-step ${activeRoute === stage.route ? "active" : ""}`} href={stage.route}>
          <span>{stage.label}</span>
          <small>{onboarding.statusByStep?.[stage.route] || stage.status}</small>
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

function LearnedMemoryPanel({ drawers, error }) {
  if (error) return <p className="pz-note">I could not read memory: {error}</p>;
  if (!drawers) return <p className="pz-note">Reading what I learned…</p>;
  return (
    <section className="pz-grid two pz-memory-grid">
      <ProfileSection title={`Facts I learned (${drawers.profile?.count || 0})`} items={drawerTexts(drawers.profile)} />
      <ProfileSection title={`What I inferred — never promoted (${drawers.derived?.count || 0})`} items={drawerTexts(drawers.derived)} />
      <ProfileSection title={`Open loops (${drawers.open_loops?.count || 0})`} items={drawerTexts(drawers.open_loops)} />
      <ProfileSection title={`Recent history (${drawers.history?.count || 0})`} items={drawerTexts(drawers.history).slice(-6)} />
    </section>
  );
}

function GreatScreen({ profile, setProfile, saveProfile }) {
  const [clarification, setClarification] = useState(profile.lastClarification || "");
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState("");
  const { drawers, error: drawersError } = useMemoryDrawers();

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
      window.location.href = "/done";
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
        <SourceTagList tags={["ST-LAYERED-ONBOARDING", "ST-MEMORY-COMPOUNDS", "ST-TRUST-DIAL"]} />
      </section>
      <section className="pz-profile-summary">
        <ProfileSection title="You" items={[
          profile.name || "Name not confirmed yet.",
          profile.summary || "Summary not confirmed yet.",
          `Trust dial: ${profile.trustDial || "Regular"}`,
        ]} />
        <ProfileSection title="People" items={(profile.people || []).map((person) => `${person.name}: ${person.role || person.relationship || "important"}`)} />
        <ProfileSection title="Tools and systems" items={profile.tools || []} />
        <ProfileSection title="Open loops" items={profile.openLoops || []} />
      </section>
      <LearnedMemoryPanel drawers={drawers} error={drawersError} />
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
        <a className="pz-button ghost" href="/onboarding/8">Back</a>
        <button className="pz-button primary pz-button-xl" type="button" onClick={confirmDossier} disabled={confirmBusy}>
          {confirmBusy ? "Saving…" : "Looks right"}
        </button>
      </div>
      {confirmMessage ? <p className="pz-note">{confirmMessage}</p> : null}
    </div>
  );
}

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

function DoneScreen() {
  return (
    <div className="pz-scene">
      <section className="pz-stage-hero pz-stage-minimal">
        <StatusPill value="live" />
        <h2>You are ready.</h2>
        <p>Go to the assistant. Speak, upload, or review what is ready for your last tap.</p>
        <div className="pz-actions pz-actions-simple">
          <a className="pz-button primary pz-button-xl" href="/">Open Anticipy</a>
          <a className="pz-button ghost" href="/settings">Settings</a>
        </div>
      </section>
    </div>
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

function MainScreen(props) {
  return (
    <div className="pz-scene pz-board-scene pz-main-collapsed">
      <ActiveListeningPanel {...props} />
      <OneInput {...props} />
      <PendingAsksPanel pendingAsks={props.pendingAsks} onResolve={props.resolvePending} />
      {props.cards.length ? <TaskBoard {...props} limit={4} /> : null}
    </div>
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

function FeaturedTaskCard({ card, comment, onComment, onResolve }) {
  const [draft, setDraft] = useState(comment);

  useEffect(() => {
    setDraft(comment);
  }, [comment]);

  return (
    <article className={`pz-featured-task pz-task-${card.risk}`}>
      <div>
        <span className="pz-category">{card.category}</span>
        <h3>{humanTitle(card.title)}</h3>
        <p>{card.checkIn}</p>
      </div>
      <details>
        <summary>Proof</summary>
        <dl>
          <div><dt>Heard</dt><dd>{card.heard}</dd></div>
          <div><dt>Proof</dt><dd>{card.proof}</dd></div>
          <div><dt>Memory</dt><dd>{card.memory}</dd></div>
        </dl>
      </details>
      <label className="pz-comment">
        <span>Quick note</span>
        <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Add a note before I continue." />
      </label>
      <div className="pz-actions pz-actions-simple">
        <button className="pz-button primary" type="button" onClick={() => onResolve(card, true)}>Approve</button>
        <button className="pz-button ghost" type="button" onClick={() => onResolve(card, false)}>Not now</button>
        <button className="pz-button subtle" type="button" onClick={() => onComment(card.id, draft)}>Save note</button>
      </div>
    </article>
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

function TranscriptInput({ intakeText, setIntakeText, submitTranscript, ingestBusy, ingestMessage, compact = false }) {
  return (
    <section className={`pz-panel pz-transcript-input ${compact ? "compact" : ""}`}>
      <div className="pz-panel-head">
        <div>
          <h3>What should I handle?</h3>
          <p>Type it instead of speaking.</p>
        </div>
        <StatusPill value="live" />
      </div>
      <textarea
        value={intakeText}
        onChange={(event) => setIntakeText(event.target.value)}
        placeholder="Paste a transcript, or type the messy real-life thing someone asked you to do."
      />
      <div className="pz-actions">
        <button className="pz-button primary" type="button" onClick={submitTranscript} disabled={ingestBusy || !intakeText.trim()}>
          {ingestBusy ? "Reading..." : "Send"}
        </button>
        <a className="pz-button ghost" href="/mp3">Upload</a>
      </div>
      {ingestMessage ? <p className="pz-note">{ingestMessage}</p> : null}
    </section>
  );
}

function GatewayCircuit({ gatewayEvents = [], compact = false }) {
  const latest = gatewayEvents.slice(0, compact ? 3 : 6);
  return (
    <section className={`pz-gateway ${compact ? "compact" : ""}`} aria-label="Proactive gateway circuit">
      <div className="pz-panel-head">
        <div>
          <h3>Live circuit</h3>
          <p>Input, brain, memory, browser, voice, proof, and follow-up now share one record.</p>
        </div>
        <StatusPill value={latest.length ? "live" : "read_only"} />
      </div>
      <div className="pz-circuit-line" aria-hidden="true">
        {["Input", "Brain", "Memory", "Action", "Proof", "Follow-up"].map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
      {latest.length ? (
        <div className="pz-gateway-list">
          {latest.map((event) => {
            const actions = Array.isArray(event.suggested_actions) ? event.suggested_actions.length : 0;
            const memories = Array.isArray(event.memory_mutations) ? event.memory_mutations.length : 0;
            const proof = Array.isArray(event.proof) ? event.proof.length : 0;
            const hasBrowser = Boolean(event.browser_run);
            return (
              <article className="pz-gateway-row" key={event.event_id}>
                <div>
                  <span>{event.source_label || event.source || "gateway"} · {formatGatewayTime(event.created_at)}</span>
                  <strong>{event.structured_summary || "Gateway event recorded."}</strong>
                  <small>{shortId(event.event_id)} · {actions} actions · {memories} memory · {proof} proof{hasBrowser ? " · browser" : ""}</small>
                </div>
                <StatusPill value={event.status || "observed"} />
                <SourceTagList tags={(event.source_of_truth_tags || SOURCE_TAGS).slice(0, 4)} />
              </article>
            );
          })}
        </div>
      ) : (
        <p className="pz-note">No gateway events yet. Type, upload, approve, or start listening to create the first circuit record.</p>
      )}
    </section>
  );
}

function Mp3Screen(props) {
  return (
    <div className="pz-scene pz-upload-scene">
      <section className="pz-stage-hero pz-stage-minimal pz-page-intro">
        <StatusPill value="live" />
        <h2>Drop in the messy thing.</h2>
        <p>Upload audio, paste a transcript, or type a note. Anticipy turns it into review cards.</p>
      </section>
      <FileUpload {...props} />
      <GatewayCircuit gatewayEvents={props.gatewayEvents} compact />
      <TranscriptInput {...props} />
    </div>
  );
}

function FileUpload({ selectedFile, setSelectedFile, uploadFile, ingestBusy, ingestMessage }) {
  return (
    <section className="pz-panel pz-form">
      <label>
        <span>Audio or transcript file</span>
        <input
          type="file"
          accept=".txt,.md,.vtt,.srt,.json,.csv,.mp3,.m4a,.wav,.aac,.flac,.ogg"
          onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
        />
      </label>
      {selectedFile ? <p className="pz-note">Selected: {selectedFile.name}</p> : null}
      <button className="pz-button primary" type="button" onClick={uploadFile} disabled={ingestBusy || !selectedFile}>
        {ingestBusy ? "Uploading..." : "Upload and read"}
      </button>
      {ingestMessage ? <p className="pz-note">{ingestMessage}</p> : null}
    </section>
  );
}

function GoToScreen(props) {
  return (
    <div className="pz-scene pz-review-scene">
      <section className="pz-stage-hero pz-stage-minimal pz-page-intro">
        <StatusPill value="live" />
        <h2>Pick one thing.</h2>
        <p>Approve it, pause it, or leave a note. Proof is there when you want to open it.</p>
      </section>
      <GatewayCircuit gatewayEvents={props.gatewayEvents} compact />
      <TaskBoard {...props} />
    </div>
  );
}

function TaskBoard({ cards, comments, textMirror, sortMode, setSortMode, saveComment, resolveCard, limit }) {
  const [selectedId, setSelectedId] = useState("");
  const sorted = useMemo(() => {
    const copy = [...cards];
    if (sortMode === "needs_approval") copy.sort((a, b) => Number(b.risk === "ask") - Number(a.risk === "ask"));
    if (sortMode === "source") copy.sort((a, b) => a.category.localeCompare(b.category));
    if (sortMode === "newest") copy.reverse();
    return limit ? copy.slice(0, limit) : copy;
  }, [cards, sortMode, limit]);
  const selected = sorted.find((card) => card.id === selectedId) || sorted[0];

  useEffect(() => {
    if (selected && !sorted.some((card) => card.id === selectedId)) setSelectedId(selected.id);
  }, [selected, selectedId, sorted]);

  return (
    <section className="pz-task-shell">
      <div className="pz-task-toolbar">
        <h3>{sorted.length} things ready</h3>
        <select value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
          <option value="priority">Priority</option>
          <option value="needs_approval">Needs approval</option>
          <option value="source">Source</option>
          <option value="newest">Newest</option>
        </select>
      </div>
      <div className="pz-queue">
        <div className="pz-queue-list" aria-label="Task queue">
          {sorted.map((card) => (
            <button
              key={card.id}
              type="button"
              className={`pz-queue-item ${selected?.id === card.id ? "active" : ""}`}
              onClick={() => setSelectedId(card.id)}
            >
              <span>{card.category}</span>
              <strong>{humanTitle(card.title)}</strong>
              <small>{card.risk === "ask" ? "Needs your okay" : card.risk === "blocked" ? "Stopped" : "Prepared"}</small>
            </button>
          ))}
        </div>
        {selected ? (
          <TaskCard
            key={selected.id}
            card={selected}
            comment={comments[selected.id] || ""}
            mirror={textMirror[selected.id]?.status || "coming_soon"}
            onComment={saveComment}
            onResolve={resolveCard}
          />
        ) : null}
      </div>
    </section>
  );
}

function TaskCard({ card, comment, mirror, onComment, onResolve }) {
  const [draft, setDraft] = useState(comment);

  useEffect(() => {
    setDraft(comment);
  }, [comment]);

  return (
    <article className={`pz-task pz-task-${card.risk}`}>
      <div className="pz-task-head">
        <div>
          <span className="pz-category">{card.category}</span>
          <h4>{humanTitle(card.title)}</h4>
        </div>
        <div className="pz-task-pills">
          <StatusPill value={card.mode || "seeded"} />
          <StatusPill value={card.status === "needs_approval" ? "coming_soon" : card.status} />
        </div>
      </div>
      <p className="pz-task-checkin">{card.checkIn}</p>
      <details className="pz-proof-details">
        <summary>Proof</summary>
        <dl className="pz-task-detail">
          <div><dt>Heard</dt><dd>{card.heard}</dd></div>
          <div><dt>Ignored</dt><dd>{card.ignored || "Nothing ignored on this card."}</dd></div>
          <div><dt>Browser work</dt><dd>{card.browserWork}</dd></div>
          <div><dt>Proof</dt><dd>{card.proof}</dd></div>
          <div><dt>Memory</dt><dd>{card.memory}</dd></div>
          <div><dt>Follow-up</dt><dd>{card.followUp}</dd></div>
        </dl>
      </details>
      <div className="pz-task-footer">
        <span>
          Text mirror: {humanStatus(mirror)}
          {card.gatewayEventId ? ` · Gateway ${shortId(card.gatewayEventId)}` : ""}
          {card.browserGatewayEventId ? ` · Browser ${shortId(card.browserGatewayEventId)}` : ""}
        </span>
        <SourceTagList tags={card.sourceTags} />
      </div>
      <label className="pz-comment">
        <span>Comment</span>
        <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Add a note for this task." />
      </label>
      <div className="pz-actions">
        <button className="pz-button primary" type="button" onClick={() => onResolve(card, true)}>Approve</button>
        <button className="pz-button ghost" type="button" onClick={() => onResolve(card, false)}>Not now</button>
        <button className="pz-button subtle" type="button" onClick={() => onComment(card.id, draft)}>Save note</button>
      </div>
    </article>
  );
}

function MemoryScreen({ profile, cards, gatewayEvents }) {
  const { drawers, error: drawersError, reload } = useMemoryDrawers();
  return (
    <div className="pz-scene pz-memory-scene">
      <section className="pz-stage-hero pz-stage-minimal pz-page-intro">
        <StatusPill value="live" />
        <h2>What I know.</h2>
        <p>This is my real memory — the facts, inferences, open loops, and history I hold. Anything wrong gets corrected here.</p>
      </section>
      <GatewayCircuit gatewayEvents={gatewayEvents} compact />
      <LearnedMemoryPanel drawers={drawers} error={drawersError} />
      <section className="pz-grid two pz-memory-grid">
        <ProfileSection title="People who matter" items={(profile.people || []).map((person) => `${person.name}: ${person.role || "important"}`)} />
        <ProfileSection title="Rules" items={profile.rules || []} />
      </section>
      <ContextPackInspector />
      <ForgetMePanel onDeleted={reload} />
    </div>
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

// The single-context spine, made visible. Type a moment; see the EXACT ContextPack the brain
// assembles — the same builder the decider (decide), the browser/API hands (act), and the
// voice (speak) all read through. This is the proof that context flows through one source,
// not three parallel pipes.
function ContextPackInspector() {
  const [about, setAbout] = useState("");
  const [purpose, setPurpose] = useState("decide");
  const [pack, setPack] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function inspect(event) {
    if (event) event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `/api/memory/context?about=${encodeURIComponent(about)}&purpose=${encodeURIComponent(purpose)}`,
        { cache: "no-store" },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data?.message || "Could not read the context.");
      setPack(data.context_pack || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPack(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="pz-context-inspector">
      <h3>What I&apos;d see for a moment.</h3>
      <p className="pz-note">
        One context source feeds every part of me — the decider, the browser hands, and the
        voice. Type a moment to see exactly what I&apos;d bring in.
      </p>
      <form className="pz-context-controls" onSubmit={inspect}>
        <input
          value={about}
          onChange={(e) => setAbout(e.target.value)}
          placeholder="e.g. Sam decking, or where do I work"
          aria-label="Moment to build context for"
        />
        <select value={purpose} onChange={(e) => setPurpose(e.target.value)} aria-label="Purpose">
          <option value="decide">Decide</option>
          <option value="act">Act</option>
          <option value="speak">Speak</option>
        </select>
        <button className="pz-button primary" type="submit" disabled={loading}>
          {loading ? "Reading…" : "Show context"}
        </button>
      </form>
      {error ? <p className="pz-error">{error}</p> : null}
      {pack ? (
        <div className="pz-context-pack">
          <div className="pz-context-meta">
            <span>Purpose: <strong>{pack.purpose}</strong></span>
            <span>Confidence: <strong>{(pack.top_relevance || 0).toFixed(2)}</strong></span>
            <span>{pack.abstain ? "Below floor — I won't guess" : "Confident enough to use"}</span>
            <span>{pack.item_count} item(s), {pack.budget_used} chars</span>
          </div>
          <ProfileSection title="Open loops (always complete)" items={pack.open_loops || []} />
          <ProfileSection title="Facts" items={pack.profile || []} />
          <ProfileSection title="Inferred (never promoted)" items={pack.derived || []} />
          <ProfileSection title="Recent history" items={pack.history || []} />
        </div>
      ) : null}
    </section>
  );
}

function SettingsScreen({ settings, setSettings, saveSettings, gatewayEvents }) {
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
      <GatewayCircuit gatewayEvents={gatewayEvents} compact />
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
          </div>
        </details>
      </section>
      <div className="pz-actions pz-actions-simple">
        <button className="pz-button primary pz-button-xl" type="submit">Save settings</button>
        <a className="pz-button ghost" href="/">Back to assistant</a>
      </div>
    </form>
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

  async function loadProfile() {
    const data = await jsonFetch("/api/profile");
    setProfile({ ...EMPTY_PROFILE, ...(data.profile || {}) });
  }

  async function saveProfile(nextProfile = profile) {
    const data = await jsonFetch("/api/profile", {
      method: "POST",
      body: JSON.stringify({ profile: nextProfile }),
    });
    setProfile({ ...EMPTY_PROFILE, ...(data.profile || {}) });
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

  async function loadCards() {
    try {
      const data = await jsonFetch("/api/owner/cards?limit=50");
      setEngineCards(Array.isArray(data.cards) ? data.cards : []);
    } catch {
      setEngineCards([]);
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
    setIngestBusy(true);
    setIngestMessage("");
    try {
      const data = await jsonFetch("/api/owner/ingest", {
        method: "POST",
        body: JSON.stringify({
          text: intakeText,
          source: "phase_zero_text",
          execute_actions: true,
          meta: { ui: "phase_zero" },
        }),
      });
      setEngineCards(Array.isArray(data.cards) ? data.cards : []);
      setIngestMessage(`Read ${data.observed_lines?.length || 0} lines. Created ${data.cards?.length || 0} cards.`);
      setIntakeText("");
      await loadCards();
      await loadGatewayEvents();
    } catch (error) {
      setIngestMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setIngestBusy(false);
    }
  }

  async function uploadFile() {
    if (!selectedFile) return;
    setIngestBusy(true);
    setIngestMessage("");
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      form.append("source", "phase_zero_upload");
      form.append("execute_actions", "true");
      const data = await jsonFetch("/api/owner/upload", { method: "POST", body: form });
      setEngineCards(Array.isArray(data.cards) ? data.cards : []);
      setIngestMessage(`Upload read. Created ${data.cards?.length || 0} cards.`);
      setSelectedFile(null);
      await loadCards();
      await loadGatewayEvents();
    } catch (error) {
      setIngestMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setIngestBusy(false);
    }
  }

  async function resolveCard(card, approved) {
    if (card.askId) {
      try {
        await jsonFetch("/api/resolve", {
          method: "POST",
          body: JSON.stringify({ ask_id: card.askId, approved }),
        });
        await loadCards();
        await loadGatewayEvents();
      } catch {
        await setMirror(card.id, "failed");
      }
    } else {
      await setMirror(card.id, "coming_soon");
    }
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
          setEngineCards(Array.isArray(result.cards) ? result.cards : []);
          setListenState(result.cards?.length ? "cards_created" : "no_task_created");
          loadCards();
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
    startBrowserListening,
    stopBrowserListening,
    startLocalListening,
    stopLocalListening,
  };

  // Welcome is a standalone landing page (its own <main className="pz-land">). It must NOT be
  // wrapped in AppShell — that re-adds the appbar + the pz-top "Vibe your life." H1 + the journey
  // rail around a page that already has its own bar, i.e. the double-chrome bug. UI_SPEC step 2.
  if (screen === "welcome") return <WelcomeScreen />;

  let content = null;
  if (screen === "sign") content = <SignScreen {...commonProps} />;
  else if (screen === "setup") content = <SetupScreen {...commonProps} />;
  else if (screen.startsWith("onboarding")) content = <OnboardingScreen screen={screen} {...commonProps} />;
  else if (screen === "great") content = <GreatScreen {...commonProps} />;
  else if (screen === "done") content = <DoneScreen />;
  else if (screen === "mp3") content = <Mp3Screen {...commonProps} />;
  else if (screen === "go-to") content = <GoToScreen {...commonProps} />;
  else if (screen === "memory") content = <MemoryScreen {...commonProps} />;
  else if (screen === "settings") content = <SettingsScreen {...commonProps} />;
  else content = <MainScreen {...commonProps} />;

  return (
    <AppShell screen={screen} profile={profile} session={auth.session} engineState={engineState}>
      {content}
    </AppShell>
  );
}
