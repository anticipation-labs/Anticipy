# The instrument asked whether a transcript was about the right script, never whether it was about all of it

Fixes for the four Criticals in `.superpowers/sdd/agc-criticals.md`, against
`76ca23ad`'s `proof/engine_or_audio.py`. Scope: `proof/` and `tests/`.

`proof/engine_or_audio.py` settles one question — is Anticipy's transcription
problem the speech engine, or the audio path in front of it? A wrong answer
costs weeks either way. Its arithmetic was already good: fluent hallucinations,
reversed scripts, alphabetised words, stutters and empty files all bounced. But
it could be made to print a confident, wrong headline four ways, all from
plausible operator or tooling error.

**Law 3, first and plainly: none of this is proven. No recording exists.** Every
number below is arithmetic over text files. A green suite here is evidence that
the stick is straight, not that anything has been measured. See §7.

---

## 1. The shape, and why four patches would have been the wrong fix

The reviewer's diagnosis is worth more than the four findings:

> the instrument's refusals all ask *"is this transcript about the right
> script?"*, and none asks *"is this transcript about **all** of it, and did the
> two cells I am about to subtract actually come from different recordings?"*

That is one gap with two halves, and every one of the four Criticals is an
instance of one half:

**Half one — EXTENT.** Every refusal at `76ca23ad` was an *identity* test.
`MIN_SCRIPT_SHARE` asks what fraction of the transcript is script material.
`MAX_INSERTION_RATE` asks whether it is too long. `MIN_REFERENCE_WORDS` asks
whether the script is long enough. All four are satisfied completely by a
transcript that is a perfect, verbatim, 100%-script-material recording of the
*first quarter of the page* — and by the single word `you`.

Two things were missing, and they are the same thing measured on two axes:

- **How far the evidence reaches.** The operator read the whole page; that is
  what makes the script a reference. A transcript whose survivors stop 25% in
  is not a measurement of a starved microphone, it is a recording that stopped,
  a truncated write, a partial from `SFSpeechURLRecognitionRequest`, or a
  microphone that died halfway. Four different bugs, one shape, and the honest
  answer is to name them and refuse. → `MIN_REFERENCE_SPAN`.

- **How much evidence there is.** `script_share = matched / len(hyp)` is a
  proportion estimated from a sample of size `len(hyp)`, and *nobody sized the
  sample*. At `len(hyp) = 1` it carries no information: `you` is 100% script
  material. The module already contains this exact sentence about the other
  side of the pair — *"below this many reference words a capture rate is noise
  with a decimal point"* — and it was never said about the transcript.
  → `MIN_TRANSCRIPT_WORDS`, deliberately the same number, 20, for the same
  reason.

**Half two — PROVENANCE.** Every rule in the file is a *subtraction*. R2 is
reference minus app. R3 is arm B minus arm A. R4 is with-vocabulary minus
without. Not one of them asked whether the two operands came from different
recordings. Nothing in the *text* can answer that question, which is why the
report conceded the arm swap as undetectable and why C4(b) is genuinely
undecidable from bytes: a biasing setting that truly does nothing, on a
deterministic decoder over one WAV, produces character-for-character the same
output as a toggle nobody wired.

The fix is the one M11 pointed at: **the scratch recorder does not exist yet, so
its output contract is still free to require a provenance line.** One line at
the top of each transcript naming the arm, the decoder, and the SHA-256 of the
source WAV. From it, three things become checkable that no arithmetic ever
could — the cell is filed under the arm it was recorded in; two cells of one arm
decoded one WAV; two cells of different arms did not.

### Why this is a shape fix and not four patches

Each half generalises past the instance that revealed it, and the tests prove it
rather than asserting it:

| Attack | Reported as | Caught by | Was it in the findings? |
|---|---|---|---|
| First 92 of 370 words | C1 | span | yes |
| **Middle 110 words of 370** | — | span | **no** |
| **Last 25% only** | — | span | **no** |
| `you` | C2 | transcript floor | yes |
| `Thank you.` | C2 | transcript floor | yes |
| **`you` × 8 — a decoder looping on silence** | — | transcript floor | **no** |
| Same bytes, `sf_ctx` vs `sf_noctx` | C4(b) | provenance | yes |
| **One WAV decoded twice, filed as arm A and arm B** | — | provenance | **no** |
| **Arm A's transcript filed under arm B** | M11 (conceded) | provenance | conceded undetectable |
| **`sf_ctx` and `sf_noctx` decoded from *different* WAVs** | — | provenance | **no** |
| **Reference decode copied into the app's cell** | — | provenance | **no** |
| **`sf_noctx` filed under `sf_ctx`** | — | provenance | **no** |

