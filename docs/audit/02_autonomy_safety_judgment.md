# Audit 02 — Autonomy, Safety & Judgment (the "judgment" pillar)

> Durable audit of the act/ask/silent judgment system: the 6 autonomy modes, the real decider
> (the proactive spine), the three safety floors (vent, money, no-self-attestation), and follow-up.
> Grounded in `file:line`. Verified this session by **code-read + fast deterministic (stub) runs only**
> — the OpenRouter brain was throttled, so no model-calling path (run_suite.sh, cert harness, live
> decider/tiebreak) was executed. Those are flagged in GAPS.
>
> Date: 2026-06-17. Repo: `/Users/omarebrahim/Anticipy`. Stub runtime: `PYTHONPATH=engine engine/.venv/bin/python`.

---

## What it is

Anticipy's "judgment" is the chain that turns one messy spoken line into exactly one of **act / ask /
silent** — and never acts (or even asks) on a vent, never moves money without a human, and never claims
"done" without read-back proof. It is built from four distinct pieces, and **only one of them is the
actual authority**:

1. **The proactive spine (THE DECIDER)** — `core/proactive.py::ProactiveEngine.on_event`
   (`engine/anticipy_engine/core/proactive.py:130-289`). This is the single act/ask/silent authority.
   Three rooms (triage → live decider → harm-line) then decision assembly. Everything else wraps it.
2. **The 6 autonomy modes** — `proactive/autonomy.py::classify_autonomy`
   (`engine/anticipy_engine/proactive/autonomy.py:24-46`). A **descriptive label**, not a gate. It
   re-reads an already-finished card and maps it to one of six mode strings for the product surface +
   certification harness. It enforces nothing.
3. **The three safety floors** — vent (`live_memory/review_infer.py` + `proactive/triage.py`), money
   (`proactive/harm.py`), no-self-attestation (`core/control_core.py:1236-1246`). Enforced in depth.
4. **Follow-up** — `proactive/follow_up.py::plan_follow_up` (`:30-46`). A deterministic 2-day
   "check back" plan attached to external-dependency cards. **Computed and displayed but never fired.**

The owner (typed/app) path funnels into the same spine via
`control_core._spine_card -> self.feed("app", ...) -> on_event` (`control_core.py:828-952`); fired
reminders re-enter the **same** `on_event` (`proactive.py:607`), so a deferred "remind me to send X" is
re-gated through the full harm-line when it fires.

---

## How it decides (`file:line`)

### The spine — the real act/ask/silent authority (`proactive.py:130-289`)

Three one-way rooms, each monotonic **toward safety** (no room can loosen a downstream verdict):

- **Room 1 — TRIAGE (the bouncer).** `on_event:158` → `Triage.actionable(text)`
  (`proactive/triage.py:859-983`). Deterministic, zero-model in stub, recall-biased (when unsure,
  PASS). Order: unified vent guard (`triage.py:882-886`, drops a vent-clause-riding-an-imperative
  utterance-absolute) → utterance-absolute negatives (`_COUNTERMAND` `:889`, `_TRAILING_HEDGE` `:894`,
  `_VENT_OPENER/_VENT_CLOSER` `:901`) → clause-scoped negatives then positive cues
  (`:911-964`) → pure-vent absolute `False` (`:969`) → `_CONTEXT_ONLY`/`_META_INJECTION` drops
  (`:971-978`) → ambiguous: stub drops, live MAY call `_tiebreak` (fails **OPEN** to pass,
  `:1020-1021`). `False` → `decision='ignore'`, `goal_id=None` (`:159-160`).
- **Room 1.5 — LIVE DECIDER.** `proactive/decider.py`; **None in stub** (suite stays deterministic),
  constructed only when `provider=openrouter`. `on_event:167-208` awaits `decider.decide(text)` under a
  hard `ANTICIPY_DECISION_WALL_S=6s` wall (`:171`). One temp-0 call → `ACT|ASK|SILENT|UNAVAILABLE`.
  Money is ALWAYS ASK; bias to SILENT (`decider.py:63-126`). **ONE-WAY**: can push ACT→ASK/SILENT,
  **never** ASK→ACT (`decider.py:35-36`, enforced at `proactive.py:220-221`). SILENT kills the event,
  no memory read, no goal, no ask (`:205-208`). UNAVAILABLE is **not a verdict** (transport error /
  empty-after-retries / 6s timeout) → bounded defer-then-retry, then **fail SILENT** — an unread line
  NEVER acts (ledger F7; `:179-203`).
