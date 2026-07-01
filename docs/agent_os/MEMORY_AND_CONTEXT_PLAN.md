# MEMORY & CONTEXT ENGINEERING — the detailed plan (always-listening proactive device)

> Standing design doc. Research + architecture + micro-plans + loops + sub-agents + done-gates.
> Read `SYSTEM_SPINE.md` first. This is the next phase after browser (product-done) and proactive
> (wired). It is the phase that makes the whole system *flow* instead of sit as parallel pipes.

---

## 0. Why this is the hard part (plain words)

An always-listening device hears a person's whole messy day. **>99% of what it hears is noise,
vents, jokes, other people talking, the TV.** The value is the tiny fraction that matters, and the
*unspoken* task hidden inside a run-on sentence. Memory is what lets the device (a) not drown in
noise, (b) *anticipate* instead of react, and (c) get smarter about YOU every day. Context
engineering is the discipline of putting **exactly the right slice** of that memory in front of the
model at the moment it decides or acts — no more (cost/latency/hallucination), no less (dropped
ball). Get this wrong on an always-on device and you get either a spammy device that acts on vents,
or a forgetful one that never anticipates. Both kill the product.

Two different disciplines, often conflated:
- **Memory engineering** = what we *store*, how it's *typed*, how it's *updated/forgotten*, how
  it's *retrieved*. (The database + the librarian.)
- **Context engineering** = what we actually *put in the model's context window* for a given
  decision/action, assembled from memory + the live moment. (The one who packs the briefcase.)

---

## 1. What the field knows (grounded research)

**The four memory types (standard cognitive-agent taxonomy) and how Anticipy already maps them:**

| Type | What it is | Anticipy drawer (exists today) |
|------|-----------|--------------------------------|
| Working / short-term | the current context window; the task at hand | `open_loops` ledger + the assembled context string |
| Episodic | timestamped events that happened | `history` (embedded append-log) |
| Semantic | durable facts about the world/user | `profile` (stated facts, confidence 1.0) |
| Procedural | learned how-to sequences | browser `recipes` (~$0 replay) |
| Inferred (derived) | patterns/routines guessed w/ confidence | `derived` (never promoted past 1.0) |

**Reference systems (what to borrow, what to skip):**
- **Stanford "Generative Agents" (2023)** — retrieval = weighted `relevance + recency + importance`,
  plus periodic *reflection* that turns many episodes into higher-level insights. → Our `inject.py`
  scoring (`0.55·sem + 0.30·kw + 0.10·recency + 0.05·importance`) IS this function. Our `infer.py`
  is a shallow version of reflection. **Borrow: deepen reflection.**
- **MemGPT / Letta (2023-24)** — treat the context window like RAM and external store like disk;
  the agent *self-edits* memory and pages relevant blocks in/out under a token budget. → **Borrow:
  the token-budgeted "context = RAM" discipline** for our single context builder. Skip the heavy
  OS metaphor.
- **Mem0 (2024)** — extraction pipeline that, per new input, decides `ADD / UPDATE / DELETE / NOOP`
  against existing facts (dedupe + contradiction handling as first-class ops). → **Borrow: the
  add/update/delete decision** — our capture currently mostly appends; supersede is newest-wins on
  3 subjects only. This is our biggest gap.
