import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { ensureCoupon } from "@/lib/offer-coupons";
import { LIST_PRICE_CENTS, FLOOR_PRICE_CENTS } from "@/lib/offers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Admin control surface for the discount ladder.
 *
 * Same bearer-token posture as the existing /api/admin/* routes: a Supabase
 * session token is validated, then checked against anticipy_admin_users.
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

/** Tiers plus live performance, so the ladder can be judged, not just edited. */
export async function GET(request: NextRequest) {
  if (!(await verifyAdmin(request))) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data: tiers } = await supabaseAdmin
    .from("anticipy_offer_tiers")
    .select("*")
    .order("sort_order");

  const { data: events } = await supabaseAdmin
    .from("anticipy_offer_events")
    .select("tier_key,event,holdout_arm")
    .limit(10_000);

  const stats: Record<string, { shown: number; accepted: number; dismissed: number }> = {};
  for (const e of events ?? []) {
    const k = (e as { tier_key: string | null }).tier_key ?? "none";
    stats[k] ||= { shown: 0, accepted: 0, dismissed: 0 };
    const ev = (e as { event: string }).event;
    if (ev === "shown") stats[k].shown++;
    else if (ev === "accepted") stats[k].accepted++;
    else if (ev === "dismissed") stats[k].dismissed++;
  }

  return NextResponse.json({
    tiers: tiers ?? [],
    stats,
    listPriceCents: LIST_PRICE_CENTS,
    floorPriceCents: FLOOR_PRICE_CENTS,
  });
}

/**
 * Updates one tier. Only the fields an operator should be able to change are
 * writable — tier_key and sort_order are structural and stay fixed.
 */
export async function PATCH(request: NextRequest) {
  if (!(await verifyAdmin(request))) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: Record<string, unknown> = {};
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const tierKey = typeof body.tierKey === "string" ? body.tierKey : "";
  if (!tierKey) {
    return NextResponse.json({ error: "tierKey required" }, { status: 400 });
  }

  const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };

  if (body.amountOffCents !== undefined) {
    const amt = Math.floor(Number(body.amountOffCents));
    const maxOff = LIST_PRICE_CENTS - FLOOR_PRICE_CENTS;
    // Rejected rather than clamped: an operator who typed 13999 should be
    // told, not quietly given something else. A 100%-off coupon would also
    // produce no PaymentIntent at all and break fulfilment silently.
    if (!Number.isFinite(amt) || amt < 0 || amt > maxOff) {
      return NextResponse.json(
        {
          error: `amountOffCents must be between 0 and ${maxOff} (floor price $${(
            FLOOR_PRICE_CENTS / 100
          ).toFixed(2)}).`,
        },
        { status: 400 }
      );
    }
    patch.amount_off_cents = amt;
    // The coupon id is derived from the amount, so changing the amount
    // invalidates the old link. Re-resolve it now rather than at checkout.
    patch.stripe_coupon_id = amt > 0 ? await ensureCoupon(amt) : null;
  }

  if (typeof body.active === "boolean") patch.active = body.active;
  if (typeof body.headline === "string") patch.headline = body.headline.slice(0, 160);
  if (typeof body.subhead === "string") patch.subhead = body.subhead.slice(0, 240);
  if (body.maxRedemptions !== undefined) {
    const n = Number(body.maxRedemptions);
    patch.max_redemptions = Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
  }
  if (body.expiresAt !== undefined) {
    patch.expires_at = body.expiresAt ? String(body.expiresAt) : null;
  }

  const { error } = await supabaseAdmin
    .from("anticipy_offer_tiers")
    .update(patch)
    .eq("tier_key", tierKey);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}

/**
 * Creates the Stripe coupon behind every active tier and writes the ids back.
 *
 * Run once after deploy, and again after changing any amount. Coupon ids are
 * deterministic, so this is safe to run repeatedly.
 */
export async function POST(request: NextRequest) {
  if (!(await verifyAdmin(request))) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data: tiers } = await supabaseAdmin
    .from("anticipy_offer_tiers")
    .select("tier_key,amount_off_cents")
    .eq("active", true);

  const results: { tier: string; coupon: string | null }[] = [];
  for (const t of tiers ?? []) {
    const row = t as { tier_key: string; amount_off_cents: number };
    if (row.amount_off_cents <= 0) {
      results.push({ tier: row.tier_key, coupon: null });
      continue;
    }
    const coupon = await ensureCoupon(row.amount_off_cents);
    if (coupon) {
      await supabaseAdmin
        .from("anticipy_offer_tiers")
        .update({ stripe_coupon_id: coupon })
        .eq("tier_key", row.tier_key);
    }
    results.push({ tier: row.tier_key, coupon });
  }

  return NextResponse.json({ ok: true, results });
}
