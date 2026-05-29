"use client";

import { FormEvent, useState } from "react";

export const dynamic = "force-dynamic";

export default function AnalyticsLogin() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/analytics/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        window.location.href = "/analytics";
        return;
      }
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Wrong password.");
    } catch {
      setError("Network error.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6"
      style={{ background: "var(--dark)", color: "var(--text-on-dark)" }}
    >
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm flex flex-col gap-4"
      >
        <h1
          className="font-serif text-center mb-2"
          style={{ fontSize: "clamp(28px, 4vw, 36px)" }}
        >
          Anticipy Analytics
        </h1>
        <p
          className="text-center text-[13px] mb-4"
          style={{ color: "var(--text-on-dark-muted)" }}
        >
          Internal dashboard. Restricted access.
        </p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          autoComplete="current-password"
          autoFocus
          className="px-5 py-3.5 rounded-pill text-[15px] outline-none"
          style={{
            background: "var(--dark-elevated)",
            border: "1px solid var(--dark-border)",
            color: "var(--text-on-dark)",
          }}
        />
        {error && (
          <p className="text-[14px] text-red-400 text-center">{error}</p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="mt-2 px-8 py-3.5 rounded-pill text-[15px] font-medium transition-colors disabled:opacity-60"
          style={{
            background: "var(--text-on-dark)",
            color: "var(--dark)",
          }}
        >
          {loading ? "Checking..." : "Enter"}
        </button>
      </form>
    </div>
  );
}
