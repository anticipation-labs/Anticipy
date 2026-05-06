"use client";

import { useEffect, useState } from "react";
import type { CrmUser } from "@/lib/crm/types";
import { writePickedUser } from "@/lib/crm/userContext";

export function NamePicker({ onPicked }: { onPicked: () => void }) {
  const [users, setUsers] = useState<CrmUser[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/crm/users")
      .then((r) => r.json())
      .then((j) => {
        if (!cancelled) {
          setUsers(j.users || []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function pick(u: CrmUser) {
    writePickedUser({ id: u.id, name: u.name });
    onPicked();
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
        padding: 24,
      }}
    >
      <div style={{ width: "100%", maxWidth: 460 }}>
        <h1 style={{ fontFamily: "var(--font-serif)", fontSize: 36, marginBottom: 8 }}>
          Who are you?
        </h1>
        <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14, marginBottom: 24 }}>
          Pick your name. Everything you do will be attributed to this user. Switch any time.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {loading ? (
            <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14 }}>Loading.</p>
          ) : users.length === 0 ? (
            <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14 }}>
              No users yet. Add one in Settings after you sign in as a temporary user.
            </p>
          ) : (
            users.map((u) => (
              <button
                key={u.id}
                onClick={() => pick(u)}
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
                <span style={{ fontFamily: "var(--font-serif)", fontSize: 22 }}>
                  {u.name}
                </span>
                {u.email && (
                  <span
                    style={{
                      display: "block",
                      color: "var(--text-on-dark-muted)",
                      fontSize: 13,
                      marginTop: 2,
                    }}
                  >
                    {u.email}
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
