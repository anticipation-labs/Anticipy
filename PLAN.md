# Anticipy Action Engine — Build Plan (converged)

This supersedes `PROBLEM_MAP.md`. The map listed what's broken; this is what we ship.

The plan synthesizes three independent research passes (`research/cost_rpm_quotas.md`, `research/browser.md`, `research/quality_reliability.md`) into one coherent architecture. The convergence is strong: AxTree-based observation, trajectory caching, multi-agent split on different models, and a `chrome.debugger`-based bridge appear in every report independently. We're not picking from competing recommendations — we're stacking the recommendations that all three agents arrived at.

---

## What we're building

A browser-control system that:

1. Runs in the user's real Chrome (their cookies, their session, their residential IP)
2. Is installed once and never reloaded
3. Costs ≤ $99/year for 1M tasks
4. Hits 95%+ reliability on hard tasks (Gmail compose, Calendar read, Reddit thread extract, multi-site research, authenticated cart flows)
5. Has no per-site rules

---

## End-state architecture

```
┌─────────────────────────────────────────────────────────┐
│  USER'S CHROME                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Anticipy Bridge Extension (signed, locked, ~200 LOC)│
│  │  • chrome.debugger.attach() per active tab          │
│  │  • WebSocket relay → server                          │
│  │  • Receives CDP commands, executes against tabs      │
│  │  • NopeCHA + audio reCAPTCHA fallback                │
│  └──────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket (server-driven)
┌────────────────────▼────────────────────────────────────┐
│  PYTHON ENGINE (server-side, all intelligence here)     │
│                                                          │
│  Bridge Layer                                            │
│   bridge_cdp.py — Browser Use CDP transport over WS     │
│                                                          │
│  Observation Layer                                       │
│   axtree.py — accessibility tree → 200-400 token snap   │
│   focus_retriever.py — LLM-pruned subtree (FocusAgent)  │
│   omniparser_fallback.py — vision for canvas/iframes    │
│                                                          │
│  Routing Layer                                           │
│   router.py — read-only → Jina Reader; action → agent   │
│   trajectory_cache.py — Supabase RAG over past wins     │
│                                                          │
│  Intelligence Layer                                      │
│   planner.py    (Gemini 2.5 Flash, structured plan)     │
│   executor.py   (Cerebras Qwen3-235B, fast actions)     │
│   critic.py     (different model — Pixtral or Gemini)   │
│   verifier.py   (end-state assertions per task type)    │
│   reflector.py  (only fires when 2× critic-fails)       │
│                                                          │
│  LLM Pool                                                │
│   llm_router.py — LiteLLM with quota tracking,          │
│                   round-robin across:                    │
│   • Cerebras Qwen3 free (1M tok/day, text)              │
│   • Pixtral 12B free (1B tok/month, vision)             │
│   • Gemini 2.5 Flash free × N projects (rotation)       │
│   • Llama 3.2 11B Vision paid spillover ($0.049/MTok)   │
│                                                          │
│  Reliability Layer                                       │
│   circuit_breakers.py (per-provider, 40% fail / 60s)    │
│   idempotency.py (write-action keys, dedup)             │
│   retry.py (DOM-drift detect, page-hash compare)        │
└──────────────────────────────────────────────────────────┘
```

---

## What we delete

- `extension/agent.js` (1,800+ LOC of locked-in agent logic) → replaced by ~200 LOC bridge
- `extension/popup.js` auth flow → simplified, no more apiConfig keys (server holds them)
- `engine/app/agent.py` Browser Use launch path keeps the framework but observation is replaced
- `engine/app/harness.py` (legacy observation compression) — superseded by axtree.py
- `engine/app/browser.py` (legacy browser manager) — superseded by bridge_cdp.py
- `engine/app/voyage.py` references → trajectory cache uses Postgres tsvector + Supabase pgvector

---

## What we keep

