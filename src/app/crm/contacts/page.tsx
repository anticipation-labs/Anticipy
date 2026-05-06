"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, Empty, Input, Label, Section, Select, Textarea } from "@/components/crm/ui";
import { crmFetch } from "@/lib/crm/userContext";

const SOURCES = ["all", "gmail", "outreach", "manual", "vendor"] as const;

export default function ContactsPage() {
  const [contacts, setContacts] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [source, setSource] = useState<(typeof SOURCES)[number]>("all");
  const [showAdd, setShowAdd] = useState(false);
  const [importStatus, setImportStatus] = useState("");

  async function load() {
    const qs = new URLSearchParams();
    if (search) qs.set("q", search);
    if (source !== "all") qs.set("source", source);
    const r = await crmFetch(`/api/crm/contacts?${qs}`);
    setContacts((await r.json()).contacts || []);
  }
  useEffect(() => { load(); }, [search, source]);

  async function connectGoogle() {
    const r = await crmFetch("/api/crm/google/start");
    const j = await r.json();
    if (j.url) {
      window.open(j.url, "_blank", "noopener,noreferrer");
      setImportStatus("Opened Google. Authorize in the new tab, then click Import from Gmail.");
    } else {
      setImportStatus(j.error || "Could not start Google OAuth.");
    }
  }
  async function importGmail() {
    setImportStatus("Importing from Gmail.");
    const r = await crmFetch("/api/crm/contacts/import/gmail", { method: "POST" });
    const j = await r.json();
    if (!r.ok) {
      setImportStatus(`Gmail import: ${j.error || "failed"}`);
    } else {
      setImportStatus(`Gmail import: ${j.inserted} new, ${j.updated} updated, ${j.skipped} skipped from ${j.total} contacts.`);
      load();
    }
  }
  async function importOutreach() {
    setImportStatus("Importing from outreach.");
    const r = await crmFetch("/api/crm/contacts/import/outreach", { method: "POST" });
    const j = await r.json();
    if (!r.ok) {
      setImportStatus(`Outreach import: ${j.error || "failed"}`);
    } else {
      setImportStatus(`Outreach import: ${j.inserted} new, ${j.skipped} skipped from ${j.unique} unique recipients.`);
      load();
    }
  }

  return (
    <div>
      <Section
        title="Contacts"
        subtitle={`${contacts.length} contact${contacts.length === 1 ? "" : "s"}`}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <Input
              placeholder="Search."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: 220 }}
            />
            <Button variant="secondary" onClick={connectGoogle}>Connect Google</Button>
            <Button variant="secondary" onClick={importGmail}>Import from Gmail</Button>
            <Button variant="secondary" onClick={importOutreach}>Import from outreach</Button>
            <Button onClick={() => setShowAdd(true)}>+ New contact</Button>
          </div>
        }
      />

      {importStatus && (
        <p style={{ marginBottom: 12, color: "var(--gold)", fontSize: 13 }}>{importStatus}</p>
      )}

      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {SOURCES.map((s) => (
          <button
            key={s}
            onClick={() => setSource(s)}
            style={{
              padding: "6px 12px",
              borderRadius: 999,
              background: source === s ? "var(--cream)" : "var(--dark-elevated)",
              color: source === s ? "var(--dark)" : "var(--text-on-dark-muted)",
              border: "1px solid var(--dark-border)",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {contacts.length === 0 ? (
        <Empty title="No contacts yet." hint="Add one with the button above, or run an import." />
      ) : (
        <Card style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead style={{ color: "var(--text-on-dark-muted)" }}>
              <tr>
                <th style={th}>Name</th>
                <th style={th}>Email</th>
                <th style={th}>Phone</th>
                <th style={th}>Role</th>
                <th style={th}>Source</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((c) => (
                <tr key={c.id} style={{ borderTop: "1px solid var(--dark-border)" }}>
                  <td style={td}>{c.name}</td>
                  <td style={td}>{c.email}</td>
                  <td style={td}>{c.phone}</td>
                  <td style={td}>{c.role}</td>
                  <td style={td}><Badge>{c.source}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {showAdd && <AddContact onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); load(); }} />}
    </div>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "12px 16px",
  fontSize: 11,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  fontWeight: 500,
};
const td: React.CSSProperties = { padding: "12px 16px" };

function AddContact({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    role: "",
    source: "manual",
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    const r = await crmFetch("/api/crm/contacts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    setSaving(false);
    if (r.ok) onSaved();
  }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", justifyContent: "flex-end", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: "min(520px, 100%)", background: "var(--dark)", borderLeft: "1px solid var(--dark-border)", padding: 24, overflowY: "auto" }}>
        <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 28, marginBottom: 12 }}>New contact</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div><Label>Email</Label><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
          <div><Label>Phone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
          <div><Label>Role</Label><Input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} /></div>
          <div>
            <Label>Source</Label>
            <Select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>
              <option value="manual">manual</option>
              <option value="gmail">gmail</option>
              <option value="outreach">outreach</option>
              <option value="vendor">vendor</option>
            </Select>
          </div>
          <div><Label>Notes</Label><Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={save} disabled={saving || !form.name.trim()}>{saving ? "Saving" : "Save"}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
