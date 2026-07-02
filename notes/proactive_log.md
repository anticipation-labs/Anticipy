> ⚠️ **SUPERSEDED AS AUTHORITY — 2026-07-02.** The living truth is **`CANON/00_START_HERE.md`**.
> Distilled into CANON/01 + 02 + 04. Kept whole as the deep reference — the use-case library and the
> feel/measurement record here remain the richest material in the repo.

# Proactive Engine — build log (branch `proactive/real`)

The third leg: act-first, harm-gated. Built room by room, test-gated, each green room
fast-forwarded into **local** main (no push). Skeleton being made real:
`core/anticipy_engine/core/proactive.py::ProactiveEngine` (wired via `control_core.feed()`).

## 0. CLEAR-THE-BAR
Does a founder / exec / student (18–25) get an assistant that acts on its own all day and only
interrupts before something that could hurt them? **YES, on the proven path:**
- It **ACTS** on safe/reversible work without asking — act-precision 1.000, act-recall 1.000,
  over-ask 0.000 on the labeled day (Room 7). No permission-seeking for safe tasks.
- It **STOPS before harm** — every detrimental action is caught and asked, NEVER executed
  silently: harm-catch recall 1.000 + SILENT-HARM gate 0, held across Room 2's 50-action battery
  AND Room 7's report card (the hard 100% gate).
- The **ask reaches the user and their reply RESUMES the exact paused action** (Room 4: real
  Twilio behind creds + in-app approve/deny in the downloadable app, which BUILDS).
- It **ANTICIPATES** (Room 3 fires on due/elapsed commitments, fire-once) and **respects
  attention** (Room 5 caps interruptions + learns from declines).

**Where it does NOT fully clear the bar yet — named next steps:**
- Memory's confidence is weak (0.30 abstention) → the harm-line fails safe to ASK on the gray
  middle, logged as `memory_forced` (counted). NEXT: the stronger confidence signal (Deferred-2).
- The harm-line is a fixed policy; it does not yet LEARN the user's line from approve/decline.
  NEXT: wire the learning loop off the Room 4/5 decline signal (Deferred-1).
- One real outbound proof (a live Twilio SMS) needs the user's creds + a test number (a one-time
  human action); everything else is proven on mock/stub.

## Merge / push policy (decided with Omar, 2026-06-04)
- **LOCAL main only — NO push to origin.** Omar wants everything collapsed onto one trunk
  (main), but no outward/Vercel side effects mid-build. He'll push to GitHub on purpose once
  the proactive engine is done and stable.
- One-time cleanup done: fast-forwarded local main from `ad0830f` (Next.js placeholder only)
  through the entire engine stack to `13c133c` (scaffold→core→hands→memory + eval harness).
  Pure ff, no force, no rewrite, no branch deletion, zero logic touched. Suite GREEN 21/21 at
  the new main.
- Per room: ff local main when the room + full suite are green. `proactive/real` is the
  working branch. Any non-clean ff → STOP and show, never force.

## DEFERRED (do NOT start during the 7 rooms — raise when Room 7's log is written)
1. **Harm-line should LEARN from approve/decline over time**, not just read a fixed category
   list. When Omar approves/declines an ask, that should sharpen where the line sits next time
   (e.g. always approves restaurant bookings >$200 → stop asking; always declines a kind of
   email → treat as more detrimental). This is the SAME signal as the Room 5 decline-capture —
   one system, not two. Build rooms 1–7 as specced first; wire the learning loop after Room 7.
2. **Memory's confidence signal is weak** (the 0.30 abstention finding, Memory Fix 2). The
   harm-line leans on it for the gray middle ("is this email binding?"). Where the harm-line
   depends on memory confidence and it's LOW → it MUST fall back to ASK (unsure-means-ask).
   That fallback must be **explicit and logged with a count** (built into Room 2), so we can see
   how often the weak signal forces an ask — that count tells us how badly we need the stronger
   confidence signal next.

---

## Room scorecards
(appended as each room goes green)

