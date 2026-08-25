# The echo guard stops guessing from the clock

Answer to `.superpowers/sdd/echo-criticals.md` (review of `f7920b39`). Both
Criticals reproduced, both closed, and the four thresholds the guard used to
decide with are gone rather than narrowed.

**Verdict on the recommended fix: TAKEN.** The lineage signal carries the
weight, and the measurement below is why.

---

## 1. C1 reproduced — the window equalled the debounce, so the guard was unreachable

Driven through the real `TranscriptCursor`, the real `TranscriptFlushPolicy` and
a discrete-event replica of `PhoneListener`'s delivery loop (no tick
quantization: the silence flush fires exactly `utteranceGap` after the partial
that armed it, which is what `asyncAfter(deadline: .now() + utteranceGap)`
does). The recorded 2026-08-17 pair: "yeah I know where it is" is delivered by
the silence timer, the recognizer then replaces its decode window and hands the
same audio back as "yeah I know it is".

```
replay begins at 4.36s — in-task window replacement
--- shipped window 2.6s ---            --- pre-fix window 12s ---
  ROW   4.35s  yeah I know where it is    ROW   4.35s  yeah I know where it is
  ROW   7.16s  yeah I know it is          drop  7.16s  yeah I know it is
        (apart 2.81s)                           (apart 2.81s)

replay at 4.40s -> apart 2.85s   ROW under 2.6s, drop under 12s
replay at 4.60s -> apart 3.05s   ROW under 2.6s, drop under 12s
replay at 5.00s -> apart 3.45s   ROW under 2.6s, drop under 12s
replay at 6.00s -> apart 4.45s   ROW under 2.6s, drop under 12s
task seam (cursor.reset) at 4.40s -> apart 2.85s   ROW under 2.6s, drop under 12s
task seam (cursor.reset) at 5.00s -> apart 3.45s   ROW under 2.6s, drop under 12s
```

Every one of these is the exact defect the guard exists for, escaping. It is
not a "band about 2.7–2.9s"; it is everything the 12s window used to cover, and
the mechanism is arithmetic:

> Row 1 goes out at `lastPartial1 + utteranceGap`. For the duplicate to be a
> separate line at all, its first partial must arrive *after* that instant —
> otherwise it re-arms the debounce and there is only one line. So
> `lastPartial2 > lastPartial1 + utteranceGap`, and since two gap flushes are
> exactly `lastPartial2 - lastPartial1` apart, **`apart > utteranceGap` always**.
> `if apart > window { return false }` with `window == utteranceGap` is therefore
> unreachable for every timer-delivered line there is.

## 2. C2 reproduced — the 3.40s human floor was an artifact of one word per partial

Same cursor, same clock. A 4-word phrase said twice, the second attempt's first
partial arriving 2.61s after the first attempt's last partial. Only the
recognizer's batching changes:

```
  1 word(s)/partial, 2.61s pause -> 3.210s apart
  2 word(s)/partial, 2.61s pause -> 3.010s apart
  4 word(s)/partial, 2.61s pause -> 2.610s apart      <- 10 ms above the window

margin over the shipped 2.6s window, once the recognizer batches: 0.010 s
isEchoOfPrevious(same, same, apart: 2.6, window: 2.6) = true
```

Identical to the reviewer's numbers. The claimed 0.8s margin is 10ms, and
`check("at exactly the window the same words are still the same audio")` pinned
the eaten case as correct.

**C1 and C2 are one fact seen from two sides.** Both populations are delivered
by the same debounce, so both have infimum `apart` = `utteranceGap` exactly.
The suite now measures them side by side and prints it:

```
ok  the closest duplicate and the closest genuine repeat are the same distance
    apart, and only one of them is caught
    (machine 2.6099999999999994s caught=true, human 2.6100000000000003s caught=false)
```

**No width of window separates them.** Widening catches more duplicates *and*
eats more repeats, in the same band, in the same proportion. 12s ate the
tester's second attempt; 2.6s let the recorded duplicate back on the feed. There
was never a value that worked, which is why the fix could not be a better number.

## 3. I4 reproduced — the 4-word floor was unpinned

Against the code as it stood:

| mutation | result |
|---|---|
| `new.count < 4 \|\| old.count < 4` → `< 5 \|\| < 5` | **SURVIVED, 41/41 green** |
| drop `\|\| old.count < 4` | **SURVIVED, 41/41 green** |

---

## 4. The argument for the lineage fix

