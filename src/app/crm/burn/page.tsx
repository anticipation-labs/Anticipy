"use client";

import { useEffect, useState } from "react";
import { Card, Empty, Money, Section } from "@/components/crm/ui";
import { crmFetch } from "@/lib/crm/userContext";

type BurnData = {
  monthCents: number;
  months: { month: string; cents: number }[];
  recurring: { vendor: string; avgCents: number; lastDate: string; status: string }[];
  top: { date: string; vendor: string; category: string; cents: number }[];
};

export default function BurnPage() {
  const [data, setData] = useState<BurnData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    crmFetch("/api/crm/burn")
      .then(async (r) => (r.ok ? r.json() : Promise.reject(await r.text())))
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <Empty title="Could not load burn." hint={error} />;
  if (!data) return <Empty title="Loading burn." />;

  return (
    <div>
      <Section title="Burn" subtitle="Auto-derived from expenses." />

      <Card style={{ marginBottom: 24 }}>
        <p
          style={{
            fontSize: 11,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-on-dark-muted)",
          }}
        >
          This month
        </p>
        <p style={{ fontFamily: "var(--font-serif)", fontSize: 80, lineHeight: 1, marginTop: 6 }}>
          <Money cents={data.monthCents} />
        </p>
      </Card>

      <Card style={{ marginBottom: 24 }}>
        <h3
          style={{
            fontSize: 11,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-on-dark-muted)",
            marginBottom: 12,
          }}
        >
          Trailing 12 months
        </h3>
        <BurnChart months={data.months} />
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
        <Card>
          <h3
            style={{
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--text-on-dark-muted)",
              marginBottom: 12,
            }}
          >
            Recurring subscriptions
          </h3>
          {data.recurring.length === 0 ? (
            <p style={{ color: "var(--text-on-dark-muted)", fontSize: 13 }}>
              None detected yet.
            </p>
          ) : (
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <thead style={{ color: "var(--text-on-dark-muted)" }}>
                <tr>
                  <th style={{ textAlign: "left", padding: 8 }}>Vendor</th>
                  <th style={{ textAlign: "right", padding: 8 }}>Avg</th>
                  <th style={{ textAlign: "left", padding: 8 }}>Last</th>
                  <th style={{ textAlign: "left", padding: 8 }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.recurring.map((r) => (
                  <tr key={r.vendor} style={{ borderTop: "1px solid var(--dark-border)" }}>
                    <td style={{ padding: 8 }}>{r.vendor}</td>
                    <td style={{ padding: 8, textAlign: "right" }}>
                      <Money cents={r.avgCents} />
                    </td>
                    <td style={{ padding: 8 }}>{r.lastDate}</td>
                    <td style={{ padding: 8, color: r.status.startsWith("silent") ? "var(--gold)" : "inherit" }}>
                      {r.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card>
          <h3
            style={{
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--text-on-dark-muted)",
              marginBottom: 12,
            }}
          >
            Top 10 this month
          </h3>
          {data.top.length === 0 ? (
            <p style={{ color: "var(--text-on-dark-muted)", fontSize: 13 }}>Nothing yet.</p>
          ) : (
            <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.top.map((t, i) => (
                <li
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "8px 0",
                    borderTop: i === 0 ? "none" : "1px solid var(--dark-border)",
                    fontSize: 13,
                  }}
                >
                  <span>
                    <span style={{ color: "var(--text-on-dark-muted)" }}>{t.date}</span>{" "}
                    {t.vendor}{" "}
                    <span style={{ color: "var(--text-on-dark-muted)" }}>({t.category})</span>
                  </span>
                  <span><Money cents={t.cents} /></span>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </div>
  );
}

function BurnChart({ months }: { months: { month: string; cents: number }[] }) {
  const max = Math.max(1, ...months.map((m) => m.cents));
  const w = 720;
  const h = 200;
  const px = w / Math.max(1, months.length - 1);
  const points = months.map((m, i) => {
    const x = i * px;
    const y = h - 16 - (m.cents / max) * (h - 32);
    return `${x},${y}`;
  });
  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="burnFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(200, 169, 126, 0.3)" />
            <stop offset="100%" stopColor="rgba(200, 169, 126, 0)" />
          </linearGradient>
        </defs>
        <polyline
          points={`0,${h - 16} ${points.join(" ")} ${w},${h - 16}`}
          fill="url(#burnFill)"
          stroke="none"
        />
        <polyline points={points.join(" ")} fill="none" stroke="#C8A97E" strokeWidth={2} />
        {months.map((m, i) => (
          <g key={m.month}>
            <text
              x={i * px}
              y={h - 2}
              fontSize="10"
              textAnchor="middle"
              fill="rgba(255,255,255,0.4)"
            >
              {m.month.slice(5)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
