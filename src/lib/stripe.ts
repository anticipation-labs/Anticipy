import Stripe from "stripe";

const secretKey = process.env.STRIPE_SECRET_KEY;

if (!secretKey && process.env.NODE_ENV !== "test") {
  throw new Error(
    "STRIPE_SECRET_KEY is not set. Add it to .env.local and Vercel env."
  );
}

export const stripe = new Stripe(secretKey ?? "sk_test_placeholder", {
  apiVersion: "2026-05-27.dahlia",
  appInfo: {
    name: "Anticipy Web",
    url: "https://www.anticipy.ai",
  },
});

export const PREORDER_PRICE_ID =
  process.env.STRIPE_PREORDER_PRICE_ID ?? "price_1TbxFiBMF3gCPOsen6FHtsa8";

export const PREORDER_PRODUCT_ID =
  process.env.STRIPE_PREORDER_PRODUCT_ID ?? "prod_Ub9YYo4OVgXz2L";

export const AGREEMENT_VERSION = "v1-2026-05-27";

export const ALLOWED_SHIPPING_COUNTRIES: Array<"US" | "CA"> = ["US", "CA"];