### Room 1 — Triage Gate (the bouncer) ✅
- **Built:** `proactive/triage.py::Triage` — deterministic high-recall bouncer. Positive
  signals: action verbs (word-boundary) + commitment/request/imperative/deadline regexes.
  Negative: empty / sub-2-token / pure-filler / bare observations. Cheap-model tiebreak for
  ambiguous events is behind the flag (live-only; fails OPEN; NEVER in CI). Wired as
  `ProactiveEngine._triage` (delegates), so dropped events never reach the gate → zero smart
  calls on the ~99%.
- **Test** (`test_triage.py`): replayed 39-event labeled stream (23 noise / 16 real, incl.
  tricky word-boundary "sending"≠send and intent-only "I should get back to Mom"). Realized:
  **recall on real = 16/16 = 1.000** (hard bar — nothing real dropped), **noise-drop = 23/23
  = 1.000**, **smart-model calls = 0** (cost spine).
- **Suite after:** 22/22 GREEN (21 + triage; `test_proactive` unchanged).
- Commit/main hash: see Commit stack (bottom).

### Room 2 — The Harm-Line (act-first, ask-only-before-harm) ✅
- **Built:** `proactive/harm.py::HarmLine` — ONE deterministic, inspectable policy (enforcement
  close to the action, per current guidance). DETRIMENTAL (ask), checked first + override:
  money, destroy, post-public, binding-send, sign-up, auth-wall. REVERSIBLE (act): research,
  draft (NOT send), add-to-cart, reminder/calendar-hold, reserve, prepare-doc. Handles
  draft-vs-send ("draft a reply" acts; "reply to X" asks) and reminder-frame ("remind me to
  email X" acts — the future action is re-gated when it fires, Room 3). Gray middle = memory:
  a send fails safe to ASK unless memory is HIGH-confidence the recipient is casual;
  low-confidence/abstain → `memory_forced` ASK, counted + logged (Deferred-2).
- **Rewired** `ProactiveEngine.on_event` act-first: triage → read_context → harm-line → act
  (start_goal) | ask (raise). HARD assert in code: a detrimental verdict NEVER creates a goal.
  `read_context` output enriched additively (+top_relevance, +abstain) for the gray middle
  (frozen worker CONTRACT untouched — method sig + proof unchanged).
- **Test** (`test_harmline.py`, 50 labeled actions): **DETRIMENTAL recall 27/27 = 1.000**
  (HARD SUB-GATE — no silent harm), **safe act-rate 23/23 = 1.000** (act-first, no over-ask),
  act-precision 1.000, **memory-forced asks = 5** (the binding sends — the Deferred-2 count
  that measures how badly we need the stronger confidence signal). `test_proactive` rewired to
  act-first; 3 downstream tests (glassbox / brain_loop / hands_loop) moved off the old
  "do_and_notify" to act-first safe events — orchestrator/hands logic untouched.
- **Suite after:** 23/23 GREEN (added harmline).
- Commit/main hash: see Commit stack (bottom).

### Room 3 — The Trigger Model (time + open-loop watching) ✅
- **Built:** `proactive/trigger.py::TriggerWatcher` — watches the open_loops ledger against a
  clock. A loop fires when `due_ts <= now` (TIME) or it's been open `>= stale_after` with no
  due-time (ELAPSED). Fire-once via an in-memory fired-id set (no storms). `MemoryWorker`
  gained `list_open_loops` (additive read intent) as the structured condition source.
  `ProactiveEngine.trigger_tick(now)` runs each fired loop through the SAME
  triage→harm-line→act/ask path (NO new input event); logs `trigger_fired` to the glass-box.
- **Test** (`test_trigger.py`): 5 planted loops — due(send) + due(research) + elapsed(draft)
  fire; future + fresh don't; routing send→**ASK**, research/draft→**ACT**; a second tick at
  the same clock fires **0** (fire-once). Real MemoryWorker + stub hands; deterministic.
- **Suite after:** 24/24 GREEN.
- **Refinements noted:** persist the fired-mark across restart; extract due-TIME from
  "Friday"→due_ts in capture (the watcher already consumes due_ts when present).
- Commit/main hash: see Commit stack (bottom).

### Room 4 — Real Channels + the Ask Round-Trip ✅
- **Built:** `channels/text.py::TextChannel` is now REAL — a Twilio SMS when
  `ANTICIPY_CHANNELS_MODE=live` + TWILIO_* creds are present, else MOCK (records to `.sent`;
  CI-safe + free). Every send (real or mock) is logged. The ask round-trip lives in the engine:
  a detrimental verdict PERSISTS a `waiting` goal (NOT executed) + sends the ask over the
  channel + registers `{ask_id → goal}`. `resolve_ask(yes)` → `orchestrator.start_goal` resumes
  the EXACT paused goal to **done**; `resolve_ask(no)` → goal failed + writes the decline to
  memory (`write_memory` via the bus) for Room 5. HARD gate asserted in code: a detrimental
  goal stays WAITING (no step run) until approved — no silent harm.
- **Test** (`test_ask_roundtrip.py`): detrimental → paused (waiting) + mock send →
  `resolve_ask(yes)` RESUMES the exact goal to done → a second detrimental → `resolve_ask(no)`
  drops it + the decline is in memory. Asserts the RESUME (goal state), not just the send.
- **Suite after:** 25/25 GREEN.
- **One real proof outstanding (one-time human action):** a real Twilio SMS needs the user's
  creds (TWILIO_ACCOUNT_SID / AUTH_TOKEN / FROM) + a test number; the inbound-reply webhook that
  calls `resolve_ask` is wired alongside the app approve/deny surface in Room 6 (same round-trip).
- Commit/main hash: see Commit stack (bottom).

### Room 5 — The Annoyance Budget (wearable 365 days) ✅
- **Built:** `proactive/budget.py::AnnoyanceBudget` — caps PROACTIVE (engine-initiated,
  `source=system`) interruptions per rolling day; learns from declines (suppress a declined
  action-TYPE, signature = harm-category + salient tokens). USER-initiated asks are never
  suppressed. A SAFE proactive action acts silently (spends no budget — only ASKS count); a
  suppressed detrimental action is neither executed nor asked (no silent harm, no annoyance).
  Wired into `on_event` (suppression check before a proactive ask, `now` threaded for the
  rolling window) + `resolve_ask(no)` records the decline — the SAME signal as the Room 4
  decline-capture (Deferred-1: one signal, not two).
- **Test** (`test_annoyance.py`): cap=3 → 6 proactive detrimental = **3 asked + 3 suppressed**;
  a declined "email investor" type is **suppressed next time** while a different type still
  asks; a user-initiated ask **bypasses** cap 0 (safety: the user asked).
- **Suite after:** 26/26 GREEN.
- **DECISIONS-ONLY-OMAR:** the cap NUMBER is a taste call — built configurable (`max_per_day`),
  defaulted to 5 (top of the research 3–5/day ceiling), adherence measured, value left to Omar.
- Commit/main hash: see Commit stack (bottom).

### Room 6 — Frontend Wiring (everything works from the download) ✅
- **Built (backend):** `ControlCore.pending_asks()` (the "needs you" list) + `ControlCore.resolve
  (ask_id, approved)` → the engine's `resolve_ask` (same round-trip as the SMS reply). Exposed
  over HTTP: `GET /pending`, `POST /resolve` (next to the existing `GET /glassbox`).
- **Built (app):** `MainView.swift` gains a **"Needs you"** Card (polls `/pending` every 2s;
  Approve/Skip buttons POST `/resolve` to resolve the REAL paused goal) above the existing live
  glass-box feed — in the existing dark / SF-Pro / champagne design system.
- **Test** (`test_frontend_api.py`, deterministic ControlCore): detrimental → PAUSED + appears
  in `pending_asks()`; approve → the exact paused goal RESUMES to done + clears from the surface;
  deny → goal dropped + decline written; glass-box carries the full trail. **The SwiftUI app
  BUILDS** — `bash macapp/scripts/build_app.sh` → `macapp/dist/Anticipy.app` (Build complete; the
  CLT modulemap fix was in place, no toolchain wall).
- **Suite after:** 27/27 GREEN.
- Commit/main hash: see Commit stack (bottom).

### Room 7 — The Proactive-Judgment Eval (the report card) ✅
- **Built:** `engine/scripts/proactive_eval.py` — scores the REAL Triage+HarmLine on a labeled
  day (14 act / 14 ask / 10 ignore), exactly as `on_event` decides. Deterministic core (zero
  model calls); judged layer flag-gated. **SELF-PROVES the instrument first** (`--selftest`, in
  CI): plants of each class classify right + the metric math + a PLANTED silent-harm is caught
  by the gate (so the eval can't pass vacuously) — only then is a score trusted.
- **Realized report card (straight):** act-precision **1.000**, act-recall **1.000**, over-ask
  **0.000**, harm-catch recall **1.000**, ignore-correct **1.000**, **SILENT-HARM gate 0**
  (HARD 0 — met). The eval CAUGHT a real triage-coverage gap on first run (act-recall 0.571,
  harm-catch 0.857 — triage's cue list was narrower than the harm-line's vocabulary) → closed it
  by aligning triage's action verbs (a general fix; labels never touch the decision path) →
  re-measured to the above. (This is the eval working as intended: found a gap → fixed → re-ran.)
- **Judged layer** (`--judge`, pinned gpt-4o): agreement **1.000** on an 8-decision sample,
  cost **$0.004**.
- **Suite after:** 28/28 GREEN (added the `proactive_eval_selftest` instrument gate).
- Commit/main hash: see Commit stack (bottom).

---

## 2. DECISIONS-ONLY-OMAR (built configurable; values left to Omar)
- **Interruption-budget number** — `AnnoyanceBudget.max_per_day`, default 5 (top of the research
  3–5/day ceiling). Tradeoff in one line: lower = less annoyance but more proactive value
  deferred/dropped; higher = more coverage but more interruptions. Adherence is measured
  (Room 5 test); the value is your taste.
- **Harm-line gray edge** — the binding-vs-casual SEND line (a send may ACT only when memory is
  HIGH-confidence the recipient is casual). One line: looser = fewer asks but risk a binding send
  slips; tighter = safer, more asks. Currently TIGHT (fail-safe to ask; `memory_forced` counted).
  The exact threshold + which recipients count as "casual" are yours.

## 3. THE HONEST WOUNDS
- **Memory confidence is weak** (0.30 abstention). The harm-line's gray middle therefore fails
  safe to ASK and logs `memory_forced` — correct + safe, but it over-asks on sends until the
  stronger signal lands. The count is surfaced (Deferred-2).
- **The harm-line is rule-based** (deterministic, general categories). A detrimental action
  phrased with a verb outside the known categories falls to `unclassified → fail-safe ASK`
  (safe, never silent-harm) rather than a precise category. The smart-model branch for genuinely
  hard cases is a seam (live-only), not yet exercised.
- **Trigger fire-once is session-scoped** (in-memory set); persisting it across restart +
  extracting due-TIME from "Friday"→due_ts in capture are noted refinements.
- **Judged layers ran on small samples** (proactive n=8 agreement 1.000; memory judged ~12).
  Encouraging but small-n; the deterministic cores are the load-bearing measurements.
- **One real outbound channel proof is unproven** (a live Twilio SMS needs creds + a number);
  everything else is proven on mock/stub.

## 4. COMMIT STACK + FINAL STATE
`proactive/real`, fast-forwarded into LOCAL main each green room (NO push to origin, per Omar):
```
  Room 1  triage          6594649
  Room 2  harm-line        96cd972
  Room 3  trigger          6838cd6
  Room 4  ask round-trip   0564c24
  Room 5  annoyance        3bd3847
  Room 6  frontend         bcd9ad1
  Room 7  eval             (this commit — see git log)
```
Final LOCAL main = the Room 7 commit (clean fast-forward; matches `proactive/real`).
**Final suite: 28/28 GREEN.** No push to origin — Omar pushes deliberately once stable.
**NO STUBS remain in the proactive path:** real Triage, HarmLine, TriggerWatcher, TextChannel
(Twilio live/mock), AnnoyanceBudget, the ask round-trip, and the app surface — all wired to the
real bus / orchestrator / memory / channels / glass-box / scorecard / frontend.
