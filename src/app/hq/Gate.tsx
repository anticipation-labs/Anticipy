"use client";

import { useState } from "react";
import { useHQ } from "./lib/store";
import Shell from "./components/Shell";
import { Avatar } from "./components/ui";

const PROTOTYPE_PASSWORD = "123";

/** Access screen: password, then "Who are you?" — then the app shell. */
export default function Gate({ children }: { children: React.ReactNode }) {
  const { unlocked, user, setUnlocked, setUser, people } = useHQ();
  const [input, setInput] = useState("");
  const [error, setError] = useState(false);

  if (unlocked && user) {
    return <Shell>{children}</Shell>;
  }

  return (
    <div
      style={{
        minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
        background: "var(--hq-surface)", padding: 16,
      }}
    >
      <div className="hq-card hq-pop-in" style={{ width: "100%", maxWidth: 360, background: "#fff", padding: "36px 32px", textAlign: "center" }}>
        <h1 className="hq-serif" style={{ fontSize: 26 }}>
          Anticipy <span style={{ color: "var(--hq-gold)" }}>HQ</span>
        </h1>
        <p style={{ color: "var(--hq-muted)", fontSize: 13, marginTop: 4, marginBottom: 28 }}>Private workspace</p>

        {!unlocked ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (input.trim() === PROTOTYPE_PASSWORD) {
                setUnlocked(true);
                setError(false);
              } else {
                setError(true);
                setInput("");
              }
            }}
          >
            <input
              type="password"
              className="hq-input"
              style={{ textAlign: "center", fontSize: 15, borderColor: error ? "var(--hq-danger)" : undefined }}
              placeholder="Password"
              value={input}
              autoFocus
              onChange={(e) => { setInput(e.target.value); setError(false); }}
              aria-label="Workspace password"
            />
            {error && (
              <p style={{ color: "var(--hq-danger)", fontSize: 12.5, marginTop: 8 }}>That is not the password.</p>
            )}
            <button type="submit" className="hq-btn hq-btn-primary" style={{ width: "100%", justifyContent: "center", marginTop: 14, padding: "9px 12px" }}>
              Continue
            </button>
          </form>
        ) : (
          <div className="hq-fade-in">
            <p style={{ fontSize: 14, fontWeight: 500, marginBottom: 14 }}>Who are you?</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {people.map((p) => (
                <button
                  key={p.id}
                  className="hq-btn"
                  style={{ justifyContent: "flex-start", padding: "10px 14px" }}
                  onClick={() => setUser(p.id)}
                >
                  <Avatar name={p.name} size={26} />
                  <span style={{ flex: 1, textAlign: "left" }}>
                    <span style={{ display: "block", fontWeight: 600 }}>{p.name}</span>
                    <span style={{ display: "block", fontSize: 11.5, color: "var(--hq-muted)", fontWeight: 400 }}>{p.role}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
