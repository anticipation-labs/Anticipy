# Finish the Cloudflare migration — checklist + exact commands

Generated 2026-09-05. Grounded in the live systems and `migration/workers/BRAIN.md` §5.

## Status right now (verified live)
- ✅ Website `www.anticipy.ai` + apex → **Cloudflare** (`server: cloudflare`)
- ✅ `api.anticipy.ai` → **Cloudflare** Worker (HTTP 200)
- ✅ Email → Google (`MX smtp.google.com`)
- ✅ iOS built to **TestFlight** (points at api.anticipy.ai)
- ❌ **Brain worker** — still on Railway (Cloudflare `anticipy-brain` NOT deployed)
- ❌ **Owner memory in R2** — copy has NOT run (bucket empty)
- ❌ **PocketBase backend** — still Online on Railway (parallel to the API Worker)

The brain CI workflows are pushed to `jose_anticipy_system`:
`brain-state-to-r2.yml` and `brain-deploy.yml`. They are `workflow_dispatch`
(manual) with a typed confirm.

---

## STEP 1 — GitHub repo secrets (for the CI workflows)
GitHub → the Anticipy repo → Settings → Secrets and variables → Actions → New:

| Secret | Value / where to get it |
|---|---|
| `RAILWAY_TOKEN` | Railway → Account Settings → Tokens → Create (needs read on the `worker` service volume) |
| `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens → Create → template "Edit Cloudflare Workers" + add **R2 Storage:Edit**, **D1:Edit**, **Workers Scripts:Edit** on account `114587b715e702461766369b01d42fc7` |
| `CLOUDFLARE_ACCOUNT_ID` | `114587b715e702461766369b01d42fc7` |
| `RAILWAY_WORKER_SERVICE_ID` | optional — defaults to the service name `worker` |

---

## STEP 2 — Brain secrets on the `anticipy-brain` Worker
Run each locally (you have wrangler auth). Values marked **(reuse)** are already
set on `anticipy-api` — use the same value. Config VARS are already in
`migration/config/wrangler.brain.jsonc` and do NOT need `secret put`.

Run from the repo root. Each command prompts for the value (nothing is echoed):

```bash
cd /Users/cjxsez/Desktop/Anticipy
CFG=migration/config/wrangler.brain.jsonc

# --- credentials you already have set on anticipy-api (reuse the SAME value) ---
npx wrangler secret put ANTICIPY_SERVICE_TOKEN --config $CFG   # (reuse from anticipy-api)
npx wrangler secret put OPENROUTER_API_KEY     --config $CFG   # (reuse)
npx wrangler secret put TWILIO_ACCOUNT_SID     --config $CFG   # (reuse)
npx wrangler secret put TWILIO_AUTH_TOKEN      --config $CFG   # (reuse)
npx wrangler secret put TWILIO_PHONE_NUMBER    --config $CFG   # (reuse)

# --- provider keys NOT on anticipy-api — get from Railway `worker` service Variables,
#     or the provider dashboard ---
npx wrangler secret put GEMINI_API_KEY  --config $CFG   # Railway worker vars / Google AI Studio
npx wrangler secret put BRAVE_API_KEY   --config $CFG   # Railway worker vars / Brave Search API
npx wrangler secret put TAVILY_API_KEY  --config $CFG   # Railway worker vars / Tavily

# --- R2 S3 API credentials for the brain's own backup lane (state_backup.py) ---
#     Create at: Cloudflare → R2 → Manage R2 API Tokens → Create (Object Read & Write)
npx wrangler secret put ANTICIPY_BACKUP_S3_ACCESS_KEY --config $CFG   # R2 token Access Key ID
npx wrangler secret put ANTICIPY_BACKUP_S3_SECRET     --config $CFG   # R2 token Secret Access Key
npx wrangler secret put ANTICIPY_BACKUP_S3_BUCKET     --config $CFG   # value: anticipy-owner-state
npx wrangler secret put ANTICIPY_BACKUP_S3_ENDPOINT   --config $CFG   # value: https://114587b715e702461766369b01d42fc7.r2.cloudflarestorage.com

# --- optional (Twilio API-key auth instead of the auth token; skip if unused) ---
# npx wrangler secret put TWILIO_API_KEY_SID    --config $CFG
# npx wrangler secret put TWILIO_API_KEY_SECRET --config $CFG
```

Config VARS already set in wrangler.brain.jsonc (no action needed):
`ANTICIPY_PB, ANTICIPY_STATE_ROOT, ANTICIPY_STATE_VOLUME_ROOT, ANTICIPY_TZ,
ANTICIPY_MODEL, ANTICIPY_GEMINI_MODEL, ANTICIPY_SEGMENTS, ANTICIPY_SUPERVISED (1),
ANTICIPY_WEBHOOK_MANAGER (0), ANTICIPY_TWILIO_WEBHOOK_URL, ANTICIPY_MAX_OWNER_WORKERS,
ANTICIPY_OWNER_DISCOVERY_SECONDS, ANTICIPY_STATE_BACKUP_*, ANTICIPY_BACKUP_REQUIRED (1),
ANTICIPY_STATE_SNAPSHOT_SECONDS`.
`ANTICIPY_STATE_R2_BUCKET` (=anticipy-owner-state) and `ANTICIPY_STATE_R2_PREFIX`
(=owners) are now both present as vars in wrangler.brain.jsonc — no action needed.

Verify: `npx wrangler secret list --config $CFG` shows all the names above.

---

## STEP 3 — Copy owner memory to R2 (the safe, reversible half)
GitHub → Actions → **Brain state → R2** → Run workflow → type `MIGRATE`.
- Reads the Railway volume READ-ONLY (never deletes it).
- integrity_check each memory.db, upload, SHA-256 round-trip verify.
- Must finish GREEN. If it fails, DO NOT proceed — read the log.

Verify after: `npx wrangler r2 object get anticipy-owner-state/owners/<an-owner-id>/memory.db --remote`
returns the file (not "key does not exist").

---

## STEP 4 — Deploy the brain, ONE owner first
GitHub → Actions → **Brain → Cloudflare Containers** → Run workflow →
`confirm=DEPLOY`, `cap=1`.
- Builds brain/Dockerfile REMOTELY on Cloudflare (no local Docker).
- Watch (§10.6): container healthy on :8731; `state pulled` then
  `state snapshot ok` within ~90s; the brain answers a real text for that owner.
- Only when that one owner is proven: re-run with `cap=100`.

---

## STEP 5 — iOS to the App Store
App Store Connect → the TestFlight build (from run 33945943140) → submit for App
Store review. Request **expedited review**. iPhone traffic leaves Railway once
users update.

---

## STEP 6 — Retire Railway (LAST, only after brain is proven)
- Confirm D1 has the full current PocketBase data (spot-check row counts) BEFORE
  stopping the Railway `backend`.
- Stop the Railway `worker` (brain) and `backend` (PocketBase) services.
- **Keep both Railway volumes in place, unmounted, undeleted, for two weeks**
  (runbook §10.9). The R2 copy is unproven until a restore has been done from it.

---

## STEP 7 — Remaining loose ends
- Chrome extension → build + publish to the Web Store (developer login required).
- Stripe + Twilio-broker secrets → add to the `anticipy-site` Worker when those
  flows are needed (`STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
  TWILIO_BROKER_ACCOUNT_SID/FROM/SID/TOKEN`).
- Apex→www is a Cloudflare Redirect Rule; the old Vercel project can be left idle
  or deleted once you're satisfied.
