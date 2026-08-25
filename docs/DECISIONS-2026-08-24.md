# Two rulings, and three judgment calls already made

Law 4: a decision that lives only in a chat gets re-derived, wrong, by the next
session. These are written down the day they were made.

---

## RULING 1 — EARS option A (`SpeechAnalyzer`) is a FORK, not a wall

### The facts, gathered rather than assumed

- `SpeechAnalyzer` / `SpeechTranscriber` / `SpeechDetector` require **iOS 26 or
  later, with no backward compatibility.** Confirmed against current sources,
  not from memory.
- Our deployment target is **iOS 16.0** (`app/ios/project.yml`).
- **Nothing in the app uses any `@available(iOS 2x)` today** — every line
  targets the 16.0 floor. Option A would be the first.
- Toolchain here is Xcode 26.3 with the iOS 26.3 runtime, so building A is not
  blocked by our machines.
- iOS 26 shipped in September 2025. It is now late August 2026, so it is roughly
  eleven months old and its successor is weeks away.

### The ruling

**Screen the recruited stranger's iOS version before writing a line of EARS.**
It is one question to one person, and it converts a coin flip into a fact. My
earlier framing — "they might be on iOS 18" — was overcautious: at eleven months
into a release cycle most iPhones in use are on the current major. But "most" is
not "this one", and we get to *ask*.

Then:

- **Stranger on iOS 26+ → build A.** It is the better engine for exactly our
  conditions (long-form, distant, multi-speaker), it keeps the local-first law,
  and the spec's §8 criteria were pre-registered precisely so this choice could
  be made on evidence.
- **Stranger below iOS 26 → do NOT build A for the week.** Behind
  `@available(iOS 26)`, users under it silently keep today's behaviour — which
  is the ~33% capture EARS exists to fix. Building A would deliver **zero**
  improvement to that stranger's week. Spend the days on
  PHONE-AS-PENDANT Stages 0–2 instead, which help every iOS version.

### The technical finding that outranks the ranking either way

**A must be ADDITIVE, never a replacement.** `SpeechAnalyzer` has no
`contextualStrings` equivalent. `AnticipyVocabulary` is what teaches the
recognizer her own name, the owner's name, and the roster — and `tejas_gate`
leg 7 ("THE RECOGNIZER KNOWS ITS NAME") pins that organ. A wholesale swap would
turn leg 7 red, or worse, pass while silently regressing the guard that stopped
her proposing to buy a misspelling of her own product's name.

So: keep the SFSpeech arm for the 16.0 floor **and** for vocabulary, and add the
analyzer arm behind a routing policy. That is the same seam
PHONE-AS-PENDANT and the local-first pendant work both need, so it gets built
once — see the roadmap's shared-seam note.

---

## RULING 2 — moment 35 vs the §7 broadband entry

### The conflict, both sides verbatim

**Moment 35:** *"You say 'Priya and I broke up.' Every future suggestion,
booking, and reminder stops assuming Priya. The old facts aren't deleted —
they're retired, and they never surface in her voice again."*

**§7, the broadband call:** memory holds `home = 18 Rowan Ave since June` and the
**superseded** `4 Maple St`. The agent asks him to confirm the address on the
account. She says: *"You moved to Rowan Ave in June — the account probably still
shows 4 Maple St."* And the entry's own trap note reads: **"the superseded fact
is the load-bearing one."**

A filter that hides retired facts everywhere makes the §7 entry
unimplementable. A filter that shows them anywhere breaks moment 35.

### The ruling

They are not in conflict once you read moment 35 for what it actually governs.
Its own sentence names the scope: *"every future suggestion, booking, and
reminder stops **assuming** Priya."* That is about a fact being used as a
**premise**. The clause that follows — "never surface in her voice again" —
means never spoken **as though it were still true**.

The §7 answer does the opposite of assuming. It names Maple St *as retired*, in
the same breath, in answer to a question about a **third party's stale copy**.

**THE RULE:**

> A retired fact may never be an INPUT to action, nor an unqualified assertion.
> It may be QUOTED as history — only when the question is about the past or
> about someone else's stale records, and only with its retirement stated in the
> same sentence.

### What that means in code, on the seams that already exist

| Sink | Retired facts | Why |
|---|---|---|
| `fill_gaps_from_memory` (orchestrator) | **NEVER — hard filter** | Its output becomes a typed form value the browser agent enters into a real site. This is the Priya half of moment 35, and money can ride on it. No exception, no flag. |
| `_queue_job` params / any goal minting | **NEVER** | Same reason: a premise for action. |
| `_answer_from_memory`, `briefing_facts` | **Allowed, carrying `retired_at`** | This is the §7 half. The composer must state the retirement; a retired fact rendered without its retirement is the moment-35 violation. |
| `recall()` feeding triage context | **Allowed, marked** | Context, never a reason to act — the existing doctrine for every other context block. |

The asymmetry is the whole answer: **retirement gates ACTION absolutely, and
gates SPEECH conditionally.** That matches the product's spine, where the same
asymmetry already governs untrusted sources — `fill_gaps_from_memory` *excludes*
them outright while `memory_notes` *fences* them behind a nonce. This ruling
gives retired facts the identical shape, which is why it needs no new machinery.

**Ownership note:** the LIBRARY card is Jose's. This ruling settles which
behaviour to build so the card is not blocked on an ambiguity; if Omar reads it
differently, his reading wins and this file gets amended rather than argued.

---

## The three judgment calls already made, and why they stand

Made while landing PHONE-AS-PENDANT Stage 0 Task 1 (`5f98baa2`).

1. **`record()` became `async`.** The plan said "write on the existing serial
   queue"; that queue used `sync`. Disk I/O inside a `sync` hop parks the audio
   thread — the thread that must keep feeding the recognizer — behind a write.
   The instrument built to explain dropped speech would have become a way to
   drop speech. Ordering survives because the queue is serial and every reader
   enters it the same way; the evidence is that the existing
   two-writers-one-reader check passes **unchanged**. **Stands.**

2. **A test that reads the file directly must drain the queue first.** The async
   change made my own check fail for a reason unrelated to what it tested. Fixed
   by draining explicitly and writing the reason into the test, rather than
   quietly switching to the syncing accessor — the next person to read the file
   directly will hit the same thing and now finds it explained. **Stands.**

3. **`clear()` clears the files too.** Not in the plan. A person who taps clear
   and still has a copy on disk was not told the truth about what clearing
   means, and this is the one screen that promises exportability. **Stands.**
