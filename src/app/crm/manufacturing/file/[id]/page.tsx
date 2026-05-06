"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Button, Card, Empty, Input, Label, Section, Textarea } from "@/components/crm/ui";
import { crmFetch } from "@/lib/crm/userContext";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";

function publicUrl(path: string) {
  return `${SUPABASE_URL.replace(/\/$/, "")}/storage/v1/object/public/crm-files/${path}`;
}

export default function FileDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [file, setFile] = useState<any | null>(null);
  const [comments, setComments] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [edit, setEdit] = useState(false);
  const [draft, setDraft] = useState({ description: "", vendor_id: "" });
  const [vendors, setVendors] = useState<any[]>([]);

  async function load() {
    const r = await crmFetch(`/api/crm/files/${id}`);
    if (!r.ok) return;
    const j = await r.json();
    setFile(j.file);
    setDraft({ description: j.file.description || "", vendor_id: j.file.vendor_id || "" });
    const cR = await crmFetch(`/api/crm/files/${id}/comments`);
    setComments((await cR.json()).comments || []);
  }
  useEffect(() => { load(); }, [id]);

  useEffect(() => {
    crmFetch("/api/crm/vendors").then(async (r) => {
      if (r.ok) setVendors((await r.json()).vendors || []);
    });
  }, []);

  if (!file) return <Empty title="Loading file." />;
  const url = publicUrl(file.storage_path);
  const isImage = file.mime_type?.startsWith("image/");
  const isPdf = file.mime_type === "application/pdf";

  async function postComment() {
    if (!text.trim()) return;
    await crmFetch(`/api/crm/files/${id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: text }),
    });
    setText("");
    load();
  }

  async function saveEdit() {
    await crmFetch(`/api/crm/files/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    setEdit(false);
    load();
  }

  async function remove() {
    if (!confirm("Delete this file?")) return;
    await crmFetch(`/api/crm/files/${id}`, { method: "DELETE" });
    window.location.href = `/crm/manufacturing/${file.project_folder}`;
  }

  return (
    <div>
      <p style={{ marginBottom: 6 }}>
        <Link
          href={`/crm/manufacturing/${file.project_folder}`}
          style={{ fontSize: 12, color: "var(--text-on-dark-muted)", textDecoration: "none" }}
        >
          ← {file.project_folder.replace(/-/g, " ")}
        </Link>
      </p>
      <Section
        title={file.filename}
        subtitle={`${file.uploader?.name || "?"} · ${new Date(file.created_at).toLocaleString()}`}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <a
              href={url}
              download={file.filename}
              style={{
                padding: "10px 16px",
                background: "var(--cream)",
                color: "var(--dark)",
                borderRadius: 10,
                textDecoration: "none",
                fontSize: 14,
                fontWeight: 500,
              }}
            >
              Download
            </a>
            <Button variant="secondary" onClick={() => setEdit((e) => !e)}>
              {edit ? "Cancel edit" : "Edit"}
            </Button>
            <Button variant="danger" onClick={remove}>Delete</Button>
          </div>
        }
      />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 24 }}>
        <div>
          <Card>
            {isImage ? (
              <img src={url} alt={file.filename} style={{ width: "100%", borderRadius: 8 }} />
            ) : isPdf ? (
              <iframe
                src={url}
                style={{ width: "100%", height: "70vh", border: 0, borderRadius: 8, background: "white" }}
              />
            ) : (
              <Empty title="Preview not available" hint="Use the Download button to open this file locally." />
            )}
          </Card>
        </div>
        <div>
          <Card>
            {edit ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                  <Label>Description</Label>
                  <Textarea
                    rows={4}
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  />
                </div>
                <div>
                  <Label>Vendor</Label>
                  <select
                    value={draft.vendor_id}
                    onChange={(e) => setDraft({ ...draft, vendor_id: e.target.value })}
                    style={{
                      width: "100%",
                      padding: "12px 14px",
                      background: "var(--dark-elevated)",
                      border: "1px solid var(--dark-border)",
                      borderRadius: 10,
                      color: "var(--text-on-dark)",
                      fontSize: 14,
                    }}
                  >
                    <option value="">None</option>
                    {vendors.map((v) => (
                      <option key={v.id} value={v.id}>{v.name}</option>
                    ))}
                  </select>
                </div>
                <Button onClick={saveEdit}>Save</Button>
              </div>
            ) : (
              <div>
                {file.description ? (
                  <p style={{ fontSize: 14, lineHeight: 1.6 }}>{file.description}</p>
                ) : (
                  <p style={{ color: "var(--text-on-dark-muted)", fontSize: 13 }}>
                    No description. Click Edit to add one.
                  </p>
                )}
                {file.vendor?.name && (
                  <p style={{ marginTop: 12, fontSize: 13 }}>
                    Vendor:{" "}
                    <Link href={`/crm/contacts`} style={{ color: "var(--gold)" }}>
                      {file.vendor.name}
                    </Link>
                  </p>
                )}
              </div>
            )}
          </Card>

          <Card style={{ marginTop: 16 }}>
            <h3
              style={{
                fontSize: 11,
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                color: "var(--text-on-dark-muted)",
                marginBottom: 10,
              }}
            >
              Comments
            </h3>
            {comments.length === 0 ? (
              <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)" }}>None yet.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {comments.map((c) => (
                  <div key={c.id}>
                    <div style={{ fontSize: 12, color: "var(--text-on-dark-muted)" }}>
                      {c.author?.name || "?"} · {new Date(c.created_at).toLocaleString()}
                    </div>
                    <p style={{ fontSize: 14, marginTop: 2 }}>{c.body}</p>
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: 12 }}>
              <Textarea
                rows={2}
                placeholder="Add a comment."
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <div style={{ marginTop: 6, display: "flex", justifyContent: "flex-end" }}>
                <Button onClick={postComment} disabled={!text.trim()}>Post</Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
