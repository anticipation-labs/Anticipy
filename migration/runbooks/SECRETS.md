# SECRETS.md — credential inventory and secure storage design for Cloudflare

**Scope.** Every credential read by any component of the merged tree: `src/`
(Next.js website), `backend/pb_hooks/` + `backend/pb_migrations/` +
`backend/start.sh` (PocketBase), `brain/` + `engine/` + `proof/` + `scripts/` +
`tools/` (Python), `.github/workflows/`, and the five clients. Every row carries
a `file:line` that was read, not inferred.

**Method.** `os.environ`/`os.getenv` across all `*.py`; `$os.getenv` across
`backend/pb_hooks/*.js` (106 call sites); `process.env` across `src/**/*.{ts,tsx}`;
`${{ secrets.* }}` across `.github/workflows/`. Config knobs (ports, paths,
model names, feature flags, timeouts) are deliberately excluded — this file is
about things that authenticate, encrypt, or gate. There is no tracked
`.env.example` in the current tree; one existed and was removed
(see ROTATION.md §7).

**No secret VALUE appears in this file.** Names and locations only.

---

## §0. How to read the "where it lives on Cloudflare" column

Four placements, and the choice is not stylistic:

| Placement | Encrypted at rest | Visible in repo | Visible in dashboard | Use for |
|---|---|---|---|---|
| **Worker secret** (`wrangler secret put`) | yes | no | name only, value write-only | anything that authenticates or decrypts |
| **`vars` in `wrangler.jsonc`** | no | **yes — it is a tracked file** | yes, in plaintext | hostnames, model ids, region names, feature flags |
| **Build-time env** (GitHub Actions / Workers Builds) | n/a | no | no | `NEXT_PUBLIC_*`, which are **inlined into the client bundle** |
| **GitHub Actions secret** | yes | no | no | credentials only CI holds (signing keys, the Cloudflare deploy token) |

The rule that decides between the first two: *if leaking it lets someone else
spend your money, read your users' data, or forge a request, it is a Worker
secret.* Everything else is a `var`. There is no third category, and
"it's only the free tier" is not one — see ROTATION.md §1.

### The `NEXT_PUBLIC_*` rule, stated plainly

`NEXT_PUBLIC_*` variables are **not secrets and cannot be made into secrets**.
Next.js substitutes their literal values into the JavaScript that ships to every
browser at *build* time. On Cloudflare this means they must be present in the
**build** environment (the GitHub Actions job or Workers Builds), and putting
them in `wrangler secret put` accomplishes nothing at all: the bundle was
already compiled before the Worker ever ran.

Two variables in this tree are named `NEXT_PUBLIC_*` and hold things that were
intended to be secret. Both are inventory rows below and both are findings:

* `NEXT_PUBLIC_CRON_SECRET` — `src/app/crm/settings/page.tsx:150-151`. Sent as
  the `x-cron-secret` header from a **client component**. The value that
  `src/app/api/cron/daily-digest/route.ts:23` checks (`CRON_SECRET`) is
  therefore published to every visitor of `/crm/settings` if the two are ever
  set to the same string. They must not be. See ROTATION.md §4.
* `NEXT_PUBLIC_DEMO_PASSCODE` — `src/app/demo/page.tsx:25`. Compared in the
  browser. This is a doormat, not a lock, and it is fine as long as nobody
  believes otherwise.

---

## §1. Assumed Worker topology

Secrets have to be assigned to a service, so this file assumes three deploy
targets. If the sibling workstreams settle on different names, only the
`--name` flags change — the *assignment* of which secret goes to which service
is the part that matters and is what is specified here.

| Service | Replaces | Holds |
|---|---|---|
| `anticipy-web` | Vercel Next.js app (`src/`) | website secrets, §2 |
| `anticipy-api` | PocketBase (`backend/`) | backend secrets, §3 |
| `anticipy-brain` | Railway `python -m brain.supervisor` (Container) | brain secrets, §4 |

D1 and R2 reach a Worker through **bindings**, not credentials. There is no
"D1 password" and no "R2 access key" to store for in-Worker access. R2 *S3-API*
keys are still needed for the two callers that are outside a Worker — see
`ANTICIPY_BACKUP_S3_*` (§3) and `R2_*` (§5).

---

## §2. Website — `anticipy-web`

### 2a. Server-only secrets