- **Room 2 — HARM-LINE (FINAL on binding/detrimental).** `on_event:215` →
  `proactive/harm.py::HarmLine.assess` (`:281-354`), deterministic, after reading memory (`:210-212`).
  Ordered policy: (1) HARD money/destroy/public/signup/auth_wall override-all (`:286-299`); (2) HARD
  SEND → `_assess_send` with reminder/draft scope carve-outs (`:300-306`); (2b) `_DELEGATED_SEND`
  always binding-send ASK (`:312-314`); (3) reminder/calendar hold → reversible `calendar_hold` ACT,
  re-gated when it fires (`:316-326`); (4) soft send → `_assess_send` (`:333-334`); (5) draft/prepare
  → reversible ACT, memory-resolved cart/slot booking → ACT (`:336-348`); (6) other `_REVERSIBLE`
  → ACT (`:350-352`); (7) unclassified → **fail-safe ASK**, confidence `unsure` (`:353-354`). The send
  path (`_assess_send:376-398`) has a **MONEY INTERLOCK** that forces category `money` **before** any
  casual downgrade (`:385-388`); the casual→ACT downgrade fires only if memory not-abstaining AND
  `top_relevance >= 0.66` AND a casual word is in the **action text** (`_recipient_casual:400-408`),
  else binding-send fail-safe ASK with `memory_forced=True`.
- **Room 3/4 — DECISION ASSEMBLY** (`on_event:217-289`). `forced_ask = decider==ASK and not detrimental`
  (`:221`, the only way the live decider escalates a harm-safe line to ask).
  `terminal_block = _never_execute_category(category, action)` (`:224`;
  `NEVER_EXECUTE_CATEGORIES={'money'}` at `:53`). Not-detrimental & not-forced-ask → `start_goal`
  (executes; planner may pause → ask) → `decision='act'`. Else → persist a PAUSED
  (`GoalState.waiting`) goal that is NEVER executed → `suppressed` / `held` (money waits one breath for
  retraction, `on_event:137-153` kills it silently) / `blocked` (money: `_block_goal`, failed, refusal
  receipt, no pending approval, no steps) / `ask` + `_send_ask` (durable pending ask; round-trip
  `resolve_ask:500-533` re-checks `_never_execute_category` so a stale approval can't make money
  executable after restart). HARD SUB-GATE `:283-284` asserts any ask/held/suppressed goal stays
  `GoalState.waiting`.

`control_core._spine_card` then maps `out['decision']` to a card disposition: `act→'do'`, `ask`/`held`
or any `ask_id` → `'ask'` (`control_core.py:889-909`). The regex classifier (`owner_mode.card_for_line`)
only **shapes** the card (title/route/args) and adds silent memory; the spine is the sole authority
(F17 "one brain", docstring `:828-836`). `owner_ingest` ranks cards (ask/blocked=3, do=2, remember=1)
and translates the winner outward (`blocked→'ask'` display, `remember→'remember'`, no card → silence;
`:622-645`).

### The 6 autonomy modes — a label layered on the finished decision (`autonomy.py:24-46`)

`MODES = (AUTO_DO, AUTO_DO_WITH_OPT_OUT, PREPARE_THEN_STOP, CLARIFY_FIRST, REMEMBER_ONLY, IGNORE)`
(`autonomy.py:13-14`; runtime-confirmed: len 6, exact order). `classify_autonomy(card)` is a **pure,
stateless, no-model** function of three already-decided fields (`disposition`, `action`,
`execution.decision`, read at `:26-28`), returning `{mode, why, rejected:[every other mode]}` (`:46`).
Strict if/elif precedence (all branches reproduced in stub this session):

| # | Condition (`autonomy.py`) | Mode |
|---|---|---|
| 1 | `disp=="remember"` (`:30`) | `REMEMBER_ONLY` |
| 2 | `disp=="blocked"` (`:32`) | `PREPARE_THEN_STOP` (money/checkout wall) |
| 3 | `action=="draft_or_confirm_message"` (`:34`) | `PREPARE_THEN_STOP` (external send) |
| 4 | `action=="browser_action"` (`:36`) | `AUTO_DO_WITH_OPT_OUT` |
| 5 | `disp=="do" OR execd=="act"` (`:38`) | `AUTO_DO` |
| 6 | `disp=="ask" and action=="ask_clarifying_question"` (`:40`) | `CLARIFY_FIRST` |
| 7 | `disp=="ask"` (any other) (`:42`) | `CLARIFY_FIRST` |
| 8 | else (`:44`) | `IGNORE` |

