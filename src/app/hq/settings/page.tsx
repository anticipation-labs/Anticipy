"use client";

import { useState } from "react";
import { useHQ } from "../lib/store";
import { SectionTitle, SavedDot, useSaved } from "../components/ui";

interface Integration {
  name: string;
  detail: string;
  connected: boolean;
}

const INTEGRATIONS: Integration[] = [
  { name: "Google Calendar", detail: "team@anticipy.ai · events sync both ways", connected: true },
  { name: "Email", detail: "Sends reminders and agent receipts from hq@anticipy.ai", connected: true },
  { name: "SMS (Twilio)", detail: "+1 (415) ···· ··82 · reminders and escalations", connected: true },
  { name: "Claude", detail: "Claude Code agent runs · key ends in ···9f4", connected: true },
  { name: "Browser agent", detail: "Runs on the local engine · CDP :9222", connected: true },
  { name: "OpenRouter", detail: "Fallback models for research and drafting", connected: false },
  { name: "GitHub", detail: "anticipy/engine, anticipy/desktop, anticipy/website", connected: true },
];

const SECURITY_LOG = [
  { at: "Today 9:41 AM", text: "Omar approved agent PR for onboarding permission fix" },
  { at: "Today 8:12 AM", text: "Ari signed in from a new device (MacBook, Lisbon)" },
  { at: "Yesterday 6:30 PM", text: "Agent budget for Research agent raised to $5 per run" },
  { at: "Yesterday 2:04 PM", text: "External email to Alta Manufacturing approved by Jose" },
  { at: "Mon 11:15 AM", text: "SMS reminders enabled for hardware deadlines" },
];

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      style={{
        width: 34, height: 20, borderRadius: 10, border: "1px solid var(--hq-border)",
        background: on ? "var(--hq-bronze)" : "var(--hq-surface)",
        position: "relative", cursor: "pointer", transition: "background 140ms ease", flexShrink: 0,
      }}
    >
      <span
        style={{
          position: "absolute", top: 2, left: on ? 15 : 2, width: 14, height: 14,
          borderRadius: "50%", background: "#fff", border: "1px solid var(--hq-border)",
          transition: "left 140ms ease",
        }}
      />
    </button>
  );
}

