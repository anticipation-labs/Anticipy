# Engine Failure Log

Canonical record of every test failure observed, classified, with repro, root
cause, fix, and regression status. Cluster patterns and graduate frequent ones
to models per the user directive (5+ occurrences of same pattern → model).

Date format: YYYY-MM-DD.

---

## 2026-05-08 — Baseline run

### Tier 1 (pure unit, no network)

| File | Result | Notes |
|---|---|---|
| test_auth.py | 15/15 PASS | clean |
| test_router.py | COLLECTION ERROR | imports DegradedResponse (missing) |
| test_safety.py | COLLECTION ERROR | imports DegradedResponse (missing) |
| test_main_security.py | 0/19 → ATTRIBUTE ERROR | main.py missing _ws_connection_admit, _bearer_user, _issue_confirmation_token, _hash_task, _verify_confirmation_token, _get_client_ip, MAX_WS_CONCURRENT_PER_USER |
| test_models.py | COLLECTION ERROR | imports effective_layer_timeout_seconds, provider_slot, _await_throttle (all missing) |
| test_code_sandbox.py | 24/24 PASS | clean |

**Tier 1 baseline pass: 39/39 of tests that ran. Missing-symbol class blocks 4 test files entirely (~50 tests).**

### Tier 2 (network/LLM/Supabase imports)

Import-only smoke, no test execution yet:

| File | Import | Notes |
|---|---|---|
| test_intents_deep.py | OK | |
| test_real.py | OK | |
| test_proactive.py | FAIL | effective_layer_timeout_seconds missing (cascaded from app.proactive.donna) |
| test_proactive_dataset.py | OK | |
| test_master_benchmark.py | OK | |
| test_torture_browser.py | OK | |
| test_torture_extension.py | OK | |
| test_torture_proactive.py | FAIL | same |
| test_extension_actions.py | OK | |
| test_extension_brutal.py | OK | |
| test_extension_hard.py | OK | |
| test_e2e_voice_action.py | OK | |
| test_concurrency.py | OK | |
| test_preferences.py | OK | |
| test_memory_layer.py | OK | |
| test_long_conversation_diagnostic.py | FAIL | same |
| test_multi_speaker_diagnostic.py | FAIL | same |
| test_wire_diagnostic.py | OK | |

---

## Failure clusters

### F1: Missing throttle/slot/timeout helpers in app/models.py
**Severity:** BLOCKER — prevents 4+ unit-test files from collecting and 4+
proactive-cascade test files from importing.

**Symbols missing:**
- `class DegradedResponse` — sentinel returned when all models in cascade fail
- `_throttle_locks: dict[str, asyncio.Lock]`
- `_throttle_last_call: dict[str, float]`
- `_provider_semaphores: dict[str, asyncio.Semaphore]`
- `async _await_throttle(provider, min_interval)` — sleeps so that ≥ min_interval has elapsed since the last call to that provider
- `async provider_slot(provider, min_interval)` — async ctx mgr; per-provider Semaphore(1) + throttle
- `effective_layer_timeout_seconds(base, expected_concurrent_calls)` — pads timeout for fan-out queue
- `llm_call_json_str(messages, tracker, max_tokens=…)` — provider-native JSON mode, returns string

**Cause:** Per progress.md, prior in-conversation rewrite of models.py was never committed. On-disk version pre-dates throttle infra. Proactive package depends on it heavily. New unit tests document the contract.

**Fix plan:**
1. Add throttle state + helpers to models.py.
2. Make `llm_call` return `DegradedResponse()` on full cascade failure (callers update).
3. Add `min_interval_seconds` field to MODEL_CHAIN entries in config.py (default 0).
4. Add `llm_call_json_str` (provider-native JSON mode).

### F2: Missing classifier dataclass + LLM-only router
**Severity:** BLOCKER — test_router.py blocks on collect.

**Contract gaps:**
- `classify(text, tracker)` must return `Classification` dataclass with `.category` + `.degraded`
- router.py must NOT use `import re`, `CHAT_PATTERNS`, `ACTION_KEYWORDS`, `QUESTION_PATTERNS` — i.e. remove keyword pre-classifier (no-hardcoding rule).

