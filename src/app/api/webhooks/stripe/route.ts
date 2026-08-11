import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { stripe } from "@/lib/stripe";
import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  sendPreorderConfirmation,
  sendOwnerPreorderNotification,
} from "@/lib/email";
import { captureServer, emailHashServer } from "@/lib/analytics-server";
import { PAY as UGC_PAY } from "@/app/ugc/program";


const CREATOR_SHARE_PCT = UGC_PAY.purchaseSharePct;

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const sig = request.headers.get("stripe-signature");
  const secret = process.env.STRIPE_WEBHOOK_SECRET;

  if (!sig || !secret) {
    return NextResponse.json(
      { error: "Missing signature or webhook secret." },
      { status: 400 }
    );
  }

  let event: Stripe.Event;
  const rawBody = await request.text();

  try {
    event = stripe.webhooks.constructEvent(rawBody, sig, secret);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Bad signature.";
    console.error("Stripe webhook signature verify failed:", message);
    return NextResponse.json({ error: message }, { status: 400 });
  }

  try {
    switch (event.type) {
      case "checkout.session.completed":
        await handleCheckoutCompleted(
          event.data.object as Stripe.Checkout.Session
        );
        break;
      case "charge.refunded":
        await handleChargeRefunded(event.data.object as Stripe.Charge);
        break;
      default:
        break;
    }
  } catch (err) {
    console.error(`Webhook handler failed for ${event.type}:`, err);
    return NextResponse.json({ received: false }, { status: 500 });
  }

  return NextResponse.json({ received: true }, { status: 200 });
}