Note the precedence trap: **action branches outrank disposition branches.** A
`draft_or_confirm_message` card shaped with `disposition='ask'` (`owner_mode.py:461-463`) classifies
`PREPARE_THEN_STOP`, not `CLARIFY_FIRST` (verified). Attachment: `control_core.py:1222` (import),
`:1247-1260` loop, `c["autonomy_mode"]=a["mode"]` (`:1250`), full proof row (input_span, chosen_mode,
why, rejected_modes, action_plan, result, proof) → `out["middle_trace"]["autonomy"]` (`:1260`).

---

## The safety floors (vent, money, no-self-attestation) — proven?

All three are enforced **in depth** (multiple independent layers) and the enforcement is **upstream of
and independent from** `classify_autonomy`. The deterministic predicates were verified live in stub;
the full end-to-end breach count was not re-run (throttle — see GAPS).

### 1. Vent floor (cardinal sin: never act OR ask on a vent) — ENFORCED IN DEPTH

- **Source of truth:** `review_infer.is_vent` (`live_memory/review_infer.py:186`) = superset of
  `is_vent_shape` (`:171`), adding `_TRAILING_HEDGE` + `_COUNTERMAND`.
- **Owner path, runs FIRST:** `owner_mode._card_for_line` CARDINAL-SIN GUARD `:374-394` —
  `is_vent(text) and not cart_no_purchase: return None`.
- **Persist defense-in-depth:** `control_core._persist_card:1263`, guard `:1282` refuses a `remember`
  card that `is_vent_shape` → treated as ignored.
- **Spine utterance-absolute layer:** `triage` unified vent guard (`triage.py:882-886`) +
  `_VENT_OPENER/_VENT_CLOSER` (`:170-207`) catch a vent **bracketing a command** that the bare
  `is_vent` misses — verified this session: `is_vent("I give up, just send the report") == False`, but
  the spine's triage opener/closer silences it. **This is load-bearing**: the regex shaper path would
  NOT silence that shape alone; the spine (the active decision-maker, F17) is the floor that catches it.

### 2. Money hard stop (Law 3: money is the only permanent wall) — ENFORCED 3× IN DEPTH

- **(a)** `harm._HARD` top-of-assess override-all (`harm.py:113`, `:286-299`) → ASK/BLOCK.
- **(b)** MONEY INTERLOCK inside `_assess_send` (`:385-388`) fires **before** the casual downgrade —
  a casual-recipient memory match can never turn a payment into a casual_send ACT (verified:
  `"Send Priya the five hundred we owe her" -> money`).
- **(c)** `NEVER_EXECUTE_CATEGORIES={'money'}` (`proactive.py:53`) → terminal `blocked`
  (`_block_goal`, `GoalState.failed`, no pending approval, no executable steps); `resolve_ask:511-515`
  and `_flush_held:398-410` **re-run** `_never_execute_category` so a stale/restarted approval can
  never make money executable.
- **Owner path mirror:** `owner_mode._has_money_signal` (`:303-319`, lazy-imports harm's signal, fails
  **CLOSED** to a local verb regex) + MONEY INTERLOCK (`:424-452`) routes money to a blocked card
  (`payment_allowed=False`) before person/send/browser branches.

### 3. No-self-attestation (never "done"/act without read-back proof) — ENFORCED, runs BEFORE the label

`control_core.py:1236-1246`: any card with `execution.decision=='act'` and **empty proof** is
force-downgraded to `disposition='ask'` / `decision='ask'` / `status='open'`. Scoped to act-claiming
cards only (`:1240`) so a proof-less held/vent card is untouched (flipping it would make a vent produce
an ask — a cardinal breach). Because this runs at `:1236-1246`, **before** the autonomy loop at
`:1247-1260`, an unproven act can never be labeled `AUTO_DO`.

