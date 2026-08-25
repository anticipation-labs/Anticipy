# MOUTH and HANDS 1, mapped against the code

Read-only survey, 2026-08-24, branch `jose_anticipy_system`. Five agents were
editing `app/ios/**`, `brain/**` and `extension/**` while this was written; every
claim below is pinned to a symbol name as well as a line number, so a churned
file can be re-found. Nothing was modified.

Two cards. For each: **what exists**, **what is only written down**, **what is
genuinely missing**, **what it would take**. Then the SHELF 2 dependency.

Both cards' own descriptions are wrong in at least one load-bearing place, and
the places are named.

---

## CARD 1 — MOUTH ("finish text-first")

### What exists

**TEXT LIKE A HUMAN is largely built, and it is not in `asking.py`.**

The card says "`asking.py` started this — its docstrings carry the findings".
That is true but small. The bigger half is `TEXTING_STYLE`, a 33-line prompt
block at `brain/anticipy_core.py:868-914`, cited in comments at
`brain/anticipy_core.py:863-867` as researched from Tomo and Boardy (the same
provenance is recorded at `CLAUDE-ONBOARDING.md:27`, `HANDOFF.md:253`, and in
`brain/conversation.py:6-10`). It is real, enforced prompt text and it already
encodes most of the card's step:

- one thought per message ("Most texts are one sentence; two is the ceiling")
- `anticipy_core.py:882` — "One question max, and only the question that
  actually unblocks you."
- `anticipy_core.py:883-887` — never repeat an unanswered question; a follow-up
  must add something new; "Sending the SAME sentence twice is not a follow-up,
  it is a loop."
- ban-list of openers, no emoji, no corporate filler, match their energy.

It is shared by both composers: `VOICE_SYSTEM` interpolates it at
`anticipy_core.py:914`, and `REPLY_SYSTEM` appends it at
`brain/conversation.py:183` (imported at `conversation.py:38`). So every model-
composed sentence she sends already has these rules in front of it.

**`brain/asking.py` (225 lines) is the DEGRADED path only, and it is genuinely
implemented, not aspirational.** Its docstring (lines 1-47) is a real post-mortem
of a live 2026-08-21 failure — the five-question comma-spliced form that ended on
the word "which" — and all three rules it states are code:

- rule 1, subject-less fragments dropped: `_key()` returns `()` when the
  non-noise token set is empty (`asking.py:104-119`), and `speakable()` skips
  those (`asking.py:148-150`).
- rule 2, same-axis dedupe: `_AXIS` (`asking.py:63-67`) plus a stemmed subject
  set, so "What document?" and "which document" collide and "Where is the
  document?" survives.
- rule 3, `SPOKEN_LIMIT = 2` (`asking.py:53`), enforced at `asking.py:153-154`.
- never cuts a word in half: `_clip()` cuts at a space (`asking.py:122-128`).
- `_mid_sentence()` (`asking.py:158-169`) lowercases a list-item capital but
  leaves ALL-CAPS alone ("NHS number", "BOL").

Two message shapes, deliberately not stapled together: `ask_line()` (holding
work + at most one sentence of questions, `asking.py:177-191`) and
`question_line()` (nothing prepared, `asking.py:198-225`).

The wall is `tests/test_question_not_a_form.py`, which pins `SPOKEN_LIMIT <= 2`,
the axis dedupe, the fragment drop, and the rendered text end-to-end
(`test_question_not_a_form.py:61-100`).

Both call sites: `anticipy_core.py:2056` (`handled = said or ask_line(...)` —
fallback when `_voice` returned nothing or invented a digit) and
`anticipy_core.py:2149` (`question_line(decision.missing, ...)` — the ask valve).

**The ledger exists, is durable, and is read back after a redeploy.**
`kind="anticipy_says"` / `"anticipy_text"` / `"sms_reply"` rows in the `events`
collection. `brain/conversation.py:1124-1158` (`_thread_from_record`) rebuilds
the last 20 turns from them; `conversation.py:1111-1121` (`_thread`) calls it
whenever the in-process dict is empty, with a docstring naming the 2026-08-02
incident it was written for.

