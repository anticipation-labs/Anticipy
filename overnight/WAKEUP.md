# WAKEUP — Anticipy overnight status (2026-07-04 → 05)

## The bar Omar set (asleep ~6h, checks hourly, no complaints by morning)
CLOUD is the system (LOCAL PAUSED). "Done" = the extension paired to the CLOUD engine, tap "Go ahead"
→ the browser ACTUALLY does it → verified by the REAL ARTIFACT (a draft in Gmail), never a log.
Browser-only, no APIs. Never fake; never touch Omar's real accounts overnight.

## What's genuinely DONE + verified live (cold-walked, not "proven in code")
- **approve→ACT WIRING** (a30e06f, deployed d90e1022): type task → card+chips (live, no reload) → tap
  "Go ahead" → real /resolve → "Done ✓". Root cause was the whole ask machinery gated on
  `execute_actions:true` but the composer previews with `execute_actions:false`. Money held, vents silent.
- Theme, browser-only (/connect deleted, API arm gone), clean onboarding, clean board, retraction
  cardinal-sin wired, send→reply live-append, honest failed-copy, polling. All deployed + verified.
- **HONEST**: that "Done ✓" is the engine RESOLVING in mock hands — it does NOT actually draft the email.
  That's the frontier below.

## THE REAL REMAINING WORK — "the hands" (task #31): extension → CLOUD browser-action
Audit found MOST of it is already real: extension CDP observe→act, WebVoyagerAgent, per-user pairing
crypto (/ws/pair, signed apc1 codes), judge-verified receipt. MOCK/MISSING = 4 narrow things:
1. Extension defaulted to localhost → repoint to cloud + rebuild the .zip.  [agent a9fcbd95 RUNNING]
2. NO pairing UI in the app (the "at scale" gap) → build SetupScreen mint-code→pair flow.  [agent aa239f5c RUNNING]
3. Railway engine flags off → set ANTICIPY_PER_USER_HANDS=1 + ENGINE_INTERNAL_TOKEN=<secret>.  [TODO config]
4. No independent artifact re-verification (Done = judge+screenshot, not a re-read of the real draft).  [TODO]
+ Second-wave audit fixes #30 (jsonFetch Supabase bearer, ephemeral stores, per-card autonomy, onboarding routing).

## Deploy discipline (learned the hard way — DO NOT SKIP)
`railway up` can silently NOT land; builds ~2-8min. ALWAYS: note current top deployment id
(`railway deployment list`) → `railway up --detach` → poll until a NEW id shows SUCCESS → verify by the
cloud's real behavior (execution.ask_id / the artifact), NOT /health. Vercel: --prod --yes, wait READY, alias.

## The one honest wall (NEEDS-OMAR — get one-click-ready, do NOT fake or touch his account)
The final "extension drafts in YOUR real Gmail, verified by the draft" needs Omar's Chrome + extension +
logged-in Gmail. I build everything to one-click-ready + flag it. Also: Supabase email provider confirm
(ogbxpqkmsdrcuilafycn), TWILIO_AUTH_TOKEN, first live call, final safety pass.
