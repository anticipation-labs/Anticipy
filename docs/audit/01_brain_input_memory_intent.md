# Audit 01 — The Understanding Brain (input routes · the moat · memory/intent · dedup)

> Pillar: how Anticipy *understands* a person's messy day — every input route, the model
> inference moat, the durable memory + intent layer, and the anti-spam dedup. Grounded in
> file:line reads of `engine/anticipy_engine/`, fast deterministic (stub) test runs, and
> static AST/grep checks. The OpenRouter model path was NOT exercised live (throttled
> ~22s/call), so the model's *judgment quality* is read-verified, not runtime-verified — this
> is called out explicitly in GAPS. Date: 2026-06-17.

---

## What it is

The understanding brain is the product. It takes a person's loose spoken/typed day and infers
the right set of confirm-first / act candidates while **never acting on a vent** (the cardinal
sin) and **never dropping a real task that sat next to a vent**. It is built from four
cooperating parts:

1. **Input routes** — typed transcript, MP3/audio upload, and always-on mic — that all
   converge on a single brain entrypoint, `ControlCore.owner_ingest`.
2. **The moat** — a temperature-0 cheap-model call per line that splits a line into its real
   tasks and judges the whole breath vent-or-not, with deterministic fail-safes underneath.
3. **Memory + intent** — a durable SQLite memory (five organs, four drawers + an inert
   remember-list) and a pure-Python intent layer that resolves vague references ("that desk
   thing") against ranked prior lines.
4. **Dedup** — two layers that enforce Omar's #1 rule: *one real obligation = one card*.

---

## How it works (file:line)

### Input routes — three doors, one brain

All three owner inputs land on `ControlCore.owner_ingest`
(`engine/anticipy_engine/core/control_core.py:1027`), which wraps `_owner_ingest_inner`
(`control_core.py:1117`). The doors differ only in how they turn their input into plain text:

- **ROUTE 1 — typed transcript.** `POST /owner/ingest` (`engine/anticipy_engine/main.py:719-722`)
  body is exactly `return await core.owner_ingest(body.source, body.text, body.meta,
  execute_actions=body.execute_actions)`. Schema `OwnerIngestIn` defaults `source="transcript"`
  (`main.py:319-323`).
- **ROUTE 2 — MP3 / audio upload.** `POST /owner/ingest-file` (`main.py:725-774`) validates the
  path is inside the upload staging area (`main.py:728-729`) and under a size cap
  (`main.py:733-737`), then for audio calls `transcribe_audio(path)` (`main.py:748-750`; real
  local Whisper+ffmpeg, `capture/transcribe.py:32-118`), joins lines into text (`main.py:760`),
  labels `source="audio_upload"` (`main.py:762`); else decodes bytes as text
  (`main.py:763-766`). It cleans up the file in a `finally` (`main.py:767-768`) and ends with
  the **same** call: `return await core.owner_ingest(source, text, meta, ...)` (`main.py:774`).
  Transcription failure raises HTTP 422 and never reaches the brain (`main.py:751-759`).
- **ROUTE 3 — always-on mic.** `POST /listen/start` (`main.py:778-803`) installs a `_sink`
  callback (`main.py:788-795`) on `MacMicSource` (`main.py:797-799`). Per heard non-noise
  window the sink logs `mic_heard` then bounces onto the engine loop:
  `asyncio.run_coroutine_threadsafe(core.owner_ingest(event.source, event.text,
  {"capture":"mac_mic"}, execute_actions=True), loop)` (`main.py:791-793`). A sink exception is
  swallowed as `mic_sink_error` so the mic loop survives (`main.py:794-795`).

### The one pipeline (`_owner_ingest_inner`, `control_core.py:1117-1129`)

The order is fixed and unconditional for every source (verified read):

1. `raw_observed = self.owner_mode.observe(text)` — split the breath (`control_core.py:1118`;
   `observe` takes only `text`, source-agnostic, `owner_mode.py:333-335`).
2. `observed = await self._expand_tasks_with_model(raw_observed)` — **THE MOAT**
   (`control_core.py:1120`).
3. `observed, trace = self._intent_resolve(observed, raw_lines)` — ranked recall / vague-ref
   resolution (`control_core.py:1121`, def at `:1050`).
4. `observed = self._consolidate_obligations(observed)` — F-012 dedup (`control_core.py:1122`,
   def at `:1089`).
5. Memory capture for every surviving line via `self.live_memory.capturer.capture(line.text,
   source=source, meta={...,"owner_ingest":True,...})` (`control_core.py:1124-1129`).

Only **after** memory+intent does the card-build loop run (`control_core.py:1131+`):
`card_for_line` preview (`:1135`), `_spine_card` on execute (`:1142`), `_apply_force_ask`
downgrade (`:1142+`), browser/timed-reminder cards. `source` is carried onto cards as a label
but the decision logic never branches on which door it came from.

### The moat (`proactive/extract.py` + `_expand_tasks_with_model`)

- `extract(gateway, line, context)` (`extract.py:130`) makes **one** cheap-model OpenRouter
  call at `temperature=0` with a long hand-tuned prompt (`_PROMPT`, `extract.py:30-60`) and
  returns strict JSON `{"tasks":[{task,kind}], "vent":bool}`.
- `_parse` (`extract.py:99`) hardens the reply: parse failure / non-dict / empty →
  `ExtractResult(available=False)` (the fail-safe "model unreadable" signal,
  `extract.py:103/106/110/111`); unknown `kind` → coerced to `"ask"` (`extract.py:121-123`);
  `vent=true` + `act` → forced to `"hold"` (`extract.py:124`).
- `actionable()` (`extract.py:71`) returns act/ask tasks **only on a calm line** (vented →
  `[]`); `vent_adjacent_tasks()` (`extract.py:79`) returns the real tasks pulled out of a vent,
  each coerced to `"ask"`.
- `_expand_tasks_with_model` (`control_core.py:954`): **returns `observed` UNCHANGED unless the
  provider is OpenRouter** (`control_core.py:964`) — so stub/test runs are byte-identical to
  the deterministic path. It keeps a rolling 8-line context (`control_core.py:974`), drops
  interrogative asides via `_is_interrogative_aside` **before** the model (`control_core.py:979`),
  then emits per line: nothing for a pure vent; one `force_ask=True` line per vent-adjacent task
  (`control_core.py:1004`); one `moat_task=True` line per clean actionable task
  (`control_core.py:1022`); or the line unchanged when the model is unavailable
  (`control_core.py:986-988`).
- The two flags drive treatment: `force_ask` is downgraded to a confirm-first ask with
  execution stripped and **the executing spine is never run** (`_spine_card` force_ask branch,
  `control_core.py:842`); `moat_task` is rescued into a confirm-first ask backed by a paused
  goal if the deterministic spine voted SILENT — gated by `decision!='blocked'` **and** not
  `is_vent_shape` **and** `harm category != 'money'` (`control_core.py:922-931`).

### Memory + intent

- **Intent** (`proactive/intent_threads.py`, pure-Python, no model): `classify(text)` →
  vent / preference / followup / action (`:109-117`); `rank_referents` + `resolve_reference`
  score prior threads by head-noun match and rewrite a vague line in place (`:137-208`). A
  winner needs score ≥ 1.0 **and** (lone strong candidate OR top-minus-next gap ≥ 5.0)
  (`:168-178`); otherwise the line is left unchanged for the smallest clarification.
- **Memory** (`live_memory/` over `memory/store.py`): one SQLite db with four drawers
  (profile_fact, open_loop ledger, history, derived) + a separate **inert** `remembered_lines`
  table no firing path can read (`remember.py:1-25`). Capture path
  (`live_memory/capture.py:capture`): generous remember side-write → keep/drop gate →
  classify → **cardinal-sin guard** (a vent-shaped line is refused entry to active drawers,
  `capture.py:179-180`) → dedupe → write. Recall (`live_memory/inject.py`): hybrid score
  `0.55*semantic + 0.30*keyword + 0.10*recency + 0.05*importance` with ALL active loops always
  prepended and a semantic-confidence abstain floor (`inject.py:78-88`, loops at `:64-65`).
- **Durability/self-heal**: SQLite at `.anticipy-data/memory.db`; `integrity_check` on init,
  quarantine corrupt db to `.corrupt-<ts>`, recreate fresh (`store.py:59-66, 83-108`).
  `Maintainer.sweep` supersedes newest facts (employer/name/location), consolidates duplicate
  episodes, decays stale low-importance history, and **never touches the open_loops ledger**
  (`live_memory/maintain.py:30-94`).

### Dedup (two layers, both in `control_core.py`)

- **Layer 1 — semantic obligation consolidation.** `_consolidate_obligations` (`:1089-1115`)
  walks observed lines, computes an object signature via `_obligation_sig` (`:224`), folds any
  line matching an already-kept one via `_same_obligation` (`:259`), keeps the **first**
  wording, and propagates the stricter guard (force_ask/moat_task) on merge. `_obligation_core`
  (`:253`) strips comm verbs/filler so "call Amazon about the monitor" and "handle the Amazon
  monitor issue" both reduce to core `{amazon,monitor}` and collapse to one card.
- **Layer 2 — durable replay dedup.** `_owner_card_dedupe_key` (`:175-188`) = sha256 of
  (normalized source_text | route | action); `_existing_owner_card` (`:1420-1451`) stops a
  double-Go or re-upload from creating a second external action. Exact-text only by design
  (comment `:191-198`); semantic dups are Layer 1's job.

---

## Working together (the seams)

- **Front-door divergence is ONLY transcription/capture, then converge.** MP3 →
  `transcribe_audio` → join lines (`main.py:748-762`); mic → `MacMicSource` → `event.text`
  (`main.py:788-793`); typed → raw `body.text` (`main.py:722`). All three hand plain text +
  source to the identical `core.owner_ingest`.
- **One capture chokepoint.** `live_memory.capturer.capture` is the single write function
  (`capture.py:153`) shared by feed (`control_core.py:607`) and owner_ingest
  (`control_core.py:1125`); `owner_ingest` sets `meta["owner_ingest"]=True` so feed won't
  double-capture (`control_core.py:602-607`). (There are 5 call sites of the function across
  the codebase, but the owner-ingest route uses exactly one.)
- **`execute_actions` differs by route, not by brain.** Typed/file pass `body.execute_actions`
  (default False → preview); mic forces `True` (`main.py:792`). Memory+intent run **before**
  the execute branch (`control_core.py:1124-1129` precede `:1141`), so they fire identically
  for preview and execute. PREVIEW == REALITY is enforced because `_apply_force_ask` runs on
  both paths and inside `_spine_card`.
- **The provider gate is the master switch for the model layer.** `extract` →
  `available=False` unless provider is OpenRouter (`extract.py:140`); `_expand_tasks_with_model`
  → `observed` unchanged unless provider is OpenRouter (`control_core.py:964`). This is the
  seam where the whole moat (and only the moat) switches off for stub/test runs.
- **The two-flag fork routes vent vs clean.** `force_ask` (real task inside a vent) →
  display-only / confirm-first ask, executing spine bypassed; `moat_task` (clean task) →
  rescued executable confirm-first ask. Mutually exclusive per line.
- **Downstream guards still run after the moat.** `_intent_resolve` drops preference lines and
  resolves referents (`control_core.py:1065`); `_consolidate_obligations` merges same-obligation
  lines and propagates the stricter flag (`control_core.py:1104-1110`). The moat is additive
  defense-in-depth, not the only filter.
- **Intent operates on moat-reworded text.** `_intent_resolve` runs after the moat may have
  changed wording, so it robustly excludes the query line by "is itself vague"
  (`intent_threads.py:147-149`) rather than by index self-match.
- **Anti-spam delivery seam.** `owner_ingest` sets `proactive._suppress_ask_delivery=True` so
  in-app asks stay in-app (no SMS flood); time-due reminders via `trigger_tick` still text.

---

## PROVEN (verified — read + fast deterministic runs)

- **MP3 upload transcribes to text then routes into the same brain; the handler builds no
  cards.** `transcribe_audio` is a real Whisper+ffmpeg pipeline (`transcribe.py:32-118`); the
  handler ends with the byte-identical `core.owner_ingest` call (`main.py:774` == `main.py:722`
  semantics); all card construction is downstream (`control_core.py:1131+`). *(VERDICT: TRUE.)*
- **The mic sink feeds heard non-noise utterances into the same brain with execute on.**
  `execute_actions=True` is hardcoded (`main.py:792`); same `core.owner_ingest`. The noise
  filter (`mac_mic.py:42-44`) drops sub-4-char / Whisper-silence stock phrases — a benign
  safety filter. *(VERDICT: mostly-true; "every utterance" is a slight overstatement — it is
  every non-noise utterance.)*
- **The brain decision logic is source-agnostic.** `observe`/`card_for_line` take only
  text/content (`owner_mode.py:333-339`); grep finds no `if source==` decision guards;
  `_spine_card` hard-codes `EventSource="app"` and demotes the real source to metadata
  (`control_core.py:882`); empirical stub run over 5 source labels × 4 text types yielded
  identical card signatures. *(VERDICT: TRUE.)*
- **All three named route segments reference `core.owner_ingest`** (re-verified by text scan +
  AST walk over `main.py`: ranges 719-723, 725-775, 777-804 → True/True/True). *(VERDICT: TRUE.)*
- **Memory + intent are deterministic, zero-model, and run under the throttled brain.** Every
  `live_memory` organ's live branch is a `pass # TODO(live)` no-op
  (`capture.py:158`, `inject.py:91`, `selfcheck.py:41`, `infer.py:57`, `maintain.py:97`).
- **Vague-ref resolution is deterministic head-noun ranking** (verified live, stub): "that desk
  thing" → "Jarvis standing desk", Mia-pickup rejected; two competing desks (gap < 5.0) → left
  unchanged for clarification (`intent_threads.py:137-208`).
- **Memory is durable + self-healing**: SQLite with inline embeddings, structured open_loops
  ledger retrievable without embeddings (`store.py`), integrity-check/quarantine/recreate
  (`store.py:59-66, 83-108`), Maintainer supersede/consolidate/decay never touching the ledger
  (`maintain.py:30-94`).
- **A vent never lands in an active durable drawer** even if its words match a profile/commit
  pattern (`capture.py:179-180`); it stays only in the inert remember-list.
- **Dedup: one real obligation = one card** (RAN `engine/scripts/test_owner_duplicate_collapse.py`
  → PASS, exit 0): duplicate trio collapses keeping original wording; the synonym-reworded
  identity-core case ("call Amazon about the monitor" + "handle the Amazon monitor issue") →
  one card; 6 distinct lines stay 6; monitor vs desk stay split; vent guard (force_ask)
  propagates on merge; thin lines (ok/yeah) never merge.
- **Moat fail-safe contract verified (stub-level):** non-OpenRouter provider → `available=False`
  (deterministic passthrough); vent → `actionable()==[]` and `act`→`hold`; vent-adjacent task
  caught as `ask`; garbage reply → `available=False` (line unchanged, no fabricated task);
  unknown kind → `ask`.

## GAPS (honest limits — what is NOT proven, and where the original claims overreached)

- **"Typed input calls the one brain directly with NO intermediate card-building" is REFUTED.**
  `owner_ingest` → `_owner_ingest_inner` is a multi-stage pipeline that **builds OwnerTaskCard
  objects** (`control_core.py:1131-1142`, `card_for_line`/`_spine_card`/etc.). The "one brain"
  (the model) is one *optional* stage reachable only under the OpenRouter provider
  (`control_core.py:964`). The handler is a direct delegate; the *brain* is not called directly.
- **"Memory is written for EVERY observed line — no input bypasses memory" is REFUTED as a
  universal.** The capture loop iterates `observed`, but `observed` is the **filtered** output
  of three transforms: `_intent_resolve` drops preference lines (`control_core.py:1065`, never
  captured), `_consolidate_obligations` merges away duplicate wordings, and (under OpenRouter)
  `_expand_tasks_with_model` drops pure vents/asides outright and captures the *extracted task
  text* rather than the raw breath. The mechanical sub-claim (every line *in `observed`* is
  captured before the execute branch) is true; the universal quantifier is not.
- **"Intent runs unconditionally for EVERY route — no input bypasses intent" is REFUTED as a
  universal.** True only *inside* `_owner_ingest_inner`. The `/event` + `/capture` default lane
  routes to `proactive.on_event` (when owner-event mode is off — the default,
  `control_core.py:460-461, 595-610`), inbound SMS YES/NO routes to `core.resolve`, and
  `/memory/remembered/approve` routes to `approve_remembered` — none pass through intent. Also:
  the moat's *model split* is provider-gated, so "moat runs unconditionally" is itself an
  overstatement under the stub provider.
- **The model's actual judgment quality is UNOBSERVED.** OpenRouter throttled (~22s/call), so
  the prompt's calls on the hard cases (sarcasm, overwhelm-markers next to real tasks,
  relayed-vs-listener-directed imperatives) are read-verified against the prompt + JSON
  contract, not runtime-verified. The prompt is the load-bearing inference and was not exercised.