**The composer sees the ledger on ONE of the two paths.** `_classify()` builds
`thread = [...self._thread(phone)[-20:]]` at `conversation.py:1229` and hands it
to `REPLY_SYSTEM`. So when he texts her, the model does see what she said.

**App loop-back for the text itself is built.** Every SMS reply is mirrored:
`post_event("anticipy_text", out["reply"])` at `brain/worker.py:2659` (and the
error-apology path at `worker.py:2650`), with the comment at `worker.py:2655-2657`
stating the intent — one history, not two. Outbound-first texts post
`anticipy_says` (`worker.py:1503, 1542, 1594, 1605, 2170, 3051, 3240, 3369`).
The phone reads both: `AnticipyApp.swift:541` filters
`kind == "anticipy_says" || kind == "anticipy_text"` into `anticipySays`.

**The server already refuses a `done` without verified evidence.**
`backend/pb_hooks/workflow_guard.pb.js:202-211`: a status transition to `done`
must carry a parseable `receipt` whose `verified` is true, whose `effect_key`
matches, and whose `evidence` array is non-empty. The `receipt` column exists
(`backend/pb_migrations/1700000025_job_workflows.js:21`). The extension builds it
at `extension/workflow_state.js:111-131` and throws locally if evidence is empty.
The research lane builds one too, from cited URLs scraped out of the summary
(`brain/worker.py:1283-1291`).

**A screenshot capability exists in the browser agent.**
`extension/agent_loop.js:112-143` (`screenshot(tabId)`) returns a
`data:image/jpeg;base64,…` frame via CDP `Page.captureScreenshot`. It is called at
`agent_loop.js:5003` when `needsEyes()` says the page is a calendar/seat-map/
slider.

### What is only written down as intent

- **"Study real human threads" is not what happened.** The findings in
  `asking.py`'s docstring and in `TEXTING_STYLE` are derived from *Anticipy's own
  recorded live failures* and from second-hand description of two products
  (Tomo, Boardy). There is no corpus, no thread study, no eval anywhere in the
  tree that measures "does this read like a person". `proof/ambient/score.py`
  scores *decisions* (ignore/act/spoke), not wording.
- **The MOUTH card's DONE=EVIDENCE step is already written down as a red gate
  leg by another agent tonight**, not as code: `overnight/stranger_gate.py`
  leg 7 (`leg_7_receipt_is_what_is_shown`, `stranger_gate.py:755-799`) and leg 8
  (`leg_8_done_text_can_carry_the_photo`, `stranger_gate.py:813-843`). Leg 8's
  own comment states the finding this card was given. Those legs are the
  tracker; they are not the fix.
- **`asking.question_line`'s third-person drop is registered TAPE**
  (`asking.py:216-218`, ledger bullet `[tape:third_person_drop]` at
  `HARNESS-LAWS.md:153-156`, registry at `overnight/tape_gate.py:525`). Its
  stated expiry is "when the composer owns person-flipping explicitly" — which
  is MOUTH work. Finishing MOUTH should retire that tape.

### What is genuinely missing

**1. The composer does not see the ledger on the path that starts a
conversation.** `Conversation.reach_out()` at `brain/conversation.py:332-350`
calls the model with a literal `"thread": []` (line 337). Every unprompted text
goes through it: `AnticipyCore.notify_owner()` routes to
`self.conversation.reach_out(...)` at `anticipy_core.py:2849`. So the model that
writes her opening sentence is told the pending jobs and the task, and *nothing*
about what she has already said. The `TEXTING_STYLE` line "Never repeat a
question they haven't answered" is therefore an instruction the model has no
evidence to obey.

**2. What actually enforces "she already bugged you" is word overlap in Python,
never the model.** Three deterministic guards read the ledger and decide for it:

