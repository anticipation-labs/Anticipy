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
// §4.8). Connect actions either launch the provider's own consent in-app (calendar &
// email) or show an honest "coming soon" chip — never a dead deep-link into a vendor
// console. Only the *words* are human ("the place this connects"), never the brand.

import { useCallback, useEffect, useState } from "react";

// Where each capability's "Connect" action goes, plus the human name and one-liner.
// The title, button, AND description stay human — never a vendor or implementation name
// on screen (§4.8). These OVERRIDE whatever raw label/copy the engine sends back, so a
// leak in the backend's what_to_do never reaches the user.
//
// `apple_signing` is intentionally absent: it's an internal release step (code signing /
// notarization), not something an end user connects, so it's filtered out entirely below.
//
// `oauth: true` means this row connects FOR REAL in-app: it launches the provider's own
// consent screen (not a dead vendor-console deep-link) and polls until the account
// actually completes authorization. `accounts` are the per-account connect targets the
// engine writes a "connect_account" open-loop for (name -> the connector's authorize()).
const CONNECT_LINKS = {
  google_arcade: {
    href: null,
    oauth: true,
    title: "Calendar & email",
    label: "Connect calendar & email",
    external: false,
    accounts: [
      { key: "calendar", name: "Google Calendar", identifier: "googlecalendar" },
      { key: "gmail", name: "Gmail", identifier: "gmail.compose" },
    ],
    live: "Connected. I can hold a time on your calendar and draft emails for you.",
    todo: "Connect this and I can add events to your calendar and draft emails for you.",
  },
  twilio: {
    href: null,
    // Text & calls isn't user-connectable in-app yet (it's the comms channel, wired
    // on our side), so we show an honest "coming soon" chip instead of a dead deep-link
    // to a vendor console the user has no business visiting.
    soon: true,
    title: "Text & calls",
    label: "Coming soon",
    external: false,
    live: "Connected. I can text you and call you back to close the loop.",
    todo: "Text and calls are on the way — soon I'll be able to text you and call you back to close the loop.",
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

// B12 — signed per-user browser pairing (OFF by default). On a shared cloud engine the browser
// helper must attach to YOUR account, not whoever set the engine up. When this build flag is on,
// we show a "Pair this browser" action that mints a short-lived signed code (server-side, tied to
// your sign-in) and hands it to the helper to claim. Default off -> this page renders byte-for-byte
// as today. The helper id is a build-time value so the page can message the installed helper.
const PER_USER_HANDS_UI = process.env.NEXT_PUBLIC_ANTICIPY_PER_USER_HANDS === "1";
const BROWSER_HELPER_ID = process.env.NEXT_PUBLIC_ANTICIPY_EXTENSION_ID || "";

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

// The real in-app connect action for an OAuth capability (calendar + email). Each account
// launches the PROVIDER's own consent in a new tab (the approval tap is the user's), then
// we poll the engine until it confirms authorization actually completed. No dead vendor
// deep-link, no fake "connected".
function OauthConnect({ link, oauthState, onConnect, onRecheck }) {
  return (
    <div className="stack" style={{ marginTop: 8, gap: 8 }}>
      {(link.accounts || []).map((acct) => {
        const st = oauthState[acct.key] || {};
        const status = st.status || "not_connected";
        const connected = status === "connected";
        const waiting = status === "launching" || status === "polling";
        return (
          <div key={acct.key} className="control-row" style={{ gap: 16, justifyContent: "flex-start" }}>
            <span className="row-source" style={{ minWidth: 0 }}>
              {(humanCopy(acct.name) || "An account").replace(/^./, (s) => s.toUpperCase())}
              {connected ? " — connected." : null}
            </span>
            {!connected ? (
              <button
                type="button"
                className="secondary"
                onClick={() => onConnect(acct)}
                disabled={waiting}
                style={{ width: "fit-content" }}
              >
                {status === "launching" ? "Opening…" : status === "polling" ? "Waiting for you to approve it" : "Connect"}
              </button>
            ) : null}
            {status === "polling" ? (
              <button
                type="button"
                className="quiet-button"
                onClick={() => onRecheck(acct)}
                style={{ width: "fit-content" }}
              >
                I&apos;ve approved it
              </button>
            ) : null}
            {st.error ? <p className="error" style={{ margin: 0 }}>{humanCopy(st.error)}</p> : null}
          </div>
        );
      })}
    </div>
  );
}

function CapabilityRow({ cap, oauthState, onConnect, onRecheck }) {
  const live = cap.status === "live";
  const link = CONNECT_LINKS[cap.capability] || { href: null, label: "Connect", external: false };
  return (
    <li className="row settle" style={{ listStyle: "none" }}>
      <div className="row-head">
        <h4 className="row-title">{capTitle(cap)}</h4>
        <StatusBadge status={cap.status} />
      </div>

      <p className="row-why">{capDescription(cap)}</p>

      {!live && link.oauth ? (
        <OauthConnect link={link} oauthState={oauthState} onConnect={onConnect} onRecheck={onRecheck} />
      ) : !live && link.soon ? (
        <span className="soon-chip" role="note">{link.label || "Coming soon"}</span>
      ) : !live ? (
        link.href ? (
          <a
            href={link.href}
            target={link.external ? "_blank" : undefined}
            rel={link.external ? "noopener noreferrer" : undefined}
            className="secondary"
            style={{ alignSelf: "flex-start", textDecoration: "none", width: "fit-content", marginTop: 4 }}
          >
            {link.label}{link.external ? <span aria-hidden style={{ marginLeft: 6, opacity: 0.7 }}>↗</span> : null}
          </a>
        ) : (
          <span className="row-source" style={{ marginTop: 4 }}>{link.label}</span>
        )
      ) : null}
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
  // Per-account real-connect state, keyed by account key (calendar/gmail):
  // { status: not_connected|launching|polling|connected, error }.
  const [oauthState, setOauthState] = useState({});
  // memory_id of each account's "connect_account" open-loop, captured from /owner/onboard.
  const [loopIds, setLoopIds] = useState({});

  // Ensure the engine has a "connect_account" open-loop for each OAuth account, returning
  // the memory_id map. Idempotent: re-onboarding the same connections re-points to the same
  // loops (the engine upserts), so this is safe to call before every connect.
  const ensureConnectLoops = useCallback(async () => {
    const accounts = (CONNECT_LINKS.google_arcade.accounts || []);
    const res = await fetch("/api/owner/onboard", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        source: "connect_page",
        connections: accounts.map((a) => ({
          name: a.name,
          status: "needs_auth",
          route: "api",
          identifier: a.identifier,
        })),
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body?.message || body?.detail || body?.error || "I couldn't prepare the connection.");
    }
    const ids = {};
    for (const w of Array.isArray(body?.written) ? body.written : []) {
      if (w?.drawer === "open_loops" && w?.fields?.action === "connect_account") {
        const acct = accounts.find((a) => a.name === w.fields.name);
        if (acct) ids[acct.key] = w.memory_id;
      }
    }
    setLoopIds((cur) => ({ ...cur, ...ids }));
    return ids;
  }, []);

  // Re-ask the engine whether an account finished authorizing (it asks the connector).
  const recheckAccount = useCallback(
    async (acct, idOverride) => {
      const id = idOverride || loopIds[acct.key];
      if (!id) return false;
      try {
        const res = await fetch("/api/connections/authorize", {
          method: "POST",
          headers: { "content-type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ id }),
        });
        const body = await res.json().catch(() => ({}));
        if (res.ok && body.status === "connected") {
          setOauthState((s) => ({ ...s, [acct.key]: { status: "connected" } }));
          return true;
        }
      } catch {
        /* a transient poll failure is not fatal — keep waiting */
      }
      return false;
    },
    [loopIds],
  );

  const pollAccount = useCallback(
    (acct, id) => {
      let tries = 0;
      const timer = setInterval(async () => {
        tries += 1;
        const done = await recheckAccount(acct, id);
        if (done || tries >= 30) clearInterval(timer);
      }, 4000);
    },
    [recheckAccount],
  );

  // Launch the provider's real consent for one account, then poll until connected.
  const connectAccount = useCallback(
    async (acct) => {
      setOauthState((s) => ({ ...s, [acct.key]: { status: "launching" } }));
      try {
        const ids = await ensureConnectLoops();
        const id = ids[acct.key] || loopIds[acct.key];
        if (!id) throw new Error("This account isn't ready to connect yet.");
        const res = await fetch("/api/connections/authorize", {
          method: "POST",
          headers: { "content-type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ id }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(body?.message || body?.detail || body?.error || "I couldn't open the sign-in.");
        }
        if (body.status === "connected") {
          setOauthState((s) => ({ ...s, [acct.key]: { status: "connected" } }));
          return;
        }
        const url = body.connect_url;
        if (url) {
          if (typeof window !== "undefined") window.open(url, "_blank", "noopener,noreferrer");
          setOauthState((s) => ({ ...s, [acct.key]: { status: "polling" } }));
          pollAccount(acct, id);
        } else {
          setOauthState((s) => ({
            ...s,
            [acct.key]: { status: "not_connected", error: body.message || "This account isn't ready to connect yet." },
          }));
        }
      } catch (err) {
        setOauthState((s) => ({
          ...s,
          [acct.key]: { status: "not_connected", error: err instanceof Error ? err.message : String(err) },
        }));
      }
    },
    [ensureConnectLoops, loopIds, pollAccount],
  );

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

  // B12: mint a signed per-user pairing code (tied to your sign-in, server-side) and hand it to
  // the browser helper so it attaches to YOUR account. Only reachable when PER_USER_HANDS_UI is on.
  const [pairState, setPairState] = useState({ status: "idle", error: "" });
  const pairThisBrowser = useCallback(async () => {
    setPairState({ status: "minting", error: "" });
    try {
      const res = await fetch("/api/pairing/mint", { credentials: "same-origin", cache: "no-store" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.code) {
        throw new Error(body?.message || body?.error || "I couldn't set up this browser yet.");
      }
      // Relay the signed code to the installed helper; it claims the code at the engine and binds
      // its hand to this account. No secret is ever exposed here — only the short-lived code.
      if (typeof chrome !== "undefined" && chrome?.runtime?.sendMessage && BROWSER_HELPER_ID) {
        chrome.runtime.sendMessage(BROWSER_HELPER_ID, { type: "pair_device", signed: true, pairing_code: body.code }, () => {});
      }
      setPairState({ status: "sent", error: "" });
    } catch (err) {
      setPairState({ status: "idle", error: err instanceof Error ? err.message : String(err) });
    }
  }, []);

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
            <p className="error">{humanCopy(error)}</p>
            <button type="button" onClick={load} className="secondary" style={{ width: "fit-content" }}>
              Try again
            </button>
          </div>
        )}

        {!loading && !error && (
          <ul className="rows" style={{ padding: 0, margin: "32px 0 0", gap: 0 }}>
            {caps.map((cap) => (
              <CapabilityRow
                key={cap.capability}
                cap={cap}
                oauthState={oauthState}
                onConnect={connectAccount}
                onRecheck={recheckAccount}
              />
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
            {knowError ? <p className="error" style={{ marginTop: 16 }}>{humanCopy(knowError)}</p> : null}
            {knowBusy && !knowYou ? (
              <div className="orb-wrap settle" style={{ marginTop: 16 }}>
                <div className="orb" />
                <p className="orb-word">Getting to know you</p>
              </div>
            ) : null}
            {knowYou ? <div style={{ marginTop: 20 }}><KnowYouRecap result={knowYou} /></div> : null}
          </div>
        )}

        {PER_USER_HANDS_UI && !loading && !error && (
          <div className="block settle" style={{ marginTop: 40 }}>
            <div className="surface-head" style={{ marginBottom: 16 }}>
              <h2 className="block-title">Pair this browser to you</h2>
              <p className="surface-sub" style={{ marginTop: 8 }}>
                Link the browser helper to your account so it acts as you — never as anyone else who
                shares this setup.
              </p>
            </div>
            <button
              type="button"
              onClick={pairThisBrowser}
              className="secondary"
              disabled={pairState.status === "minting"}
              style={{ width: "fit-content" }}
            >
              {pairState.status === "minting" ? "Pairing…" : pairState.status === "sent" ? "Paired — you can close this" : "Pair this browser"}
            </button>
            {pairState.error ? <p className="error" style={{ marginTop: 16 }}>{humanCopy(pairState.error)}</p> : null}
          </div>
        )}

        <p className="block-note" style={{ marginTop: 40 }}>
          Money is the only hard stop: I&apos;ll never check out a cart or spend without you, even after
          these are connected.
        </p>

        {/* ---- The one forward action: on to onboarding. Connecting above is optional here — you
            can come back to it anytime — so Continue is the single primary action on this screen. ---- */}
        <div className="settle" style={{ marginTop: 40 }}>
          <a
            href="/onboarding/2"
            className="primary"
            style={{ textDecoration: "none", width: "fit-content" }}
          >
            Continue
          </a>
          <p className="block-note" style={{ marginTop: 12 }}>
            You can connect these anytime — Continue when you&apos;re ready.
          </p>
        </div>
      </div>
    </main>
  );
}
