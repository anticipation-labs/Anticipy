# Stripe dashboard TODO for Anticipy pre-orders

Generated 2026-05-27. After the autonomous overnight build, three things remain that the Stripe MCP cannot do for you. They take about five minutes total.

## 1. Paste the Stripe secret key into env

Production live mode is already authenticated to the Aevoy Stripe account (`acct_1T3RNiBMF3gCPOse`). The product and price exist in LIVE mode:

- Product: `prod_Ub9YYo4OVgXz2L` (Anticipy Pendant Pre-Order, $149.99 USD)
- Price:   `price_1TbxFiBMF3gCPOsen6FHtsa8`

The web app needs your live secret key to talk to Stripe server-side. Get it from https://dashboard.stripe.com/apikeys.

Edit `.env.local` and paste:

```
STRIPE_SECRET_KEY=sk_live_REPLACE_ME
```

Then add the same key in Vercel project settings, scoped to Production and Preview. The build will throw at start time if it is missing.

## 2. Create the webhook endpoint in the Stripe dashboard

Go to https://dashboard.stripe.com/webhooks and click "Add endpoint".

- Endpoint URL: `https://www.anticipy.ai/api/webhooks/stripe`
- API version: latest
- Events: subscribe to two events
  - `checkout.session.completed`
  - `charge.refunded`

Click Add endpoint. On the resulting endpoint page, click "Reveal" on the signing secret. It starts with `whsec_`. Paste it into `.env.local` and into Vercel:

```
STRIPE_WEBHOOK_SECRET=whsec_REPLACE_ME
```

## 3. Confirm the live product and price look right

Open https://dashboard.stripe.com/products/prod_Ub9YYo4OVgXz2L. Verify:

- Name: Anticipy Pendant Pre-Order
- Status: Active, shippable
- Default price: $149.99 USD one-time
- Metadata: `product_type=preorder`, `estimated_ship=2026-08`, `retail_price_usd=199.00`, `preorder_price_usd=149.99`, `ships=us_canada`

If anything looks wrong, edit it in the dashboard. The code reads the price ID from env, so changing the price ID requires updating `STRIPE_PREORDER_PRICE_ID` in env too.

## 4. After deployment

After Vercel deploys the new branch, run a single $149.99 test purchase with a real card or a test card if you are still in test mode. Then refund yourself from the dashboard. Confirm:

- A row appears in `public.anticipy_preorders` in Supabase with `status=paid`.
- The pre-order confirmation email lands in your inbox.
- The Stripe receipt lands in your inbox.
- After the refund, the row updates to `status=refunded`.

If the row never appears, the webhook is misconfigured. Recheck the URL and the signing secret.