- `already_said(text, within_hours, overlap=0.6)` — `brain/worker.py:1902-1938`,
  `_content_words` Jaccard-ish overlap ≥ 0.6.
- `already_raised(goal, …)` — `brain/worker.py:1846-1899`, `goal_tokens` overlap
  ≥ 0.6.
- `raised_and_ignored(goal, text)` — `brain/worker.py:1960-2007`,
  `NAG_OVERLAP = 0.34`, `NAG_LIMIT = 2`, `NAG_WINDOW_DAYS = 14`.

All three are called from `SPEAK_ONCE` (`brain/worker.py:2249-2311`) or from the
parked-ask sender (`worker.py:2156`). This is the card's real content: the ledger
*is* consulted, by a threshold, and its verdict can cancel a card outright
(`anticipy_core.py:2087-2118` cancels the job when `_may_say` returns falsy). The
model is never shown the rows and never gets to say "I already asked this, but
the deadline moved, so this follow-up adds something."

Note this sits directly under HARNESS-LAWS Law 1. `NAG_OVERLAP` at 0.34 is a
number deciding whether two sentences *mean* the same thing. The comment at
`worker.py:1994-2000` defends it with measured separation on five real cases —
honest, and still a threshold on meaning.

**3. `_voice()` — the composer for every ambient/outbound sentence — has no
thread channel at all.** `anticipy_core.py:2666-2690` calls
`llm.chat(VOICE_SYSTEM, json.dumps(context))`. The context dicts passed to it
are small and fixed: `{situation, heard, goal, missing, assumption}`
(`anticipy_core.py:2035-2042`), `{situation, task, what_you_found}`
(`worker.py:1573-1583`), `{situation, their_message}` (`worker.py:2639-2644`).
There is no key for prior turns, and by design (`anticipy_core.py:2674-2684`) any
token outside that dict is treated as an invention and the composition is thrown
away. Surfacing the ledger to `_voice` therefore also means widening the
allowed-vocabulary guard, or the added history will trip the name/digit checks.

**4. The parked ask is sent verbatim, with no composer pass at all.**
`worker.py:2162` sends `text` — the raw `question_line()` template string — via
`notify_owner`, which does route through `reach_out` and so does get one model
rewrite, but with an empty thread (see 1).

**5. DONE = EVIDENCE: both halves of the audit are confirmed.**

- **`MediaUrl` appears in no `.py`, `.js` or `.swift` in the repo.** Verified:
  `grep -rni mediaurl` over the whole tree returns four files, all of them the
  gate and its docs — `overnight/stranger_gate.py:805-830`,
  `tests/test_stranger_gate.py:590,601`, `research/2026-08-24-stranger-gate.md`,
  `research/2026-08-24-cold-stranger-walkthrough.md`. Zero in shipped code.
  `VoiceArm.text()` at `brain/voice_arm.py:411-420` posts exactly
  `{"From", "To", "Body"}` to `Messages.json`.
- **`AgentJob` never decodes `receipt`.** `app/ios/Anticipy/Backend/AnticipyBackend.swift:5-46`
  — the full field list is `id, goal, params, status, result, created,
  workflow_id, workflow_version, workflow_state, consequence, approval,
  scope_digest, effect_key, effect_uncertain, reconciliation, lane`. No
  `receipt`. The done card is fed `job.result` and nothing else:
  `ContentView.swift:1889` → `JobReceiptPolicy.doneCard(goal:result:)` at
  `JobReceiptPolicy.swift:41-51`, which promotes `result` verbatim as the lead.

  The same is true on the text side: `report_finished_jobs` composes the done
  text from `{"task": goal, "what_you_found": result}` (`worker.py:1573-1583`).
  `grep -n receipt brain/worker.py` returns one hit, and it is an unrelated
  comment (`worker.py:2290`). **So the server-verified receipt is written by the
  extension, enforced by the backend, and then read by nobody.** That is the
  card's "a model grading a model": `result` is the browser model's own done-claim
  string, and the done text is a second model's sentence about it.

