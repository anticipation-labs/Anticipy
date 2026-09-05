# The 12 harness cards, as the board actually has them — 2026-08-24

Read off anticipy.ai/internal directly. Every card was created by "Claude"
6-7h ago. **Nothing on the board is marked complete. No card has a single
checked step. No card has a comment.** One card is "In progress"; the other
eleven are "To do".

That is the first finding: the board says zero progress while this branch
carries 44 unpushed commits.

| # | Card | Assignees | Board status | Steps checked |
|---|------|-----------|--------------|---------------|
| 1 | Read the Brief | Jose | **In progress** | 0 / 3 |
| 2 | 0 · READ ME | Jose, Omar | To do | none listed |
| 3 | WIRE IT ALL | Claude, Jose, Omar | To do | 0 / 5 |
| 4 | PHONE-AS-PENDANT | **Claude** | To do | none listed |
| 5 | SHELF 2 | **Claude**, Jose | To do | none listed |
| 6 | MOUTH | Jose | To do | 0 / 5 |
| 7 | HANDS 3 | Jose | To do | 0 / 5 |
| 8 | HANDS 2 | Jose | To do | 0 / 5 |
| 9 | HANDS 1 | Jose | To do | 0 / 4 |
| 10 | LIBRARY | Jose | To do | 0 / 5 |
| 11 | SORTER | Jose | To do | (not read) |
| 12 | EARS | Jose | To do | (not read) |

## What each card asks for, and where we actually are

### 1. Read the Brief — Jose — IN PROGRESS
Everything is in `docs/BRIEF.html` on `harness/tejas-fixes`. Contains what
we're building, done + fifty concrete moments (the spec), the six laws, every
screen with file refs, the brain pipeline, 105 worked examples.
Steps: open and read Done + the fifty moments · read the six laws (binding) ·
skim your organ sections.
**Us:** read end to end, twice. Produced `docs/BRIEF-AUDIT-2026-08-24.md` (the
Brief is stale on its own §9 — items 3 and 5 were fixed by `4888612d` the day
after publication — plus two factual errors) and `docs/FIFTY-MOMENTS-STATUS.md`
(**5 true, 27 partial, 18 owned by nobody**). Board steps still unchecked.

### 2. 0 · READ ME — Jose + Omar — TO DO
Five body parts: EARS → SORTER → LIBRARY → HANDS → MOUTH. "Claude builds two
cards tonight: SHELF 2 and PHONE-AS-PENDANT." WIRE IT ALL is the finish line.
Ground rules: HARNESS-LAWS.md at the branch root; full spec docs/BRIEF.html.
**Us:** all 18 cards organised into
`docs/superpowers/plans/2026-08-24-five-organs-roadmap.md`.

### 3. WIRE IT ALL — Claude + Jose + Omar — TO DO
THE LAST CARD. Definition of done, and nobody may redefine it: *a cold stranger
onboards on their own accounts, lives a normal week, she catches real things,
never makes them say "what?", and they don't want to give it back. Every
morning one question: was yesterday clean? Not clean → fix the ONE thing that
broke it. No session, demo, or green test may declare done — only lived days.*
Steps: every app button wired (approve/cancel/undo/receipts) · verify loop
end-to-end (act → evidence → done-text with photo) · onboard a fresh account
from zero · the clean-day counter · then: the stranger week.
**Us:** correctly untouched. It cannot start until the organs exist.

### 4. PHONE-AS-PENDANT — CLAUDE — TO DO
*"Make always-listening on the phone solid enough to live with: background
audio survival, the watchdog, resume after calls/Siri/interruptions, battery
sanity, and the feed showing which ear heard what (phone vs pendant provenance
is already stamped). **Build 76 is on the phone**; this task is the reliability
pass from a day of real wearing. Findings become fixes or precise bug rows."*

