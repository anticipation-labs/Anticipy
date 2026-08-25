# The Five Organs — roadmap and sequencing

> This is a ROADMAP, not an implementation plan. Nine cards covering nine
> subsystems do not belong in one plan document. Each card earns its own
> bite-sized plan when its turn comes; two of them (SHELF 2, PHONE-AS-PENDANT)
> already have one and are linked below.

**Board structure, which is the source of truth:** EARS → SORTER → LIBRARY →
HANDS → MOUTH, with SHELF 2 and PHONE-AS-PENDANT built alongside, converging on
WIRE IT ALL.

**Binding, read before any card:** `HARNESS-LAWS.md` (root), `docs/BRIEF.html`
(full spec), `docs/FOLLOWUPS.md` (known open items).

**Definition of done, which nobody may redefine:** a cold stranger onboards on
their own accounts, lives a normal week, she catches real things, never makes
them say "what?", and they don't want to give it back. Every morning, one
question: was yesterday clean? Not clean → fix the ONE thing that broke it. No
session, demo, or green test may declare done — only lived days.

---

## Where the tree actually is (measured 2026-08-24, not assumed)

Run on `jose_anticipy_system` after the fast-forward from `harness/tejas-fixes`:

```
pytest                1071 passed        extension suites   56/56
tejas_gate            8/8 PASS           iOS logic gate     all passed
done_gate             legs 1-5 PASS, leg 6 (A STRANGER) FAIL
is_the_brain_live     5/5 PASS  "THE DEPLOYED BRAIN IS KEEPING ITS PROMISES"
triage_eval --live    76% (19/25)        replay_call  3 acts / 1 mid-call text / 0 invented people
```

Two numbers deserve care. `triage_eval` is **76%**, not the 80% the Brief's §8
claims — six rows fail, and three of them (`tejas-domain`, `tejas-him`,
`tejas-after-five`) are the same shape: expected ignore, got act. But that is
the RAW PROMPT, with no posture, no owes gate, no shard floor. The replay proves
the guards below the model catch every one. **The judgment is still wrong there;
the seatbelt is what saves it.** That is precisely what SORTER is for.

The fifty moments, audited against source: **5 true, 27 partial, 18 owned by
nobody** (`docs/FIFTY-MOMENTS-STATUS.md`). The eighteen collapse into six
missing organs, and every one of them is a card below.

---

## The dependency graph

```
EARS ──────────────► SORTER            SORTER blocks on EARS's segment-close events
  │                    │                (the card says so: "DEPENDS ON")
  │                    │
  └──► PHONE-AS-PENDANT (Claude)       shares PhoneListener; must not collide
                       │
LIBRARY ───────────────┼──► HANDS 3    browser reads the library, provenance-respected
  (independent)        │
                       │
HANDS 1 ──► HANDS 3    HANDS 3 consumes the skills cache
HANDS 1 ──► HANDS 2    the repeated-chore detector counts skill runs
                       │
SHELF 2 (Claude) ──────┴──► MOUTH      the middle-shelf VOICE lands with SHELF 2
                                        MOUTH's DONE=EVIDENCE needs HANDS 3 screenshots
ALL ──────────────────────► WIRE IT ALL
```

**Independent, startable now:** EARS, LIBRARY, HANDS 1, SHELF 2, PHONE-AS-PENDANT.
**Blocked:** SORTER (on EARS), HANDS 2 and HANDS 3 (on HANDS 1), MOUTH's
middle-shelf voice (on SHELF 2).

---

## The cards, with what is already true

### EARS — capture that judges at thought-close (Jose, first)

Card ranks **A > B > C**: A = migrate to Apple SpeechAnalyzer/SpeechTranscriber
(iOS 26, on-device, sample-accurate timestamps, free SpeechDetector VAD); B =
keep SFSpeechRecognizer + Silero VAD + Smart Turn v3; C = cloud ASR, refused as
anything but a flagged temporary fallback because it breaks local-first.

**Already landed** (the Brief is stale here — verify before rebuilding):
`capture_started_at`/`spoken_at`/`capture_ended_at` are all written from one
caller-supplied instant (`AnticipyBackend.swift:508-512`); cut-marking exists
(`TranscriptFlushPolicy.flushReason`, `parent_line`); `ListenJournal` records
session/flush/POST causes. **Genuinely missing:** VAD (grep confirms zero hits),
segment-close events, the recognizer migration, and the dead `LocalTranscriber`
path still shipping disconnected.

