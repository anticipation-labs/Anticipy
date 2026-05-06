"use client";

import { useState, FormEvent } from "react";

export function PasswordGate() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/crm/gate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.status === 204) {
        window.location.reload();
        return;
      }
      const j = await res.json().catch(() => ({}));
      setError(j.error || "Wrong password");
    } catch {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--dark)",
        color: "var(--text-on-dark)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
      }}
    >
      <form onSubmit={onSubmit} style={{ width: "100%", maxWidth: 360 }}>
        <div style={{ marginBottom: 28, display: "flex", alignItems: "center", gap: 10 }}>
          <span
            aria-hidden
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              display: "inline-block",
            }}
          />
          <span style={{ fontFamily: "var(--font-serif)", fontSize: 24 }}>Anticipy</span>
        </div>
        <h1 style={{ fontFamily: "var(--font-serif)", fontSize: 32, marginBottom: 8 }}>
          CRM
        </h1>
        <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14, marginBottom: 24 }}>
          Internal tool. Enter the password to continue.
        </p>
        <label
          style={{
            display: "block",
            fontSize: 12,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-on-dark-muted)",
            marginBottom: 8,
          }}
        >
          Password
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          autoComplete="current-password"
          style={{
            width: "100%",
            padding: "14px 16px",
            background: "var(--dark-elevated)",
            border: "1px solid var(--dark-border)",
            borderRadius: 10,
            color: "var(--text-on-dark)",
            fontSize: 16,
            outline: "none",
          }}
        />
        {error && (
          <p style={{ color: "#ff6b6b", fontSize: 13, marginTop: 10 }}>{error}</p>
        )}
        <button
          type="submit"
          disabled={loading || password.length === 0}
          style={{
            marginTop: 20,
            width: "100%",
            padding: "14px 16px",
            background: "var(--cream)",
            color: "var(--dark)",
            border: "none",
            borderRadius: 10,
            fontSize: 15,
            fontWeight: 500,
            cursor: loading ? "wait" : "pointer",
            opacity: loading || password.length === 0 ? 0.5 : 1,
          }}
        >
          {loading ? "Checking" : "Unlock"}
        </button>
      </form>
    </div>
  );
}
