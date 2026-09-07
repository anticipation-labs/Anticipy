"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useHQ } from "../../lib/store";
import { fmtAgo, fmtTime, fmtTokens } from "../../lib/format";
import { AgentStatusBadge, Avatar, EmptyState } from "../../components/ui";

export default function AgentRunPage() {
  const { id } = useParams<{ id: string }>();
  const { runs, people, tasks, updateRun, updateTask, logActivity } = useHQ();
  const run = runs.find((r) => r.id === id);
  const [showRaw, setShowRaw] = useState(false);

  if (!run) {
    return (
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "40px 20px" }}>
        <EmptyState title="Run not found." hint="It may have been cleared from this prototype session." />
        <p style={{ marginTop: 12 }}><Link href="/hq/agents" style={{ color: "var(--hq-bronze)" }}>← Back to agents</Link></p>
      </div>
    );
  }

  const requester = people.find((p) => p.id === run.requester);
  const task = tasks.find((t) => t.id === run.taskId);
  const running = ["queued", "planning", "working", "verifying", "waiting_input", "waiting_approval"].includes(run.status);

  const answer = (choice: string) => {
    updateRun(run.id, {
      question: run.question ? { ...run.question, answered: choice } : null,
      status: "working",
      liveStatus: "Continuing with your answer",
      steps: [
        ...run.steps.map((s) => ({ ...s, state: "done" as const })),
        { id: `s-${Date.now()}`, label: `Answered: ${choice}`, at: new Date().toISOString(), state: "active" as const },
      ],
    });
  };

  const decide = (decided: "approved" | "rejected") => {
    const approvedRun = decided === "approved";
    updateRun(run.id, {
      approval: run.approval ? { ...run.approval, decided } : null,
      status: approvedRun ? "verifying" : "cancelled",
      liveStatus: approvedRun ? "Applying the approved action" : "Cancelled",
      steps: [
        ...run.steps.map((s) => ({ ...s, state: "done" as const })),
        {
          id: `s-${Date.now()}`,
          label: approvedRun ? "Approval granted — applying change" : "Approval declined — stopping safely",
          at: new Date().toISOString(),
          state: "active" as const,
        },
      ],
    });
    if (task) logActivity(task.id, approvedRun ? "Approved agent action" : "Declined agent action");
  };

  const stop = () => {
    updateRun(run.id, {
      status: "cancelled",
      liveStatus: "Stopped by you",
      steps: [
        ...run.steps.map((s) => ({ ...s, state: "done" as const })),
        { id: `s-${Date.now()}`, label: "Stopped by user", at: new Date().toISOString(), state: "done" as const },
      ],
    });
    if (task) {
      updateTask(task.id, { status: "open" });
      logActivity(task.id, "Agent run stopped");
    }
  };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "24px 20px" }}>
      <Link href="/hq/agents" className="hq-no-print" style={{ fontSize: 12.5, color: "var(--hq-muted)", textDecoration: "none" }}>← Agents</Link>

      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, margin: "10px 0 4px" }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, flex: 1, lineHeight: 1.3 }}>{run.taskName}</h1>
        {running && (
          <button className="hq-btn hq-btn-danger hq-no-print" onClick={stop}>Stop</button>
        )}
      </div>

      {/* Metadata strip */}
      <div className="hq-mono" style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", color: "var(--hq-muted)", margin: "8px 0 16px" }}>
        <span>{run.agent}</span>
        <span>requested by {requester?.name}</span>
        <span>started {fmtAgo(run.startedAt)} ({fmtTime(run.startedAt)})</span>
        <span>runtime {run.runtimeMin}m / {run.timeLimitMin}m</span>
        <span>{fmtTokens(run.tokens)} tokens</span>
        <span>${run.costUsd.toFixed(2)} / ${run.budgetUsd.toFixed(2)} budget</span>
      </div>

      <div style={{ marginBottom: 18 }}>
        <AgentStatusBadge status={run.status} />
        <span style={{ fontSize: 13, color: "var(--hq-muted)", marginLeft: 10 }}>{run.liveStatus}</span>
      </div>

      {/* Question */}
      {run.question && !run.question.answered && (
        <div className="hq-card hq-pop-in" style={{ padding: 14, marginBottom: 16, borderColor: "var(--hq-gold)" }}>
          <p className="hq-label" style={{ color: "var(--hq-bronze)" }}>The agent needs an answer</p>
          <p style={{ fontSize: 14, marginBottom: 10 }}>{run.question.text}</p>
          <div className="hq-no-print" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {run.question.options.map((o) => (
              <button key={o} className="hq-btn" onClick={() => answer(o)}>{o}</button>
            ))}
          </div>
        </div>
      )}
      {run.question?.answered && (
        <div className="hq-card" style={{ padding: 12, marginBottom: 16, background: "var(--hq-surface)", fontSize: 13 }}>
          Question answered: <strong>{run.question.answered}</strong>
        </div>
      )}

      {/* Approval */}
      {run.approval && !run.approval.decided && (
        <div className="hq-card hq-pop-in" style={{ padding: 14, marginBottom: 16, borderColor: "var(--hq-danger)" }}>
          <p className="hq-label" style={{ color: "var(--hq-danger)" }}>Approval required</p>
          <p style={{ fontSize: 14 }}>{run.approval.action}</p>
          <p style={{ fontSize: 12.5, color: "var(--hq-muted)", marginTop: 4 }}>{run.approval.reason}</p>
          <div className="hq-no-print" style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="hq-btn hq-btn-primary" onClick={() => decide("approved")}>Approve</button>
            <button className="hq-btn hq-btn-danger" onClick={() => decide("rejected")}>Decline</button>
          </div>
        </div>
      )}
      {run.approval?.decided && (
        <div className="hq-card" style={{ padding: 12, marginBottom: 16, background: "var(--hq-surface)", fontSize: 13 }}>
          Action {run.approval.decided}: {run.approval.action}
        </div>
      )}

      {/* Timeline */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <p className="hq-label">Timeline</p>
        <button className="hq-btn hq-btn-sm hq-no-print" onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? "Hide raw logs" : "Show raw logs"}
        </button>
      </div>
      <div className="hq-card" style={{ padding: "6px 0", marginBottom: 18 }}>
        {run.steps.map((s, i) => (
          <div key={s.id} style={{ display: "flex", gap: 12, padding: "8px 14px", position: "relative" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 14 }}>
              <span
                className={s.state === "active" ? "hq-dot hq-pulse" : "hq-dot"}
                style={{
                  width: 9, height: 9, marginTop: 5,
                  background: s.state === "done" ? "var(--hq-success)" : s.state === "active" ? "var(--hq-bronze)" : "var(--hq-border)",
                }}
              />
              {i < run.steps.length - 1 && <span style={{ flex: 1, width: 1, background: "var(--hq-border)", marginTop: 3 }} />}
            </div>
            <div style={{ flex: 1, minWidth: 0, paddingBottom: 2 }}>
              <p style={{ fontSize: 13.5, fontWeight: s.state === "active" ? 600 : 500 }}>{s.label}</p>
              {s.detail && <p style={{ fontSize: 12.5, color: "var(--hq-muted)" }}>{s.detail}</p>}
              {showRaw && s.raw && (
                <p className="hq-mono" style={{ background: "var(--hq-surface)", border: "1px solid var(--hq-border)", borderRadius: 6, padding: "5px 8px", marginTop: 5, color: "var(--hq-muted)", overflowX: "auto" }}>
                  {s.raw}
                </p>
              )}
            </div>
            <span className="hq-mono" style={{ color: "var(--hq-muted)", flexShrink: 0 }}>{fmtTime(s.at)}</span>
          </div>
        ))}
      </div>

      {/* Proof */}
      {run.proof && (
        <>
          <p className="hq-label">{run.status === "failed" ? "Result" : "Proof of completion"}</p>
          <div className="hq-card" style={{ padding: 14 }}>
            <p style={{ fontSize: 13.5, marginBottom: 10 }}>{run.proof.summary}</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
              {run.proof.filesChanged && run.proof.filesChanged.length > 0 && (
                <div>
                  <p className="hq-label">Files changed</p>
                  {run.proof.filesChanged.map((f) => <p key={f} className="hq-mono">{f}</p>)}
                </div>
              )}
              {run.proof.pullRequest && (
                <div>
                  <p className="hq-label">Pull request</p>
                  <p className="hq-mono" style={{ color: "var(--hq-bronze)" }}>{run.proof.pullRequest}</p>
                </div>
              )}
              {run.proof.sitesVisited && (
                <div>
                  <p className="hq-label">Websites visited</p>
                  {run.proof.sitesVisited.map((s) => <p key={s} className="hq-mono">{s}</p>)}
                </div>
              )}
              {run.proof.emailReceipt && (
                <div>
                  <p className="hq-label">Email receipt</p>
                  <p className="hq-mono">{run.proof.emailReceipt}</p>
                </div>
              )}
              {run.proof.screenshots && (
                <div>
                  <p className="hq-label">Screenshots</p>
                  {run.proof.screenshots.map((s) => <p key={s} className="hq-mono">{s}</p>)}
                </div>
              )}
              {run.proof.tests && (
                <div>
                  <p className="hq-label">Tests</p>
                  <p className="hq-mono">{run.proof.tests}</p>
                </div>
              )}
              <div>
                <p className="hq-label">Cost & runtime</p>
                <p className="hq-mono">${run.costUsd.toFixed(2)} · {run.runtimeMin}m · {fmtTokens(run.tokens)} tokens</p>
              </div>
            </div>
          </div>
        </>
      )}

      {task && (
        <p style={{ marginTop: 16, fontSize: 13 }}>
          Connected task: <Link href={`/hq/work?task=${task.id}`} style={{ color: "var(--hq-bronze)" }}>{task.title}</Link>
        </p>
      )}
    </div>
  );
}
