"use client";

import { useState, useEffect } from "react";

export default function DemoPage() {
  const [authenticated, setAuthenticated] = useState(false);
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");
  const [engineUrl, setEngineUrl] = useState("");

  useEffect(() => {
    // Check if already authenticated
    const stored = sessionStorage.getItem("anticipy_demo_auth");
    if (stored === "true") {
      setAuthenticated(true);
    }
    // Engine URL from env or default
    setEngineUrl(
      process.env.NEXT_PUBLIC_ENGINE_URL || "https://anticipy-engine.up.railway.app"
    );
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const expected = process.env.NEXT_PUBLIC_DEMO_PASSCODE;
    if (expected && passcode === expected) {
      sessionStorage.setItem("anticipy_demo_auth", "true");
      setAuthenticated(true);
      setError("");
    } else {
      setError("Wrong passcode");
      setPasscode("");
    }
  };

  if (!authenticated) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <h1 style={styles.title}>Anticipy</h1>
          <p style={styles.subtitle}>Enter the demo passcode to continue</p>
          {error && <div style={styles.error}>{error}</div>}
          <form onSubmit={handleSubmit}>
            <input
              type="password"
              value={passcode}
              onChange={(e) => setPasscode(e.target.value)}
              placeholder="Enter passcode"
              style={styles.input}
              autoFocus
            />
            <button type="submit" style={styles.button}>
              Continue
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.fullscreen}>
      <iframe
        src={engineUrl}
        style={styles.iframe}
        allow="clipboard-read; clipboard-write"
        title="Anticipy Demo"
      />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#0a0a0b",
    padding: 20,
  },
  card: {
    background: "#141417",
    border: "1px solid #2a2a32",
    borderRadius: 12,
    padding: 40,
    width: "100%",
    maxWidth: 400,
    textAlign: "center" as const,
  },
  title: {
    fontSize: 28,
    fontWeight: 700,
    color: "#e8e8ed",
    marginBottom: 8,
    letterSpacing: "-0.03em",
  },
  subtitle: {
    fontSize: 14,
    color: "#8e8e9a",
    marginBottom: 32,
  },
  error: {
    background: "rgba(239,68,68,0.1)",
    border: "1px solid rgba(239,68,68,0.2)",
    color: "#f87171",
    padding: "10px 14px",
    borderRadius: 8,
    fontSize: 13,
    marginBottom: 16,
  },
  input: {
    width: "100%",
    padding: "10px 14px",
    background: "#1c1c21",
    border: "1px solid #2a2a32",
    borderRadius: 8,
    color: "#e8e8ed",
    fontSize: 15,
    outline: "none",
    marginBottom: 16,
  },
  button: {
    width: "100%",
    padding: 11,
    background: "#7c6aef",
    color: "white",
    border: "none",
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 500,
    cursor: "pointer",
  },
  fullscreen: {
    position: "fixed" as const,
    top: 0,
    left: 0,
    width: "100vw",
    height: "100vh",
    background: "#0a0a0b",
  },
  iframe: {
    width: "100%",
    height: "100%",
    border: "none",
  },
};
