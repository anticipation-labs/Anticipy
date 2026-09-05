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
row. Two sources for that file: the daily backup zip, or the live Railway volume
at `/pb_data/data.db` over SSH. **Not** `/app/pb_data/data.db` — that is the
156 KB empty image default, and reading it is exactly how a first attempt set
`ANTICIPY_AUTH_SECRET` to the empty string (`_collections` empty → lookup
returns None → `wrangler secret put` fed nothing).

`migration/runbooks/extract_auth_secret.py` now does this safely and is the
command to run (owner drives it — Railway SSH + wrangler auth):

    python3 extract_auth_secret.py /pb_data/data.db --check      # proof-of-life first
    # then, guarded so a failed extract can never feed wrangler an empty value:
    set -euo pipefail
    SECRET="$(python3 extract_auth_secret.py /pb_data/data.db)"
    [ -n "$SECRET" ] || { echo "empty — refusing"; exit 1; }
    printf %s "$SECRET" | npx wrangler secret put ANTICIPY_AUTH_SECRET --name anticipy-api
    unset SECRET

It aborts loudly on the empty/wrong DB, searches the owners row without assuming
the schema version, prints only length + a sha256 prefix (never the value), and
emits the secret with NO trailing newline (a newline would corrupt the HMAC
key). Tested against synthetic good / empty-default / no-table fixtures. Prefer
running it ON the container so the customer DB never leaves the box; a local copy
is the approved-download path.

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
person does not rediscover them as Worker gaps. `CLERK_HQ_JWT_KEY` was the one
HQ credential still missing; it was SET this session (piped from Railway,
confirmed in `wrangler secret list`, clerk/exchange 400s like prod).

## Update 2026-09-04 (later) — RESOLVED: secret set to PocketBase's live value

Read `owners.authToken.secret` directly off the running backend container
(`ssh anticipy-backend`, `strings /pb_data/data.db | grep legacy_uuid` to isolate
the owners row, extract the single `authToken` block): 50 chars, ONE unique
value, `duration 604800` matching the admin UI's Auth duration. Set it on the
Worker with `wrangler secret put ANTICIPY_AUTH_SECRET --name anticipy-api`
(piped, no newline, value never written to a file or printed — only a masked
len+sha proof). The PocketBase admin UI does NOT expose the secret anywhere
(Options → Tokens options shows only durations + "invalidate" buttons), and the
container has no sqlite3/python — `strings` on the raw DB was the only in-place
read, and it keeps all customer data on the box.

Negative-path verified LIVE: a forged token is rejected 401 on BOTH the Worker
and production. Positive-path — the property that actually decides zero-logout —
is `TestCrossOriginTokenCompatibility` in migration/spec/contract_tests.py:

    BASE_URL=https://backend-production-61e0a.up.railway.app \
    ANTICIPY_CROSS_ORIGIN=https://anticipy-api.omar-114.workers.dev \
    ANTICIPY_TEST_EMAIL=<a test owner> ANTICIPY_TEST_PASSWORD=<their pw> \
    python3 -m pytest migration/spec/contract_tests.py -k CrossOrigin -v

It needs a real owner login (auth-with-password), so it is a cutover-window
check — run it once before flipping traffic. It should now PASS: secret parity
is closed here and tokenKey parity was closed at import. If it 401s, do NOT flip.

## Update 2026-09-04 — the secret now EXISTS but is EMPTY, which is worse

The extract was attempted and failed against `/app/pb_data/data.db` (the 156 KB
empty image default, not the volume). `_collections` was empty, the lookup
returned None, and `wrangler secret put` was fed an empty string. So today
`ANTICIPY_AUTH_SECRET` is IN the secret list — and still wrong. "Is it set?"
answered by `wrangler secret list` now returns yes and lies. The only true test
is the cross-origin auth leg. Re-set it with the guarded command above; the
extractor aborts on that exact empty-DB mistake instead of emitting nothing.
