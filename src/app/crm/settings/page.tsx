"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, Input, Label, Section } from "@/components/crm/ui";
import { crmFetch, useCrmSession } from "@/lib/crm/userContext";

type CrmUserRow = {
  id: string;
  name: string;
  email: string | null;
  is_admin: boolean;
  has_password: boolean;
  created_at: string;
};

export default function SettingsPage() {
  const me = useCrmSession();
  const [users, setUsers] = useState<CrmUserRow[]>([]);
  const [usersError, setUsersError] = useState("");
  const [newUser, setNewUser] = useState({
    name: "",
    email: "",
    password: "",
    is_admin: false,
  });
  const [adding, setAdding] = useState(false);
  const [tests, setTests] = useState<Record<string, { ok: boolean; message?: string }> | null>(null);
  const [testing, setTesting] = useState(false);
  const [cronInfo, setCronInfo] = useState<{ lastRun: string | null; lastSummary: string | null } | null>(null);

  const [pwForm, setPwForm] = useState({ current: "", next: "", confirm: "" });
  const [pwMsg, setPwMsg] = useState("");
  const [pwSaving, setPwSaving] = useState(false);

  async function load() {
    const r = await crmFetch("/api/crm/users");
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setUsersError(j.error || `HTTP ${r.status}`);
      return;
    }
    setUsersError("");
    setUsers(((await r.json()).users || []) as CrmUserRow[]);
    const cs = await crmFetch("/api/crm/cron-status");
    if (cs.ok) setCronInfo(await cs.json());
  }
  useEffect(() => { load(); }, []);

  async function addUser() {
    if (!newUser.name.trim()) return;
    setAdding(true);
    const r = await crmFetch("/api/crm/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newUser),
    });
    setAdding(false);
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      alert(j.error || "Failed to add user");
      return;
    }
    setNewUser({ name: "", email: "", password: "", is_admin: false });
    load();
  }

  async function resetPassword(u: CrmUserRow) {
    const next = prompt(`New password for ${u.name}? Leave blank to clear (forces them to set one on next sign-in).`);
    if (next === null) return;
    const r = await crmFetch(`/api/crm/users/${u.id}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        next.trim().length === 0 ? { clear: true } : { password: next }
      ),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      alert(j.error || "Failed to update password");
      return;
    }
    load();
  }

  async function toggleAdmin(u: CrmUserRow) {
    if (!confirm(`${u.is_admin ? "Demote" : "Promote"} ${u.name}?`)) return;
    const r = await crmFetch(`/api/crm/users/${u.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_admin: !u.is_admin }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      alert(j.error || "Failed to update");
      return;
    }
    load();
  }

  async function removeUser(u: CrmUserRow) {
    if (!confirm(`Delete ${u.name}? This cannot be undone.`)) return;
    const r = await crmFetch(`/api/crm/users/${u.id}`, { method: "DELETE" });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      alert(j.error || "Failed to delete");
      return;
    }
    load();
  }

  async function changeMyPassword(e: React.FormEvent) {
    e.preventDefault();
    setPwMsg("");
    if (pwForm.next.length < 4) {
      setPwMsg("New password must be at least 4 characters.");
      return;
    }
    if (pwForm.next !== pwForm.confirm) {
      setPwMsg("Passwords do not match.");
      return;
    }
    setPwSaving(true);
    const r = await crmFetch("/api/crm/users/me/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: pwForm.current,
        new_password: pwForm.next,
      }),
    });
    setPwSaving(false);
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setPwMsg(j.error || "Failed to change password");
      return;
    }
    setPwForm({ current: "", next: "", confirm: "" });
    setPwMsg("Password updated.");
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
        <Heading>My password</Heading>
        <form onSubmit={changeMyPassword} style={{ display: "grid", gap: 10, maxWidth: 480 }}>
          <div>
            <Label>Current password</Label>
            <Input
              type="password"
              value={pwForm.current}
              onChange={(e) => setPwForm({ ...pwForm, current: e.target.value })}
              autoComplete="current-password"
            />
          </div>
          <div>
            <Label>New password</Label>
            <Input
              type="password"
              value={pwForm.next}
              onChange={(e) => setPwForm({ ...pwForm, next: e.target.value })}
              autoComplete="new-password"
            />
          </div>
          <div>
            <Label>Confirm new password</Label>
            <Input
              type="password"
              value={pwForm.confirm}
              onChange={(e) => setPwForm({ ...pwForm, confirm: e.target.value })}
              autoComplete="new-password"
            />
          </div>
          {pwMsg && (
            <p style={{ fontSize: 13, color: pwMsg.startsWith("Password updated") ? "var(--gold)" : "#ff8a8a" }}>
              {pwMsg}
            </p>
          )}
          <div>
            <Button disabled={pwSaving || !pwForm.next}>{pwSaving ? "Saving" : "Update password"}</Button>
          </div>
        </form>
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <Heading>Users {me.is_admin ? "(admin)" : ""}</Heading>
        {usersError && (
          <p style={{ fontSize: 13, color: "#ff8a8a", marginBottom: 10 }}>{usersError}</p>
        )}
        {!me.is_admin && (
          <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)", marginBottom: 10 }}>
            Read-only view. Ask an admin to add or remove users, or to reset a password.
          </p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
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
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span>{u.name}</span>
                {u.is_admin && <Badge tone="good">admin</Badge>}
                {!u.has_password && <Badge>no password</Badge>}
                <span style={{ color: "var(--text-on-dark-muted)", fontSize: 13 }}>
                  {u.email || ""}
                </span>
              </div>
              {me.is_admin && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <Button variant="ghost" onClick={() => resetPassword(u)}>
                    Set password
                  </Button>
                  <Button variant="ghost" onClick={() => toggleAdmin(u)}>
                    {u.is_admin ? "Demote" : "Promote"}
                  </Button>
                  {u.id !== me.id && (
                    <Button variant="danger" onClick={() => removeUser(u)}>
                      Delete
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))}
          {users.length === 0 && (
            <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)" }}>No users.</p>
          )}
        </div>

        {me.is_admin && (
          <div
            style={{
              borderTop: "1px solid var(--dark-border)",
              paddingTop: 14,
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr auto auto",
              gap: 8,
              alignItems: "end",
            }}
          >
            <div>
              <Label>Name</Label>
              <Input
                placeholder="Full name"
                value={newUser.name}
                onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
              />
            </div>
            <div>
              <Label>Email</Label>
              <Input
                placeholder="optional"
                value={newUser.email}
                onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
              />
            </div>
            <div>
              <Label>Initial password</Label>
              <Input
                type="password"
                placeholder="optional"
                value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
              />
            </div>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 13,
                color: "var(--text-on-dark-muted)",
                paddingBottom: 12,
              }}
            >
              <input
                type="checkbox"
                checked={newUser.is_admin}
                onChange={(e) => setNewUser({ ...newUser, is_admin: e.target.checked })}
              />
              admin
            </label>
            <Button onClick={addUser} disabled={adding || !newUser.name.trim()}>
              {adding ? "Adding" : "+ Add user"}
            </Button>
          </div>
        )}
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
