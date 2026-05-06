"use client";

import { useEffect, useState } from "react";
import { Badge, Card, Empty, Input, Section } from "@/components/crm/ui";
import { crmFetch } from "@/lib/crm/userContext";

export default function FeedPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [agents, setAgents] = useState<string[]>([]);
  const [agent, setAgent] = useState<string>("");
  const [search, setSearch] = useState("");

  async function load() {
    const qs = new URLSearchParams();
    if (agent) qs.set("agent", agent);
    if (search) qs.set("q", search);
    const r = await crmFetch(`/api/crm/feed?${qs}`);
    const j = await r.json();
    setEvents(j.events || []);
    setAgents(j.agents || []);
  }
  useEffect(() => { load(); }, [agent, search]);

  return (
    <div>
      <Section
        title="Agent feed"
        subtitle="Every meaningful action by every agent. Read-only here. Agents POST to /api/log to write."
        right={
          <Input
            placeholder="Search summary."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 240 }}
          />
        }
      />

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
        <button onClick={() => setAgent("")} style={chip(agent === "")}>all agents</button>
        {agents.map((a) => (
          <button key={a} onClick={() => setAgent(a)} style={chip(agent === a)}>
            {a}
          </button>
        ))}
      </div>

      {events.length === 0 ? (
        <Empty title="No events yet." hint="Agents will post here as they work." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {events.map((e) => (
            <Card key={e.id}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                <div>
                  <Badge>{e.agent_name}</Badge>{" "}
                  <span style={{ color: "var(--text-on-dark-muted)", fontSize: 12 }}>{e.action}</span>
                  <p style={{ marginTop: 6, fontSize: 14 }}>{e.summary}</p>
                </div>
                <span style={{ fontSize: 12, color: "var(--text-on-dark-muted)" }}>
                  {new Date(e.created_at).toLocaleString()}
                </span>
              </div>
              {e.payload_jsonb && (
                <details style={{ marginTop: 10 }}>
                  <summary style={{ cursor: "pointer", color: "var(--text-on-dark-muted)", fontSize: 12 }}>
                    payload
                  </summary>
                  <pre
                    style={{
                      fontSize: 12,
                      marginTop: 6,
                      padding: 12,
                      background: "var(--dark)",
                      border: "1px solid var(--dark-border)",
                      borderRadius: 8,
                      overflowX: "auto",
                    }}
                  >
                    {JSON.stringify(e.payload_jsonb, null, 2)}
                  </pre>
                </details>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function chip(active: boolean): React.CSSProperties {
  return {
    padding: "6px 12px",
    borderRadius: 999,
    background: active ? "var(--cream)" : "var(--dark-elevated)",
    color: active ? "var(--dark)" : "var(--text-on-dark-muted)",
    border: "1px solid var(--dark-border)",
    fontSize: 12,
    cursor: "pointer",
  };
}
