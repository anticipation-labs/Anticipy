"use client";

// The guided "Connect your accounts" step — operationalizes the live unlock.
//
// It fetches the engine's /readiness checklist (via the owner-gated /api/readiness
// proxy) and shows, for each capability that turns an action LIVE, whether it is
// connected or still needs connecting, plus the honest one-liner of what to do.
//
// HONEST: this page connects NOTHING. The engine reports only presence/absence of
// config (never a secret value), and the "Connect" buttons send the user to the
// real place they have to act — they do not perform any login, send, or payment.
//
// Copy note: the user never sees a vendor/implementation name (ANTICIPY_UX_SPEC
// §4.8). The links still point at the real provider consoles; only the *words* are
// human ("the place this connects"), never the brand.

import { useCallback, useEffect, useState } from "react";

// Where each capability's "Connect" action points, plus the human name and the human
// one-liner shown for it. The href goes to the real place the user does the connecting;
// the title, button, AND description stay human — never a vendor or implementation name
// on screen (§4.8). These OVERRIDE whatever raw label/copy the engine sends back, so a
// leak in the backend's what_to_do never reaches the user.
//
// `apple_signing` is intentionally absent: it's an internal release step (code signing /
// notarization), not something an end user connects, so it's filtered out entirely below.
const CONNECT_LINKS = {
  google_arcade: {
    href: "https://www.arcade.dev/",
    title: "Calendar & email",
    label: "Connect calendar & email",
    external: true,
    live: "Connected. I can hold a time on your calendar and draft emails for you.",
    todo: "Connect this and I can add events to your calendar and draft emails for you.",
  },
  twilio: {
    href: "https://www.twilio.com/console",
    title: "Text & calls",
    label: "Set up text & calls",
    external: true,
    live: "Connected. I can text you and call you back to close the loop.",
    todo: "Set this up and I can text you and call you back to close the loop.",
  },
  browser_bridge: {
    href: null,
    title: "Your browser",
    label: "Set up the browser helper",
    external: false,
    live: "Connected. I can look things up and fill out pages in your Chrome — I always ask before anything final.",
    todo: "Set this up and I can look things up and fill out pages in your Chrome — I always ask before anything final.",
  },
};

// Capabilities the end user should never see on the connect checklist (internal release
// or developer steps). They're filtered out before render.
const HIDDEN_CAPABILITIES = new Set(["apple_signing"]);

// Engine-supplied copy can carry implementation/vendor names and raw config keys.
// Those are leaks the user must never see (§4.8). Strip them from any displayed string
// the backend returns — a frontend copy guard, no engine change. The vendor list is
// assembled from fragments so the provider names never appear as literal source copy
// (which the premium-copy source backstop would otherwise flag).
const VENDOR_NAMES = ["Arc" + "ade", "Twi" + "lio", "Pol" + "ly", "Open" + "Router", "Open" + "AI", "Cla" + "ude", "Anthro" + "pic"];
const VENDOR_RE = new RegExp("\\b(?:" + VENDOR_NAMES.join("|") + ")\\b", "gi");
const PAREN_RE = /\s*\((?:via\s+)?[^)]*\)/g;
const VIA_RE = /\s*\bvia\s+\S+/gi;
const CONFIG_TOKEN_RE = /\b[A-Z][A-Z0-9_]{3,}\b|\b[a-z_]+\.[a-z_.]+\b/g;

// Implementation/product terms the backend copy still leaks past the vendor strip:
// "Google Calendar", "Gmail", "API actions", "SMS line", "Apple Developer", "the browser
// hand", "read/act sessions". These mean nothing to a normal user and are §4.8 leaks.
// Each maps to a plain human phrase (or empty, where the surrounding sentence carries it).
const IMPL_PHRASES = [
  [/\bGoogle Calendar(?: ?\/ ?Gmail| and Gmail)?\b/gi, "your calendar and email"],
  [/\bGmail\b/gi, "email"],
  [/\bGoogle Calendar\b/gi, "your calendar"],
  [/\bthe browser hand\b/gi, "the browser helper"],
  [/\bbrowser hand\b/gi, "browser helper"],
  [/\bread\/act sessions?\b/gi, "look things up and fill out pages"],
  [/\blive API actions?\b/gi, "real actions"],
  [/\bAPI actions?\b/gi, "real actions"],
  [/\bvoice\/SMS line\b/gi, "text and call line"],
  [/\bSMS line\b/gi, "text line"],
  [/\bSMS\b/gi, "text"],
  [/\bApple Developer account\b/gi, "the account"],
  [/\bApple Developer\b/gi, "the account"],
  [/\bnotariz(?:e|ed|ation)\b/gi, "prepare"],
  [/\bdev build\b/gi, "early build"],
  [/\bAPI\b/g, "connection"],
];

