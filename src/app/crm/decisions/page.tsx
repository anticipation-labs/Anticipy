"use client";

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge, Button, Card, Empty, Input, Label, Section, Textarea } from "@/components/crm/ui";
import { crmFetch } from "@/lib/crm/userContext";

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);

  async function load() {
    const qs = new URLSearchParams();
    if (search) qs.set("q", search);
    if (tagFilter) qs.set("tag", tagFilter);
    const r = await crmFetch(`/api/crm/decisions?${qs.toString()}`);
    setDecisions((await r.json()).decisions || []);
  }
  useEffect(() => { load(); }, [search, tagFilter]);

  const allTags = useMemo(() => {
    const s = new Set<string>();
    decisions.forEach((d) => (d.tags || []).forEach((t: string) => s.add(t)));
    return Array.from(s).sort();
  }, [decisions]);

  return (
    <div>
      <Section
        title="Decisions"
        subtitle={`${decisions.length} entries`}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <Input
              placeholder="Search decisions."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: 220 }}
            />
            <Button onClick={() => setShowAdd(true)}>+ New decision</Button>
          </div>
        }
      />

      {allTags.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 18 }}>
          <button
            onClick={() => setTagFilter(null)}
            style={chipStyle(tagFilter == null)}
          >
            all tags
          </button>
          {allTags.map((t) => (
            <button key={t} onClick={() => setTagFilter(t)} style={chipStyle(tagFilter === t)}>
              {t}
            </button>
          ))}
        </div>
      )}

      {decisions.length === 0 ? (
        <Empty title="No decisions yet." hint="Log the first one above." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {decisions.map((d) => (
            <Card key={d.id}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                <div>
                  <p
                    style={{
                      fontSize: 11,
                      letterSpacing: "0.15em",
                      textTransform: "uppercase",
                      color: "var(--text-on-dark-muted)",
                    }}
                  >
                    {d.decided_at} · {d.decided_by?.name || "?"}
                  </p>
                  <h3 style={{ fontFamily: "var(--font-serif)", fontSize: 24, marginTop: 4 }}>
                    {d.title}
                  </h3>
                </div>
                <Button variant="ghost" onClick={() => setEditing(d)}>Edit</Button>
              </div>
              {d.body && (
                <div style={{ marginTop: 10, fontSize: 15, lineHeight: 1.7 }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{d.body}</ReactMarkdown>
                </div>
              )}
              {d.tags?.length > 0 && (
                <div style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap" }}>
                  {d.tags.map((t: string) => (
                    <Badge key={t}>{t}</Badge>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {(showAdd || editing) && (
        <DecisionPanel
          existing={editing}
          onClose={() => {
            setShowAdd(false);
            setEditing(null);
          }}
          onSaved={() => {
            setShowAdd(false);
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function chipStyle(active: boolean): React.CSSProperties {
  return {
    padding: "6px 12px",
    borderRadius: 999,
    background: active ? "var(--cream)" : "var(--dark-elevated)",
    color: active ? "var(--dark)" : "var(--text-on-dark-muted)",
    border: "1px solid var(--dark-border)",
    fontSize: 12,
    cursor: "pointer",
  };
}

function DecisionPanel({
  existing,
  onClose,
  onSaved,
}: {
  existing: any | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    title: existing?.title || "",
    body: existing?.body || "",
    decided_at: existing?.decided_at || new Date().toISOString().slice(0, 10),
    tags: (existing?.tags || []).join(", "),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setSaving(true);
    setError("");
    const tags = form.tags.split(",").map((s: string) => s.trim()).filter(Boolean);
    const payload = {
      title: form.title,
      body: form.body || null,
      decided_at: form.decided_at,
      tags,
    };
    let r: Response;
    if (existing) {
      r = await crmFetch(`/api/crm/decisions/${existing.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      r = await crmFetch("/api/crm/decisions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
    setSaving(false);
    if (!r.ok) {
      setError("Save failed");
      return;
    }
    onSaved();
  }

  async function remove() {
    if (!existing || !confirm("Delete this decision?")) return;
    await crmFetch(`/api/crm/decisions/${existing.id}`, { method: "DELETE" });
    onSaved();
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        justifyContent: "flex-end",
        zIndex: 60,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(620px, 100%)",
          background: "var(--dark)",
          borderLeft: "1px solid var(--dark-border)",
          padding: 24,
          overflowY: "auto",
        }}
      >
        <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 28, marginBottom: 12 }}>
          {existing ? "Edit decision" : "New decision"}
        </h2>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <Label>Title</Label>
            <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </div>
          <div>
            <Label>Date</Label>
            <Input
              type="date"
              value={form.decided_at}
              onChange={(e) => setForm({ ...form, decided_at: e.target.value })}
            />
          </div>
          <div>
            <Label>Body (markdown)</Label>
            <Textarea
              rows={10}
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
          </div>
          <div>
            <Label>Tags (comma separated)</Label>
            <Input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
          </div>
          {error && <p style={{ color: "#ff8a8a" }}>{error}</p>}
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
            {existing ? <Button variant="danger" onClick={remove}>Delete</Button> : <span />}
            <div style={{ display: "flex", gap: 8 }}>
              <Button variant="secondary" onClick={onClose}>Cancel</Button>
              <Button onClick={save} disabled={saving || !form.title.trim()}>
                {saving ? "Saving" : "Save"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
