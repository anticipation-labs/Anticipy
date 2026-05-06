"use client";

import { useEffect, useState, FormEvent } from "react";

type LoginUser = {
  id: string;
  name: string;
  email: string | null;
  has_password: boolean;
};

export function PasswordGate() {
  const [users, setUsers] = useState<LoginUser[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [picked, setPicked] = useState<LoginUser | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/crm/users?for=login")
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => {
        if (cancelled) return;
        setUsers(j.users || []);
      })
      .catch((e) => {
        if (cancelled) return;
        setLoadError(String(e?.message || e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!picked) return;
    setError("");
    if (password.length < 4) {
      setError("Password must be at least 4 characters.");
      return;
    }
    if (!picked.has_password && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/crm/gate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: picked.id, password }),
      });
      if (res.ok) {
        window.location.reload();
        return;
      }
      const j = await res.json().catch(() => ({}));
      setError(j.error || "Sign in failed");
    } catch {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }

  if (users === null && !loadError) {
    return <FullScreen><Muted>Loading.</Muted></FullScreen>;
  }
  if (loadError) {
    return (
      <FullScreen>
        <Muted>Could not load users: {loadError}</Muted>
      </FullScreen>
    );
  }
  if ((users ?? []).length === 0) {
    return (
      <FullScreen>
        <Header />
        <p style={{ marginTop: 24, color: "var(--text-on-dark-muted)", fontSize: 14 }}>
          No users exist yet. Ask an admin to add you.
        </p>
      </FullScreen>
    );
  }

  if (!picked) {
    return (
      <FullScreen>
        <Header />
        <p style={{ marginTop: 12, color: "var(--text-on-dark-muted)", fontSize: 14, marginBottom: 24 }}>
          Pick your name to sign in.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {(users ?? []).map((u) => (
            <button
              key={u.id}
              onClick={() => {
                setPicked(u);
                setPassword("");
                setConfirm("");
                setError("");
              }}
              style={{
                textAlign: "left",
                padding: "16px 20px",
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
                color: "var(--text-on-dark)",
                borderRadius: 12,
                fontSize: 16,
                cursor: "pointer",
              }}
            >
              <span style={{ fontFamily: "var(--font-serif)", fontSize: 22 }}>{u.name}</span>
              <span style={{
                display: "block",
                color: "var(--text-on-dark-muted)",
                fontSize: 12,
                marginTop: 4,
              }}>
                {u.email || ""}
                {u.email ? " · " : ""}
                {u.has_password ? "password set" : "first time: pick a password"}
              </span>
            </button>
          ))}
        </div>
      </FullScreen>
    );
  }

  const firstTime = !picked.has_password;

  return (
    <FullScreen>
      <form onSubmit={onSubmit} style={{ width: "100%", maxWidth: 360 }}>
        <Header />
        <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 26, marginTop: 18 }}>
          {picked.name}
        </h2>
        <p style={{ color: "var(--text-on-dark-muted)", fontSize: 13, marginBottom: 20, marginTop: 4 }}>
          {firstTime
            ? "First time signing in. Set your password."
            : "Enter your password to continue."}
        </p>

        <Label>Password</Label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          autoComplete={firstTime ? "new-password" : "current-password"}
          style={inputStyle}
        />

        {firstTime && (
          <>
            <div style={{ height: 12 }} />
            <Label>Confirm password</Label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              style={inputStyle}
            />
          </>
        )}

        {error && <p style={{ color: "#ff8a8a", fontSize: 13, marginTop: 12 }}>{error}</p>}

        <button
          type="submit"
          disabled={loading || password.length === 0 || (firstTime && confirm.length === 0)}
          style={{
            marginTop: 18,
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
          {loading ? "Signing in" : firstTime ? "Set password and sign in" : "Sign in"}
        </button>

        <button
          type="button"
          onClick={() => {
            setPicked(null);
            setError("");
            setPassword("");
            setConfirm("");
          }}
          style={{
            marginTop: 10,
            width: "100%",
            padding: "10px 16px",
            background: "transparent",
            color: "var(--text-on-dark-muted)",
            border: "1px solid var(--dark-border)",
            borderRadius: 10,
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          Pick a different name
        </button>
      </form>
    </FullScreen>
  );
}

function FullScreen({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--dark)",
        color: "var(--text-on-dark)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div style={{ width: "100%", maxWidth: 460 }}>{children}</div>
    </div>
  );
}

function Header() {
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          aria-hidden
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: "var(--dark-elevated)",
            border: "1px solid var(--dark-border)",
          }}
        />
        <span style={{ fontFamily: "var(--font-serif)", fontSize: 22 }}>Anticipy</span>
      </div>
      <h1 style={{ fontFamily: "var(--font-serif)", fontSize: 32, marginTop: 18 }}>
        CRM
      </h1>
    </>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
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
      {children}
    </label>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14 }}>{children}</p>;
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "14px 16px",
  background: "var(--dark-elevated)",
  border: "1px solid var(--dark-border)",
  borderRadius: 10,
  color: "var(--text-on-dark)",
  fontSize: 16,
  outline: "none",
};
