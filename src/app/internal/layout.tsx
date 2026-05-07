"use client";

import { useState, useEffect } from "react";

function PasswordGate({ children }: { children: React.ReactNode }) {
  const [unlocked, setUnlocked] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && sessionStorage.getItem("anticipy_internal") === "1") {
      setUnlocked(true);
    }
  }, []);

  if (unlocked) return <>{children}</>;

  return (
    <div style={{ background: "#0C0C0C", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center", maxWidth: 360, padding: 40 }}>
        <h1 style={{ fontFamily: "Georgia, serif", fontSize: 28, color: "#C8A97E", marginBottom: 8 }}>ANTICIPY</h1>
        <p style={{ color: "#8A8A8A", fontSize: 14, marginBottom: 32 }}>Internal — Enter access code</p>
        <form onSubmit={(e) => {
          e.preventDefault();
          const cleaned = input.replace(/\s+/g, "").toLowerCase();
          if (cleaned === "123" || cleaned === "onetwothree") {
            sessionStorage.setItem("anticipy_internal", "1");
            setUnlocked(true);
          } else {
            setError(true);
            setInput("");
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
            style={{
              background: "#1A1A1A", border: error ? "1px solid #ff4444" : "1px solid #333",
              borderRadius: 8, padding: "12px 16px", width: "100%", color: "#F5F0EB",
              fontSize: 16, outline: "none", marginBottom: 16,
            }}
          />
          <button type="submit" style={{
            background: "#C8A97E", color: "#0C0C0C", border: "none", borderRadius: 100,
            padding: "12px 32px", fontSize: 14, fontWeight: 600, cursor: "pointer", width: "100%",
          }}>
            Enter
          </button>
          {error && <p style={{ color: "#ff4444", fontSize: 13, marginTop: 12 }}>Wrong code</p>}
        </form>
      </div>
    </div>
  );
}

export default function InternalLayout({ children }: { children: React.ReactNode }) {
  return <PasswordGate>{children}</PasswordGate>;
}
