"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Empty, Section, Select } from "@/components/crm/ui";
import { crmFetch, readPickedUser } from "@/lib/crm/userContext";
import type { CrmUser, CrmVoiceMemo } from "@/lib/crm/types";

type MemoRow = CrmVoiceMemo & { user?: { name: string } | null };

const MAX_SECONDS = 60;
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";

export function VoiceView() {
  const me = readPickedUser();
  const [users, setUsers] = useState<CrmUser[]>([]);
  const [viewUser, setViewUser] = useState<string>(me?.id || "");
  const [memos, setMemos] = useState<MemoRow[]>([]);
  const [loading, setLoading] = useState(true);

  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [recError, setRecError] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<number | null>(null);
  const stopperRef = useRef<number | null>(null);

  useEffect(() => {
    crmFetch("/api/crm/users").then(async (r) => {
      if (r.ok) setUsers((await r.json()).users || []);
    });
  }, []);

  async function load() {
    setLoading(true);
    const qs = viewUser ? `?user_id=${viewUser}` : "";
    const r = await crmFetch(`/api/crm/voice${qs}`);
    const j = await r.json();
    setMemos(j.memos || []);
    setLoading(false);
  }
  useEffect(() => { load(); }, [viewUser]);

  const todayIso = new Date().toISOString().slice(0, 10);
  const today = memos.find((m) => m.recorded_date === todayIso && (!viewUser || m.user_id === viewUser));
  const past = memos.filter((m) => m.id !== today?.id);

  const grouped = useMemo(() => {
    const map: Record<string, MemoRow[]> = {};
    for (const m of past) {
      const key = m.recorded_date.slice(0, 7);
      map[key] ??= [];
      map[key].push(m);
    }
    return Object.entries(map).sort(([a], [b]) => b.localeCompare(a));
  }, [past]);

  async function start() {
    setRecError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: pickMime() });
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: mr.mimeType });
        await upload(blob, mr.mimeType);
      };
      mr.start();
      recorderRef.current = mr;
      setRecording(true);
      setSeconds(0);
      tickRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);
      stopperRef.current = window.setTimeout(() => {
        if (recorderRef.current?.state === "recording") {
          recorderRef.current.stop();
        }
      }, MAX_SECONDS * 1000);
    } catch (e: any) {
      setRecError(e?.message || "Could not access microphone");
    }
  }

  function stop() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setRecording(false);
    if (tickRef.current) window.clearInterval(tickRef.current);
    if (stopperRef.current) window.clearTimeout(stopperRef.current);
  }

  async function upload(blob: Blob, mime: string) {
    setUploading(true);
    const fd = new FormData();
    const ext = mime.includes("ogg") ? "ogg" : "webm";
    fd.append("audio", new File([blob], `memo.${ext}`, { type: mime }));
    const r = await crmFetch("/api/crm/voice", { method: "POST", body: fd });
    setUploading(false);
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setRecError(j.error || "Upload failed");
      return;
    }
    setSeconds(0);
    load();
  }

  function pickMime(): string {
    if (typeof MediaRecorder === "undefined") return "audio/webm";
    if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
    if (MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
    if (MediaRecorder.isTypeSupported("audio/ogg")) return "audio/ogg";
    return "";
  }

  return (
    <div>
      <Section
        title="Voice memos"
        subtitle="One short note a day. Tap once to start, again to stop. 60 seconds max."
        right={
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Select value={viewUser} onChange={(e) => setViewUser(e.target.value)}>
              <option value="">Everyone</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </Select>
          </div>
        }
      />

      <Card style={{ marginBottom: 24 }}>
        <h3
          style={{
            fontSize: 11,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-on-dark-muted)",
            marginBottom: 14,
          }}
        >
          Today
        </h3>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {!recording ? (
            <Button onClick={start} size="lg">{uploading ? "Uploading" : "Record"}</Button>
          ) : (
            <Button onClick={stop} size="lg" variant="danger">Stop</Button>
          )}
          {recording && (
            <p style={{ fontFamily: "var(--font-serif)", fontSize: 22 }}>
              {String(Math.floor(seconds / 60)).padStart(2, "0")}:
              {String(seconds % 60).padStart(2, "0")}
            </p>
          )}
          {!recording && today && (
            <span style={{ color: "var(--text-on-dark-muted)", fontSize: 13 }}>
              You already have a memo today. Recording again creates a second one.
            </span>
          )}
        </div>
        {recError && <p style={{ color: "#ff8a8a", marginTop: 10 }}>{recError}</p>}

        {today && (
          <div style={{ marginTop: 18 }}>
            {today.transcript ? (
              <p style={{ fontSize: 15, lineHeight: 1.7 }}>{today.transcript}</p>
            ) : (
              <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14 }}>
                Transcription pending or unavailable.
              </p>
            )}
            <audio
              controls
              src={`${SUPABASE_URL.replace(/\/$/, "")}/storage/v1/object/public/crm-files/${today.audio_storage_path}`}
              style={{ marginTop: 10, width: "100%" }}
            />
          </div>
        )}
      </Card>

      {loading ? (
        <Empty title="Loading memos." />
      ) : grouped.length === 0 ? (
        <Empty title="No prior memos yet." />
      ) : (
        grouped.map(([month, list]) => (
          <Card key={month} style={{ marginBottom: 14 }}>
            <h3
              style={{
                fontSize: 11,
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                color: "var(--text-on-dark-muted)",
                marginBottom: 12,
              }}
            >
              {new Date(month + "-01").toLocaleDateString("en-CA", { year: "numeric", month: "long" })}
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {list.map((m) => (
                <details key={m.id} style={{ borderLeft: "2px solid var(--dark-border)", paddingLeft: 14 }}>
                  <summary style={{ cursor: "pointer", color: "var(--text-on-dark)" }}>
                    <span style={{ fontSize: 13, color: "var(--text-on-dark-muted)" }}>
                      {m.recorded_date}
                      {m.user?.name ? ` · ${m.user.name}` : ""}
                      {m.duration_seconds ? ` · ${Math.round(m.duration_seconds)}s` : ""}
                    </span>{" "}
                    {m.transcript && <span style={{ marginLeft: 6 }}>{m.transcript.slice(0, 80)}</span>}
                  </summary>
                  <div style={{ marginTop: 10 }}>
                    {m.transcript && <p style={{ fontSize: 14, lineHeight: 1.6 }}>{m.transcript}</p>}
                    <audio
                      controls
                      src={`${SUPABASE_URL.replace(/\/$/, "")}/storage/v1/object/public/crm-files/${m.audio_storage_path}`}
                      style={{ marginTop: 10, width: "100%" }}
                    />
                  </div>
                </details>
              ))}
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
