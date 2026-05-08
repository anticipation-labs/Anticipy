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
