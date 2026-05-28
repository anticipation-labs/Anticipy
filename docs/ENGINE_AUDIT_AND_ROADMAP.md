# Anticipy Action Engine — Audit & Roadmap to v1

**Status**: Draft 1 · 2026-04-30
**Scope**: `/engine/` Python service + the engine-touching surface of the Next.js site (`/src/app/api/engine/*`, `/src/app/engine`, `/src/app/admin`, `/src/app/internal`, `/src/app/demo`) + path to investor-grade v1 + hardware transferability
**Audience**: Omar (founder), any new senior engineer onboarded onto the engine, any investor doing technical diligence

---

## 0. TL;DR

Anticipy's Action Engine is the moat. Every other wearable AI in 2026 — Limitless (acquired by Meta Dec 5 2025), Friend.com (being vandalized in NYC), Bee Computer (Amazon-incubated, $49), Plaud, Omi, Humane (dead, HP wrote it down to $116M) — *records*. None of them *act*. Anticipy already has a working browser agent that closes loops on real websites; nothing else in this category does.

That advantage is undermined today by:

- **Five P0 security holes on the website's engine API surface** that let an unauthenticated stranger from the public internet (a) create fake sessions, (b) trigger spam emails/SMS to the founder's hard-coded test number, (c) execute any pending intent by guessing UUIDs, (d) read the Deepgram API key out of the client bundle, and (e) bypass the entire access-code system because two of the access codes are the literal string `"123"` checked into git.
- **Five P0 reliability/security holes inside the engine itself**: a hardcoded JWT default secret, a Fernet encryption key that regenerates on every process restart (i.e., every restart wipes every saved cookie), no graceful degradation when both LLM providers fail, no real browser-process cleanup (the system will accumulate zombie Chrome processes under load), and a `/execute-intent` REST endpoint that auto-confirms every action — even purchases — with no user in the loop.
- **A growing gap between marketing and prototype**: the website promises an 8 g brushed titanium pendant whose audio "never touches the internet"; the actual `firmware/` and `internal/docs/hardware` describe an 18 g matte-black PETG ESP32-S3 board that uploads audio clips directly to `anticipy.ai`. An investor or journalist who picks up the prototype will see this immediately. Both stories can be true (prototype vs v1), but the engine architecture must be designed for whichever one is the v1 launch story, and that decision hasn't been made on paper yet.

Two-to-three weeks of focused engineering against §3 and §4 of this document closes the security gaps, makes the engine boring-but-reliable, and brings per-task cost from current ~$0.001-0.005 (Gemini 2.5 Flash heavy use) to ~$0.018-0.025 routed (Scout → Haiku 4.5 → Sonnet 4.6 with prompt caching). Eight to ten weeks gets us a hardware-transfer-ready architecture (§9). Twelve to sixteen weeks gets us a credible alpha proactive engine (§7) that can demo as "Donna" rather than "Siri who books restaurants."

The remaining decisions are five product calls only Omar can make (§11). They block roughly half the implementation work; he should answer them this week.

---

## 1. The product, in one paragraph

Anticipy is a wearable that listens to ambient conversation and autonomously completes the small tasks people mention but never get around to (book the dinner, cancel the trial, dispute the charge, schedule the follow-up). It has three stages: **Ears** — a pendant capturing audio over BLE; **Brain** — a phone app diarizing the user's own voice, transcribing locally, classifying intent; **Hands** — the Action Engine, a Python/FastAPI service that drives a stealth Chromium via Browser Use to execute tasks on real websites. This document is a roadmap to make Hands perfect before Ears and Brain are built around it. The Action Engine is the moat.

## 2. Where we are today

### 2.1 Engine (`/engine/`)

| Module | LOC | Status |
|---|---|---|
| `app/agent.py` | 580 | Core. Browser Use wrapper. Clean. |
| `app/main.py` | 578 | FastAPI + WebSocket. Partial. |
| `app/browser.py` | 557 | **Dead** (legacy, not imported) |
| `app/captcha.py` | 365 | NopeCHA + 2Captcha + CapSolver |
| `app/models.py` | 358 | LLM fallback chain |
| `app/harness.py` | 308 | **Dead** (legacy, not imported) |
| `app/safety.py` | 151 | Deterministic, solid |
| `app/router.py` | 132 | Pre-classify + LLM fallback |
| `app/auth.py` | ~150 | bcrypt 12-round, in-memory rate limit |
| `app/planner.py` | ~90 | Goal decomposition, URL extraction |
| `app/vision.py` | 64 | **Stub** (always returns None) |
| `test_real.py` | 470 | 9 real-site browser tests + classifier tests |
| **Engine total** | **~4,200** | **~92% prototype, ~8% production** |

**Working today**: WebSocket task streaming with intermediate status updates; deterministic safety filter that LLM cannot override; real-world test suite hitting OpenTable, Amazon, GitHub, SauceDemo, Cloudflare, reCAPTCHA, login forms (target 9/10 passing); per-user encrypted cookie store keyed on `(user_id, site_domain)`; in-memory login rate limiter (5 failures / 30 min); per-task budget caps (40 steps, 300 s, $0.08).

**Broken or missing for production**: see §3.

### 2.2 Website engine surface (`/src/app/api/engine/*`, `/src/app/engine`, `/src/app/internal`, `/src/app/demo`)

5 P0 + 6 P1 issues catalogued in §3 and Appendix B. The marketing surface is fine; the engine API surface is the worst part of the codebase. Most of it shipped without auth on the assumption that the WebSocket transport authenticated the user — it does, but parallel REST endpoints (`/api/engine/session`, `/api/engine/analyze`, `/api/engine/transcribe`, `/api/engine/confirm`) reach the same backend without that auth.

### 2.3 Hardware (current prototype vs v1 marketing claims)

| Dimension | Marketing (`/funded`, homepage) | Current prototype (`firmware/`, `internal/docs/hardware`) |
|---|---|---|
| Body | 8 g brushed titanium (silver/gold) | 18 g matte black PETG (3D-printed) |
| Compute | nRF5340 | ESP32-S3 |
| Mic | (unspecified) | INMP441 MEMS |
| Battery | 200 mAh, "wireless charging up to 15 ft" | 400 mAh LiPo, USB-C |
| Audio architecture | "Audio never touches the internet … encrypted Bluetooth to phone, classified, **discarded in seconds**" | **"Ships audio clips to the Anticipy cloud engine for transcription"** |
| Dims | (unspecified) | 38 × 25 × 11 mm |

This gap is not a problem if the v1 product (Sept 2026 prototype, Nov 2026 limited launch, Q1 2027 scale per `/funded`) ships the marketed architecture. It **becomes a problem** if a journalist or investor picks up the current prototype before then and tweets a side-by-side. The engine has to be designed for the v1 architecture (audio diarized on-device, only short text instructions cross the network), not the prototype's architecture.

## 3. The 12 critical risks (P0)

Every one of these should be fixed before another user touches the engine. Most are <2 hours each. All are verified against current code, not the 25-day-old project memory.

### Engine

**P0-E1 — Hardcoded JWT secret default** · `engine/app/config.py:28` · 30 min
`JWT_SECRET = os.environ.get("JWT_SECRET", "anticipy-engine-secret-change-me")`. If the env var is unset on any deployment, every user token is forgeable by anyone reading this repo. Fix: refuse to start unless `JWT_SECRET` is set and ≥32 bytes; remove the default.

