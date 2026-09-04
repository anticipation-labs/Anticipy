# Cloudflare migration — what is running, what is not

Measured 2026-09-04. Every line here was verified against a live origin, not
planned. The previous revision of this file said "D1 EMPTY" and "all 38
/internal/* HQ routes 404"; both were true when written and neither is now.

## Deployed and live

    https://anticipy-api-b.omar-114.workers.dev      the backend Worker  <- USE THIS
    https://anticipy-api.omar-114.workers.dev        WEDGED: serves an 18:39
      build and will not update. Everything below is deployed to BOTH; only
      -b actually serves it. See
      research/2026-09-04-the-workers-dev-url-is-wedged.md before cutover.
      D1        anticipy-backend        36 collections, 2,451 rows, 0 mismatches
      R2        anticipy-evidence
      DO        PairCodeCounter         the pair-code brute-force counter
      Assets    pb_public
      Cron      */5 * * * *  and  17 4 * * *
      Secrets   ANTICIPY_INTERNAL_KEY (PRODUCTION's), ANTICIPY_VAULT_KEY,
                ANTICIPY_SERVICE_TOKEN, OPENROUTER_API_KEY, RESEND_API_KEY,
                TWILIO_ACCOUNT_SID/AUTH_TOKEN/PHONE_NUMBER/FROM
      Crons     "17 4 * * *" ONLY. The sweep is off until cutover — see below.

    Website (separate repo, anticipation-labs/aniticipy-web)
      main        -> Vercel, live at www.anticipy.ai
      cloudflare  -> builds and runs on workerd

## HQ: every live route ported

internal_hq.pb.js is 4,276 lines with its own auth stack, a Clerk JWT exchange,
an encrypted vault and an ICS feed. All 30 live routes are wired, plus the
three retired AI routes that still answer 410, plus the six-pass sweep cron.

`/internal/assistant` was last because it was the only route whose behaviour
could not be checked without a vendor credential. With OPENROUTER_API_KEY it
now can be, and is: asked what is on the board it answers off live D1 rather
than telling the person to go and look — which was the whole point of giving it
the board in the first place.

TestHQPortProgressIsHonest keys on (METHOD, path) and reads all three dispatch
forms index.ts uses, so "ported" cannot drift from the source. It found two
bugs in ITSELF while the port finished, both fixed rather than loosened.

## Conformance, measured today — with production's key

    Whole suite, LIVE production                147 passed,  0 failed
    Whole suite, LIVE anticipy-api-b            146 passed,  0 failed

    236 tests on both. Per-test diff:

      production passes AND worker passes      146
      production passes BUT worker fails         0
      worker passes where production does not    7
      the only other difference                  1   (CLERK_HQ_JWT_KEY)

The 7 are security properties the Worker RESTORES: production runs a
pre-2026-08-25 image missing afd4380a (the approval gate failing closed),
9748acf4 (a row may not be born holding a lease) and 5f66016c (the Shelf 2
validator), plus a CORS origin check and the agent-credential refusals.

The 1 is `/internal/clerk/exchange`, which needs CLERK_HQ_JWT_KEY. Production
has it; the Worker does not. It SKIPS naming the variable rather than passing
or failing quietly, because a configuration gap and a port gap must not look
alike.

## The bodies were diffed, not just the status codes

This file previously said the authenticated response bodies were UNPROVEN
because they could not be compared without production's key. They can now, and
they were. `/internal/state` fetched from both origins as the same admin:

    top-level keys                       identical
    field names across all 12 lists      identical
    167 rows compared field-for-field    0 mismatches

The only row-count difference was 8 todos plus 1 activity row that production's
08:00 cron created after the migration snapshot — and the Worker's own repeat
motor, run once, produced the same 8: 146 vs 146 todos, identical sets of
(title, track, due, status).

## The HQ sweep cron

Six passes, all ported: the remind_at bell, past-due follow-ups,
internal_reminders, the notification digest, the research-slot backstop and the
repeat motor. It was previously a skeleton reading `to` and `text` columns that
internal_reminders does not have, so it ran every five minutes and did nothing
without erroring. See research/2026-09-04-the-sweep-was-a-silent-noop.md.

## Cutover

1. THE HQ KEY — DONE, and the hazard it guarded is verified closed rather than
   merely avoided. `cal_url` is `sha256(teamKey + personId)`; the token the
   Worker now returns is byte-identical to production's for the same person, so
   every calendar already subscribed survives. Had a different key shipped,
   those feeds would have 404'd with no client reporting why.

2. TWO SWEEP CRONS ARE NOW LIVE AT ONCE, against SEPARATE databases, so nothing
   duplicates today. At cutover exactly one must remain: two sweeps against one
   database is two nudges and two laydowns.

3. The website's `/internal/*` rewrites still point at Railway. Repoint them
   only after the assistant lands or is accepted as absent, since the page
   calls it.

## Order of the remaining work

1. UNWEDGE OR ABANDON anticipy-api. Either fix the route in the Cloudflare
   dashboard or accept anticipy-api-b as the name and point the cutover there.
   Nothing outside this repo depends on the old hostname yet.
2. Set CLERK_HQ_JWT_KEY — the last missing secret, and the only remaining
   difference from production in the whole suite.
3. Repoint the 34 /internal/* rewrites. The redirect-following bug they shared
   with /r/ and /c/ is FIXED for the referral links
   (aniticipy-web@63dc14d) and does not apply to these: none of the
   GET-reachable ones answers 3xx. The 24 POST-only ones stay unverified.
4. brain/ onto Containers. Needs Docker in CI, and its per-owner memory.db
   moved off a Railway volume.
5. DNS. Nameservers are at Porkbun; there is no Cloudflare zone yet.

## Access still needed

  CLERK_HQ_JWT_KEY                      Clerk sign-in to HQ. The ONLY
                                        credential still missing.
  Cloudflare account 5b63e25e           holds anticipy-downloads (the Mac DMG);
                                        this login cannot see it

## Credentials to rotate before this is public

EVERYTHING in .env.local — all 38 values arrived by chat and the file's own
header says to treat those as burned. That includes OPENROUTER_API_KEY, the
Twilio auth token, SUPABASE_SERVICE_ROLE_KEY, the R2 secret, Resend, Cerebras,
Groq, Mistral, Kimi, Deepgram, Capsolver and Brave — plus access code 77c04c26,
the PocketBase superuser password, and ANTICIPY_VAULT_KEY.

ANTICIPY_INTERNAL_KEY BELONGS ON THIS LIST TOO, and rotating it is not free:
`cal_url` is `sha256(teamKey + personId)`, so changing the key silently
invalidates every calendar feed anyone has subscribed to. Rotate it during a
window where the team can re-subscribe, tell them first, and change it on BOTH
origins at once — not as a quiet cleanup.
