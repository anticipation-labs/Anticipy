"use client";

import { useEffect, useMemo, useState } from "react";
import { useHQ } from "../lib/store";
import { fmtCountdown, fmtTime } from "../lib/format";
import { Avatar, EmptyState } from "../components/ui";
import type { CalendarEvent } from "../lib/types";

const KIND_LABEL: Record<CalendarEvent["kind"], string> = {
  meeting: "Meeting",
  focus: "Focus",
  deadline: "Deadline",
  agent: "Agent deadline",
  prep: "Prep",
  followup: "Follow-up",
};

const KIND_COLOR: Record<CalendarEvent["kind"], string> = {
  meeting: "var(--hq-bronze)",
  focus: "var(--hq-success)",
  deadline: "var(--hq-danger)",
  agent: "var(--hq-gold)",
  prep: "var(--hq-muted)",
  followup: "var(--hq-muted)",
};

export default function CalendarPage() {
  const { events, people } = useHQ();
  const [mode, setMode] = useState<"Day" | "Week">("Day");
  const [, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const next = useMemo(
    () => [...events].filter((e) => new Date(e.start).getTime() > Date.now()).sort((a, b) => a.start.localeCompare(b.start))[0],
    [events]
  );

  const days = useMemo(() => {
    const n = mode === "Day" ? 1 : 7;
    const out: { label: string; items: CalendarEvent[] }[] = [];
    for (let i = 0; i < n; i++) {
      const d = new Date();
      d.setDate(d.getDate() + i);
      out.push({
        label: i === 0 ? "Today" : i === 1 ? "Tomorrow" : d.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" }),
        items: events
          .filter((e) => new Date(e.start).toDateString() === d.toDateString())
          .sort((a, b) => a.start.localeCompare(b.start)),
      });
    }
    return out;
  }, [events, mode]);

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "24px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, marginRight: "auto" }}>Calendar</h1>
        {next && (
          <span className="hq-mono" style={{ color: "var(--hq-bronze)" }}>
            {next.title.slice(0, 34)} {fmtCountdown(next.start)}
          </span>
        )}
        <div className="hq-no-print" style={{ display: "flex", border: "1px solid var(--hq-border)", borderRadius: 8, overflow: "hidden" }}>
          {(["Day", "Week"] as const).map((m) => (
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
      </div>
      <p style={{ fontSize: 12.5, color: "var(--hq-muted)", marginBottom: 18 }}>
        Google Calendar events, task deadlines, and scheduled focus work. Tasks only land here when you deliberately schedule them.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {days.map((day) => (
          <section key={day.label}>
            <p className="hq-label">{day.label}</p>
            {day.items.length > 0 ? (
              <div className="hq-card">
                {day.items.map((e) => (
                  <div key={e.id} className="hq-row">
                    <span className="hq-mono" style={{ minWidth: 70, color: "var(--hq-muted)" }}>
                      {fmtTime(e.start)}
                    </span>
                    <span className="hq-dot" style={{ background: KIND_COLOR[e.kind] }} />
                    <span style={{ flex: 1, fontSize: 13.5, fontWeight: 500 }}>{e.title}</span>
                    <span className="hq-badge" data-hq-hide-sm>{KIND_LABEL[e.kind]}</span>
                    {e.source === "google" && <span className="hq-mono" style={{ color: "var(--hq-muted)" }} data-hq-hide-sm>gcal</span>}
                    <span style={{ display: "flex", gap: 2 }}>
                      {e.attendees?.map((a) => {
                        const p = people.find((x) => x.id === a);
                        return p ? <Avatar key={a} name={p.name} size={18} /> : null;
                      })}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="Nothing scheduled." hint="Use “Schedule” on a task to place focus time here." />
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