Six of the twelve were never reported. They fall out of the two rules for free,
which is the test of whether the shape was fixed or the symptoms were.

---

## 2. The four wrong headlines, reproduced then refused

Each reproduced against the shipped 370-word `proof/fixtures/read_aloud_script.txt`.

### C1 — a truncated app transcript convicts the engine

`A/sf_ctx` = the script's first 92 of 370 words (a partial result, or a
truncated write from a recorder nobody has written). `C/reference` 0.94,
`A/reference` 0.82.

**Before:**

```
A/sf_ctx from first 92 of 370 words:
  unalignable: False  capture: 0.2486  share: 1.0  longest_run: 90  matched_in_runs: 0.978
  R2 True | reference 0.82 against the app's 0.25 — a gap of 0.57 ...
  HEADLINE: ENGINE AT FAULT - the audio was decodable and the app's recognizer
  did not decode it. The §8 migration is justified on evidence.
```

**After:**

```
  VERDICT: CANNOT DECIDE
  the §8 engine migration is not licensed by this run.
  R2: fired=None
  A/sf_ctx: REFUSED — the surviving words reach across 25% of the script, under
  the 70% floor — this transcript is about part of the page, not the page. A
  recording that stopped early, a truncated write, a decoder that returned a
  partial and a microphone that went deaf halfway are one shape from here.
  Split the file, or say in the manifest what was actually read
```

The finding noted that the harness *already computed* the discriminating
evidence — `longest_run 90`, `matched_in_runs 1.00` — and marked it
"DIAGNOSTIC ONLY — no rule reads either number." A rule reads one now, and the
`span` column is printed beside capture in every report.

### C2 — one word defeats the empty-transcript refusal

**Before:**

```
  'you'                              unalignable=False capture=0.0027 share=1.0
  'Thank you.'                       unalignable=False capture=0.0027 share=0.5
  HEADLINE: AUDIO PATH AT FAULT - a strong decoder loses the same words off the
  same file. Fix the front end; do not migrate the engine.
  R1 fired=True — "the reference decoder captured 0.00 ... at or under the 0.45 ceiling"
```

**After:**

```
  'you'                              unalignable=True capture=None
  'Thank you.'                       unalignable=True capture=None
  'you you you you you you you you'  unalignable=True capture=None
  VERDICT: CANNOT DECIDE
  A/reference: REFUSED — the transcript is 1 words against a 370-word script,
  under the 20-word floor. A dead recognizer emits a canned phrase — 'you',
  'Thank you.' — and it is 100% script material by accident. Below this floor
  the script-share check that separates a wrong file from a starved microphone
  has nothing to measure
```

### C3 — a missing measurement prints as a decided verdict, with a false reason, exit 0

Control credible, `A/reference` 0.82, `A/sf_ctx` absent.

**Before:**

```
  HEADLINE: INDETERMINATE - the reference decoder landed between the two
  pre-registered thresholds. Neither conclusion is available; this is the
  answer, not a rounding opportunity.
  decidable: True  => exit 0
  R1 False | ... 0.82 ... above the 0.45 ceiling
  R2 None  | A/sf_ctx is missing from the run
```

0.82 is *above* the 0.75 floor, so the printed reason is factually false about
the number printed two lines above it. This is verbatim the sin the function's
own docstring at `:493` forbids — *"Collapsing None into False is how a missing
measurement becomes a claim."*

**After:**

```
  VERDICT: CANNOT DECIDE
  decidable: False => exit 1
  R2 None | A/sf_ctx could not be aligned: no transcript at 'arm_a/sf_ctx.txt'
```

The headline chain was `R1 is None and R2 is None`; it is now `or`. But `or`
alone would have withheld a sound conclusion, so R2 was also made
**determinate where the missing cell cannot change it**: with the reference at
0.40, R2's first clause has already failed on a cell that *is* present, so no
value the absent one could take fires R2. That case still answers:

```
  HEADLINE: AUDIO PATH AT FAULT | R1: True | R2: False
```

That distinction — a measurement that does not matter versus a measurement that
decides the verdict — is exactly what the `:493` docstring asks for, and only
the second is None now.

### C4 — R4 has no positive control and fires hardest when least entitled

**(a) Before** — starved arm, names 0/26 both sides:

```
  R1 True | the reference decoder captured 0.40 ... at or under the 0.45 ceiling
  R4 True | names came through 0.00 with the vocabulary and 0.00 without (+0.00, band 0.1)
```

The outcome the experiment expects mechanically manufactures the vocabulary
finding.

**After:**

```
  R4 None | neither decoder heard a single one of the 26 vocabulary mentions.
  Zero against zero is not 'the biasing changed nothing', it is 'nothing was
  heard for the biasing to change' — and if R1 fired, that is what this arm is
  telling you
```

**(b) Before** — `arm_a/sf_ctx.txt` and `arm_a/sf_noctx.txt` the same bytes,
because the toggle was never wired:

```
  R4 True | names came through 0.35 with the vocabulary and 0.35 without (+0.00, band 0.1)
```

**After:**

```
  R4 None | A/sf_ctx and A/sf_noctx are byte-identical and neither says which
  recording it came from. A toggle that was never wired and a setting that
  genuinely does nothing produce the same bytes, and only the provenance line
  separates them
```

And with the provenance line present, naming two decoders and one WAV, the same
identical bytes are read as the real finding they would then be:

```
  R4 True | names came through 0.35 with the vocabulary and 0.35 without (+0.00, band 0.1)
```

That asymmetry is the whole point. A byte comparison alone would have
suppressed the true positive along with the false one.

---

## 3. Every check, and the mutation that proves it

**61 mutations applied one at a time to `proof/engine_or_audio.py` and
`proof/reference_decode.py`; every one turns `tests/test_engine_or_audio.py`
red. Zero survivors.** The reviewer found eight silent survivors among threshold
comparisons alone, so five rounds were needed — the first pass left five
survivors, and each is recorded below because *how* they survived is the useful
part.

### The new refusals

| Check | Mutation | Killed by |
|---|---|---|
| `MIN_REFERENCE_SPAN` | floor removed | `test_a_transcript_holding_only_the_top_of_the_page_is_refused` |
| | comparison inverted | `test_the_span_floor_is_a_boundary_not_a_direction` |
| | floor loosened by 0.5 | same |
| | `_span` back to raw first/last | `..._top_of_the_page_is_refused` |
| | `SPAN_TRIM` 0.10 → 0.40 | `test_the_thresholds_are_pinned...` (see §4) |
| `MIN_TRANSCRIPT_WORDS` | floor removed | `test_one_word_is_refused_for_the_reason_zero_words_is` |
| | inverted | `test_the_transcript_floor_is_a_boundary_not_a_direction` |
| | off by one | same |
| C3 headline chain | back to `and` | `test_a_missing_app_cell_that_decides_the_verdict_cannot_decide_it` |
| C3 R2 determinacy | collapsed to None | same |
| | fires False even when the gap decides | `test_a_missing_app_cell_that_cannot_change_the_verdict_does_not_block_it` |
| `decidable` | hardcoded True | `..._that_decides_the_verdict_cannot_decide_it` |
| exit code | always `return 0` | `test_the_exit_code_contract_is_what_the_docstring_says_it_is` |
| `MIN_NAME_HITS_EITHER_SIDE` | control removed | `test_an_arm_that_heard_no_names_at_all_cannot_call_the_vocabulary_inert` |
| | inverted | `test_the_same_name_rate_..._calls_it_inert` |

### Provenance and distinctness