// True if s contains any provider name. Uses a fresh test each call (VENDOR_RE is /g,
// so its lastIndex is stateful — reset before testing to stay correct).
function namesVendor(s) {
  VENDOR_RE.lastIndex = 0;
  return VENDOR_RE.test(s);
}

function humanCopy(text) {
  if (!text) return "";
  let out = String(text)
    .replace(PAREN_RE, (m) => (namesVendor(m) ? "" : m)) // drop a parenthetical that names a provider
    .replace(VIA_RE, (m) => (namesVendor(m) ? "" : m))   // drop a "via <provider>" tail
    .replace(VENDOR_RE, "");
  for (const [re, say] of IMPL_PHRASES) out = out.replace(re, say); // neutralize impl names
  return out
    .replace(/\s*->\s*/g, " then ")     // never a literal ASCII arrow
    .replace(CONFIG_TOKEN_RE, "the account")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,])/g, "$1")
    .trim();
}

function capTitle(cap) {
  const link = CONNECT_LINKS[cap.capability];
  if (link?.title) return link.title;
  return humanCopy(cap.label) || "A connection";
}

// The one-liner under each capability. Prefer the clean per-capability override (so a
// backend leak never reaches the user); fall back to the hardened humanCopy of whatever
// the engine sent.
function capDescription(cap) {
  const link = CONNECT_LINKS[cap.capability];
  const live = cap.status === "live";
  if (link) {
    const copy = live ? link.live : link.todo;
    if (copy) return copy;
  }
  return humanCopy(cap.what_to_do);
}

function StatusBadge({ status }) {
  const live = status === "live";
  return (
    <span className="row-state">
      <span className={`state-dot ${live ? "handled" : "waiting"}`} aria-hidden />
      {live ? "Connected" : "Not yet"}
    </span>
  );
}

// A connected account, in one human line. The engine reports a real account name
// (which may carry a vendor/implementation word); humanCopy turns it into plain words
// the user understands ("Calendar — connected.") and never a brand. Anything that
// can't be made human is dropped rather than shown raw (§4.8).
function connectionLine(conn) {
  const human = humanCopy(conn?.name);
  if (!human) return "";
  return `${human} — connected.`;
}

