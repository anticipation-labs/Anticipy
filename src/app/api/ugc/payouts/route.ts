import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { PAY } from "@/app/ugc/program";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * What each UGC creator is owed on orders.
 *
 * Reads attribution off the pre-order rows rather than recomputing it: the
 * webhook freezes creator_ref, the share percentage and the amount owed onto
 * the order at payment time. Recalculating here from today's rate would
 * silently restate what was owed on an order placed under an older one.
 *
 * Refunded orders are excluded from what is payable but still listed, so a
 * creator asking "what happened to that sale" gets an answer.
 *
 * The per-video fee is deliberately absent. Nothing on the site can verify a
 * view count, so it is settled by hand and this endpoint would only give it a
 * false air of precision.
 */
async function verifyAdmin(request: NextRequest): Promise<boolean> {
  const authHeader = request.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) return false;
  const token = authHeader.slice(7);

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
  const { data } = await supabase.auth.getUser(token);
  if (!data.user) return false;

  const { data: adminUser } = await supabaseAdmin
    .from("anticipy_admin_users")
    .select("role")
    .eq("id", data.user.id)
    .single();

  return !!adminUser;
}

interface Order {
  email: string | null;
  amount_total: number | null;
  status: string | null;
  created_at: string;
  refunded_at: string | null;
  metadata: Record<string, unknown> | null;
}

const money = (cents: number) => Number((cents / 100).toFixed(2));

export async function GET(request: NextRequest) {
  if (!(await verifyAdmin(request))) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data: orders, error } = await supabaseAdmin
    .from("anticipy_preorders")
    .select("email, amount_total, status, created_at, refunded_at, metadata")
    .order("created_at", { ascending: false })
    .limit(2000);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const attributed = ((orders as Order[] | null) ?? []).filter(
    (o) => typeof o.metadata?.creator_ref === "string" && o.metadata.creator_ref
  );

  // Creator names, so the payout list is readable. Absent until the creators
  // table exists, which must not break the numbers.
  const nameByHandle = new Map<string, { name: string; email: string; method: string | null; detail: string | null }>();
  try {
    const { data: creators } = await supabaseAdmin
      .from("anticipy_ugc_creators")
      .select("handle, name, email, payout_method, payout_detail");
    for (const c of creators ?? []) {
      nameByHandle.set(String(c.handle).toLowerCase(), {
        name: c.name,
        email: c.email,
        method: c.payout_method ?? null,
        detail: c.payout_detail ?? null,
      });
    }
  } catch {
    /* creators table not created yet — numbers still work */
  }

  const byHandle = new Map<
    string,
    { handle: string; orders: number; refunded: number; grossCents: number; owedCents: number; lastOrderAt: string }
  >();

  for (const o of attributed) {
    const handle = String(o.metadata!.creator_ref).toLowerCase();
    const owed = Number(o.metadata!.creator_owed_cents ?? 0) || 0;
    const isRefunded = !!o.refunded_at || o.status === "refunded";

    const row = byHandle.get(handle) ?? {
      handle,
      orders: 0,
      refunded: 0,
      grossCents: 0,
      owedCents: 0,
      lastOrderAt: o.created_at,
    };
    if (isRefunded) {
      row.refunded += 1;
    } else {
      row.orders += 1;
      row.grossCents += o.amount_total ?? 0;
      row.owedCents += owed;
    }
    if (o.created_at > row.lastOrderAt) row.lastOrderAt = o.created_at;
    byHandle.set(handle, row);
  }

  const creators = Array.from(byHandle.values())
    .sort((a, b) => b.owedCents - a.owedCents)
    .map((r) => {
      const who = nameByHandle.get(r.handle);
      return {
        handle: r.handle,
        link: `https://anticipy.ai/c/${r.handle}`,
        name: who?.name ?? null,
        email: who?.email ?? null,
        payTo: who ? `${who.method ?? "?"} — ${who.detail ?? "?"}` : null,
        knownCreator: !!who,
        paidOrders: r.orders,
        refundedOrders: r.refunded,
        gross: money(r.grossCents),
        owed: money(r.owedCents),
        lastOrderAt: r.lastOrderAt,
      };
    });

  return NextResponse.json({
    sharePct: PAY.purchaseSharePct,
    totalOwed: money(creators.reduce((n, c) => n + Math.round(c.owed * 100), 0)),
    attributedOrders: attributed.length,
    creators,
    note:
      "Order commission only. The per-video fee is settled by hand — nothing here can verify a view count.",
  });
}
