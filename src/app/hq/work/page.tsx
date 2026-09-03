"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useHQ } from "../lib/store";
import type { PersonId, Priority, Project, Task, TaskStatus, ViewName } from "../lib/types";
import { fmtDue, PRIORITIES, PRIORITY_LABEL, STATUS_LABEL, TASK_STATUSES } from "../lib/format";
import TaskRow from "../components/TaskRow";
import TaskPanel from "../components/TaskPanel";
import { Modal, EmptyState, Avatar, PriorityBadge, AgentIcon } from "../components/ui";
import { createTaskFromDraft } from "../components/CommandK";

const VIEWS: ViewName[] = ["My work", "Company", "Software", "Hardware", "Growth", "Waiting", "Completed"];
type Mode = "List" | "Board" | "Calendar";
type SortKey = "order" | "due" | "priority" | "title";

const priorityRank: Record<Priority, number> = { urgent: 0, important: 1, normal: 2, later: 3 };

function ManualTaskForm({ onClose }: { onClose: () => void }) {
  const { addTask, people } = useHQ();
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState<PersonId | "">("");
  const [project, setProject] = useState<Project>("Company");
  const [priority, setPriority] = useState<Priority>("normal");
  const [due, setDue] = useState("");
  const [recurrence, setRecurrence] = useState<Task["recurrence"]>("none");

  return (
    <Modal onClose={onClose} label="New task" width={480}>
      <form
        style={{ padding: 16 }}
        onSubmit={(e) => {
          e.preventDefault();
          if (!title.trim()) return;
          const t = createTaskFromDraft({
            title: title.trim(),
            owner: owner || null,
            due: due ? new Date(due).toISOString() : null,
            reminderChannel: null,
            project,
            priority,
          });
          addTask({ ...t, recurrence });
          onClose();
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>New task</h2>
        <label className="hq-label">Title</label>
        <input className="hq-input" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} style={{ marginBottom: 10 }} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <label className="hq-label">Owner</label>
            <select className="hq-input" value={owner} onChange={(e) => setOwner(e.target.value as PersonId | "")}>
              <option value="">Unassigned</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="hq-label">Project</label>
            <select className="hq-input" value={project} onChange={(e) => setProject(e.target.value as Project)}>
              {["Hardware", "Software", "Growth", "Company", "Fundraise"].map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="hq-label">Priority</label>
            <select className="hq-input" value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
              {PRIORITIES.map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
            </select>
          </div>
          <div>
            <label className="hq-label">Due</label>
            <input type="datetime-local" className="hq-input" value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
          <div>
            <label className="hq-label">Repeats</label>
            <select className="hq-input" value={recurrence} onChange={(e) => setRecurrence(e.target.value as Task["recurrence"])}>
              {["none", "daily", "weekly", "monthly"].map((r) => <option key={r} value={r}>{r === "none" ? "Does not repeat" : r[0].toUpperCase() + r.slice(1)}</option>)}
            </select>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button type="button" className="hq-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="hq-btn hq-btn-primary" disabled={!title.trim()}>Create task</button>
        </div>
      </form>
    </Modal>
  );
}

function WorkPageInner() {
  const params = useSearchParams();
  const { tasks, user, people, updateTask, logActivity } = useHQ();
  const [view, setView] = useState<ViewName>("My work");
  const [mode, setMode] = useState<Mode>("List");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("order");
  const [filterStatus, setFilterStatus] = useState<TaskStatus | "all">("all");
  const [filterOwner, setFilterOwner] = useState<PersonId | "all">("all");
  const [openTask, setOpenTask] = useState<string | null>(params.get("task"));
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showManual, setShowManual] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let list = tasks;
    switch (view) {
      case "My work": list = list.filter((t) => t.owner === (user ?? "omar") && !["done", "cancelled"].includes(t.status)); break;
      case "Company": list = list.filter((t) => !["done", "cancelled"].includes(t.status)); break;
      case "Software": list = list.filter((t) => t.project === "Software" && !["done", "cancelled"].includes(t.status)); break;
      case "Hardware": list = list.filter((t) => t.project === "Hardware" && !["done", "cancelled"].includes(t.status)); break;
      case "Growth": list = list.filter((t) => t.project === "Growth" && !["done", "cancelled"].includes(t.status)); break;
      case "Waiting": list = list.filter((t) => ["waiting", "blocked"].includes(t.status)); break;
      case "Completed": list = list.filter((t) => t.status === "done"); break;
    }
    if (filterStatus !== "all") list = list.filter((t) => t.status === filterStatus);
    if (filterOwner !== "all") list = list.filter((t) => t.owner === filterOwner);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter((t) => t.title.toLowerCase().includes(q) || t.notes.toLowerCase().includes(q));
    }
    const sorted = [...list];
    if (sort === "due") sorted.sort((a, b) => (a.due ?? "z").localeCompare(b.due ?? "z"));
    else if (sort === "priority") sorted.sort((a, b) => priorityRank[a.priority] - priorityRank[b.priority]);
    else if (sort === "title") sorted.sort((a, b) => a.title.localeCompare(b.title));
    else sorted.sort((a, b) => a.order - b.order);
    return sorted;
  }, [tasks, view, query, sort, filterStatus, filterOwner, user]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const bulk = (patch: Partial<Task>, log: string) => {
    selected.forEach((id) => { updateTask(id, patch); logActivity(id, log); });
    setSelected(new Set());
  };

  const onDropRow = (targetId: string) => {
    if (!dragId || dragId === targetId) return;
    const dragTask = tasks.find((t) => t.id === dragId);
    const targetTask = tasks.find((t) => t.id === targetId);
    if (dragTask && targetTask) {
      updateTask(dragId, { order: targetTask.order - 0.5 });
    }
    setDragId(null);
  };

  const boardStatuses: TaskStatus[] = view === "Completed" ? ["done"] : ["open", "in_progress", "waiting", "blocked", "done"];

  // Calendar view: group by day over next 7 days plus "No date".
  const calendarDays = useMemo(() => {
    const days: { label: string; date: Date | null; items: Task[] }[] = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date();
      d.setDate(d.getDate() + i);
      d.setHours(0, 0, 0, 0);
      days.push({
        label: i === 0 ? "Today" : i === 1 ? "Tomorrow" : d.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" }),
        date: d,
        items: filtered.filter((t) => t.due && new Date(t.due).toDateString() === d.toDateString()),
      });
    }
    days.push({ label: "No date", date: null, items: filtered.filter((t) => !t.due) });
    return days;
  }, [filtered]);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: "24px 20px" }}>
      <div className="hq-no-print" style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, marginRight: "auto" }}>Work</h1>
        <div style={{ display: "flex", border: "1px solid var(--hq-border)", borderRadius: 8, overflow: "hidden" }}>
          {(["List", "Board", "Calendar"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                padding: "5px 12px", fontSize: 12.5, fontWeight: 500, border: "none", cursor: "pointer",
                background: mode === m ? "var(--hq-surface)" : "#fff",
                color: mode === m ? "var(--hq-text)" : "var(--hq-muted)",
              }}
            >
              {m}
            </button>
          ))}
        </div>
        <button className="hq-btn hq-btn-primary" onClick={() => setShowManual(true)}>New task</button>
      </div>

      {/* Saved views */}
      <div className="hq-no-print" style={{ display: "flex", gap: 6, marginBottom: 12, overflowX: "auto", paddingBottom: 2 }}>
        {VIEWS.map((v) => (
          <button
            key={v}
            className="hq-btn hq-btn-sm"
            style={view === v ? { background: "#111", borderColor: "#111", color: "#fff" } : undefined}
            onClick={() => setView(v)}
          >
            {v}
          </button>
        ))}
      </div>

      {/* Search / filters / sort */}
      <div className="hq-no-print" style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <input
          className="hq-input"
          style={{ maxWidth: 260 }}
          placeholder="Search tasks…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select className="hq-input" style={{ maxWidth: 150 }} value={filterStatus} onChange={(e) => setFilterStatus(e.target.value as TaskStatus | "all")} aria-label="Filter by status">
          <option value="all">All statuses</option>
          {TASK_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
        <select className="hq-input" style={{ maxWidth: 140 }} value={filterOwner} onChange={(e) => setFilterOwner(e.target.value as PersonId | "all")} aria-label="Filter by owner">
          <option value="all">Anyone</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select className="hq-input" style={{ maxWidth: 150 }} value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Sort">
          <option value="order">Manual order</option>
          <option value="due">Sort by due</option>
          <option value="priority">Sort by priority</option>
          <option value="title">Sort by title</option>
        </select>
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div className="hq-card hq-pop-in hq-no-print" style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", marginBottom: 10, background: "var(--hq-surface)" }}>
          <span style={{ fontSize: 12.5, fontWeight: 600 }}>{selected.size} selected</span>
          <span style={{ color: "var(--hq-border)" }}>|</span>
          {people.map((p) => (
            <button key={p.id} className="hq-btn hq-btn-sm" onClick={() => bulk({ owner: p.id }, `Assigned to ${p.name}`)}>→ {p.name}</button>
          ))}
          <button className="hq-btn hq-btn-sm" onClick={() => bulk({ status: "in_progress" }, "Status → In progress")}>Start</button>
          <button className="hq-btn hq-btn-sm" onClick={() => bulk({ status: "done" }, "Marked complete")}>Complete</button>
          <button className="hq-btn hq-btn-sm hq-btn-danger" onClick={() => bulk({ status: "cancelled" }, "Cancelled")}>Cancel</button>
          <div style={{ flex: 1 }} />
          <button className="hq-btn hq-btn-sm" onClick={() => setSelected(new Set())}>Clear</button>
        </div>
      )}

      {/* List */}
      {mode === "List" && (
        filtered.length > 0 ? (
          <div className="hq-card">
            {filtered.map((t) => (
              <div
                key={t.id}
                draggable={sort === "order"}
                onDragStart={() => setDragId(t.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDropRow(t.id)}
                style={dragId === t.id ? { opacity: 0.4 } : undefined}
              >
                <TaskRow
                  task={t}
                  onOpen={setOpenTask}
                  selected={selected.has(t.id)}
                  onSelect={toggleSelect}
                />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No tasks match this view." hint="Change the view or filters, or create a task." />
        )
      )}

      {/* Board */}
      {mode === "Board" && (
        <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 8 }}>
          {boardStatuses.map((s) => {
            const col = filtered.filter((t) => t.status === s);
            return (
              <div
                key={s}
                style={{ minWidth: 220, width: 220, flexShrink: 0 }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => {
                  if (dragId) {
                    updateTask(dragId, { status: s });
                    logActivity(dragId, `Status → ${STATUS_LABEL[s]}`);
                    setDragId(null);
                  }
                }}
              >
                <p className="hq-label" style={{ padding: "0 2px" }}>{STATUS_LABEL[s]} · {col.length}</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, minHeight: 60 }}>
                  {col.map((t) => {
                    const owner = people.find((p) => p.id === t.owner);
                    return (
                      <div
                        key={t.id}
                        className="hq-card hq-row-click"
                        draggable
                        onDragStart={() => setDragId(t.id)}
                        onClick={() => setOpenTask(t.id)}
                        style={{ padding: "8px 10px", cursor: "pointer", opacity: dragId === t.id ? 0.4 : 1 }}
                      >
                        <p style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35 }}>{t.title}</p>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
                          {t.agentRunId && <AgentIcon />}
                          <PriorityBadge priority={t.priority} />
                          <div style={{ flex: 1 }} />
                          {t.due && <span className="hq-mono" style={{ color: "var(--hq-muted)" }}>{fmtDue(t.due)}</span>}
                          {owner && <Avatar name={owner.name} size={18} />}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Calendar */}
      {mode === "Calendar" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {calendarDays.map((day) => (
            <div key={day.label}>
              <p className="hq-label">{day.label}</p>
              {day.items.length > 0 ? (
                <div className="hq-card">
                  {day.items.map((t) => <TaskRow key={t.id} task={t} onOpen={setOpenTask} compact />)}
                </div>
              ) : (
                <p style={{ fontSize: 12.5, color: "var(--hq-muted)", padding: "2px 2px 0" }}>—</p>
              )}
            </div>
          ))}
        </div>
      )}

      {openTask && <TaskPanel taskId={openTask} onClose={() => setOpenTask(null)} />}
      {showManual && <ManualTaskForm onClose={() => setShowManual(false)} />}
    </div>
  );
}

export default function WorkPage() {
  return (
    <Suspense>
      <WorkPageInner />
    </Suspense>
  );
}
