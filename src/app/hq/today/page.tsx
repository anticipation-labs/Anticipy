"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useHQ } from "../lib/store";
import { fmtCountdown, fmtTime } from "../lib/format";
import TaskRow from "../components/TaskRow";
import TaskPanel from "../components/TaskPanel";
import { DraftReview, createTaskFromDraft, parseDraft, TaskDraft } from "../components/CommandK";
import { AgentStatusBadge, Avatar, EmptyState, SectionTitle } from "../components/ui";

export default function TodayPage() {
  const { user, people, tasks, runs, events, addTask } = useHQ();
  const me = people.find((p) => p.id === user) ?? people[0];
  const [openTask, setOpenTask] = useState<string | null>(null);
  const [command, setCommand] = useState("");
  const [draft, setDraft] = useState<TaskDraft | null>(null);
  const [, setTick] = useState(0);

  // Live countdown.
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const dateStr = new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });

  const priorityRank = { urgent: 0, important: 1, normal: 2, later: 3 };

  const focus = useMemo(
    () =>
      tasks
        .filter((t) => t.owner === me.id && !["done", "cancelled"].includes(t.status))
        .sort((a, b) => priorityRank[a.priority] - priorityRank[b.priority] || (a.due ?? "z").localeCompare(b.due ?? "z"))
        .slice(0, 3),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tasks, me.id]
  );

  const needsYou = useMemo(() => {
    const items: { id: string; text: string; kind: string; href: string }[] = [];
    for (const r of runs) {
      if (r.status === "waiting_approval" && r.approval && !r.approval.decided) {
        items.push({ id: r.id, text: `${r.agent} — ${r.approval.action}`, kind: "Approval", href: `/hq/agents/${r.id}` });
      }
      if (r.status === "waiting_input" && r.question && !r.question.answered) {
        items.push({ id: `${r.id}-q`, text: `${r.agent} has a question on “${r.taskName}”`, kind: "Question", href: `/hq/agents/${r.id}` });
      }
    }
    for (const t of tasks) {
      if (t.status === "blocked") {
        const owner = people.find((p) => p.id === t.owner);
        items.push({ id: t.id, text: `${owner?.name ?? "Someone"} is blocked: ${t.title}`, kind: "Blocked", href: "/hq/work" });
      }
    }
    return items;
  }, [runs, tasks, people]);

  const inProgress = useMemo(() => {
    const humans = tasks.filter((t) => t.status === "in_progress");
    const liveRuns = runs.filter((r) => ["planning", "working", "verifying", "queued"].includes(r.status));
    return { humans, liveRuns };
  }, [tasks, runs]);

  const upcoming = useMemo(
    () =>
      events
        .filter((e) => new Date(e.end).getTime() > Date.now() && new Date(e.start).toDateString() === new Date().toDateString())
        .sort((a, b) => a.start.localeCompare(b.start)),
    [events]
  );
  const nextEvent = upcoming[0];

  const submitCommand = () => {
    if (command.trim().length < 3) return;
    setDraft(parseDraft(command.trim()));
  };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "28px 20px" }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 className="hq-serif" style={{ fontSize: 28 }}>
          {greeting}, {me.name}.
        </h1>
        <p style={{ color: "var(--hq-muted)", fontSize: 13, marginTop: 2 }}>{dateStr}</p>
        <div className="hq-no-print" style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <input
            className="hq-input"
            placeholder="Add a task or ask an agent."
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submitCommand(); }}
            aria-label="Command input"
          />
          <button className="hq-btn hq-btn-primary" onClick={submitCommand} disabled={command.trim().length < 3}>
            New task
          </button>
        </div>
      </div>

      {/* My focus */}
      <section style={{ marginBottom: 22 }}>
        <SectionTitle>My focus</SectionTitle>
        {focus.length > 0 ? (
          <div className="hq-card">
            {focus.map((t) => <TaskRow key={t.id} task={t} onOpen={setOpenTask} />)}
          </div>
        ) : (
          <EmptyState title="Nothing on your plate." hint="Pick something up from Work, or enjoy it while it lasts." />
        )}
      </section>

      {/* Needs you */}
      <section style={{ marginBottom: 22 }}>
        <SectionTitle>Needs you</SectionTitle>
        {needsYou.length > 0 ? (
          <div className="hq-card">
            {needsYou.map((n) => (
              <Link key={n.id} href={n.href} className="hq-row hq-row-click" style={{ textDecoration: "none", color: "inherit" }}>
                <span
                  className="hq-badge"
                  style={{ color: n.kind === "Blocked" ? "var(--hq-danger)" : "var(--hq-bronze)" }}
                >
                  {n.kind}
                </span>
                <span style={{ flex: 1, fontSize: 13.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.text}</span>
                <span style={{ color: "var(--hq-muted)", fontSize: 12 }}>→</span>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="Nothing needs your approval or decision right now." />
        )}
      </section>

      {/* In progress */}
      <section style={{ marginBottom: 22 }}>
        <SectionTitle right={<Link href="/hq/agents" style={{ fontSize: 12, color: "var(--hq-bronze)", textDecoration: "none" }}>All agents →</Link>}>
          In progress
        </SectionTitle>
        <div className="hq-card">
          {inProgress.liveRuns.map((r) => (
            <Link key={r.id} href={`/hq/agents/${r.id}`} className="hq-row hq-row-click" style={{ textDecoration: "none", color: "inherit" }}>
              <AgentStatusBadge status={r.status} />
              <span style={{ flex: 1, fontSize: 13.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.taskName}</span>
              <span className="hq-mono hq-pulse" style={{ color: "var(--hq-bronze)" }}>{r.liveStatus}</span>
            </Link>
          ))}
          {inProgress.humans.map((t) => <TaskRow key={t.id} task={t} onOpen={setOpenTask} compact />)}
          {inProgress.liveRuns.length === 0 && inProgress.humans.length === 0 && (
            <p style={{ padding: 14, fontSize: 13, color: "var(--hq-muted)" }}>Nothing running right now.</p>
          )}
        </div>
      </section>

      {/* Next on calendar */}
      <section style={{ marginBottom: 22 }}>
        <SectionTitle right={<Link href="/hq/calendar" className="hq-btn hq-btn-sm" style={{ textDecoration: "none" }}>Open calendar</Link>}>
          Next on calendar
        </SectionTitle>
        {nextEvent ? (
          <div className="hq-card">
            <div className="hq-row">
              <span className="hq-mono" style={{ color: "var(--hq-bronze)", minWidth: 68 }}>{fmtCountdown(nextEvent.start)}</span>
              <span style={{ flex: 1, fontWeight: 500, fontSize: 13.5 }}>{nextEvent.title}</span>
              <span className="hq-mono" style={{ color: "var(--hq-muted)" }}>{fmtTime(nextEvent.start)}</span>
            </div>
            {upcoming.slice(1, 5).map((e) => (
              <div key={e.id} className="hq-row">
                <span className="hq-mono" style={{ color: "var(--hq-muted)", minWidth: 68 }}>{fmtTime(e.start)}</span>
                <span style={{ flex: 1, fontSize: 13.5, color: "var(--hq-muted)" }}>{e.title}</span>
                <span className="hq-badge">{e.kind}</span>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="Nothing else on the calendar today." />
        )}
      </section>

      {/* Team */}
      <section>
        <SectionTitle>Team</SectionTitle>
        <div className="hq-card">
          {people.map((p) => {
            const blocked = tasks.some((t) => t.owner === p.id && t.status === "blocked");
            return (
              <Link key={p.id} href="/hq/people" className="hq-row hq-row-click" style={{ textDecoration: "none", color: "inherit" }}>
                <Avatar name={p.name} size={24} />
                <span style={{ fontWeight: 600, fontSize: 13.5, width: 46 }}>{p.name}</span>
                <span style={{ flex: 1, fontSize: 13, color: "var(--hq-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {p.focus}
                </span>
                {blocked && <span className="hq-badge" style={{ color: "var(--hq-danger)" }}>Blocked</span>}
              </Link>
            );
          })}
        </div>
      </section>

      {openTask && <TaskPanel taskId={openTask} onClose={() => setOpenTask(null)} />}
      {draft && (
        <DraftReview
          draft={draft}
          onCancel={() => setDraft(null)}
          onConfirm={(d) => {
            addTask(createTaskFromDraft(d));
            setDraft(null);
            setCommand("");
          }}
        />
      )}
    </div>
  );
}