| NAME | Authenticates to | Component | Read at | Class | Cloudflare home | Rotation |
|---|---|---|---|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase (RLS-bypassing) | website | `src/middleware.ts:37`, `src/app/api/extension/auth/route.ts:69`, `src/app/api/extension/agent-config/route.ts:153` (29 sites) | server-only | Worker secret on `anticipy-web` | Supabase dash → Project Settings → API → roll `service_role`. **Also re-signs every gate cookie** — see §7. |
| `STRIPE_SECRET_KEY` | Stripe API | website | `src/lib/stripe.ts:7` | server-only | Worker secret | Stripe dash → Developers → API keys → roll, 24 h overlap |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature | website | `src/app/api/webhooks/stripe/route.ts:20` | server-only | Worker secret | Stripe dash → Webhooks → endpoint → roll signing secret |
| `RESEND_API_KEY` | Resend (transactional email) | website | `src/lib/email.ts:16`, `src/app/api/crm/integrations/test/route.ts:83`, `src/app/api/health/route.ts:26` | server-only | Worker secret | Resend dash → API Keys → create new, delete old |
| `MAIL_RESEND_API_KEY` | Resend (override key) | website | `src/lib/email.ts:16` | server-only | Worker secret | as `RESEND_API_KEY`; unset it unless a second Resend account is genuinely in play |
| `SENDGRID_API_KEY` | SendGrid | website (CRM) | `src/lib/crm/email.ts:7`, `src/app/api/crm/integrations/test/route.ts:70` | server-only | Worker secret | SendGrid → Settings → API Keys → create/delete |
| `DEEPGRAM_API_KEY` | Deepgram ASR | website | `src/app/api/transcribe/route.ts:60`, `src/app/api/crm/integrations/test/route.ts:57`, `verifier/lib/audio.py:128` | server-only | Worker secret | Deepgram console → API Keys |
| `GOOGLE_API_KEY` | Google Generative AI | website | `src/app/api/extension/auth/route.ts:89`, `src/lib/crm/gemini.ts:76`, `src/lib/voyage.ts:30` | server-only **but currently handed to clients — see §7** | Worker secret | Google AI Studio → API keys → delete + recreate |
| `GEMINI_API_KEY` | Google Generative AI (alias) | website, backend | `src/lib/crm/gemini.ts:76`, `backend/pb_hooks/agent_key.pb.js:24,202` | server-only | Worker secret on **both** `anticipy-web` and `anticipy-api` | as `GOOGLE_API_KEY` |
| `GROQ_API_KEY` | Groq | website, engine | `src/app/api/extension/auth/route.ts:88`, `engine/app/config.py:72` | server-only **but handed to clients — §7** | Worker secret | Groq console → API Keys |
| `MISTRAL_API_KEY` | Mistral | website, engine | `src/app/api/extension/auth/route.ts:90`, `engine/app/config.py:78` | server-only **but handed to clients — §7** | Worker secret | Mistral console → API Keys |
| `DEEPSEEK_API_KEY` | DeepSeek | website, engine | `src/app/api/extension/auth/route.ts:91`, `src/lib/llm-cascade.ts:86`, `engine/app/config.py:71` | server-only **but handed to clients — §7** | Worker secret | DeepSeek platform → API keys |
| `CEREBRAS_API_KEY` | Cerebras | website, engine | `src/app/api/extension/auth/route.ts:97`, `engine/app/config.py:82`, `engine/synthetic_trajectory_generator.py:355` | server-only **but handed to clients — §7**; **prior value is in public git history, ROTATION.md §1** | Worker secret | Cerebras cloud → API Keys |
| `OPENROUTER_API_KEY` | OpenRouter | website, backend, brain | `src/app/api/engine/model/route.ts:66`, `backend/pb_hooks/agent_key.pb.js:203`, `brain/llm.py:218` | server-only | Worker secret on all three services | openrouter.ai → Keys. Set a per-key credit limit at creation. |
| `VOYAGE_API_KEY` | Voyage AI embeddings | website | `src/lib/voyage.ts:71,114` | server-only | Worker secret | Voyage dash → API keys |
| `TWILIO_BROKER_ACCOUNT_SID` | Twilio (broker subaccount) | website | `src/app/api/twilio/voice-relay/route.ts:201`, `src/app/api/twilio/relay/route.ts:265` | identifier, not secret, but keep with its token | Worker secret (co-located with the token) | Twilio console → Account |
| `TWILIO_BROKER_SID` | Twilio API key SID | website | `src/app/api/twilio/voice-relay/route.ts:202,205` | half of a credential pair | Worker secret | Twilio → Account → API keys → create new pair, delete old |
| `TWILIO_BROKER_TOKEN` | Twilio API key secret | website | `src/app/api/twilio/status/route.ts:46`, `src/app/api/twilio/voice-relay/route.ts:206` | server-only | Worker secret | as above, rotate as a pair |
| `TWILIO_AUTH_TOKEN` | Twilio (account auth + inbound webhook signature) | website, backend, brain | `src/lib/twilio-verify.ts:47`, `backend/pb_hooks/sms.pb.js:88`, `backend/pb_hooks/password_reset.pb.js:112` | server-only | Worker secret on `anticipy-web` **and** `anticipy-api` | Twilio → Account → Auth tokens → promote secondary. **Rotating this breaks inbound-SMS signature checks until every consumer has the new value** — ROTATION.md §6. |
| `TWILIO_MESSAGING_SERVICE_SID` | Twilio Messaging Service | website | `src/lib/notification-adapter.ts:136` | identifier | `vars` | n/a |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth | website | `src/lib/google-calendar.ts:4`, `src/lib/crm/google.ts:8` | public by OAuth design | `vars` | n/a |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth | website | `src/lib/google-calendar.ts:5`, `src/lib/crm/google.ts:9` | server-only | Worker secret | Google Cloud Console → Credentials → reset secret. Invalidates stored refresh tokens. |
| `ENCRYPTION_KEY` | encrypts stored Google refresh tokens | website | `src/lib/google-calendar.ts:6`, `src/lib/crm/google.ts:10` | server-only, **data-bearing** | Worker secret | **Cannot be rotated alone** — decrypt-and-re-encrypt every stored token first, or every Calendar connection breaks. Same hazard class as `ANTICIPY_VAULT_KEY` (§3). |
| `JWT_SECRET` | signs engine JWTs, confirm tokens, admin trigger | website, engine | `src/lib/confirm-token.ts:28`, `src/lib/engine-transfer-gate.ts:11`, `engine/app/config.py:93`, `engine/app/main.py:534` | server-only | Worker secret | Roll; invalidates live sessions and outstanding confirm links (7-day TTL, `src/lib/confirm-token.ts:20`) |
| `GATE_COOKIE_SECRET` | HMACs the site gate cookie | website | `src/lib/gate-cookie.ts:27`, `src/middleware.ts:36`, `src/lib/engine-transfer-gate.ts:10` | server-only | Worker secret | Roll; logs everyone out of the gate. **Set it explicitly** — see §7. |
| `GATE_PASSCODE_INTERNAL` | the internal-area passcode | website | `src/app/api/internal-gate/route.ts:14` | server-only | Worker secret | Change the string; tell the humans |
| `GATE_PASSCODE_TRANSFER` | the engine-transfer passcode | website | `src/lib/engine-transfer-gate.ts:41` | server-only | Worker secret | as above. Fails secure in production if unset (`engine-transfer-gate.ts:49-51`) — good. |
| `ANALYTICS_SECRET` | HMACs the `/analytics` session cookie | website | `src/lib/analytics-auth.ts:4` | server-only | Worker secret | Roll; logs analytics viewers out |
| `ANALYTICS_PASSWORD` | the `/analytics` password | website | `src/lib/analytics-auth.ts:35` | server-only | Worker secret | Change the string. **Its former default is in git history** — ROTATION.md §5. |
| `AGENT_LOG_SECRET` | gates `POST /api/log` | website | `src/app/api/log/route.ts:18` | server-only | Worker secret | Roll; update every agent that posts logs |
| `CRON_SECRET` | gates `/api/cron/daily-digest` | website | `src/app/api/cron/daily-digest/route.ts:23` | server-only | Worker secret | Roll. Must **not** equal `NEXT_PUBLIC_CRON_SECRET` — ROTATION.md §4. |
| `META_MONITOR_TEST_SECRET` | gates a test route | website, engine | `src/app/api/test-meta-monitor/route.ts:36`, `engine/test_meta_monitor.py:283` | server-only | Worker secret, or omit | Route already 404s in production (`route.ts:32-34`). Prefer not deploying it. |
| `CLOUDFLARE_EMAIL_API_TOKEN` | Cloudflare Email API | website | `src/lib/notification-adapter.ts:86` | server-only | Worker secret | Cloudflare dash → My Profile → API Tokens → roll |
| `CLOUDFLARE_ACCOUNT_ID` | selects the Cloudflare account | website, CI | `src/lib/notification-adapter.ts:86` | identifier, not a secret | `vars` | n/a |

