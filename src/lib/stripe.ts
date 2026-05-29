import Stripe from "stripe";

let _stripe: Stripe | null = null;

export function getStripe(): Stripe {
  if (_stripe) return _stripe;
  const secretKey = process.env.STRIPE_SECRET_KEY;
  if (!secretKey) {
    throw new Error(
      "STRIPE_SECRET_KEY is not set. Add it to .env.local and Vercel env."
    );
  }
  _stripe = new Stripe(secretKey, {
    apiVersion: "2026-05-27.dahlia",
    appInfo: {
      name: "Anticipy Web",
      url: "https://www.anticipy.ai",
    },
  });
  return _stripe;
}

export const stripe = new Proxy({} as Stripe, {
  get(_target, prop) {
    const client = getStripe();
    const value = (client as unknown as Record<string | symbol, unknown>)[prop];
    if (typeof value === "function") {
      return (value as (...args: unknown[]) => unknown).bind(client);
    }
    return value;
  },
});

export const PREORDER_PRICE_ID =
  process.env.STRIPE_PREORDER_PRICE_ID ?? "price_1TbxFiBMF3gCPOsen6FHtsa8";

export const PREORDER_PRODUCT_ID =
  process.env.STRIPE_PREORDER_PRODUCT_ID ?? "prod_Ub9YYo4OVgXz2L";

export const AGREEMENT_VERSION = "v2-2026-05-28";

export const ALLOWED_SHIPPING_COUNTRIES: Array<"US" | "CA"> = ["US", "CA"];
