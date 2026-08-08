import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import {
  selectTier,
  scoreVisitor,
  resolvePrice,
  LIST_PRICE_CENTS,
  type OfferTier,
} from "@/lib/offers";
import {
  getOrCreateVisitorId,
  updateProfile,
  logOfferEvent,
  type SignalPatch,
} from "@/lib/visitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Evaluates which offer, if any, the current visitor has earned.
 *
 * The response deliberately does NOT include anything the checkout will
 * trust. Checkout re-derives the tier from the same httpOnly cookie on its
 * own, so this endpoint is purely presentational — if a visitor tampered
 * with the response to show themselves "$110", checkout would still charge
 * the tier they actually earned. That is why there is no signed token here:
 * there is nothing worth signing.
 */
export async function POST(request: NextRequest) {
  const ip = clientIp(request);
  // Generous: this fires on scroll/dwell milestones during normal browsing.
  const limit = rateLimit(`offer-eval:${ip}`, 60, 60_000);
  if (!limit.allowed) {
    return NextResponse.json({ eligible: false }, { status: 429 });
  }

  let body: SignalPatch = {};
  try {
    body = (await request.json()) as SignalPatch;
  } catch {
    body = {};
  }

  const { visitorId } = await getOrCreateVisitorId();
  const profile = await updateProfile(visitorId, body);
  const scores = scoreVisitor(profile);

  // The control arm never sees a behavioural offer, and the legacy arm sits
  // on the old flat price. Both are what make the ladder's lift measurable
  // rather than merely observed.
  if (profile.holdout_arm !== "ladder") {
    return NextResponse.json({
      eligible: false,
      arm: profile.holdout_arm,
      listPriceCents: LIST_PRICE_CENTS,
    });
  }

  if (profile.offer_redeemed) {
    return NextResponse.json({
      eligible: false,
      arm: profile.holdout_arm,
      reason: "already_redeemed",
      listPriceCents: LIST_PRICE_CENTS,
    });
  }

  const { data: tierRows } = await supabaseAdmin
    .from("anticipy_offer_tiers")
    .select("*")
    .eq("active", true)
    .order("sort_order");

  const tiers = (tierRows ?? []) as OfferTier[];
  const tier = selectTier(scores, profile, tiers);

  if (!tier || tier.amount_off_cents <= 0) {
    return NextResponse.json({
      eligible: false,
      arm: profile.holdout_arm,
      tierKey: tier?.tier_key ?? null,
      listPriceCents: LIST_PRICE_CENTS,
    });
  }

  const { amountOffCents, finalPriceCents } = resolvePrice(tier.amount_off_cents);

  return NextResponse.json({
    eligible: true,
    arm: profile.holdout_arm,
    tierKey: tier.tier_key,
    headline: tier.headline,
    subhead: tier.subhead,
    listPriceCents: LIST_PRICE_CENTS,
    priceCents: finalPriceCents,
    amountOffCents,
    intentScore: scores.intent,
    frictionScore: scores.friction,
  });
}

/** Records impressions, dismissals and accepts against the holdout arm. */
export async function PUT(request: NextRequest) {
  const ip = clientIp(request);
  const limit = rateLimit(`offer-evt:${ip}`, 60, 60_000);
  if (!limit.allowed) return NextResponse.json({ ok: false }, { status: 429 });

  let body: {
    event?: string;
    tierKey?: string | null;
    triggerType?: string | null;
    priceAfterCents?: number | null;
  } = {};
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400 });
  }

  const ALLOWED = new Set([
    "shown",
    "accepted",
    "dismissed",
    "suppressed",
  ]);
  if (!body.event || !ALLOWED.has(body.event)) {
    return NextResponse.json({ ok: false }, { status: 400 });
  }

  const { visitorId } = await getOrCreateVisitorId();

  await logOfferEvent({
    visitorId,
    tierKey: body.tierKey ?? null,
    event: body.event,
    triggerType: body.triggerType ?? null,
    priceBeforeCents: LIST_PRICE_CENTS,
    priceAfterCents: body.priceAfterCents ?? null,
  });

  if (body.event === "shown" || body.event === "dismissed") {
    const col =
      body.event === "shown" ? "offer_shown_count" : "offer_dismissed_count";
    const { data } = await supabaseAdmin
      .from("anticipy_visitor_profiles")
      .select(col)
      .eq("visitor_id", visitorId)
      .maybeSingle();
    const current = ((data as Record<string, number> | null)?.[col] ?? 0) + 1;
    await supabaseAdmin
      .from("anticipy_visitor_profiles")
      .update({ [col]: current })
      .eq("visitor_id", visitorId);
  }

  return NextResponse.json({ ok: true });
}
