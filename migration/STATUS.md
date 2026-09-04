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
      Secrets   ANTICIPY_INTERNAL_KEY (a NEW dev value — see Cutover)
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

## Conformance, measured today

    HQ gate surface, LIVE production      36 passed,  0 failed
    HQ gate surface, Worker               35 passed,  1 skipped
    Whole HQ surface, Worker (with key)   97 passed,  1 skipped,  0 failed

The one skip is CLERK_HQ_JWT_KEY, which production has and the Worker does not.
It skips naming the variable rather than passing or failing quietly, because a
configuration gap and a port gap are different things and must not look alike.

## What is proven, and what is only ported

PROVEN against live production: every HQ route's UNAUTHENTICATED behaviour.
That is the whole gate — 401 vs 400 vs 410 vs 200 — which is the part most
easily got subtly wrong in a port and the part that is a security property.

PROVEN against real migrated data on the Worker: every route's authenticated
behaviour that the contract suite covers, plus the projections in
/internal/state, plus decryption of the real `secret_enc` row PocketBase wrote.

NOT PROVEN: that the Worker's authenticated RESPONSE BODIES equal production's,
field for field. That needs production's ANTICIPY_INTERNAL_KEY, which is not
available here. Under law 3 the signed-in half is therefore UNPROVEN however
carefully it was ported, and it is written here rather than in a commit message
that later reads as a green tick.

## Cutover — the two that will bite

1. THE HQ KEY MUST BE PRODUCTION'S, not the dev value now on the Worker.
   `cal_url` is `sha256(teamKey + personId)`, so every calendar somebody has
   already subscribed to is derived from the CURRENT key. Deploying with a
   different key silently kills every existing feed — the URL keeps returning
   404 and no calendar client reports why.

2. The website's `/internal/*` rewrites still point at Railway. Repoint them
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

  ANTICIPY_INTERNAL_KEY (production's)  the cutover, and the only thing that
                                        can prove the ported bodies match
  OPENROUTER_API_KEY                    /internal/assistant
  CLERK_HQ_JWT_KEY                      Clerk sign-in to HQ
  Cloudflare account 5b63e25e           holds anticipy-downloads (the Mac DMG);
                                        this login cannot see it

## Credentials to rotate before this is public

The Cerebras key, access code 77c04c26, everything pasted into this session's
.env.local, the PocketBase superuser password, and the dev
ANTICIPY_INTERNAL_KEY now on the Worker.
