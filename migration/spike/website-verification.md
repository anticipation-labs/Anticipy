# VERIFIED: the website on Cloudflare Workers

Measured 2026-09-03 on the merged tree, wrangler 4.129.0,
@opennextjs/cloudflare 1.15.1, against a real workerd.

## The version that matters

@opennextjs/cloudflare raised its `next` peer to `>=15` at **1.16.0**.
**1.15.1** declares `^14.2.35 || ~15.0.7 || ...` and this site is on exactly
`next@14.2.35`. So leaving Vercel needs NO Next.js major upgrade. The dependency
is pinned; unpinning it means upgrading Next first.

## Route conformance, run against workerd (not just built)

    pages        60/60 correct
    API routes   84/84 run, zero 5xx caused by the port

Every non-200 is intended behaviour, verified by following each one:

    /internal/*        401  middleware passcode gate, still holding
    /analytics         307 -> /analytics/login          -> 200
    /engine            301 -> /app                      -> 200
    /pre-orders        307 -> /pre-orders/purchase       -> 200
    /ugc, /ugc/apply   307 -> anticipyfellowship.com     -> 200

The two 503s are routes doing their job, not breakage:
    /api/engine/deepgram-key   retired 2026-05-13, answers 503 by design
    /api/health                reports which env vars are set; placeholder env here

## Bundle size

    Total Upload   12,658 KiB
    gzip            2,689 KiB   (2.63 MB)

Workers limits are 3 MB gzip on free and 10 MB on paid. It fits either -- but
2.63 of 3 MB is **88% of the free ceiling**, so the free tier has ~370 KB of
headroom and any sizeable addition breaks the deploy. Paid is wanted anyway:
bcrypt login needs more than the free tier's 10 ms CPU (see
spike/bcrypt-on-workerd.md).

243 files in .open-next/assets.

## Two source changes were required

  src/app/api/geo/route.ts    runtime="edge" was the smaller half of the
                              problem -- it read x-vercel-ip-* headers that do
                              not exist off Vercel. Now reads cf-ipcity /
                              cf-region / cf-ipcountry first and the Vercel
                              names second, so it is correct on either platform
                              and needs no edit on cutover day.
                              REQUIRES the zone's "Add visitor location headers"
                              managed transform; without it the field prefills
                              empty, which is already its behaviour for an
                              unknown visitor.

  src/app/apple-icon.tsx      next/og + Satori + a resvg WASM binary, drawing a
                              capsule and a dot. Replaced by the same image as a
                              static 180x180 PNG rendered from the same
                              geometry -- one less WASM dependency in the hot
                              path, serving a file that never changes.

## What this does NOT prove

- Nothing is deployed. This is `wrangler dev --local` plus `deploy --dry-run`;
  no public URL exists and DNS is untouched.
- next.config.mjs still points 34 `/internal/*` rewrites at
  backend-production-61e0a.up.railway.app. The site runs on Cloudflare; HQ
  still answers from Railway until the backend moves. Those rewrites are the
  remaining tie to Railway on the website side.
- Real credentials were never used: Supabase vars were placeholders, so no
  route was exercised against real data.