| Card requirement | State |
|---|---|
| the watchdog | **DONE** — `2c4e9ec8` + `074281d8`. Rotation leg was dead code after the first utterance of any task |
| resume after calls/Siri | **DONE** — `a21bda71`. `resumeListeningIfWanted` was a total no-op |
| background audio survival | **PARTIAL** — the assertion is ~30s, not a phone call. Long calls still suspend; the resume policy is what covers those |
| battery sanity | **NOT STARTED** — nothing measures it anywhere |
| the feed showing which ear | **DONE** — the feed had it since `54157bba` (badge per line in `TranscriptRow`, per card in `ConversationCard`, `HeardGroup.ear` refuses a mixed conversation; see `research/2026-08-24-battery-and-ear.md` §2). 2026-09-05: the Listening screen adds the day's total by ear (`ListenTally.linesDeliveredByEar`), and a line sent from the queue now carries its ear into the journal so an outage day counts honestly |

Not asked for but built first, because none of the above could be judged
otherwise: the Stage 0 instrument (journal that survives a crash, tally,
diagnostics screen shipping in RELEASE, server-side day report).

### 5. SHELF 2 — CLAUDE + Jose — TO DO
Omar's ruling (Aug 24), three shelves: 1 just do it (math, lookups — live);
2 **do it and tell him, one-tap undo** — reversible things, no approval wait —
NEW, this task builds it; 3 gate — money, messages to other humans, deletes —
tap first, forever. HOW: the effect-channel field already classifies
compute/read/world. Shelf 2 = world-touching AND provably reversible. The plan
carries its own undo recipe **before** acting; the announcement text includes
the undo tap; the receipts system logs the evidence.
Jose's part: review the reversibility classifier — the one dangerous edge is
calling an irreversible act reversible.
**Us:** plan written (`2026-08-25-shelf-2-undo.md`). **NO CODE.** Stage 2 was
killed by adversarial judges before implementation: it rested on "the captured
handle is a fact, not a judgement", which is false — every field is
page-authored input. Needs redesign, not implementation.

### 6. MOUTH — Jose — TO DO
Part 5 of 5. Texts are the product; the app is the receipt drawer.
Steps: text like a human (researched, one thought per message) · thread
continuity (she knows what she asked, never re-asks) · the middle-shelf voice
("on it — booking the 7pm, cancel anytime") · **DONE = EVIDENCE** (a short text
+ screenshot/receipt, not a claim; a model grading a model is worthless) ·
app loop-back: every text mirrors into the feed with its evidence.
**Us:** nothing.

### 7. HANDS 3 — Jose — TO DO
Part 4(c). The browser, her hands inside the owner's own Chrome. SAFE (takeover
list: credential and payment fields never touched, even inside an approved
plan; effect-journal written BEFORE every click — exists, keep it; screenshots
as evidence) · REMEMBERING (task memory + skills cache + the library,
read-only, provenance respected) · CHEAP (recipes first, small model for
navigation, strong model only at decision points).
**Us:** nothing.

### 8. HANDS 2 — Jose — TO DO
Part 4(b). **First subtask is RESEARCH — Composio is a candidate, not a
decision.** Compare Composio vs Arcade vs Pipedream Connect vs native
per-service OAuth on auth UX, token security/storage, per-call cost, coverage,
reliability. Pick with evidence, write the comparison into the card.
Steps: research + pick · onboarding connect flow (optional, skippable, never
blocks) · repeated-chore detector → the suggestion text · adapters for the top
3 services · **tokens live server-side, never in the app or the extension**.
**Us:** nothing.

### 9. HANDS 1 — Jose — TO DO
Part 4(a). Research always before acting, and never pay for the same learning
twice. Steps: deep-research gate (any world-touching plan gets a research pass
first, server-side, before the browser opens) · skills cache (write the recipe
down after every successful run; recalled BEFORE planning the next similar
goal) · skill aging (stale recipes re-verified, not trusted) · wire skills into
both the server research lane and the browser agent.
**Us:** nothing.

### 10. LIBRARY — Jose — TO DO
Part 3 of 5. Three tools in a line: VECTOR (fuzzy finder) → GRAPH (family tree,
precise) → RANK (the librarian: fresh × important × relevant, hands over 5).
Have: episodes → graph facts with importance AND confidence AND source quote;
keyword+graph+importance recall; nightly consolidation.

