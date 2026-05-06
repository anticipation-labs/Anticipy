"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, Input, Label, Section } from "@/components/crm/ui";
import { crmFetch } from "@/lib/crm/userContext";

export default function SettingsPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [newUser, setNewUser] = useState({ name: "", email: "" });
  const [tests, setTests] = useState<Record<string, { ok: boolean; message?: string }> | null>(null);
  const [testing, setTesting] = useState(false);
  const [cronInfo, setCronInfo] = useState<{ lastRun: string | null; lastSummary: string | null } | null>(null);

  async function load() {
    const r = await crmFetch("/api/crm/users");
    setUsers((await r.json()).users || []);
    const cs = await crmFetch("/api/crm/cron-status");
    setCronInfo(await cs.json());
  }
  useEffect(() => { load(); }, []);

  async function addUser() {
    if (!newUser.name.trim()) return;
    await crmFetch("/api/crm/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newUser),
    });
    setNewUser({ name: "", email: "" });
    load();
  }

  async function runTests() {
    setTesting(true);
    const r = await crmFetch("/api/crm/integrations/test");
    setTests(await r.json());
    setTesting(false);
  }

  async function runDigestNow() {
    const r = await crmFetch("/api/cron/daily-digest", {
      headers: process.env.NEXT_PUBLIC_CRON_SECRET
        ? { "x-cron-secret": process.env.NEXT_PUBLIC_CRON_SECRET }
        : {},
    });
    if (!r.ok) {
      alert("Digest failed: " + (await r.text()));
    } else {
      alert("Digest sent. Check email.");
      load();
    }
  }

  return (
    <div>
      <Section title="Settings" />

      <Card style={{ marginBottom: 16 }}>
        <Heading>Users</Heading>
        <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)", marginBottom: 12 }}>
          Anyone can pick any user. This is intentional. Add as many as you like.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
          {users.map((u) => (
            <div
              key={u.id}
              style={{
                padding: "10px 14px",
                background: "var(--dark)",
                border: "1px solid var(--dark-border)",
                borderRadius: 10,
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <span>{u.name}</span>
              <span style={{ color: "var(--text-on-dark-muted)", fontSize: 13 }}>{u.email || ""}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 8 }}>
          <Input
            placeholder="Name"
            value={newUser.name}
            onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
          />
          <Input
            placeholder="Email (optional)"
            value={newUser.email}
            onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
          />
          <Button onClick={addUser} disabled={!newUser.name.trim()}>+ Add user</Button>
        </div>
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <Heading>Integrations</Heading>
        <Button variant="secondary" onClick={runTests} style={{ marginBottom: 12 }}>
          {testing ? "Testing." : "Run tests"}
        </Button>
        {tests ? (
          <table style={{ width: "100%", fontSize: 14, borderCollapse: "collapse" }}>
            <tbody>
              {Object.entries(tests).map(([name, r]) => (
                <tr key={name} style={{ borderTop: "1px solid var(--dark-border)" }}>
                  <td style={{ padding: 10, textTransform: "capitalize" }}>{name}</td>
                  <td style={{ padding: 10 }}>
                    {r.ok ? <Badge tone="good">ok</Badge> : <Badge tone="bad">fail</Badge>}
                  </td>
                  <td style={{ padding: 10, color: "var(--text-on-dark-muted)" }}>{r.message || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ color: "var(--text-on-dark-muted)", fontSize: 13 }}>
            Click Run tests to confirm Gemini, Deepgram, SendGrid, Storage and Supabase are reachable.
          </p>
        )}
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <Heading>Daily digest cron</Heading>
        {cronInfo?.lastRun ? (
          <p style={{ fontSize: 13 }}>
            Last run: {new Date(cronInfo.lastRun).toLocaleString()}.{" "}
            <span style={{ color: "var(--text-on-dark-muted)" }}>{cronInfo.lastSummary}</span>
          </p>
        ) : (
          <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)" }}>Never run.</p>
        )}
        <Button variant="secondary" onClick={runDigestNow} style={{ marginTop: 10 }}>
          Run digest now
        </Button>
      </Card>

      <Card>
        <Heading>Brand</Heading>
        <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)", marginBottom: 12 }}>
          Brand tokens live in the marketing site source (tailwind.config.ts and globals.css)
          and are imported by the CRM. There is nothing to re-extract; touching those files
          updates both surfaces.
        </p>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {[
            { name: "dark", color: "#0C0C0C" },
            { name: "elevated", color: "#161616" },
            { name: "cream", color: "#F5F0EB" },
            { name: "gold", color: "#C8A97E" },
          ].map((t) => (
            <div key={t.name} style={{ textAlign: "center" }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 10,
                  background: t.color,
                  border: "1px solid var(--dark-border)",
                }}
              />
              <p style={{ fontSize: 11, marginTop: 6, color: "var(--text-on-dark-muted)" }}>
                {t.name}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h3
      style={{
        fontSize: 11,
        letterSpacing: "0.15em",
        textTransform: "uppercase",
        color: "var(--text-on-dark-muted)",
        marginBottom: 12,
      }}
    >
      {children}
    </h3>
  );
}