### 2b. Public by construction — build-time, not Worker secrets

These are compiled into the browser bundle. Set them in the **build** step.

| NAME | What it is | Read at | Why it is not a secret |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | `src/app/admin/page.tsx:8` (32 sites) | A public hostname. The project ref is also in `_archive/legacy_extension_v1/background.js:8`. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon JWT | `src/app/admin/page.tsx:9` (14 sites) | Anon keys are designed to ship in browsers. **All of your protection is RLS.** ROTATION.md §8. |
| `NEXT_PUBLIC_POSTHOG_KEY` | PostHog project ingest key | `src/components/PostHogProvider.tsx:8`, `src/lib/analytics-server.ts:18` | Write-only ingest key, public by PostHog's design |
| `NEXT_PUBLIC_POSTHOG_HOST` | PostHog host | `src/components/PostHogProvider.tsx` | hostname |
| `NEXT_PUBLIC_SITE_URL` | canonical site URL | 6 sites | hostname |
| `NEXT_PUBLIC_ENGINE_URL` | engine base URL | 2 sites | hostname |
| `NEXT_PUBLIC_SALES_MODE` | feature flag | 1 site | flag |
| `NEXT_PUBLIC_DEMO_PASSCODE` | `/demo` passcode | `src/app/demo/page.tsx:25` | **Compared in the browser.** Ships to every visitor. Treat `/demo` as public. |
| `NEXT_PUBLIC_CRON_SECRET` | header for the cron route | `src/app/crm/settings/page.tsx:150-151` | **Ships to every visitor of `/crm/settings`.** A bug, not a design. ROTATION.md §4. |

---

## §3. Backend — `anticipy-api` (replacing PocketBase)