**RE-CHECKED AGAINST THE CODE 2026-09-04. FOUR OF THE FIVE "MISSING" ITEMS ARE
BUILT.** The list below was accurate when it was written and has not been true
for a while, which is the hazard the Brief already names: an agent was sent to
rebuild supersession on 2026-08-25 because it grepped this document's word
(`superseded_by`) instead of the code's (`retired_ts`) and got zero hits. A
card that lists finished work as missing spends a session re-deriving it.

| item | state | evidence |
|---|---|---|
| supersession | **DONE** | `_supersede`, `retired_ts`/`retired_by` (memory.py:102,190). Rows retired, never deleted, model-judged. 44 tests in `tests/test_memory_supersession.py` |
| aging | **DONE** | `_HALF_LIFE_DAYS = {"stable": None, "situation": 30.0}` (memory.py:474); situation facts decay, stable ones do not |
| confidence actually READ | **DONE** | `salience = importance × _confidence_band(confidence)` (memory.py:1541, band at :511), banded so it reorders inside an importance tier and provably cannot reach the tier above |
| **provenance gates action** | **DONE, and it is the strongest of the four** | `_UNTRUSTED_SOURCES = {"import", "supervised_mail", "supervised_professional", OVERHEARD}` (anticipy_core.py:441). `fill_gaps_from_memory` EXCLUDES rather than fences them (orchestrator.py:1258-1260) because that answer becomes `filled[gap] → params[key] → seed_facts → the browser agent's approved values → a form it submits`. Fails CLOSED: an ImportError there propagates to the caller's except, which asks the owner instead. Membership, not a literal string, so a fifth untrusted source is one line. Tested: `tests/test_imported_facts_are_fenced.py`, `tests/test_supervised_read_is_fenced.py` (86 checks pass with supersession) |
| vector channel | **NOT BUILT** | one mention in the whole file, and it is the doctrine arguing against it: memory.py:9 "Recall is graph-walk + time, not embedding soup" |

So the only open item is the vector channel, and it is contested rather than
merely undone: the card asks for it and the module's own header declines it. It
should be decided on evidence about what recall actually misses, not built
because a card lists it.
**Us:** ruled on the moment-35 vs §7 conflict — retirement gates ACTION
absolutely, SPEECH conditionally (`22649e77`). No code.

### 11. SORTER — Jose — TO DO
Part 2 of 5. Do after EARS ships segment-close events. The judge: for every
finished thought — ignore / ask / act / answer, and whose task it is. Checks
whose VOICE said it (speaker tags — linked in build 76, **unproven live**), who
it was AIMED at, and whether the owner took it on.
Current: worked examples + effect-channel field in the prompt, frontier-model
second opinion on anything about to act, meeting posture, a shard floor (marked
as tape). **Judgment measured 68% → 80% on the labeled set.** Remaining
blindness: she still judges LINE BY LINE.
Option A (recommended): conversation-granularity judging — one strong-model
call per closed segment sees the whole conversation; retires the shard tape,
cuts ~50 cheap calls to ~3.
**Us:** brain-side fixes landed that touch this (`00d9a90f`, `8849df15`,
`e60946a4`) but option A is not built.

### 12. EARS — Jose — TO DO
Part 1 of 5. **Everything downstream is capped by this task.** Today: Apple
dictation, no VAD, no real spoken-at timestamps; the Aug-23 call measured
**~1 word in 3 captured, 54% of lines ≤4 words.**
THE RULE: never judge while sound is arriving — judge when a thought CLOSES.
A (recommended): migrate to Apple SpeechAnalyzer/SpeechTranscriber (iOS 26) —
long-form, distant, multi-speaker, on-device, sample-accurate timestamps, free
SpeechDetector VAD, ~55% faster than Whisper-large.
B: keep SFSpeechRecognizer + Silero VAD + fix spoken_at (smaller, but the
recognizer stays dictation-grade).
C: cloud streaming ASR with diarization — raw audio leaves the phone, violates
local-first.
**Us:** ruled A is a **fork, not an upgrade** — screen the stranger first, and A
must be additive or `tejas_gate` leg 7 breaks (`22649e77`). No code.
Related: `proof/capture_day.py` now re-measures the §9 number live — the first
run says 41% short thoughts for the real owner, but against pre-cut-marking
production code.
