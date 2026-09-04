# The 51 Railway variables: which the migration needs

Derived from the code, not from the dashboard:
  backend : grep '$os.getenv("X")' over backend/pb_hooks/*.js   -> 27 distinct
  worker  : grep os.environ over brain/*.py                     -> 32 distinct

Railway shows 29 and 22. The small differences are Railway's own injected vars
(RAILWAY_PUBLIC_DOMAIN, PORT) and a few set-but-unread leftovers.

## CARRY (real credentials — these must exist on Cloudflare)

| variable | who reads it | notes |
|---|---|---|
| ANTICIPY_SERVICE_TOKEN | both | THE lock on the data API. guard.pb.js fails OPEN without it; the Worker fails CLOSED. |
| ANTICIPY_VAULT_KEY | backend | AES-256 key for internal_passwords. VERIFIED 2026-09-04: standard AES-GCM, 12-byte prepended nonce, decrypts under WebCrypto. Ports directly; no re-encryption needed. |
| ANTICIPY_INTERNAL_KEY | backend | HQ's own auth, separate from PocketBase auth. Also seeds the ICS feed token. |
| CLERK_HQ_JWT_KEY | backend | HQ's Clerk sign-in exchange. |
| OPENROUTER_API_KEY | both | the LLM. |
| GEMINI_API_KEY | both | PROVIDER SWITCH, not an extra key — brain/llm.py:133 prefers Gemini unconditionally and swaps the model. Carry the value; keep it UNSET unless deliberately switching. |
| RESEND_API_KEY | backend | outbound email. |
| TWILIO_ACCOUNT_SID / _AUTH_TOKEN | both | AUTH_TOKEN is load-bearing twice: outbound fallback AND the only thing that validates an inbound webhook signature. Twilio offers no API-key equivalent for signatures. |
| TWILIO_PHONE_NUMBER / _FROM | both | |
| TWILIO_API_KEY_SID / _SECRET | backend | the pair in .env.local is DEAD (401). Mint fresh or leave unset. |
| CAPSOLVER_API_KEY | backend | server-side captcha. |
| BRAVE_API_KEY, TAVILY_API_KEY | worker | research lane. |

## RECONFIGURE (same idea, different value on Cloudflare)

| variable | becomes |
|---|---|
| ANTICIPY_PB | the Worker's URL, not the Railway one. Baked into shipped clients — see runbooks/CLIENTS.md. |
| ANTICIPY_PUBLIC_URL, ANTICIPY_HQ_ORIGIN, ANTICIPY_TWILIO_WEBHOOK_URL | new hostnames. The Twilio one must be updated IN THE TWILIO CONSOLE too, or inbound SMS keeps hitting Railway. |
| ANTICIPY_MEMORY_DB, ANTICIPY_STATE_ROOT, ANTICIPY_STATE_VOLUME_ROOT | Railway VOLUME paths. Containers have ephemeral disk — this per-owner memory must move to D1/R2/DO. The single biggest brain-side task. |
| ANTICIPY_BACKUP_S3_* (5 vars, both services) | already Cloudflare R2, but on ACCOUNT 5b63e25e, which this login cannot see. Reissue against 114587b7 once the bucket is copied. |

## DROP (Railway-specific or plain config)

RAILWAY_PUBLIC_DOMAIN, PORT — injected by Railway; Workers has neither.
PYTEST_CURRENT_TEST — a test-runner artifact that got read in product code.

Everything else is tuning, not secrets, and can be re-declared as plaintext
`vars` in wrangler.jsonc rather than `wrangler secret put`:

  ANTICIPY_MODEL, _AUX_MODEL, _STRONG_MODEL, _BROWSER_MODEL, _VISION_MODEL,
  _GEMINI_MODEL, _INTERNAL_MODEL, _TZ, _INTERNAL_TZ, _SUPERVISED, _SEGMENTS,
  _SEGMENT_TRIAGE, _LINKS, _LLM_LEDGER, _CLOCK_STATE, _MAX_OWNER_WORKERS,
  _OWNER_DISCOVERY_SECONDS, _STATE_BACKUP_SECONDS, _HQ_LOGIN_CEILING,
  _INTERNAL_LLM_CEILING, _HQ_PAGE, _FELLOWSHIP_URL, _RESEARCH_OWNER_REF,
  _WEBHOOK_MANAGER, _BACKUP_REQUIRED, TWILIO_API_BASE, TWILIO_MOCK

## Two that carry a hazard

ANTICIPY_OWNER_ID / ANTICIPY_OWNER_PHONE — bind ONE worker process to ONE
person. brain/worker.py texts ANTICIPY_OWNER_PHONE about that owner's errands.
Setting the phone to someone else while the id stays Omar's texts that person
about HIS life. Carry them; do not guess them.

## Answer to "do we need all of them"

No. Roughly 15 are real credentials that must move, ~8 need new values, 2 are
Railway-only and die with it, and the remaining ~26 are model names, timeouts
and feature flags that belong in wrangler.jsonc as plain vars where they are
readable in a diff instead of hidden behind seven asterisks.
