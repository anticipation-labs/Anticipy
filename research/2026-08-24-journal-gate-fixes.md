# The journal gate stops vouching for the channels it never read

Answering `.superpowers/sdd/privacy-gate-criticals.md` (review of `f2ed456b`) —
four Criticals, the eleventh fail-open, one Minor, and one correction. Scope was
`app/ios/` only. Everything below was reproduced on a scratchpad copy of
`app/ios` before it was fixed, and every rule written or amended was then broken
on purpose and watched to fail.

Line numbers in the review are stale — `PhoneListener` was rewritten by the
echo-guard fix (`c2bdef7b`) and a battery leg was added to the journal runner.
Everything here is **re-pinned by symbol**, not by line.

---

## 1. The four leaks, reproduced then refused

Reproduced against the tree as it stood, on a copy under the scratchpad. Each
one is quoted with the gate's own last line of output.

### C1 — `.flushed(reason:)`, a third free-form String the allowlist never read

`ListenEvent.flushed(reason: String, words: Int)` in `ListenJournal.swift` is
rendered verbatim by `describe`. At the flush site in `PhoneListener.flushLine`,
directly beneath the comment *"The word COUNT, never the words. The journal is
exportable from Settings"*, one token:

```swift
.flushed(reason: line,                      // was: reason?.rawValue ?? "banked"
         words: line.split(whereSeparator: { $0.isWhitespace }).count))
```

```
$ sh app/ios/Tests/run_journal_tests.sh
ListenJournal: all 19 checks passed
$ echo $?
0
```

Now:

```
A journal write hands over a value this gate has not been told is safe:
…/Audio/PhoneListener.swift	reason	 line
$ echo $?
2
```

The same mutation on the parting-tail flush (`reason: tail`) is red too.

### C2 — a write through `self.`, which `namelines.awk` could not see

`bare = "(^|[^A-Za-z0-9_.])" name …` excluded a preceding `.`, so `self.facts`
matched nothing and the line was `continue`d before it was ever classified.
Promoting `facts` to a stored property and writing the report's own headline
leak with three characters in front:

```swift
self.facts += self.partial
```

```
ListenJournal: all 19 checks passed        exit 0
```

### C3 — an unrecognised assignment shape read as a plain read

The matcher wanted `=` immediately after the name. Anything else fell through
every arm and landed on "a plain read", so **failing to understand a line was a
pass** — the inversion of the rule's own principle.

```swift
(facts, lastSessionFacts) = (self.partial, "")
```

```
ListenJournal: all 19 checks passed        exit 0
```

It also blanks the dedupe key, so the live transcript is journalled on every
watchdog tick for the length of a call.

### C4 — one space defeats both anchors

`.noted(` and `detail:` were seven-character comparisons at a fixed offset.

```swift
ListenJournal.shared.record(.noted (line))                      // exit 0
ListenJournal.shared.record(.posted(ok: true, detail : line))   // exit 0
```

Both `ListenJournal: all 19 checks passed`. And an extraction returning zero
expressions read as "everything was allowlisted".

### I5 — the eleventh fail-open, inside a rule the same commit rewrote

`run_control_policy_tests.sh` counted `found` globally across
`"$content" "$settings"` and `END` fires once for both, so an anchor lost in one
file was invisible while the other still had one. Renaming every indicator in
ContentView to `PulseDot`/`PulseBars` and putting the pre-fix regression back on
the greeting dot:

```swift
if session.listener.isListening || !handling.isEmpty { PulseDot(size: 7) }
```

```
ListenControlPolicy: all 12 checks passed  exit 0
```

ContentView unread end to end, the greeting dot pulsing over "Something else has
the microphone right now." for the whole of every call.

### These are real Swift, not scan artifacts

All five leak shapes compiled under `swiftc -O` as a standalone reduction and
printed the card number into the journal line:

```
flushed  7 words sent, reason: he said his card number is 4111
noted  dropped 0he said his card number is 4111 buffers while swapping
noted  dropped he said his card number is 4111 buffers while swapping
noted  he said his card number is 4111
posted  true he said his card number is 4111
```