The reviewer's §8(b) recommendation is right, and the reason it is right is
stronger than "it is more principled": **it is the only signal in the system
that differs between the two populations.**

Measured, driving the real cursor:

```
A. the machine duplicate — was a lineage break raised before it?
   in-task window replacement at 4.36 / 4.40 / 5.00 / 6.00s   YES (all)
   in-task replacement delivered in ONE partial (apart 2.61s)  YES
   task seam (cursor.reset) at 4.36 / 5.00s                    YES

B. the human repeat — was the lineage intact?
   three attempts at one phrase inside one task               no break (3 rows)
   tightest batched repeat there is (apart 2.61s)             no break

C. ordinary speech
   250-word monologue: 11 lines delivered, 0 lineage breaks
```

The direction that matters is airtight by construction, not by sampling: a word
in the cursor's `record` cannot reappear in `pendingWords` unless
`placeBoundary` rejected the text (`didReset`) or the record was wiped
(`cursor.reset()`). **A duplicate line requires a lineage break.** And a person
repeating themselves inside one recognition task breaks nothing — the
recognizer keeps the whole transcript, the record still describes its head, the
boundary is placed past it, and the repeat arrives as ordinary new words.

The three objections the brief told me to test, and what the measurement says:

* *Is it raised on every path?* Yes — both named mechanisms
  (`takePending()` with `recordDescribes == false`, and the task seam), across
  30 driven configurations.
* *Is it raised too often?* No — zero times in 250 words of continuous speech.
* *Is it available where the decision is made?* Yes. `PhoneListener` already
  called `cursor.reset()` itself and already read `update.didReset`. It held the
  fact and never passed it on. That is the whole of the plumbing.

**Arming alone is not sufficient**, and the fix does not pretend otherwise. A
task rotation is uncorrelated with speech, so a break can coincide with genuinely
new words. Two mechanical bounds close that, both reusing constants the file
already owns:

1. **`wordsAppearedAt`** — held audio is replayed into the new request
   synchronously with the seam, so a re-rendering's words appear in the same
   breath as the break, while someone speaking again is seconds or minutes past
   it. Bounded by `utteranceGap`, which is *not* structurally defeated the way
   the window was: appearance time is the one clock the debounce does not push.
   This is the same distinction `cutContinues` already makes.
2. **The mark is consumed by the next delivery**, whatever it is. One break
   answers for one line. A flag with nothing to clear it is a mode.

## 5. What changed

### `app/ios/Anticipy/Audio/TranscriptFlushPolicy.swift`

* **Deleted `echoWindow`.** There is no window anywhere in the file now.
* **`isEchoOfPrevious` is now an instance method** taking `lineageBrokeAt: Date?`
  and `wordsAppearedAt: Date` instead of `apart:`/`window:`. It returns false
  unless a break is open, the words appeared at or after it, and they appeared
  less than `utteranceGap` after it.
* **`addsNoWord(_:beyond:)` replaces the three thresholds.** It answers one
  question with no number in it: does this line contain a word the previous line
  did not already contain, in the order the previous line had them? Gone:
  `new.count < 4 || old.count < 4`, `novel > 2`, `shared/new >= 0.7`.
* **The doc comment the measurements falsified is gone.** The replacement states
  the arithmetic that makes a window impossible, cites the measured 2.61s floors
  for both populations, and names both concrete failures (the eaten second
  attempt, the re-admitted duplicate).

### `app/ios/Anticipy/Audio/PhoneListener.swift` (surgical, 5 sites)

1. `private var lineageBrokeAt: Date?` added.
2. `private var lastDelivered: (text: String, at: Date)?` → `String?` — nothing
   measures elapsed time any more, and a timestamp nobody reads is how the next
   reader concludes there is still a window here.
3. `startRecognition()`: `lineageBrokeAt = Date()` immediately before
   `cursor.reset()` and the orphan replay.
4. The recognition callback: `if update.didReset { self.lineageBrokeAt = Date() }`
   — placed **after** the banked delivery, on purpose. Banked words are words
   the cursor hands over *because* the window died under them; they were never
   sent, and arming in front of them would suppress the one delivery that exists
   to stop speech being lost.
5. `deliver(...)`: reads and clears the mark, then asks the policy with it.
6. `stop()`: clears the mark next to `cutAt = nil`, same boundary, same reason.

Untouched, as required: `utteranceGap` (2.6), `maxHold` (8), the debounce,
`takePending`'s all-or-nothing contract. `minNewWords` still absent, grep guard
intact.

