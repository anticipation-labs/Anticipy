import "server-only";

import { cookies } from "next/headers";
import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  assignArm,
  classifyReferrer,
  scoreVisitor,
  type VisitorProfile,
} from "@/lib/offers";

/**
 * Visitor identity and behavioural profile storage.
 *
 * The visitor id lives in an httpOnly cookie so the browser cannot read or
 * forge it. That matters because this id is what the discount tier is keyed
 * to: if the client could set it, clearing a cookie until you land on the
 * floor tier would be a trivial exploit, and the ladder would collapse into
 * "everyone pays $109.99".
 *
 * The profile is the accumulated behaviour the offer engine scores. It is
 * written from the client via /api/offers/evaluate, which is why every field
 * that could move a visitor DOWN the price ladder is either clamped or
 * monotonic here — a hostile client that reports "I abandoned checkout 900
 * times" must not be able to buy its way to the floor.
 */

const COOKIE = "ap_vid";
const ONE_YEAR_S = 60 * 60 * 24 * 365;

function newVisitorId(): string {
  return `v_${crypto.randomUUID().replace(/-/g, "")}`;
}

/** Reads the visitor cookie, minting one if absent. */
export async function getOrCreateVisitorId(): Promise<{
  visitorId: string;
  isNew: boolean;
}> {
  const jar = await cookies();
  const existing = jar.get(COOKIE)?.value;
  if (existing && /^v_[a-f0-9]{32}$/.test(existing)) {
    return { visitorId: existing, isNew: false };
  }
  const visitorId = newVisitorId();
  jar.set(COOKIE, visitorId, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: ONE_YEAR_S,
  });
  return { visitorId, isNew: true };
}

export async function loadProfile(
  visitorId: string
): Promise<VisitorProfile | null> {
  const { data, error } = await supabaseAdmin
    .from("anticipy_visitor_profiles")
    .select("*")
    .eq("visitor_id", visitorId)
    .maybeSingle();
  if (error || !data) return null;
  return data as VisitorProfile;
}

/** Client-reported behaviour. Every value is treated as hostile. */
export interface SignalPatch {
  engagedSeconds?: number;
  maxScrollPct?: number;
  priceDwellSeconds?: number;
  pagesSeen?: string[];
  sectionsSeen?: string[];
  frictionFlags?: string[];
  checkoutStarted?: boolean;
  checkoutAbandoned?: boolean;
  emailFieldCompleted?: boolean;
  emailCaptured?: boolean;
  referrer?: string | null;
  utmSource?: string | null;
  utmMedium?: string | null;
  utmCampaign?: string | null;
  landingPath?: string | null;
  newSession?: boolean;
}

const clampInt = (v: unknown, min: number, max: number): number => {
  const n = Math.floor(Number(v));
  if (!Number.isFinite(n)) return min;
  return Math.min(max, Math.max(min, n));
};

const cleanList = (v: unknown, allowed: RegExp, cap: number): string[] =>
  Array.isArray(v)
    ? Array.from(
        new Set(
          v
            .filter((x): x is string => typeof x === "string")
            .map((x) => x.slice(0, 40))
            .filter((x) => allowed.test(x))
        )
      ).slice(0, cap)
    : [];

/**
 * Merges a client patch into the stored profile and rescores.
 *
 * Counters only ever move UP and are capped, so replaying the same request a
 * thousand times cannot inflate a visitor into the floor tier. Session count
 * increments at most once per call, and the holdout arm is derived from the
 * id rather than stored, so it can never drift.
 */
