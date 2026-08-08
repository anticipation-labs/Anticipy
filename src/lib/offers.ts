import "server-only";

/**
 * The offer engine.
 *
 * Server-only by construction. The visitor's tier is derived here from a
 * stored behavioural profile and never accepted from the client — if the
 * browser could assert its own tier, the discount ladder would be a DevTools
 * exercise and every order would land on the floor price.
 *
 * Two scores rather than one, which is the whole design:
 *
 *   INTENT   — how likely this person is to buy at all.
 *   FRICTION — evidence they are stalling: abandonment, repeated price
 *              visits, refund-policy reading, exit signals.
 *
 * A single propensity score systematically mis-targets, because the
 * highest-propensity visitors are precisely the ones who would have bought
 * anyway. Discounting them is a pure margin transfer. The ladder therefore
 * runs DOWN as intent falls and UP as friction rises: the deepest offers go
 * to people showing real hesitation, not to the most enthusiastic visitors.
 */

export type SalesMode = "preorder" | "order";

/**
 * The single flip between pre-order and real-order operation. Everything
 * that differs between the two modes reads from here, so switching is one
 * env var rather than a hunt through copy strings.
 */
export const SALES_MODE: SalesMode =
  process.env.NEXT_PUBLIC_SALES_MODE === "order" ? "order" : "preorder";

export const LIST_PRICE_CENTS = 14999;

/** Hard floor. No tier, admin action, or scoring accident may go below this. */
export const FLOOR_PRICE_CENTS = 10999;

/**
 * Minimum intent score before ANY discount is offered.
 *
 * Set at the lower bound of the mid ladder so the deep tiers are reachable
 * only by being bumped down from here on demonstrated friction — never by
 * simply scoring low. Discounts are for people who are deciding and stalling,
 * not for people who just arrived.
 */
export const MIN_OFFER_INTENT = 14;

export interface VisitorProfile {
  visitor_id: string;
  session_count: number;
  engaged_seconds: number;
  max_scroll_pct: number;
  price_dwell_seconds: number;
  pages_seen: string[];
  sections_seen: string[];
  friction_flags: string[];
  checkout_started_count: number;
  checkout_abandoned_count: number;
  email_field_completed: boolean;
  email_captured: boolean;
  referrer_class: string | null;
  first_seen_at: string;
  last_seen_at: string;
  holdout_arm: string;
  offer_redeemed: boolean;
}

export interface OfferTier {
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
  min_sessions: number;
  active: boolean;
  max_redemptions: number | null;
  redemption_count: number;
  expires_at: string | null;
}

export interface Scores {
  intent: number;
  friction: number;
}

/**
 * Referrer classes carry very different buying intent. A visitor arriving
 * from a coupon aggregator is scored NEGATIVELY on intent — they came for a
 * discount rather than for the product, and handing them the deepest tier is
 * how a ladder degrades into a permanent across-the-board price cut.
 */
export function classifyReferrer(referrer: string | null, utmMedium?: string | null): string {
  if (!referrer && !utmMedium) return "direct";
  const r = (referrer || "").toLowerCase();
  const m = (utmMedium || "").toLowerCase();

  if (/honey|retailmenot|slickdeals|coupon|promo|dealnews/.test(r)) return "deal_site";
  if (m === "email") return "email";
  if (/reddit|news\.ycombinator|discord|lobste/.test(r)) return "community";
  if (/google|bing|duckduckgo/.test(r)) return "search";
  if (/facebook|instagram|tiktok|twitter|x\.com|linkedin/.test(r)) return "social";
  if (m === "cpc" || m === "paid") return "paid";
  return "referral";
}

export function scoreVisitor(p: VisitorProfile): Scores {
  let intent = 0;

  // Repeat visits are the strongest single predictor in the popup data —
  // stronger than any amount of time spent in one sitting.
  if (p.session_count >= 5) intent += 22;
  else if (p.session_count >= 3) intent += 18;
  else if (p.session_count >= 2) intent += 10;

  // Engaged seconds, not wall clock. See src/lib/analytics.ts.
  if (p.engaged_seconds > 600) intent += 20;
  else if (p.engaged_seconds >= 180) intent += 14;
  else if (p.engaged_seconds >= 60) intent += 6;

  if (p.max_scroll_pct >= 90) intent += 8;

  // Dwelling on the price block is the closest thing to a stated purchase
  // consideration that a visitor emits without typing anything.
  if (p.price_dwell_seconds > 90) intent += 18;
  else if (p.price_dwell_seconds > 30) intent += 12;

  const readSpecs = p.sections_seen.some((s) =>
    ["comparison", "object", "trust", "faq"].includes(s)
  );
  if (readSpecs) intent += 6;

  if (p.email_captured) intent += 12;
  if (p.checkout_started_count > 0) intent += 25;

  switch (p.referrer_class) {
    case "community":
      intent += 15;
      break;
    case "email":
      intent += 14;
      break;
    case "search":
      intent += 12;
      break;
    case "direct":
      intent += 10;
      break;
    case "referral":
      intent += 5;
      break;
    case "deal_site":
      intent -= 10;
      break;
    default:
      break;
  }

  // ── Friction ────────────────────────────────────────────────────
  let friction = 0;
  if (p.checkout_abandoned_count >= 2) friction += 3;
  else if (p.checkout_abandoned_count === 1) friction += 2;

  if (p.email_field_completed && !p.email_captured) friction += 2;
  if (p.friction_flags.includes("refund_policy_viewed")) friction += 1;
  if (p.friction_flags.includes("exit_intent")) friction += 1;
  if (p.friction_flags.includes("repeat_price_view")) friction += 1;
  if (p.session_count >= 3 && p.checkout_started_count === 0) friction += 1;

  return { intent: Math.max(0, intent), friction };
}