- Browser Use 0.11.13+ as the action-execution framework — they shipped `--cdp-url` support yesterday, we ride upstream
- `engine/app/main.py` FastAPI WebSocket handler — keep, extend with bridge protocol
- `engine/app/safety.py` — deterministic safety rules, untouched
- `engine/app/messages.py` — user-facing message templates, untouched
- `engine/app/auth.py` — bcrypt + JWT, untouched
- Supabase tables (engine_users, engine_tasks, engine_trajectories, browser_profiles)

---

## Modules to build (ordered by dependency)

Each module has: purpose, interface, dependency on prior modules, acceptance criterion (how we know it's done).

### Layer 0 — Bridge (unblocks everything else)

**M0.1 `engine/app/bridge_cdp.py`**
- *Purpose*: speak Chrome DevTools Protocol over our WebSocket so Browser Use can drive the user's tabs
- *Interface*: implements the `BrowserSession` shape Browser Use expects, but transport is `await ws.send(json.dumps(cdp_command))`
- *Acceptance*: a smoke task ("navigate to wikipedia.org") opens a tab in a connected Chrome and returns the page title
- *Depends on*: nothing

**M0.2 Bridge extension v1 (`extension/bridge/`)**
- *Purpose*: minimal Chrome extension that holds a WebSocket to our server and relays CDP commands to `chrome.debugger`
- *Interface*: ~200 LOC. Listens for server commands, forwards to `chrome.debugger.sendCommand(target, method, params)`. Echoes events back. 25-second keepalive ping for MV3 service-worker survival.
- *Acceptance*: signed, listed on Chrome Web Store, never needs another reload, M0.1 smoke passes through it
- *Depends on*: M0.1 (the protocol it relays)

**M0.3 Chrome Web Store submission**
- *Purpose*: get a stable extension ID and a "permanent" install path (sideload OK for V1, store-listed for production)
- *Acceptance*: store listing live, user clicks install once, extension survives Chrome restarts and updates
- *Depends on*: M0.2

### Layer 1 — Observation (the cost+quality unlock)

**M1.1 `engine/app/axtree.py`**
- *Purpose*: replace Browser Use's DOM serialization with accessibility-tree extraction. ~200-400 tokens/snapshot vs 12-18k.
- *Interface*: `await axtree_snapshot(tab_id, max_tokens=400)` returns `{nodes, focus, url, title}`
- *Acceptance*: on 10 representative pages (Wikipedia, Gmail, Calendar, Reddit, x.com, news.yc, github, amazon, books.toscrape, ddg), the snapshot is ≤ 600 tokens AND the LLM can correctly identify the next action to take from it
- *Depends on*: M0.1 (CDP access)

**M1.2 `engine/app/focus_retriever.py`**
- *Purpose*: when the AxTree is still too big (long pages, complex SPAs), use a small LLM to prune to the relevant subtree. FocusAgent pattern.
- *Interface*: `await focus(axtree, task_intent) → pruned_axtree`. Backs off to full tree on cache miss.
- *Acceptance*: on Gmail / Calendar / Sheets pages where M1.1 returns >500 tokens, FocusAgent compresses to <200 with no accuracy regression on the action benchmark
- *Depends on*: M1.1

**M1.3 `engine/app/omniparser_fallback.py`**
- *Purpose*: vision-only fallback for canvas, iframes, and pages that hate accessibility trees
- *Interface*: takes screenshot, runs OmniParser V2 (or hosted equivalent), returns numbered bounding boxes (Set-of-Mark style)
- *Acceptance*: on a Figma/Sheets/Excalidraw page, agent can perform a click on a specific element identified visually
- *Depends on*: M0.1

### Layer 2 — Routing (the cost win)

**M2.1 `engine/app/router.py` (rewrite)**
- *Purpose*: classify incoming task as `read_only` ("what does X say?") or `action` (any side effect)
- *Interface*: `classify(task_text) → {kind: "read_only"|"action", confidence}`. No hardcoded site rules — pure intent classification via small LLM (Cerebras llama3.1-8b, free).
- *Acceptance*: on a 50-task labeled set, classifier hits >95% on a held-out split
- *Depends on*: nothing

**M2.2 `engine/app/jina_reader.py`**
- *Purpose*: bypass the agent entirely for read-only tasks. Just hit `r.jina.ai/{url}`, get markdown, ask Cerebras to extract the answer.
- *Interface*: `await read_only(task, url) → answer`
- *Acceptance*: on Wikipedia / news / blog tasks, answer matches agent path's answer at <1/100 the token cost
- *Depends on*: M2.1

**M2.3 `engine/app/trajectory_cache.py`**
- *Purpose*: cache successful trajectories keyed by `hash(task_intent + start_url + axtree_fingerprint)`. On hit, replay the action sequence. On replay-fail, fall back to LLM.
- *Interface*: `await cache_lookup(task) → trajectory|None`; `await cache_store(task, trajectory)`. Storage: `engine_trajectories` table + Supabase pgvector for semantic similarity.
- *Acceptance*: second run of an identical task is >10× faster and uses zero LLM tokens
- *Depends on*: M1.1 (uses axtree fingerprint)

### Layer 3 — Intelligence (multi-agent split)

**M3.1 `engine/app/llm_router.py`**
- *Purpose*: LiteLLM-based pool with per-provider quota tracking, circuit breakers, and ordered fallback chains
- *Interface*: `await call(model_role, messages, schema=None)` where role is `planner|executor|critic|verifier|router`. Each role has its own preferred model + fallback chain.
- *Configured pool*: Cerebras Qwen3 (executor primary) → Pixtral 12B free (vision fallback) → Gemini 2.5 Flash multi-project rotation → Llama 3.2 11B Vision paid spillover
- *Acceptance*: synthetic load of 100 calls in 30s succeeds 100% by spilling across providers; per-provider quota counters update correctly
- *Depends on*: nothing

**M3.2 `engine/app/planner.py` (rewrite)**
- *Purpose*: read task + initial AxTree → produce 3-7 step plan with success criteria per step
- *Interface*: `await plan(task, initial_axtree) → [{step, goal, success_criteria}]`. Strict JSON via Gemini structured output.
- *Acceptance*: on a 25-task labeled set, plans are coherent and the success_criteria are observable from page state
- *Depends on*: M1.1, M3.1

**M3.3 `engine/app/executor.py` (rewrite)**
- *Purpose*: take current step + AxTree → emit one CDP-shaped action (click, type, navigate, extract, done)
- *Interface*: `await next_action(step, axtree, history) → action`. Cerebras Qwen3 primary (free, fast).
- *Acceptance*: on the action benchmark, > 90% of single-action choices are correct vs human label
- *Depends on*: M1.1, M3.1, M3.2

**M3.4 `engine/app/critic.py` (re-enable, repurpose)**
- *Purpose*: after each action, decide: progress / no_progress / unsafe. Different model from executor (anti-degeneration-of-thought).
- *Interface*: `await criticize(action, before_axtree, after_axtree, plan, step_idx) → {verdict, diagnosis}`. Pixtral 12B (vision) or Gemini.
- *Acceptance*: on a 50-step labeled set, critic agreement with human label > 85%
- *Depends on*: M1.1, M3.1, M3.3

**M3.5 `engine/app/reflector.py` (re-enable, gate harder)**
- *Purpose*: only fires when 2 consecutive critic verdicts are no_progress. Decides: pivot (new plan) / abort. Last-line-of-defense.
- *Interface*: `await reflect(history, two_critic_diagnoses) → {decision, new_plan|abort_message}`. Different model from planner+executor+critic.
- *Acceptance*: when manually injected into a 50-step stuck-trajectory dataset, reflector pivots correctly > 70% of the time
- *Depends on*: M3.2, M3.4

### Layer 4 — Verification (the biggest single quality win)

**M4.1 `engine/app/verifier.py` (rewrite — end-state assertions, not LLM trust)**
- *Purpose*: when the agent declares `done`, don't trust it. Fetch evidence. The biggest single quality win identified by research (+25-40 points).
- *Interface*: `await verify(task, agent_done_payload) → {ok, missing, evidence}`. Per-task-type assertion library:
  - `read_extract`: required values from the task description must literally appear in the extracted text
  - `email_send`: re-fetch Sent folder, find a message matching subject in the last 60s
  - `calendar_create`: re-fetch events, find one matching title + start time
  - `cart_add`: re-fetch cart, item present
  - `comment_post`: re-fetch comments, agent's text appears
  - generic fallback: required_fields heuristic
- *Acceptance*: on a 30-task multi-type benchmark, verifier catches every false-success the executor surfaced (zero false-positive `done`s)
- *Depends on*: M0.1, M3.1

### Layer 5 — Reliability hardening

**M5.1 `engine/app/circuit_breakers.py`**
- *Purpose*: per-provider 40%-fail-in-60s circuit. Half-open probe at cooldown.
- *Acceptance*: when one provider is down (simulated 100% fail), traffic routes around it within 60s and resumes when it recovers
- *Depends on*: M3.1

**M5.2 `engine/app/dom_drift.py`**
- *Purpose*: before re-attempting a cached action, hash the current AxTree against the one captured when the cache entry was written. Mismatch → invalidate cache, re-plan.
- *Acceptance*: when a page's structure changes between runs, the cached trajectory is invalidated cleanly instead of executing on stale selectors
- *Depends on*: M1.1, M2.3

**M5.3 `engine/app/idempotency.py`**
- *Purpose*: for irreversible actions (send_email, place_order, post_comment), require an idempotency key per task; the bridge refuses duplicates within 60s.
- *Acceptance*: under simulated retry storm on a write-action, only one side effect lands
- *Depends on*: M0.1

### Layer 6 — CAPTCHA (low priority but cheap)

**M6.1 NopeCHA install at signup**
- *Purpose*: free, no API call, runs in user's browser. 100/day on residential IP.
- *Acceptance*: on a CAPTCHA-protected test site, agent gets through without server-side captcha service
- *Depends on*: M0.2

**M6.2 reCAPTCHA audio fallback**
- *Purpose*: when NopeCHA misses (>100/day or reCAPTCHA hard mode), use playwright-recaptcha audio path — free, code-only.
- *Acceptance*: 95%+ on a curated reCAPTCHA test set
- *Depends on*: M0.1, M6.1

---

## Build order (dependency graph)

```
M0.1 (bridge protocol)
  → M0.2 (extension)
      → M0.3 (Chrome store listing)
M0.1 → M1.1 (axtree)
            → M1.2 (focus retriever)
            → M5.2 (drift detect)
M1.1 → M2.3 (cache)
M3.1 (llm router) → M2.1 → M2.2 (jina)
                  → M3.2 (planner)
                          → M3.3 (executor)
                                  → M3.4 (critic)
                                          → M3.5 (reflector)
                                          → M4.1 (verifier)
M3.1 → M5.1 (circuit breakers)
M0.1 → M5.3 (idempotency)
M0.2 → M6.1 (NopeCHA)
            → M6.2 (audio reCAPTCHA)
M1.3 (omniparser) — independent, ship when canvas/iframe failures justify
```

Critical path: **M0.1 → M0.2 → M0.3 → M1.1 → M2.3 → M3.* → M4.1**. Everything else parallelizes.

---

## Acceptance — the single benchmark that gates "done"

A 25-task hostile benchmark covering:
- Read-only on stable sites (Wikipedia, news, blog, books.toscrape, GitHub README)
- DDG / Google search + extract
- Multi-site research (HN headline → Wikipedia first sentence; news headline compare)
- Authenticated read (Gmail unread count, Calendar today's events, Reddit personal feed)
- Authenticated action (Calendar create event with verifier-checked side effect; Gmail draft with verifier-checked Drafts folder)
- E-commerce read (Amazon product page, BestBuy price)
- Cross-domain compare (Amazon vs BestBuy)
- Captcha-gated (the-internet.herokuapp captcha demo)
- Login flow (saucedemo.com checkout)
- Canvas-light (Excalidraw add a shape — fallback to OmniParser)
- Hostile abort (task that should be refused: "delete all my emails")

Pass criteria:
- 24/25 task wins (96%) — one allowed canvas/captcha failure
- Total LLM tokens used < 1M for the full run (prove the compression works)
- Total wall clock < 60 minutes
- Cost < $1 (proves the free pool absorbs ~all of it)
- Zero false-positive `done`s (verifier catches every wrong claim)

If the benchmark fails on a specific task, the failure mode determines which module gets iterated. We don't ship until the whole 24/25 + token + cost + reliability + verifier-trustworthiness gates pass simultaneously.

---

## Deployment

- Engine runs on Fly.io (already has `engine/fly.toml`). Cold-start is fine because the WebSocket holds the session warm.
- Extension lives in Chrome Web Store with a fixed extension ID. User installs once.
- Vercel website routes `wss://anticipy.ai/ws` to the Fly engine.
- Multi-project Gemini rotation: 5+ Google Cloud projects on the engine's billing — quota stacks 5×, all free tier.
- Pixtral 12B free (1B tok/month) on Mistral La Plateforme — primary vision provider.
- LiteLLM tracks per-key TPM/RPM/TPD/quota in Redis (already on Fly).

---

## Risks (called out, not glossed)

1. **Chrome Web Store review of `"debugger"` permission**: 1-2 week delay possible. Mitigation: while review pending, keep developer-mode sideload zip on `anticipy.ai/anticipy-extension.zip` (already does this).
2. **Yellow "automated test software" bar in Chrome**: unhideable, fired whenever `chrome.debugger.attach` runs. Anthropic's Claude for Chrome accepts this UX. We will too.
3. **MV3 service-worker WebSocket eviction**: 30-second idle timeout. 25-second keepalive ping mitigates. Tested in `pasky/chrome-cdp-skill` and confirmed stable.
4. **Chrome 136+ killed `--remote-debugging-port` against the user's profile.** This means we MUST use `chrome.debugger` from inside an extension — there is no profile-clone trick. The plan accounts for this; any future "let's just use CDP directly" suggestion is a dead end.
5. **Pixtral free 1B tok/month is generous but not infinite**. At 5k tok/task that's 200k tasks/month free. If we exceed, paid spillover starts at $0.10/MTok.
6. **Trajectory cache poisoning**: a cached "win" for site X might be obsolete after site X redesigns. M5.2 (DOM drift) is the structural defense. We also TTL the cache (default 30 days).
7. **Browser Use upstream stability**: they shipped CDP yesterday. APIs may shift. We pin the version and update on a deliberate cadence, never auto-upgrade.

---

## Things research said to skip

- Best-of-N at inference (CATTS) — too slow for real-time UX
- Fine-tuning a base model (OpAgent-style) — months of work, no training stack
- ABP frozen-browser substrate — track the paper; don't build it ourselves
- AGPL deps (Skyvern, nodriver, BrowserOS) — license-incompatible
- LaVague — dead project, skip
- Forking Browser Use — upstream is solving our problem, don't fragment
- Stagehand — strongest alternative but TS-first, would scrap 4,200 LOC of Python
- 2captcha / CapSolver — paid; NopeCHA + audio fallback covers our volume

---

## What changes for the user

- One install of the new bridge extension. After that, they never touch it again.
- Their /engine page works the same way: type a task, see results.
- Tasks that used to fail at 0/35 now hit 24/25.
- They never see a yellow bar surprise — we tell them up front this is what enables real-Chrome operation.
- No paid LLM key required to operate the engine.
- Their data and cookies never leave their machine; the engine sees only the AxTree snapshots and CDP responses, which it generates against THEIR browser.

---

## Open questions for omar

1. Chrome Web Store review timing — are you OK with us submitting now while we keep the sideload zip live as a fallback? (Lowers risk of waiting on review.)
2. How many Google Cloud projects do you want me to provision for the multi-project Gemini rotation? Each one carries ~250-1500 free RPD; 5 projects = comfortable margin.
3. Pixtral 12B free tier requires a Mistral La Plateforme account with billing attached (free tier still asks for a card on file). OK to set that up?
4. Final go/no-go on the Chrome Web Store `"debugger"` permission — yellow bar will appear while attached. Once you're OK, we proceed.
