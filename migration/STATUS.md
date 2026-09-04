# Cloudflare migration — what is running, what is not

Measured 2026-09-04. Every line here was verified, not planned.

## Deployed and live

    https://anticipy-api.omar-114.workers.dev        the backend Worker
      D1        anticipy-backend-staging   26 tables, 46 indexes, EMPTY
      R2        anticipy-evidence          empty
      DO        PairCodeCounter            the pair-code brute-force counter
      Assets    pb_public                  10 files, all serving
      Cron      */5 * * * *  and  17 4 * * *

    Website (separate repo, anticipation-labs/aniticipy-web)
      main        -> Vercel, live at www.anticipy.ai, 159/159
      cloudflare  -> builds and runs on workerd, 158/158, 2.62 MB gzip

## What the Worker actually implements

  YES   GET  /api/health
  YES   the generic records API: /api/collections/{c}/records  (+ filter DSL)
  YES   POST /api/collections/owners/auth-with-password, /auth-refresh
  YES   /api/realtime  (guarded)
  YES   /api/files/{c}/{id}/{name}  evidence host on R2, share window ported
  YES   pb_public static assets
  YES   the four policy middlewares: guard, workflow_guard, research_lane,
        owner_profile_owner

  NO    the ~50 custom hook routes. All return 404:
          /auth/reset/request, /auth/reset/confirm
          /agent/register, /agent/key, /agent/llm, /agent/solve-captcha,
            /agent/upgrade-credential
          /me/delete, /me/phone/remove, /me/profile/upsert
          /evidence/share
          /worker/owners
          /admin/purge-audit
          /auth/claim
          the Twilio SMS inbound webhook
          all 38 /internal/* HQ routes

## Conformance, measured

Same suite, both backends, `-m "not destructive"`:

    PocketBase   190 tests | 16 failed | 77 passed | 70 skipped | 27 xfailed
    Worker       190 tests | 37 failed | 12 passed |132 skipped |  8 xfailed

    PocketBase PASS and Worker PASS :  12
    PocketBase PASS but Worker SKIP :  28   <- D1 is empty; not a port gap
    PocketBase PASS but Worker FAIL :  37   <- THE REAL PORT GAPS

The 37 are exactly the hook routes above. The data layer is ported; the route
layer largely is not.

The 28 skips are not failures: fixtures that need a live owner, agent or job
skip against an empty D1. They become real tests the moment data is imported,
and they are the reason the export matters before any further porting.

## The 16 PocketBase failures are not port bugs

They assert security properties the DEPLOYED PocketBase does not have --
production runs a pre-2026-08-25 workflow_guard.pb.js missing afd4380a
(approval gate fails closed), 9748acf4 (a row may not be born holding a lease)
and 5f66016c (the Shelf 2 validator). The Worker, built from this repo, would
RESTORE them. See research/2026-09-04-production-is-not-this-repo.md.

## Order of the remaining work

1. EXPORT PocketBase. Needs superuser credentials. Unlocks the 28 skips and is
   the prerequisite for everything else. Re-encrypt internal_passwords FIRST:
   secret_enc is Go AES keyed by ANTICIPY_VAULT_KEY and WebCrypto cannot read
   it, so a copy taken without that key is a vault of unreadable ciphertext.
2. PORT THE HOOK ROUTES, in this order by risk:
     a. /auth/reset/*, /me/delete           identity and the privacy promise
     b. /agent/*                            the extension's whole lifecycle
     c. /evidence/share + /api/files        currently 404 in production too
     d. the Twilio inbound webhook          TWILIO_AUTH_TOKEN signature check
     e. /internal/*                         HQ: 3,185 code lines, its own auth
                                            stack, a Clerk exchange, an ICS feed
3. REPOINT the website's 34 /internal/* rewrites, AFTER fixing the
   redirect-following bug in migration/spike/rewrite-redirect-following.md.
4. brain/ onto Containers. Needs Docker in CI, and its in-memory state moved.

## Access still needed

  PocketBase superuser        the export. Blocks 1, and therefore everything.
  ANTICIPY_VAULT_KEY          the vault. Irreversible if missed.
  Railway logs                why 3 hook files are absent from the running image
  Cloudflare account 5b63e25e holds anticipy-downloads (the Mac DMG); this
                              login cannot see it
