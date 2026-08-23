"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useHQ } from "../lib/store";
import type { NotificationKind } from "../lib/types";
import { fmtAgo } from "../lib/format";
import { EmptyState, SectionTitle } from "../components/ui";

const KIND_META: Record<NotificationKind, { label: string; color: string }> = {
  mention: { label: "Mention", color: "var(--hq-bronze)" },
  due_soon: { label: "Due soon", color: "var(--hq-gold)" },
  overdue: { label: "Overdue", color: "var(--hq-danger)" },
  agent_done: { label: "Agent done", color: "var(--hq-success)" },
  agent_failed: { label: "Agent failed", color: "var(--hq-danger)" },
  approval: { label: "Approval", color: "var(--hq-danger)" },
  calendar: { label: "Calendar", color: "var(--hq-bronze)" },
  followup: { label: "Follow-up", color: "var(--hq-muted)" },
};

export default function NotificationsPage() {
  const { notifications, markNotificationRead, markAllNotificationsRead } = useHQ();

  const sorted = useMemo(
    () => [...notifications].sort((a, b) => b.at.localeCompare(a.at)),
    [notifications]
  );
  const unread = sorted.filter((n) => !n.read);
  const read = sorted.filter((n) => n.read);

  const Row = ({ id }: { id: string }) => {
    const n = sorted.find((x) => x.id === id)!;
    const meta = KIND_META[n.kind];
    const inner = (
      <>
        <span className="hq-dot" style={{ background: meta.color, opacity: n.read ? 0.4 : 1 }} />
        <span style={{ flex: 1, minWidth: 0, fontSize: 13.5, color: n.read ? "var(--hq-muted)" : "var(--hq-text)" }}>
          {n.text}
        </span>
        <span className="hq-badge" data-hq-hide-sm style={{ color: meta.color }}>{meta.label}</span>
        <span className="hq-mono" style={{ color: "var(--hq-muted)", flexShrink: 0 }}>{fmtAgo(n.at)}</span>
      </>
    );
    const style = { textDecoration: "none", color: "inherit" } as const;
    return n.href ? (
      <Link href={n.href} className="hq-row hq-row-click" style={style} onClick={() => markNotificationRead(n.id)}>
        {inner}
      </Link>
    ) : (
      <button className="hq-row hq-row-click" style={{ ...style, width: "100%", textAlign: "left", background: "none", border: "none", cursor: "pointer" }} onClick={() => markNotificationRead(n.id)}>
        {inner}
      </button>
    );
  };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "24px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, flex: 1 }}>Notifications</h1>
        {unread.length > 0 && (
          <button className="hq-btn hq-btn-sm" onClick={markAllNotificationsRead}>Mark all read</button>
        )}
      </div>

      <section style={{ marginBottom: 22 }}>
        <SectionTitle>Unread · {unread.length}</SectionTitle>
        {unread.length > 0 ? (
          <div className="hq-card" style={{ padding: 0, overflow: "hidden" }}>
            {unread.map((n) => <Row key={n.id} id={n.id} />)}
          </div>
        ) : (
          <EmptyState title="You're caught up." hint="Mentions, approvals, deadlines, and agent results land here." />
        )}
      </section>

      <section>
        <SectionTitle>Earlier</SectionTitle>
        {read.length > 0 ? (
          <div className="hq-card" style={{ padding: 0, overflow: "hidden" }}>
            {read.map((n) => <Row key={n.id} id={n.id} />)}
          </div>
        ) : (
          <EmptyState title="Nothing earlier." />
        )}
      </section>

      <p style={{ fontSize: 12, color: "var(--hq-muted)", marginTop: 14 }}>
        Reminders to teammates are delivered automatically in-app, by email, or by SMS.
        Anything sent outside the team requires your approval first.
      </p>
    </div>
  );
}