| NAME | Authenticates to | Component | Read at | Class | Cloudflare home | Rotation |
|---|---|---|---|---|---|---|
| `ANTICIPY_SERVICE_TOKEN` | the guard middleware — a **god credential** over every collection | backend, brain, proof | `backend/pb_hooks/guard.pb.js:25,37`; `backend/pb_hooks/worker_owners.pb.js:10`; `backend/pb_hooks/agent_auth.pb.js:80`; `backend/pb_hooks/research_lane.pb.js:429`; `brain/pb.py:24`; `proof/postdeploy_production.py:42` | server-only, **highest value in the system** | Worker secret on `anticipy-api` **and** `anticipy-brain` | Generate 32 random bytes; set on **both** services in the same maintenance window, brain first. **Never deploy the Worker without it** — see the fail-open note below. |
| `ANTICIPY_INTERNAL_KEY` | every `/internal/*` HQ route; also unlocks the password vault | backend | `backend/pb_hooks/internal_hq.pb.js:21,43` (53 references in that one file) | server-only, shared by the HQ team | Worker secret on `anticipy-api` | Roll and redistribute to HQ staff. Fails **closed** when unset (`internal_hq.pb.js:44`) — correct. |
| `ANTICIPY_VAULT_KEY` | AES key for `internal_passwords.secret_enc` | backend | `backend/pb_hooks/internal_hq.pb.js:3052,3126`; schema `backend/pb_migrations/1700000050_expenses_vault.js:42` | server-only, **data-bearing, irreplaceable** | Worker secret on `anticipy-api` | **Cannot be rotated in place.** Must be exactly 32 chars (`internal_hq.pb.js:3053`). Losing it destroys the vault. Full procedure: ROTATION.md §3. |
| `ANTICIPY_VAULT_KEY_GCM` | AES-GCM key that **replaces** `ANTICIPY_VAULT_KEY` after cutover | backend | generated by `migration/runbooks/reencrypt_vault.md` step 2; consumed by the Worker via WebCrypto | server-only, **data-bearing, irreplaceable** | Worker secret on `anticipy-api` | Same hazard as its predecessor: escrow before use, and re-wrap every row to rotate. ROTATION.md §8. |
| `CLERK_HQ_JWT_KEY` | HS256 verification key for Clerk-issued HQ JWTs | backend | `backend/pb_hooks/internal_hq.pb.js:3388` | server-only | Worker secret on `anticipy-api` | Clerk dash → JWT templates → rotate signing key, then update here |
| `TWILIO_ACCOUNT_SID` | Twilio account | backend, brain | `backend/pb_hooks/sms.pb.js:144`, `backend/pb_hooks/password_reset.pb.js:99`, `brain/voice_arm.py:357`, `brain/worker.py:921` | identifier; used as an **allowlist value** at `sms.pb.js:144` | Worker secret (co-located) / container env | Twilio console |
| `TWILIO_API_KEY_SID` | Twilio API key SID | backend | `backend/pb_hooks/password_reset.pb.js:110` | half of a pair | Worker secret | rotate as a pair |
| `TWILIO_API_KEY_SECRET` | Twilio API key secret | backend | `backend/pb_hooks/password_reset.pb.js:111` | server-only | Worker secret | rotate as a pair |
| `TWILIO_PHONE_NUMBER` / `TWILIO_FROM` | the sending number; also an inbound allowlist | backend | `backend/pb_hooks/sms.pb.js:145`, `backend/pb_hooks/password_reset.pb.js:100` | not a secret, but **security-relevant** (it is checked, not just used) | `vars` | n/a |
| `SENDBLUE_API_KEY_ID` | Sendblue (iMessage/RCS/SMS) — the provider replacing Twilio, 2026-09-05 | backend, brain | `migration/workers/src/messaging.ts` (the HQ reminder sweep and the password-reset code), `brain/sendblue_arm.py` | identifier half of a pair | Worker secret on `anticipy-api` **and** `anticipy-brain` | Sendblue → Developer → rotate as a pair |
| `SENDBLUE_API_SECRET_KEY` | Sendblue API secret | backend, brain | as above | server-only | Worker secret on both | rotate as a pair |
| `SENDBLUE_WEBHOOK_SECRET` | Sendblue's webhook (`POST /sms/sendblue`, inbound texts + status updates) — Sendblue sends it verbatim in the `sb-signing-secret` header | backend (Worker only) | `migration/workers/src/routes/sendblue.ts` | server-only, shared with Sendblue's dashboard | Worker secret on `anticipy-api` | Generate it (`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`), enter it in Sendblue → Developer → Webhooks beside the URL `https://api.anticipy.ai/sms/sendblue`, and `wrangler secret put` the same value in the same window — a mismatch is every inbound text 403-ing. Fails **closed** (503, logged) when unset. |
| `SENDBLUE_FROM_NUMBER` | the Sendblue sending number (E.164) — every outbound text names it, and `/sms/sendblue` refuses an inbound message addressed to any other number (an allowlist, like `TWILIO_PHONE_NUMBER`) | backend, brain | `migration/workers/src/messaging.ts`, `migration/workers/src/routes/sendblue.ts`, `brain/sendblue_arm.py` | not a secret, but **security-relevant** (it is checked, not just used) | `vars` | n/a |
| `ANTICIPY_SMS_PROVIDER` | `sendblue` or `twilio`: the owner's word on which arm sends; unset, the Worker picks Sendblue when its three names are bound, else Twilio | backend, brain | `migration/workers/src/messaging.ts chooseProvider` | not a secret | `vars` | n/a |
| `CAPSOLVER_API_KEY` | CapSolver | backend, engine | `backend/pb_hooks/captcha_solve.pb.js:33,135`, `engine/app/config.py:85` | server-only, **spends money per call** | Worker secret on `anticipy-api` | CapSolver dash → rotate. Set a balance alert. |
| `PB_SETTINGS_ENCRYPTION_KEY` | encrypts PocketBase's own `settings` in `data.db` | backend | `backend/start.sh:4,35` | server-only, data-bearing | **Retire.** D1 has no equivalent; the settings blob it protected does not survive the migration. | Delete after cutover. Until then: 32 chars exactly, or the container refuses to boot (`start.sh:4-7`). |
| `ANTICIPY_BACKUP_S3_ACCESS_KEY` | R2 S3 API (backups) | backend | `backend/pb_migrations/1700000053_off_volume_backups.js:12,30` | server-only | **Retire after cutover.** D1 uses Time Travel + `wrangler d1 export`; no S3 key needed. | Cloudflare dash → R2 → Manage API tokens → revoke |
| `ANTICIPY_BACKUP_S3_SECRET` | R2 S3 API (backups) | backend | `backend/pb_migrations/1700000053_off_volume_backups.js:13,31` | server-only | as above | as above |
| `ANTICIPY_BACKUP_S3_BUCKET` / `_ENDPOINT` / `_REGION` | R2 bucket coordinates | backend | `1700000053_off_volume_backups.js:10,11,27,28` | not secret | `vars` while still in use | n/a |

### The fail-open that `ANTICIPY_SERVICE_TOKEN` sits on

`backend/pb_hooks/guard.pb.js:25-26`:

```js
const token = $os.getenv("ANTICIPY_SERVICE_TOKEN");
if (!token) return e.next();
```

If that variable is unset, the guard passes **every** request through. And
`migration/d1/RULES.md` records that 42 rule slots across 11 of the 12 product
collections are `""` — PocketBase for *public*. So an unset service token is not
a degraded mode: it publishes every transcript, job, profile and receipt photo
to anyone who can guess a URL.

**Therefore the port must invert this.** In the Worker, a missing
`ANTICIPY_SERVICE_TOKEN` binding must return `503` and serve nothing — the
`internal_hq.pb.js:44` polarity, not the `guard.pb.js:26` polarity. This is
the same conclusion `migration/spec/CONTRACT.md:575` reaches independently.
Concretely, at the top of the Worker's fetch handler:

```ts
// A missing binding is a refusal, never a default. guard.pb.js:26 did the
// opposite and that is the single most dangerous line in the backend.
if (!env.ANTICIPY_SERVICE_TOKEN) {
  return Response.json({ error: "service is not configured" }, { status: 503 });
}
```

---

## §4. Brain — `anticipy-brain` (Container)