**P0-E2 — Fernet encryption key regenerates on every restart** · `engine/app/config.py:44-46` · 1 h
`PROFILE_ENCRYPTION_KEY: str = os.environ.get("PROFILE_ENCRYPTION_KEY", Fernet.generate_key().decode())`. Every process restart generates a new key, which means every previously encrypted cookie in `browser_profiles` becomes unrecoverable. Users have to re-login to every site after a deploy. Fix: refuse to start without `PROFILE_ENCRYPTION_KEY`; document the rotation procedure.

**P0-E3 — `/execute-intent` REST endpoint auto-confirms every action** · `engine/app/main.py:333-334` · 2 h
`async def receive_confirmation() -> str: return "confirmed"  # Auto-confirm for API-driven executions`. This is the only confirmation gate. Any caller — including the website's `/api/engine/confirm` route, which is itself unauthenticated (P0-W3) — can execute purchases, sends, deletes without a real user in the loop. Fix: remove auto-confirm; require an explicit `confirmed_at` timestamp + signed token from the originating client; fail closed on missing confirmation for any action that hits `safety.check_needs_confirmation()`.

**P0-E4 — No browser process cleanup under load** · `engine/app/agent.py:461-468`, `main.py:545-572` · 1-2 h
Browser session is closed in a `try/finally`, but: (a) on WebSocket disconnect the background task is *not* cancelled; it keeps running and holds the browser; (b) if `session.stop()` itself hangs the process leaks; (c) no subprocess-level fallback. Fix: cancel the background task on `WebSocketDisconnect`; wrap `session.stop()` in `asyncio.wait_for(timeout=5)`; on timeout `pkill -f patchright` as a hard fallback; emit a leak-counter metric.

**P0-E5 — Silent total failure when all LLM providers are down** · `engine/app/models.py:283-332`, `router.py:80-93`, `planner.py` · 2 h
If Gemini and Groq both 5xx (Groq had a 90-min outage in 2024), `llm_call` returns `None`, the router defaults to `"ambiguous"`, the planner falls through to a Google search — the user sees a confusing partial response and has no idea why it didn't work. Fix: degraded-mode response when all providers fail ("Our planning service is temporarily unavailable; want me to try a simpler approach?"); structured error log with provider trace; circuit-breaker that short-circuits for 60 s after N consecutive failures.

### Website

**P0-W1 — Hardcoded passcode `"123"` in two gates** · `src/app/demo/page.tsx:5`, `src/app/internal/layout.tsx:25` · 30 min
String comparison, in version control. `/demo` and `/internal` are publicly reachable (sitemap includes `/internal`). Fix: delete both gates entirely if they're unused, or replace with a Supabase auth check.

**P0-W2 — `/api/engine/session` and `/api/engine/analyze` require no auth** · `src/app/api/engine/session/route.ts`, `src/app/api/engine/analyze/route.ts` · 2-4 h
Anyone can `POST /api/engine/session` to create a fake `anticipy_sessions` row, then `POST /api/engine/analyze` with an arbitrary transcript. The analyze route then (a) broadcasts the result to the public Supabase Realtime channel `"anticipy-intents"` (which any subscriber receives), and (b) sends notification email/SMS hardcoded to `TEST_USER_EMAIL` / `TEST_USER_PHONE` env vars (`src/app/api/engine/analyze/route.ts:198,228`). This is a free spam vector pointed at Omar's phone. Fix: require a Supabase JWT or signed engine session token on every engine API route; use it as the routing key for notifications; strip the hardcoded test recipients from the analyze code path.

**P0-W3 — `/api/engine/confirm` lets anyone execute any pending intent by UUID** · `src/app/api/engine/confirm/route.ts` · 2 h
`GET /api/engine/confirm?intentId=<uuid>&action=yes` runs the intent. No auth, no ownership check. Iterating UUIDs (or scraping them from the Realtime broadcast) is a one-line attack. Fix: require auth; verify `intent.user_id == request.user.id`; rate-limit per IP and per intent.

**P0-W4 — Deepgram API key returned to the client** · `src/app/api/engine/deepgram-key/route.ts` · 1-2 h
The route returns the raw `DEEPGRAM_API_KEY`. Anyone who hits the engine page once can extract it from network tab and bill Deepgram against your account. Fix: server-issued short-lived (15-min) tokens via Deepgram's `/v1/auth/grant`; never return the master key.

**P0-W5 — HTML injection in the confirm-route response** · `src/app/api/engine/confirm/route.ts:133-134,157` · 1 h
`result.data?.task` is interpolated into an HTML response without escaping. If the agent's task description ever contains `<script>` (it can — site content is influencing it), it executes in the user's browser. Fix: escape with `escape-html` or render as plain text.

### Marketing/product

**P0-P1 — Marketing-vs-prototype audio architecture mismatch** · `firmware/`, `src/app/internal/docs/hardware/page.tsx`, marketing copy · product decision (see §11.Q1)
The marketing claim "audio never touches the internet" is the privacy wedge against Meta. The current prototype contradicts it. This must be resolved before any press, demo day, or investor walkthrough where someone might pick up the device. The engine architecture also depends on the answer: if v1 ships the marketed architecture, the engine should reject any audio-bearing payloads at the API boundary; if v1 streams audio to the cloud, the engine needs an audio ingestion endpoint with very strong PII handling.

**P0-P2 — Engine API surface is reachable from the public internet without an engine session** · multiple
The combined effect of P0-W2/W3 + the missing RLS on engine tables (P1-W3) means anyone can drive the engine without ever creating an account. Fix is the same as P0-W2/W3 plus a Supabase RLS audit.

## 4. The 18 must-fix issues (P1)

Condensed; full descriptions in Appendix A and B.

### Engine

