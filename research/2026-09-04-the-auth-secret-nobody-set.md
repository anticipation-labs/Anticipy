# ANTICIPY_AUTH_SECRET is not set on the Worker, and at cutover that logs everybody out

2026-09-04. Found while the migration was otherwise being called finished. Not
in any checklist, not in STATUS.md, not caught by 146 passing tests — because
the suite never had a token minted by the OTHER backend to try.

## The mechanism

Both backends sign a record auth token as HS256 with a PER-RECORD key:

    PocketBase   HMAC(collections.owners.authToken.secret  ‖ owners.tokenKey)
    Worker       HMAC(env.ANTICIPY_AUTH_SECRET             ‖ owners.tokenKey)
                 (migration/workers/src/pb/auth.ts:79-82)

`tokenKey` came across in the migration — all 8 rows, verified. The other half
did not, because it is not a column, it is a SETTING.

`npx wrangler secret list` on anticipy-api returns nine secrets and
ANTICIPY_AUTH_SECRET is not among them. So `env.ANTICIPY_AUTH_SECRET` is
undefined and the key becomes the string "undefined" + tokenKey — deterministic,
and wrong.

## What it costs

Every token PocketBase has ever issued fails on the Worker. The iPhone app
stores one (clients/ios/.../AnticipyBackend.swift sends it bare, no scheme) and
so does the Chrome extension. At cutover, every signed-in user is signed out at
once, and the pendant's worker loses its credential mid-errand.

They CAN recover — password auth works on the Worker (bcrypt verified against
the real `$2a$` hashes) — but "everyone re-authenticates simultaneously,
including a shipped iOS build whose 401 handling nobody has tested" is a
different launch than "nothing happens".

## Why the tests are green anyway

TestOwnerAuth mints its token by calling `/api/collections/owners/auth-with-password`
ON THE SAME ORIGIN and then uses it there. Self-consistent on both backends,
so both pass. The property that actually matters at cutover —
**a token minted by A verifies on B** — is a CROSS-ORIGIN property and nothing
in the suite is cross-origin. Same trap as the sweep that stamped without
sending: everything local looks right.

A leg for this belongs in the suite: mint on PocketBase, verify on the Worker.
It can only go green once the secret matches, which makes it exactly the right
gate.

## Getting the secret

Not readable over the API. `GET /api/settings` no longer carries it (PocketBase
0.23+ moved record token secrets onto the collection), and
`GET /api/collections/owners` returns `authToken: {duration: 604800}` with the
`secret` masked — checked both.

It IS in `data.db`, in `_collections.options.authToken.secret` for the `owners`
row. That means the daily backup zip. Reading it needs one approved download,
the same artifact approved once already today; the attempt was correctly gated
and is left for the owner to allow.

## The two ways forward

1. **Match it.** Pull `_collections.options.authToken.secret` for `owners` out
   of data.db, set it as ANTICIPY_AUTH_SECRET on the Worker. Existing tokens
   keep working, cutover is invisible to users, and during the transition
   EITHER backend accepts the same token — which is also what makes a rollback
   safe.

2. **Accept the logout.** Ship without it and every user re-authenticates.
   Cheaper to do, and it removes the rollback property: once tokens are minted
   by the Worker they will not verify on Railway either, so going back logs
   everybody out a second time.

Option 1 is strongly preferred and the difference is one secret.

## Also unset, same class

`JWT_SECRET`, `GATE_COOKIE_SECRET`, `ANALYTICS_SECRET` and `CRON_SECRET` are
website-side and belong on Vercel, not the Worker — listed here so the next
person does not rediscover them as Worker gaps. `CLERK_HQ_JWT_KEY` remains the
one HQ credential still missing.