C1's one-token mutation was also built in the real target: `** BUILD SUCCEEDED **`
on the Release configuration, then reverted.

---

## 2. Two more leaks, found by attacking the fix

The review's shape — *the extractor can return nothing and that reads as
success* — has a wider instance than the four it names. `journalwrites.awk`
found call sites with `index(s, "ListenJournal.shared.record(")`, a literal on
one line. Two writes that never contain that text:

```swift
ListenJournal
    .shared
    .record(.noted(line))                       // exit 0

let sink = ListenJournal.shared
sink.record(.noted(line))                       // exit 0
```

Neither was a wrong rule. **No rule ran at all**, because the scan never saw the
call. Both are red now.

---

## 3. Did I take the typed-function fix? Yes — in a stronger form

The previous report proposed `ListenSessionFacts.sentence(category:mode:lowPower:)
-> String` and deferred it; the review's verdict is that deferring it is why C2
and C3 exist. I took it, and changed one thing: **the type is what is compared
and held, not just what renders the sentence.**

`app/ios/Anticipy/Audio/ListenSessionFacts.swift` (new, pure Foundation):

```swift
struct ListenSessionFacts: Equatable {
    let category: String
    let mode: String
    let lowPower: Bool
    var sentence: String {
        "session category: \(category) mode: \(mode)"
            + (lowPower ? " · low power mode on" : "")
    }
}
```

`PhoneListener.configureAndStartEngine` now holds a value, and
`lastSessionFacts` is a `ListenSessionFacts?` rather than a `String`:

```swift
let facts = ListenSessionFacts(category: session.category.rawValue,
                               mode: session.mode.rawValue,
                               lowPower: ProcessInfo.processInfo.isLowPowerModeEnabled)
if facts != lastSessionFacts {
    lastSessionFacts = facts
    ListenJournal.shared.record(.noted(facts.sentence))
}
```

**Why this form.** A static `sentence(...)` function would still have left a
`var facts: String` in `PhoneListener` for the change-detector to compare, which
is the exact object C2 and C3 exploit. Holding the *value* removes it. C2's and
C3's mutations no longer compile at all: there is no `+=`, no `.append` and no
`= self.partial` on a `ListenSessionFacts`. That is the argument
`ListenEvent.batteryRead` already makes about its own payload — the privacy
claim is the type — and it is now the argument here.

**Why the scan was fixed anyway.** A type is worth what its openings are worth,
and a later commit can change the type back. `namelines.awk` is fixed
independently (§4), and the two openings of the type are read: every
construction of it anywhere in the app, argument by argument, and the body of
`sentence` through the two passes a journal literal gets.

`sentence` is one expression on purpose. There are no assignment shapes in it
for a scan to misread.

---

## 4. Every rule written or amended, with the mutation that breaks it

Forty-three mutations on the journal gate, five on the control policy gate, two
on the interruption contract. All run on a scratchpad copy; the tree is green
after each. Nothing below passed with the line it names removed.

### run_journal_tests.sh

