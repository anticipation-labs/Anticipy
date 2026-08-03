import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// One-time setup endpoint. Requires the setup token; remove after use.
const SETUP_TOKEN =
  "b7c1f4e9a2d84f60b3a5c8e7d1f09a4b6c2e8d5f7a1b9c4e0d3f6a8b5c7e2d19";

const TIERS = [
  { code: "ANTICIPY65", percentOff: 65 },
  { code: "ANTICIPY60", percentOff: 60 },
  { code: "ANTICIPY50", percentOff: 50 },
  { code: "ANTICIPY25", percentOff: 25 },
  { code: "ANTICIPY100", percentOff: 100 },
];

export async function POST(request: NextRequest) {
  if (request.headers.get("x-setup-token") !== SETUP_TOKEN) {
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  }

  const results: Array<{ code: string; percentOff: number; id: string }> = [];
  for (const tier of TIERS) {
    const coupon = await stripe.coupons.create({
      percent_off: tier.percentOff,
      duration: "once",
      name: `${tier.percentOff}% off pre-order`,
    });
    const promo = await stripe.promotionCodes.create({
      promotion: { type: "coupon", coupon: coupon.id },
      code: tier.code,
    });
    results.push({ code: promo.code, percentOff: tier.percentOff, id: promo.id });
  }

  return NextResponse.json({ created: results }, { status: 200 });
}
