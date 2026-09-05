# 2026-09-05 — Website (Vercel → Cloudflare) cutover, in progress

Live actions taken this session, in order, with the exact state so the next
session (or a resumed one) can continue without re-deriving anything.

## Backend (already done earlier)
- `anticipy-api` Worker + D1 live. `ANTICIPY_AUTH_SECRET` set to PocketBase's
  real `owners.authToken.secret` (zero-logout ready; forged tokens 401 on both).
- `CLERK_HQ_JWT_KEY` set. R2 bucket `anticipy-owner-state` created.

## Website on Cloudflare — built, deployed (staging), configured
- Repo `anticipation-labs/aniticipy-web` at `/Users/cjxsez/Desktop/Aniticpy_Website`,
  branch `cloudflare`. `next.config.mjs` `FELLOWSHIP_ORIGIN` default flipped to the
  Worker (commit 7d4c0ea, pushed).
- `npm run cf:build` (OpenNext 1.15.1) succeeds → `.open-next/worker.js`.
- `npm run cf:deploy` → Worker **`anticipy-site`** live at
  **https://anticipy-site.omar-114.workers.dev** (no custom domain yet = no prod impact).
- Runtime env: **30 secrets** loaded onto `anticipy-site` via `wrangler secret bulk`
  (pulled from Vercel production env). `/api/health` reports
  `supabase/supabaseAdmin/resend/groq/mistral/... : true`. Site renders: `/`, `/apply`,
  `/crm` all 200.
- **Deferred (owner):** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and the 4
  `TWILIO_BROKER_*` — Vercel marks them "Sensitive"/unpullable and they are not in
  `.env.local`. Checkout + broker-SMS stay unset until the owner supplies them.

## DNS — nameserver switch DONE, propagating
- **2026-09-05: switched anticipy.ai's authoritative nameservers at Porkbun**
  from the 4 `*.ns.porkbun.com` to Cloudflare's **`aldo.ns.cloudflare.com`** +
  **`marge.ns.cloudflare.com`** (owner confirmed the Porkbun save).
- Cloudflare zone already serves authoritative (SOA via aldo.ns.cloudflare.com OK)
  and **mirrors all 12 live records** — verified CF-vs-live identical for A(apex→
  Vercel 76.76.21.21), www(→cname.vercel-dns.com), MX(smtp.google.com), SPF,
  google-verification, DMARC, Google DKIM, 4 SendGrid CNAMEs. So the switch drops
  nothing; email stays on Google; site keeps serving from Vercel until www is repointed.
- At time of writing the `.ai` registry still delegates to Porkbun (normal lag;
  Porkbun notes up to 48h, usually far less). A background poll is watching for the
  Cloudflare delegation to land.

## Bug caught by the parity audit and FIXED (2026-09-05)
The cutover-readiness workflow (Cloudflare-staged site vs live Vercel, all route
groups, adversarially verified) found ONE real cutover-blocker: on the OpenNext
worker the literal route `/app` resolved to the root homepage — a route-name
collision with the app-router `app/` directory. Effect: `/engine`→`/app` (the
signup/login entry) served marketing content; users could not sign up or log in.
Only `/app` was affected (all other routes, incl. other client pages, fine;
`/app/download` fine). `force-dynamic` did NOT fix it (collision is in route
MATCHING, not prerender). FIX (aniticipy-web `cloudflare` branch, commit 1669214,
built+deployed+pushed): a non-colliding alias route `/enter` re-exports
`src/app/app/page.tsx`, and middleware rewrites `/app`→`/enter` (exact match) so
the URL stays `/app`. Verified: CF `/app` now === Vercel (title "Anticipy App",
the real signup form). The site is now parity-clean and safe to flip.

## CRITICAL: the first nameserver save silently FAILED (fixed 2026-09-05)
The initial Porkbun "Save Nameservers" click hung the tab and did NOT persist —
re-opening the editor later showed the domain STILL on the 4 Porkbun nameservers,
which is why nothing propagated for ~1h. Re-done and VERIFIED: the Porkbun
authoritative-nameservers editor now shows `aldo.ns.cloudflare.com` +
`marge.ns.cloudflare.com` (and Porkbun now offers "Use Our Default Nameservers",
which only appears when custom NS are set). Lesson: after a Porkbun NS save,
always re-open the editor to confirm it stuck. Propagation genuinely started at
this point; a background poll watches the `.ai` registry for the flip.

## iOS: backend repointed to api.anticipy.ai (committed 66abdd3d, push HELD)
`app/ios` now defaults to `https://api.anticipy.ai` (was the Railway URL) across 5
files, with a launch migration for existing installs (custom overrides kept). The
release CI already exists — `.github/workflows/ios-testflight.yml` builds via
Xcode 26, cloud-signs (team 49T86P9XGW), uploads to TestFlight via the ASC API
key secrets. It triggers on push to `jose_anticipy_system` for `app/ios/**`. The
commit is on `cloudflare-backend`; to ship, place it on `jose_anticipy_system`.
PUSH IS HELD until api.anticipy.ai is live, or the build would migrate users to a
dead domain.