1. **JWT expiry 72 h → 1 h with refresh token** · `config.py:30` · 3 h
2. **Login rate limit in-memory only** (lost on restart) → move to Supabase with TTL · `auth.py:22-49` · 2 h
3. **Password policy 6 chars** → 12 chars + complexity + HIBP check · `main.py:207-208` · 1 h
4. **Per-user Fernet key derivation** (one master key today protects every user's cookies) · `agent.py:39-42` · 4 h
5. **WebSocket connection lifecycle**: no heartbeat, no idle timeout, no cancel-task-on-disconnect · `main.py:572-579` · 2 h
6. **Concurrency cap on Browser Use sessions** (today: unbounded; will OOM around 50 concurrent) · `main.py` · 2 h
7. **Structured logging + Sentry/error tracking** with request-ID propagation · across · 4 h
8. **Action-level logging in `engine_tasks`** (today: one row per task with final status only) · `main.py:361-376` · 3 h
9. **Supabase RLS audit** on `engine_users`, `browser_profiles`, `engine_tasks`, `anticipy_sessions`, `anticipy_intents`, `anticipy_admin_users` · 2 h + however long the policy work takes
10. **Required env-var validation on startup** (today: only Supabase vars are required; engine starts without any LLM key and silently fails on first task) · `config.py:108-112` · 1 h
11. **Health endpoint** that pings Supabase + at least one LLM · `main.py` · 1 h
12. **Dockerfile hardening**: non-root user, `HEALTHCHECK`, multi-stage, signal forwarding · 2 h

### Website

13. **Engine `/api/admin/*` rate limiting on read/delete** (export entire waitlist with no throttle today) · `src/app/api/admin/*` · 1 h
14. **Realtime broadcast ACL** — today the `"anticipy-intents"` channel is public, broadcasts have no per-user filter · `src/app/api/engine/analyze/route.ts:174-189` · 2 h
15. **CSP + security-header middleware** (`middleware.ts` does not exist today) · 2 h
16. **Outdated Next.js + supabase-js** — Next 14.2.35 → 16.x, supabase-js 2.100 → 2.105, react 18 → 19 — known CVEs · 2 h
17. **WebSocket reconnect on `/engine` page** — today, a transient disconnect kills the active recording with no recovery · `src/app/engine/page.tsx` · 2 h
18. **Admin IDOR audit** — `verifyAdmin()` checks "is row in `anticipy_admin_users`" but the DELETE handler doesn't verify the deleted row's ownership · `src/app/api/admin/waitlist/route.ts` · 1 h

## 5. Strategic recommendations — model & cost strategy

### 5.1 Replace single-default routing with intent-based cascade

Today: every LLM call goes Gemini 2.5 Flash → Groq Llama 3.3 70B → DeepSeek (no credits), regardless of whether it's a `"hi"` greeting or a 10-step booking. That over-pays for trivial calls and under-paies for hard ones.

Recommended routing matrix (reasoning behind it in Appendix C):

| Task | Model | $/1M in | $/1M out | Why |
|---|---|---|---|---|
| Greeting / chitchat | Llama 4 Scout (Groq free tier) | $0.11 | $0.34 | ~free at 1k req/day |
| Intent classification | Llama 4 Scout (Groq) | $0.11 | $0.34 | cached prompt; classifier is deterministic-ish |
| Goal decomposition (planning) | Claude Haiku 4.5 | $1 | $5 | computer-use trained; tool use beats Scout |
| Action loop, simple sites | Claude Haiku 4.5 (with prompt caching) | $1 / $0.10 cached | $5 | 50.7% OSWorld; cheapest with vision |
| Action loop, complex sites (banking, travel, multi-tab) | Claude Sonnet 4.6 (with prompt caching) | $3 / $0.30 cached | $15 | 72.5% OSWorld; computer-use SOTA |
| Recovery / "stuck >3 steps" | Sonnet 4.6 with extended thinking | $3 + thinking | $15 | one-shot rescue is cheap insurance |
| Dense screenshot/PDF reading | Opus 4.7 (only when Sonnet fails) | $15 | $75 | 3.75 MP image ceiling; rare path |

Drop DeepSeek from the action loop. It has no native vision and will fail any browser task that requires reading a screenshot.

### 5.2 Adopt Anthropic prompt caching everywhere

This is the single biggest cost lever. Browser-agent prompts are >90% static (system prompt + tool schemas + history) and <10% delta per step. With caching, the static portion costs 0.1× base on hits. Real numbers for a 14-step "book a flight" task:

| Strategy | $/task |
|---|---|
| 100% Sonnet 4.6 uncached | $0.342 |
| 100% Sonnet 4.6 + 90% cache hit | **$0.041** |
| 100% Haiku 4.5 + caching | **$0.038** |
| Routed (Scout/Haiku/Sonnet) + caching | **$0.018-0.025** |

Targets: **<$0.02/task average, <$0.08/task p95** (the existing per-task hard cap).

### 5.3 Track cost in real time and surface it

Today `MAX_COST_USD = 0.08` is checked at task start (`tracker.exceeded`) but not during. Per-step check + a "we're approaching the budget — should I push on?" UX confirmation is honest, builds trust, and matches the safety architecture's existing confirmation pattern.

### 5.4 Drop `langchain-google-genai` / `langchain-groq` for direct SDKs

These add a layer that rate-limits which provider features (extended thinking, prompt caching, structured outputs) you can opt into. Both are simple HTTP APIs; an in-house wrapper of ~200 LOC is cleaner. Also closes the litellm transitive-dependency risk for good.

## 6. Strategic recommendations — anti-bot, stealth, CAPTCHA

### 6.1 Browser engine: route per-domain instead of one-size-fits-all

Today: Patchright + Browser Use, full stop. Patchright clears ~70% of the consumer web but is detectably-flagged on Cloudflare Turnstile enterprise tier, DataDome v4, Akamai, Kasada.

Recommended layered router:

1. **Patchright** for default consumer sites (Amazon, Wikipedia, OpenTable, etc.).
2. **Camoufox** (Firefox-based, 0% headless detection on standard suites) for sites where Patchright fails first time. Trade-offs: ~42 s to clear Turnstile, 200 MB RAM/instance.
3. **nodriver** (CDP-direct, async) for sites where Camoufox struggles. Beats Patchright on Cloudflare; still fails enterprise DataDome without proxy.
4. **Paid bypass API** (Scrapfly / Hyper SDK at ~$3/1k req) only as last resort for Akamai / Kasada banking sites.

The router is a per-domain decision tree built up empirically over the first 2-4 weeks of real traffic.

### 6.2 Network: mobile-residential proxies, with `curl_cffi` for HTTP probes

Datacenter IPs lose to DataDome's 35-signal ML scoring on banking and airline sites. Mobile-residential (Bright Data Mobile or IPRoyal) is the floor at ~$15-20/GB. Use them only on second-attempt bounce-back; default traffic stays on cheap residential/datacenter.

Naked Python `requests` / `httpx` is a tell on JA4+ TLS fingerprinting (now standard at Cloudflare, AWS, VirusTotal). For pre-flight HTTP probes (cookie warming, robots.txt fetch, JSON API hits) before launching a browser, use `curl_cffi`.

### 6.3 CAPTCHA: cascade NopeCHA → CapSolver → 2Captcha → Whisper

NopeCHA is free 100/day at ~88% on reCAPTCHA v2 but weak on v3 and dead on Turnstile. CapSolver is the best $/accuracy at ~$0.80/1k v2 and ~$1.20/1k Turnstile, ~10 s. 2Captcha (human-backed) is the AI-resistant fallback at slightly higher cost. Audio reCAPTCHA can be solved free with `faster-whisper` on the existing CPU at ~95% accuracy on US-EN.

### 6.4 Watchdog process, not in-process asyncio task

Browser Use's in-process watchdogs deadlock under load (their own GH #2808). Run a separate Python process (or container sidecar) that:
- monitors the agent process's heartbeat over Unix socket
- can `SIGKILL` and respawn the browser
- counts leaked Chromium PIDs and emits a metric

This is what every production browser-agent SaaS does. Cost: ~150 LOC.

## 7. Strategic recommendations — proactive engine

The engine today is reactive: user types/says a task, agent executes. The product's vision (Donna from Suits, "vibe your life") requires proactive: agent overhears intent, decides whether to act, surfaces or executes. This is the hardest part of the product. Most existing wearables that tried it (Humane, Friend, Rabbit's first LAM) failed loudly. The ones that succeeded (Plaud, Bee, Limitless) deliberately stayed reactive.

