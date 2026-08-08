import "server-only";

import { stripe } from "@/lib/stripe";

/**
 * Maps a discount amount to a reusable Stripe coupon.
 *
 * Deterministic ids (`anticipy_off_2999`) rather than one coupon per visitor.
 * The tier is decided server-side, so the discount is applied by passing
 * `discounts: [{ coupon }]` on the Checkout Session and the buyer never sees
 * or types a code. That collapses "a unique code per visitor at scale" into
 * eight reusable coupons — no per-request object creation, no rate-limit
 * exposure in the checkout path, and nothing to paste into a coupon site
 * because no code string ever reaches the browser.
 *
 * amount_off, never percent_off: none of the ladder's target prices is
 * exactly expressible as a percentage of 14999 ($120.00 would need
 * 20.0013…%), and Stripe does not document how it rounds percentage
 * discounts. A fixed amount lands on the intended price every time.
 */

const MAX_OFF_CENTS = 4000;

export function couponIdFor(amountOffCents: number): string {
  return `anticipy_off_${amountOffCents}`;
}

/**
 * Returns a coupon id, creating it if absent. Idempotent by construction:
 * a concurrent create loses the race with `resource_already_exists`, which
 * is caught and treated as success.
 */
export async function ensureCoupon(amountOffCents: number): Promise<string | null> {
  const amount = Math.floor(amountOffCents);
  if (!Number.isFinite(amount) || amount <= 0 || amount > MAX_OFF_CENTS) {
    return null;
  }

  const id = couponIdFor(amount);

  try {
    const existing = await stripe.coupons.retrieve(id);
    if (existing && !existing.deleted) return id;
  } catch {
    // Not found — fall through to create.
  }

  try {
    await stripe.coupons.create({
      id,
      amount_off: amount,
      currency: "usd",
      // `once` is the correct duration for one-time payments; `repeating`
      // and `forever` only mean anything for subscriptions.
      duration: "once",
      name: `Anticipy $${(amount / 100).toFixed(2)} off`,
      metadata: { source: "offer_engine" },
    });
    return id;
  } catch (err) {
    const code = (err as { code?: string })?.code;
    if (code === "resource_already_exists") return id;
    console.error("Coupon create failed:", err);
    return null;
  }
}