**Side effect:** main.py call site uses `category = await classify(...)` as string. Must update.

**`needs_clarification`** uses regex, but is consumed by main.py too. Move to a separate `clarify.py` module so router.py can drop `import re`.

### F3: Missing AI safety_check + Verdict dataclass
**Severity:** BLOCKER — test_safety.py blocks on collect.

**Contract gaps:**
- `safety_check(text, tracker)` returns `Verdict` with `.blocked`, `.requires_confirmation`, `.reason`, `.degraded`
- LLM-driven (not regex)
- Empty input → blocked=False, no LLM call
- DegradedResponse → blocked=True (fail-closed)
- Truncates input to 1500 chars before LLM
- Normalizes blocked+requires_confirmation→blocked-only

**Existing keyword-based check_blocked / block_reason / check_needs_confirmation are still called from main.py.** They can stay as a **deterministic floor** (defense in depth), but the AI layer needs to be added on top.

### F4: Missing main.py security helpers
**Severity:** BLOCKER — test_main_security.py blocks at attribute access.

**Contract gaps:**
- `_ws_connections_by_user: dict[str,int]`, `_ws_connections_by_ip: dict[str,int]`
- `MAX_WS_CONCURRENT_PER_USER`, `MAX_WS_CONCURRENT_PER_IP` constants
- `_ws_connection_admit(user_id, ip)` returns `None` on admit, error string on cap
- `_ws_connection_release(user_id, ip)` decrements (clamped to 0)
- `_get_client_ip(request)` honors `TRUST_FORWARDED_FOR=1` env, default direct
- `_issue_confirmation_token(task, user_id)` / `_verify_confirmation_token(token, task, user_id)` (JWT, purpose=execute_intent, exp + task_hash)
- `_hash_task(task)` (sha256 helper for token payload)
- `_bearer_user(authorization)` validates Bearer, raises `HTTPException(401)` on bad

---

## Decisions made autonomously

- D1 (2026-05-08): Treating F1-F4 as production-code refactors rather than test edits. The tests document the no-hardcoding contract; rewriting tests to match keyword-based router/safety would ratify a violation of the project rule. Production caller (main.py) updated accordingly.
- D2: Keeping `check_blocked` / `block_reason` keyword tables as a deterministic floor (defense in depth) under the new LLM `safety_check`. Removing them entirely would re-open the password/financial blocked-list as LLM-only, which is brittle for the highest-confidence categories.
- D3: Moved `needs_clarification` to `app/clarify.py`. Reasons: (1) test_router enforces no `import re` in router.py; (2) clarify is a UX gate (does the user need to specify slots first?), not a routing decision. Clarify is a deterministic floor; the future LLM-based slot-completeness check will sit on top of it.

---

## 2026-05-08 — F1..F4 fix outcomes

| # | Test file | Before | After | Notes |
|---|---|---|---|---|
| F1 | test_models.py | COLLECTION ERR | 7/7 PASS | DegradedResponse + throttle/slot/effective_layer_timeout_seconds/llm_call_json_str shipped |
| F2 | test_router.py | COLLECTION ERR | 9/9 PASS | classify→Classification dataclass; needs_clarification → app/clarify.py |
| F3 | test_safety.py | COLLECTION ERR | 16/16 PASS | safety_check + Verdict; LLM-driven; fail-closed on degraded |
| F4 | test_main_security.py | 2/19 | 19/19 PASS | _ws_connection_admit/release, _hash_task, _issue/_verify_confirmation_token, _bearer_user, _get_client_ip honoring TRUST_FORWARDED_FOR |
| – | test_auth.py | 15/15 | 15/15 | unchanged |
| – | test_code_sandbox.py | 24/24 | 24/24 (one flake) | test_bwrap_cpu_cap_kills_busy_loop occasionally exceeds 6.0s threshold under load (logged as FLAKE-1) |
| – | test_proactive.py (unit) | (blocked F1) | 38/38 PASS | unblocked by F1 |

**Tier-1 stability:** 90/90 across 3 consecutive runs (37s / 29.5s / 39.7s wall-clock).

