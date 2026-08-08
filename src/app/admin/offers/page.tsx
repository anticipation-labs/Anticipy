"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

interface Tier {
  tier_key: string;
  label: string;
  sort_order: number;
  amount_off_cents: number;
  stripe_coupon_id: string | null;
  headline: string;
  subhead: string | null;
  min_intent_score: number;
  max_intent_score: number | null;
  min_friction_score: number;
  active: boolean;
  max_redemptions: number | null;
  redemption_count: number;
}

type Stats = Record<string, { shown: number; accepted: number; dismissed: number }>;

export default function OffersAdmin() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [stats, setStats] = useState<Stats>({});
  const [listPrice, setListPrice] = useState(14999);
  const [floorPrice, setFloorPrice] = useState(10999);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      const t = data.session?.access_token ?? null;
      if (!t) router.push("/admin/login");
      else setToken(t);
    });
  }, [router]);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    const res = await fetch("/api/admin/offers", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const d = await res.json();
      setTiers(d.tiers);
      setStats(d.stats ?? {});
      setListPrice(d.listPriceCents);
      setFloorPrice(d.floorPriceCents);
    }
    setLoading(false);
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const patch = async (tierKey: string, body: Record<string, unknown>) => {
    setMsg(null);
    const res = await fetch("/api/admin/offers", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ tierKey, ...body }),
    });
    const d = await res.json();
    setMsg(res.ok ? `${tierKey} updated.` : `${tierKey}: ${d.error}`);
    if (res.ok) void load();
  };

  const syncStripe = async () => {
    setMsg("Creating Stripe coupons…");
    const res = await fetch("/api/admin/offers", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    const d = await res.json();
    setMsg(
      res.ok
        ? `Synced ${d.results.filter((r: { coupon: string | null }) => r.coupon).length} coupons.`
        : `Sync failed: ${d.error}`
    );
    void load();
  };

  // Realized median assumes an even spread across active tiers. The true
  // number depends on how traffic actually distributes, which only the
  // offer_events log can answer.
  const activeTiers = tiers.filter((t) => t.active);
  const prices = activeTiers.map((t) => listPrice - t.amount_off_cents).sort((a, b) => a - b);
  const median = prices.length
    ? prices[Math.floor(prices.length / 2)]
    : listPrice;

  const money = (c: number) => `$${(c / 100).toFixed(2)}`;

  if (loading) return <main style={{ padding: 40, color: "#888" }}>Loading…</main>;

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#0C0C0C",
        color: "#FAFAFA",
        padding: "40px 28px",
        fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <h1 style={{ fontSize: 26, margin: "0 0 6px" }}>Discount ladder</h1>
        <p style={{ color: "#8A8A8A", fontSize: 14, margin: "0 0 24px" }}>
          List {money(listPrice)} · floor {money(floorPrice)} · median of active tiers{" "}
          <strong style={{ color: "#C8A97E" }}>{money(median)}</strong>
        </p>

        <button
          onClick={syncStripe}
          style={{
            background: "#C8A97E",
            color: "#0C0C0C",
            border: "none",
            borderRadius: 100,
            padding: "10px 22px",
            fontWeight: 600,
            cursor: "pointer",
            marginBottom: 18,
          }}
        >
          Sync Stripe coupons
        </button>

        {msg && (
          <p style={{ color: "#C8A97E", fontSize: 13, margin: "0 0 16px" }}>{msg}</p>
        )}

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "#8A8A8A", textAlign: "left" }}>
                <th style={{ padding: "8px 10px" }}>Tier</th>
                <th style={{ padding: "8px 10px" }}>Price</th>
                <th style={{ padding: "8px 10px" }}>$ off</th>
                <th style={{ padding: "8px 10px" }}>Intent</th>
                <th style={{ padding: "8px 10px" }}>Coupon</th>
                <th style={{ padding: "8px 10px" }}>Shown</th>
                <th style={{ padding: "8px 10px" }}>Took</th>
                <th style={{ padding: "8px 10px" }}>Rate</th>
                <th style={{ padding: "8px 10px" }}>Live</th>
              </tr>
            </thead>
            <tbody>
              {tiers.map((t) => {
                const s = stats[t.tier_key] ?? { shown: 0, accepted: 0, dismissed: 0 };
                const rate = s.shown ? ((s.accepted / s.shown) * 100).toFixed(1) : "—";
                return (
                  <tr key={t.tier_key} style={{ borderTop: "1px solid #1F1F1F" }}>
                    <td style={{ padding: "10px" }}>
                      <strong>{t.tier_key}</strong>
                      <div style={{ color: "#6A6A6A", fontSize: 11 }}>{t.label}</div>
                    </td>
                    <td style={{ padding: "10px", color: "#C8A97E", fontWeight: 600 }}>
                      {money(listPrice - t.amount_off_cents)}
                    </td>
                    <td style={{ padding: "10px" }}>
                      <input
                        type="number"
                        defaultValue={t.amount_off_cents}
                        onBlur={(e) => {
                          const v = Number(e.target.value);
                          if (v !== t.amount_off_cents) patch(t.tier_key, { amountOffCents: v });
                        }}
                        style={{
                          width: 78,
                          background: "#161616",
                          border: "1px solid #2A2A2A",
                          color: "#FAFAFA",
                          borderRadius: 6,
                          padding: "5px 7px",
                        }}
                      />
                    </td>
                    <td style={{ padding: "10px", color: "#8A8A8A" }}>
                      {t.min_intent_score}
                      {t.max_intent_score == null ? "+" : `–${t.max_intent_score}`}
                    </td>
                    <td
                      style={{
                        padding: "10px",
                        fontFamily: "monospace",
                        fontSize: 11,
                        color: t.stripe_coupon_id ? "#6A6A6A" : "#C86A6A",
                      }}
                    >
                      {t.stripe_coupon_id ?? "not synced"}
                    </td>
                    <td style={{ padding: "10px" }}>{s.shown}</td>
                    <td style={{ padding: "10px" }}>{s.accepted}</td>
                    <td style={{ padding: "10px", color: "#C8A97E" }}>{rate}%</td>
                    <td style={{ padding: "10px" }}>
                      <input
                        type="checkbox"
                        checked={t.active}
                        onChange={(e) => patch(t.tier_key, { active: e.target.checked })}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <p style={{ color: "#5A5A5A", fontSize: 12, marginTop: 22, lineHeight: 1.6 }}>
          Editing a $ off value re-creates its Stripe coupon automatically. Values
          above {money(listPrice - floorPrice)} are rejected rather than clamped, so a
          mistyped amount fails loudly instead of quietly selling below the floor.
        </p>
      </div>
    </main>
  );
}