| NAME | Authenticates to | Component | Read at | Class | Cloudflare home | Rotation |
|---|---|---|---|---|---|---|
| `ANTICIPY_SERVICE_TOKEN` | `anticipy-api` | brain | `brain/pb.py:24` | server-only | see §3 — same value, both services | see §3 |
| `OPENROUTER_API_KEY` | OpenRouter | brain | `brain/llm.py:218` | server-only | container env via the Worker (§6c) | openrouter.ai → Keys |
| `GEMINI_API_KEY` | Google Generative AI | brain | `brain/llm.py:214` | server-only | container env | Google AI Studio |
| `BRAVE_API_KEY` | Brave Search | brain | `brain/worker.py:1737,1837`, `brain/anticipy_core.py:3630,3919` | server-only | container env | Brave Search API dash |
| `TAVILY_API_KEY` | Tavily Search | brain | `brain/worker.py:1738,1838` | server-only | container env | Tavily dash |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS | engine | `engine/app/product/tts.py:208,272` | server-only | container env | ElevenLabs → Profile → API key |
| `AWS_ACCESS_KEY_ID` | AWS (Polly TTS) | engine | `engine/app/product/tts.py:212` | server-only | container env | IAM → rotate access key; scope to `polly:SynthesizeSpeech` only |
| `AWS_SECRET_ACCESS_KEY` | AWS (Polly TTS) | engine | `engine/app/product/tts.py:214` | server-only | container env | as above, rotate as a pair |
| `TWOCAPTCHA_API_KEY` | 2Captcha | engine | `engine/app/config.py:86` | server-only, spends money | container env | 2captcha dash |
| `KIMI_API_KEY` | Moonshot/Kimi | engine | `engine/app/config.py:74` | server-only | container env, or retire — `src/app/api/extension/auth/route.ts:101` already returns `null` for it | Moonshot console |
| `PROFILE_ENCRYPTION_KEY` | Fernet key for stored browser cookies | engine | `engine/app/config.py:126`, `engine/app/authsec/tokens.py:36` | server-only, **data-bearing** | container env | **Cannot be rotated alone** — re-encrypt every `browser_profiles` row first. Same hazard class as `ANTICIPY_VAULT_KEY`. |
| `ENGINE_INTERNAL_TOKEN` | engine's own internal routes | engine | `engine/app/config.py:108` | server-only | container env | Roll; update callers |
| `ANTICIPY_TRIGGER_SECRET` | the local desktop bridge on `127.0.0.1` | desktop, engine, scripts | `desktop/src-tauri/resources/anticipy-bridge.py:80`, `engine/app/product/universal_surface_runtime.py:32`, `engine/app/product/surface_dom_extractor.py:36` | local-only; **defaults to `"local-dev"`** | **Stays on the user's Mac.** Never a Cloudflare secret. | Per-install random value. See ROTATION.md §9. |
| `ANTICIPY_CLOUD_AUTH_TOKEN` | the cloud engine from the desktop app | desktop/engine | `engine/app/desktop_app.py:30`, `engine/app/anticipy/platform_adapter.py:251` | per-user bearer, held on the user's Mac | issued by `anticipy-web`; not a deploy secret | per-user reissue |
| `ADMIN_TRIGGER_SECRET` | engine admin trigger route | engine | `engine/app/main.py:534` | server-only; **falls back to `JWT_SECRET`** | container env | Roll |
| `ANTICIPY_ACCESS_CODE` | the extension access code | engine tests | `engine/test_real_machine.py:251`, `engine/test_extension_runner.py:343` | per-user bearer | never a deploy secret | **A real one is committed.** ROTATION.md §2. |
| `ANTICIPY_SMOKE_TOKEN` | smoke-test auth | engine scripts | `engine/scripts/broker_cost_cap_smoke.py:42`, `engine/scripts/profile_api_smoke.py:41` | test-only | not deployed | n/a |
| `RIG_SERVICE_TOKEN` | proof-harness rig | proof | `proof/day_zero_20.py:42`, `proof/test_workflow_security_rig.py:38`, `proof/test_supervisor_isolation_live.py:19` | test-only; **three different hardcoded defaults** | not deployed | ROTATION.md §9 |
| `RIG_TWILIO_AUTH_TOKEN` | proof-harness fake Twilio | proof | `proof/test_workflow_security_rig.py:39` | test-only, hardcoded default | not deployed | n/a |

### The supervisor hands its whole environment to every owner's worker

`brain/supervisor.py:79` — `env = dict(os.environ if base is None else base)`.
Every secret in the supervisor's environment is inherited by every per-owner
`brain.worker` subprocess. That is acceptable while all owners run in one trust
domain, and it is exactly why the per-owner state root exists. It is worth
stating because it means **there is no per-owner secret isolation today**, and
the container port should not accidentally advertise one.

---

## §5. Build, release and CI

