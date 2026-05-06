import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const db = crmDb();

  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const oneYearAgo = new Date(today.getFullYear() - 1, today.getMonth(), 1);

  const { data: yearRows, error: yearErr } = await db
    .from("crm_expenses")
    .select("date, amount_cents, vendor_id, category, notes, currency, vendor:crm_vendors(name)")
    .gte("date", oneYearAgo.toISOString().slice(0, 10));
  if (yearErr) return NextResponse.json({ error: yearErr.message }, { status: 500 });

  const monthBuckets: Record<string, number> = {};
  for (let i = 0; i < 12; i++) {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
    monthBuckets[d.toISOString().slice(0, 7)] = 0;
  }
  let monthCents = 0;
  for (const r of yearRows ?? []) {
    if (!(r as any).date) continue;
    const month = String((r as any).date).slice(0, 7);
    if (month in monthBuckets) {
      monthBuckets[month] += (r as any).amount_cents || 0;
    }
    if ((r as any).date >= monthStart.toISOString().slice(0, 10)) {
      monthCents += (r as any).amount_cents || 0;
    }
  }

  // Recurring software subscriptions: vendors with category=software_subscription
  // and 2+ expenses in the last 90 days.
  const ninety = new Date(today.getTime() - 90 * 86400 * 1000)
    .toISOString()
    .slice(0, 10);
  const { data: subs } = await db
    .from("crm_expenses")
    .select("vendor_id, amount_cents, date, vendor:crm_vendors(name)")
    .eq("category", "software_subscription")
    .gte("date", ninety);
  type Vendor = { vendorId: string; name: string; amounts: number[]; lastDate: string };
  const byVendor = new Map<string, Vendor>();
  for (const r of subs ?? []) {
    const id = (r as any).vendor_id as string | null;
    if (!id) continue;
    const v: Vendor = byVendor.get(id) ?? {
      vendorId: id,
      name: (r as any).vendor?.name || "Unknown",
      amounts: [],
      lastDate: "",
    };
    v.amounts.push((r as any).amount_cents || 0);
    if (!v.lastDate || (r as any).date > v.lastDate) v.lastDate = (r as any).date;
    byVendor.set(id, v);
  }
  const recurring = Array.from(byVendor.values())
    .filter((v) => v.amounts.length >= 2)
    .map((v) => {
      const avg = Math.round(v.amounts.reduce((a, b) => a + b, 0) / v.amounts.length);
      const lastDate = v.lastDate;
      const daysSince = Math.floor(
        (Date.now() - new Date(lastDate).getTime()) / (86400 * 1000)
      );
      return {
        vendor: v.name,
        avgCents: avg,
        lastDate,
        status: daysSince > 35 ? `silent ${daysSince}d` : "active",
      };
    })
    .sort((a, b) => b.avgCents - a.avgCents);

  // Top 10 line items this month.
  const top = (yearRows ?? [])
    .filter((r: any) => (r.date || "") >= monthStart.toISOString().slice(0, 10))
    .map((r: any) => ({
      date: r.date,
      vendor: r.vendor?.name || "—",
      category: r.category,
      cents: r.amount_cents || 0,
    }))
    .sort((a, b) => b.cents - a.cents)
    .slice(0, 10);

  return NextResponse.json({
    monthCents,
    months: Object.entries(monthBuckets)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => ({ month: k, cents: v })),
    recurring,
    top,
  });
}
