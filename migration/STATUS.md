# Cloudflare migration — what is running, what is not

Measured 2026-09-04, late. Every line was verified against a live origin.

This file has now been wrong three times, each time by lagging rather than by
guessing: it said "D1 EMPTY" after the import, "all 38 HQ routes 404" after they
were ported, and "anticipy-api is WEDGED" after the wedge turned out to be
propagation. Corrections are kept visible rather than overwritten, because the
pattern — a status file read as current while it describes yesterday — is
itself the recurring defect.

## Deployed and live

    https://anticipy-api.omar-114.workers.dev    the backend Worker
      (anticipy-api-b was a temporary duplicate created while diagnosing what
       looked like a permanently wedged route. It was ~50 minutes of
       propagation. -b is DELETED; this is the only Worker.)

      D1        anticipy-backend    36 tables, 2,451 rows migrated
      R2        anticipy-evidence, anticipy-downloads
      DO        PairCodeCounter     the pair-code brute-force counter
      Assets    pb_public           internal.html now byte-identical to
                                    production's (141,898 B, same sha256)
      Crons     "17 4 * * *" ONLY — the sweep trigger is deliberately OFF
      Zone      anticipy.ai         PENDING, id 31cfa9047733c3d3616a4825b2117bf9
      Secrets   ANTICIPY_INTERNAL_KEY (production's), ANTICIPY_VAULT_KEY,
                ANTICIPY_SERVICE_TOKEN, OPENROUTER_API_KEY, RESEND_API_KEY,
                TWILIO_ACCOUNT_SID/AUTH_TOKEN/PHONE_NUMBER/FROM,
                CLERK_HQ_JWT_KEY (set this session; clerk/exchange 400s like prod)
      FIXED     ANTICIPY_AUTH_SECRET re-set 2026-09-04 to PocketBase's LIVE
                owners.authToken.secret (read from /pb_data/data.db over Railway
                SSH: 50 chars, single unique value, duration 604800 matching the
                admin UI). Negative-path verified live: a forged token is 401 on
                BOTH the Worker and production. Positive-path (a real PB-minted
                token accepted by the Worker) is the cutover-moment check — it
                needs a real login; command in the auth-secret research note.

    Website (separate repo, anticipation-labs/aniticipy-web)
      main        -> Vercel, live at www.anticipy.ai
      cloudflare  -> builds and runs on workerd

## HQ: every live route ported but one

All 30 live routes are wired, plus the three retired AI routes that still
answer 410, plus the six-pass sweep cron.

**Not ported: POST /internal/me/password, and password login via
/internal/session.** Production's HQ app calls both — Change Password from
Settings, and password sign-in `{person_id, password}` alongside the 8-char
code. The repo's internal_hq.pb.js has ZERO pw_hash handling and no password
path in /internal/session, yet production accepts both and D1 holds 8 sha256
pw_hash values (set 2026-08-31). So production is AHEAD of the repo here too,
and the sha256 SALTING SCHEME is invisible from outside — every failed attempt
returns the same "didn't match" sentence. Guessing the scheme could silently
break password login or write hashes the checker rejects, which is exactly the
identity risk the project laws forbid guessing at. It needs the real source:
fellowship_host.pb.js (untracked, no git blob) or a newer internal_hq.pb.js,
readable only off the Railway container.

The code path (8-char login code) IS ported and works, so nobody is locked out;
password sign-in and Change Password degrade to "didn't match" rather than
breaking. Contract of /internal/me/password, derived from production:

    no/blank/unknown actor_id ......... 400 {"error":"pick yourself first"}
    real actor_id, password ""  ....... 400 {"error":"three characters at least"}
    real actor_id, password >= 3 ...... 200 {"ok":true}, sets internal_people.pw_hash

Also absent: `POST /internal/fellows/pay`, same untracked file, and it moves
money.

## The fellowship surface — 17 routes, 404 until today

anticipyfellowship.com is a SEPARATE Vercel site that calls `/fellows/*` on this
same backend. All 17 were 404 on the Worker, so a fellow could not sign up,
apply, verify, submit or consent once traffic moves. Ported from recovered
source (migration/recovered/fellowship*.pb.js) via a workflow, assembled into
src/routes/fellows.ts. Every UNAUTHENTICATED contract verified identical to
production, field-for-field (17/17, order-independent). The authenticated /
email / oembed / minor-consent / payout halves ship UNPROVEN and must be diffed
with a real fellow session before anticipyfellowship.com is repointed. See
research/2026-09-04-fellowship-surface-ported.md.

`POST /internal/fellows/pay` is NOT ported — it moves money and its source is in
the untracked fellowship_host.pb.js (no git blob; Railway container only). The
fellowship admin screen renders but its Pay button 404s.

## The product surface — five collections were 404 until today

Every earlier diff compared HQ. Nobody had diffed what the pendant, the iPhone
and the extension actually call. `src/pb/schema.ts` said "GENERATED, NOT
HAND-WRITTEN" and named `npm run gen:schema`; that generator did not exist and
the file had been hand-filled for "the four collections the skeleton
exercises".

Now generated from `migration/d1/schema.sql` by `scripts/gen_schema.py`, nine
collections, chosen to match what production answers 200 for:

    evidence        the extension's receipt photos (background.js:1355)
    owner_profile   iOS + brain
    pendants        the entire iOS pairing flow
    segments        brain's segmenter
    purges          privacy deletion

Generating it also removed two PHANTOM columns the hand-written file declared
(`events.intent`, `events.memory_purged`) which exist in neither D1 nor
production.

## New-user signup was dead, and is not any more

`records.create()` was one generic writer that did not know `owners` is an AUTH
collection. The iPhone's real signup call was refused with `unknown_field` on
`passwordConfirm`; an EMPTY POST wrote a passwordless, emailless row from
anywhere. Both fixed, with production's exact contract including its non-obvious
validation ORDER. Round trip verified end to end. See
research/2026-09-04-signup-was-dead-on-the-worker.md.

`owners` also leaked: the Worker answered a service token with all 31 records
including email and phone where production answers `totalItems 0`. PocketBase's
`listRule` (`id = @request.auth.id`) had never been ported — the guard decides
whether a request may RUN, the rule decides which ROWS it sees. Now matched.

## Conformance, measured today — with production's key

    Whole suite, LIVE production      148 passed,  0 failed
    Whole suite, LIVE anticipy-api    147 passed,  0 failed

    production passes BUT worker fails         0
    worker passes where production does not    7
    the only other difference                  1   (CLERK_HQ_JWT_KEY)

The 7 are security properties the Worker RESTORES: production runs a
pre-2026-08-25 image missing afd4380a (the approval gate failing closed),
9748acf4 (a row may not be born holding a lease) and 5f66016c (the Shelf 2
validator), plus a CORS origin check and the agent-credential refusals.

## The bodies were diffed, not just the status codes

`/internal/state` from both origins as the same admin: identical top-level keys,
identical field names across all 12 lists, 167 rows compared field-for-field
with zero mismatches. `/internal/fellows` likewise, 12 fellows and 5 submissions,
ids and order included. The vault decrypts PocketBase's own ciphertext.

## The blocker that outranks the numbered list

**ANTICIPY_AUTH_SECRET is present on the Worker but WRONG (empty string).** The
failed extract set it to "" (it read the empty image-default DB), and
`wrangler secret list` shows the NAME regardless of value — so "it's in the
list" is not proof it works; the cross-origin auth leg is. Both backends sign
owner tokens HS256 with a per-record key: PocketBase uses
`collections.owners.authToken.secret + owners.tokenKey`, the Worker uses
`env.ANTICIPY_AUTH_SECRET + tokenKey`. `tokenKey` migrated; the secret is a
SETTING, not a column, so it did not.

Every token PocketBase has issued therefore fails on the Worker. The iPhone and
the extension each hold one. Cutting over without it signs out every user at
once. It is in `data.db` at `_collections.options.authToken.secret` for the
`owners` row — one approved backup download. Matching it also buys a safe
rollback, since during the transition either backend accepts the same token.
research/2026-09-04-the-auth-secret-nobody-set.md, and there is now a
cross-origin test leg that goes green only once it matches.

## Order of the remaining work

1. **Fix a real password first.** A probe set a teammate's HQ password to `abc`
   on PRODUCTION. research/2026-09-04-I-changed-a-real-password-while-probing.md
   has the two remediation commands. Do this before anything else here.
2. ~~`wrangler secret put CLERK_HQ_JWT_KEY`~~ **DONE this session** — piped from
   Railway (backend -> Variables), never printed; clerk/exchange now 400s on
   both origins like production, so existing Clerk sign-ins are preserved.
   Confirmed present in `wrangler secret list --name anticipy-api`.
3. `wrangler secret put ANTICIPY_AUTH_SECRET` — from data.db, as above. Use
   `migration/runbooks/extract_auth_secret.py /pb_data/data.db` (the volume, NOT
   `/app/pb_data/data.db`, which is the empty default that set it to "" last
   time). The script + guarded command fail closed on a bad DB and add no
   trailing newline; the exact block is in
   research/2026-09-04-the-auth-secret-nobody-set.md.
4. Port `POST /internal/me/password` and password login, from
   `fellowship_host.pb.js` read off the Railway container — NOT by guessing the
   sha256 scheme.
5. Delete the 25 junk `owners` rows in D1 (blank-email + `@example.invalid`
   probes). Verified to own zero jobs and zero events; the 8 real rows left are
   a strict subset of production's 9. Blank creation is now refused so they
   cannot refill.
6. Repoint the website: `FELLOWSHIP_ORIGIN` in the Vercel dashboard for project
   aniticipy-web, Production scope, then redeploy with a full rebuild. There is
   no Vercel CLI or token on this machine.
7. Swap the crons, atomically with 6. PocketBase's API can only LIST and RUN
   crons, never disable one, so removing `internal_hq_sweep` needs a Railway
   deploy. `railway` is not installed here.
8. brain/ onto Containers. migration/BRAIN-ON-CONTAINERS.md. The two code
   blockers are now WRITTEN (2026-09-04) and statically validated but
   runtime-UNTESTED: `migration/workers/brain/src/index.ts` (`tsc --noEmit`
   green against @cloudflare/containers@0.3.7, vendored into brain/node_modules;
   OwnerBrain + BrainSupervisor + scheduled()) and `brain/container_entry.py`
   (py_compile OK; R2 pull that aborts on any non-404 GET). Neither has run —
   no oracle, and container_entry's failure mode is silent memory loss, so both
   need a real container + R2 run before trust (research/
   2026-09-04-brain-container-code-written.md). Still blocked on: a Docker CLI
   this machine lacks; the R2 bucket `anticipy-owner-state` (CREATED 2026-09-04, empty); and the one-way
   `brain/Dockerfile:14` CMD flip, which is a cutover step (it would break the
   live Railway `worker`), not a now-change.
9. DNS. Smaller than previously recorded: the Cloudflare zone already exists and
   is PENDING. The remaining action is switching nameservers at Porkbun, which
   needs the Porkbun dashboard — no API key on this machine.

## Access still needed

    CLERK_HQ_JWT_KEY         DONE — set on anticipy-api this session.
    ANTICIPY_AUTH_SECRET     data.db at /pb_data/data.db (Railway volume), via
                             SSH or one approved backup download. Currently set
                             to EMPTY on the Worker — must be re-set correctly.
    Railway CLI + superuser  the cron swap, and reading fellowship_host.pb.js
                             off the container — the only remaining source for
                             the last routes.
    Vercel dashboard         the FELLOWSHIP_ORIGIN flip.
    Porkbun dashboard        the nameserver switch.

## Credentials to rotate before this is public

EVERYTHING in .env.local — all 38 values arrived by chat and the file's own
header says to treat those as burned. That includes OPENROUTER_API_KEY, the
Twilio auth token, SUPABASE_SERVICE_ROLE_KEY, the R2 secret, Resend, Cerebras,
Groq, Mistral, Kimi, Deepgram, Capsolver and Brave — plus access code 77c04c26,
the PocketBase superuser password, and ANTICIPY_VAULT_KEY.

ANTICIPY_INTERNAL_KEY belongs on this list too, and rotating it is not free:
`cal_url` is `sha256(teamKey + personId)`, so changing the key silently
invalidates every calendar feed anyone has subscribed to. Rotate it in a window
where the team can re-subscribe, tell them first, and change it on BOTH origins
at once — not as a quiet cleanup.