The CHI 2025 research on proactive AI is unambiguous: persistent suggestions are universally rated annoying; people prefer non-proactive chat *unless* the proactivity feels like *completion of an action they already started* (autocomplete is the most successful proactive AI in history). Translate to Anticipy:

### 7.1 Three confidence buckets

For every detected intent, score trajectory-success probability (not final-answer confidence) and route by bucket:

- **>0.85** → execute; tell user after the fact ("Done. Booked Quattro for 7 pm. Want to see the confirmation?").
- **0.5-0.85** → ask one yes/no question via the phone ("Book Quattro for Friday at 7?"). One question, not a dialogue.
- **<0.5** → silent log to the "Things I noticed" feed. User can look, ignore, or trigger later.

Confirmation is *always* required for irreversible actions regardless of bucket: sending email, spending money, contacting people, deleting things. This is the existing `safety.check_needs_confirmation()` pattern; it stays.

### 7.2 Diarization gate

Only the user's own diarized voice cluster ever drives action. Bystander speech is dropped at the VAD/Sortformer stage on-device. This isn't a feature toggle — it's the architectural guarantee that keeps Anticipy alive in two-party-consent states (12 of them in 2026; CA SB 1130 raises stakes to $10K/year jail). It's also the most defensible privacy claim, the one Meta cannot credibly copy because Meta's incentive is to harvest, not protect.

Sub-feature, opt-in: "act on what others tell me to do" toggle, default OFF, surfaced as a setting. When ON, the agent treats requests from non-user voices the same as user requests, but gates them through the same confidence buckets.

### 7.3 The "Things I noticed" feed

Surface the agent's silence. A scrollable feed, updated throughout the day:

> **2:14 pm** — You said you should call your mom back. I'll surface a reminder at 6 pm.
> **3:02 pm** — Your dentist's office mentioned a Tuesday opening. Want me to grab it?
> **3:48 pm** — You complained about the Spotify auto-renewal. I can cancel it now or tomorrow.

Each item: one-tap "yes do it" / "no ignore" / "remind me later." Ignored items train the implicit-trigger threshold. This is the antidote to silent-FN ("the agent missed something") and the only honest way to make a 30-second proactive trigger feel proactive but not Clippy.

### 7.4 Donna persona, not Siri persona

Encode an actual personality: concise, dry, slightly impatient, opinionated, willing to refuse. "No, you're tired and you'll regret sending it" is a Donna move; "Sure, I can help with that" is Siri and is dead on arrival. This is a product/copywriting decision (§11.Q5) that lives in `engine/app/messages.py`, but the engineering hooks are: (a) a single, consistent voice template across all user-facing strings; (b) a `refusal_reasons` enum with human copy that explains *why* the agent declined; (c) a "second opinion" branch in the planner where the agent can choose to push back instead of decompose.

### 7.5 Trust slope, not trust score

Each correct micro-action raises the agent's autonomy bar. Each user-corrected mistake drops it. Surface this as a slow-moving "autonomy level" the user can see, not a black-box score. Users who feel in control let the agent do more.

## 8. Strategic recommendations — testing

Three layers, no shortcuts:

### 8.1 Unit tests with mocked LLM (currently zero)

Test the deterministic logic: `safety.check_blocked()`, `router._pre_classify()`, cost-tracker arithmetic, JWT issue/verify, encrypted-cookie round-trip, planner URL extraction. Target: **>90% line coverage on `safety.py`, `auth.py`, `router.py`, `planner.py`** by week 2. These are the modules where a regression silently kills production safety.

### 8.2 Eval harness (currently zero)

50-100 golden tasks with expected outputs, scored by an LLM-as-judge calibrated against human raters on a 20-task subset. Run on every model swap. Goals: catch regressions when we promote a model from Haiku to Sonnet; catch regressions when Browser Use upgrades. Adopt the **Online-Mind2Web 300-task harness** as the public benchmark — it's what Browser Use Cloud (97%), Surfer 2 (97.1%), and Magnitude (93.9%) all report on, and what Anticipy will be benchmarked against publicly. Skip WebVoyager — saturated.

Add a small **WebGames** subset for spatial grounding (humans 96%, GPT-4o 41%) — that's where Sonnet 4.6's vision premium pays off and where competitors will lose first.

### 8.3 Real-site integration tests (current `test_real.py`)

Already exists, target 9/10. Expand to **20 tasks across 6 categories** (booking, cancellation, dispute, scheduling, fact-finding, login-walled-content) and run nightly. Add **failure-mode injection tests**: kill the LLM provider mid-step, kill the browser process mid-step, swap the proxy mid-step, inject a CAPTCHA mid-step. The current 9-test suite covers happy paths only.

### 8.4 Observability that closes the testing loop

Per-task: success rate, steps, wall-clock, $-cost, model used, browser engine used, CAPTCHA encountered, retries. Weekly dashboard. Without this, evals are theater — you can't tell whether last week's "fixes" helped or hurt.

## 9. Hardware transferability — 6-phase roadmap

The engine is server-resident today (Python on Linux with Xvfb). The wearable + phone product needs a phone-side companion that streams *intents* (not raw audio) to the engine. That's a roughly six-phase journey, with the first two doable in parallel with §3-§8 hardening.

**Phase 0 — Engine hardening (now → 6 weeks).** §3 P0s + §4 P1s + §5/6/8 strategic upgrades. Engine becomes multi-tenant-safe, observably reliable, $0.02/task. Milestone: 9.5/10 on `test_real.py`-equivalent expanded suite; 1k tasks in dogfood without a leaked browser process.

**Phase 1 — Phone companion (text-input first; 6-14 weeks).** Native iOS + Android (or Flutter) app. Auth to engine over WebSocket. UI shows "Things I noticed" feed, current-task streaming, confirmation prompts, cost ledger. *No mic yet.* The point is to validate the engine's mobile-orchestrator surface before adding audio. Milestone: 50 alpha users, 20 actions/user/week, <5% false-positive rate on confirmations.

**Phase 2 — On-device audio (14-22 weeks).** Phone's mic only — no pendant yet. Pipeline: Silero VAD → Sortformer diarization (CoreML) → Whisper Turbo or Parakeet V3 transcription → ~1B-parameter intent classifier on NPU → intent payload to engine. Milestone: ≤30 s p95 from end-of-utterance to "Things I noticed" feed entry; ≤5 s p95 for explicit commands; user-voice diarization recall ≥0.9 in noisy environments.

**Phase 3 — Pendant v1 (22-34 weeks; ~6 months hardware).** BLE-only audio capture. Mic + visible LED + mechanical mute switch + USB-C + 12-24 h battery. Talks only to companion app. ODM partner in Shenzhen unless capex permits in-house. The marketed 8 g brushed-titanium spec is a stretch but achievable with nRF5340 + small LiPo. Milestone: 1k units, ≥4.5/5 reliability, BLE audio loss <1% over a 2-h continuous session.

**Phase 4 — Proactive layer (parallel, 24-40 weeks).** Confidence buckets, "Things I noticed" feed, refusal logic, persona fine-tuning, multi-turn intent buildup. This is where Anticipy stops being "Siri who books restaurants" and starts being Donna. Milestone: ≥30% of accepted actions are proactive offers (not user-initiated commands); <10% dismissal rate.