export async function updateProfile(
  visitorId: string,
  patch: SignalPatch
): Promise<VisitorProfile> {
  const existing = await loadProfile(visitorId);

  const arm = assignArm(visitorId);
  const referrerClass =
    existing?.referrer_class ??
    classifyReferrer(patch.referrer ?? null, patch.utmMedium ?? null);

  const merged: VisitorProfile = {
    visitor_id: visitorId,
    // Monotonic, and capped well above any legitimate value.
    session_count: Math.min(
      500,
      (existing?.session_count ?? 0) + (patch.newSession || !existing ? 1 : 0)
    ),
    engaged_seconds: Math.max(
      existing?.engaged_seconds ?? 0,
      clampInt(patch.engagedSeconds ?? 0, 0, 86_400)
    ),
    max_scroll_pct: Math.max(
      existing?.max_scroll_pct ?? 0,
      clampInt(patch.maxScrollPct ?? 0, 0, 100)
    ),
    price_dwell_seconds: Math.max(
      existing?.price_dwell_seconds ?? 0,
      clampInt(patch.priceDwellSeconds ?? 0, 0, 86_400)
    ),
    pages_seen: Array.from(
      new Set([
        ...(existing?.pages_seen ?? []),
        ...cleanList(patch.pagesSeen, /^\/[A-Za-z0-9/_-]*$/, 40),
      ])
    ).slice(0, 40),
    sections_seen: Array.from(
      new Set([
        ...(existing?.sections_seen ?? []),
        ...cleanList(patch.sectionsSeen, /^[a-z_]+$/, 30),
      ])
    ).slice(0, 30),
    friction_flags: Array.from(
      new Set([
        ...(existing?.friction_flags ?? []),
        ...cleanList(patch.frictionFlags, /^[a-z_]+$/, 20),
      ])
    ).slice(0, 20),
    checkout_started_count: Math.min(
      50,
      (existing?.checkout_started_count ?? 0) + (patch.checkoutStarted ? 1 : 0)
    ),
    checkout_abandoned_count: Math.min(
      50,
      (existing?.checkout_abandoned_count ?? 0) +
        (patch.checkoutAbandoned ? 1 : 0)
    ),
    email_field_completed:
      (existing?.email_field_completed ?? false) ||
      patch.emailFieldCompleted === true,
    email_captured:
      (existing?.email_captured ?? false) || patch.emailCaptured === true,
    referrer_class: referrerClass,
    first_seen_at: existing?.first_seen_at ?? new Date().toISOString(),
    last_seen_at: new Date().toISOString(),
    holdout_arm: arm,
    offer_redeemed: existing?.offer_redeemed ?? false,
  };

  const scores = scoreVisitor(merged);

  const row = {
    ...merged,
    intent_score: scores.intent,
    friction_score: scores.friction,
    utm_source: existing ? undefined : patch.utmSource?.slice(0, 120) ?? null,
    utm_medium: existing ? undefined : patch.utmMedium?.slice(0, 120) ?? null,
    utm_campaign: existing
      ? undefined
      : patch.utmCampaign?.slice(0, 120) ?? null,
    landing_path: existing ? undefined : patch.landingPath?.slice(0, 200) ?? null,
  };

  // Strip undefined so an upsert never overwrites first-touch attribution
  // with nulls on a later visit.
  const clean = Object.fromEntries(
    Object.entries(row).filter(([, v]) => v !== undefined)
  );

  await supabaseAdmin
    .from("anticipy_visitor_profiles")
    .upsert(clean, { onConflict: "visitor_id" });

  return merged;
}

export async function logOfferEvent(args: {
  visitorId: string;
  tierKey: string | null;
  event: string;
  triggerType?: string | null;
  priceBeforeCents?: number | null;
  priceAfterCents?: number | null;
  holdoutArm?: string | null;
  meta?: Record<string, unknown>;
}): Promise<void> {
  try {
    await supabaseAdmin.from("anticipy_offer_events").insert({
      visitor_id: args.visitorId,
      tier_key: args.tierKey,
      event: args.event,
      trigger_type: args.triggerType ?? null,
      price_before_cents: args.priceBeforeCents ?? null,
      price_after_cents: args.priceAfterCents ?? null,
      holdout_arm: args.holdoutArm ?? null,
      meta: args.meta ?? {},
    });
  } catch {
    // Measurement must never break the offer itself.
  }
}