| Check | Mutation | Killed by |
|---|---|---|
| R4 distinctness | not consulted | `test_two_cells_that_are_one_file_cannot_be_subtracted` |
| R3 distinctness | not consulted | `test_one_recording_filed_as_two_arms_is_caught_by_its_hash` |
| R2 distinctness | not consulted | `test_the_reference_and_the_app_cell_must_also_be_two_decodes` |
| byte-identity | never reported | `..._one_file_cannot_be_subtracted` |
| provenance excuse | removed (identical bytes always refused) | `test_a_provenance_line_lets_a_genuinely_inert_setting_still_be_reported` |
| arm check | not called / arm compared to itself | `test_an_arm_swap_is_caught_by_the_line_the_recorder_writes` |
| decoder check | decoder compared to itself | `test_a_transcript_filed_under_the_wrong_decoder_is_caught_too` |
| same arm ⇒ same WAV | not reported | `test_two_cells_of_one_arm_scored_from_different_recordings_are_refused` |
| different arms ⇒ different WAV | not reported | `test_one_recording_filed_as_two_arms_is_caught_by_its_hash` |
| line stripped before scoring | left in the text | `test_the_provenance_line_is_not_scored_as_words_the_decoder_invented` |
| `reference_decode` writes the line | not written | `test_decode_stamps_the_line_onto_the_file_it_writes` |
| shared `PROVENANCE_PREFIX` | restated locally | `test_the_reference_decoder_writes_the_provenance_line...` |
| arm read off the path | guessed as "A" | `test_the_arm_is_read_off_the_path_and_never_guessed` |
| WAV hash | replaced by the filename | `..._writes_the_provenance_line...` |

### The validity gate (I7)

| Check | Mutation | Killed by |
|---|---|---|
| `MIN_CONTROL_SCRIPT_RATIO` | removed / inverted | `test_a_short_control_does_not_calibrate_a_decoder_for_a_long_script`, `test_the_control_script_ratio_is_a_boundary_not_a_direction` |
| `MAX_RECORDING_ATTEMPTS` | removed / inverted | `test_a_control_re_recorded_until_it_cleared_is_a_maximum_not_a_measurement`, `test_the_attempt_ceiling_is_a_boundary_not_a_direction` |
| unrecorded count | assumed to be 1 | `test_an_unrecorded_attempt_count_is_not_assumed_to_be_one` |
| scaffold writes it | key renamed | `test_the_scaffold_writes_the_attempt_count_it_requires` |
| load_run stamps it | hardcoded 1 | `test_the_manifests_attempt_count_reaches_the_rule_that_reads_it` |

### The pre-registered document (I5)

| Check | Mutation | Killed by |
|---|---|---|
| `explain()` numbers | advertise a 0.60 control floor while enforcing 0.85 | `test_the_printed_rule_quotes_the_numbers_the_code_enforces` |
| | drop any threshold from the document (5 tried) | same |
| | hardcode an extra number beside a real one | same |
| `HEADLINE_MEANING` | AUDIO PATH AT FAULT reversed to "Migrate." | `test_the_verdict_sentences_are_pinned_because_reversing_one_costs_weeks` |
| `HEADLINE_LICENSES_MIGRATION` | booleans swapped | `test_what_each_verdict_licenses_is_pinned_like_the_thresholds_are` |
| rendered instruction | printed for the wrong headline | `test_the_printed_instruction_follows_the_rule_that_actually_fired` |

### The eight comparisons that survived inversion at `76ca23ad`

All eight, plus five more, now die. `test_every_threshold_comparison_is_pinned_at_its_own_boundary`
and `test_the_script_share_floor_and_its_exemption_are_boundaries` carry a pair
either side of each: control credibility `>=`, R1 `<=`, R2's floor `>=`, R2's
gap `>=`, R3 `>=`, R4 `<`, script share `<`, anchor exemption `<`, insertion
ceiling `>`, R4's mention floor, the span floor, the transcript floor, the
attempt ceiling.

**Two of those needed a second attempt, and the reason generalises.** R3's and
R4's inversions survived the first version of the boundary test because
`0.45 - 0.30` is `0.15000000000000002` in binary floating point — it clears both
`>=` and `>`, so it pins neither. The deltas now land *exactly* on the constant
(`0.0` against `AGC_WIN_MARGIN`). Any boundary test written by subtracting two
decimal literals is worth re-checking for the same reason.

### The other three first-pass survivors

- **`SPAN_TRIM` 0.10 → 0.40 survived** because `_span` rescales by the trim, so
  widening it barely moves a uniformly-spread transcript. A constant with no
  behavioural signature is precisely the constant a later session can move
  without anything going red, so it is pinned by declaration in the thresholds
  test, with a comment saying why.
- **`load_run` stamping a constant `attempts = 1` survived** because every rule
  test builds its cells by hand. Covered end to end now: the number the operator
  writes in the manifest must reach the gate.