**Phase 5 — Memory & taste, phone-free mode (40-60 weeks).** Per-user semantic memory store, taste learning (favored brands, contacts, routines), conversation-level retrieval. Pendant gets enough on-board NPU (next-gen nRF or Ambiq) to run quantized Parakeet + small intent classifier locally and queue intents while the phone is unreachable. Milestone: ≥50% of actions reference user-specific memory; 8 h offline-pendant operation; intent queue is end-to-end encrypted with per-device keys.

Crucially: **the browser agent itself stays server-resident through all six phases.** iOS WebKit (App Store rule) and Android Chromium, even in Appium/WebView wrappers, do not have anything close to Browser Use's maturity. Comet, Manus Browser Operator, OpenAI Operator all keep the brain on a server and stream UI to phones. Don't try to put Playwright on a phone.

## 10. Cost economics

Per-user-per-month assuming a typical user:

| Component | Cost path | $/user/mo |
|---|---|---|
| Streaming transcription | On-device (Silero + Sortformer + Parakeet) | **~$0** marginal |
| Cloud transcription fallback (rare) | AssemblyAI Universal-2, ~10% of audio | $1-3 |
| LLM intent classification on-device | ~1B-param model on NPU | ~$0 marginal (battery cost only) |
| LLM context-building / overnight summarization | Gemini Flash batched | $3-8 |
| Browser agent (engine) | Routed cascade with caching, 10-30 actions/user/mo | $0.50-6 |
| Embedding storage / retrieval | Postgres pgvector or similar | $0.20 |
| **Total cost** | | **~$5-17/user/mo** |

Pricing target to match value perception and unit economics:

- **$199-299** hardware (one-time)
- **$25-40/mo** subscription, with first 100 actions/mo included

Friend.com charged $129 one-time with no subscription and is bleeding inference cost without revenue — that's the failed model. Limitless was $99/mo + $99 device and the math worked but they sold to Meta because subscription wearables don't have a venture-scale exit absent acquisition. Anticipy's pricing should be subscription-driven from day 1; the device is the hook, the subscription is the business.

## 11. Open questions for the founder

These five product decisions block a meaningful share of the implementation. Each has a default recommendation; treat the recommendation as the path I'll take if you don't push back.

### Q1 — V1 audio architecture: cloud-stream or on-device-only?

The marketing says "audio never leaves the phone." The current prototype streams to `anticipy.ai`. Pick one for v1:
- **(a) On-device only (recommended).** Privacy is the wedge against Meta. Limitless died because of GDPR; Anticipy doesn't need to repeat that. Eats more battery (~25-35%/day on phone), requires NPU-grade phone, makes the engine API simpler (no audio ingestion at all).
- **(b) Cloud-stream.** Cheaper to ship hardware sooner, easier transcription quality, but kills the privacy claim and exposes you to GDPR and CA SB 1130.

Default: **(a)**. Tell me if you want (b).

### Q2 — V1 site coverage: arbitrary websites or a curated allowlist?

The vision sells "we handle whatever needs handling." The reality of Browser Use + Patchright is ~70% reliability on the consumer web, lower on banking/airline. Pick:
- **(a) Curated allowlist of ~50 high-frequency cancellation/booking/dispute sites at launch (recommended).** Reliable, marketing-defensible, lets us do per-site stealth tuning. Expand the list weekly.
- **(b) Open web from day 1.** More magical, more failures, more edge cases that erode trust.

Default: **(a)**. The Friend/Bee/Plaud comparison pages on your site are about *acting*; the "anywhere on the web" promise can be in the marketing without being literally true on day 1.

### Q3 — Confirmation policy: when does the agent ask before acting?

Your `safety.py` already has an `ALWAYS_CONFIRM` pattern list. We need to formalize the rule. Options:
- **(a) Action-category based (recommended)**: send/contact/spend/delete/subscribe always confirms; fact-finding never confirms; everything else uses the confidence-bucket rule (§7.1).
- **(b) Dollar threshold**: anything over $X confirms. Requires us to extract and parse dollar amounts reliably; fragile.
- **(c) Confidence-only**: trust the agent's self-reported confidence to gate. Calibration is hard and we'll over- or under-confirm for months.

Default: **(a)**, with (c)'s confidence buckets layered on top for non-irreversible actions.

### Q4 — Identity & credentials: where do user logins live?

Today the engine stores per-user encrypted cookies in Supabase. For the wearable product, options:
- **(a) Stay with Supabase-encrypted cookies (recommended for v1).** What we have. Per-user Fernet key derivation (§4.4) closes the obvious risk.
- **(b) Phone-side credential proxy.** User's saved logins stay on phone; phone proxies HTTPS traffic for the engine. Better privacy story, much harder engineering, breaks the "engine works headlessly while user is asleep" model.
- **(c) Eventually on-device on the pendant.** Years away.

Default: **(a)** for v1, **(b)** as a Phase 5 option once Phase 4 is shipped.

### Q5 — Donna persona: voice or silent?

Should the engine surface itself with a voice/personality (confirmations, acknowledgments, "things I noticed" copy), or be silent infrastructure with the phone OS doing all the talking?
- **(a) Voice with personality (recommended).** Differentiates against Siri/Alexa, lives up to the Donna positioning. Requires writing — hire a copywriter, not just an ML engineer. All copy lives in `engine/app/messages.py`.
- **(b) Silent infrastructure.** Faster to ship, blander to use, harder to differentiate.

Default: **(a)**. Friend was vandalized partly because its persona was syrupy and weak. A confident, dry, opinionated voice is the opposite of that and is uncopyable IP.

## 12. Proposed next 4 weeks

A concrete sprint plan for *engine* work. Website fixes (P0-W1..W5, P1-W3..W4) are tracked in parallel and scoped at ~2 days total — they should be done before any new engine code ships, because they're the cheapest reputational gunshot wound to plug.

### Week 1 — Stop the bleeding (P0s)

- Day 1-2: P0-E1 (JWT default), P0-E2 (Fernet key persistence), P0-E3 (auto-confirm), P0-W1 (`"123"` passcode). All <2 h each. Plus Supabase RLS audit (§3.W2 and P1-9).
- Day 3: P0-E4 (browser cleanup) + P0-E5 (LLM degraded mode). Add structured logging skeleton with request-IDs while you're in there.
- Day 4-5: P0-W2/W3/W4/W5 (engine API auth, deepgram token grants, HTML escape, intent ownership check).

End of week 1: no public-internet attack vector; no silent-failure on provider outage; engine restarts don't wipe cookies.

### Week 2 — Cost & model strategy (§5)

- Day 1-2: replace `langchain-google-genai` / `langchain-groq` with direct SDK wrappers; add Anthropic SDK. Wire prompt caching on the static system-prompt portion of every agent step.
- Day 3-4: implement intent-routing matrix (§5.1). Deterministic rules in `models.py`; per-call selection in `agent.py`, `router.py`, `planner.py`.
- Day 5: cost dashboard (per-user, per-day, per-model). Plug it into the `/stats` endpoint and the admin panel.

End of week 2: average-task cost is in the $0.018-0.025 range; we can see it.

### Week 3 — Reliability (§4 + §6.4 watchdog)

- Day 1: WebSocket lifecycle (cancel-on-disconnect, heartbeat, idle timeout).
- Day 2: concurrency cap with per-user semaphore; queue UX feedback.
- Day 3-4: separate watchdog process; PID monitor; `pkill` fallback.
- Day 5: per-user Fernet key derivation; rotate the existing master key and back-fill.

