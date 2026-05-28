import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { stripe } from "@/lib/stripe";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { sendPreorderConfirmation } from "@/lib/email";

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

  try {
    await sendPreorderConfirmation(email.toLowerCase(), {
      name: row.name,
      amount: row.amount_total,
      currency: row.currency,
      sessionId: session.id,
    });
  } catch (err) {
    console.error("Pre-order confirmation email failed:", err);
  }
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
