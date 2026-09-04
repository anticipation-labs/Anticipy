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

1. UNWEDGE OR RENAME. anticipy-api will not update; anticipy-api-b serves the
   current build. Either fix the route in the dashboard or accept -b as the
   name. See research/2026-09-04-the-workers-dev-url-is-wedged.md.
2. SET CLERK_HQ_JWT_KEY. The last missing credential, and the only remaining
   difference from production anywhere in the suite.
3. REPOINT THE WEBSITE. next.config.mjs:10 FELLOWSHIP_ORIGIN, which 33
   rewrites read. One variable.
4. REPOINT THE EXTENSION. extension/config.js:12 DEFAULT_BASE. This one ships
   to users' browsers, so it is a release, not a deploy -- and the currently
   installed build is a DIFFERENT build from what this repo contains
   (research/2026-09-04-production-is-not-this-repo.md).
5. SWAP THE CRONS, in ONE change: add "*/5 * * * *" to the Worker and remove
   PocketBase's. Two sweeps against one database is two nudges and two texts.
6. brain/ ONTO CONTAINERS. Not started. Needs Docker in CI and the per-owner
   memory.db off a Railway volume.
7. DNS, LAST. Nameservers move to Cloudflare, or the records point at the
   Worker. Nothing above needs DNS; DNS needs everything above.

## The one-line test for "is it live yet"

    curl -s -o /dev/null -D - https://www.anticipy.ai/ | grep -i '^server:'

`Vercel` means no. Nothing else in this file overrides that line.
