"use client";

import { useMemo, useState } from "react";
import { useHQ } from "../lib/store";
import type { Person } from "../lib/types";
import { fmtDue } from "../lib/format";
import TaskRow from "../components/TaskRow";
import TaskPanel from "../components/TaskPanel";
import { Avatar, SectionTitle, EmptyState } from "../components/ui";

export default function PeoplePage() {
  const { people, tasks, runs } = useHQ();
  const [openPerson, setOpenPerson] = useState<Person | null>(null);
  const [openTask, setOpenTask] = useState<string | null>(null);

  const stats = useMemo(() => {
    const map = new Map<string, { open: number; blocked: number; done: number; runs: number; nextDue: string | null }>();
    for (const p of people) {
      const mine = tasks.filter((t) => t.owner === p.id);
      const open = mine.filter((t) => !["done", "cancelled"].includes(t.status));
      const dues = open.filter((t) => t.due).sort((a, b) => a.due!.localeCompare(b.due!));
      map.set(p.id, {
        open: open.length,
        blocked: mine.filter((t) => t.status === "blocked").length,
        done: mine.filter((t) => t.status === "done").length,
        runs: runs.filter((r) => r.requester === p.id).length,
        nextDue: dues[0]?.due ?? null,
      });
    }
    return map;
  }, [people, tasks, runs]);

  if (openPerson) {
    const s = stats.get(openPerson.id)!;
    const mine = tasks.filter((t) => t.owner === openPerson.id);
    const open = mine.filter((t) => !["done", "cancelled"].includes(t.status));
    const done = mine.filter((t) => t.status === "done");
    return (
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "24px 20px" }}>
        <button className="hq-btn hq-btn-sm hq-no-print" onClick={() => setOpenPerson(null)}>← People</button>
        <div style={{ display: "flex", gap: 14, alignItems: "center", margin: "16px 0 4px" }}>
          <Avatar name={openPerson.name} size={44} />
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 600 }}>{openPerson.name}</h1>
            <p style={{ fontSize: 13, color: "var(--hq-muted)" }}>{openPerson.role}</p>
          </div>
        </div>
        <p style={{ fontSize: 13, color: "var(--hq-muted)", marginBottom: 18 }}>
          Owns {openPerson.owns.join(", ")} · {openPerson.calendarStatus} · Prefers {openPerson.reminderPref} reminders
        </p>

        <SectionTitle>Current focus</SectionTitle>
        <p className="hq-card" style={{ padding: "10px 14px", fontSize: 13.5, marginBottom: 20 }}>{openPerson.focus}</p>

        <SectionTitle>Open work · {open.length}</SectionTitle>
        {open.length > 0 ? (
          <div className="hq-card" style={{ marginBottom: 20 }}>
            {open.map((t) => <TaskRow key={t.id} task={t} onOpen={setOpenTask} />)}
          </div>
        ) : (
          <div style={{ marginBottom: 20 }}><EmptyState title="No open work." /></div>
        )}

        <SectionTitle>Recently completed · {done.length}</SectionTitle>
        {done.length > 0 ? (
          <div className="hq-card" style={{ marginBottom: 20 }}>
            {done.map((t) => <TaskRow key={t.id} task={t} onOpen={setOpenTask} compact />)}
          </div>
        ) : (
          <div style={{ marginBottom: 20 }}><EmptyState title="Nothing completed recently." /></div>
        )}

        <SectionTitle>Contact & preferences</SectionTitle>
        <div className="hq-card" style={{ padding: "10px 14px", fontSize: 13 }}>
          <p><span style={{ color: "var(--hq-muted)" }}>Email</span> · <span className="hq-mono">{openPerson.email}</span></p>
          <p><span style={{ color: "var(--hq-muted)" }}>SMS</span> · <span className="hq-mono">{openPerson.phone}</span></p>
          <p><span style={{ color: "var(--hq-muted)" }}>Reminders</span> · {openPerson.reminderPref}</p>
          <p><span style={{ color: "var(--hq-muted)" }}>Agent runs started</span> · {s.runs}</p>
        </div>

        {openTask && <TaskPanel taskId={openTask} onClose={() => setOpenTask(null)} />}
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "24px 20px" }}>
      <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>People</h1>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {people.map((p) => {
          const s = stats.get(p.id)!;
          return (
            <button
              key={p.id}
              className="hq-card hq-row-click"
              style={{ display: "flex", gap: 14, alignItems: "center", padding: "14px 16px", textAlign: "left", cursor: "pointer", background: "#fff" }}
              onClick={() => setOpenPerson(p)}
            >
              <Avatar name={p.name} size={38} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontWeight: 600, fontSize: 14 }}>{p.name} <span style={{ fontWeight: 400, color: "var(--hq-muted)", fontSize: 12.5 }}>· {p.role}</span></p>
                <p style={{ fontSize: 12.5, color: "var(--hq-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  Focus: {p.focus} · {p.calendarStatus}
                </p>
              </div>
              <div style={{ display: "flex", gap: 6, flexShrink: 0, alignItems: "center" }}>
                <span className="hq-badge">{s.open} open</span>
                {s.blocked > 0 && <span className="hq-badge" style={{ color: "var(--hq-danger)" }}>{s.blocked} blocked</span>}
                {s.nextDue && <span className="hq-mono" style={{ color: "var(--hq-muted)" }} data-hq-hide-sm>next {fmtDue(s.nextDue)}</span>}
              </div>
            </button>
          );
        })}
      </div>
      <p style={{ fontSize: 12, color: "var(--hq-muted)", marginTop: 14 }}>
        This is for coordination, not scoring. No rankings, no productivity metrics.
      </p>
    </div>
  );
}