| Rule | What it now does | Mutation | Result |
|---|---|---|---|
| **channel derivation** (`channels.awk`, new) | reads `ListenEvent`'s cases and emits every `String` payload with the anchor to read it by: `label:` or `.case(`. Replaces two hand-written anchors. | add `case whispered(aside: String)` and record `.whispered(aside: line)` | exit 2, `aside  line` |
| | | rename `enum ListenEvent` | exit 2, "no String payload" |
| | | `case noted(String, Int)` — a String with no usable anchor | exit 2, "cannot anchor on" |
| | | declare a String case nothing records | exit 2, "no journal write uses" |
| **call-site finder** (`journalwrites.awk`) | regex anchor ending in its paren, `\.(record\|flushed\|noted\|posted)[ \t]*\(`, over every Swift file; `ListenJournal.swift` skipped (`parse` reads events back, it does not write them); `case .noted(let x):` skipped | `ListenJournal` ⏎ `.shared` ⏎ `.record(…)` | exit 2 |
| | | `let sink = ListenJournal.shared; sink.record(…)` | exit 2 |
| | | two record calls on one line, the second carrying the line | exit 2 |
| | | `detail:` with its value on the next line | exit 2 |
| **rule 2 anchors** | whitespace-tolerant, and every occurrence prints `SEEN` so the caller can insist each declared channel produced one | `.noted (line)` | exit 2 |
| | | `detail : line` | exit 2 |
| | | `reason : line` | exit 2 |
| **rule 2 extraction** | `\001` when an expression runs off the end unclosed, and an empty expression is `UNREAD`, not "nothing to check" | unbalanced quote in a build value | exit 2 |
| **rule 3 allowlist** | `+ ListenSessionFacts.swift#(category\|mode)` | see rule 3d | |
| **rule 3b** `namelines.awk` — `self.` | `bare`/`assign`/`touch`/`inout` all take an optional `self.` and no longer exclude a preceding `.` | `self.dropped += self.partial` on an allowlisted name | exit 2, "given a value this gate has not been told is safe: self.partial" |
| **rule 3b** — unparsed assignment | if the name sits in the left-hand side of an assignment this scan did not parse, that is a **failure**, not a read. LHS is cut at the last *top-level* comma, so `(a, b) = …` stays whole while `if x > 0, let y = z` does not false-fire | `(dropped, lastFactsEcho) = (self.partial, "")` | exit 2, "written by an assignment shape this scan cannot read" |
| | | `dropped["k"] = self.partial` | exit 2 |
| | | `dropped =` ⏎ `self.partial` | exit 2 |
| | | `withUnsafeMutablePointer(to: &dropped) { … }` | exit 2 |
| **rule 3b** — spend order | a journal call only counts as spending the name when the call **opens before** it on the line | `dropped.append(self.partial); ListenJournal.shared.record(.sessionStarted)` | exit 2, "something is done to it that this scan cannot follow" |
| **rule 3b** — continuations | a value is read on while its parens/brackets are open or a quote is unclosed, as well as on a leading operator; an unbalanced value fails | `dropped = "x" +` | exit 2 |
| | | `dropped = "unbalanced` | exit 2 |
| **rule 3b** — wrapper accounting | the values it synthesises are wrapped in the enum's own positional case, taken from the derivation, and it fails if fewer anchors were read than values handed in | make the bare-String case labelled (`case noted(fact: String)`) | exit 2, "no case taking a bare String" |
| **rule 3c** — construction | every `ListenSessionFacts(` in the app, read argument by argument against an allowlist | `category: self.partial` | exit 2 |
| | | a fourth field `heard: self.partial` | exit 2 |
| | | a property with no argument at any construction site | exit 2, "never given a value at a construction site" |
| | | delete `ListenSessionFacts.swift` | exit 2 |
| **rule 3d** — the sentence | `sentence`'s body through both passes a journal literal gets | `+ category` outside the quotes | exit 2, residue not allowlisted |
| | | `\(lowPower)` interpolated | exit 2, interpolation not allowlisted |
| | | `sentence` renamed | exit 2 (rule 2: `facts.line` not allowlisted) |
| | | body emptied | exit 2, "can no longer read the body" |

The recorded regressions from the previous wave are all still red: `+=` verbatim,
`.appending(…)`, a continuation `.appending`, a ternary, a function return, an
interpolation inside a string inside an array, a trailing operator, an unbalanced
quote, `let facts = words` in another file, a brand-new Swift file outside every
pair list, renaming `configureAndStartEngine`, renaming `installTap(onBus: 0`,
renaming the `.noted` case wholesale, and removing the dedupe guard. Raw strings
(`#"\#(line)"#`), multi-line `"""` literals, nested interpolation and
`String(line)` are red too.

### run_control_policy_tests.sh

| Rule | Change | Mutation | Result |
|---|---|---|---|
| live indicator | `found[FILENAME]`, and the file list comes off `ARGV` so a third file cannot opt out; the three-line window is cleared at each file boundary instead of carrying the previous file's tail across it | every indicator in ContentView renamed, regression restored | exit 1, names ContentView |
| | | only SettingsView's `WaveBars()` renamed | exit 1, names SettingsView |
| | (must not regress) | the whole condition and the dot on one line | exit 1, quotes the line |
| idle line | same per-file form, for the same reason: one file makes global and per-file the same answer today, and nobody re-reads the `END` block the day a second one is added | `idleLine` renamed | exit 1 |
| | | idle line ungated | exit 1 |