## CUTOVER EXECUTED 2026-09-05 (SSL provisioning)
DNS propagated (`.ai` registry now delegates to aldo/marge.ns.cloudflare.com;
public recursive resolves to Cloudflare). Then:
- `api.anticipy.ai` → `anticipy-api` Worker: custom domain added to
  migration/workers/wrangler.jsonc `routes` and deployed (deploy output confirmed
  "api.anticipy.ai (custom domain)").
- `www.anticipy.ai` → `anticipy-site` Worker: FIRST deploy failed with code 100117
  ("www already has externally managed DNS records") because the CF zone still held
  the mirrored `www` CNAME → cname.vercel-dns.com. Deleted that record in the CF
  DNS dashboard, re-deployed, confirmed "www.anticipy.ai (custom domain)".
- Email intact throughout: `MX 1 smtp.google.com` still resolves.
- Apex `anticipy.ai` still 307→www via the Vercel A record (76.76.21.21) mirrored
  in the zone — TODO: replace with a Cloudflare redirect rule so Vercel leaves the
  path.
Edge SSL certs provisioning at time of writing; a background waiter polls www+api
until both 200, then: final verify + push the iOS commit to trigger TestFlight.

## THE REMAINING STEP (do when the zone goes Active)
`www` is canonical (apex 307→www; site HTML references www.anticipy.ai). So:
1. Cloudflare → Workers → `anticipy-site` → Domains → **Add Custom Domain →
   `www.anticipy.ai`**. This overrides the www record (currently → Vercel) to route
   to the Worker + provisions SSL. THIS is the moment the live site moves to Cloudflare.
2. Apex `anticipy.ai`: keep redirecting to www — either a Cloudflare Redirect Rule
   (`anticipy.ai/* → https://www.anticipy.ai/$1`, 301) or leave apex A → Vercel
   (its 307 still works). Prefer the CF rule to drop the Vercel dependency.
3. Verify: `curl -I https://www.anticipy.ai` shows a `cf-ray` header (served by
   Cloudflare, not `server: Vercel`); apex redirects to www; `dig MX` still Google.

## Still NOT migrated (out of scope of the website flip)
- Railway `backend` (PocketBase) + `worker` (brain) still serve production.
- Cron swap (Railway deploy to stop the digest sender there) — not done.
- iPhone + Chrome-extension releases (they hit the backend directly) — owner only.
- brain/ → Cloudflare Containers (code written, untested, no Docker).
- Arav's HQ password remediation (`abc`, from an earlier probe).