**Adversarial gate:** `engine/scripts/safety_mega_eval.py` — 157-line corpus (84 vent-family, 42 money,
8 commit, 5 commit_ask, 8 prompt, 8 noise, 1 aside, 1 decider_tier) run through proactive spine +
press-go infer/map/whitelist dryrun + `/owner/ingest` split path with `execute_actions=True`. Bar is
**ZERO breaches**. Receipts report 0 across multiple dated runs (`docs/agent_os/RECEIPTS.md:13,24,61,81,92,118`),
wired into `run_suite.sh`. **Not re-run this session** (model-calling, throttled).

---

## Working together

- The four pieces compose as **one authority + three guards + two annotators**. The spine
  (`on_event`) is the only thing that decides act/ask/silent. The vent, money, and no-self-attestation
  floors are guards that run **inside or upstream of** the spine/ingest and can only push toward safety.
  `classify_autonomy` and `plan_follow_up` are **annotators** that run after the decision is final and
  change nothing.
- The decision is **monotonic toward safety**: triage can only DROP, the decider can only push
  ACT→ASK/SILENT, the harm-line is FINAL on binding/detrimental, and the no-self-attestation downgrade
  only flips act→ask. No layer loosens a downstream verdict.
- Deafness is never silence-that-acts: a decider non-read fails SILENT; the triage live tiebreak fails
  OPEN to pass — opposite directions, both safe because the harm-line still gates anything passed.
- The vent definition is shared across the proactive path, the owner regex shaper, the persist guard,
  and `press_go.py` — one definition, but the **only** layer that catches a vent-bracketed-command is
  the spine's triage; the regex/press-go paths rely on the narrower `is_vent` and would miss it alone.
- The autonomy modes ride out on `card["autonomy_mode"]` + `middle_trace.autonomy`; the **only**
  consumer is the certification harness (`cert_harness.py:177,208-210`) — verified by grep: the string
  is written at `control_core.py:1250` and read only by cert. There is no UI/API/executor path that
  branches behavior on the mode.

---

## PROVEN

These were verified this session by code-read + fast deterministic stub runs (no model):

- **6 modes, exact order** (`autonomy.py:13-14`): runtime `len==6`, tuple, exact values/order.
- **`classify_autonomy` is pure/deterministic/stateless, no model** (`autonomy.py:24-46`): all 8
  branches reproduced; `rejected` is exactly the other 5 modes; same input → same output.
- **Precedence trap** (action outranks disposition): `{disposition:'ask',action:'draft_or_confirm_message'} -> PREPARE_THEN_STOP` (stub).
- **Allow-list gap, not a live breach but a real reporting hole**: an unlisted dangerous action that
  reaches `disposition='do'` is labeled the most-autonomous mode —
  `{disposition:'do',action:'make_purchase'} -> AUTO_DO` (stub). Harmless only because the label gates
  nothing; it would falsely **report** a money/send card as `AUTO_DO`.
- **`_AUTO_ACTIONS` is dead code** (`autonomy.py:16-21`): repo grep returns ONLY the definition site
  (`:17`); `classify_autonomy` never consults it. The intended autonomy-scope allow-list was never wired.
- **`autonomy_mode` is never read for gating**: grep shows it written at `control_core.py:1250` and
  read only by `cert_harness.py:177,208-210` (a non-blocking `noncritical` mode-match assertion).
- **No-self-attestation downgrade runs before classification** (`control_core.py:1236-1246` precedes
  `:1247-1260`), scoped to `decision=='act'` only.
- **Harm-line money + send interlock** (verified live in stub via the maps): money signal forces
  category `money` before any casual downgrade; binding-send with abstaining memory → ASK
  `memory_forced=True`; unclassified → fail-safe ASK `unsure`; delegated send → binding ASK.
- **Vent floor catches the bracketed-command case at the spine** (verified): `is_vent` returns False
  on `"I give up, just send the report"` but triage's opener/closer silences it.
- **`plan_follow_up` is pure/deterministic** (`follow_up.py:30-46`): vents (`ignore`), prefs
  (`remember`), money (`blocked`) → `None`; external-dependency actions / `_AWAIT` verbs → 2-day plan
  (`when_ts = now + 2*86400`); internal-only actions → `None`. Attached at `control_core.py:1222-1231`.

## GAPS

- **Mega-eval not re-run (BREACHES=0 is from RECEIPTS, not re-proven this session).** The deterministic
  predicates agree with documented behavior, but the full proactive + press-go + ingest-split breach
  count was not re-derived (model-calling, throttled).
- **Live decider / triage tiebreak / forced_ask escalation not exercised end-to-end.** Wiring verified
  by code-read only (`proactive.py:167-221`, `triage.py:985-1024`); behavior under a real model reply
  is asserted from docstrings/ledger, not run.
