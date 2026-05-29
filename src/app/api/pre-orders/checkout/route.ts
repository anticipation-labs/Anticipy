import { NextRequest, NextResponse } from "next/server";
import {
  stripe,
  PREORDER_PRICE_ID,
  AGREEMENT_VERSION,
  ALLOWED_SHIPPING_COUNTRIES,
} from "@/lib/stripe";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const agreementAccepted = body.agreementAccepted === true;
    const marketingOptIn = body.marketingOptIn !== false;

    if (!email || !EMAIL_REGEX.test(email)) {
      return NextResponse.json({ error: "Enter a valid email." }, { status: 400 });
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
            delivery_estimate: {
              minimum: { unit: "month", value: 3 },
              maximum: { unit: "month", value: 5 },
            },
          },
        },
      ],
      consent_collection: {
        terms_of_service: "required",
      },
      custom_text: {
        terms_of_service_acceptance: {
          message:
            "By placing this pre-order you agree to the [Pre-Order Agreement](https://www.anticipy.ai/pre-orders/agreement), [Terms of Service](https://www.anticipy.ai/terms), and [Privacy Policy](https://www.anticipy.ai/privacy). Estimated ship: August 2026.",
        },
        submit: {
          message:
            "Charges $149.99 USD now to lock in your Anticipy pendant at $50 off the $199 retail price.",
        },
      },
      allow_promotion_codes: true,
      metadata: {
        product_type: "preorder",
        agreement_version: AGREEMENT_VERSION,
        marketing_opt_in: marketingOptIn ? "true" : "false",
        ip,
        customer_name: name || "",
      },
      success_url: `${origin}/pre-orders/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/pre-orders/purchase?canceled=1`,
    });

    return NextResponse.json({ url: session.url, id: session.id }, { status: 200 });
  } catch (err: unknown) {
    console.error("Pre-order checkout error:", err);
    const message =
      err instanceof Error ? err.message : "Could not start checkout. Try again.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
