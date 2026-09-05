# Has anything actually moved to Cloudflare? No. Measured 2026-09-04, late.

Everything is BUILT on Cloudflare and verified against production. NOTHING is
SERVING from it. Not one real request — from a person, a pendant, the Chrome
extension or the team's own HQ — reaches Cloudflare today.

That distinction is the whole point of this file, because "the migration is
done" and "the migration is ready" are one DNS change apart and read the same
in a status meeting.

**This file was itself wrong twice today** — it claimed no Cloudflare zone
existed, and it claimed the cron swap could be done over PocketBase's API.
Both are corrected below. A status file that lags is worse than none, because
it is read as current while describing yesterday.

## What actually serves production right now

    www.anticipy.ai          VERCEL         server: Vercel
    anticipy.ai DNS          PORKBUN        live NS is still the four
                                            *.ns.porkbun.com
    the backend API          RAILWAY        /api/health 200, HQ gated:true
    HQ, the team's dashboard RAILWAY        via 33 rewrites in next.config.mjs
    the reminder/digest cron RAILWAY        the only sweep that sends
    brain/ (the worker)      RAILWAY        no container exists on Cloudflare
    the Chrome extension     RAILWAY        extension/config.js:12 DEFAULT_BASE
    the Mac DMG              R2 (old acct)  reachable, /dl/... -> 200

## CORRECTION 1 — a Cloudflare zone for anticipy.ai DOES exist

The previous revision said "there is no Cloudflare zone", inferred from
`dig NS anticipy.ai` still returning Porkbun — not the same question.

    zone     anticipy.ai
    id       31cfa9047733c3d3616a4825b2117bf9
    status   PENDING          <- created, but nameservers NOT yet switched
    created  2026-09-04 05:33Z
    CF NS    aldo.ns.cloudflare.com, marge.ns.cloudflare.com

PENDING means inert: Cloudflare will not serve the domain until the nameservers
change at Porkbun. So the operational conclusion is unchanged — DNS has not
moved — but the SETUP step is already done, and step 7 is smaller than claimed.

(Reported by a sweep agent reading the Cloudflare API. Independent
re-verification with `wrangler zone list` was blocked by a rate limit at the
time; confirm the zone id before relying on it.)

## CORRECTION 2 — the cron swap CANNOT be done over PocketBase's API

The previous revision said `GET /api/crons` made the swap "reachable without the
Railway CLI". It does not. PocketBase v0.30.4 (backend/Dockerfile:3) registers
exactly `GET /api/crons` (list) and `POST /api/crons/{id}` (run). No disable, no
delete. Removing `internal_hq_sweep` means shipping a build without its
`cronAdd`, which means a Railway deploy — and `backend/deploy.sh` shells to
`railway up`, which is not installed here. Step 5 is blocked on ACCESS after all.

## What is finished, stated narrowly

Data: migrated and verified row-by-row. `/internal/state` bodies diffed
field-for-field across 167 rows, zero mismatches. The vault decrypts
PocketBase's own ciphertext.

HQ: every live route ported except `POST /internal/me/password` and password
login via `/internal/session` (their source is untracked — see STATUS.md). The
HQ app itself is byte-identical to production's, and — fixed today — key sign-in
now works: the port read the key from the header while the shipped gate sends it
in the BODY, so every fresh login had been 401ing. Contract test added.

The product surface: `evidence`, `owner_profile`, `pendants`, `segments` and
`purges` were 404 on the Worker until today and are now served. New-user signup,
which could not succeed at all, now works end to end.

Suite: 147 passed / 0 failed on the Worker, 148 / 0 on production.

## The two things that must be true before cutover, and are not yet

1. ~~**ANTICIPY_AUTH_SECRET is present but EMPTY.**~~ **FIXED 2026-09-04.** Read
   the live `owners.authToken.secret` off the running backend container
   (`ssh anticipy-backend`, `strings /pb_data/data.db | grep legacy_uuid` to
   isolate the owners row — the admin UI does NOT expose the secret, and the
   container has no sqlite3/python) and set it on the Worker (50 chars, single
   unique value, duration 604800 matching the UI; piped, no newline, never
   printed). Negative-path verified LIVE: a forged token is 401 on both the
   Worker and production. Positive-path (a real PB token accepted by the Worker)
   is the cutover-moment check — command in
   research/2026-09-04-the-auth-secret-nobody-set.md.