- **`on_event` itself not run** (awaits orchestrator/bus/memory workers). The act/ask/held/blocked/
  suppressed branch outcomes are mapped from code-read; harm-line and triage were exercised only as
  isolated pure functions.
- **No dedicated unit tests** for `classify_autonomy` or `plan_follow_up` (grep of `engine/tests` /
  `engine/scripts/test_*.py` for "autonomy"/"plan_follow_up" returns nothing). Coverage exists only via
  the throttled, model-calling cert harness; branch behavior here is from direct invocation of the pure
  functions, not the project's own suite.
- **The autonomy label is only correct if the upstream card fields are correct.** The LABEL mapping was
  verified deterministically, but the full spine pipeline that SETS `disposition/action/execution.decision`
  (e.g. that a real browser line actually arrives with `action='browser_action'`) was read, not executed.
- **Follow-up is computed and displayed but NEVER FIRED.** `TriggerWatcher`
  (`proactive/trigger.py:30-54`) fires only on loop-ledger `remind_ts/due_ts/created_ts`; grep confirms
  `follow_up` appears nowhere in `trigger.py` or `engine.py`. No code converts `follow_up.when_ts` into
  a scheduled nudge — contradicting the docstring at `follow_up.py:5-6`.
- **Follow-up UI mismatch + fixed delay.** `app/page.js:332` keys "Worth a follow-up." on
  `action==='follow_up'` (a card-action literal), NOT the attached `follow_up` plan dict — the computed
  plan has no found render site. Delay is a hard-coded 2 days (`_DEFAULT_DELAY_DAYS`), ignoring the
  card's own stated deadline; `now_ts` is a fresh `time.time()` per ingest, so re-ingesting yields a
  different `when_ts` and nothing dedupes follow-ups.
- **Follow-up over-trigger surface.** Exclusions key only on disposition; `_AWAIT` matches bare verbs
  (`order`, `return`, `reply`, `confirm`) in `source_text`, so a `do`/`ask` card merely mentioning such
  a verb gets a follow-up. The cert harness checks only the happy path.
- **`press_go.py` is a third `harm.assess` consumer** (a separate app/memory path) that keys off the
  harm CATEGORY, not the broad `detrimental` flag; whether its interpretation stays in lockstep with the
  spine over time was grepped, not fully traced. The `aside` class is a softer floor than vent/money (it
  may legitimately whitelist after approval).

---

## Honest verdict

**The judgment system is real and the safety floors are genuinely enforced in code — but the "6
autonomy modes" are not a safety mechanism, and follow-up is not wired to fire.**

The act/ask/silent authority is the proactive spine, and it is well-built: three one-way rooms that can
only move toward safety, with money enforced three times in depth (the only permanent wall), the vent
cardinal-sin guarded utterance-absolute before any positive judgment, and a no-self-attestation
downgrade that runs before any "done" label so AUTO_DO can never assert an unproven act. Those floors
are code-enforced, not prompted, and the deterministic predicates behind them verify clean.

The autonomy modes are honest but oversold: `classify_autonomy` is a pure, post-hoc **relabeler** of an
already-finished decision, read only by the certification harness, gating nothing. The "6 modes
constrain autonomy" framing fails the "enforced not prompted" bar — the framing is reporting, not
protection. Two concrete smells confirm it: `_AUTO_ACTIONS` (the intended safe-action allow-list) is
dead code never wired into the AUTO_DO branch, so a `do`-card with **any** action string (including
`make_purchase`) is labeled `AUTO_DO`; this is harmless today only because the mode gates nothing, but
it would become a real over-action hole the moment any code trusts `autonomy_mode==AUTO_DO` as
act-authorization.

Follow-up is the clearest unfinished edge: a correct, deterministic 2-day plan is computed and stamped
on every external-dependency card, but no trigger ever reads it and the one UI label keys on a different
concept — so the "I'll check back and nudge" promise is currently computed and silent.

Net: the dangerous decisions (act/ask/silent, vent, money, proof) are guarded for real; the autonomy
modes and follow-up are descriptive scaffolding that should be either wired in or labeled as
non-load-bearing so no future reader mistakes the mode for a gate. Subject to the throttle caveat — the
model-driven end-to-end gate (mega-eval, live decider, cert harness) was not re-run this session.