### `app/ios/Tests/run_flush_policy_tests.sh` — a finding demanded it

The findings file says not to touch a runner unless a finding demands it. This
one does: `TranscriptFlushPolicyTests` compiles the policy and the cursor and
**cannot see `PhoneListener`**, so unwiring the lineage signal leaves all 48
checks green while duplicates go back on the feed. Eight legs added, each proven
red (§7). They read a comment-stripped copy of the file, because every sentence
they check for is also written in the prose beside the code it describes.

### `app/ios/project.yml` + regenerated `.pbxproj`

Build 77 → 78 (the runner's own leg 3 demanded it; the pbxproj diff is exactly
the two version lines). `xcodegen generate` was run as the runner instructs;
`build_on_mac.sh` was not.

## 6. Every check, and the mutation that reddens it

48 checks, up from 41. New or rewritten echo checks and their killers:

| check | reddened by |
|---|---|
| a re-decoded sentence is caught however the window was lost (30/30) | M10 word test demands a word-for-word copy (0/30) |
| a person repeating themselves is never eaten, at any rate, pause or batching (116 pairs) | M1 arming removed; M6 lineage discarded, 2.6s window put back |
| the closest duplicate and the closest genuine repeat are the same distance apart, and only one is caught | M1, M6, M10 |
| three attempts at the same test phrase are three rows, not two | M1, M6 |
| a task swap does not eat a sentence spoken long after it | M2 the arming never expires |
| nothing in a 250-word monologue is suppressed | M1, M6 |
| with the lineage intact, identical words are never an echo | M1 |
| a broken lineage catches the same words | M7 word test always says nothing was new (inverse), M10 |
| words that predate the break are never suppressed | M3 drop `age >= 0` |
| the arming ends where an utterance ends | M2, M4 boundary one instant wider, M5 one instant narrower |
| the same sentence re-rendered says nothing new | M10 |
| a new thought is never swallowed | M7 |
| saying more about the same thing says something new | M7 |
| restating a sentence and adding to it says something new | M7 |
| a different request built the same way says something new | M7 |
| the same words in a different order say something new | M8 membership instead of sequence |
| a short repetition says nothing new either | M12 a four-word floor is put back |
| a word said three times is not accounted for by one | M8, M9 drop multiplicity |
| short natural repetition is still left alone with the lineage intact | M1 |
| an empty line is not an echo of anything | M11 empty becomes an echo of anything |
| a re-rendering that splits a word is NOT caught (known miss) | M7 |

All 12 mutations killed. **Two survived the first pass and both were my checks'
fault, not the mutants':**

* `age < utteranceGap` → `age <= utteranceGap` **SURVIVED**. The boundary was
  written `t.addingTimeInterval(policy.utteranceGap)`, which measures back as
  2.6000000000000005 — outside the gap whichever way the comparison is written.
  The check was green for `<` and `<=` alike and pinned neither. Rewritten
  anchored to the reference date so the boundary is exactly reachable.
* dropping `i += 1` (one old word answering for many new ones) **SURVIVED**. No
  check exercised multiplicity. Added "a word said three times is not accounted
  for by one".

## 7. The wiring legs, each proven red

| mutation to `PhoneListener.swift` | leg |
|---|---|
| deliver stops asking the policy at all | RED — "no longer asks the policy whether a line is a duplicate" |
| deliver asks without the lineage break | RED — "judges duplicates without the lineage break" |
| judged on delivery time instead of when the words appeared | RED — "no longer says when the words it is judging appeared" |
| the mark is never cleared — it becomes a mode | RED — "never closes the lineage break it opened" |
| the task seam stops marking the break | RED — "does not mark the lineage break at a task seam" |
| ...and the mark survives only as a **comment** | RED — same leg; the legs read a comment-stripped copy |
| a replaced decode window stops marking the break | RED — "ignores the cursor telling it the window was replaced" |
| the arming is moved **above** the banked delivery | RED — "arms the echo guard before it hands over banked words" |

**Three of these legs passed on their first draft with the thing they name
deleted**, and each failure was the disease the brief warned about:

* the `deliver` body also calls `cutContinues(cutAt:wordsAppearedAt:)`, so a leg
  grepping that body for `wordsAppearedAt: wordsAppearedAt` was answered by a
  *different call four lines below the one it meant to read*. Fixed by flattening
  the whole `deliver` body and pinning the argument adjacent to `lineageBrokeAt:`.
