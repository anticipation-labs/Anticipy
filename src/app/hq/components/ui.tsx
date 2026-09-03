"use client";

import { useEffect, useRef, useState } from "react";
import type { AgentStatus, Priority, TaskStatus } from "../lib/types";
import { AGENT_STATUS_LABEL, PRIORITY_LABEL, STATUS_LABEL } from "../lib/format";

export function Avatar({ name, size = 24 }: { name: string; size?: number }) {
  return (
    <span
      className="hq-avatar"
      style={{ width: size, height: size, fontSize: size * 0.42 }}
      aria-hidden
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}

export function Check({
  checked,
  onToggle,
  label,
}: {
  checked: boolean;
  onToggle: () => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      className="hq-check"
      data-checked={checked}
      role="checkbox"
      aria-checked={checked}
      aria-label={label ?? "Toggle"}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
    >
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
        <path d="M1.5 5.5L4 8L8.5 2.5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

const STATUS_DOT: Record<TaskStatus, string> = {
  open: "#9b968d",
  in_progress: "#8a6b44",
  waiting: "#b08d3e",
  blocked: "#a33a3a",
  done: "#2e6b4f",
  cancelled: "#c9c4bb",
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span className="hq-badge">
      <span className="hq-dot" style={{ background: STATUS_DOT[status] }} />
      {STATUS_LABEL[status]}
    </span>
  );
}

const PRIORITY_COLOR: Record<Priority, string> = {
  urgent: "#a33a3a",
  important: "#8a6b44",
  normal: "#66625b",
  later: "#9b968d",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span className="hq-badge" style={{ color: PRIORITY_COLOR[priority] }}>
      {PRIORITY_LABEL[priority]}
    </span>
  );
}

export function ProjectBadge({ project }: { project: string }) {
  return <span className="hq-badge">{project}</span>;
}

const AGENT_DOT: Record<AgentStatus, string> = {
  queued: "#9b968d",
  planning: "#8a6b44",
  working: "#8a6b44",
  waiting_input: "#b08d3e",
  waiting_approval: "#b08d3e",
  verifying: "#8a6b44",
  done: "#2e6b4f",
  failed: "#a33a3a",
  cancelled: "#c9c4bb",
};

export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  const live = ["planning", "working", "verifying"].includes(status);
  return (
    <span className="hq-badge">
      <span
        className={`hq-dot ${live ? "hq-pulse" : ""}`}
        style={{ background: AGENT_DOT[status] }}
      />
      {AGENT_STATUS_LABEL[status]}
    </span>
  );
}

export function AgentIcon({ size = 13 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-label="Agent" style={{ flexShrink: 0 }}>
      <rect x="2" y="3.5" width="10" height="8" rx="2" stroke="#8a6b44" strokeWidth="1.3" />
      <circle cx="5.2" cy="7.5" r="0.9" fill="#8a6b44" />
      <circle cx="8.8" cy="7.5" r="0.9" fill="#8a6b44" />
      <path d="M7 3.5V1.5" stroke="#8a6b44" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

/** Tiny autosave indicator: flashes "Saved" then fades without interrupting. */
export function useSaved(): [boolean, () => void] {
  const [saved, setSaved] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const flash = () => {
    setSaved(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setSaved(false), 1400);
  };
  return [saved, flash];
}

export function SavedDot({ visible }: { visible: boolean }) {
  return (
    <span
      className="hq-mono"
      style={{
        color: "var(--hq-success)",
        opacity: visible ? 1 : 0,
        transition: "opacity 160ms ease",
        fontSize: 11,
      }}
      aria-live="polite"
    >
      Saved
    </span>
  );
}

export function SectionTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 8 }}>
      <h2 style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--hq-muted)" }}>
        {children}
      </h2>
      {right}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="hq-card" style={{ padding: "28px 16px", textAlign: "center" }}>
      <p style={{ fontWeight: 500 }}>{title}</p>
      {hint && <p style={{ color: "var(--hq-muted)", fontSize: 13, marginTop: 4 }}>{hint}</p>}
    </div>
  );
}

export function Modal({
  onClose,
  children,
  width = 560,
  label,
}: {
  onClose: () => void;
  children: React.ReactNode;
  width?: number;
  label: string;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="hq-fade-in hq-no-print"
      role="dialog"
      aria-modal="true"
      aria-label={label}
      style={{
        position: "fixed", inset: 0, zIndex: 60,
        background: "rgba(17,17,17,0.32)",
        display: "flex", alignItems: "flex-start", justifyContent: "center",
        padding: "10vh 16px 16px",
      }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="hq-card hq-pop-in"
        style={{ width: "100%", maxWidth: width, background: "#fff", maxHeight: "80vh", overflowY: "auto" }}
      >
        {children}
      </div>
    </div>
  );
}