End of week 3: 50 concurrent simulated users for an hour without a leaked browser process or a hung WebSocket.

### Week 4 — Tests, observability, deploy hardening

- Day 1-2: unit tests for `safety.py`, `auth.py`, `router.py`, `planner.py`. >90% coverage.
- Day 3: Online-Mind2Web 50-task subset wired into nightly CI. Eval harness with LLM-as-judge.
- Day 4: failure-mode injection tests (kill LLM, kill browser, swap proxy, inject CAPTCHA).
- Day 5: Dockerfile hardening, health endpoint, signal forwarding, non-root user. CI/CD that deploys on green.

End of week 4: the engine is investor-grade. Hand to a new senior engineer Monday, they ship a fix on Tuesday, no incidents on Wednesday.

This sequencing intentionally puts security/reliability before features. The proactive engine (§7), Camoufox/nodriver routing (§6.1), mobile-residential proxies (§6.2) are weeks 5-8. Hardware transferability (§9 phases 1+) is weeks 9-16.

---

## Appendix A — Full engine audit

(Compiled from a structural audit performed 2026-04-30. File:line references are against the current main branch, commit `e564477`.)

### A.1 Architecture

A1.1 — Boundary between Browser Use, the engine wrapper, and the API layer is clean and stateless. `agent.py:213-572` has no WebSocket awareness; `main.py:432-579` has no browser-internals awareness; `safety.py` is independent. *Strength.*

A1.2 — Agent state is fully ephemeral. If the process dies mid-task, no recovery. No heartbeat, no state serialization, no circuit breaker. *P1.*

A1.3 — No God objects, no hardcoded website logic. Generic URL extraction (`planner.py`), LLM-driven planning, no site-specific selectors. Browser Use does the DOM extraction. *Strength.*

### A.2 Reliability

A2.1 — Browser process cleanup is `try/finally`, but on `WebSocketDisconnect` (`main.py:572`) the background `run_task()` is not cancelled and the browser keeps running. *P0-E4.*

A2.2 — `session.stop()` has no timeout. If it hangs, the process leaks. *P0-E4.*

A2.3 — No subprocess-level fallback (`pkill -f patchright` or PID tracking). *P0-E4.*

A2.4 — `/tmp/engine_profiles` grows unbounded. *P2.*

A2.5 — Timeout on agent.run is `MAX_SECONDS + 30 = 330 s`. Confirmation wait is 120 s. CAPTCHA solving polls 24 × 5 s = 120 s with no outer cap (`captcha.py:181,240`); a stuck CAPTCHA can block the entire agent loop. *P1.*

A2.6 — DISPLAY env var: if `start.sh` is forgotten, Xvfb never starts and the browser silently fails or hangs. *P1.*

A2.7 — Network errors are caught generically. No exponential backoff on Supabase retries. No circuit breaker. *P2.*

A2.8 — When all LLM providers fail: `models.py:283-332` returns None, `router.py:80-93` defaults to `"ambiguous"`, `planner.py` falls through to Google search. User sees a confusing partial response with no error. *P0-E5.*

### A.3 Safety

A3.1 — `safety.py` is deterministic and not bypassable by the LLM. `check_blocked()` runs *before* sending to the agent (`main.py:509-511`). Word-boundary regex; normalization handles case + spacing. *Strength.*

A3.2 — `ALWAYS_BLOCKED`: delete account, wire transfer, factory reset, unsubscribe all, delete all, remove all data, export all passwords. Coverage is good for irreversible destructive actions.

A3.3 — `ALWAYS_CONFIRM`: purchase, buy, order, checkout, pay, send email, send message, book, subscribe. Coverage is reasonable; needs a periodic sweep of new attack categories.

A3.4 — `/execute-intent` REST endpoint auto-confirms (line 333-334). *P0-E3.* This means the WebSocket-side confirmation flow is the only real human-in-the-loop, but the website also calls `/execute-intent` from `/api/engine/confirm` (which is itself unauthenticated — see B.3). End-to-end, an attacker can hit `/api/engine/confirm` → `/execute-intent` → real action with zero auth and zero human approval.

A3.5 — Page content sent to Browser Use is not sanitized. Theoretically prompt-injectable; in practice mitigated by Browser Use's prompt design. *P3.*

### A.4 Cost

A4.1 — Static priority order Gemini → Groq → DeepSeek (`config.py:60-105`). No adaptive selection. Trivial classifications pay full Gemini Flash rate. *P2 — see §5.*

A4.2 — Per-task cost ceiling enforced at start (`tracker.exceeded`). Not checked during execution. No user feedback when hit. *P2.*

A4.3 — Daily caps (`MAX_TASKS_PER_DAY=100`, `MAX_COST_PER_DAY_USD=0.50`) are present (`config.py:48-50`). Good.

### A.5 Auth & security

A5.1 — bcrypt 12 rounds. Industry standard. *Strength.*

A5.2 — `JWT_SECRET` defaults to `"anticipy-engine-secret-change-me"` (config.py:28). *P0-E1.*

A5.3 — `JWT_EXPIRY_HOURS = 72` (config.py:30). 72 h is too long for an action engine that can spend money. *P1.*

A5.4 — Login rate limit (`auth.py:22-49`) is in-memory dict; lost on restart; no distributed-attack mitigation. *P1.*

A5.5 — Password minimum 6 chars (`main.py:207-208`). *P1.*

A5.6 — `PROFILE_ENCRYPTION_KEY` regenerates on every restart if env var missing (config.py:44-46). *P0-E2.*

A5.7 — Single master Fernet key for all users' cookies. Compromise of the key compromises every user. *P1 — per-user key derivation.*

A5.8 — Cookies named `password|passwd|secret|credit|card` are stripped before storage (`agent.py:168-176`); `session|auth|token` are kept. Acceptable for an action engine that needs session continuity, but should be reviewed.

A5.9 — Cookie isolation depends on Supabase RLS being correctly configured on `browser_profiles`. Not currently audited from code. *P1 (must-audit).*

A5.10 — REST API filtering uses `eq.{value}` query params (`supabase_client.py:43-62`); Supabase parses safely. SQL injection risk low. *Strength.*

### A.6 Observability

A6.1 — Plain Python logging to stdout. No structured logs, no JSON, no request-ID propagation, no Sentry. *P1.*

A6.2 — `engine_tasks` row stores `status`, `result`, `metadata` (intent_id, plan, message count). No per-step action log, no cost, no duration, no exception trace. When a task fails, you can't debug it. *P1.*

A6.3 — Metrics: `_total_tasks` and `_total_errors` global counters via `/stats` (main.py:76-79). No latency histograms, no per-site success rate, no cost per user, no browser crash rate. *P2.*

A6.4 — Errors swallowed into generic "Connection error" message (main.py:555-557). User and ops both lose context. *P1.*

### A.7 Concurrency

A7.1 — `MAX_BROWSER_TASKS = 50` (config.py:58, restart hint) but no actual concurrency cap on the running set. With 1 Uvicorn worker, ~50 concurrent browsers OOM the server. *P1.*

