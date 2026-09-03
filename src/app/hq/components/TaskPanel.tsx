"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useHQ } from "../lib/store";
import type { PersonId, Priority, Project, Task, TaskStatus } from "../lib/types";
import {
  fmtAgo, fmtDay, fmtTime, PRIORITIES, PRIORITY_LABEL, STATUS_LABEL, TASK_STATUSES,
} from "../lib/format";
import { AgentStatusBadge, Avatar, Check, SavedDot, useSaved } from "./ui";
import AgentLaunch from "./AgentLaunch";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 30 }}>
      <span style={{ width: 90, fontSize: 12, color: "var(--hq-muted)", flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
    </div>
  );
}

export default function TaskPanel({
  taskId,
  onClose,
}: {
  taskId: string;
  onClose: () => void;
}) {
  const { tasks, runs, events, people, user, updateTask, logActivity, addEvent } = useHQ();
  const task = tasks.find((t) => t.id === taskId);
  const [saved, flashSaved] = useSaved();
  const [showAgent, setShowAgent] = useState(false);
  const [showReminder, setShowReminder] = useState(false);
  const [comment, setComment] = useState("");
  const [newCheck, setNewCheck] = useState("");
  const [reminderChannel, setReminderChannel] = useState<"In-app" | "Email" | "SMS" | "Email + SMS">("SMS");
  const [reminderWhen, setReminderWhen] = useState("1 hour before deadline");
  const [reminderRepeat, setReminderRepeat] = useState(false);
  const [reminderEscalate, setReminderEscalate] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!task) return null;

  const patch = (p: Partial<Task>, log?: string) => {
    updateTask(task.id, p);
    if (log) logActivity(task.id, log);
    flashSaved();
  };

  const run = runs.find((r) => r.id === task.agentRunId);
  const linkedEvent = events.find((e) => task.scheduledAt && e.title.includes(task.title.slice(0, 24)));
  const owner = people.find((p) => p.id === task.owner);
  const me = people.find((p) => p.id === user) ?? people[0];
  const deps = task.dependsOn.map((id) => tasks.find((t) => t.id === id)).filter(Boolean) as Task[];

  const scheduleOnCalendar = () => {
    const start = task.due ? new Date(task.due) : new Date(Date.now() + 3600000);
    const startIso = start.toISOString();
    const end = new Date(start.getTime() + 3600000).toISOString();
    patch({ scheduledAt: startIso }, "Scheduled on calendar");
    addEvent({
      id: `ev-${Date.now()}`,
      title: `Focus — ${task.title.slice(0, 40)}`,
      start: startIso,
      end,
      kind: "focus",
      attendees: task.owner ? [task.owner] : undefined,
      source: "hq",
    });
  };

  const smsPreview = `Anticipy HQ: “${task.title.slice(0, 60)}” is due ${task.due ? `${fmtDay(task.due)} ${fmtTime(task.due)}` : "soon"}. Reply DONE to complete.`;

  return (
    <>
      <div
        className="hq-fade-in hq-no-print"
        style={{ position: "fixed", inset: 0, zIndex: 45, background: "rgba(17,17,17,0.12)" }}
        onMouseDown={onClose}
        aria-hidden
      />
      <aside
        className="hq-slide-in"
        data-hq-panel
        role="dialog"
        aria-label="Task details"
        style={{
          position: "fixed", top: 0, right: 0, bottom: 0, width: 520, maxWidth: "100vw",
          zIndex: 46, background: "#fff", borderLeft: "1px solid var(--hq-border)",
          overflowY: "auto", padding: "16px 20px 40px",
        }}
      >
        {/* Header actions */}
        <div className="hq-no-print" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <button className="hq-btn hq-btn-sm" onClick={onClose} aria-label="Close panel">✕</button>
          <SavedDot visible={saved} />
          <div style={{ flex: 1 }} />
          <button className="hq-btn hq-btn-sm" onClick={() => window.print()}>Print / export</button>
        </div>

        {/* Title */}
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start", marginBottom: 6 }}>
          <div style={{ paddingTop: 6 }}>
            <Check
              checked={task.status === "done"}
              onToggle={() => patch({ status: task.status === "done" ? "open" : "done" }, task.status === "done" ? "Reopened" : "Marked complete")}
              label="Mark complete"
            />
          </div>
          <textarea
            className="hq-input"
            style={{ border: "none", padding: 0, fontSize: 18, fontWeight: 600, resize: "none", lineHeight: 1.35 }}
            rows={2}
            value={task.title}
            onChange={(e) => patch({ title: e.target.value })}
            aria-label="Task title"
          />
        </div>

        <input
          className="hq-input"
          style={{ border: "none", padding: 0, fontSize: 13, color: "var(--hq-muted)", marginBottom: 14 }}
          placeholder="One sentence: what does done look like?"
          value={task.outcome}
          onChange={(e) => patch({ outcome: e.target.value })}
          aria-label="Desired outcome"
        />

        {/* Primary actions */}
        <div className="hq-no-print" style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
          <button
            className="hq-btn hq-btn-primary hq-btn-sm"
            onClick={() => patch({ status: task.status === "done" ? "open" : "done" }, task.status === "done" ? "Reopened" : "Marked complete")}
          >
            {task.status === "done" ? "Reopen" : "Mark complete"}
          </button>
          <button className="hq-btn hq-btn-sm" onClick={() => setShowAgent(true)}>Run with agent</button>
          <button className="hq-btn hq-btn-sm" onClick={() => setShowReminder((v) => !v)}>Add reminder</button>
          <button className="hq-btn hq-btn-sm" onClick={scheduleOnCalendar}>Schedule</button>
        </div>

        {/* Reminder editor with preview */}
        {showReminder && (
          <div className="hq-card hq-pop-in" style={{ padding: 12, marginBottom: 16 }}>
            <p className="hq-label">Reminder</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <select className="hq-input" value={reminderChannel} onChange={(e) => setReminderChannel(e.target.value as typeof reminderChannel)}>
                {["In-app", "Email", "SMS", "Email + SMS"].map((c) => <option key={c}>{c}</option>)}
              </select>
              <select className="hq-input" value={reminderWhen} onChange={(e) => setReminderWhen(e.target.value)}>
                {["1 hour before deadline", "Tomorrow 9:00", "At a specific time", "1 day before deadline"].map((w) => <option key={w}>{w}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 12.5 }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
                <input type="checkbox" checked={reminderRepeat} onChange={() => setReminderRepeat((v) => !v)} style={{ accentColor: "var(--hq-bronze)" }} />
                Repeat until done
              </label>
              <label style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
                <input type="checkbox" checked={reminderEscalate} onChange={() => setReminderEscalate((v) => !v)} style={{ accentColor: "var(--hq-bronze)" }} />
                Escalate if ignored
              </label>
            </div>
            {(reminderChannel === "SMS" || reminderChannel === "Email + SMS") && (
              <div style={{ marginTop: 10 }}>
                <p className="hq-label">SMS preview</p>
                <p className="hq-mono hq-card" style={{ padding: "8px 10px", background: "var(--hq-surface)", color: "var(--hq-text)" }}>{smsPreview}</p>
              </div>
            )}
            {(reminderChannel === "Email" || reminderChannel === "Email + SMS") && (
              <div style={{ marginTop: 10 }}>
                <p className="hq-label">Email preview</p>
                <div className="hq-card" style={{ padding: "8px 10px", background: "var(--hq-surface)", fontSize: 12.5 }}>
                  <p className="hq-mono" style={{ color: "var(--hq-muted)" }}>To: {owner?.email ?? me.email} · Subject: Reminder — {task.title.slice(0, 40)}</p>
                  <p style={{ marginTop: 4 }}>Due {task.due ? `${fmtDay(task.due)} at ${fmtTime(task.due)}` : "soon"}. Open Anticipy HQ to complete or reschedule.</p>
                </div>
              </div>
            )}
            <p style={{ fontSize: 11.5, color: "var(--hq-muted)", marginTop: 8 }}>
              Internal reminders send automatically. External email requires approval in this version.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
              <button className="hq-btn hq-btn-sm" onClick={() => setShowReminder(false)}>Cancel</button>
              <button
                className="hq-btn hq-btn-primary hq-btn-sm"
                onClick={() => {
                  patch(
                    { reminder: { channel: reminderChannel, when: reminderWhen, repeat: reminderRepeat, escalate: reminderEscalate } },
                    `Reminder set — ${reminderChannel}, ${reminderWhen.toLowerCase()}`
                  );
                  setShowReminder(false);
                }}
              >
                Save reminder
              </button>
            </div>
          </div>
        )}

        {/* Properties */}
        <div style={{ display: "flex", flexDirection: "column", gap: 2, borderTop: "1px solid var(--hq-border)", borderBottom: "1px solid var(--hq-border)", padding: "10px 0", marginBottom: 16 }}>
          <Field label="Owner">
            <select className="hq-input" value={task.owner ?? ""} onChange={(e) => {
              const v = (e.target.value || null) as PersonId | null;
              patch({ owner: v }, v ? `Assigned to ${v[0].toUpperCase()}${v.slice(1)}` : "Unassigned");
            }}>
              <option value="">Unassigned</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Team">
            <span style={{ fontSize: 13 }}>Anticipy core</span>
          </Field>
          <Field label="Project">
            <select className="hq-input" value={task.project} onChange={(e) => patch({ project: e.target.value as Project })}>
              {["Hardware", "Software", "Growth", "Company", "Fundraise"].map((p) => <option key={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Status">
            <select className="hq-input" value={task.status} onChange={(e) => patch({ status: e.target.value as TaskStatus }, `Status → ${STATUS_LABEL[e.target.value as TaskStatus]}`)}>
              {TASK_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </select>
          </Field>
          <Field label="Priority">
            <select className="hq-input" value={task.priority} onChange={(e) => patch({ priority: e.target.value as Priority })}>
              {PRIORITIES.map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
            </select>
          </Field>
          <Field label="Due">
            <input
              type="datetime-local"
              className="hq-input hq-mono"
              value={task.due ? task.due.slice(0, 16) : ""}
              onChange={(e) => patch({ due: e.target.value ? new Date(e.target.value).toISOString() : null })}
            />
          </Field>
          <Field label="Recurrence">
            <select className="hq-input" value={task.recurrence} onChange={(e) => patch({ recurrence: e.target.value as Task["recurrence"] })}>
              {["none", "daily", "weekly", "monthly"].map((r) => <option key={r} value={r}>{r === "none" ? "Does not repeat" : r[0].toUpperCase() + r.slice(1)}</option>)}
            </select>
          </Field>
          {task.reminder && (
            <Field label="Reminder">
              <span className="hq-badge">{task.reminder.channel} · {task.reminder.when}{task.reminder.escalate ? " · escalates" : ""}</span>
            </Field>
          )}
        </div>

        {/* Notes */}
        <p className="hq-label">Description & notes</p>
        <textarea
          className="hq-input"
          rows={3}
          style={{ marginBottom: 16 }}
          placeholder="Notes…"
          value={task.notes}
          onChange={(e) => patch({ notes: e.target.value })}
        />

        {/* Checklist */}
        <p className="hq-label">Checklist</p>
        <div style={{ marginBottom: 4 }}>
          {task.checklist.map((c) => (
            <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
              <Check
                checked={c.done}
                onToggle={() => patch({ checklist: task.checklist.map((x) => (x.id === c.id ? { ...x, done: !x.done } : x)) })}
                label={c.text}
              />
              <span style={{ fontSize: 13, color: c.done ? "var(--hq-muted)" : "var(--hq-text)", textDecoration: c.done ? "line-through" : "none" }}>
                {c.text}
              </span>
            </div>
          ))}
        </div>
        <form
          className="hq-no-print"
          style={{ display: "flex", gap: 6, marginBottom: 16 }}
          onSubmit={(e) => {
            e.preventDefault();
            if (!newCheck.trim()) return;
            patch({ checklist: [...task.checklist, { id: `c-${Date.now()}`, text: newCheck.trim(), done: false }] });
            setNewCheck("");
          }}
        >
          <input className="hq-input" placeholder="Add checklist item…" value={newCheck} onChange={(e) => setNewCheck(e.target.value)} />
          <button className="hq-btn" type="submit" disabled={!newCheck.trim()}>Add</button>
        </form>

        {/* Dependencies */}
        {deps.length > 0 && (
          <>
            <p className="hq-label">Depends on</p>
            <div style={{ marginBottom: 16 }}>
              {deps.map((d) => (
                <p key={d.id} style={{ fontSize: 13, padding: "3px 0", color: d.status === "done" ? "var(--hq-muted)" : "var(--hq-text)" }}>
                  {d.status === "done" ? "✓ " : "○ "}{d.title}
                </p>
              ))}
            </div>
          </>
        )}

        {/* Files & links */}
        {task.links.length > 0 && (
          <>
            <p className="hq-label">Files & links</p>
            <div style={{ marginBottom: 16 }}>
              {task.links.map((l) => (
                <a key={l.label} href={l.href} style={{ display: "block", fontSize: 13, color: "var(--hq-bronze)", padding: "2px 0" }}>
                  {l.label} ↗
                </a>
              ))}
            </div>
          </>
        )}

        {/* Connected calendar event */}
        {(task.scheduledAt || linkedEvent) && (
          <>
            <p className="hq-label">Calendar</p>
            <p style={{ fontSize: 13, marginBottom: 16 }}>
              Scheduled {task.scheduledAt ? `${fmtDay(task.scheduledAt)} at ${fmtTime(task.scheduledAt)}` : ""}
              {" "}<Link href="/hq/calendar" style={{ color: "var(--hq-bronze)" }}>Open calendar</Link>
            </p>
          </>
        )}

        {/* Connected agent run */}
        {run && (
          <>
            <p className="hq-label">Agent run</p>
            <Link href={`/hq/agents/${run.id}`} className="hq-card" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", marginBottom: 16, textDecoration: "none", color: "inherit" }}>
              <span style={{ fontSize: 13, fontWeight: 500, flex: 1 }}>{run.agent}</span>
              <AgentStatusBadge status={run.status} />
              <span className="hq-mono" style={{ color: "var(--hq-muted)" }}>${run.costUsd.toFixed(2)}</span>
            </Link>
          </>
        )}

        {/* Proof */}
        {task.proof && (
          <>
            <p className="hq-label">Completion proof</p>
            <p className="hq-card" style={{ fontSize: 13, padding: "8px 12px", marginBottom: 16, background: "var(--hq-surface)" }}>{task.proof}</p>
          </>
        )}

        {/* Comments */}
        <p className="hq-label">Comments</p>
        <div style={{ marginBottom: 8 }}>
          {task.comments.map((c) => {
            const author = people.find((p) => p.id === c.author);
            return (
              <div key={c.id} style={{ display: "flex", gap: 8, padding: "6px 0" }}>
                <Avatar name={author?.name ?? "?"} size={22} />
                <div>
                  <p style={{ fontSize: 12, color: "var(--hq-muted)" }}>
                    <strong style={{ color: "var(--hq-text)" }}>{author?.name}</strong> · {fmtAgo(c.at)}
                  </p>
                  <p style={{ fontSize: 13 }}>{c.text}</p>
                </div>
              </div>
            );
          })}
          {task.comments.length === 0 && <p style={{ fontSize: 12.5, color: "var(--hq-muted)" }}>No comments yet.</p>}
        </div>
        <form
          className="hq-no-print"
          style={{ display: "flex", gap: 6, marginBottom: 18 }}
          onSubmit={(e) => {
            e.preventDefault();
            if (!comment.trim()) return;
            patch({
              comments: [...task.comments, { id: `cm-${Date.now()}`, author: me.id, text: comment.trim(), at: new Date().toISOString() }],
            }, "Commented");
            setComment("");
          }}
        >
          <input className="hq-input" placeholder="Comment…" value={comment} onChange={(e) => setComment(e.target.value)} />
          <button className="hq-btn" type="submit" disabled={!comment.trim()}>Send</button>
        </form>

        {/* Activity */}
        <p className="hq-label">Activity</p>
        <div>
          {[...task.activity].reverse().map((a) => (
            <p key={a.id} className="hq-mono" style={{ color: "var(--hq-muted)", padding: "2px 0" }}>
              {fmtAgo(a.at)} — <span style={{ color: "var(--hq-text)" }}>{a.text}</span>
            </p>
          ))}
        </div>
      </aside>

      {showAgent && <AgentLaunch task={task} onClose={() => setShowAgent(false)} />}

      <style jsx global>{`
        @media (max-width: 640px) {
          [data-hq-panel] { width: 100vw !important; }
        }
      `}</style>
    </>
  );
}
