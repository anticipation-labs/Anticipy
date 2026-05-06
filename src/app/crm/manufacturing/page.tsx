"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button, Card, Input, Label, Section } from "@/components/crm/ui";
import { crmFetch } from "@/lib/crm/userContext";
import { DEFAULT_FOLDERS } from "@/lib/crm/types";

export default function ManufacturingPage() {
  const [folders, setFolders] = useState<string[]>([...DEFAULT_FOLDERS]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [adding, setAdding] = useState(false);
  const [newFolder, setNewFolder] = useState("");
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<any[] | null>(null);

  useEffect(() => {
    crmFetch("/api/crm/files")
      .then(async (r) => (r.ok ? await r.json() : { files: [] }))
      .then((j) => {
        const c: Record<string, number> = {};
        for (const f of j.files || []) c[f.project_folder] = (c[f.project_folder] || 0) + 1;
        setCounts(c);
        // Add any folders that exist in data but not in our default list.
        const all = new Set([...DEFAULT_FOLDERS, ...Object.keys(c)]);
        setFolders(Array.from(all));
      });
  }, []);

  async function runSearch() {
    if (!search.trim()) {
      setResults(null);
      return;
    }
    const r = await crmFetch(`/api/crm/files?q=${encodeURIComponent(search)}`);
    const j = await r.json();
    setResults(j.files || []);
  }

  function addFolder() {
    const slug = newFolder.toLowerCase().trim().replace(/[^a-z0-9-]/g, "-");
    if (!slug) return;
    if (!folders.includes(slug)) setFolders([...folders, slug]);
    setNewFolder("");
    setAdding(false);
  }

  return (
    <div>
      <Section
        title="Manufacturing"
        subtitle="Files for hardware, packaging, and supplier work."
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <Input
              placeholder="Search files."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              style={{ width: 240 }}
            />
            <Button onClick={runSearch}>Search</Button>
            <Button variant="secondary" onClick={() => setAdding(true)}>+ Folder</Button>
          </div>
        }
      />

      {adding && (
        <Card style={{ marginBottom: 16 }}>
          <Label>Folder name</Label>
          <div style={{ display: "flex", gap: 8 }}>
            <Input
              value={newFolder}
              onChange={(e) => setNewFolder(e.target.value)}
              placeholder="aurora-flex-cables"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && addFolder()}
            />
            <Button onClick={addFolder}>Add</Button>
            <Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
          </div>
        </Card>
      )}

      {results ? (
        <Section title={`Search results for "${search}"`} right={<Button variant="ghost" onClick={() => { setResults(null); setSearch(""); }}>Clear</Button>}>
          {results.length === 0 ? (
            <p style={{ color: "var(--text-on-dark-muted)" }}>No files matched.</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
              {results.map((f) => (
                <FileCard key={f.id} f={f} />
              ))}
            </div>
          )}
        </Section>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
          {folders.map((slug) => (
            <Link
              key={slug}
              href={`/crm/manufacturing/${slug}`}
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
                borderRadius: 14,
                padding: 22,
                textDecoration: "none",
                color: "var(--text-on-dark)",
              }}
            >
              <p
                style={{
                  fontSize: 11,
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                  color: "var(--text-on-dark-muted)",
                }}
              >
                Folder
              </p>
              <p style={{ fontFamily: "var(--font-serif)", fontSize: 24, marginTop: 4 }}>
                {slug.replace(/-/g, " ")}
              </p>
              <p style={{ marginTop: 12, color: "var(--text-on-dark-muted)", fontSize: 13 }}>
                {counts[slug] || 0} file{counts[slug] === 1 ? "" : "s"}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function FileCard({ f }: { f: any }) {
  return (
    <Link
      href={`/crm/manufacturing/file/${f.id}`}
      style={{
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        borderRadius: 14,
        padding: 16,
        textDecoration: "none",
        color: "var(--text-on-dark)",
        display: "block",
      }}
    >
      <p style={{ fontSize: 14, wordBreak: "break-all" }}>{f.filename}</p>
      <p style={{ marginTop: 8, color: "var(--text-on-dark-muted)", fontSize: 12 }}>
        {f.project_folder}
        {f.size_bytes ? ` · ${(f.size_bytes / 1024 / 1024).toFixed(1)} MB` : ""}
      </p>
    </Link>
  );
}