async function handleCheckoutCompleted(session: Stripe.Checkout.Session) {
  if (session.mode !== "payment") return;
  if (session.metadata?.product_type !== "preorder") return;
  if (session.payment_status !== "paid") return;

  const email =
    session.customer_details?.email ??
    session.customer_email ??
    null;

  if (!email) {
    console.error("Pre-order completed without email:", session.id);
    return;
  }

  const shipping = session.collected_information?.shipping_details ?? null;
  const shippingAddress = shipping?.address ?? null;

  const row = {
    stripe_checkout_session_id: session.id,
    stripe_payment_intent_id:
      typeof session.payment_intent === "string"
        ? session.payment_intent
        : (session.payment_intent?.id ?? null),
    stripe_customer_id:
      typeof session.customer === "string"
        ? session.customer
        : (session.customer?.id ?? null),
    email: email.toLowerCase(),
    name:
      session.metadata?.customer_name ||
      session.customer_details?.name ||
      shipping?.name ||
      null,
    shipping_name: shipping?.name ?? null,
    shipping_address_line1: shippingAddress?.line1 ?? null,
    shipping_address_line2: shippingAddress?.line2 ?? null,
    shipping_address_city: shippingAddress?.city ?? null,
    shipping_address_state: shippingAddress?.state ?? null,
    shipping_address_postal_code: shippingAddress?.postal_code ?? null,
    shipping_address_country: shippingAddress?.country ?? null,
    amount_total: session.amount_total ?? 0,
    currency: session.currency ?? "usd",
    status: "paid",
    paid_at: new Date().toISOString(),
    ip_address: session.metadata?.ip ?? null,
    marketing_opt_in: session.metadata?.marketing_opt_in === "true",
    agreement_version: session.metadata?.agreement_version ?? "v1-2026-05-27",
    metadata: {
      // Creator attribution, frozen at payment time. The rate is stored
      // alongside the ref rather than looked up later, so raising the
      // program's share never silently restates what was already owed.
      creator_ref: session.metadata?.creator_ref || null,
      creator_share_pct: session.metadata?.creator_ref
        ? CREATOR_SHARE_PCT
        : null,
      creator_owed_cents: session.metadata?.creator_ref
        ? Math.round(((session.amount_total ?? 0) * CREATOR_SHARE_PCT) / 100)
        : null,
      checkout_consent_collection: session.consent ?? null,
      payment_link: session.payment_link ?? null,
    },
  };

  const { error } = await supabaseAdmin
    .from("anticipy_preorders")
    .upsert(row, { onConflict: "stripe_checkout_session_id" });

  if (error) {
    console.error("Failed to upsert pre-order row:", error);
    throw error;
  }

  // Revenue attribution, emitted server-side.
  //
  // The distinct_id is the SHA-256 of the email rather than the browser's
  // anonymous id, because that hash is what identifyByEmail() set on the
  // client at form submit — so this event lands on the same person as all
  // the pre-purchase browsing. The anonymous id from checkout metadata is
  // kept as a property for debugging stitch failures, not used as the key.
  //
  // Awaited rather than fire-and-forget: this handler runs in a serverless
  // function that can be frozen the instant it returns, which would drop an
  // in-flight request. captureServer never throws.
  try {
    await captureServer({
      distinctId: emailHashServer(email),
      event: "order_paid",
      properties: {
        amount_total_cents: session.amount_total ?? 0,
        amount_subtotal_cents: session.amount_subtotal ?? 0,
        amount_discount_cents: session.total_details?.amount_discount ?? 0,
        currency: session.currency ?? "usd",
        stripe_checkout_session_id: session.id,
        anonymous_distinct_id: session.metadata?.posthog_distinct_id || null,
        posthog_session_id: session.metadata?.posthog_session_id || null,
        marketing_opt_in: session.metadata?.marketing_opt_in === "true",
        shipping_country: row.shipping_address_country,
      },
      set: {
        lifecycle_stage: "customer",
        order_value_cents: session.amount_total ?? 0,
        stripe_customer_id: row.stripe_customer_id,
      },
      setOnce: {
        first_order_at: new Date().toISOString(),
      },
    });
  } catch (err) {
    console.error("Server-side order_paid capture failed:", err);
  }

  // The owner detail email is a convenience — a failure here must not cost the
  // customer their confirmation, so it is sent first and its error is only
  // logged. The owner still receives the customer's own email via the bcc
  // below, so a failure here does not lose the record of the sale.
  try {
    await sendOwnerPreorderNotification(email.toLowerCase(), {
      name: row.name,
      amount: row.amount_total,
      currency: row.currency,
      sessionId: session.id,
      paymentIntent: row.stripe_payment_intent_id,
      shippingCity: row.shipping_address_city,
      shippingState: row.shipping_address_state,
      shippingCountry: row.shipping_address_country,
    });
  } catch (err) {
    console.error("Pre-order owner notification failed:", err);
  }

  // The customer confirmation is not optional. Let it throw: the POST handler
  // turns that into a 500, which makes Stripe retry the event with backoff for
  // up to three days. The upsert above is idempotent on
  // stripe_checkout_session_id, so replaying the event is safe.
  //
  // This is deliberately louder than the previous behaviour, which caught the
  // error, logged it, and returned 200 — telling Stripe the pre-order was
  // fully handled while the customer got nothing.
  await sendPreorderConfirmation(email.toLowerCase(), {
    name: row.name,
    amount: row.amount_total,
    currency: row.currency,
    sessionId: session.id,
  });
}

async function handleChargeRefunded(charge: Stripe.Charge) {
  const paymentIntent =
    typeof charge.payment_intent === "string"
      ? charge.payment_intent
      : (charge.payment_intent?.id ?? null);

  if (!paymentIntent) return;

  const { error } = await supabaseAdmin
    .from("anticipy_preorders")
    .update({
      status: charge.refunded ? "refunded" : "partially_refunded",
      refunded_at: new Date().toISOString(),
      refund_reason: charge.refunds?.data?.[0]?.reason ?? null,
    })
    .eq("stripe_payment_intent_id", paymentIntent);

  if (error) {
    console.error("Failed to mark pre-order refunded:", error);
    throw error;
  }
}
