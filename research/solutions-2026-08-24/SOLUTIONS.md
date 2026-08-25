# The §9 Solutions — designed, adversarially verified, ordered

2026-08-24 · grounded against `harness/tejas-fixes` at `a71d7ca7` (post-rebase).
Method: eight independent designers (one per Brief §9 problem cluster), each
required to ground in CODE not the Brief, then three adversarial judges — laws
compliance, recorded-failure regressions, path-to-leg-6 — attacked the full
set. Raw designs and full verdicts: `designs.json` / `judgments.json` in this
directory. This file is the synthesis: what survived, with the judges'
required changes folded in. The metronome still applies — one item at a time,
in the order below.

**Context that reframes everything: done_gate legs 1–5 all pass today. The
only failing leg is 6 — a cold stranger carried through a real clean week.
Every choice below is optimized for the shortest SAFE path to that week.**

---

## What the Brief already got stale (verified in code, not assumed)

- §9 item 3 (ask valve) and item 5 (meeting window): **fixed** by `4888612d` —
  parked governed asks, adaptive 360–600s settle, DIGEST_PENDING parking.
- §9 item 1's sub-claims: capture timestamps, cut-marking (`flushReason` /
  `parent_line`), and session observability (ListenJournal) all landed in
  today's 8 capture commits. **Repo-green only — never measured live.** The
  ~67% word-loss number itself is unmoved and unmeasured post-fix.
- The rest of §9 (items 2, 4, 6, 7, 8, 9, 10) is real and open.

## Live bugs found during this pass (none in the Brief)

1. **The bare go-ahead guard misses the meeting posture.** `anticipy_core.py:1370`
   checks `in_conversation` but not `in_meeting` — during an armed meeting,
   the OTHER person's "okay let's do it" can release a held consequential
   card with no tap. (Cluster C; verified by two judges.)
2. **The typed-ask confirmation bypass.** The direct lane drops the model's
   `touches="world"` declaration at `anticipy_core.py:2085-2087` — a typed
   errand whose verb `_VERBS` doesn't know mints UNHELD and skips the
   confirmation gate. (Cluster H; verified in source by two judges.)
3. **The 3/day uninvited-text cap counts almost nothing.** The counter's
   `params` clause is dead code (events has no params column); the FYI path
   checks the budget but never spends it; clock texts and digests are
   invisible. A busy week can legally produce 10+ uninvited texts/day.
   (Cluster E; reproduced independently by two judges.)
4. **TestFlight's silent rejection has two locally-proven causes.** Xcode
   ≥15.3 copies junk stub framework bundles (temp-path `LC_ID_DYLIB`) for the
   statically-linked sherpa/onnxruntime products, and the linked onnxruntime
   imports `sysctl`/`sysctlbyname` (SystemBootTime required-reason category)
   that `PrivacyInfo.xcprivacy` does not declare. The rejection emails go to
   an Apple-ID inbox nobody reads. (Cluster F; stubs and `nm` output
   reproduced on this machine.)

---

## The pre-stranger plan, in order

~14–19 focused days across two lanes, +3–5 conditional. Consensus of all
three judges' orderings; disagreements were only about adjacent swaps.