**6. There is no image anywhere in the product's data path.**
- `receipt.evidence` is a list of *strings*, not URLs to images:
  `extension/agent_loop.js:1728-1748` (`verificationEvidence`) emits
  `url:<page url>`, `title:…`, `page:<content fingerprint>`, `facts:…`,
  `proof:<kind>`, `journal:<url#hash,…>`. Useful as an audit index; it is not a
  picture and it is not a receipt a person reads.
- The `screenshot()` frame at `agent_loop.js:112-143` is passed to `llmStep` as
  `image` (`agent_loop.js:5003, 5006`) and then discarded. It is never uploaded,
  never attached to the job, never posted to `events`.
- No PocketBase collection has a file field: `grep -rn 'type: "file"'
  backend/pb_migrations/*.js` → zero hits across all 45 migrations. The `events`
  schema (`backend/pb_migrations/1700000000_anticipy.js:27-42`, extended by
  `1700000020`, `1700000028`, `1700000029`, `1700000040`) is text columns only.
- The iOS app cannot render a remote image: `grep -rn 'AsyncImage'
  app/ios/Anticipy/` → zero. The single `Image(uiImage:)` in the app is a tiling
  noise texture (`Theme.swift:321`).

**7. "Every text mirrors into the app feed WITH ITS EVIDENCE ATTACHED" — the
mirroring is built, the attachment is not.** The feed row is `{kind, text,
decision, goal, needs_confirmation, …}`. There is no evidence field on it and
nothing joins an `anticipy_says` row to the job whose receipt proves it.

### What it would take

Rough shape, no ordering implied.

- **Thread continuity (smallest real win).** Pass the reconstructed ledger into
  `reach_out`'s payload instead of `[]` — `_thread_from_record` already returns
  exactly the right object and is already owner-scoped. Then widen `_voice`'s
  context with a `already_said_about_this` list, and extend `invented_names`'s
  allowed vocabulary to cover it (or history text will be read as an invention
  and every composition discarded). Half a day for `reach_out`; `_voice` is
  bigger because of the vocabulary guard.
- **Retire the overlap thresholds into the model.** Once the composer can see
  the ledger, `raised_and_ignored`/`already_said` can demote from *decider* to
  *retrieval* — hand the matching rows to the model and let it decide whether a
  third message adds something. This is the Law 1 fix, and it needs an eval
  (there is none for wording today) before the thresholds can be removed. Note
  `_may_say` returning falsy currently **cancels the card**
  (`anticipy_core.py:2087-2118`); that coupling has to survive the change.
- **DONE = EVIDENCE, text side.** Three separate pieces:
  1. Add `MediaUrl` to `VoiceArm.text()` (`voice_arm.py:411-420`) as an optional
     list. That is the leg `stranger_gate` leg 8 asks for, and it is small.
  2. Give it something to point at. Twilio requires a **publicly fetchable
     https URL** for `MediaUrl` — a `data:` URI will not do — so this needs a
     hosting decision that does not exist anywhere in the repo today: no file
     field in PocketBase, no blob store, no CDN. That is the real cost of this
     step, not the parameter.
  3. Persist a screenshot at all. `screenshot()` exists but its output is
     thrown away. Capturing at the commit milestone and uploading it is new
     extension work plus a new storage column/collection.
- **DONE = EVIDENCE, app side.** Add `let receipt: String?` to `AgentJob`
  (`AnticipyBackend.swift:5-46`, plus its `init` and `withStatus`), decode the
  JSON, and feed it to `JobReceiptPolicy.doneCard` so the lead comes from the
  server-verified receipt rather than the engine's sentence. Small and
  self-contained; this is `stranger_gate` leg 7 and it is the cheapest honest
  improvement on this card. Also feed `receipt` (not `result`) into
  `worker.py:1573-1583`'s `what_you_found` so the text and the card quote the
  same verified thing.
