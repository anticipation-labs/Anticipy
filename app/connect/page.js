"use client";

// The guided "Connect your accounts" step — operationalizes the live unlock.
//
// It fetches the engine's /readiness checklist (via the owner-gated /api/readiness
// proxy) and shows, for each capability that turns an owner action LIVE, whether it
// is connected or still needs connecting, plus the honest one-liner of what to do.
//
// HONEST: this page connects NOTHING. The engine reports only presence/absence of
// config (never a secret value), and the "Connect" buttons send the owner to the
// real place they have to act (Arcade, Twilio, Apple, the bridge install) — they do
// not perform any login, send, or payment.

import { useCallback, useEffect, useState } from "react";

// Where each capability's "Connect" action points. External links open the place
// the owner actually does the connecting; the rest are honest references.
const CONNECT_LINKS = {
  google_arcade: { href: "https://www.arcade.dev/", label: "Open Arcade", external: true },
  twilio: { href: "https://www.twilio.com/console", label: "Open Twilio", external: true },
  browser_bridge: { href: null, label: "Set up the browser bridge", external: false },
  apple_signing: {
    href: "https://developer.apple.com/account/",
    label: "Open Apple Developer",
    external: true,
  },
};

function StatusBadge({ status }) {
  const live = status === "live";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 12px",
        borderRadius: 99,
        fontSize: 13,
        fontWeight: 600,
        letterSpacing: 0.2,
        whiteSpace: "nowrap",
        color: live ? "var(--ready)" : "var(--ask)",
        background: live ? "rgba(23,107,77,0.10)" : "rgba(138,90,0,0.10)",
        border: `1px solid ${live ? "rgba(23,107,77,0.30)" : "rgba(138,90,0,0.30)"}`,
      }}
    >
      <span
        aria-hidden
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: live ? "var(--ready)" : "var(--ask)",
        }}
      />
      {live ? "Connected" : "Needs connecting"}
    </span>
  );
}

function CapabilityRow({ cap }) {
  const live = cap.status === "live";
  const link = CONNECT_LINKS[cap.capability] || { href: null, label: "Connect", external: false };
  return (
    <li
      style={{
        listStyle: "none",
        border: "1px solid var(--line)",
        borderRadius: 14,
        background: "var(--panel)",
        padding: "18px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ fontSize: 17, fontWeight: 600, color: "var(--ink)" }}>
          {cap.label || cap.capability}
        </div>
        <StatusBadge status={cap.status} />
      </div>

      <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: "var(--muted)" }}>
        {cap.what_to_do}
      </p>

      {!live &&
        (link.href ? (
          <a
            href={link.href}
            target={link.external ? "_blank" : undefined}
            rel={link.external ? "noopener noreferrer" : undefined}
            style={{
              alignSelf: "flex-start",
              display: "inline-block",
              padding: "10px 18px",
              borderRadius: 10,
              fontSize: 14,
              fontWeight: 600,
              textDecoration: "none",
              color: "var(--panel)",
              background: "var(--done)",
              border: "1px solid var(--done)",
            }}
          >
            {link.label} →
          </a>
        ) : (
          <span
            style={{
              alignSelf: "flex-start",
              padding: "10px 18px",
              borderRadius: 10,
              fontSize: 14,
              fontWeight: 600,
              color: "var(--muted)",
              background: "var(--panel-2)",
              border: "1px solid var(--line)",
            }}
          >
            {link.label}
          </span>
        ))}
    </li>
  );
}

export default function ConnectPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/readiness", { cache: "no-store" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body?.message || body?.error || `Engine returned ${res.status}`);
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

  const caps = Array.isArray(data?.capabilities) ? data.capabilities : [];
  const liveCount = data?.live_count ?? caps.filter((c) => c.status === "live").length;
  const total = data?.total ?? caps.length;

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        color: "var(--ink)",
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        padding: "56px 20px",
      }}
    >
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <div style={{ fontSize: 13, letterSpacing: 2, textTransform: "uppercase", color: "var(--muted)" }}>
          Anticipy
        </div>
        <h1 style={{ fontSize: 36, fontWeight: 700, margin: "10px 0 8px", lineHeight: 1.15 }}>
          Connect your accounts
        </h1>
        <p style={{ fontSize: 16, lineHeight: 1.55, color: "var(--muted)", margin: "0 0 8px" }}>
          Anticipy already hears your day, remembers it, and prepares each task. Connect the
          accounts below to let it actually do the work — make a calendar event, draft an email,
          drive your browser, text and call you back. Nothing here spends a cent or sends
          anything; it only unlocks the hands.
        </p>

        {data && (
          <div style={{ fontSize: 14, color: "var(--muted)", margin: "0 0 24px" }}>
            <strong style={{ color: "var(--ink)" }}>
              {liveCount} of {total}
            </strong>{" "}
            connected
            {data.overall === "all_live" ? " — everything is live." : "."}
          </div>
        )}

        {loading && (
          <div style={{ padding: "24px 0", color: "var(--muted)" }}>Checking what is connected…</div>
        )}

        {error && (
          <div
            style={{
              padding: "16px 18px",
              borderRadius: 12,
              background: "rgba(157,52,48,0.08)",
              border: "1px solid rgba(157,52,48,0.30)",
              color: "var(--blocked)",
              fontSize: 14,
              lineHeight: 1.5,
              marginBottom: 16,
            }}
          >
            <strong>Could not load the checklist.</strong> {error}
            <div style={{ marginTop: 10 }}>
              <button
                type="button"
                onClick={load}
                style={{
                  padding: "8px 16px",
                  borderRadius: 8,
                  border: "1px solid var(--line)",
                  background: "var(--panel)",
                  color: "var(--ink)",
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {!loading && !error && (
          <ul style={{ display: "flex", flexDirection: "column", gap: 14, padding: 0, margin: 0 }}>
            {caps.map((cap) => (
              <CapabilityRow key={cap.capability} cap={cap} />
            ))}
          </ul>
        )}

        <p style={{ fontSize: 13, lineHeight: 1.5, color: "var(--muted)", margin: "28px 0 0" }}>
          Money is the only hard stop: Anticipy will never check out a cart or spend without you,
          even after these are connected.
        </p>
      </div>
    </main>
  );
}
