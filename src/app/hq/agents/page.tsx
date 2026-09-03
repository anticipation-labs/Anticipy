"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useHQ } from "../lib/store";
import { fmtAgo, fmtTokens } from "../lib/format";
import { AgentStatusBadge, Avatar, EmptyState, SectionTitle } from "../components/ui";
import AgentLaunch from "../components/AgentLaunch";

export default function AgentsPage() {
  const { runs, people } = useHQ();
  const [showLaunch, setShowLaunch] = useState(false);

  const groups = useMemo(() => {
    const active = runs.filter((r) => ["queued", "planning", "working", "verifying"].includes(r.status));
    const needsAttention = runs.filter((r) => ["waiting_input", "waiting_approval"].includes(r.status));
    const finished = runs.filter((r) => ["done", "failed", "cancelled"].includes(r.status));
    return { active, needsAttention, finished };
  }, [runs]);

  const Row = ({ id }: { id: string }) => {
    const r = runs.find((x) => x.id === id)!;
    const req = people.find((p) => p.id === r.requester);
    return (
      <Link href={`/hq/agents/${r.id}`} className="hq-row hq-row-click" style={{ textDecoration: "none", color: "inherit" }}>
        <AgentStatusBadge status={r.status} />
        <span style={{ flex: 1, minWidth: 0, fontSize: 13.5, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {r.taskName}
        </span>
        <span className="hq-badge" data-hq-hide-sm>{r.agent}</span>
        <span className="hq-mono" style={{ color: "var(--hq-muted)" }} data-hq-hide-sm>
          {fmtTokens(r.tokens)} tok · ${r.costUsd.toFixed(2)}
        </span>
        <span className="hq-mono" style={{ color: "var(--hq-muted)" }}>{fmtAgo(r.startedAt)}</span>
        {req && <Avatar name={req.name} size={20} />}
      </Link>
    );
  };

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "24px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, flex: 1 }}>Agents</h1>
        <button className="hq-btn hq-btn-primary" onClick={() => setShowLaunch(true)}>Run with agent</button>
      </div>

      <section style={{ marginBottom: 22 }}>
        <SectionTitle>Needs attention</SectionTitle>
        {groups.needsAttention.length > 0 ? (
          <div className="hq-card">{groups.needsAttention.map((r) => <Row key={r.id} id={r.id} />)}</div>
        ) : (
          <EmptyState title="No questions or approvals waiting." />
        )}
      </section>

      <section style={{ marginBottom: 22 }}>
        <SectionTitle>Running</SectionTitle>
        {groups.active.length > 0 ? (
          <div className="hq-card">{groups.active.map((r) => <Row key={r.id} id={r.id} />)}</div>
        ) : (
          <EmptyState title="No agents running right now." hint="Launch one from any task, or from the button above." />
        )}
      </section>

      <section>
        <SectionTitle>Finished</SectionTitle>
        {groups.finished.length > 0 ? (
          <div className="hq-card">{groups.finished.map((r) => <Row key={r.id} id={r.id} />)}</div>
        ) : (
          <EmptyState title="No finished runs yet." />
        )}
      </section>

      {showLaunch && <AgentLaunch task={null} onClose={() => setShowLaunch(false)} />}
    </div>
  );
}
