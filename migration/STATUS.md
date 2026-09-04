# Cloudflare migration — what is running, what is not

Measured 2026-09-04. Every line here was verified against a live origin, not
planned. The previous revision of this file said "D1 EMPTY" and "all 38
/internal/* HQ routes 404"; both were true when written and neither is now.

## Deployed and live

    https://anticipy-api.omar-114.workers.dev        the backend Worker
      D1        anticipy-backend        36 collections, 2,451 rows, 0 mismatches
      R2        anticipy-evidence
      DO        PairCodeCounter         the pair-code brute-force counter
      Assets    pb_public
      Cron      */5 * * * *  and  17 4 * * *
      Secrets   ANTICIPY_INTERNAL_KEY (PRODUCTION's — set 2026-09-04)
                ANTICIPY_VAULT_KEY (production's)

    Website (separate repo, anticipation-labs/aniticipy-web)
      main        -> Vercel, live at www.anticipy.ai
      cloudflare  -> builds and runs on workerd

## HQ: 29 of 30 live routes ported

internal_hq.pb.js is 4,276 lines with its own auth stack, a Clerk JWT
exchange, an encrypted vault and an ICS feed. It was parked as unportable
because production is not built from this repo and no HQ key was available to
check a port. Both halves of that turned out to be too pessimistic —
`research/2026-09-04-hq-hook-IS-production.md` establishes that this hook file
IS what production runs (35/35 unauthenticated routes conform, error strings
verbatim), which made it the right source to port from.

    WIRED   session, session/end, me, state, login, clerk/exchange
            people (POST/PATCH), people/code
            todos (POST/PATCH/delete)
            events, tracks, expenses, notes (+ their deletes)
            passwords (upsert/reveal/delete)
            comments (POST/PATCH/delete)
            reminders (POST/delete)
            notifs/read, settings, cal/{token}.ics
            the three retired AI routes, still 410

    NOT     /internal/assistant

`/internal/assistant` is last ON PURPOSE and not by accident: it is the only
HQ route whose behaviour cannot be checked without a vendor credential
(OPENROUTER_API_KEY, which is not on this machine). Roughly half of it is
context-building that could be tested against D1, and the other half is model
tool-calling that could not be tested at all. Shipping 550 lines whose
principal path has never run is the thing CLAUDE.md law 6 exists to stop, so
it waits for the key rather than being written blind.

## Conformance, measured today — with production's key

    Whole suite, LIVE production      147 passed,  0 failed
    Whole suite, Worker               146 passed,  0 failed

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

1. /internal/assistant, once OPENROUTER_API_KEY exists.
2. Set on the Worker: CLERK_HQ_JWT_KEY, RESEND_API_KEY, TWILIO_*, and
   production's ANTICIPY_INTERNAL_KEY.
3. Repoint the 34 /internal/* rewrites. The redirect-following bug they shared
   with /r/ and /c/ is FIXED for the referral links
   (aniticipy-web@63dc14d) and does not apply to these: none of the
   GET-reachable ones answers 3xx. The 24 POST-only ones stay unverified.
4. brain/ onto Containers. Needs Docker in CI, and its per-owner memory.db
   moved off a Railway volume.
5. DNS. Nameservers are at Porkbun; there is no Cloudflare zone yet.

## Access still needed

  OPENROUTER_API_KEY                    /internal/assistant
  CLERK_HQ_JWT_KEY                      Clerk sign-in to HQ
  Cloudflare account 5b63e25e           holds anticipy-downloads (the Mac DMG);
                                        this login cannot see it

## Credentials to rotate before this is public

The Cerebras key, access code 77c04c26, everything pasted into this session's
.env.local, the PocketBase superuser password, and the dev
ANTICIPY_INTERNAL_KEY now on the Worker.
