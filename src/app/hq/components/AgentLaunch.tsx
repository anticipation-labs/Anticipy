"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useHQ } from "../lib/store";
import type { AgentRun, AgentType, PersonId, Task } from "../lib/types";
import { Modal } from "./ui";

const AGENTS: AgentType[] = [
  "Claude Code",
  "Browser agent",
  "Research agent",
  "Growth agent",
  "General AI",
];

const PERMISSIONS = [
  "Read the repository",
  "Run tests",
  "Browse the web",
  "Draft emails (never send)",
  "Create files in the workspace",
];

const APPROVAL_ACTIONS = [
  "Send external email",
  "Deploy",
  "Spend money",
  "Delete or overwrite data",
];

export default function AgentLaunch({
  task,
  onClose,
}: {
  task: Task | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const { user, addRun, updateTask, logActivity } = useHQ();
  const [agent, setAgent] = useState<AgentType>("Claude Code");
  const [instructions, setInstructions] = useState(task ? task.title : "");
  const [expected, setExpected] = useState(task?.outcome ?? "");
  const [workspace, setWorkspace] = useState("github.com/omize10/Anticipy");
  const [context, setContext] = useState("");
  const [budget, setBudget] = useState(5);
  const [timeLimit, setTimeLimit] = useState(60);
  const [perms, setPerms] = useState<string[]>(["Read the repository", "Run tests"]);
  const [approvals, setApprovals] = useState<string[]>([...APPROVAL_ACTIONS]);
  const [responsible, setResponsible] = useState<PersonId>(user ?? "omar");
  const [makePr, setMakePr] = useState(true);
  const [verification, setVerification] = useState("Tests must pass; show the diff and test output as proof.");

  const summary =
    `${agent} will ${instructions.trim() ? instructions.trim().replace(/\.$/, "").toLowerCase() : "work on this task"}` +
    `${workspace ? ` in ${workspace}` : ""}, keep within $${budget} and ${timeLimit} minutes` +
    `${makePr ? ", and open a pull request" : ""}. ` +
    `It cannot ${approvals.length ? approvals.map((a) => a.toLowerCase()).join(", ") : "take risky actions"} without ${responsible[0].toUpperCase() + responsible.slice(1)}.`;

  const launch = () => {
    const id = `run-new-${Date.now()}`;
    const run: AgentRun = {
      id,
      taskId: task?.id ?? null,
      taskName: instructions.trim() || task?.title || "Untitled run",
      agent,
      requester: user ?? "omar",
      startedAt: new Date().toISOString(),
      runtimeMin: 0,
      tokens: 0,
      costUsd: 0,
      status: "queued",
      liveStatus: "Queued",
      budgetUsd: budget,
      timeLimitMin: timeLimit,
      steps: [
        { id: `${id}-s1`, label: "Queued", detail: "Waiting for a worker", at: new Date().toISOString(), state: "active" },
      ],
      question: null,
      approval: null,
      proof: null,
    };
    addRun(run);
    if (task) {
      updateTask(task.id, { agentRunId: id, status: "in_progress" });
      logActivity(task.id, `Launched ${agent}`);
    }
    onClose();
    router.push(`/hq/agents/${id}`);
  };

  const toggle = (list: string[], set: (v: string[]) => void, item: string) => {
    set(list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);
  };

  return (
    <Modal onClose={onClose} label="Run with agent" width={640}>
      <div style={{ padding: 18 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 2 }}>Run with agent</h2>
        {task && <p style={{ color: "var(--hq-muted)", fontSize: 12.5, marginBottom: 12 }}>For task: {task.title}</p>}

        <label className="hq-label">Agent</label>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
          {AGENTS.map((a) => (
            <button
              key={a}
              className="hq-btn hq-btn-sm"
              style={agent === a ? { borderColor: "#111", background: "#111", color: "#fff" } : undefined}
              onClick={() => setAgent(a)}
            >
              {a}
            </button>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="hq-label">Instructions</label>
            <textarea className="hq-input" rows={2} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="hq-label">Expected result</label>
            <input className="hq-input" value={expected} onChange={(e) => setExpected(e.target.value)} placeholder="What does done look like?" />
          </div>
          <div>
            <label className="hq-label">Repository / website / workspace</label>
            <input className="hq-input hq-mono" value={workspace} onChange={(e) => setWorkspace(e.target.value)} />
          </div>
          <div>
            <label className="hq-label">Context & attachments</label>
            <input className="hq-input" value={context} onChange={(e) => setContext(e.target.value)} placeholder="Links, notes, files…" />
          </div>
          <div>
            <label className="hq-label">Budget (USD)</label>
            <input type="number" min={1} className="hq-input hq-mono" value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
          <div>
            <label className="hq-label">Time limit (minutes)</label>
            <input type="number" min={5} className="hq-input hq-mono" value={timeLimit} onChange={(e) => setTimeLimit(Number(e.target.value))} />
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 14 }}>
          <div>
            <label className="hq-label">Permissions</label>
            {PERMISSIONS.map((p) => (
              <label key={p} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "3px 0", cursor: "pointer" }}>
                <input type="checkbox" checked={perms.includes(p)} onChange={() => toggle(perms, setPerms, p)} style={{ accentColor: "var(--hq-bronze)" }} />
                {p}
              </label>
            ))}
          </div>
          <div>
            <label className="hq-label">Requires approval</label>
            {APPROVAL_ACTIONS.map((a) => (
              <label key={a} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "3px 0", cursor: "pointer" }}>
                <input type="checkbox" checked={approvals.includes(a)} onChange={() => toggle(approvals, setApprovals, a)} style={{ accentColor: "var(--hq-bronze)" }} />
                {a}
              </label>
            ))}
          </div>
          <div>
            <label className="hq-label">Answers questions</label>
            <select className="hq-input" value={responsible} onChange={(e) => setResponsible(e.target.value as PersonId)}>
              <option value="omar">Omar</option>
              <option value="ari">Ari</option>
              <option value="jose">Jose</option>
            </select>
          </div>
          <div>
            <label className="hq-label">Code changes</label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "6px 0", cursor: "pointer" }}>
              <input type="checkbox" checked={makePr} onChange={() => setMakePr((v) => !v)} style={{ accentColor: "var(--hq-bronze)" }} />
              Create a branch and pull request
            </label>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="hq-label">Verification requirements</label>
            <input className="hq-input" value={verification} onChange={(e) => setVerification(e.target.value)} />
          </div>
        </div>

        <div className="hq-card" style={{ background: "var(--hq-surface)", padding: "10px 14px", marginTop: 16, fontSize: 13, lineHeight: 1.55 }}>
          {summary}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button className="hq-btn" onClick={onClose}>Cancel</button>
          <button className="hq-btn hq-btn-primary" onClick={launch} disabled={!instructions.trim()}>
            Launch agent
          </button>
        </div>
      </div>
    </Modal>
  );
}