- **Loop-back with evidence.** Once a receipt/image URL exists, the feed row
  needs a way to point at it — either an `events.job` relation or an evidence
  text column — and the app needs its first `AsyncImage`.

---

## CARD 2 — HANDS 1 ("research-first + a skills cache")

### What exists

**A server-side research lane, complete and working.** `brain/research.py`
(153 lines): Brave Search → fetch top 3 pages → LLM summary with bracketed
citations, `run_research()` at `research.py:125-153`, never raises. Driven by
`run_research_jobs()` at `brain/worker.py:1198-1320`, called from the worker's
main loop at `worker.py:3405-3407`. It claims with stamp-and-read-back
(`worker.py:1246-1270`), sweeps its own stranded claims
(`release_stranded_research`, `worker.py:1142-1195`), and — the part worth
keeping — **it fails the plan when the answer carries no cited URL**:
`worker.py:1283-1296` regexes `https?://` out of the result and calls
`fail_plan(reason="research produced no verifiable source")` when there is none.

Lane separation is enforced in three places, not one: `job_lane()` at
`brain/anticipy_core.py:844-861` picks it at queue time
(`anticipy_core.py:3393`), `backend/pb_hooks/research_lane.pb.js` rewrites
browser claim filters, and the extension's own poll excludes it
(`BROWSER_LANE = 'workflow_id!="" && lane!="research"'`,
`extension/background.js:76`).

**A skills cache exists. Two of them. Both in the extension.** The card says a
skills cache is "a new collection"; another agent reported zero hits. Both are
wrong — the search was for the word "skills", and this repo calls them
*recipes* and *procedures*.

1. **`extension/recipes.js` (621 lines) — the recipe cache.** Site, steps,
   selectors, checkpoints, `compiledAt`, `runs`, `sources`. Four documented
   rules in the header (lines 16-49): two clean runs before anything compiles
   (`CLEAN_RUNS_REQUIRED = 2`, line 67); every step carries a checkpoint that
   must still be true; **a recipe may never carry a value the owner did not
   give this time** (there is structurally no `text` key on a typing step); the
   commit is never replayed. Aging is real: `RECIPE_TTL_MS = 14 days`
   (`recipes.js:66`), enforced at the read door in `recall()`
   (`recipes.js:156-172`), which also re-checks the no-stored-values rule and
   refuses a witness that has only been seen once.
2. **`extension/learn.js` (387 lines) — the researched-procedure cache.**
   `learnProcedure()` (`learn.js:241-…`) searches, ranks sources by *authority
   shape* rather than by vendor (`AUTHORITATIVE`/`LOW_VALUE`,
   `learn.js:40-56`), refuses to research banks (`NEVER_RESEARCH`,
   `learn.js:35`) or any private/loopback host (`isResearchable`,
   `learn.js:137-163`), and distills to `{start_url, needs, steps, caveats}`
   under a prompt that fences everything as untrusted page text
   (`learn.js:62-83`). Cached with `learnedAt` and `PROCEDURE_TTL_MS = 30 days`
   (`learn.js:59`, `recallProcedure` at `learn.js:348-357`).

Both key on the same normaliser, `taskShape()` (`learn.js:94-116`), which strips
digits, months and weekdays so "the March bill" and "the April bill" are one
entry — imported by `recipes.js:57` specifically so the two cannot drift.

**Both are wired into the browser agent, and one of them is recalled before
planning.** `extension/agent_loop.js:4015-4016` calls
`recallRecipe(shape, chrome.storage.local)` **before** `planRun` is invoked at
`agent_loop.js:4029-4031`. The procedure cache is recalled after planning,
`agent_loop.js:4049-4058`. A verified `done` records the run:
`recordCleanRun(shape, goal, runTrace)` at `agent_loop.js:5144`, defined at
`agent_loop.js:3958-3965` — and deliberately only on a *verified* done, not a
done claim (`agent_loop.js:5136-5139`).