### FLAKE-1: test_bwrap_cpu_cap_kills_busy_loop timing variance

`test_code_sandbox.py::test_bwrap_cpu_cap_kills_busy_loop` asserts the wall-clock duration of a CPU-rlimit-killed busy loop is `< 6.0s`. Observed 6.549s under concurrent load, 1.9s solo. Not introduced by my changes; surfaced under contention. **Decision:** monitor, do not patch yet — relaxing to 8.0s would mask a real CPU-cap-not-killing regression. Will revisit if it shows up 5+ times.

---

## 2026-05-08 — Tier-2 baseline (LLM-only, no browser)

Other Claude session is running `test_extension_brutal.py -n 5`; **deferring all
headed-browser tests on this thread** to avoid colliding with that session.

### LCD-1: long_conversation_diagnostic (single 70-utterance pass)

| Metric | Value | Bar | Status |
|---|---|---|---|
| utterances | 70 | n/a | |
| minutes of talk | ~4.0 | n/a | |
| real intents | 5 | n/a | |
| dispatched | 7 | n/a | |
| recall (real intents hit) | 5/5 = 100% | n/a strict | PASS |
| false positives (extras) | 2 | 0 | FAIL |
| density (per-min talk) | 1.76 | < 1.5 | FAIL |
| log-only | 0 | n/a | |
| elapsed | 517.9s | | |

**Failure cluster LCD-1.A: meta-level "prioritize_tasks" dispatch.** L2
extracted a "user prioritized tasks" intent from a passage where the user
verbally listed what they had to do. That's a side-effect of "the user
enumerates 2+ concrete items as part of an errand or commitment" rule
in the salience prompt — it picks up the meta-list as a separate intent.

**Failure cluster LCD-1.B: dispatch overlap "lookup_website" vs
"search_recipe".** The user asked for "the recipe for a soup from The
Savory Spoon"; engine fired both `search_recipe` and `lookup_website`
for the same underlying intent. L6 dispatcher dedup didn't catch it
because the action_verb differed.

Both clusters affect the user-stated bar of "1-6 / day", and density
1.76/min implies ~7-30 alerts per real conversation hour, ~50-200 per
day with 5h talking. That's well over the bar.

These are the proactive cascade's 2026-05 priorities. The other Claude
session has been pushing the voice→intent benchmark from 57% → 73%;
density is the next gap. **Not blocking my own thread to attack it
since the parallel session is closer to the source.**

### TBR-3 (infra, RATE-LIMIT CEILING): both providers exhausted

After bumping judge max_tokens (TBR-2.A fix), tb1f produced 2/9 PASS.
Re-running with judge cascade fallback → Groq, ALL 9 scenario generations
failed with:

```
generation failed: all providers failed (last gemini/groq 429:
"Rate limit reached for model `llama-3.3-70b-versatile` in organization
... service tier `on_demand` on tokens per day (TPD): Limit 100000, Used 99941")
```

Both Gemini (free-tier daily quota) and Groq (100k TPD) are exhausted on
this account. The torture_browser harness alone consumes ~10-20k tokens
per scenario across (1) scenario generation (2) the agent's per-step
LLM calls (3) the post-run judge.

**Decision:** stop hammering. Quotas reset daily. Pause torture_browser
on this thread until tomorrow.

**For tomorrow:**
- Try torture_browser at N=1 once quotas reset.
- If still tight, switch the test harness to use `kimi` as a tertiary
  fallback (KIMI_API_KEY is set per .env.local; memory says it works as
  of 2026-05-01).
- If still tight, drop scenario generation in favor of a fixed scenario
  set hard-checked into the repo (loses adversarial diversity but is
  deterministic and quota-cheap).

### TBR-2 (skill-level, recurring): browser-agent task accuracy

After F-TBR-1 (CDP probe + ephemeral profile), torture_browser at N=1 ran
to completion. Strict pass: 1/9 = 11.1%. Breakdown:

| Category | Verdict | Failure mode |
|---|---|---|
| canvas_editor | PASS | Graceful sign-in decline |
| webgl_or_map | FAIL | Wrong distance: agent reported 1033km, expected 800-860km |
| shadow_dom | FAIL | judge error (Gemini JSON truncated mid-string) |
| multi_field_form | FAIL | Timeout submitting EPA contact form |
| autocomplete | FAIL | Timeout, no URL with correct route |
| lazy_load | FAIL | Wrong description extracted for GitHub topic |
| login_wall | FAIL | judge error (Gemini JSON truncated) |
| multi_step | FAIL | Incomplete Stanford address + wrong President |
| ambiguous_goal | FAIL | judge error (Gemini JSON truncated) |

**TBR-2.A: judge JSON truncation cluster** — 3/9 failures are LLM-judge
JSON truncation (`max_tokens=512` cuts mid-string in the verbose
`reason` field). Fixed by bumping judge `max_tokens` to 1024.

**TBR-2.B: skill-level failures** — 5/9 are real agent-skill failures:
- map distance accuracy (1033 vs 800-860 km)
- form submission timeouts
- search-flow timeouts
- factual extraction (wrong Stanford President)
- lazy-load result extraction

These are the kinds of failures the parallel session's voice→intent
benchmark targets at the L2 layer, but the action-engine path has its
own L1-equivalent prompts in agent.py / browser-use Agent. **Density
fixes from the parallel session won't transfer here directly.**

### TP-3: torture_proactive 3-pass run (n=3, mixed scenario sizes)

| Pass | utts | real | hit | miss | extra | dup | density | P | R | elapsed |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 29 | 5 | 5 | 0 | 0 | 0 | 2.24 | 100% | 100% | 233.9s |
| 2 | 25 | 5 | 5 | 0 | 1 | 0 | 3.10 | 83% | 100% | 193.5s |
| 3 | 25 | 5 | 3 | 2 | 1 | 0 | 2.06 | 75% | 60% | 179.9s |
| **avg** | – | – | – | – | – | – | **2.47** | **86%** | **87%** | – |

**TP-3 cluster: precision/recall vary substantially across scenarios** —
the cascade is solid on 29-utt scenarios but the 25-utt scenarios surface
both kinds of failure: the "book_flight tonight" exploration false-positive
(in passes 2 and 3 — same fail mode), and a missed-intents pattern in
pass 3 where the cascade dropped 2/5 real intents while extracting 1
false positive.

**The "book_flight tonight" exploration false-positive is now confirmed
a chronic pattern, not sample noise** (3 occurrences across 5 total
torture passes). The L1 salience prompt or L2 extract prompt isn't
distinguishing "I should book a flight tonight" (resolved commitment)
from "I might / I'm thinking of booking a flight" (exploration).

### TBR-1 (chronic, BLOCKER): browser-use 0.11.13 BrowserStartEvent 30s timeout

Repro: `python test_torture_browser.py 1` on a fresh run. Every scenario:

```
Traceback ...
ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 34539)
TimeoutError: Event handler browser_use.browser.watchdog_base.BrowserSession.
on_BrowserStartEvent#7232(?▶ BrowserStartEvent#9a29 🏃) timed out after 30.0s

INFO     [BrowserSession] ✅ Browser session reset complete
... agent proceeds anyway ...
INFO     [Agent]   ▶️   navigate: url: https://...
ERROR    [tools] Action 'navigate' failed with error: Error executing action
  navigate: CDP client not initialized - browser may not be connected yet
WARNING  [Agent] ❌ Result failed 1/6 times: ...
ERROR    [Agent] ❌ Stopping due to 5 consecutive failures
[complete] I couldn't find a way forward on that one. Want to try a different approach?
```

Root cause: in browser-use 0.11.13, `BrowserStartEvent` has a 30s internal
timeout. When Chromium's first launch on a fresh profile (random
`/tmp/wire_diag_profile_*`) takes > 30s under codespace load, the event
times out, the BrowserSession does an internal `reset()`, and `start()`
returns NORMALLY (no exception) — but the CDP client is None. The agent
then fires its first `navigate` action, which hits "CDP client not
initialized" 5 times and gives up.

`agent.py` already has a retry-on-`start()`-exception loop, but Browser
Use swallows the timeout internally so the loop never fires.