* `startRecognition` encloses the entire recognition callback, so an awk range
  over it also contains the nested `self.lineageBrokeAt = Date()`. The seam leg
  passed with its own line deleted, answered by the one inside the closure.
  Fixed by anchoring the indent, the way the `cutAt = nil` leg already does.

## 8. Law 1 disposition — item #54 is closed, and no tape is owed

`research/2026-08-24-law1-audit.md` item **#54** names
`TranscriptFlushPolicy.isEchoOfPrevious` a VIOLATION, severity H, for
`shared/new.count >= 0.7`, `novel > 2`, `count < 4` and the 12s window, on the
ground that "the line is never delivered — not to the backend, not to the brain,
not to the transcript UI".

**All four named constructs are deleted.** What decides now:

* `lineageBrokeAt` — an event this file caused (`cursor.reset()`) or was told
  about (`update.didReset`). Not a reading of wording. Senses.
* `wordsAppearedAt` vs `utteranceGap` — a timestamp against the file's own
  utterance boundary, the same arithmetic `cutContinues` and `flushReason`
  already use. Senses.
* `addsNoWord(_:beyond:)` — carries **no threshold, no count, no ratio, no word
  list, no regex**. It asks whether the recognizer returned a token it had not
  already returned, which is duplicate-detection on the transport, and it only
  runs when the machine has already said its send record is gone.

The audit's objection to `novel > 2` and `shared/new >= 0.7` was that they decide
whether a line "says little the last one did not" — a judgment about content, on
a sliding scale, applied to every line. Subsumption has no scale to slide: a line
that contributes one word of its own is delivered, always. The suite's own
conceding case name is retired with the threshold that made it necessary.

**No `TAPE:` comment, no `overnight/tape_gate.py` entry, no ledger line** —
because nothing here is a string-level patch standing in for a real fix. This
*is* the Law-5 fix: the sense (the lineage break) was the thing that was missing,
and the rule written while it was unavailable was tape by definition. `tape_gate`
still reports the same 5 registered items and the same census; I added nothing to
it.

If a reviewer disagrees and rules `addsNoWord` a Law-1 construct, the honest
consequence is registration, not deletion — but I do not think the argument
survives contact with the code, because there is no number in it to argue about.

## 9. What is not fixed, and what needs a device

**Law 3: none of this is proven. It has never run on a phone against a real
voice.** Everything above is the real cursor and the real policy driven by a
simulated recognizer at a simulated clock. Repo-green is not done. What a device
run has to check, in this order:

1. **Say a phrase, watch for the row, say it again, say it a third time.** Three
   rows. This is the defect that started it.
2. **The 2026-08-17 shape**: talk continuously long enough for the ceiling to
   fire, then let the recognizer collapse. One row per sentence, no repeats.
3. **Whether `update.didReset` fires on a real re-render as it does here.** This
   is the single assumption the whole fix rests on. `ListenJournal` already
   records swaps; a device run should confirm a break is marked before each
   observed duplicate.
4. **Whether a real recognizer batches** the way §2 models. If Apple never hands
   a phrase over in one partial, C2's 10ms margin was theoretical — but C1 is
   unaffected either way, and the fix does not depend on it.

**Residuals, stated rather than buried:**

* **A task swap landing within one utterance gap of the words appearing, on a
  line that adds no word at all beyond the previous one, is still eaten.** Both
  conditions must hold. This is the narrowed remnant of the old failure and it
  cannot be closed with what the policy can see; closing it properly needs
  `SFTranscriptionSegment.timestamp` correlated against `requestBornAt` to prove
  the audio predates the seam, which is device-only work and much larger.
* **A re-rendering that splits a word** ("it is" → "it's") produces a token the
  first rendering never had and survives. Safe direction, pinned by a check
  rather than left to be rediscovered.
* **`PhoneListener.stop()` emits the parting tail through `onLine?` directly**,
  bypassing `deliver` and so the guard entirely. Pre-existing, flagged by the
  reviewer, and arguably correct — pressing Stop must not delete what you just
  said. Untouched.
* **If any line is delivered between the break and the duplicate**, the mark is
  consumed and the duplicate escapes. Safe direction, deliberate.

## 10. Gate results

```
sh app/ios/Tests/run_all.sh          -> iOS logic gate: all suites passed
                                        (TranscriptFlushPolicy: all 48 checks passed)
xcodebuild ... -configuration Release -> ** BUILD SUCCEEDED **
python3 overnight/tape_gate.py        -> unchanged: red at leg 2, census 5/5
                                        (pre-existing brain/ tape; nothing added)
```