A7.2 — Browser Use agent is not reentrant; each task creates a fresh BrowserSession. Pays 3-5 s launch cost per task. Acceptable for MVP; pool for scale. *P2.*

A7.3 — WebSocket: no heartbeat, no idle timeout, no cancel-task-on-disconnect. *P1.*

### A.8 Testing

A8.1 — `test_real.py` (470 LOC): 9 real-site browser tests + 3 classifier tests + technical-leakage audit. Target 9/10. *Strength as a smoke test, weakness as a full harness.*

A8.2 — Zero unit tests, zero mocks, zero failure-mode tests, zero load tests. *P2 — see §8.*

A8.3 — Tests use real `.env.local` API keys; cannot run in untrusted CI without provisioning. *P2.*

### A.9 Streaming UX

A9.1 — Status messages throttled to every 2 s (`agent.py:248-250`). Acceptable for MVP; users may feel the gap on slow links.

A9.2 — Sanitization of agent output strips technical terms before sending to user (`agent.py:481-551`). *Strength* — matches Omar's "no technical leakage" preference.

### A.10 Profile / cookies

A10.1 — Encrypted at rest with Fernet. Decrypted into BrowserSession on task start. *Strength.*

A10.2 — Single master key (A5.7). *P1.*

A10.3 — Sensitive cookie name filter is allow-list-style with a short denylist (A5.8). Worth periodic review.

### A.11 Browser stealth

A11.1 — Patchright args: disable automation, no sandbox, software WebGL, no first-run, headless=False, custom UA, NopeCHA disabled if installed, 0.5 s wait between actions. *Adequate for low-tier sites.*

A11.2 — No proxy rotation, no fingerprint randomization, no timezone spoofing, no WebRTC leak prevention. *P2 — see §6.*

A11.3 — `browser.py` (legacy, 557 LOC) has more stealth logic that's not used in the current path. Either delete or integrate. *P3.*

### A.12 Planner / router

A12.1 — Pre-classifier is keyword-based (`router.py:41-94`) with LLM fallback. Deterministic; no hallucination. *Strength.*

A12.2 — Planner extracts URLs by regex; merges explicit-user URL with LLM-suggested URL preferring explicit if domains differ (`planner.py:59-67`). Reasonable; doesn't validate URL reachability. *P3.*

### A.13 Hardware transferability

A13.1 — API surface is text-only (WebSocket + REST). No audio ingestion. Adding it would be additive (new endpoints) rather than disruptive. *Strength.*

A13.2 — `CostTracker` is LLM-agnostic; can extend to transcription cost.

A13.3 — `classify()` reusable for intent detection from continuous audio.

A13.4 — `execute_task()` is goal-string-agnostic.

A13.5 — Auth is REST-tied today; would need to bind to a phone-companion session. *2-3 weeks of engineering for full audio path; see §9.*

### A.14 Dead code

A14.1 — `browser.py` (557 LOC) — delete or integrate. *P3.*

A14.2 — `harness.py` (308 LOC) — delete. Browser Use does this. *P3.*

A14.3 — `vision.py` (`describe_screenshot()` always returns None) — delete or integrate. *P3.*

### A.15 Configuration

A15.1 — `REQUIRED_ENV_VARS` only enforces Supabase URL/anon key (config.py:108-112). Engine starts without any LLM key and silently fails. *P1.*

A15.2 — No env-var validation (e.g., `MAX_STEPS` must be positive int).

A15.3 — JWT secret default is unsafe (A5.2). *P0-E1.*

A15.4 — Encryption key default regenerates (A5.6). *P0-E2.*

### A.16 Deployment

A16.1 — `Dockerfile` is minimal: Playwright Python base, Xvfb, requirements, browser binaries, `start.sh`. No `HEALTHCHECK`, no resource limits, runs as root, no SIGTERM trap, no multi-stage build. *P1.*

A16.2 — `start.sh`: Xvfb + uvicorn. No process supervision. If uvicorn crashes, the container keeps running. *P1.*

A16.3 — No infra-as-code, no docker-compose, no Kubernetes manifests, no CI/CD. *P2.*

### A.17 Honest verdict

This is **~92% prototype, ~8% production**.

Strengths: clean architecture, deterministic safety layer that the LLM cannot override, encrypted multi-user cookie store, generic browser agent (no hardcoded site logic), real-world test suite that exercises Cloudflare and reCAPTCHA, sanitization layer that prevents technical leakage to users.

Production gaps: no error recovery, no observability, no concurrency control, no deployment hardening, five P0 security/reliability holes that are each <2 h to close. Two-to-three weeks of focused work closes the gap.

**Blast radius for a new senior engineer:** within the first three days they'd most likely hit (1) the Fernet-key reset wiping every user's cookies on their first deploy, (2) the JWT default in a staging environment that gets crawled by a bot, (3) a runaway browser process pool from disconnected WebSockets in load testing. None of these are subtle; all are checked-into-Git defaults.

## Appendix B — Full website audit

(Compiled 2026-04-30. Scope: engine-touching surface only.)

### B.1 Engine integration

B1.1 — `/engine` page uses Supabase Auth; on success calls `/api/extension/access-code` to get the user's unique access code. *Adequate.*
B1.2 — `/api/extension/access-code/route.ts` returns the access code without rate limit. *P1.*
B1.3 — `/api/extension/auth/route.ts` validates the access code and returns LLM API keys (Groq, Gemini) to the client. *P1 — should not return raw provider keys; should return a server-mediated session token instead.*
B1.4 — Deepgram WebSocket: client opens `wss://api.deepgram.com` directly, passing the API key as subprotocol token, pulled from `/api/engine/deepgram-key`. *P0-W4.*

### B.2 Auth

B2.1 — Engine users sign up via Supabase Auth; one access code per user. No invite flow. Sitemap exposes `/engine`. *P2 — discoverability.*
B2.2 — Admins verified by Supabase auth + `anticipy_admin_users` table lookup. Single hardcoded admin email in the Footer (`omar@anticipy.ai`). *P1 — RBAC if you ever onboard a second admin.*
B2.3 — Tokens stored in React state, not localStorage. *Strength.*

### B.3 Engine API surface (the worst part of the codebase)

B3.1 — `/api/engine/session`: no auth on POST/PATCH. Anyone can create or modify sessions. *P0-W2.*
B3.2 — `/api/engine/analyze`: no auth. Accepts arbitrary transcripts. Broadcasts to public Realtime channel `"anticipy-intents"`. Sends notifications to hardcoded `TEST_USER_EMAIL` / `TEST_USER_PHONE` env vars. *P0-W2.*
B3.3 — `/api/engine/confirm` GET: no auth. `intentId` + `action=yes` executes. *P0-W3.*
B3.4 — `/api/engine/transcribe`: no auth. Stores audio + transcript. *P1.*
B3.5 — `/api/engine/deepgram-key`: returns master Deepgram key to the client. *P0-W4.*
B3.6 — `/api/engine/confirm` GET: HTML response interpolates `result.data?.task` without escape. *P0-W5.*

### B.4 Database

B4.1 — Public client uses anon key (expected). Admin client uses service role (expected for server-side).
B4.2 — RLS not visible in code; depends on Supabase policy configuration. *P1 (must-audit).*
B4.3 — Realtime broadcasts use service role key; no per-subscriber filter; channel is public. *P1.*

