"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useHQ } from "../lib/store";
import type { PersonId, Priority, Project, Task } from "../lib/types";
import { Modal, PriorityBadge, ProjectBadge } from "./ui";

const PAGES: { label: string; href: string }[] = [
  { label: "Today", href: "/hq/today" },
  { label: "Work", href: "/hq/work" },
  { label: "Agents", href: "/hq/agents" },
  { label: "Calendar", href: "/hq/calendar" },
  { label: "People", href: "/hq/people" },
  { label: "Notifications", href: "/hq/notifications" },
  { label: "Settings", href: "/hq/settings" },
];

export interface TaskDraft {
  title: string;
  owner: PersonId | null;
  due: string | null;
  reminderChannel: "In-app" | "Email" | "SMS" | "Email + SMS" | null;
  project: Project;
  priority: Priority;
}

/** Naive natural-language parse: enough for the prototype to feel real. */
export function parseDraft(input: string): TaskDraft {
  const lower = input.toLowerCase();
  let owner: PersonId | null = null;
  if (/\bari\b/.test(lower)) owner = "ari";
  else if (/\bjose\b/.test(lower)) owner = "jose";
  else if (/\bomar\b|\bme\b|\bmyself\b/.test(lower)) owner = "omar";

  let due: string | null = null;
  const days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
  const dayIdx = days.findIndex((d) => lower.includes(d));
  if (dayIdx >= 0) {
    const d = new Date();
    let diff = (dayIdx - d.getDay() + 7) % 7;
    if (diff === 0) diff = 7;
    d.setDate(d.getDate() + diff);
    d.setHours(17, 0, 0, 0);
    due = d.toISOString();
  } else if (lower.includes("tomorrow")) {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
    due = d.toISOString();
  } else if (lower.includes("today") || lower.includes("tonight") || lower.includes("by end of day")) {
    const d = new Date();
    d.setHours(17, 0, 0, 0);
    due = d.toISOString();
  }

  let reminderChannel: TaskDraft["reminderChannel"] = null;
  const wantsSms = /\bsms\b|\btext\b/.test(lower);
  const wantsEmail = /\bemail\b/.test(lower) && /remind/.test(lower);
  if (wantsSms && wantsEmail) reminderChannel = "Email + SMS";
  else if (wantsSms) reminderChannel = "SMS";
  else if (wantsEmail) reminderChannel = "Email";

  let project: Project = "Company";
  if (/onboard|engine|bug|deploy|code|app|asr|agent/.test(lower)) project = "Software";
  else if (/pendant|battery|pcb|board|enclosure|manufactur|mic/.test(lower)) project = "Hardware";
  else if (/video|content|post|launch|pre-?order|growth/.test(lower)) project = "Growth";
  else if (/investor|fund|pitch|deck/.test(lower)) project = "Fundraise";

  let priority: Priority = "normal";
  if (/urgent|asap|now\b/.test(lower)) priority = "urgent";
  else if (/important|priority/.test(lower)) priority = "important";
  else if (/someday|later|eventually/.test(lower)) priority = "later";

  // Title: strip the ask/remind scaffolding.
  let title = input
    .replace(/^(ask|tell|get)\s+(ari|jose|omar)\s+to\s+/i, "")
    .replace(/\s+and\s+remind\s+(him|her|them|me)[^.]*$/i, "")
    .replace(/\s+by\s+(tomorrow|today|tonight|sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b[^,]*/i, "")
    .trim();
  if (title.length > 0) title = title[0].toUpperCase() + title.slice(1);

  return { title: title || input, owner, due, reminderChannel, project, priority };
}

export function DraftReview({
  draft,
  onConfirm,
  onCancel,
}: {
  draft: TaskDraft;
  onConfirm: (d: TaskDraft) => void;
  onCancel: () => void;
}) {
  const { people } = useHQ();
  const [d, setD] = useState<TaskDraft>(draft);
  return (
    <Modal onClose={onCancel} label="Review task draft" width={520}>
      <div style={{ padding: 16 }}>
        <p className="hq-label">Draft — nothing is created until you confirm</p>
        <input
          className="hq-input"
          style={{ fontSize: 15, fontWeight: 500, marginBottom: 12 }}
          value={d.title}
          onChange={(e) => setD({ ...d, title: e.target.value })}
          aria-label="Task title"
        />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <label className="hq-label">Owner</label>
            <select className="hq-input" value={d.owner ?? ""} onChange={(e) => setD({ ...d, owner: (e.target.value || null) as PersonId | null })}>
              <option value="">Unassigned</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="hq-label">Deadline</label>
            <input
              type="datetime-local"
              className="hq-input"
              value={d.due ? d.due.slice(0, 16) : ""}
              onChange={(e) => setD({ ...d, due: e.target.value ? new Date(e.target.value).toISOString() : null })}
            />
          </div>
          <div>
            <label className="hq-label">Reminder channel</label>
            <select
              className="hq-input"
              value={d.reminderChannel ?? "None"}
              onChange={(e) => setD({ ...d, reminderChannel: e.target.value === "None" ? null : (e.target.value as TaskDraft["reminderChannel"]) })}
            >
              {["None", "In-app", "Email", "SMS", "Email + SMS"].map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="hq-label">Project</label>
            <select className="hq-input" value={d.project} onChange={(e) => setD({ ...d, project: e.target.value as Project })}>
              {["Hardware", "Software", "Growth", "Company", "Fundraise"].map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <label className="hq-label">Suggested priority</label>
          <div style={{ display: "flex", gap: 6 }}>
            {(["urgent", "important", "normal", "later"] as Priority[]).map((p) => (
              <button
                key={p}
                className="hq-btn hq-btn-sm"
                style={d.priority === p ? { borderColor: "var(--hq-bronze)", color: "var(--hq-bronze)", background: "var(--hq-surface)" } : undefined}
                onClick={() => setD({ ...d, priority: p })}
              >
                {p[0].toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <button className="hq-btn" onClick={onCancel}>Cancel</button>
          <button className="hq-btn hq-btn-primary" onClick={() => onConfirm(d)} disabled={!d.title.trim()}>
            Create task
          </button>
        </div>
      </div>
    </Modal>
  );
}

export function createTaskFromDraft(d: TaskDraft): Task {
  const id = `task-new-${Date.now()}`;
  return {
    id,
    title: d.title,
    outcome: "",
    owner: d.owner,
    agentRunId: null,
    status: "open",
    priority: d.priority,
    project: d.project,
    due: d.due,
    recurrence: "none",
    reminder: d.reminderChannel
      ? { channel: d.reminderChannel, when: d.due ?? "Before deadline", repeat: false, escalate: false }
      : null,
    notes: "",
    checklist: [],
    dependsOn: [],
    links: [],
    comments: [],
    activity: [{ id: `${id}-a1`, text: "Task created", at: new Date().toISOString() }],
    scheduledAt: null,
    proof: null,
    createdAt: new Date().toISOString(),
    order: 0,
  };
}

export default function CommandK({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const { tasks, addTask } = useHQ();
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<TaskDraft | null>(null);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pageHits = PAGES.filter((p) => !q || p.label.toLowerCase().includes(q)).map((p) => ({
      kind: "page" as const, label: `Go to ${p.label}`, href: p.href,
    }));
    const taskHits = q
      ? tasks
          .filter((t) => t.title.toLowerCase().includes(q))
          .slice(0, 5)
          .map((t) => ({ kind: "task" as const, label: t.title, href: `/hq/work?task=${t.id}` }))
      : [];
    const create = q.length > 2
      ? [{ kind: "create" as const, label: `Create task: “${query.trim()}”`, href: "" }]
      : [];
    return [...create, ...taskHits, ...pageHits];
  }, [query, tasks]);

  if (!open) return null;

  if (draft) {
    return (
      <DraftReview
        draft={draft}
        onCancel={() => { setDraft(null); onClose(); }}
        onConfirm={(d) => {
          addTask(createTaskFromDraft(d));
          setDraft(null);
          onClose();
          router.push("/hq/work");
        }}
      />
    );
  }

  const activate = (r: (typeof results)[number]) => {
    if (r.kind === "create") {
      setDraft(parseDraft(query.trim()));
    } else {
      onClose();
      router.push(r.href);
    }
  };

  return (
    <Modal onClose={onClose} label="Command menu" width={600}>
      <div>
        <input
          ref={inputRef}
          className="hq-input"
          style={{ border: "none", borderBottom: "1px solid var(--hq-border)", borderRadius: "10px 10px 0 0", padding: "14px 16px", fontSize: 15 }}
          placeholder="Add a task or ask an agent."
          value={query}
          onChange={(e) => { setQuery(e.target.value); setSelected(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setSelected((s) => Math.min(s + 1, results.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setSelected((s) => Math.max(s - 1, 0)); }
            if (e.key === "Enter" && results[selected]) { e.preventDefault(); activate(results[selected]); }
          }}
          aria-label="Command input"
        />
        <div style={{ padding: 6, maxHeight: 340, overflowY: "auto" }}>
          {results.map((r, i) => (
            <button
              key={`${r.kind}-${r.label}`}
              onClick={() => activate(r)}
              onMouseEnter={() => setSelected(i)}
              style={{
                display: "flex", alignItems: "center", gap: 10, width: "100%",
                textAlign: "left", padding: "8px 10px", borderRadius: 8,
                background: i === selected ? "var(--hq-surface)" : "transparent",
                border: "none", cursor: "pointer", fontSize: 13.5, color: "var(--hq-text)",
              }}
            >
              <span style={{ color: "var(--hq-muted)", fontSize: 12, width: 44, flexShrink: 0 }}>
                {r.kind === "create" ? "New" : r.kind === "task" ? "Task" : "Page"}
              </span>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.label}</span>
            </button>
          ))}
          {results.length === 0 && (
            <p style={{ padding: 16, color: "var(--hq-muted)", fontSize: 13 }}>Nothing matches.</p>
          )}
        </div>
        <div className="hq-mono" style={{ borderTop: "1px solid var(--hq-border)", padding: "8px 16px", color: "var(--hq-muted)", display: "flex", gap: 14 }}>
          <span><span className="hq-kbd">↑↓</span> navigate</span>
          <span><span className="hq-kbd">Enter</span> confirm</span>
          <span><span className="hq-kbd">Esc</span> close</span>
        </div>
      </div>
    </Modal>
  );
}