- **The decoder-name check turned into `pass` survived** (also M12) — it had no
  cover at all. `test_an_unknown_decoder_in_a_manifest_is_rejected_not_ignored`.

### Also fixed, cheaply, because they undermined the above

- **M12: `align`'s `ValueError` escaped `load_run`** as a traceback (only
  `FileNotFoundError` was caught). A refusal that crashes the harness is a
  refusal nobody reads. `test_an_absurdly_large_transcript_is_refused_not_raised`.
- **I9: `--scaffold` wrote nine cells** while the protocol listed five flat
  names, two of the nine being `speech_transcriber` cells the protocol never
  mentions. A correctly-run experiment printed **four REFUSED lines that were
  normal** — which trains the reader to skim past REFUSED. Every refusal added
  above depends on a human noticing exactly that word. `--scaffold` now lays out
  the five cells a rule reads and nothing else, and
  `test_the_scaffold_lays_out_only_cells_a_rule_actually_reads` asserts a
  complete run prints **no** REFUSED line at all.
- **I10, partly:** arm B's protocol row omitted "screen up". Orientation selects
  which handset mic dominates, so the A-vs-B difference would have been partly
  the setting and partly the phone's attitude. Documentation only.

---

## 4. The three judgement calls

### C2 — where the honest floor is, and what it costs

The empty-transcript refusal's rationale is *"a dead recognizer and a wrong file
look identical from here."* That sentence is exactly as true at one word as at
zero, and at eight. The line was drawn at the single point where the confusion
cannot occur, not at the point where it stops.

I did **not** draw the new line at a word count chosen to defeat `"you"`. The
honest framing is that `script_share` is a proportion over an unsized sample,
and the file already contains the same argument about the reference side:
*"Below this many reference words a capture rate is noise with a decimal
point."* `MIN_TRANSCRIPT_WORDS = 20` is that sentence said about the transcript,
at the same number, for the same reason — and it kills `"you"`, `"Thank you."`,
`"Thanks for watching!"` and a decoder emitting one canned word eight times,
none of which were chosen for.

**What it costs, stated rather than hidden:** against the shipped 370-word
script the harness can no longer report a capture below about **0.054**. Every
threshold the decision rule reads sits above 0.30, production's observed 42 wpm
against 130–160 natural is ~0.27, and R1's ceiling is 0.45. The instrument keeps
full resolution across the entire decision-relevant range and gives up only the
region where it could not tell a starved microphone from a dead one.
`test_the_floor_still_leaves_the_whole_decision_range_measurable` asserts that,
so if a threshold ever moves down toward the floor, it goes red.

**One protected test changed, deliberately.**
`test_a_catastrophically_starved_recording_is_still_scored_not_refused` used a
fixture of *four words out of sixty — the reference's first four*. That shape is
not starvation, it is truncation, and it is C1 in miniature: reading it as "the
microphone captured 7%" is the exact confusion this work exists to close. Four
words is on the same side of the line as zero, not the same side as
30%-in-three-word-bursts.

The **property** the test protects — *a catastrophic capture is a finding, not a
reason to refuse* — is preserved, at a scale where the evidence exists: 22 words
out of 300, spread the whole way down the page, capture 0.073, scored, not
refused. And the old fixture's shape now has its own test asserting it is
refused. This is the one place I changed something on the do-not-regress list,
and I would rather flag it loudly than quietly weaken a rule to keep a fixture.

### I5 — how the printed rule and the printed conclusion get pinned

Adding more string assertions would be the same disease: a test that lists the
strings drifts with them. Three mechanisms instead, in decreasing order of how
structural they are.

1. **`explain()` is checked against the code it documents, not against a list.**
   Every number the rule branches on must appear in the printed document, and
   every *decimal* printed must be one of them. Hardcoding `0.60` while the code
   enforces `0.85` fails both legs: it removes a value that must be there and
   adds one that must not. It survived the first draft in one place —
   `MIN_REFERENCE_WORDS` and `MIN_TRANSCRIPT_WORDS` are both 20 by design, so
   *"does 20 appear?"* was satisfied by either alone — so the check counts
   occurrences and demands one per distinct constant.