- **Zep / Graphiti (2024)** — a *temporal knowledge graph*: facts are edges with `valid_from` /
  `valid_to`; a new fact *invalidates* the old one at a time boundary instead of deleting it. → **Borrow:
  bi-temporal validity** ("pickup moved to 3 *today*" is valid only today; "works at X" until it
  doesn't). This directly fixes always-on temporal chaos.
- **Context engineering discipline (Anthropic / LangChain framing, 2024-25)** — four moves on the
  context window: **Write** (persist to memory/scratchpad), **Select** (retrieve the right bits),
  **Compress** (summarize when it won't fit), **Isolate** (give sub-agents their own scoped
  context). → **This is the skeleton of our single context builder (§4).**
- **RAG evolution** — naive → hybrid (semantic+keyword, we have it) → **rerank** (we don't) →
  agentic/hierarchical retrieval (we don't). → **Borrow: a cheap rerank pass + hierarchical
  (daily-digest → drill-down) retrieval** to scale to always-on volume.

---

## 2. The hard problems UNIQUE to an always-listening device (and our answer to each)

1. **Signal-to-noise (the firehose).** Hours of transcript/day, >99% worthless.
   → **Salience gate at capture** (cheap/local first): most lines never become durable memory;
   they live in a short rolling raw buffer that auto-expires. Only salient lines get embedded/stored.
   *We must not embed everything — cost and recall both die if we do.*
2. **Privacy, consent & bystanders.** It records other people, health, finances, kids.
   → **Privacy is a first-class layer, not an afterthought:** PII/sensitive tagging at capture,
   configurable retention windows, hard "never store" categories, redaction before anything leaves
   the device, local-first storage, and a real right-to-delete. Two-party-consent reality must be a
   product setting, not a legal surprise. **This is a design pillar, gated like the money-stop.**
3. **Speaker & provenance.** Who said it — Omar, a third party, the TV? A task Omar *committed to*
   vs one *said to him* vs *overheard*.
   → **Every captured line carries `speaker` + `provenance` + `addressed_to`.** The decider already
   cares (a task voiced to another person is `ask`); memory must preserve it so the decision is right.
4. **Temporal validity (facts rot).** "Pickup is at 3 *today*." "I work at X" (until a new job).
   → **Bi-temporal facts** (`valid_from`/`valid_to`, `event_time` vs `ingest_time`); new facts
   invalidate old ones at a boundary instead of silently overwriting. Ephemeral facts auto-expire.
5. **Contradiction & self-correction.** People misspeak and correct themselves mid-sentence.
   → **ADD/UPDATE/DELETE reconciliation at capture** (Mem0-style) + supersede with provenance, so
   the newest *stated* fact wins but the trail is auditable.
6. **Volume → compression.** Can't keep every episode hot forever.
   → **Tiered memory + nightly consolidation:** raw buffer (hours) → episodic (days, embedded) →
   daily digest (weeks, summarized) → semantic facts + derived routines (durable). Reflection runs
   in the cold loop.
7. **Vents must never become commitments (the cardinal sin).** An emotional line can look like a task.
   → **Vent-shape gate on the write path AND the read path** (already partially in `inject.py`'s
   `is_vent_shape`); a vent is stored as episodic *feeling*, NEVER as an `open_loop` commitment.
8. **Latency + cost at decision time.** The proactive decision must be cheap and fast, yet complete.
   → **Two-speed context:** a tight, always-complete context for the *decider* (all open loops +
   top-k relevant, cheap model); a richer, drill-down context for the *hands* when executing.
9. **Never fabricate a fact.** → **Abstain floor** (already in `inject.py`): below a calibrated
   semantic-confidence floor, say "I don't know" instead of inventing. Keep and extend it.
10. **Identity resolution across days.** Same "Sarah" / same "the deck" across sessions.
    → **Entity + open-loop linking** in consolidation (dedupe by capture_key + entity match).

---

## 3. Current state (honest inventory — measured by reading the code)

**Real and working (deterministic stub path, no model needed):**
- 4 drawers in SQLite + local cosine vector scan (`memory/store.py`).
- Hybrid retrieval + dedupe + char-budget assembly + abstain floor (`live_memory/inject.py`).
- Recall self-check → scorecard (`selfcheck.py`): completeness (all open loops surfaced) + relevance.
- Cold sweep: supersede / consolidate / decay (`maintain.py`).
- Shallow reflection: routines / recurring people as derived facts (`infer.py`).
- Open-loops = deterministic commitment ledger, always fully surfaced (never drops a ball).

**The gaps (this phase closes them):**
- **G1 — one shared context builder is missing.** `inject.py` returns a flat char-budgeted string;
  the decider and the hands don't provably share ONE assembled context. (This is the "plumbed
  separately" risk you named.)
- **G2 — capture mostly appends.** No first-class ADD/UPDATE/DELETE reconciliation (Mem0) → dupes,
  stale facts, weak contradiction handling beyond 3 hard-coded subjects.
- **G3 — no temporal validity.** `valid_from/valid_to` absent; "today only" facts live forever.
- **G4 — no salience gate / tiering at capture.** Everything trends toward being stored; won't
  scale to true always-on volume.
- **G5 — privacy layer is implicit.** PII/sensitivity tagging, retention windows, redaction, and
  right-to-delete are not first-class.
- **G6 — the live-model seams are all TODO/stub.** Reranking, relevance judging, richer reflection
  are stubbed (`pass  # TODO(live)`). Quality is capped by deterministic heuristics.
- **G7 — retrieval is a full cosine scan, single pass.** Fine now; no rerank, no hierarchical
  drill-down for scale.

---

## 4. The target design: ONE context builder (the anti-"separate plumbing" core)

A single module — **`live_memory/context_builder.py`** — is the ONLY thing that assembles a model
context anywhere in the system (decider, hands, voice). It implements the four context-engineering
moves and returns a typed `ContextPack`, not a raw string.

```
build_context(moment, purpose) -> ContextPack:
  # purpose ∈ {decide, act, speak}; each gets a different budget + shape, SAME source of truth.
  SELECT   : open_loops (ALL active, always) + hybrid-retrieve top-k over profile/history/derived
  RERANK   : cheap cross-check of the k candidates vs the moment (live model seam; heuristic in stub)
  COMPRESS : if over budget, summarize episodics into a digest line (never drop an open loop)
  ISOLATE  : purpose-scoped view — decider gets tight+complete; hands get drill-down; voice gets facts
  WRITE-BACK hook: the outcome of the decision/action is handed back to capture (closes the loop)
  returns ContextPack{ open_loops, facts, episodic_digest, derived, provenance, abstain, budget_used }
```

Rules baked in: open loops are never dropped; vents never appear as commitments; below the abstain
floor it returns `abstain=True`; every item keeps provenance + speaker + validity so the decider can
apply the harm-line correctly. **Because all three consumers call this one builder, memory /
decision / action provably share one context — that is what makes it flow, not plumb.**

---

## 5. THE LOOPS (memory is loops, not a pipe)

1. **HOT capture loop (per line, milliseconds, local/cheap):** salience gate → tag
   (speaker/provenance/PII/vent) → raw buffer; if salient, extract → ADD/UPDATE/DELETE reconcile →
   write to the right drawer with validity. *No smart model on the hot path.*
2. **HOT read loop (per decision/action):** `context_builder.build_context(moment, purpose)` →
   decider/hands → self-check audit → scorecard. Fast, cheap, complete.
3. **WARM write-back loop (per completed action):** action outcome + receipt → capture → memory, so
   the next decision is better and the browser recipe is learned. Closes the flywheel.
4. **COLD consolidation loop (idle / nightly, bigger model OK):** dedupe/consolidate episodes →
   daily digest → reflection (routines, preferences, recurring people, standing prefs) → supersede
   stale/contradicted facts → expire ephemeral + apply retention/privacy windows → decay clutter.
5. **EVAL loop (every build lap):** recall precision/recall + completeness + abstain-calibration +
   "learned-fact-changes-later-action" real-day test → scorecard. **No lap is done without this.**

---

## 6. SUB-AGENTS (each with a contradictor + a failable check — per the Laws)

Each sub-agent is a scoped model call the loops USE; none is the loop. All are stub-deterministic by
default and escalate to a model only behind the live flag. Each ships with an adversarial check.

| Sub-agent | Job | Contradictor / failable check |
|-----------|-----|-------------------------------|
| **Salience gate** | is this line worth keeping? | planted-noise set must score ~0 kept; planted weak-signal task must be kept (recall on held-out lines) |
| **Extractor** | line → structured fact/loop (+speaker, provenance, validity) | vent-shaped lines must NEVER produce an open_loop (safety_mega_eval = 0 breaches) |
| **Reconciler (ADD/UPDATE/DELETE)** | merge vs existing memory | contradiction set: newer fact must supersede older; no silent dupes; delete only on explicit correction |
| **Reranker** | order the k candidates for the moment | must not demote a ground-truth expected item below budget (recall@k held) |
| **Reflector** | episodes → routines/preferences (derived only) | derived facts stay confidence < 1.0, never promoted; a planted-false pattern must not become a fact |
| **Privacy/redactor** | tag PII/sensitive, apply retention, redact before egress | "never-store" categories must be absent from durable store; right-to-delete removes all traces |
| **Relevance judge (self-check)** | is the pack relevant+complete? | completeness: every active open loop present; recall logged to scorecard |

Contradiction discipline: the reflector/reconciler outputs are checked by a *different-family*
verifier before anything durable is written, and holdout personas the builder can't read guard
against overfit — same regime the factory already enforces.

---

## 7. PHASED MICRO-PLAN (each micro-step: change → test that can FAIL → done-gate)

> Order is by leverage. Nothing is "done" without its attached, reproducible measurement.
> Every micro-step runs through the whole spine on a real day, not in isolation.

> **STATUS (2026-06-28) — M0→M7 ALL GREEN.** Every gate is a reproducible test in the suite
> (`bash scripts/run_suite.sh`) that can FAIL:
> - M0 baseline harness · M1 `test_memctx_contextpack.py` (one builder, three consumers)
> - M2 `test_memctx_reconcile.py` · M3 `test_memctx_temporal.py` · M4 `test_memctx_salience.py`
> - M5 `test_memctx_privacy.py` (never-store masked at source, redact-before-egress, right-to-delete)
> - M6 `test_memctx_rerank.py` (moment-aware rerank + recall-guard contradictor; reflection
>   contradictor rejects re-ingest fakes & vents)
> - M7 `test_memctx_flywheel.py` (day-1 fact reaches decide+act+speak on day 3, CHANGES the action
>   vs a counterfactual, no ephemeral leak, judge honors it, post-action write-back recalled).
> Frontend seam live: `GET /memory/context?about=&purpose=decide|act|speak` (the ONE pack every
> consumer reads) + `POST /memory/forget-me` (default-deny right-to-delete). Suite: 107 passed,
> 12 pre-existing unrelated failures (owner-mode / next-server), zero regressions from M5–M7.

**M0 — Instrument the baseline (measure before touching).**
- Build/extend a memory eval harness: a labeled real-day set (messy transcript → expected
  facts/loops/retrievals). Report recall, precision, completeness, abstain-calibration, $/decision.
- *Failable check:* the harness runs green and prints today's numbers. *Done-gate:* baseline numbers
  written to scorecard so every later step is measured against them.

**M1 — The single ContextPack builder (closes G1, the anti-plumbing core).**
- Add `context_builder.py` returning a typed `ContextPack`; route decider + hands + voice through it.
- *Failable check:* decider and hands assert-share one pack (integration test); no regression in
  recall/completeness; safety_mega_eval = 0. *Done-gate:* one builder, three consumers, measured.

**M2 — Capture reconciliation ADD/UPDATE/DELETE (closes G2).**
- Replace append-mostly with a reconcile step against existing memory (Mem0-style), keyed by
  capture_key + entity.
- *Failable check:* contradiction set — re-ingesting "works at X" then "works at Y" yields ONE active
  fact (Y), X superseded with trail; dupes collapse. *Done-gate:* dedupe/contradiction metrics up.

**M3 — Bi-temporal validity (closes G3).**
- Add `valid_from`/`valid_to`, `event_time`; ephemeral facts ("today") auto-expire; retrieval
  filters by validity at the moment.
- *Failable check:* "pickup moved to 3 today" is NOT surfaced tomorrow; "works at X" surfaces until
  invalidated. *Done-gate:* temporal test green on a two-day real-day.

**M4 — Salience gate + tiered memory (closes G4, the always-on scale problem).**
- Cheap/local salience gate on the hot path; raw buffer (hours) → episodic (days) → digest (weeks) →
  durable. Stop embedding noise.
- *Failable check:* on an hour-long noisy transcript, durable-store growth is bounded and weak-signal
  tasks are still caught (recall held while volume stored drops sharply). *Done-gate:* volume↓, recall≈.

**M5 — Privacy layer (closes G5, gated like the money-stop).**
- PII/sensitivity tagging, "never-store" categories, retention windows, redaction-before-egress,
  right-to-delete.
- *Failable check:* never-store categories absent from durable store; delete-user wipes all traces;
  no raw sensitive text leaves the device. *Done-gate:* privacy eval = 0 leaks (independent re-run).

**M6 — Light-up the live seams: rerank + relevance judge + richer reflection (closes G6/G7).**
- Turn the `pass # TODO(live)` seams into cheap-model calls behind the flag, each with its
  contradictor; add a cheap rerank pass and hierarchical (digest→drill-down) retrieval.
- *Failable check:* recall/precision up vs M0 baseline at bounded $/decision; reflection produces a
  real routine that is judge-verified true, not a hallucinated pattern. *Done-gate:* quality↑, cost bounded.

**M7 — Prove the flywheel end-to-end (the whole-loop done-gate).**
- *Failable check (the one that matters):* a fact learned on **day 1** demonstrably changes an
  **action on day 3**, judge-verified on a real day the builder never saw — with the write-back loop
  closing after the action. *Done-gate:* this passes; recall/precision/privacy metrics all hold.

---

## 8. Metrics (the scoreboard for this phase)

- **Recall** (expected facts/loops surfaced), **Precision** (junk kept out), **Completeness**
  (every active open loop present — must be ~100%).
- **Abstain calibration** (says "don't know" when it should; doesn't over-abstain).
- **Volume stored vs heard** (salience working — should be a tiny fraction on always-on input).
- **$/decision and latency** on the hot path (must stay cheap/fast).
- **Safety:** vent→commitment breaches = 0; privacy leaks = 0 (both independently re-run).
- **The flywheel metric:** learned-fact → later-action change rate, judge-verified.

## 9. Risks / where this can go wrong
- Over-storing (kills recall + cost) → salience gate + tiering (M4) is non-negotiable.
- Over-forgetting (drops a ball) → open loops are NEVER decayed; only episodic/derived decay.
- Hallucinated facts/routines → abstain floor + derived-never-promoted + different-family verifier.
- Privacy as an afterthought → M5 gated like money-stop, designed in, not bolted on.
- "Plumbed separately" regression → the single ContextPack builder (M1) is the structural guard;
  the done-gate is always the whole-loop real-day test, never a unit test.