`requirements.txt` declares `browser-use>=0.12.6` but the installed
version is 0.11.13 (warning printed by the agent itself: "📦 Newer
version available: 0.12.6 (current: 0.11.13)"). The version drift
predates this session.

**Fix candidates:**
- F-TBR-1.A (preferred, surgical): after `_session.start()`, **probe** the
  CDP client. If `None` or unresponsive, force a retry through the
  existing retry path. Generic — does not depend on browser-use version
  semantics.
- F-TBR-1.B (broad): `pip install -U "browser-use>=0.12.6"`. Aligns
  installed with declared. Risk: API drift in 0.12.x may break our
  Controller registry / Custom action registration. Touches a stack
  component, but only as installed-version drift correction (declared
  is already 0.12.6), so this is **not** a stack swap — it's compliance.

Going with F-TBR-1.A first (lowest risk). If still failing, consider
F-TBR-1.B but only after a clean unit-test regression check.

### MSD-1: multi_speaker_diagnostic (single 31-utterance pass)

| Metric | Value | Bar | Status |
|---|---|---|---|
| utterances | 31 | n/a | |
| wearer truth chunks | 16 | n/a | |
| other-speaker chunks | 15 | n/a | |
| L0 wearer recall | 16/16 = 100% | 100% | PASS |
| L0 other precision | 15/15 = 100% | 100% | PASS |
| false drops (wearer→other) | 0 | 0 | PASS |
| leaks (other→wearer) | 0 | 0 | PASS |
| user-facing dispatches | 4 | n/a | |
| real wearer intents | 4 | n/a | |
| recall on wearer intents | 4/4 = 100% | 100% | PASS |
| extra dispatches | 0 | 0 | PASS |
| elapsed | 241.7s | | |

**L0 layer is solid.** 31-utterance multi-speaker conversation, no
mis-classifications either direction. The wearable's "don't act on
overheard speech" guarantee holds on this scenario.

### TP-2: torture_proactive 2-pass run (n=2, 29 utterances each)

| Metric | Pass 1 | Pass 2 | Avg |
|---|---|---|---|
| precision | 100% | 100% | 100% |
| recall | 100% | 100% | 100% |
| density (per-min talk) | 2.24 | 2.24 | 2.24 |
| extra dispatches | 0 | 0 | – |
| duplicates | 0 | 0 | – |
| elapsed | 272.9s | 310.7s | – |

**The single 25-utterance pass at TP-1 had 1 false positive** (book-flight
exploration mention asked rather than ignored). Two new 29-utterance passes
hit P=R=100%. **TP-1.A is intermittent, not chronic; sample noise on n=1.**
TP-1.B (density above 1.5/min) reproduced consistently — 2.24/min in both
n=2 passes. Density is the cluster to chase.

### TP-1: torture_proactive 1× pass (n=1 scenario)

| Metric | Value | Bar | Status |
|---|---|---|---|
| utterances | 25 | n/a | |
| real intents | 5 | | |
| recall | 5/5 = 100% | n/a strict | PASS |
| precision | 5/6 = 83% | n/a strict | PARTIAL |
| extra dispatches | 1 | 0 | FAIL |
| duplicates | 0 | 0 | PASS |
| density (per-min talk) | 3.10 | < 1.5 | FAIL |
| elapsed | 231.8s | | |

**Failure cluster TP-1.A: false-positive on "book a flight tonight"** —
the engine emitted an `ask` for a flight intent that wasn't in the
ground-truth list. This is the "exploration mention" pattern where
the user *says* "I should book a flight tonight" without committing.
The L1 salience layer didn't reject it as exploration.

**Failure cluster TP-1.B: density 3.10/min vs 1.5/min target** — the
torture-proactive run pushed 6 user-facing dispatches in ~1.9 min of
talk. The user's stated bar from progress.md is sparse, ~1-6/day. This
suggests either L4 urgency is too lax or L6 dispatcher isn't deduping
enough.

Both clusters are existing OPEN issues — the parallel session's
voice→intent benchmark already targets recall/precision, but density
isn't measured there. TP-1.B is the user-bar-violation worth triaging.

Need n≥3 passes to confirm the cluster vs sample noise.
