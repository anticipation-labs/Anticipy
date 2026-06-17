# MIDDLE_SPINE_TRUTH — the hard middle (Gate Middle-1)

MESSY INPUT → CONTEXT CAPTURE → RANKED RECALL → INTENT → ACTION → PREPARE/PARK → RECEIPT/BLOCKER.

## The layer (new): `engine/anticipy_engine/proactive/intent_threads.py`
Each transcript line is classified into exactly one kind (not a diary line):
- **vent** — emotion/joke/hyperbole → zero action (moat drops it; re-guarded here).
- **preference** — "the Jarvis desk is the one I liked / don't buy it yet" → a REFERENT, never a card.
- **action** — concrete obligation/request to the speaker → a card-eligible thread.
- **followup** — "remind me before I send it" → attaches to a prior thread, not a new card.

A vague reference is resolved by RANKING prior threads (deterministic, no model):
- **head-noun match** ("that **desk** thing" → only the Jarvis thread names "desk") wins big;
- **bare pronoun** ("send **it**") matches on a shared cue (both about *sending*) → the Sam-deck thread;
- recency is only a tie-breaker; vents and other follow-ups are NOT eligible referents;
- a winner must be clearly ahead, else the reference stays **ambiguous** → the caller asks the smallest
  clarification (it never guesses the wrong thread). This is the anti-mis-recall rule.

## Wired into the real path
`control_core._owner_ingest_inner`: `observe → moat expand → _intent_resolve(threads) → consolidate`.
`_intent_resolve` rewrites vague task text in place, drops preference lines from the card path, and
emits `middle_trace` (returned on `/owner/ingest` + logged to glassbox `intent_middle_trace`).

## Proven (real owner-ingest path, the endpoint the UI POSTs to) — 2026-06-16
Input: the 7-line scenario (Mia pickup / Jarvis desk preference / coffee vent / "that desk thing" /
lottery vent / Sam deck / "remind me before I send it").
- captured memories: pickup=action, Jarvis=preference, coffee=vent, desk-thing=action, lottery=vent,
  Sam-deck=action, remind=followup.
- "that desk thing" → **chosen: Jarvis standing desk**; **rejected: Mia pickup**; resolved text
  "put Jarvis standing desk in the cart".
- "remind me before I send it" → **chosen: the Sam revised-deck thread** (resolved, then merged).
- **3 cards, one per obligation** (pickup; Jarvis-desk cart→browser confirm-first, parks before
  checkout; Sam-deck). Coffee + lottery → **0 cards**. Nothing external fired (channels=mock).
All seven proof fields are in `middle_trace`: captured_memories, ranked_candidates, chosen_referent,
rejected_referents (+ formed intent = the resolved task, action plan = card route/action, result =
disposition/parked). Deterministic test: `engine/scripts/test_memory_handoff.py`.

## What still fails / is honest
- **Cross-ingest live re-submit** can still reword (the moat is a live model) and `_existing_owner_card`
  is exact-text, so a reworded re-submit could add a near-dup. WITHIN one ingest the result is clean;
  stub re-ingest is idempotent (public_backend_path replay). Semantic `_existing_owner_card` is the
  durable follow-up.
- The card titles are the resolved task text ("send the revised deck Friday" drops "Sam"); the thread
  is correct, the title is plain. Cosmetic.
- Classification is deterministic-heuristic (regex markers for vent/preference/followup). It covers the
  scenario + common shapes; unusual phrasings may misclassify — the moat's model vent-guard is the
  safety backstop (safety_mega_eval stays 0).
