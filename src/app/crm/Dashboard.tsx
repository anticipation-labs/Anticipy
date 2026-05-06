"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, Money, Empty, Badge } from "@/components/crm/ui";
import { crmFetch, readPickedUser } from "@/lib/crm/userContext";

type DashData = {
  myTodos: { id: string; title: string; due_date: string | null; status: string; priority: string | null }[];
  sharedTodos: { id: string; title: string; due_date: string | null; status: string; priority: string | null }[];
  events: { id: string; agent_name: string; action: string; summary: string; created_at: string }[];
  burnCents: number;
  todayMemo: { id: string; transcript: string | null; duration_seconds: number | null } | null;
  pendingReviewCount: number;
};

export function Dashboard() {
  const [data, setData] = useState<DashData | null>(null);
  const [error, setError] = useState("");
  const user = typeof window !== "undefined" ? readPickedUser() : null;

  useEffect(() => {
    crmFetch("/api/crm/dashboard")
      .then(async (r) => {
        if (!r.ok) throw new Error("Failed");
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <Empty title="Could not load dashboard" hint={error} />;
  }

  return (
    <div>
      <header style={{ marginBottom: 32 }}>
        <p
          style={{
            fontSize: 11,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-on-dark-muted)",
          }}
        >
          {new Date().toLocaleDateString("en-CA", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
        <h1
          style={{
            fontFamily: "var(--font-serif)",
            fontSize: "clamp(40px, 6vw, 64px)",
            lineHeight: 1.05,
            marginTop: 4,
          }}
        >
          Hi, {user?.name ?? "friend"}.
        </h1>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 16,
        }}
      >
        <Card>
          <Heading>Voice memo</Heading>
          <Sub>{data?.todayMemo ? "Recorded today." : "No memo today."}</Sub>
          {data?.todayMemo?.transcript && (
            <p style={{ fontSize: 14, marginTop: 12, lineHeight: 1.6 }}>
              {data.todayMemo.transcript.slice(0, 220)}
              {data.todayMemo.transcript.length > 220 ? "." : ""}
            </p>
          )}
          <Link
            href="/crm/voice"
            style={{
              marginTop: 14,
              display: "inline-block",
              padding: "10px 16px",
              borderRadius: 10,
              background: "var(--cream)",
              color: "var(--dark)",
              textDecoration: "none",
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            {data?.todayMemo ? "Open voice" : "Record memo"}
          </Link>
        </Card>

        <Card>
          <Heading>New expense</Heading>
          <Sub>Drag a receipt or use your phone camera.</Sub>
          <Link
            href="/crm/expenses?new=1"
            style={{
              marginTop: 14,
              display: "inline-block",
              padding: "10px 16px",
              borderRadius: 10,
              background: "var(--cream)",
              color: "var(--dark)",
              textDecoration: "none",
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            Add expense
          </Link>
          {data && data.pendingReviewCount > 0 && (
            <p style={{ marginTop: 12, fontSize: 12, color: "var(--gold)" }}>
              {data.pendingReviewCount} pending review.
            </p>
          )}
        </Card>

        <Card>
          <Heading>Burn this month</Heading>
          <p
            style={{
              fontFamily: "var(--font-serif)",
              fontSize: 44,
              marginTop: 8,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            <Money cents={data?.burnCents ?? 0} />
          </p>
          <Link
            href="/crm/burn"
            style={{
              marginTop: 8,
              display: "inline-block",
              fontSize: 13,
              color: "var(--text-on-dark-muted)",
              textDecoration: "none",
            }}
          >
            Open burn page
          </Link>
        </Card>

        <Card>
          <Heading>Your todos</Heading>
          <TodoList items={data?.myTodos ?? []} fallback="Nothing assigned to you." />
        </Card>

        <Card>
          <Heading>Shared todos</Heading>
          <TodoList items={data?.sharedTodos ?? []} fallback="No shared work right now." />
        </Card>

        <Card>
          <Heading>Recent agent events</Heading>
          {!data || data.events.length === 0 ? (
            <Sub>No agent activity yet.</Sub>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: "10px 0 0", display: "flex", flexDirection: "column", gap: 10 }}>
              {data.events.map((e) => (
                <li key={e.id} style={{ fontSize: 13, lineHeight: 1.5 }}>
                  <Badge>{e.agent_name}</Badge>{" "}
                  <span style={{ color: "var(--text-on-dark)" }}>{e.summary}</span>
                  <span style={{ display: "block", color: "var(--text-on-dark-muted)", fontSize: 11, marginTop: 2 }}>
                    {new Date(e.created_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h3
      style={{
        fontSize: 11,
        letterSpacing: "0.15em",
        textTransform: "uppercase",
        color: "var(--text-on-dark-muted)",
        marginBottom: 6,
      }}
    >
      {children}
    </h3>
  );
}

function Sub({ children }: { children: React.ReactNode }) {
  return <p style={{ color: "var(--text-on-dark-muted)", fontSize: 13 }}>{children}</p>;
}

function TodoList({
  items,
  fallback,
}: {
  items: { id: string; title: string; due_date: string | null; priority: string | null }[];
  fallback: string;
}) {
  if (items.length === 0) return <Sub>{fallback}</Sub>;
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: "10px 0 0", display: "flex", flexDirection: "column", gap: 8 }}>
      {items.map((t) => (
        <li key={t.id} style={{ fontSize: 14 }}>
          <Link href={`/crm/todos?focus=${t.id}`} style={{ color: "var(--text-on-dark)", textDecoration: "none" }}>
            {t.title}
          </Link>
          {t.due_date && (
            <span style={{ color: "var(--text-on-dark-muted)", marginLeft: 8, fontSize: 12 }}>
              {new Date(t.due_date).toLocaleDateString()}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
