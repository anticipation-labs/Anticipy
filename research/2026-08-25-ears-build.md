# EARS — the turn envelope, built

**Date:** 2026-08-25
**Branch:** `jose_anticipy_system`
**Spec:** `docs/superpowers/specs/2026-08-25-ears-turn-envelope.md` (606 lines, `12fb9989`)
**Build:** 88 (from 87; `project.yml` and the pbxproj agree)
**Card:** EARS — finish the ears (capture that judges at thought-close)

---

## 1. What shipped

The spec's three-value subset, whole. No new column, no migration, no server
change.

| Value | Was | Is |
|---|---|---|
| `capture_started_at` | the flush instant | `wordsAppearedAt` — when the words first went unsent |
| `capture_ended_at` | the same flush instant, aliased | the flush instant, as a genuinely distinct value |
| `spoken_at` | the same flush instant, aliased | the older name for the START, so two readers of one row agree |

New pure type: **`app/ios/Anticipy/Audio/CaptureEnvelope.swift`**. It owns which
column gets which instant, and it is the ONE construction rule (`CaptureEnvelope.of`)
used by the live push and the offline flush alike — because two paths building
envelopes two ways is how a buffered line and a live line come to mean different
things, and the buffered ones are exactly the rows this work exists for.

Threaded through all four delivery sites and the on-disk queue:

- `Audio/PhoneListener.swift` — `onLine` and `onSpeaker` widened from three
  arguments to four (`line, startedAt, endedAt, continuesPrevious`); both
  `deliver` call sites now pass `wordsAppearedAt` **and** `now`.
- `Audio/PhoneListener.swift` — the **parting tail at session stop**, which
  bypasses `deliver` entirely and used to hand over `Date()` as start and end at
  once. It is the last line of every session, and it is the site a
  signature-driven refactor fixes by hand and forgets.
- `AnticipyApp.swift` — `heard(... at:endedAt:)`; `BufferedLine.endedAt: Date? = nil`;
  the offline flush rebuilds the envelope from both stored optionals.
- `Backend/AnticipyBackend.swift` — `pushEvent` takes a `CaptureEnvelope?` and
  stamps nothing itself.

### Why `endedAt` on the queue had to be an optional with a default

`unsent`'s getter answers a failed decode with `?? []`. A required field there
does not warn — on the first launch after the update it would silently DELETE
every line a person spoke while offline, from a product whose whole promise is
remembering. There is a law leg on this.

### One hazard found while building, not in the spec

Two instants a few hundred milliseconds apart (a short banked-words delivery)
render as the **same string** under a whole-second ISO8601 formatter. The row
then arrives indistinguishable from the aliasing bug, with every Swift check
still green. `ISO8601DateFormatter.anticipyUTC` does carry
`.withFractionalSeconds` today; there is now a law leg pinning that, and a pure
check that proves the hazard is real against both formatters rather than
asserting it in a comment.

### A judgement the spec did not make: reads that came back out of order

A wall clock steps backwards for ordinary reasons — NTP correcting, a person
changing the time, a timezone database landing — and there is room for one
between `pendingSince` and the flush. Two instants that do not bracket anything
are not a span; they are one stale read and one fresh one. The envelope
collapses onto the **flush instant**, the fresher read and the one the words
actually left at. Collapsing the other way would publish a stamp from the future
and post an end preceding its own start, which is the first invariant a wrong
clock breaks (gate leg 3).

---

## 2. The gate leg

**`overnight/turn_envelope_gate.py`**, built to §10's shape.

**No leg checks that a field is non-empty.** That check reports GREEN TODAY on
the exact column this card exists to fix, and the file says so at the top in a
box so nobody softens a floor back toward it. Every leg asserts a relationship
between two instants, with floors above anything push-time stamping can
physically produce.

| Leg | Asserts | Floor |
|---|---|---|
| 1 | the stamp is not the postmark | median(created − start) ≥ 2.0 s, one row ≥ 2.6 s |
| 2 | start and end are two instants | strictly greater on ≥ 90%, median span ≥ 0.5 s |
| 3 | it cannot finish speaking after posting | end ≤ created on 100% |
| 4 | the queue preserved the stamp | one row > 60 s late, else **UNPROVEN** |
| 5 | a flush burst did not collapse | ≥3 rows arriving within 2 s must span > 30 s of speech, else **UNPROVEN** |
| 6 | the ears are alive at all | precondition; zero transcripts ⇒ **UNPROVEN** |