2. **The one bit that costs weeks is a boolean, and the operator's instruction
   is generated from it.** `HEADLINE_LICENSES_MIGRATION` maps each headline to
   *does this license the §8 migration?* — `False`, `True`, `None`, `None` —
   pinned literally beside the nine thresholds, and `render()` prints
   *"the §8 engine migration is NOT licensed by this run"* from the boolean, not
   from the prose. The prose can no longer be the only thing carrying direction.

3. **The two decisive sentences are pinned literally**, by the same standard as
   the numbers, in a test named
   `test_the_verdict_sentences_are_pinned_because_reversing_one_costs_weeks`.
   Brittle to rewording on purpose: rewording is exactly the act that should be
   visible in a diff.

And `test_the_printed_instruction_follows_the_rule_that_actually_fired` drives
two real runs off disk to the printed line, so the test cannot agree with a
reversal by reading the same dict the code reversed.

### I7(b) — the protocol, the code, or both

**Both**, and the code is load-bearing because a written instruction is not a
constraint.

`RECORDING-PROTOCOL.md:82-86` told the operator in writing to re-record arm C
until it cleared. A pass/fail on decoder credibility that may be retried without
limit or record is a maximum over attempts, not a measurement. It also had no
symmetric guard: **re-recording arm A until it reads like the expected finding
is the same act pointed at the conclusion**, which the finding did not mention
and which the fix covers.

- **Code.** `manifest.json` carries `attempts` per arm; `--scaffold` writes it as
  1; every rule reading a cell from an arm recorded more than
  `MAX_RECORDING_ATTEMPTS = 2` times is blocked with a reason that says so. **An
  absent count blocks too** — "nobody wrote it down" and "the ninth try" are the
  same evidence from here, and defaulting to 1 would be the assumption the whole
  refusal exists to refuse.
- **Ceiling of 2, not 1.** The protocol legitimately tells the operator to
  restart a take when they lose their place. That is a retake for a fumbled
  *read*; a retake because the *score* was low is p-hacking. Nobody can separate
  them afterwards, so the rule allows exactly one honest retake and refuses
  beyond it.
- **Protocol.** The "re-record C" instruction is gone. CANNOT DECIDE now names
  **two** live explanations — the recording, *or* the reference decoder being
  `whisper base` where §11 asked for large-v3 — and step 2 is
  `--allow-download`, not another take. The reviewer's separate note stands: the
  protocol never told the operator the reference decoder was a compromise and
  never had them run `reference_decode.py --check`. It does both now.

---

## 5. Left for another tree

- **`overnight/tejas_gate.py:381-392`, leg 7 — out of scope and named as such.**
  It greps `PhoneListener.swift` for the literal `contextualStrings` and for
  `Anticipy` within 400 characters, then reports *"the recognizer is taught its
  own vocabulary"* — a behavioural claim a substring search cannot support. It
  has been asserting an unverified belief since it was written, on a board
  CLAUDE.md tells the owner to *"run and believe"*. **Leg 7's message should say
  what it actually proves — that the string is present in source — today**, not
  conditionally on R4.

  **And R4 as built cannot settle it.** C4(b) is why: the strongest R4 signal
  was indistinguishable from a harness that never turned the toggle on. That is
  now fixed *for a run whose recorder writes the provenance line* — which no
  recorder yet does. Treating "R4 fired" as the trigger to flip leg 7 red would
  swap one unverified green for one unverified red.

- **The scratch iOS recorder itself** (`app/ios/**`). Section 3 of
  `.superpowers/sdd/agc-harness-report.md` specifies it; **its output contract
  now has a fifth requirement**: each transcript opens with
  `#anticipy: arm=<A|B|C> decoder=<sf_ctx|sf_noctx|...> wav=<name> sha256=<hex>`.
  `proof/reference_decode.py` already writes exactly that line for the cells it
  produces, so the format has a working reference implementation.

- **I8 — an in-order duplicating decoder** (`:443`). A reference containing the
  script twice scores capture 1.00 with insertion rate *exactly* 1.00, and the
  refusal is `>`, so it passes. I did **not** change `>` to `>=`: the same
  signature is produced by a decoder that stutters every word, which the
  do-not-regress list explicitly protects as scored, with all three numbers
  printed side by side as the designed mitigation. `longest_run` does not
  separate them either (both give a full-length run). The boundary is now
  *pinned* by `test_the_insertion_ceiling_is_pinned_at_exactly_the_ceiling`, so
  it cannot be inverted silently, but **the hole is real and unclosed**:
  separating a loop from a stutter needs timestamps, which the text contract
  does not carry.

