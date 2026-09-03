import type { AgentStatus, Priority, TaskStatus } from "./types";

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function fmtDay(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === tomorrow.toDateString()) return "Tomorrow";
  return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

export function fmtDue(iso: string | null): string {
  if (!iso) return "";
  const day = fmtDay(iso);
  return day === "Today" ? fmtTime(iso) : day;
}

export function isOverdue(iso: string | null, status: TaskStatus): boolean {
  if (!iso || status === "done" || status === "cancelled") return false;
  return new Date(iso).getTime() < Date.now();
}

export function fmtCountdown(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "now";
  const mins = Math.floor(ms / 60000);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h > 0) return `in ${h}h ${m}m`;
  const s = Math.floor((ms % 60000) / 1000);
  if (mins === 0) return `in ${s}s`;
  return `in ${m}m`;
}

export function fmtAgo(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${Math.round(n / 1000)}k`;
  return String(n);
}

export const STATUS_LABEL: Record<TaskStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  waiting: "Waiting",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled",
};

export const PRIORITY_LABEL: Record<Priority, string> = {
  urgent: "Urgent",
  important: "Important",
  normal: "Normal",
  later: "Later",
};

export const AGENT_STATUS_LABEL: Record<AgentStatus, string> = {
  queued: "Queued",
  planning: "Planning",
  working: "Working",
  waiting_input: "Waiting for input",
  waiting_approval: "Waiting for approval",
  verifying: "Verifying",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const TASK_STATUSES: TaskStatus[] = [
  "open", "in_progress", "waiting", "blocked", "done", "cancelled",
];

export const PRIORITIES: Priority[] = ["urgent", "important", "normal", "later"];