| NAME | Authenticates to | Component | Read at | Class | Home | Rotation |
|---|---|---|---|---|---|---|
| `ASC_KEY_ID` | App Store Connect API | CI | `.github/workflows/ios-testflight.yml:20`, `clients/ios/scripts/app_store_connect.py:86` | identifier | GitHub Actions secret | ASC → Users and Access → Keys |
| `ASC_ISSUER_ID` | App Store Connect API | CI | `.github/workflows/ios-testflight.yml:21`, `clients/ios/scripts/app_store_connect.py:87` | identifier | GitHub Actions secret | stable per team |
| `ASC_KEY_P8` | App Store Connect API (**private key**, base64) | CI | `.github/workflows/ios-testflight.yml:38` | **private key** | GitHub Actions secret | ASC → Keys → revoke + generate. **Revoking is the only true rotation.** |
| `ASC_KEY_PATH` | path to the decoded `.p8` on the runner | CI | `.github/workflows/ios-testflight.yml:45`, `clients/ios/scripts/app_store_connect.py:88` | path, not a secret | workflow env | n/a |
| `R2_ACCESS_KEY_ID` | R2 S3 API (DMG upload) | release tooling | `tools/upload_dmg_to_r2.py:62` | server-only | GitHub Actions secret (and the operator's local `.env.local`) | Cloudflare → R2 → Manage API tokens |
| `R2_SECRET_ACCESS_KEY` | R2 S3 API (DMG upload) | release tooling | `tools/upload_dmg_to_r2.py:63` | server-only | GitHub Actions secret | as above, rotate as a pair |
| `R2_ENDPOINT` / `R2_BUCKET` / `R2_PUBLIC_URL` | R2 coordinates | release tooling | `tools/upload_dmg_to_r2.py:61,64,65` | not secret | workflow env / `vars` | n/a |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API (deploys) | CI | **new** — see §6d | server-only | GitHub Actions secret | Cloudflare → My Profile → API Tokens → Roll |
| `CLOUDFLARE_ACCOUNT_ID` | selects the account | CI, website | `src/lib/notification-adapter.ts:86` | identifier | `vars` / workflow env | n/a |

`DEVELOPMENT_TEAM: "49T86P9XGW"` is hardcoded at
`.github/workflows/ios-testflight.yml:19`. An Apple Team ID is a public
identifier (it is in every shipped app's provisioning profile); leaving it in
the workflow is fine.

---

## §6. The commands

### 6a. Worker secrets — literal command list

Run each; `wrangler` prompts for the value on stdin and never writes it to disk.
Values must come from the provider's dashboard or a password manager — never
from a file in this repo.

```sh
# ── anticipy-web ────────────────────────────────────────────────────────────
wrangler secret put SUPABASE_SERVICE_ROLE_KEY   --name anticipy-web
wrangler secret put STRIPE_SECRET_KEY           --name anticipy-web
wrangler secret put STRIPE_WEBHOOK_SECRET       --name anticipy-web
wrangler secret put RESEND_API_KEY              --name anticipy-web
wrangler secret put SENDGRID_API_KEY            --name anticipy-web
wrangler secret put DEEPGRAM_API_KEY            --name anticipy-web
wrangler secret put GOOGLE_API_KEY              --name anticipy-web
wrangler secret put GEMINI_API_KEY              --name anticipy-web
wrangler secret put GROQ_API_KEY                --name anticipy-web
wrangler secret put MISTRAL_API_KEY             --name anticipy-web
wrangler secret put DEEPSEEK_API_KEY            --name anticipy-web
wrangler secret put CEREBRAS_API_KEY            --name anticipy-web
wrangler secret put OPENROUTER_API_KEY          --name anticipy-web
wrangler secret put VOYAGE_API_KEY              --name anticipy-web
wrangler secret put TWILIO_BROKER_ACCOUNT_SID   --name anticipy-web
wrangler secret put TWILIO_BROKER_SID           --name anticipy-web
wrangler secret put TWILIO_BROKER_TOKEN         --name anticipy-web
wrangler secret put TWILIO_AUTH_TOKEN           --name anticipy-web
wrangler secret put GOOGLE_OAUTH_CLIENT_SECRET  --name anticipy-web
wrangler secret put ENCRYPTION_KEY               --name anticipy-web
wrangler secret put JWT_SECRET                   --name anticipy-web
wrangler secret put GATE_COOKIE_SECRET           --name anticipy-web
wrangler secret put GATE_PASSCODE_INTERNAL       --name anticipy-web
wrangler secret put GATE_PASSCODE_TRANSFER       --name anticipy-web
wrangler secret put ANALYTICS_SECRET             --name anticipy-web
wrangler secret put ANALYTICS_PASSWORD           --name anticipy-web
wrangler secret put AGENT_LOG_SECRET             --name anticipy-web
wrangler secret put CRON_SECRET                  --name anticipy-web
wrangler secret put CLOUDFLARE_EMAIL_API_TOKEN   --name anticipy-web

# MAIL_RESEND_API_KEY: only if a second Resend account is genuinely in use.
# META_MONITOR_TEST_SECRET: only if /api/test-meta-monitor is deployed at all.

# ── anticipy-api ────────────────────────────────────────────────────────────
wrangler secret put ANTICIPY_SERVICE_TOKEN      --name anticipy-api
wrangler secret put ANTICIPY_INTERNAL_KEY       --name anticipy-api
wrangler secret put ANTICIPY_VAULT_KEY          --name anticipy-api
wrangler secret put ANTICIPY_VAULT_KEY_GCM      --name anticipy-api   # after reencrypt_vault.md
wrangler secret put CLERK_HQ_JWT_KEY            --name anticipy-api
wrangler secret put TWILIO_ACCOUNT_SID          --name anticipy-api
wrangler secret put TWILIO_AUTH_TOKEN           --name anticipy-api
wrangler secret put TWILIO_API_KEY_SID          --name anticipy-api
wrangler secret put TWILIO_API_KEY_SECRET       --name anticipy-api
wrangler secret put SENDBLUE_API_KEY_ID         --name anticipy-api   # outbound: src/messaging.ts
wrangler secret put SENDBLUE_API_SECRET_KEY     --name anticipy-api   # rotate as a pair
wrangler secret put SENDBLUE_WEBHOOK_SECRET     --name anticipy-api   # inbound: /sms/sendblue; Sendblue → Developer → Webhooks, same value both sides
wrangler secret put GEMINI_API_KEY              --name anticipy-api
wrangler secret put OPENROUTER_API_KEY          --name anticipy-api
wrangler secret put CAPSOLVER_API_KEY           --name anticipy-api

# ── anticipy-brain (the Worker in front of the Container) ───────────────────
wrangler secret put ANTICIPY_SERVICE_TOKEN      --name anticipy-brain
wrangler secret put OPENROUTER_API_KEY          --name anticipy-brain
wrangler secret put GEMINI_API_KEY              --name anticipy-brain
wrangler secret put BRAVE_API_KEY               --name anticipy-brain
wrangler secret put TAVILY_API_KEY              --name anticipy-brain
wrangler secret put ELEVENLABS_API_KEY          --name anticipy-brain
wrangler secret put AWS_ACCESS_KEY_ID           --name anticipy-brain
wrangler secret put AWS_SECRET_ACCESS_KEY       --name anticipy-brain
wrangler secret put TWOCAPTCHA_API_KEY          --name anticipy-brain
wrangler secret put PROFILE_ENCRYPTION_KEY      --name anticipy-brain
wrangler secret put ENGINE_INTERNAL_TOKEN       --name anticipy-brain
wrangler secret put ADMIN_TRIGGER_SECRET        --name anticipy-brain
wrangler secret put TWILIO_ACCOUNT_SID          --name anticipy-brain
wrangler secret put TWILIO_AUTH_TOKEN           --name anticipy-brain
```

Verify and audit:

```sh
wrangler secret list --name anticipy-web     # names only; values are write-only
wrangler secret list --name anticipy-api
wrangler secret list --name anticipy-brain
wrangler secret delete OLD_NAME --name anticipy-web
```

For a scripted first load, `wrangler secret bulk` reads a flat JSON object of
`{"NAME": "value"}`. If you use it, write the file to a `tmpfs`/`mktemp` path,
`chmod 600`, and `shred` it in a trap — never inside the repo, which is public:

```sh
f=$(mktemp) && chmod 600 "$f"
trap 'rm -P -f "$f" 2>/dev/null || rm -f "$f"' EXIT
# ...populate $f from your password manager's CLI, not by hand...
wrangler secret bulk "$f" --name anticipy-web
```

### 6b. Plaintext config — `wrangler.jsonc`

`wrangler.jsonc` is a **tracked file in a public repository**. Everything in
`vars` is published. This is the complete set that belongs there:

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "anticipy-web",
  "main": ".open-next/worker.js",
  "compatibility_date": "2026-09-01",
  "compatibility_flags": ["nodejs_compat"],

  // Public identifiers and knobs ONLY. If leaking it costs money or data,
  // it is `wrangler secret put`, not here. See SECRETS.md §0.
  "vars": {
    "CLOUDFLARE_ACCOUNT_ID": "",            // account identifier, not a credential
    "GOOGLE_OAUTH_CLIENT_ID": "",           // public by OAuth design
    "TWILIO_MESSAGING_SERVICE_SID": "",     // identifier
    "TWILIO_PHONE_NUMBER": "",              // the number itself is public
    "TWILIO_STATUS_CALLBACK_URL": "",       // src/lib/notification-adapter.ts:150
    "ANTICIPY_NOTIFY_EMAIL_PROVIDER": "auto",   // notification-adapter.ts:83
    "ANTICIPY_NOTIFY_FROM_EMAIL": "",           // notification-adapter.ts:100
    "ANTICIPY_NOTIFY_FROM_NAME": "Anticipy",    // notification-adapter.ts:106
    "ANTICIPY_NOTIFY_FROM_ALLOWLIST": "",       // notification-adapter.ts:114
    "ADMIN_EMAIL": "",                      // src/app/api/engine/analyze/route.ts:889
    "OWNER_EMAIL": "",                      // src/lib/email.ts:31
    "NODE_ENV": "production"
  },

  "d1_databases": [
    { "binding": "DB", "database_name": "anticipy", "database_id": "" }
  ],
  "r2_buckets": [
    { "binding": "BACKUPS", "bucket_name": "anticipy-pocketbase-backups-production" }
  ],
  "observability": { "enabled": true }
}
```

Note that `wrangler.jsonc` has no `[vars]` TOML table — in JSONC it is the
`"vars"` object above. If the migration keeps `wrangler.toml` instead, the same
set goes under a literal `[vars]` table.

### 6c. Getting secrets into the Container

Cloudflare Containers are started by a Worker. The Worker holds the secrets
(`wrangler secret put --name anticipy-brain`, §6a) and passes them into the
container instance as environment variables when it starts it. Do **not** bake
any credential into the container image — the image is built from this public
repo's Dockerfile and its layers are not a secret store.

If passing env into the container turns out to be unavailable or awkward
(marked UNVERIFIED below), the fallback needs no new mechanism: keep every
credential in the Worker, expose a single internal endpoint on the Worker that
the container calls over the container↔Worker binding, and have the container
hold nothing but the address of its own Worker. That is strictly better anyway
— it makes each outbound provider call auditable and lets a leaked container
be revoked without touching the providers.

### 6d. The Cloudflare API token for CI — exact permissions

Create at **Cloudflare dashboard → My Profile → API Tokens → Create Token →
Create Custom Token**. Store as the GitHub Actions secret `CLOUDFLARE_API_TOKEN`.

Permissions — grant exactly these and nothing more:

| Scope | Permission | Access | Needed for |
|---|---|---|---|
| Account | **Workers Scripts** | Edit | `wrangler deploy` for all three services |
| Account | **D1** | Edit | `wrangler d1 execute --remote`, `d1 migrations apply` |
| Account | **Workers R2 Storage** | Edit | `wrangler r2 object put` (DMG upload, backups) |
| Account | **Account Settings** | Read | wrangler resolving the account |
| Account | **Workers KV Storage** | Edit | *only if* a KV namespace is actually used — omit otherwise |
| Account | **Workers Tail** | Read | `wrangler tail` in CI; omit if unused |
| User | **User Details** | Read | `wrangler whoami` |
| Zone (`anticipy.ai` only) | **Workers Routes** | Edit | custom domains / route bindings |

Account Resources: **Include → the single Anticipy account**, not "All accounts".
Zone Resources: **Include → Specific zone → anticipy.ai**, not "All zones".
Client IP Address Filtering: leave unset — GitHub-hosted runners have no stable
egress range, so an IP filter here will either be wrong or so broad it is
theatre. TTL: set an expiry and put the renewal in the calendar.

**Not on the list, deliberately:** Zone DNS Edit, Zone Cache Purge, Account
Access/Zero Trust, Account Billing, Account Member Management, Zone SSL. A
Workers deploy needs none of them, and a token that can edit DNS is a token that
can take the domain away from you.

**Containers deploy** — the exact permission name is marked UNVERIFIED below.
Determine it empirically: deploy the container with the token above; if it is
refused, the API error names the missing permission. Add only that one.

---

## §7. Findings this sweep produced

These are inventory facts with security consequences. They are ranked and given
concrete actions in `ROTATION.md`; they are listed here because they change how
the secrets above must be treated.

1. **Five live LLM keys are handed to clients over CORS `*`.**
   `src/app/api/extension/auth/route.ts:109-121` returns `cerebrasApiKey`,
   `groqApiKey`, `geminiApiKey`, `mistralApiKey`, `deepseekApiKey` as plaintext
   JSON, with `Access-Control-Allow-Origin: *` (`route.ts:20-23`, `:124-128`),
   gated only by an access code. Those five keys are therefore **already on
   every extension user's machine**. Marking them "server-only" in §2a is the
   intent, not the reality, until this endpoint becomes a proxy.
   The backend already shows the right shape: `backend/pb_hooks/agent_key.pb.js`
   exposes `/agent/llm`, which uses `GEMINI_API_KEY`/`OPENROUTER_API_KEY`
   server-side (`:202-203`) and returns *completions*, never keys. Port
   `/api/extension/auth` to that shape and the five rows become honest.

2. **A real production access code is committed.**
   `engine/test_real_machine.py:247-249` names it as the owner's own code and
   `src/app/api/extension/auth/route.ts:51` repeats it in a comment. Also in
   `engine/test_multi_agent_brain.py:31`, `STATUS.md:47`,
   `AUTONOMY_PLAN.md:95`, `engine/test_real_machine.py:25`. Public since
   2026-05-09. Combined with (1), this is a working credential for the five
   keys. ROTATION.md §2.

3. **A live Cerebras key is still in the working tree.**
   Removed from the two source files, but quoted in full in the bug report that
   documented it: `planning/00-handoff/BUG_LIST.md:121` and `:251`, byte-identical
   to the value committed in `b9602058`. ROTATION.md §1.

4. **Three hardcoded default HMAC secrets ship in the public repo.**
   `src/lib/engine-transfer-gate.ts:12`, `src/lib/confirm-token.ts:30`,
   `src/lib/analytics-auth.ts:6`. Each is reached only when its env vars are
   unset — which is exactly the state a fresh Cloudflare environment starts in.
   Set `GATE_COOKIE_SECRET`, `JWT_SECRET` and `ANALYTICS_SECRET` explicitly on
   `anticipy-web` **before** first deploy, and delete the literals. ROTATION.md §4.

5. **`GATE_COOKIE_SECRET` and `JWT_SECRET` silently fall back to
   `SUPABASE_SERVICE_ROLE_KEY`** (`src/lib/gate-cookie.ts:27-29`,
   `src/lib/confirm-token.ts:28-31`, `src/lib/analytics-auth.ts:4-5`). That
   couples three unrelated rotations to one key and makes the site an HMAC
   oracle over the service role key. Setting all three explicitly costs nothing
   and removes the coupling.

6. **`ANTICIPY_SERVICE_TOKEN` fails open** (`backend/pb_hooks/guard.pb.js:26`).
   §3 above specifies the inversion the Worker must make.

---

## §8. Missing-secret behaviour — what the Worker must do

The single most useful thing this migration can fix. Today the behaviours are
inconsistent; specify them once and hold every ported route to it.

| Secret | Today, if unset | Must be, in the Worker |
|---|---|---|
| `ANTICIPY_SERVICE_TOKEN` | **guard passes everything** (`guard.pb.js:26`) | `503`, serve nothing |
| `ANTICIPY_INTERNAL_KEY` | `503` (`internal_hq.pb.js:44`) | unchanged — correct |
| `ANTICIPY_VAULT_KEY` | `503` unless exactly 32 chars (`internal_hq.pb.js:3053`) | unchanged — correct |
| `GATE_PASSCODE_TRANSFER` | random sentinel in prod, dev default otherwise (`engine-transfer-gate.ts:49-51`) | unchanged — correct |
| `ANALYTICS_PASSWORD` | `false` in prod, a hardcoded dev literal otherwise (`analytics-auth.ts:37-41`) | `false` always; drop the dev literal |
| `GATE_COOKIE_SECRET` | falls back to service role key, then throws (`gate-cookie.ts:27-35`) | `503`, no fallback |
| `JWT_SECRET` (confirm tokens) | falls back to service role key, then a **public literal** (`confirm-token.ts:28-32`) | `503`, no fallback |
| `GATE_COOKIE_SECRET` (transfer gate) | falls back to `JWT_SECRET`, then a **public literal** (`engine-transfer-gate.ts:10-13`) | `503`, no fallback |
| `ANALYTICS_SECRET` | falls back to service role key, then a **public literal** (`analytics-auth.ts:4-6`) | `503`, no fallback |
| every LLM key | provider skipped, cascade continues | unchanged — correct |
| `CAPSOLVER_API_KEY` | `captcha_solve.pb.js:33` | refuse the solve, do not silently succeed |

---

## §9. Unverified

* **Container environment variables.** §6c asserts that a Worker passes env vars
  into the container instance it starts. I did not verify the exact binding
  shape or field name against current Cloudflare documentation, and there is no
  container config anywhere in this tree to read it off. Confirm before relying
  on it; the fallback in §6c needs no new mechanism.
* **The Cloudflare API-token permission that authorises a Containers deploy.**
  Not asserted. Determine it from the API's own error, as §6d says.
* **Cloudflare Secrets Store.** An account-level secret store with a
  `secrets_store_secrets` binding would let one secret be shared across all three
  Workers instead of being `wrangler secret put` three times (`OPENROUTER_API_KEY`,
  `GEMINI_API_KEY`, `TWILIO_AUTH_TOKEN`, `ANTICIPY_SERVICE_TOKEN` are each
  duplicated today). I believe this exists but did not verify its availability
  on this account or its exact binding syntax, so §6a specifies per-Worker
  secrets, which certainly work. Worth revisiting.
* **Whether every secret named here is actually set in production today.** This
  is a sweep of what the *code reads*, not of what Railway and Vercel currently
  hold. The Vercel snapshot in the tree (`vercel-env-snapshot.md`) is a
  Playwright accessibility dump with no variable names in it, so it settles
  nothing. Before cutover, dump the real sets (`vercel env ls`, Railway
  variables) and diff against §2–§5; a name in production that is absent here is
  either dead or a gap in this sweep, and both are worth knowing.
* **`brain/` and `engine/` overlap.** Rows attributed to "brain" include
  `engine/app/**` reads, because both run inside the same supervised process
  tree on Railway today. If the container split puts them in different images,
  §4 must be split with them.
* **Phone numbers.** 15 distinct `+1XXXXXXXXXX` literals are committed across
  `engine/scripts/`, `extension/tests/`, `clients/ios/Tests/` and
  `scripts/v7/`. They look like test fixtures. I did not confirm that none is a
  real subscriber number, and they are PII rather than credentials, so they are
  noted here rather than in ROTATION.md.