- **I10 — n=1 per arm, fixed order, no counterbalancing.** Recording A, B, A, B
  would turn both the drift confound and the swap hazard into detectable
  inconsistencies for ten extra minutes. Only the "screen up" omission is fixed;
  counterbalancing is a protocol redesign I did not make unilaterally.

- **M13 — §11 deviations.** Unchanged: two people and the ten-minute duration
  are still undisclosed deviations, and R2's second clause as a ≥0.30 *gap*
  fires at 0.95-vs-0.60 where §11's text would not.

---

## 6. What did not change, and was checked

Every attack in the findings' "could not break" list still bounces: fluent
hallucination at 369 and at 90 words; 370 and 120 random draws from the script's
commonest words; the script alphabetised, reversed, and paragraph-shuffled;
capture held at exactly 0.686 across 1×, 2× and 3× chatter; every word doubled
scoring 1.00/1.00/1.00 side by side and tripled refused; empty, whitespace-only
and punctuation-only refused; a reference under 20 words refused; the 0.70
measurement on a pair built to lose exactly 30%; the three-word-burst 0.30; the
two-objective alignment claim in both directions including `ebdce`/`bbebed`; a
half-finished run naming its missing path; an unknown arm rejected. A complete,
honest run still prints ENGINE AT FAULT, or AUDIO PATH AT FAULT, with no refused
cells and every rule fired True or False.

The one exception is the 4-of-60 fixture, argued in §4.

---

## 7. Law 3 — this proves nothing

**No recording exists.** Everything above is arithmetic over synthetic text
files, exercised against fixtures a person wrote. Nothing here has measured the
phone, the engine, the microphone, or production, and a green suite is evidence
that the stick is straight — not that anything has been weighed.

Specifically unproven until real audio runs through it:

- **Whether `MIN_REFERENCE_SPAN = 0.70` is the right floor.** It is set from an
  argument (the operator reads the whole page, so real survivors reach the end)
  and checked against synthetic spreads. A real starved recording might drop the
  last few sentences for reasons that are the finding rather than a filing
  error — in which case this refuses a true positive, and the report will say
  "part of the page" when the honest answer is "the microphone gave up at
  minute two." That is a refusal, not a wrong headline, and it names the four
  possibilities so the operator can look. **But it is the fix most likely to
  need adjusting after the first real run, and the first run should be read with
  that in mind.**
- **Whether `SPAN_TRIM = 0.10` absorbs enough tie-break scatter.** Measured on
  one real case — the shipped script against its own first 92 words, where the
  scatter is a couple of words. A different script could scatter more.
- **Whether `whisper base` clears the control at all.** If it does not, every
  rule above is untested against real numbers and the answer is a bigger model,
  not another take.
- **Whether the provenance line is ever written.** The recorder does not exist.
  Until it does, C4(b) and the arm swap are caught *for reference cells only*,
  and a run made entirely by hand can still put one file in two places without
  the harness being able to tell.
- **Everything the reviewer's own §5 said:** a read-aloud arm cannot measure the
  failure §4(b) describes — production's missing words come from a room with two
  people and long silences, and a single reader at a steady pace is easier audio
  than that. A good score on arm A does not exonerate the capture path under
  real conversational conditions.

---

## 8. Files

- `proof/engine_or_audio.py` — the instrument.
- `proof/reference_decode.py` — now writes the provenance line for the cells it
  produces, sharing `PROVENANCE_PREFIX` rather than restating it.
- `proof/RECORDING-PROTOCOL.md` — one naming scheme, the attempt count, the
  provenance line, the second explanation for CANNOT DECIDE, "screen up" on B.
- `tests/test_engine_or_audio.py` — 86 tests, 61 mutations, 0 survivors.

`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q --ignore=tests/test_day_zero_oracle.py -p no:cacheprovider`
→ **1432 passed, 1 failed**. The one failure is
`tests/test_earls_live_failures.py::test_needs_user_questions_are_never_swallowed_into_fallback`,
which asserts over `extension/agent_loop.js` — a file another agent is
modifying in this working tree, and which was already failing before any change
here. `tests/test_engine_or_audio.py`: **86 passed**.