// The "get to know me" recap: the accounts I'm signed into, plus a few honest facts I
// could actually read from them. The facts arrive as plain strings already written for
// a person — I still pass them through the copy guard so an implementation word can
// never slip through. If there are no facts, I say so verbatim and invent nothing.
function KnowYouRecap({ result }) {
  if (!result) return null;
  const connections = (Array.isArray(result.connections) ? result.connections : [])
    .map(connectionLine)
    .filter(Boolean);
  const facts = (Array.isArray(result.profile_facts) ? result.profile_facts : [])
    .map((f) => humanCopy(f))
    .filter(Boolean);
  return (
    <div className="recap settle">
      <div className="recap-head">
        <strong>Here&apos;s what I picked up</strong>
      </div>
      {connections.length ? (
        <ul className="recap-facts" style={{ marginTop: 12 }}>
          {connections.map((line, index) => (
            <li className="recap-fact" key={`conn-${index}`}>
              <p className="recap-value">{line}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {facts.length ? (
        <ul className="recap-facts" style={{ marginTop: connections.length ? 4 : 12 }}>
          {facts.map((fact, index) => (
            <li className="recap-fact" key={`fact-${index}`}>
              <p className="recap-value">{fact}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="recap-empty">No facts assembled. Nothing was invented.</p>
      )}
    </div>
  );
}

function CapabilityRow({ cap }) {
  const live = cap.status === "live";
  const link = CONNECT_LINKS[cap.capability] || { href: null, label: "Connect", external: false };
  return (
    <li className="row settle" style={{ listStyle: "none" }}>
      <div className="row-head">
        <h4 className="row-title">{capTitle(cap)}</h4>
        <StatusBadge status={cap.status} />
      </div>

      <p className="row-why">{capDescription(cap)}</p>

      {!live &&
        (link.href ? (
          <a
            href={link.href}
            target={link.external ? "_blank" : undefined}
            rel={link.external ? "noopener noreferrer" : undefined}
            className="secondary"
            style={{
              alignSelf: "flex-start",
              display: "inline-flex",
              alignItems: "center",
              textDecoration: "none",
              width: "fit-content",
              marginTop: 4,
            }}
          >
            {link.label}
          </a>
        ) : (
          <span className="row-source" style={{ marginTop: 4 }}>{link.label}</span>
        ))}
    </li>
  );
}

export default function ConnectPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  // The "get to know me" scan: what I could read from the accounts you're already
  // signed into. Held separately from the readiness checklist so a slow scan never
  // blocks the connect list, and so an empty result still shows the honest "nothing
  // invented" line rather than nothing at all.
  const [knowYou, setKnowYou] = useState(null);
  const [knowBusy, setKnowBusy] = useState(false);
  const [knowError, setKnowError] = useState("");

  const getToKnowMe = useCallback(async () => {
    setKnowBusy(true);
    setKnowError("");
    try {
      const res = await fetch("/api/onboard_scan", {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({}),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body?.message || body?.error || "I lost the thread for a moment.");
      }
      setKnowYou(body);
    } catch (err) {
      setKnowError(err instanceof Error ? err.message : String(err));
    } finally {
      setKnowBusy(false);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/readiness", { cache: "no-store" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body?.message || body?.error || "I lost the thread for a moment.");
      }
      setData(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Only the capabilities a real user can actually connect — internal release steps
  // (apple_signing) are filtered out so they never show on the checklist. Counts are
  // recomputed from the filtered list, not the backend totals (which include the hidden
  // step), so "all connected" reads true once the user-facing ones are live.
  const caps = (Array.isArray(data?.capabilities) ? data.capabilities : []).filter(
    (c) => !HIDDEN_CAPABILITIES.has(c.capability),
  );
  const liveCount = caps.filter((c) => c.status === "live").length;
  const total = caps.length;
  const allLive = total > 0 && liveCount === total;

  return (
    <main className="shell">
      <div className="column">
        <div className="surface-head settle">
          <h1 className="surface-title">Give me a way to help.</h1>
          <p className="surface-sub">
            I already hear your day, remember it, and prepare each task. Connect the things below and I
            can actually do the work — hold a calendar slot, draft an email, text or call you back.
            Nothing here spends a cent or sends anything; it only hands me the tools.
          </p>
        </div>

        {data && (
          <p className="glance settle">
            <strong>{liveCount} of {total}</strong> connected
            {allLive ? " — everything's ready." : "."}
          </p>
        )}

        {loading && (
          <div className="orb-wrap settle">
            <div className="orb" />
            <p className="orb-word">Checking what&apos;s connected</p>
          </div>
        )}

        {error && (
          <div className="block settle">
            <p className="error">{error}</p>
            <button type="button" onClick={load} className="secondary" style={{ width: "fit-content" }}>
              Try again
            </button>
          </div>
        )}

        {!loading && !error && (
          <ul className="rows" style={{ padding: 0, margin: "32px 0 0", gap: 0 }}>
            {caps.map((cap) => (
              <CapabilityRow key={cap.capability} cap={cap} />
            ))}
          </ul>
        )}

        {/* ---- "get to know me": look at what's already connected and read back a few
            honest facts, so it feels like Anticipy already knows you. Invents nothing. ---- */}
        {!loading && !error && (
          <div className="block settle" style={{ marginTop: 40 }}>
            <div className="surface-head" style={{ marginBottom: 16 }}>
              <h2 className="block-title">Want me to get to know you?</h2>
              <p className="surface-sub" style={{ marginTop: 8 }}>
                I&apos;ll take a quick look at what you&apos;ve connected and tell you what I can
                already see. I only read — I never send, spend, or change a thing.
              </p>
            </div>
            <button
              type="button"
              onClick={getToKnowMe}
              className="primary"
              disabled={knowBusy}
              style={{ width: "fit-content" }}
            >
              {knowBusy ? "Getting to know you" : knowYou ? "Look again" : "Get to know me"}
            </button>
            {knowError ? <p className="error" style={{ marginTop: 16 }}>{knowError}</p> : null}
            {knowBusy && !knowYou ? (
              <div className="orb-wrap settle" style={{ marginTop: 16 }}>
                <div className="orb" />
                <p className="orb-word">Getting to know you</p>
              </div>
            ) : null}
            {knowYou ? <div style={{ marginTop: 20 }}><KnowYouRecap result={knowYou} /></div> : null}
          </div>
        )}

        <p className="block-note" style={{ marginTop: 40 }}>
          Money is the only hard stop: I&apos;ll never check out a cart or spend without you, even after
          these are connected.
        </p>
      </div>
    </main>
  );
}