### run_interruption_contract_tests.sh — M7

`OVERRAN` stopped a range at `^    (private )?(func |var |let |@Published )`, so
`fileprivate`, `internal`, `public`, `open`, `final`, `static`, `override`,
`class func`, `init`, `subscript`, any other attribute and every member at a
different indent ran straight through it. It now stops on the *shape* of a
declaration at an indent no deeper than the one the block opened at.

Reindenting `configureAndStartEngine`'s closing brace with a
`fileprivate static func` after it: **old gate exit 0, new gate exit 1.**

---

## 5. The `dropped` correction

The previous commit called `dropped` *"a second bare name with no justification
at all"* and let that stand as a third leak found. **Half of it holds.**

- The **widening was real**. The entry was the bare word `dropped`, so any
  file's `dropped` had a pass. Pairing it with `PhoneListener.swift` was right.
- The **leak was not**. `TranscriptCursor.dropped` is `private var dropped = 0`
  — an `Int` counting words cut off the front of the ring so an alignment index
  keeps its origin (`sentWordCount`, `rebuilt`). Rule 1's own comment says
  counting speech is the design. There was never a shape in which it could carry
  a word.

Two of the three leaks that commit claimed were real. The claim is corrected
where it was made that is still editable: the rule 3 comment in
`run_journal_tests.sh`. The commit message itself is history and stands. A gate
whose comments overstate what they caught is a gate nobody can calibrate
against, which is precisely the failure that let `dropped`'s pairing be counted
as a third find.

The header claim *"EVERY record call site, in EVERY file, checked two ways"* was
corrected the same way: it was false when it was written, and the channel list
is now produced by the code rather than asserted by the sentence.

---

## 6. What this gate still cannot see

- **Inside `ListenJournal.swift`.** The call scan skips it, because `parse`
  rebuilds the same cases from lines already on disk and reading them back is
  not a write. A leak added to `describe` or to the file sink itself is outside
  every rule here. `ListenJournalTests` has one check on this
  (*"nothing written to disk carries transcript text"*) and that check is a
  fixture, not a scan.
- **Three allowlist entries rest on a type, not on a line-by-line scan.**
  `AnticipyApp.swift#source.wireName` (a closed three-case enum returning
  literals), `PhoneListener.swift#reason?.rawValue??` and
  `#TranscriptFlushPolicy.Reason.final.rawValue` (a `String` enum of `gap`,
  `ceiling`, `final`). `earn_name` is not run on any of them. If one of those
  types stopped being closed, the entry would keep passing.
- **`Self.postFailureShape(error)`** is on the interpolation allowlist and is
  not earned line by line either. It is the only thing between a server's own
  sentence and the log; `run_journal_tests.sh` asserts the call site still goes
  through it and nothing more.
- **Renaming the `.noted` case is a review moment, not a free refactor.** The
  spend classifier in `namelines.awk` still names `.noted(` and `detail:`
  literally; a wholesale rename fails the gate rather than following along. That
  matches the recorded expectation from the previous wave, and it is a
  hand-written anchor of exactly the kind rule 2 no longer has.
- **These are still text scans over a file no binary runs.** They constrain the
  shape of the code that writes the journal. Law 3: repo-green is not done. Not
  one line of this was observed on a device. What *is* proven beyond the scans:
  the five leak shapes compile and print under `swiftc -O`, C1's mutation builds
  the real Release target, `sh app/ios/Tests/run_all.sh` exits 0, and the Release
  build succeeds at build 79 with `Info.plist` untouched.
- **Could a fifth leak be written?** Probably, and the honest answer is that
  every wave so far has produced one. The two I found while attacking my own fix
  (§2) were not in the review; they were in the *finder*, one layer below every
  rule that had been argued about. The layer below this one is
  `ListenJournal.swift` itself, and nothing scans it.
