import { NextRequest, NextResponse } from "next/server";
import {
  stripe,
  PREORDER_PRICE_ID,
  AGREEMENT_VERSION,
  ALLOWED_SHIPPING_COUNTRIES,
} from "@/lib/stripe";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { getOrCreateVisitorId, loadProfile } from "@/lib/visitor";
import {
  selectTier,
  scoreVisitor,
  resolvePrice,
  type OfferTier,
} from "@/lib/offers";
import { ensureCoupon } from "@/lib/offer-coupons";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface ResolvedOffer {
  visitorId: string;
  arm: string;
  tierKey: string | null;
  amountOffCents: number;
  couponId: string | null;
}

/**
 * Derives the discount this visitor has actually earned, from the httpOnly
 * cookie and the stored profile — never from the request body.
 *
 * Returns null on any failure. A broken offer engine must degrade to
 * full-price checkout, never to a blocked checkout: losing a discount costs
 * margin, losing the sale costs the whole order.
 */
async function resolveOfferForRequest(): Promise<ResolvedOffer | null> {
  try {
    const { visitorId } = await getOrCreateVisitorId();
    const profile = await loadProfile(visitorId);
    if (!profile) return null;

    const base: ResolvedOffer = {
      visitorId,
      arm: profile.holdout_arm,
      tierKey: null,
      amountOffCents: 0,
      couponId: null,
    };

    // Control and legacy arms pay list price — that is what makes the
    // ladder's incremental lift measurable rather than merely observed.
    if (profile.holdout_arm !== "ladder") return base;
    if (profile.offer_redeemed) return base;

    const scores = scoreVisitor(profile);
    const { data } = await supabaseAdmin
      .from("anticipy_offer_tiers")
      .select("*")
      .eq("active", true)
      .order("sort_order");

    const tier = selectTier(scores, profile, (data ?? []) as OfferTier[]);
    if (!tier || tier.amount_off_cents <= 0) return base;

    const { amountOffCents } = resolvePrice(tier.amount_off_cents);
    const couponId = await ensureCoupon(amountOffCents);
    if (!couponId) return base;

    return {
      ...base,
      tierKey: tier.tier_key,
      amountOffCents,
      couponId,
    };
  } catch (err) {
    console.error("Offer resolution failed, falling back to list price:", err);
    return null;
  }
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const ageConfirmed = body.ageConfirmed === true;
    const agreementAccepted = body.agreementAccepted === true;
    const marketingOptIn = body.marketingOptIn === true;

    // Carried through Stripe so the webhook can attribute the paid order to
    // the same PostHog person who did the browsing. Length-capped because
    // Stripe rejects metadata values over 500 chars, and treated as opaque —
    // never trusted, never used for authorisation, only for analytics joins.
    const posthogDistinctId =
      typeof body.posthogDistinctId === "string"
        ? body.posthogDistinctId.slice(0, 200)
        : "";
    const posthogSessionId =
      typeof body.posthogSessionId === "string"
        ? body.posthogSessionId.slice(0, 200)
        : "";

    if (!email || !EMAIL_REGEX.test(email)) {
      return NextResponse.json({ error: "Enter a valid email." }, { status: 400 });
    }

    if (!ageConfirmed) {
      return NextResponse.json(
        { error: "You must confirm that you are at least 18 years old." },
        { status: 400 }
      );
    }

    if (!agreementAccepted) {
      return NextResponse.json(
        { error: "You must accept the Pre-Order Agreement to continue." },
        { status: 400 }
      );
    }

    const ip =
      request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
      request.headers.get("x-real-ip") ||
      "unknown";

    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const { count } = await supabaseAdmin
      .from("anticipy_preorders")
      .select("*", { count: "exact", head: true })
      .eq("ip_address", ip)
      .gte("created_at", oneHourAgo);

    if (count && count >= 5) {
      return NextResponse.json(
        { error: "Too many checkout attempts. Try again in an hour." },
        { status: 429 }
      );
    }

    const origin =
      request.headers.get("origin") ||
      `https://${request.headers.get("host") || "www.anticipy.ai"}`;

    // Re-derive the earned tier here rather than trusting anything the
    // client sent. The browser never passes a tier or a price — if it could,
    // the whole ladder would be a DevTools exercise ending at the floor.
    const offer = await resolveOfferForRequest();

    // Which UGC creator sent this buyer, if any. /c/<handle> drops this
    // cookie for 90 days; Stripe metadata is what carries it across the
    // hosted checkout, since the webhook fires server-to-server and can see
    // nothing else about the browser that started the session.
    const creatorRef = (request.cookies.get("ap_ref")?.value || "")
      .toLowerCase()
      .replace(/[^a-z0-9-]/g, "")
      .slice(0, 24);

    const session = await stripe.checkout.sessions.create({
      mode: "payment",
      line_items: [{ price: PREORDER_PRICE_ID, quantity: 1 }],
      customer_email: email,
      submit_type: "book",
      payment_intent_data: {
        statement_descriptor_suffix: "PREORDER",
        description: "Anticipy Pendant Pre-Order",
        metadata: {
          product_type: "preorder",
          agreement_version: AGREEMENT_VERSION,
        },
      },
      shipping_address_collection: {
        allowed_countries: ALLOWED_SHIPPING_COUNTRIES,
      },
      phone_number_collection: { enabled: true },
      billing_address_collection: "required",
      shipping_options: [
        {
          shipping_rate_data: {
            display_name: "Free shipping (US and Canada)",
            type: "fixed_amount",
            fixed_amount: { amount: 0, currency: "usd" },
          },
        },
      ],
      consent_collection: {
        terms_of_service: "required",
      },
      custom_text: {
        terms_of_service_acceptance: {
          message:
            "By placing this pre-order you agree to the [Pre-Order Agreement](https://www.anticipy.ai/pre-orders/agreement), [Terms of Service](https://www.anticipy.ai/terms), and [Privacy Policy](https://www.anticipy.ai/privacy). Estimated ship: Q4 2026.",
        },
        submit: {
          message:
            "Charges $149.99 USD now to lock in your Anticipy pendant at $50 off the $199 retail price.",
        },
      },
      metadata: {
        product_type: "preorder",
        agreement_version: AGREEMENT_VERSION,
        marketing_opt_in: marketingOptIn ? "true" : "false",
        age_confirmed: "true",
        ip,
        customer_name: name || "",
        posthog_distinct_id: posthogDistinctId,
        posthog_session_id: posthogSessionId,
        offer_tier: offer?.tierKey ?? "",
        offer_amount_off_cents: String(offer?.amountOffCents ?? 0),
        holdout_arm: offer?.arm ?? "",
        creator_ref: creatorRef,
      },
      success_url: `${origin}/pre-orders/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/pre-orders/purchase?canceled=1`,

      // `discounts` and `allow_promotion_codes` are MUTUALLY EXCLUSIVE on a
      // Checkout Session — Stripe rejects a request carrying both, and it
      // does so even when allow_promotion_codes is false. So exactly one of
      // these keys may be present, which is why this is a spread rather than
      // two static fields.
      //
      // When the visitor has earned a tier we pre-apply it and suppress the
      // promo-code box: they should not be prompted to hunt for a better code
      // than the one already applied. Otherwise the box stays available.
      ...(offer?.couponId
        ? { discounts: [{ coupon: offer.couponId }] }
        : { allow_promotion_codes: true }),
    });

    // Burn the offer so the same visitor cannot re-run the ladder for a
    // second discount. Deliberately fire-and-forget: a failure here must not
    // block a checkout the customer has already committed to.
    if (offer?.visitorId && offer.couponId) {
      // AWAITED, not fire-and-forget. A Supabase query builder is a lazy
      // thenable: it issues no HTTP request until it is awaited. The previous
      // `void` never triggered it, so offer_redeemed was never set for anyone
      // and the one-time discount was infinitely reusable.
      //
      // Awaiting it also matters on serverless, where the function can be
      // frozen the instant it returns and an in-flight request is simply
      // dropped. The error is swallowed so a bookkeeping failure cannot break
      // a checkout the customer has already committed to.
      try {
        await supabaseAdmin
          .from("anticipy_visitor_profiles")
          .update({ offer_redeemed: true })
          .eq("visitor_id", offer.visitorId);
      } catch (err) {
        console.error("Failed to burn offer for", offer.visitorId, err);
      }
    }

    return NextResponse.json({ url: session.url, id: session.id }, { status: 200 });
  } catch (err: unknown) {
    console.error("Pre-order checkout error:", err);
    const message =
      err instanceof Error ? err.message : "Could not start checkout. Try again.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