## COMPLETE 2026-09-05 — verified in production
- www.anticipy.ai → HTTP 200, `server: cloudflare`, `cf-ray` (Cloudflare Worker; Vercel gone from the path).
- anticipy.ai (apex) → HTTP 301 → https://www.anticipy.ai/, `server: cloudflare` (CF Redirect Rule; apex A record set to Proxied). Vercel fully out of the web path.
- api.anticipy.ai → HTTP 200 (D1-backed anticipy-api Worker).
- Email intact: MX 1 smtp.google.com.
- iOS: commit db43db14 on jose_anticipy_system; ios-testflight.yml run 33945943140 SUCCEEDED (build .github#3) — new build uploaded to TestFlight pointing at api.anticipy.ai.

STILL ON RAILWAY (not part of the web cutover; unchanged): PocketBase `backend`
and the brain `worker` service. iPhone traffic moves off Railway only once users
install the new TestFlight/App Store build. Extension + brain/ + the Stripe/Twilio
secrets remain as previously documented.

## Brain migration — state DONE, runtime NOT done (2026-09-05, later)
- ✅ 9 owners' memory in R2, SHA-verified, integrity_check ok (data never on a laptop; uploaded container→R2 via boto3).
- ✅ anticipy-brain deployed via CI (GitHub runner builds brain/Dockerfile; no local Docker). Container app anticipy-brain-owner created.
- ✅ 11 brain secrets set (4 R2 by me, 7 pulled from Railway worker env by the owner; GEMINI_API_KEY absent on Railway too).
- ✅ GitHub secrets CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN set; brain workflows registered on main.
- 🐞 BUG 1: ANTICIPY_PB was https://www.anticipy.ai (site Worker → 404s /api/collections/*). Fixed to https://api.anticipy.ai (commit 644995fd) but running containers keep the old env until restart.
- 🐞 BUG 2: OwnerBrain DO does not keep containers warm — instance goes `inactive`; brain not continuously running. Untested-code lifecycle bug (index.ts needs an alarm keep-alive).
- 🐞 BUG 3: D1 has 33 owner rows, only 5 real; supervisor tries to spawn a container per row (28 junk/probe). Clean D1 owners before running the fleet.
- DECISION: Railway brain STAYS live (not stopped). Cutting over to the flaky CF brain would break 5 real users. Do NOT stop Railway until bugs 1-3 fixed and one real owner verified running continuously over time.
- Deployed CF brain is currently inert (cap=1, inactive instance, was pointing at www→404) = no double-outreach; harmless as-is.

### Remaining to finish the brain (in order)
1. Delete 28 junk owner rows from D1 (keep the 5 real).
2. Fix OwnerBrain keep-alive (alarm loop) in migration/workers/brain/src/index.ts; redeploy.
3. Verify 1 real owner: container stays up, polls api.anticipy.ai, processes a job.
4. Stop Railway worker (`railway down`-style); keep the volume 2 weeks.

## Brain — precise diagnosis after both fixes (2026-09-05 ~07:35 UTC)
- Deployed anticipy-brain worker config IS correct: ANTICIPY_PB = https://api.anticipy.ai (verified via CF API /settings bindings). Owner filter + keep-alive shipped.
- BUT the container LOGS (dashboard → Containers → anticipy-brain-owner → Logs) show, at 07:32 UTC, the running container still hitting `https://www.anticipy.ai/api/collections/...` → 404 "backend unreachable". So the containers are STALE: they booted with the OLD www env (before the PB fix) and are still on it.
- ROOT CAUSE of the staleness: container env is captured at container START (OwnerBrain.envFor → startOptions.envVars). A worker var change does NOT restart running containers. Worse, my keep-alive fix (container_entry.py child-restart loop) + the fact that "backend unreachable 404" is NON-FATAL (worker logs it, keeps polling, does not exit) means the container never dies → never re-spawns with the new env. The keep-alive made stale env sticky.
- Net: the CF brain is deployed but NON-FUNCTIONAL (can't reach its backend). Railway brain STAYS live. Do NOT stop it.

## To finish the brain (needs a monitored session, not blind autonomous redeploys)
1. Force the containers to CYCLE so they boot with api.anticipy.ai:
   - `wrangler containers delete <appID>` then redeploy, OR bump the container image
     (trivial Dockerfile change) to force a rollout of fresh instances. Confirm new
     instances boot with ANTICIPY_PB=api.anticipy.ai.
2. Fix the keep-alive/env-propagation interaction: on a config change, containers
   must be explicitly cycled (document this, or have the supervisor detect a config
   version bump and recycle). Consider making persistent "backend unreachable"
   eventually exit so stale containers self-heal.
3. Verify against the runtime (this is why it needs monitoring): a fresh container
   for one real owner must — boot, pull R2 state, poll api.anticipy.ai with 200s
   (not 404), stay alive across several minutes, and process a real event.
4. Only then: stop the Railway worker (`railway down`-style), keep the volume 2 weeks.

## Why I stopped autonomous iteration here
~15 deploy/debug cycles on UNTESTED container code, each revealing another layer
(cap override, wrong PB URL, container keep-alive, now stale-env propagation). This
is the "careful monitored session against the runtime" the runbook required from the
start — not something to finish by firing more blind production deploys. Railway is
safe and serving; no user impact; no data lost (state is migrated + verified).

## Brain: FIXED on Cloudflare + Railway incident resolved (2026-09-05 ~08:1x UTC)
- FIX confirmed: the stale-env bug was cured by deleting the container app (a03b1004)
  and redeploying → fresh containers boot with ANTICIPY_PB=api.anticipy.ai. Verified
  by LIVE traffic: 50 requests/20s to https://api.anticipy.ai/api/collections/*
  (events/jobs/agents/owner_profile), 0 to www, all 200 OK. Fleet health healthy=8,
  stopped=0, failed=0 stable across 90s. Brain IS running on Cloudflare.
  New container app id: a0396380-ac5a-4fbc-bca0-872604bf12d2.
- SSH note: `wrangler containers ssh` returns "instance not found" for these
  DO-managed per-owner containers (works for standalone containers only). Verified
  via network traffic instead (stronger: proves reachability + 200s, not just env).

- INCIDENT (my error): I handed the owner a `railway down --service worker` as a
  "final step". It removed the active worker deployment → worker Failed. The CLI
  `railway redeploy` then FAILED because Railway rebuilds from a git source whose
  current tree no longer has brain/Dockerfile ("couldn't locate the dockerfile at
  path brain/Dockerfile in code archive"). RESOLVED by dashboard Rollback to the
  last-good git deployment (commit 4eb753f4) — uses the cached image, no rebuild.
  Worker + backend both Online again. Backend (PocketBase) stayed Online throughout,
  so events were still STORED during the gap; only brain PROCESSING paused (~quiet
  hours, low impact).

- CORRECTED SEQUENCING (the lesson): Railway must be stopped LAST — only AFTER the
  iOS App Store release + extension release repoint current users to api.anticipy.ai.
  Current shipped clients still post to Railway; the CF brain polls D1 (which has no
  client traffic yet: events_last_hour=0). Stopping Railway before client cutover
  blinds current users' brain. Do NOT run `railway down` on the worker until clients
  are released on api.
- FOLLOW-UP: the worker's git source no longer contains brain/Dockerfile on the
  tracked branch, so an auto-deploy/rebuild would fail. Before the eventual Railway
  retirement this is moot, but if the Railway worker must be rebuilt meanwhile, point
  it at a branch that has brain/ (cloudflare-backend / jose_anticipy_system) or
  rollback to a good image.