export default function SettingsPage() {
  const { user, people, setWalkthroughDone, setUnlocked, setUser } = useHQ();
  const me = people.find((p) => p.id === user);
  const [saved, flash] = useSaved();

  const [prefs, setPrefs] = useState({
    mentions: true,
    dueSoon: true,
    agentResults: true,
    approvalsSms: true,
    calendar: true,
    quietHours: false,
  });
  const [timezone, setTimezone] = useState("Europe/Lisbon");
  const [budget, setBudget] = useState("10");
  const [timeLimit, setTimeLimit] = useState("60");
  const [connections, setConnections] = useState(INTEGRATIONS);
  const [showLog, setShowLog] = useState(false);

  const setPref = (k: keyof typeof prefs) => (v: boolean) => {
    setPrefs((p) => ({ ...p, [k]: v }));
    flash();
  };

  return (
    <div style={{ maxWidth: 680, margin: "0 auto", padding: "24px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, flex: 1 }}>Settings</h1>
        <SavedDot visible={saved} />
      </div>

      <section style={{ marginBottom: 24 }}>
        <SectionTitle>Integrations</SectionTitle>
        <div className="hq-card">
          {connections.map((c, i) => (
            <div key={c.name} className="hq-row">
              <span className="hq-dot" style={{ background: c.connected ? "var(--hq-success)" : "var(--hq-border)" }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 13.5, fontWeight: 500 }}>{c.name}</p>
                <p style={{ fontSize: 12, color: "var(--hq-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.detail}</p>
              </div>
              <button
                className="hq-btn hq-btn-sm"
                onClick={() => {
                  setConnections((arr) => arr.map((x, j) => (j === i ? { ...x, connected: !x.connected } : x)));
                  flash();
                }}
              >
                {c.connected ? "Disconnect" : "Connect"}
              </button>
            </div>
          ))}
        </div>
        <p style={{ fontSize: 12, color: "var(--hq-muted)", marginTop: 6 }}>
          Keys are stored encrypted and never shown here.
        </p>
      </section>

      <section style={{ marginBottom: 24 }}>
        <SectionTitle>Notifications{me ? ` · ${me.name}` : ""}</SectionTitle>
        <div className="hq-card" style={{ padding: "4px 0" }}>
          {(
            [
              ["mentions", "Mentions and comments"],
              ["dueSoon", "Tasks due soon and overdue"],
              ["agentResults", "Agent completions and failures"],
              ["approvalsSms", "Approval requests also by SMS"],
              ["calendar", "Calendar reminders"],
              ["quietHours", "Quiet hours (10 PM – 8 AM, escalations only)"],
            ] as const
          ).map(([key, label]) => (
            <div key={key} className="hq-row">
              <span style={{ flex: 1, fontSize: 13.5 }}>{label}</span>
              <Toggle on={prefs[key]} onChange={setPref(key)} label={label} />
            </div>
          ))}
          <div className="hq-row">
            <span style={{ flex: 1, fontSize: 13.5 }}>Timezone</span>
            <select className="hq-input" style={{ width: "auto" }} value={timezone} onChange={(e) => { setTimezone(e.target.value); flash(); }}>
              <option>Europe/Lisbon</option>
              <option>America/New_York</option>
              <option>America/Los_Angeles</option>
              <option>Asia/Dubai</option>
            </select>
          </div>
        </div>
      </section>

      <section style={{ marginBottom: 24 }}>
        <SectionTitle>Agent defaults</SectionTitle>
        <div className="hq-card" style={{ padding: "4px 0" }}>
          <div className="hq-row">
            <span style={{ flex: 1, fontSize: 13.5 }}>Default budget per run</span>
            <span className="hq-mono" style={{ color: "var(--hq-muted)" }}>$</span>
            <input className="hq-input" style={{ width: 70 }} value={budget} onChange={(e) => { setBudget(e.target.value); flash(); }} inputMode="decimal" aria-label="Default budget in dollars" />
          </div>
          <div className="hq-row">
            <span style={{ flex: 1, fontSize: 13.5 }}>Default time limit</span>
            <input className="hq-input" style={{ width: 70 }} value={timeLimit} onChange={(e) => { setTimeLimit(e.target.value); flash(); }} inputMode="numeric" aria-label="Default time limit in minutes" />
            <span className="hq-mono" style={{ color: "var(--hq-muted)" }}>min</span>
          </div>
          <div className="hq-row">
            <span style={{ flex: 1, fontSize: 13.5 }}>Always require approval for</span>
            <span style={{ fontSize: 12.5, color: "var(--hq-muted)", textAlign: "right" }}>
              External email · Deploys · Spending money · Deleting data
            </span>
          </div>
        </div>
        <p style={{ fontSize: 12, color: "var(--hq-muted)", marginTop: 6 }}>
          These limits are enforced in code, not by the agent.
        </p>
      </section>

      <section style={{ marginBottom: 24 }}>
        <SectionTitle
          right={
            <button className="hq-btn hq-btn-sm" onClick={() => setShowLog((v) => !v)}>
              {showLog ? "Hide" : "Show"}
            </button>
          }
        >
          Activity & security log
        </SectionTitle>
        {showLog && (
          <div className="hq-card hq-fade-in">
            {SECURITY_LOG.map((e) => (
              <div key={e.text} className="hq-row">
                <span style={{ flex: 1, fontSize: 13 }}>{e.text}</span>
                <span className="hq-mono" style={{ color: "var(--hq-muted)", flexShrink: 0 }}>{e.at}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <SectionTitle>Workspace</SectionTitle>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="hq-btn" onClick={() => setWalkthroughDone(false)}>Restart walkthrough</button>
          <button
            className="hq-btn"
            onClick={() => {
              setUser(null);
              setUnlocked(false);
            }}
          >
            Lock workspace
          </button>
        </div>
      </section>
    </div>
  );
}