/**
 * Picks the tier this visitor has earned.
 *
 * The intent bands are treated as CONTIGUOUS AND EXHAUSTIVE: every possible
 * score lands in exactly one band, so there is no combination of signals that
 * falls through to full price by accident.
 *
 * An earlier version applied `min_friction_score` and `min_sessions` as hard
 * gates on top of the bands. That left 20% of the score space matching no
 * tier at all, and worse, made the ladder non-monotonic — a first-session
 * visitor scoring 40 received nothing while one scoring 30 received $20 off.
 * Friction now DEEPENS an already-chosen tier instead of being able to
 * disqualify a visitor from every tier at once.
 *
 * Tiers that are inactive, expired, or out of redemptions are skipped
 * SHALLOWER (toward full price), never deeper: running out of budget on a
 * discount must not promote someone into a bigger one.
 */
export function selectTier(
  scores: Scores,
  profile: VisitorProfile,
  tiers: OfferTier[]
): OfferTier | null {
  const now = Date.now();

  const available = (t: OfferTier): boolean =>
    t.active &&
    (!t.expires_at || new Date(t.expires_at).getTime() > now) &&
    (t.max_redemptions == null || t.redemption_count < t.max_redemptions);

  const ordered = [...tiers].sort((a, b) => a.sort_order - b.sort_order);
  if (!ordered.length) return null;

  // NOTHING is offered below this. A visitor who has read nothing is not a
  // persuadable, they are a bounce — and a discount is wasted on them twice
  // over: it cannot change a decision they have not started making, and it
  // hands away margin to anyone who simply loads the page.
  //
  // An earlier revision omitted this. Because the intent bands are
  // exhaustive, a brand-new visitor scored 0 and landed in the deepest band,
  // so the very first request from someone with zero seconds on site
  // returned the $109.99 floor. That was live and verified in production.
  if (scores.intent < MIN_OFFER_INTENT) return null;

  let idx = ordered.findIndex(
    (t) =>
      scores.intent >= t.min_intent_score &&
      (t.max_intent_score == null || scores.intent <= t.max_intent_score)
  );

  // Defensive: if an admin edit leaves a genuine gap in the bands, fall back
  // to the shallowest tier rather than returning nothing. Erring toward full
  // price is the safe direction for a misconfiguration.
  if (idx < 0) idx = 0;

  // Clear hesitation earns one step deeper — but only one, so friction
  // cannot cascade a casual visitor to the floor.
  if (scores.friction >= 2 && idx + 1 < ordered.length) idx += 1;

  // Walk shallower until a tier is both available AND one this visitor
  // actually qualifies for. min_friction_score and min_sessions are enforced
  // HERE rather than as entry filters: as filters they could disqualify a
  // visitor from every tier at once and blow a hole in the ladder, but as a
  // downward walk they only ever move someone toward full price.
  for (let i = idx; i >= 0; i--) {
    const t = ordered[i];
    if (!available(t)) continue;
    if (scores.friction < t.min_friction_score) continue;
    if (profile.session_count < t.min_sessions) continue;
    return t;
  }
  return null;
}

/**
 * Final safety clamp. A misconfigured tier or an admin typo must not be able
 * to sell the pendant below the floor, and a negative or absurd amount_off
 * must not produce a free order — a 100%-off checkout creates no
 * PaymentIntent at all, which silently breaks every downstream fulfilment
 * hook that keys on payment events.
 */
export function resolvePrice(amountOffCents: number): {
  amountOffCents: number;
  finalPriceCents: number;
  clamped: boolean;
} {
  const safeOff = Math.max(0, Math.floor(amountOffCents || 0));
  const naive = LIST_PRICE_CENTS - safeOff;
  if (naive < FLOOR_PRICE_CENTS) {
    return {
      amountOffCents: LIST_PRICE_CENTS - FLOOR_PRICE_CENTS,
      finalPriceCents: FLOOR_PRICE_CENTS,
      clamped: true,
    };
  }
  return { amountOffCents: safeOff, finalPriceCents: naive, clamped: false };
}

/**
 * Holdout assignment, stable for the life of a visitor.
 *
 * Derived from the visitor id rather than stored-then-read, so it is
 * identical on every request even if the profile row is lost or rebuilt.
 * Reassigning a returning visitor to a different arm is the single easiest
 * way to destroy an experiment without noticing.
 *
 *   control  25% — never sees a behavioural offer
 *   ladder   60% — the full tier engine
 *   legacy   15% — flat legacy price, the status-quo benchmark
 *
 * The legacy arm is the one teams forget, and it is the only thing that can
 * answer "is any of this better than what we did before?"
 */
export function assignArm(visitorId: string): "control" | "ladder" | "legacy" {
  let h = 0;
  for (let i = 0; i < visitorId.length; i++) {
    h = (h * 31 + visitorId.charCodeAt(i)) >>> 0;
  }
  const bucket = h % 100;
  if (bucket < 25) return "control";
  if (bucket < 85) return "ladder";
  return "legacy";
}
