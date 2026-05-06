"use client";

import { useEffect, useRef, useState, DragEvent } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Button, Card, Empty, Section } from "@/components/crm/ui";
import { crmFetch } from "@/lib/crm/userContext";

export default function FolderPage() {
  const params = useParams<{ folder: string }>();
  const folder = decodeURIComponent(params.folder);
  const [files, setFiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    const r = await crmFetch(`/api/crm/files?folder=${encodeURIComponent(folder)}`);
    const j = await r.json();
    setFiles(j.files || []);
    setLoading(false);
  }
  useEffect(() => { load(); }, [folder]);

  async function uploadFiles(list: File[]) {
    if (list.length === 0) return;
    setUploading(true);
    setError("");
    const fd = new FormData();
    fd.append("folder", folder);
    list.forEach((f) => fd.append("files", f));
    const r = await crmFetch("/api/crm/files", { method: "POST", body: fd });
    setUploading(false);
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setError(j.error || "Upload failed");
      return;
    }
    load();
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    uploadFiles(Array.from(e.dataTransfer.files));
  }

  return (
    <div>
      <Section
        title={folder.replace(/-/g, " ")}
        subtitle={`${files.length} file${files.length === 1 ? "" : "s"}`}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <Link
              href="/crm/manufacturing"
              style={{
                padding: "10px 16px",
                background: "transparent",
                color: "var(--text-on-dark)",
                border: "1px solid var(--dark-border)",
                borderRadius: 10,
                textDecoration: "none",
                fontSize: 14,
              }}
            >
              All folders
            </Link>
            <Button onClick={() => inputRef.current?.click()}>+ Upload</Button>
          </div>
        }
      />

      <input
        ref={inputRef}
        type="file"
        multiple
        style={{ display: "none" }}
        onChange={(e) => uploadFiles(Array.from(e.target.files || []))}
      />

      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        style={{
          border: "1px dashed var(--dark-border)",
          borderRadius: 14,
          padding: 28,
          textAlign: "center",
          marginBottom: 24,
          background: "var(--dark-elevated)",
        }}
      >
        <p style={{ color: "var(--text-on-dark-muted)" }}>
          Drop files here, or use the upload button. Anything goes: STEP, STL, PDF, images, ZIPs.
        </p>
        {uploading && <p style={{ marginTop: 8, color: "var(--gold)" }}>Uploading.</p>}
        {error && <p style={{ marginTop: 8, color: "#ff8a8a" }}>{error}</p>}
      </div>

      {loading ? (
        <Empty title="Loading files." />
      ) : files.length === 0 ? (
        <Empty title="This folder is empty." hint="Drop files above to add them." />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
          {files.map((f) => (
            <Link
              key={f.id}
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
                {f.uploader?.name || "?"}{" "}
                {f.size_bytes ? `· ${(f.size_bytes / 1024 / 1024).toFixed(1)} MB` : ""}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