**Two things already write down what a run learned, server-side and durable.**
- `jobs.trace` — the step-by-step history, written every ~4s during the run
  (`extension/background.js:1353-1393`), capped at 90 KB in the writer and
  100 KB in the column (`backend/pb_migrations/1700000034_jobs_trace_large.js`).
- `params._execution_journal` — up to 18 live-page evidence entries
  (`{fingerprint, url, title, text≤2500, elements}`), also on the job row
  (`background.js:1364-1372`), reloaded on a lease retry
  (`background.js:1348-1349`).
- Plus `jobs.receipt` (see MOUTH) and the LLM audit ledger
  (`backend/pb_migrations/1700000030_agent_llm_audit.js`).

**Column-migration machinery now exists.** The card's framing ("no column-
migration machinery at all until tonight") was true and is no longer. For the
per-owner SQLite: `_ADDED_COLUMNS` + `_retrofit_columns()` at
`brain/memory.py:124-148` and `brain/memory.py:459-478`, with the
`ALTER TABLE … ADD COLUMN` replay and a shape-parity test named in the comment.
For the backend: 45 PocketBase migrations in `backend/pb_migrations/`. A *new
table* in the SQLite store has always been free (`CREATE TABLE IF NOT EXISTS` in
`SCHEMA`, `memory.py:33-118`) — the comment at `memory.py:107-110` says so
explicitly about `vetoed_facts`. So "a new collection" is cheap now, in either
store.

### What is only written down as intent

- The roadmap's own HANDS 1 note (`docs/superpowers/plans/2026-08-24-five-organs-roadmap.md:157-162`)
  is the accurate version of the card and already says "do not rebuild" about
  the research lane and `recipes.js`. The card as handed over is the stale one.
- `learn.js:29` calls the procedure cache "the seed of the recipes the MVP spec
  calls the moat" — that framing is written down; the moat itself is one
  browser profile deep (see below).

### What is genuinely missing

**1. The research pass does not gate. It is available, and it is opt-in by the
model.** Two separate mechanisms, and neither is what the card describes:

- **`job_lane()` is a router, not a gate.** `anticipy_core.py:844-861` sends
  read-only goals *away from* the browser to the research arm. A goal that will
  touch the world (`_IRREVERSIBLE_RE` hit, or no `_READ_ONLY_RE` hit) returns
  `""` and goes straight to the browser lane with **no research pass at all**.
  It is also `_READ_ONLY_RE` (`anticipy_core.py:125-137`) doing the deciding —
  registered standing tape, `[tape:read_only_re]` at `HARNESS-LAWS.md:126-136`,
  whose ledger entry notes the gate leg that was supposed to track it is green
  while the regex still decides.
- **`learnProcedure` is gated on `plan.unfamiliar` — a model self-report.**
  `agent_loop.js:4049`: `if (plan && plan.unfamiliar)`. `unfamiliar` is set by
  the planner itself (`PLAN_SYSTEM`, `agent_loop.js:2585-2596`), which is told
  outright: "Set `unfamiliar` false for anything you can already name the site
  and the flow for. Researching a restaurant booking is a waste of the owner's
  money." And it only fires when the model also produced a search question
  (`agent_loop.js:2660-2664`). So: the model decides whether it needs research,
  and it is prompted toward "no". Additionally `plan` is `null` whenever the
  caller supplied an explicit `startUrl` or the run is a resume
  (`agent_loop.js:4029`), which skips research entirely.

  The card's rule — "any plan that will touch the world gets a research pass
  first, server-side, before the browser opens" — is implemented as neither
  *any*, nor *first*, nor *server-side*.

**2. The two caches are browser-local, and that is the load-bearing gap.** Both
persist to `chrome.storage.local` (`agent_loop.js:4016, 4052, 4057`,
`recipes.js:160,201`, `learn.js:348,359`). Consequences:

- Nothing server-side can read them. The research lane in `brain/` has no idea a
  recipe exists; `run_research_jobs` (`worker.py:1198-1320`) never consults one.
- They die with the browser profile, a reinstall, or a second machine.
- They are per-browser, never per-owner. There is no owner scoping on them at
  all, unlike every job/event read in the tree.
- The card's step "wire skills into **both** the server research lane and the
  browser agent's context" — the browser half is done, the server half does not
  exist and cannot without moving the store.

**3. Nothing named "skills" exists, and no *server-side* cache of any kind
exists.** Where I looked: `grep -rn "skills\|skill_"` over `brain/`, `backend/`,
`extension/`, `overnight/` → zero hits outside `docs/superpowers/`. No
`skills`/`recipes`/`procedures` collection in any of the 45 migrations. No
skills table in `memory.py`'s `SCHEMA` (`memory.py:33-118` — the tables are
`episodes`, `nodes`, `edges`, `profile_facts`, `consolidation_state`,
`vetoed_facts`).

**4. Aging is expiry, not re-verification.** Both caches hard-expire on read and
return `null` (`recipes.js:169`, `learn.js:354`), which sends the next run back
to full-price reasoning. A recipe's clock is refreshed by a clean run
(`mergeRecord`, `recipes.js:186-204`), so a *frequently used* recipe never ages
out — but a recipe used monthly on a 14-day TTL is re-learned every time and
never accumulates. There is no `lastVerified` distinct from `compiledAt`, no
cheap re-verification pass, and no signal to the owner that a recipe went stale.
The card's "stale recipes get re-verified, not trusted" is not built.

**5. The recall point exists in the browser and does not exist on the server.**
`agent_loop.js:4015` is the exact line where a recipe is recalled before
planning, and `planRun`'s user payload (`agent_loop.js:2626-2634`) is already
shaped to receive extra background blocks — it takes `ownerProfile`, `scope`,
`memory`, each fenced. Adding a recalled-skill block there is a small change.
The server has no equivalent: `job_lane` is called at
`anticipy_core.py:3393` before the job row is even written, and there is nothing
between it and the queue that could consult a cache.

### What it would take

- **Move the store, keep the logic.** `recipes.js` and `learn.js` are pure by
  contract (no chrome/DOM/network — stated at `recipes.js:73-76`) and take a
  `storage` object with `.get()`/`.set()`. Swapping `chrome.storage.local` for a
  backend-backed adapter is the smallest path to a server-side, owner-scoped,
  cross-machine cache and does not require rewriting the caching rules. New
  PocketBase collection (`skills` / `recipes`), owner-scoped like `jobs`, plus
  the two `storage` call sites at `agent_loop.js:4016/4052/4057`.
- **Make the research pass a gate rather than a self-report.** The honest
  version is a decision the model does not get to skip: either always research
  when the plan will touch the world (and pay for it), or ask an isolated
  second model — the `_about_pending` pattern at `conversation.py:1212-1226` is
  the existing shape for that. Note `plan.unfamiliar`'s current wording exists
  *because* researching a restaurant booking wastes money, so "always" needs a
  cost answer, and `research.py`'s server pass is the cheap place to put it.
- **Wire the server lane to the cache.** Once the store is server-side,
  `run_research_jobs` can recall before searching and write back after — this is
  where "never pay for the same learning twice" actually lands, because the
  research lane is the cheap lane.
- **Aging.** Add `lastVerified` alongside `compiledAt`, and on expiry
  degrade to *hint* (feed the stale steps to the planner as background) rather
  than to *null*. Cheap; the `procedureBlock()` renderer at `learn.js:200-217`
  already produces exactly that kind of fenced background block.
- **Distillation from what already exists.** `jobs.trace` and
  `params._execution_journal` are already durable, server-side, per-job records
  of what a run did and saw. A server-side skills cache does not need new
  capture — it needs a distiller over rows that are already being written.

