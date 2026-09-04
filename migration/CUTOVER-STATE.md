# Has anything actually moved to Cloudflare? No. Measured 2026-09-04.

Everything is BUILT on Cloudflare and verified against production. NOTHING is
SERVING from it. Not one real request — from a person, a pendant, the Chrome
extension or the team's own HQ — reaches Cloudflare today.

That distinction is the whole point of this file, because "the migration is
done" and "the migration is ready" are one DNS change apart and read the same
in a status meeting.

## What actually serves production right now

    www.anticipy.ai          VERCEL         server: Vercel, x-vercel-cache HIT
    anticipy.ai DNS          PORKBUN        ns: {fortaleza,curitiba,maceio,
                                            salvador}.ns.porkbun.com
                                            -- there is no Cloudflare zone
    the backend API          RAILWAY        /api/health 200, HQ gated:true
    HQ, the team's dashboard RAILWAY        via 33 rewrites in next.config.mjs
    the reminder/digest cron RAILWAY        the only sweep that sends
    brain/ (the worker)      RAILWAY        `wrangler containers list` ->
                                            "No containers found"
    the Chrome extension     RAILWAY        extension/config.js:12
                                            DEFAULT_BASE = ...railway.app
    the Mac DMG              R2 (old acct)  reachable, /dl/... -> 200

## What exists on Cloudflare, serving nobody

    Worker  anticipy-api-b   every ported route; 146 passed / 0 failed against
                             LIVE, with production's key
    Worker  anticipy-api     WEDGED on an 18:39 build; do not use
    D1      anticipy-backend 36 collections, 2,451 rows, 0 mismatches
    R2      anticipy-evidence
    R2      anticipy-downloads  exists in the new account (created 02:59 today)
    DO      PairCodeCounter
    Cron    "17 4 * * *" only -- the sweep is OFF on purpose

## So what is actually finished

The hard half, and it is genuinely finished: the data is migrated and verified
row-by-row, every route is ported, and the Worker matches production on every
test in the suite while restoring seven security properties production's older
image lacks. `/internal/state` bodies were diffed field-for-field across 167
rows with zero mismatches. The vault decrypts PocketBase's own ciphertext.

What is NOT done is the part that makes any of it real: pointing traffic at it.

## The cutover, in the order it has to happen

Status after working steps 1-3 and 5 on 2026-09-04:

1. DONE. anticipy-api is canonical again — the "wedge" was propagation and
   cleared itself after ~50 minutes. 146 passed / 0 failed against it live.
   The temporary anticipy-api-b is deleted.

2. BLOCKED, needs CLERK_HQ_JWT_KEY. Still the only credential missing, and
   still the only difference from production anywhere in the test suite.

3. BLOCKED, and the pre-flight is why. Calling all 33 rewrite destinations on
   both origins found 2 that answered 200 on Railway and 404 here; both are now
   ported and all 33 match. But `FELLOWSHIP_ORIGIN` also drives two things the
   33 do not cover, and both are still broken on the Worker:

     /internal.html      production's HQ app is a strict SUPERSET of this
                         repo's. Serving the repo's would hand the team an
                         older app.
     /r/{code}, /c/{code} the referral hop. src/app/r/[code]/route.ts reads
                         FELLOWSHIP_ORIGIN too, so the flip would point the
                         referral handlers at a Worker that 404s them. Every
                         fellow link dies. This is money.

   Plus /internal/me/password, which production's app calls and the Worker
   does not have. Four routes total exist in the running image and in no hook
   file in this tree — see
   research/2026-09-04-two-routes-that-are-not-in-this-repo.md.

   THE FLIP IS ONE VARIABLE AND IT IS NOT READY. Do not set it yet.

4. Extension release. Unchanged, and yours to time.

5. BLOCKED ON 3, not on access. PocketBase turns out to expose GET /api/crons
   and `internal_hq_sweep` is listed there, so the swap is reachable without
   the Railway CLI. But it MUST be atomic with step 3: swapping crons while
   HQ traffic still goes to Railway would leave the team editing one database
   and being reminded from another.

6. brain/ onto Containers. Not started.

7. DNS, last.

## The one-line test for "is it live yet"

    curl -s -o /dev/null -D - https://www.anticipy.ai/ | grep -i '^server:'

`Vercel` means no. Nothing else in this file overrides that line.
