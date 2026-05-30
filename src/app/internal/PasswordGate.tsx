"use client";

import { useState, useEffect } from "react";

/**
 * Posts the passcode to /api/internal-gate, which compares it server-side
 * and sets a signed httpOnly cookie. In NODE_ENV=development the expected
 * code is the literal "123". In production GATE_PASSCODE_INTERNAL must be
 * set on the host (Vercel env) - the route fails secure with 401 if it is
 * missing or too short (< 6 chars).
 *
 * B064: cookie name and field name (`passcode`) must stay in sync with
 * the route and with src/middleware.ts which gates /internal/* server-side.
 */
export default function PasswordGate({ children }: { children: React.ReactNode }) {
  const [unlocked, setUnlocked] = useState(false);
  const [checked, setChecked] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetch("/api/internal-gate")
      .then((r) => r.json())
      .then((d) => {
        if (d?.unlocked) setUnlocked(true);
      })
      .catch(() => {})
      .finally(() => setChecked(true));
  }, []);

  if (unlocked) return <>{children}</>;

  // Hide the form briefly while we check the cookie to avoid a flash
  // of the prompt on refresh.
  if (!checked) {
    return (
      <div style={{ background: "#0C0C0C", minHeight: "100vh" }} />
    );
  }

  return (
    <div style={{ background: "#0C0C0C", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center", maxWidth: 360, padding: 40 }}>
        <h1 style={{ fontFamily: "Georgia, serif", fontSize: 28, color: "#C8A97E", marginBottom: 8 }}>ANTICIPY</h1>
        <p style={{ color: "#8A8A8A", fontSize: 14, marginBottom: 32 }}>Internal — Enter access code</p>
        <form onSubmit={async (e) => {
          e.preventDefault();
          if (submitting) return;
          setSubmitting(true);
          setError(false);
          try {
            const cleaned = input.replace(/\s+/g, "");
            const res = await fetch("/api/internal-gate", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ passcode: cleaned }),
            });
            if (res.ok) {
              setUnlocked(true);
            } else {
              setError(true);
              setInput("");
            }
          } catch {
            setError(true);
          } finally {
            setSubmitting(false);
          }
        }}>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            value={input}
            onChange={(e) => { setInput(e.target.value); setError(false); }}
            placeholder="Access code (123)"
            autoFocus
            disabled={submitting}
            style={{
              background: "#1A1A1A", border: error ? "1px solid #ff4444" : "1px solid #333",
              borderRadius: 8, padding: "12px 16px", width: "100%", color: "#F5F0EB",
              fontSize: 16, outline: "none", marginBottom: 16,
            }}
          />
          <button type="submit" disabled={submitting} style={{
            background: "#C8A97E", color: "#0C0C0C", border: "none", borderRadius: 100,
            padding: "12px 32px", fontSize: 14, fontWeight: 600, cursor: submitting ? "default" : "pointer", width: "100%",
            opacity: submitting ? 0.7 : 1,
          }}>
            {submitting ? "Checking…" : "Enter"}
          </button>
          {error && <p style={{ color: "#ff4444", fontSize: 13, marginTop: 12 }}>Wrong code</p>}
        </form>
      </div>
    </div>
  );
}