- **The "live" memory enrichment is entirely unimplemented** — every organ's live branch is a
  `pass`. Today's capture gate, classification, disambiguation, relevance audit, inference and
  reflection are ALL the deterministic stub rules.
- **Intent resolution is single-head-noun + regex.** It cannot resolve synonyms ("the standing
  one" vs "desk"), multi-word objects with no shared head token, or cross-line coreference. The
  **bare-ref rewrite is grammatically broken** (verified: "Before I send it..." →
  "Before I send Finish Sam deck send team.").
- **Dedup precision tradeoffs.** Verb-only-different obligations on a single entity with no
  object collapse by design ("call Amazon" == "email Amazon"); kept wording is order-dependent
  (first line wins — relies on the moat emitting the canonical wording first); the generic/stop
  word lists are small hand-curated allowlists, so out-of-list synonyms ("chase", "follow up",
  "escalate") may not collapse. **Cross-batch / cross-session semantic dedup was not exercised**
  — reading suggests two separate ingests with the same obligation but different exact text
  would each persist a card (Layer 1 is within-batch; Layer 2 is exact-text).
- **Abstain floor in stub mode is uncalibrated** (`inject.py:36`: stub=0.22 is a "CI sanity
  value"; only the live floor 0.66 is fit on held-out data). Supersede fires for only three
  hard-coded subjects (employer/name/location); any other contradicting fact coexists. Vector
  retrieval is a full linear cosine scan (no ANN/sqlite-vec) — fine at single-user scale, won't
  scale.
- **Not run per the throttle constraint:** `run_suite.sh`, the cert harness, the safety
  mega-eval, any model-calling or live-embedding test, and the live engine round-trip.

---

## Honest verdict

The understanding brain is **structurally sound and genuinely strong on safety, with its
headline inference quality still unproven at runtime**. The architecture does the most important
thing right: three real input doors (typed, MP3-via-Whisper, always-on mic) collapse to one
source-agnostic pipeline, so there is no second-class input lane and no place for a vent to slip
into the act path — the cardinal-sin guard is enforced in *three* independent ways (model vent
judgment → force_ask downgrade with the executing spine bypassed → money hard-stop), and that
chain plus the dedup ("one obligation = one card") is verified by a passing deterministic test
and direct code reads. The memory/intent layer is durable, self-healing, vent-shielded, and
works entirely without the model, which is exactly what you want under a throttled brain. But
two things keep this short of "proven good": first, the part that makes the product magical —
the temperature-0 prompt that decides task-vs-vent-vs-ambient and resolves vague references — is
the one part that could not be exercised live, so its real-world catch-rate and false-positive
behavior are read-verified, not measured; second, the "live" deterministic-to-model upgrade path
is wired but entirely unimplemented (`pass # TODO`), and the convenient summary claims ("one
brain directly, no intermediate card-building", "every line captured", "intent runs for every
route") overstate a reality that is actually a multi-stage, provider-gated, partially-filtered
pipeline with several non-ingest routes that bypass intent. Net: a trustworthy, safety-first
skeleton with the muscle (memory, dedup, vent guards) verified — but the brain's actual
intelligence is currently a well-reasoned promise on paper, not a measured result.
