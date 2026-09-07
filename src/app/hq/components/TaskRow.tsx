"use client";

import { useHQ } from "../lib/store";
import type { Task } from "../lib/types";
import { fmtDue, isOverdue } from "../lib/format";
import { AgentIcon, Avatar, Check, PriorityBadge, ProjectBadge, StatusBadge } from "./ui";

export default function TaskRow({
  task,
  onOpen,
  selected,
  onSelect,
  compact,
}: {
  task: Task;
  onOpen: (id: string) => void;
  selected?: boolean;
  onSelect?: (id: string) => void;
  compact?: boolean;
}) {
  const { updateTask, logActivity, people } = useHQ();
  const owner = people.find((p) => p.id === task.owner);
  const done = task.status === "done";
  const overdue = isOverdue(task.due, task.status);

  const toggleDone = () => {
    const next = done ? "open" : "done";
    updateTask(task.id, { status: next });
    logActivity(task.id, next === "done" ? "Marked complete" : "Reopened");
  };

  return (
    <div
      className="hq-row hq-row-click"
      onClick={() => onOpen(task.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter") onOpen(task.id); }}
      style={selected ? { background: "var(--hq-surface)" } : undefined}
    >
      {onSelect && (
        <input
          type="checkbox"
          checked={Boolean(selected)}
          onClick={(e) => e.stopPropagation()}
          onChange={() => onSelect(task.id)}
          aria-label={`Select ${task.title}`}
          style={{ accentColor: "var(--hq-bronze)" }}
        />
      )}
      <Check checked={done} onToggle={toggleDone} label={`Complete ${task.title}`} />
      <span
        style={{
          flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          fontWeight: 500, fontSize: 13.5,
          color: done || task.status === "cancelled" ? "var(--hq-muted)" : "var(--hq-text)",
          textDecoration: done ? "line-through" : "none",
        }}
      >
        {task.title}
      </span>
      {task.agentRunId && <AgentIcon />}
      {!compact && <StatusBadge status={task.status} />}
      {!compact && <PriorityBadge priority={task.priority} />}
      {!compact && <span data-hq-hide-sm><ProjectBadge project={task.project} /></span>}
      {task.due && (
        <span
          className="hq-mono"
          style={{ color: overdue ? "var(--hq-danger)" : "var(--hq-muted)", flexShrink: 0 }}
        >
          {fmtDue(task.due)}
        </span>
      )}
      {owner ? <Avatar name={owner.name} size={22} /> : <span className="hq-avatar" style={{ width: 22, height: 22, fontSize: 10, color: "var(--hq-muted)" }}>–</span>}
    </div>
  );
}