2. ~~**CLERK_HQ_JWT_KEY is unset.**~~ **SET this session** — piped from Railway,
   confirmed in `wrangler secret list`; clerk/exchange 400s like production.

## The cutover, in the order it has to happen

0. **Fix the password I changed.** A probe set a teammate's HQ password to `abc`
   on PRODUCTION. research/2026-09-04-I-changed-a-real-password-while-probing.md.
   Do this first.
1. DONE. anticipy-api is canonical; the wedge was propagation.
2. `wrangler secret put ANTICIPY_AUTH_SECRET` (re-set — it is currently empty;
   use runbooks/extract_auth_secret.py). CLERK_HQ_JWT_KEY is already set.
3. Port `/internal/me/password`, password login, and `/internal/fellows/*`
   actions — all in the untracked `fellowship_host.pb.js`, readable only off the
   Railway container. `GET /internal/fellows` IS ported and returns real data,
   so the fellowship admin screen renders fully populated but every action
   button 404s until this is done. Do NOT guess the sha256 password scheme.
4. Extension release. Yours to time. `ANTICIPY_AUTH_SECRET` first.
5. Swap the crons, atomically with the website flip. Needs Railway (Correction 2).
6. Delete the 25 junk `owners` rows in D1 (verified safe; they own nothing).
7. Repoint the websites. TWO separate flips, and they are NOT the same shape:
   - **Fellowship** (`anticipyfellowship.com`, Vercel project `anticipy-fellowship`):
     `FELLOWSHIP_ORIGIN` IS a dashboard env var — a real one-line flip. But hold
     it: the authenticated / payout `/internal/fellows/*` actions ship UNPROVEN
     and the Pay button 404s until step 3, so flipping now breaks fellow actions.
   - **Main app** (`www.anticipy.ai`, Vercel project `anticipy`, repo
     `anticipation-labs/aniticipy-web`): there is NO backend-origin env var in
     that Vercel project (checked 2026-09-04: no var matching pocket/railway/url
     is a PB origin). The API is routed by `next.config.mjs` rewrites with a
     HARDCODED Railway destination. So the main-app cutover is a CODE CHANGE +
     deploy in the aniticipy-web repo — a DIFFERENT GitHub org (anticipation-labs,
     not omize10) and NOT checked out on this machine. It cannot be done from
     here at all; it needs that repo.
8. brain/ onto Containers. migration/BRAIN-ON-CONTAINERS.md. Three blockers:
   `migration/workers/brain/src/index.ts` and `brain/container_entry.py` do not
   exist, and a Docker CLI this machine lacks.
9. DNS. Measured 2026-09-04: nameservers are still Porkbun
   (`curitiba/fortaleza/maceio/salvador.ns.porkbun.com`), which is WHY the
   Cloudflare zone is PENDING. www + apex point to Vercel today
   (`cname.vercel-dns.com` / `76.76.21.21`). **HARD PREREQ before any NS switch:**
   email is Google Workspace (`MX 1 smtp.google.com`, apex `SPF
   v=spf1 include:_spf.google.com`, plus a google-site-verification TXT). The
   Cloudflare zone MUST carry the MX + SPF + verification TXT + the correct
   www/apex target BEFORE the nameservers move, or switching NS silently breaks
   BOTH email and the website. Confirm the zone's record set first; the switch is
   also coupled to where the site is hosted (stay on Vercel → www CNAMEs Vercel;
   move to Cloudflare Workers via OpenNext → www points at the site Worker).

## The data-divergence fact the cutover must account for

The Worker and Railway now serve SEPARATE datastores forked from a common copy
that diverged today: each ran its own daily repeat-laydown, so the same logical
task exists twice under two different ids, and any write against one origin is
invisible to the other. This is inherent to running two live systems, not a bug.
The cutover must therefore either (a) freeze writes on Railway and re-import the
delta into D1 immediately before the flip, or (b) accept that changes made in
the gap between "D1 snapshot" and "flip" are lost. There is no third option that
keeps both live and consistent.

## The one-line test for "is it live yet"

    curl -s -o /dev/null -D - https://www.anticipy.ai/ | grep -i '^server:'

`Vercel` means no. Nothing else in this file overrides that line.