| # | What | Days | Why this position |
|---|------|------|-------------------|
| 1 | **F — TestFlight fix**, day one: strip-script + SystemBootTime manifest + IPA audit gate + ASC API polling gate (`testflight_gate.py`), upload build 77. **On VALID: immediately create the external tester group and submit for Beta App Review** with pre-written notes for the always-on mic + background audio. Request a monitored ASC admin email. | 1–2.5 + Apple latency | Owns the two longest external clocks (processing AND Beta review — the judges' biggest catch: `VALID ≠ stranger-installable`). Leg 6 hard-depends on it. |
| 1b | **G Stage 0** (filler while Apple processes): the tripwire test — red if `api.deepgram.com` exists in app/ios while `BUILD_RECEIPT.json` says anything but NOT_FLASHED. | 0.5 | Nearly free; makes the local-first violation unshippable by accident. |
| 2 | **H Stages 0+1**: red gate leg while `_READ_ONLY_RE` exists; thread `touches` into the direct lane, `:1527`, `:3129` **and the want-side of `_same_pending`/`_refines_pending`**; persist the channel on job rows; behavioral typed-world-goal-holds test in the same commit. | 1.5 | Closes live bug #2 — the thing a stranger hits the first time they text her. Small worker/core diff lands before E and B churn the same files. |
| 3 | **The measurement build**: C's journal instrument FIRST (speaker-score ListenEvent + the missing Settings export), then A Phase 1 (EnrollmentInvite + onboarding enrollment page + behavioral tejas leg 9 + span refinement *including BufferedLine persistence*), plus **C's `in_meeting` go-ahead guard** (+ TAPE-register `_GO_AHEAD_RE` per FOLLOWUPS item 9). | 2 | Everything the merged field session needs; the guard fix is 0.25d and closes live bug #1 regardless of measurement outcome. |
| 4 | **The merged field session**: A Phase 2 + C's five-condition protocol as ONE cable-installed recording day (owner + one second human; Meet-at-speaker-volume = the Tejas condition). Two scorers, two eval dirs. Scorer reports BOTH raw and stitched shard rates. | 1.5 | One day, two fork-deciding numbers: engine yes/no (spec §8, pre-registered) and tagger on/dark for the stranger build. Screen the recruited stranger's iOS version here too — the engine fork is moot for their week if they're not on iOS 26. |
| 5 | **E — outbound budget** (with required changes): `events.uninvited` flag as the ledger, shared 3/day budget over FYI/clock/parked-ask/digest, busy-defer on the unguarded paths. **The stuck-ask busy-defer is an OWNER DECISION** — it amends the recorded speak-at-once decision (`worker.py:2938-2950`) and `test_backlog_and_delivery` in the same diff, or it gets dropped/scoped to `ASK_QUIET_S` only. Digest gets a reserved budget slot so FYIs can't starve it. Live leg asserts rig owner_ref + rig-only phone. | 3 | Closes live bug #3 before any real-texting week; smaller worker.py diff lands before B's big one. |
| 6 | **D — write-time memory supersession** (nightly reconcile deferred post-week): three-way relation verdict (same/replaces/different), `status`/`superseded_by` columns, confidence finally read in salience, **plus the retired-row fix**: a restatement matching a superseded row with NEWER evidence re-judges against the active occupant (reverse supersession), never silently accrues on the dead row. Keyed eval lives beside done_gate, NOT in tejas_gate. | 2 | Runs during B's shadow soak (disjoint files). First to cut if the calendar squeezes — `forget_fact` is the in-week hedge, taught in onboarding. |
| 7 | **A Phase 3 — SpeechAnalyzer arm** ONLY IF the §8 gate fired AND the stranger's phone runs iOS 26. Built behind the RecognitionEngine seam G specifies — one extraction, ever. | +3–5 conditional | Capture is the floor; but only on measured evidence, and B's shadow must soak on post-fix traffic. |
| 8 | **B — segment-granularity triage**, shadow then flip, with the judges' hardening: (a) `_ambient_verdict` extraction as its own commit with a replay pin proving verdict-identical behavior; (b) **judge-lease idempotency** (lease → model → advance cursor only on successful parse → side effects; stranded leases released) — NOT cursor-advance-before-model, which strands words and stamps false "judged" claims; (c) digit/invention/name guards scoped to the item's cited evidence ordinals, whole segment as context only; (d) rewritten leg 2 keeps a deterministic At-5:15 pin; (e) go-ahead release + stitching organs explicitly specified in segment mode (`_GO_AHEAD_RE` as accelerate-only fast-lane trigger); (f) shadow writes nothing but its diff log; (g) pre-registered soak content (one scripted rig conversation/day) and flip criteria; (h) carries E's `uninvited` stamps through the extracted funnel. Flip commit deletes `shard_too_thin` + rewrites leg 2. | 7–9 + soak calendar | The long pole and the shard tape's declared expiry. Last among builds: needs the quietest tree, H's persisted touches, E's ledger. |
| 9 | **Pre-week freeze + cold-start rehearsal**: every gate green against LIVE (tejas 9/9, done_gate 1–5, outbound_gate, voice_gate verdict applied, testflight_gate for the shipped build), then one full dry-run of stranger onboarding on a fresh account — new owner ref, empty memory DB, Twilio provisioning, welcome text, day-zero interview, enrollment page. **No cluster owned the cold-start path; this step does.** | 1 | The stranger hits this path first; nobody has ever walked it cold. |
| 10 | **THE STRANGER WEEK.** Nothing ships during it. Daily question: was yesterday clean. Journals + events collected daily so a failed week produces the next paired eval, not an anecdote. | 7 (calendar) | done_gate leg 6. |

## Post-stranger queue (in order)

H Stage 2 (frozen corpus eval; can fill soak days) → H Stage 3 (delete
`_READ_ONLY_RE` under the frozen death criterion — **`compute_answer` branch
at `:539` stays forever**: tejas leg 4 pins it and the judge caught the design
contradicting itself) → B's deferred pieces (backfill re-triage, per-segment
memory extraction, cheap gate tier) → D's nightly reconcile → G Stages 1–4
(libopus decode, RecognitionEngine extraction, Deepgram deletion — WER bench
on synthetic/bench clips ONLY, owner audio never goes to Deepgram; single-source
arbitration on SpeakerTagger's ring buffer; pendant tags ship no-verdict until
C's protocol runs over the pendant path) → A's VAD/Smart Turn/envelope fields
(pendant era) → E's moment batcher → C's voice-naming UX + passive coverage
monitor.

---

## Binding cross-cutting decisions (all three judges converged)

1. **Gate-leg registry** — assign once, before any merge: A = tejas leg 9
   (behavioral, not grep). H = leg 10. C = its own `overnight/voice_gate.py`.
   D's keyed eval = beside done_gate (tejas_gate stays offline-deterministic).
   B rewrites leg 2 at flip.
2. **One HARNESS-LAWS ledger edit** registers all three newly-flagged standing
   items together: `_NON_ANSWER` (word-list deciding meaning, worker.py:863),
   `_GO_AHEAD_RE` (FOLLOWUPS item 9, gets TAPE + leg in C's diff),
   `_IRREVERSIBLE_RE` (permanent deny-only backstop: may add a hold, never
   release, failure mode one tap, DO NOT ADD SIBLINGS).
3. **The engine seam is built once.** A Phase 3's SpeechAnalyzer arm and G's
   RecognitionEngine are the same abstraction. Whoever builds first owns the
   extraction of PhoneListener's core; record the seam decision in a plan doc
   before either starts.
4. **worker.py lands small-to-large**: H → E → B; B rebases on their diffs.
5. **The ghost-booking rule binds every live probe** (E leg 4, D's SMS
   round-trip, B's rig conversation, H's probes): migration `1700000016`
   shares phone numbers across accounts, so every probe asserts rig
   owner_ref scoping and a rig-only phone number before posting
   (`done_gate.py:257` is the scar).
6. **Enrollment-page coupling** (A builds it, C gates it): the page ships in
   step 3, but the stranger build's tagger posture is C's gate's verdict,
   enforced through `SpeakerTagger.available` (page self-hides when dark).
   Written into both diffs so neither team "fixes" the other's gate.
7. **is_it_live is one pattern, not five copies**: `testflight_gate.py` and
   the other live-verification legs share a helper with
   `is_the_brain_live.py`.
8. **Canonical checkout**: `harness/tejas-fixes` in `~/Desktop/anticipy-tejas`
   (rebased onto origin 2026-08-24). The `anticipy-omize` folder holds the
   `jose_anticipy_system` lineage — gates run there describe a tree prod
   isn't serving.

## Refused / killed, for the record

- The Brief's literal "unattributed lines must never mint actions" — refused
  as deafness (97% no-verdict measured); the confirmation tap is the
  attribution of last resort. All three judges upheld the refusal.
- Segment-native rewrite of `hear()` — the forbidden rewrite.
- Cloud shadow diarization for attribution ground truth — never-build.
- A Local/Cloud transcription toggle — rule 1 violated on demand.
- VAD now — recovers ~zero words; instrumentation with no consumer.
- Engine-first SpeechAnalyzer migration without the §8 measurement.
- The outbox collection and notify_owner-governance shapes for the budget —
  each re-opens a recorded incident (two-sources-of-truth; post-compose burn).
- Owner audio to Deepgram for the WER bench — the harness may not commit the
  violation its green light is meant to retire.