Scope: `kind="transcript"`, `device_id` build ≥ 88, `source != "typed"` (a typed
line has no speaking duration and would drag leg 2). Under 20 qualifying rows it
exits 2. Too-few-rows and deaf ears exit **2, never 0**.

It never requests the `text` column — `FIELDS` names six columns and speech is
not one of them — so it cannot measure meaning with a threshold even by
accident.

### What it says today

```
--self-test   exit 0   7/7 cases
--replay research/evals/call-2026-08-23-tejas/call_transcripts.json
              exit 1   leg 1 FAIL, leg 2 FAIL, leg 5 FAIL, leg 4 UNPROVEN
live --hours 48
              exit 2   137 transcript rows, builds [75], 0 qualifying
```

**The replay is the one claim about this work that could be checked without a
phone, and it is the important one.** Run against the 137 stored production
rows, the gate measures `median(created − capture_started_at) = 0.05 s, widest
0.07 s` — independently reproducing the spec's p50 0.053 / max 0.065 — and goes
RED. A gate that went green on today's data would be written wrong. This one
does not.

---

## 3. Tests, with real exit codes

Read from `rc=$?` on the command, never from a trailing pipe.

| Suite | Result |
|---|---|
| `app/ios/Tests/run_capture_envelope_tests.sh` | **exit 0** — 7 wiring law legs + **34 checks** |
| `app/ios/Tests/run_all.sh` | **exit 0** — **369** `ok` checks (335 before this card, +34) |
| `xcodebuild` (iPhone 17 Pro simulator, Debug) | **exit 0**, `** BUILD SUCCEEDED **` |
| `overnight/turn_envelope_gate.py --self-test` | **exit 0** — 7/7 |

The pure suite compiles `CaptureEnvelope.swift` with `swiftc` alone — no
simulator, no scheme, no signing — in this repo's tradition. `run_all.sh` reaches
its end.

`run_reset_message_tests.sh` gained `CaptureEnvelope.swift` on its `swiftc` line,
because `AnticipyBackend.pushEvent` now takes one. That is a real coupling, not
a workaround.

### Mutation testing — 15 mutations, **0 survivors**

Every behaviour was shown able to fail: mutate in place, run, restore from a
`cp` backup, then diff all four files against the backups to prove restoration
(all four byte-identical afterwards). `git checkout --` was not used anywhere.

Seven against the pure type, and each killed exactly the intended checks rather
than merely something:

- alias end onto start on the wire → 4 red, incl. *start and end are two different values*
- point `spoken_at` at the end → 1 red, *spoken_at is the older name for the start*
- trust two reads however they came back → *reads that ran backwards collapse onto the flush instant*
- collapse backwards reads onto the STALE read → *never publish the future read*
- an old queue row becomes no envelope → *a queue row from the previous build is one instant*
- equal instants count as a span (`>` → `>=`) → 4 red, incl. *two identical reads are not a span*
- drop the `spoken_at` column → *the wire carries exactly three columns*

Eight against the production wiring, each firing the intended law leg (exit 2):
tagged site sends the flush instant as start; untagged site the same; parting
tail back to `Date()`; queue end made required; offline flush stops re-sending
the end; backend stamps a capture column by hand again; wire clock loses
fractional seconds; line callback narrowed back to one instant.

---

## 4. LAW 3 — what is UNPROVEN

**The ears are dead and nothing here has run in the world.**

Measured live at 2026-08-25 22:10 UTC:

```
newest kind="transcript"     2026-08-24 01:30:11Z   iphone-b75   (44.7 hours ago)
newest kind="anticipy_says"  2026-08-25 17:11:14Z   anticipy-brain (5 hours ago)
```

The backend has been accepting writes the whole time. This is the
one-directional asymmetry `are_the_ears_live.py` exists to catch, still open.

Nothing in this card is verified live. Specifically **unproven**:

- that `capture_started_at` ever differs from `created` by more than 0.07 s
- that start and end arrive as two distinct values
- that the offline queue preserves stamps across a flush (legs 4 and 5)
- whether `pendingSince` tracks speech onset closely enough in the field —
  §5.1's residual error is reasoned, not measured

**Proven now:** the type's arithmetic, the wiring (by law legs, all
mutation-tested), that the app compiles and links at build 88, and that the gate
goes red on the rows production already has.

### What a person should look at the moment a phone is connected

Install build 88, speak two sentences with a pause between them, wait for the
rows, then run:

```
python3 overnight/turn_envelope_gate.py --hours 2
```

It must move off `UNPROVEN` and print `0 qualifying → N qualifying`. **Leg 1 is
the whole card**: it must report a median start-to-arrival of seconds, not
hundredths. Leg 4 needs a deliberate act nobody has run yet — airplane mode on,
speak two sentences, wait a minute, airplane mode off — and until somebody does,
it stays UNPROVEN, which is honest but is not proof.

---

## 5. Spec drift found while building

**`TranscriberClient` no longer exists.** Spec §5.4 rules the pendant callback
widening in scope and gives its line numbers. Another agent deleted that type in
the LOCAL-FIRST work (`AnticipyApp.swift:169-179` now says so explicitly:
"NO PENDANT TRANSCRIBER"). `LocalTranscriber.onTranscript` is the intended home
and has zero call sites. **There is nothing to widen**, so §5.4 was not
implemented — not skipped. When the pendant path is wired, it must carry two
instants from the start; the envelope is already the shape to carry them.

The spec's line numbers for `PhoneListener.swift` and `AnticipyApp.swift` had
also moved (builds 82 → 87 under three agents). Everything was re-located by
symbol, not by line.

---

## 6. Handed back — NOT touched here

1. **`brain/sorter.py:261-262` — the `seq` zero-default defect.** Confirmed
   present in the tree. PocketBase returns `"seq": 0` as an int on all 137 rows,
   so `isinstance(seq, int)` is True, the `i + 1` fallback never runs, every turn
   renders `#0` and nothing is ever `[NEW]`. **`brain/` was contended while this
   card ran (another agent had `brain/memory.py` modified), so it was reported
   rather than edited**, per the card. Fix is server-side and is specified in
   `2026-08-25-sorter-conversation-granularity.md:172-173`. iOS writes no `seq`,
   deliberately: writing it from the phone without `boot_id` masks the bug and is
   strictly worse than not writing it.

2. **`brain/segmenter.py:44-46` `_ANAPHORIC`** — a live Law 1 violation, another
   agent was on it. Not touched.

3. **Leg 4 needs a standing procedure.** Without one it sits at UNPROVEN
   forever. Whoever holds the phone owns it.

---

## 7. Collision report

`git status --porcelain` was **clean** at the start of this card. It did not stay
clean. Mid-flight, another agent began working in the same tree, and their
uncommitted changes appeared in `brain/memory.py`, two `tests/test_library_*`
files, `tests/test_segmenter_link_tape.py`, `app/ios/Tests/run_end_errand_tests.sh`
(+284 lines) and — inside a file this card owns —
**`app/ios/Anticipy/AnticipyApp.swift`**, where they relocated the Law 2 `TAPE:`
marker for audit item #55.

**Their file write clobbered two of my edits.** The `Edit` tool reported the file
had changed on disk; the two closure-formatting edits I had just made were gone
while my substantive changes survived. They were re-applied atomically and
verified.

Nothing of theirs was committed: the commit stages **only my hunks** of
`AnticipyApp.swift` and never uses `git add -A` or a pathspec commit (which would
have swept their working-tree content in). Their work is left exactly where they
put it, unstaged.

**This is worth a process note:** two agents editing one Swift file by
whole-file write will silently lose each other's work, and only the `Edit` tool's
"modified on disk" warning surfaced it. A `cp` backup taken before each edit
session is what made the recovery certain.

---

## 8. Law compliance

- **LAW 1.** Everything added is clocks and arithmetic over clocks. Neither the
  type nor the gate can see a word — the gate never requests `text`. The four
  meaning-adjacent pieces the spec names (`_ANAPHORIC`, trigger A, the
  `<6 content words` short-circuit, the `<2 words = fragment` guard) are
  untouched and remain named rather than absorbed.
- **LAW 2.** No tape. Nothing here is a string patch; no `TAPE:` comment would
  be honest and none was added.
- **LAW 3.** §4 splits every claim. The gate runs against LIVE and exits 2 when
  it cannot prove anything.
- **LAW 4.** This file, written the day the work exists.
- **LAW 5.** Senses first, and within senses recording before detecting. No VAD,
  no endpointer, no `SpeechAnalyzer` — the spec's §8 refuses them until the wire
  can carry what the phone already knows, and it now can.
- **LAW 6.** Self-reviewed to convergence: 15 mutations, 0 survivors; the gate
  replayed against real rows to confirm it fails on them.
