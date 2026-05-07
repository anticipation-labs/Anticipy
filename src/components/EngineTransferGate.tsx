"use client";

import { useState } from "react";

export function EngineTransferGate() {
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/engine-transfer-gate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passcode }),
      });
      if (res.ok) {
        // Reload so the server component re-evaluates the cookie.
        window.location.reload();
      } else {
        setError("Wrong passcode");
        setPasscode("");
      }
    } catch {
      setError("Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6"
      style={{ background: "var(--dark)" }}
    >
      <div className="w-full max-w-[400px] text-center">
        <h1
          className="font-serif text-[32px] mb-2"
          style={{ color: "var(--gold)", letterSpacing: "-0.02em" }}
        >
          Anticipy
        </h1>
        <p
          className="text-[13px] uppercase tracking-[0.15em] mb-10"
          style={{ color: "var(--text-on-dark-muted)" }}
        >
          Engine Transfer — Restricted
        </p>

        <form onSubmit={onSubmit}>
          <input
            type="password"
            value={passcode}
            onChange={(e) => {
              setPasscode(e.target.value);
              if (error) setError("");
            }}
            placeholder="Access code"
            autoFocus
            disabled={loading}
            className="w-full px-5 py-3.5 rounded-pill text-[15px] outline-none mb-4 transition-all"
            style={{
              background: "var(--dark-elevated)",
              color: "var(--text-on-dark)",
              border: error
                ? "1px solid #c44"
                : "1px solid var(--dark-border)",
            }}
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full px-8 py-3.5 rounded-pill text-[15px] font-semibold transition-colors duration-200"
            style={{
              background: "var(--gold)",
              color: "var(--dark)",
              opacity: loading ? 0.7 : 1,
              cursor: loading ? "default" : "pointer",
            }}
          >
            {loading ? "..." : "Enter"}
          </button>
          {error && (
            <p className="text-[13px] mt-4" style={{ color: "#c44" }}>
              {error}
            </p>
          )}
        </form>

        <p
          className="text-[12px] mt-10 leading-[1.6]"
          style={{ color: "var(--text-on-dark-muted)", opacity: 0.7 }}
        >
          This page contains internal engineering documentation. If you arrived here
          by accident, you can close the tab.
        </p>
      </div>
    </div>
  );
}