---

## The SHELF 2 dependency

**SHELF 2 has no code.** Confirmed by absence, not inference: `brain/undo.py`,
`overnight/shelf2_gate.py`, `tests/test_shelf2_eligibility.py`,
`tests/test_undo_is_a_compensating_plan.py` do not exist; `grep -n undo
brain/workflow.py brain/conversation.py` → zero; `grep -n 'Undo'
app/ios/Anticipy/Views/ContentView.swift` → zero. The plan at
`docs/superpowers/plans/2026-08-25-shelf-2-undo.md` is complete and unexecuted.

**What was killed, and why it matters to MOUTH.** The plan's own header (lines
9-13) and the roadmap (`2026-08-24-five-organs-roadmap.md:196-208`) record that
the *auto-run* half — moment #25, act-without-asking — was struck by two
adversarial judges: the design rested on the executor possessing a captured undo
handle, and every field of that handle is page-authored input, so "free
cancellation" is a string an adversary writes. What remains scheduled is moment
#28: undo with a real cancellation receipt, **no gate change**,
`is_consequential()` untouched.

**So, precisely:**

*MOUTH cannot do* the card's own example sentence — "on it — booking the 7pm,
cancel anytime". Both halves are blocked by different things. "on it" (rather
than "want me to go ahead?") requires acting unattended on consequential work,
which is the struck half and is not scheduled; the split today is
`say_handling(goal, needs_ok)` at `anticipy_core.py:2693-2701`, which returns
"On it: …" only when the work was never held. "cancel anytime" requires an undo
affordance that does not exist in any of `brain/`, `extension/`, or the app —
saying it today would be the confident lie the codebase already has a name for.

*MOUTH can do*, with no SHELF 2 at all:

- everything in TEXT LIKE A HUMAN (`TEXTING_STYLE` and `asking.py` are complete
  and independent),
- all of THREAD CONTINUITY — `reach_out`'s empty thread, `_voice`'s missing
  history, and the overlap thresholds are three self-contained changes in
  `brain/`,
- all of APP LOOP-BACK for the text itself (already built; only evidence
  attachment is open),
- **all of DONE = EVIDENCE except the picture.** Decoding `receipt` into
  `AgentJob` and feeding it to `doneCard` and to the done-text composer needs
  nothing from SHELF 2 — the receipt is already written, already verified, and
  already refused by the backend when absent. This is the largest honest chunk
  of MOUTH available today.

*MOUTH's shelf-1 voice is already live.* Where work genuinely was not held, the
"On it: …" line exists. What SHELF 2 would add is the middle register — and the
half of it that is scheduled (undo + receipt) would give "cancel anytime"
something true to point at, without changing who runs unattended.

---

## Where I looked and found nothing

Stated so the negatives are auditable.

- `MediaUrl` — `grep -rni mediaurl` over the entire tree excluding `.git`: four
  files, all gate/test/research. Zero in `brain/`, `backend/`, `extension/`,
  `app/`.
- `receipt` in the brain's delivery path — `grep -n receipt brain/worker.py`: one
  hit, an unrelated comment at line 2290.
- `receipt` in Swift — full field list read at `AnticipyBackend.swift:5-46`.
- Skills cache, server-side — `grep -rn "skills\|skill_"` over `brain/`,
  `backend/`, `extension/`, `overnight/`: zero outside `docs/superpowers/`. No
  collection in any of the 45 files in `backend/pb_migrations/`. No table in
  `memory.py`'s `SCHEMA`.
- File/blob storage — `grep -rn 'type: "file"' backend/pb_migrations/*.js`: zero.
- Remote image rendering in the app — `grep -rn AsyncImage app/ios/Anticipy/`:
  zero.
- SHELF 2 — the four files its plan says to create do not exist; `undo` appears
  in neither `workflow.py`, `conversation.py`, nor `ContentView.swift`.