**One warning that outranks the card's ranking:** option A is `@available(iOS
26)`. Screen the recruited stranger's phone FIRST. If they are on iOS 18, A does
nothing for their week and B is the only option that helps. This decision costs
nothing to make early and is expensive to discover late.

**Also:** the spec at `docs/superpowers/specs/2026-08-24-voice-capture-design.md`
pre-registered a §8 decision gate (shard <25%, speaker populated, capture still
<60% → migration justified). Those criteria were fixed in advance precisely so a
bake-off cannot be talked into the wrong conclusion. Honour them.

### SORTER — judge closed conversations, not lines (Jose, after EARS)

Card's own answer: build **A in the shape of C** — cheap per-line filter for
obvious noise, full judgment at segment close. This retires `shard_too_thin`,
which is marked TAPE in source with *this exact expiry*
(`anticipy_core.py:581-612`, tracked by `tejas_gate` leg 2).

The card's steps say "re-measure: triage_eval + replay_call must not regress."
Take that literally and pre-register the bar before starting: **triage_eval ≥
76% per-label, replay_call ≤ 3 acts / ≤ 1 mid-call text / 0 invented people.**
A number agreed after the fact is not a bar.

### LIBRARY — memory that survives 95 years (Jose, anytime)

Five steps, and the first is the one the Brief calls out: **supersession**. "We
broke up" must RETIRE "partner is Sarah" — `invalid_at` on the old fact, kept for
audit, excluded from recall. Today they coexist and the old one outranks.

A full design for this already exists in
`research/solutions-2026-08-24/designs.json` (cluster D): three-way relation
verdict (same/replaces/different), `status`/`superseded_by` columns, confidence
finally read in salience, nightly reconcile. **Two traps the adversarial pass
found, both worth carrying into the plan:**

1. **The retired-row merge trap.** `_find_same_fact` returns on first match. A
   genuine reversal ("actually, back with Dana") exact-matches the *retired* row,
   merges as evidence, and never reaches the relation judgment against the active
   one. The owner's correction changes nothing she says — the card's own problem
   rebuilt one level down. Fix: when a restatement matches a superseded row AND
   its evidence is newer than the superseding row, re-judge against the active
   occupant.
2. **"Never surface in her voice again" vs the §7 broadband entry.** Moment 35
   says retired facts never surface. But §7's broadband-call example *requires*
   the superseded address ("the account probably still shows 4 Maple St"). A
   filter that hides retired facts everywhere makes that example unimplementable.
   These two Brief clauses genuinely conflict — **this is an owner decision, not
   an engineering one.**

### HANDS 1 — research-first + a skills cache (Jose, anytime)

Deep-research gate before the browser opens; a skills cache written after every
successful run (site, steps, selectors, gotchas, last-verified); skill aging so
stale recipes are re-verified, not trusted.

**Already exists, do not rebuild:** the research lane runs server-side in the
worker (`worker.py` `run_research_jobs`, Brave + fetch + cited summary, and it
*fails* the plan without a cited URL). Recipes exist in `extension/recipes.js`
with `RECIPE_TTL_MS` = 14 days — the aging idea is already there in one place;
this card generalises it and moves it server-side.

### HANDS 2 — the API ladder (Jose, after HANDS 1)

**The first subtask is research and the card says so:** Composio is the named
candidate, NOT the decision. Compare against Arcade, Pipedream Connect, and
native per-service OAuth on auth UX, token security, per-call cost, coverage,
reliability. Pick with evidence, write the comparison into the card.

Non-negotiable from the card: tokens live server-side, never in the app or the
extension. That matches the existing posture exactly — the phone holds only its
own session token, and Chrome holds only a per-agent token
(`AnticipyBackend.swift:123-126`, `guard.pb.js`).

### HANDS 3 — browser: cheap, safe, remembering (Jose, after HANDS 1)

**Already true, and the card says keep it:** the effect-journal written before
every click, and the takeover list — `protectedInput` in `agent_loop.js` refuses
password fields and payment autocomplete *mechanically*, which the moments audit
confirmed is genuinely enforced today (moment 48, second clause).

**Missing:** screenshots as evidence rows at milestones, library+skills in the
browser context, and the cost pass.

### MOUTH — finish text-first (Jose, anytime)

Texts are the product; the app is the receipt drawer. The step that matters most
and is hardest to fake: **DONE = EVIDENCE.** Finished work arrives as a short
text plus the screenshot or receipt, never a claim. The card states the reason in
one line — *"a model grading a model is worthless — artifacts only."*

Thread continuity has a ready-made lever: the ledger already exists as durable
`anticipy_says` rows; the card asks to surface it *to the composer* so the model
also knows it already bugged you.

### SHELF 2 — act-and-tell with one-tap undo (Claude, tonight)

Omar's ruling, three shelves: 1) just do it (math, lookups) — live; 2) **do it
and tell him, one-tap undo** — NEW, this card builds it; 3) gate (money,
messages to humans, deletes) — tap first, forever.

**Full plan:** `docs/superpowers/plans/2026-08-25-shelf-2-undo.md`

**The auto-run half of this card is STRUCK.** Two adversarial judges killed it
and they were right: the design's safety rested on the executor "possessing a
captured undo handle, which is a fact, not a judgement" — but every field of
that handle is **page-authored input**. A site wanting non-refundable bookings
need only print the words "free cancellation." Possession of a string the
adversary wrote is not possession of a capability. A future version would need a
**proven-host allowlist** — hosts admitted only after a real undo receipt has
come back from them — which is a different card and is not scheduled.

**What ships is moment #28: undo, with a real cancellation receipt, and no gate
change at all.** `is_consequential()` is not modified by one line and nothing
runs unattended. Moment #25 does not ship from this card — a smaller claim than
the card's title, and the honest one.

### PHONE-AS-PENDANT — reliability (Claude, tonight)

**Full plan:** `docs/superpowers/plans/2026-08-25-phone-as-pendant.md`

The single largest finding, stated plainly because a stranger hits it on day
one: **a phone call can end listening for the rest of the day, and the only
thing that restarts it is the owner opening the app.** On interruption `.began`
we set `suspended = true` and nothing else; once audio stops, iOS suspends the
app and the 4-second watchdog Timer stops with it; `resumeListeningIfWanted()`
is a no-op because it guards on `!listener.isListening` and `isListening` was
never set false.

Second: a recognizer that dies **with nothing pending is invisible**, because
the only "recognizer is deaf" leg requires words to be pending — the rarer
state.

Stage 0 is two days and buys the thing everything else needs: **a real day
becomes diagnosable for the first time.** Note the code currently claims a
Settings export that does not exist (`ListenJournal.swift:30-32`,
`PhoneListener.swift:570-571`); Stage 0 makes the comments true.

### WIRE IT ALL — the last card (read first, do last)

Its five steps are the honest finish: every app button actually wired
(approve/cancel/undo/receipts); the verify loop end-to-end (act → evidence →
done-text with photo); onboard a fresh account from zero and note every rough
edge; the clean-day counter; then the stranger week.

**Two of these are already assigned inside other cards** — "undo" is SHELF 2,
"done-text with photo" is MOUTH + HANDS 3. What WIRE IT ALL uniquely owns is the
**cold-start rehearsal**: fresh owner ref, empty memory DB, Twilio provisioning,
welcome text, day-zero interview, as a NON-owner experiences them. No card owns
that path today and the stranger meets it first.

---

## Recommended order

Two lanes, because Jose and Claude do not touch the same files.

**Claude's lane (tonight):** PHONE-AS-PENDANT Stage 0 → SHELF 2 Stage 1 →
PHONE-AS-PENDANT Stage 1 → SHELF 2 Stage 2 (only after Stage 1 is verified live).

**Jose's lane:** EARS (screen the stranger's iOS version first) → SORTER →
then LIBRARY / HANDS 1 / MOUTH as capacity allows. HANDS 2 and 3 after HANDS 1.

**Then, jointly:** WIRE IT ALL's cold-start rehearsal → the stranger week.

### Two external clocks that should start before any of this

1. **TestFlight.** The stranger cannot receive the app while builds carrying the
   speaker frameworks vanish in processing. Two defects are proven locally: junk
   stub framework bundles (temp-path `LC_ID_DYLIB`) that Xcode ≥15.3 copies for
   statically-linked SPM products, and `sysctl`/`sysctlbyname` imports with no
   `SystemBootTime` declaration in `PrivacyInfo.xcprivacy`. **And processing-VALID
   is not enough** — an external tester needs Beta App Review, its own multi-day
   Apple clock. Start it first; it runs under everything else.
2. **The deploy.** Production runs whatever was last uploaded by hand. There is
   no git pipeline: `railway up` from a linked directory is the only mechanism
   (`cliCaller: "claude_code"`, `watchPatterns: []`, no commit field). Merging
   and pushing deploy nothing.

---

## Standing rules for every card

- **Run `overnight/done_gate.py` first and work only its first failing leg.**
- Law 1: no regex, verb list, or word count decides what words MEAN. Legal only
  in senses (audio plumbing), the seatbelt (what a plan TOUCHES), and gates.
- Law 2: tape ships with a `TAPE:` comment and a red gate leg. No expiry = a
  rejected diff.
- Law 3: nothing is fixed until green against the LIVE system. Repo-green is a
  claim, not a fact.
- Law 6: adversarial pass before ship. The owner is not the review loop.
- **A test double that rejects an unknown keyword is a signature pin, not a
  stub.** This repo has paid for that twice now — `chat()`'s `aux` flag and, this
  week, threading `touches` through the queue. Give doubles `**kw`.
- **Source-inspection tests pin exact guards on purpose.** Do not clean them up;
  if a diff breaks one, read the scar it names before changing it.