### B.5 Deployment / dependencies

B5.1 — No `middleware.ts`, no CSP, no security headers. *P2.*
B5.2 — Next 14.2.35 (16.x available), supabase-js 2.100 (2.105 available), React 18 (19 available). Multiple known CVEs. *P2.*
B5.3 — No `vercel.json`. Build config minimal.

### B.6 UX

B6.1 — `/engine` shows audio level, live transcript, speaker diarization. *Strength.*
B6.2 — WebSocket error path logs to console only; no UI feedback; no reconnect. User submits empty transcript on a dead socket. *P2.*

### B.7 Discovery

B7.1 — Footer link to `/engine` with `opacity-50` (low-discoverability, reasonable for a private alpha). *Acceptable.*
B7.2 — Sitemap includes `/engine` at priority 0.6. *P2.*
B7.3 — `/demo` and `/internal` use the literal passcode `"123"` checked into git (`src/app/demo/page.tsx:5`, `src/app/internal/layout.tsx:25`). *P0-W1.*

### B.8 Admin

B8.1 — Waitlist dashboard protected by `verifyAdmin()`. Export CSV, delete, search.
B8.2 — DELETE handler doesn't verify ownership of the row being deleted. If `verifyAdmin()` is bypassed (it currently relies on existence in `anticipy_admin_users`), any authenticated user can delete arbitrary waitlist entries. *P0-W with admin escalation chain.*

### B.9 Honest verdict

The marketing site is fine. The engine API surface is the worst code in the project — an attacker reading this audit can sketch an exploit chain in 15 minutes. None of the fixes are hard; they're all "add an auth check + an ownership check + a rate limit." Two days of focused engineering closes B.3 entirely.

LOC by major dir:
- `src/components/` — 1,564
- `src/app/api/` — 1,376 (16 routes)
- `src/lib/` — 1,339
- `src/app/*` (pages) — ~16,187
- **Total** — ~20,500

## Appendix C — Model routing matrix (April 2026)

| Model | $/1M in | $/1M out | Vision | Tool use | OSWorld | BU bench | Free tier | Notes |
|---|---|---|---|---|---|---|---|---|
| Claude Opus 4.7 | 15 | 75 | Excellent | Excellent | 78.0% | n/a | No | 3.75 MP image ceiling; recovery only |
| Claude Sonnet 4.6 | 3 | 15 | Excellent | Excellent | 72.5% | 59% | No | Computer-use SOTA, primary action model |
| Claude Haiku 4.5 | 1 | 5 | Good | Strong | 50.7% | n/a | No | Cheapest with computer-use training |
| GPT-5.5 | ~2 | ~15 | Excellent | Excellent | 78.7% | n/a | No | OSWorld leader; no caching parity |
| Gemini 3.1 Pro | 1.25 | 10 | Excellent | Strong | n/a | 59.3% | Limited | Strong but Anthropic caching is better |
| Gemini 3 Flash (preview) | 0.50 | 3 | Good | Good | n/a | n/a | Yes | Good chitchat fallback |
| Gemini 2.5 Flash (current) | 0.30 | 2.50 | Good | OK | mid | mid | Yes | Current default; keep as fallback |
| Llama 4 Scout (Groq) | 0.11 | 0.34 | Limited | OK | weak | weak | Yes (1k/day) | Free at low volume; chitchat only |
| Llama 4 Maverick (Groq) | 0.50 | 0.77 | Better | Decent | n/a | n/a | Yes (500/day) | Optional middle tier |
| DeepSeek V3.2 | 0.28 | 0.42 | None | Good | n/a | n/a | Limited | Drop from action loop (no vision) |
| DeepSeek R1 | 0.70 | 2.50 | None | Strong reasoning | n/a | n/a | Yes | Reasoning-only fallback |
| Qwen3-VL-72B | OSS | OSS | Strong | Native GUI | rivals Opus 4.6 | n/a | Self-host | Hold for self-hosted future |

**Recommended Anticipy chain (intent-routed, with prompt caching everywhere on Anthropic):**

```
greeting / chitchat        → Llama 4 Scout (Groq, free)
classification            → Llama 4 Scout (cached prompt)
planning / decomposition  → Claude Haiku 4.5 (cached)
action loop, simple       → Claude Haiku 4.5 (cached)
action loop, complex      → Claude Sonnet 4.6 (cached, extended thinking on demand)
recovery (>3 stuck)        → Claude Sonnet 4.6 with extended thinking
dense screenshot/PDF       → Claude Opus 4.7 (rare)
fallback if Anthropic out  → Gemini 2.5 Flash → Groq Maverick
```

## Appendix D — Market landscape snapshot (April 2026)

| Player | Status | What worked / failed | Lesson for Anticipy |
|---|---|---|---|
| Humane AI Pin | **Dead.** HP acquired assets Feb 2025 for $116M. ~10k units sold of 100k target. | Novelty form factor; brutal latency; useless replacing-the-phone thesis. | Don't sell against the phone. Augment. |
| Rabbit R1 | Pivoted; April 2026 added DLAM + OpenClaw alpha | Original "LAM" was Playwright scripts; agent layer mattered more than form. | Demo-ware agents fail to retain users. Action engine has to be *real*. |
| Friend.com | Shipping; vandalized in NYC | Companion-only, no subscription; loneliness pretender; cost compounds. | Pure-companion is a cul-de-sac. |
| Limitless Pendant | **Acquired by Meta Dec 5 2025**; existing customers sunset ~12 months; EU/UK killed by GDPR overnight | Best-in-class transcription was acquihire-worthy, not defensibly venture-scale. | Transcription is necessary, not sufficient. Action is the moat. |
| Tab / Compass (Schiffmann) | Pivoted into Friend; quiet | n/a | n/a |
| Plaud Note / NotePin | Boring winner, Red Dot 2025 | Vertical PMF (meeting recorder), freemium SaaS | Stay narrow; ship boring |
| Bee Computer | $49, Amazon-incubated, CES 2026 "proactive second brain" | Privacy-first (no audio storage); requires explicit activation | Amazon validates the thesis. Anticipy needs to ship *action* before they do. |
| Granola.ai | $125M raise March 2026, $1.5B valuation, web/desktop | Vertical (knowledge-worker meetings) + enterprise SaaS | Vertical wedge + enterprise distro beats consumer AI |
| Apple AI smart glasses | Targeted 2027; AirPods with cameras "this year" | Visual Intelligence as primitive | Existential threat; race the action layer |
| Meta Ray-Ban Gen 2 | Shipping LLAMA 4, "catch me up on my messages" | Owns audio I/O on the body | Privacy is the wedge they cannot copy |
| Omi | $89, open-source, BasedHardware | Frequent BLE disconnect; weak summaries in noise | Hardware reliability is non-negotiable |

**Anticipy's three unfair advantages, ranked:**

1. **Already-working browser agent.** Twelve-plus months of replication for any competitor. Lead with action.
2. **Privacy architecture as positioning.** Diarization-gated user-only voice; no raw audio storage. Limitless's death is the lesson; Meta's incentive structure means they can't credibly copy it.
3. **Donna persona as IP.** A consistent, dry, opinionated, refusing voice. Friend was vandalized partly because its persona was syrupy. Hire a writer.

---

*End of document.*
