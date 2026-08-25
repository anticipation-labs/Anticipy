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
`contextualStrings` equivalent that the module we want will honour — see the
correction below, which makes this finding stronger, not weaker.
`AnticipyVocabulary` is what teaches the
recognizer her own name, the owner's name, and the roster — and `tejas_gate`
leg 7 ("THE RECOGNIZER KNOWS ITS NAME") pins that organ. A wholesale swap would
turn leg 7 red, or worse, pass while silently regressing the guard that stopped
her proposing to buy a misspelling of her own product's name.

### CORRECTION, same day — the API exists, and that is worse

The sentence above originally read "`SpeechAnalyzer` has no `contextualStrings`
equivalent" flat. That is **half wrong**, and the accurate version is a sharper
warning rather than a reprieve. Found by an independent session against primary
Apple sources; relayed here rather than left in a chat, per LAW 4.

`AnalysisContext.contextualStrings` is real and documented (iOS 26+):

    final var contextualStrings: [AnalysisContext.ContextualStringsTag : [String]] { get set }

attached with `SpeechAnalyzer.setContext(_:)`, capped at 100 phrases of one or
two words — the same cap the legacy API carries.

**But `SpeechTranscriber` ignores it.** An Apple engineer, in the accepted
answer on Developer Forums thread 811083: *"currently, contextual strings only
help transcriptions from the DictationTranscriber module. The SpeechTranscriber
module does not currently take contextual strings into account."* Apple's own
prose scopes the property the same way, and structurally `DictationTranscriber`
carries an "Improve accuracy" section while `SpeechTranscriber` has no
`ContentHint` type and no `contentHints` in its initializer. The custom-LM
bridge (`SFSpeechLanguageModel`) lands on `DictationTranscriber` too.

**Why this is worse than the original claim.** A missing API is a compile
error: loud, immediate, impossible to ship. An API that exists and is inert on
the module you actually want is a **silent** failure — the code compiles,
`setContext` succeeds, nothing throws, and the vocabulary biasing simply does
not happen. `AnticipyVocabulary` exists because she once proposed buying a
misspelling of her own product's name, and it owns `tejas_gate` leg 7. This is
exactly the shape the ruling warned about: "pass while silently regressing the
guard".

**So option A is a three-way fork, not two:**

- **`SpeechTranscriber`** — the high-quality long-form model, and no phrase
  biasing at all.
- **`DictationTranscriber`** — keeps biasing and unlocks custom language
  models, but Apple describes it as the same models and locales as on-device
  `SFSpeechRecognizer`. Ask hard what the migration buys over the incumbent
  before paying for it.
- **Stay on `SFSpeechRecognizer`.**

Unchanged by this correction: the iOS 26 floor, the requirement that A be
additive, and the §8 gate, whose inputs are still failing or unmeasured.

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

---

## RULING 3 — HANDS 2 is NOT built. The owner said so, and the code already said so.

**Decided by the owner, 2026-08-24**, on the evidence in
`research/2026-08-24-api-ladder.md`. Recorded here rather than left in a chat,
per LAW 4, because this card will look attractive again in a month.

**The card asks to "use APIs whenever connected." Three places in the shipped
code refuse that route by name**, and this ruling does not overturn them:

- `extension/supervised_read.js:47-52` — *"there is no OAuth here, no Gmail API,
  no LinkedIn API, no network call to a provider of any kind… which is the whole
  argument of `design/day-zero.md` §2, and the reason `gmail.readonly` (a Google
  RESTRICTED scope: CASA assessment, ~$540–$4,500+/yr, re-certified annually)
  never enters the picture."*
- `design/day-zero.md:122` — *"The API route is a subscription to an audit."*
- `ContextGrant.swift`.

**Three of the four named candidates fail LOCAL-FIRST outright.** Composio,
Arcade Cloud and Pipedream Connect each hold the owner's refresh token and proxy
his mail — custody and transit both. Only native per-service OAuth survives,
plus Arcade self-hosted (Helm/K8s, enterprise).

**Composio fails on evidence as well as on law:** the 2026-05-21 breach
exfiltrated roughly 5,001 GitHub OAuth tokens and 5,241 API keys, through a
Composio employee's Gmail token, across Gmail / Calendar / Slack / Notion /
Drive connections.

**The finding that reframes the card:** a platform does not save the expensive
half. Composio's and Arcade's own documentation requires bring-your-own OAuth
app in production, so Google verification and any CASA obligation stay ours
either way. **The trade is a vendor in the trust path for a few hundred lines of
token vault** — which is a bad trade at any price.

**And the card's premise does not hold.** "An API is always faster, cheaper and
safer" is false three ways. Safer is the important one: **no Gmail scope is
narrower than the whole mailbox**, so `supervised_read.js`'s thirty-second lease
on one page the owner opened himself is NARROWER than the narrowest API scope.
Slack gives non-Marketplace apps one `conversations.history` a minute at fifteen
objects. Airlines, OpenTable, utilities and government forms have no API at all.
Cheaper is unmeasured and probably false for exactly the repeated chores this
card exists to serve, because `recipes.js` already replays run 3 and later with
no model in the loop.

**If this is ever revisited** it is native OAuth, `calendar.events` first and
`gmail.send` second — both *sensitive* scopes (3–5 day verification, no security
assessment), never restricted ones. The one-day experiment that would settle it
is in §7 of the research: two arms on one errand, measuring the custody bill for
holding a single refresh token. If that half runs past a day, that is the answer.

**Carried forward, and it is the more urgent half:**
`backend/pb_hooks/transcription_token.pb.js` is LIVE IN PRODUCTION minting
credentials against `api.deepgram.com/v1/auth/grant` — for the one vendor
`LOCAL-FIRST` names and kills. That is what "server-side vendor credential
broker" looks like once it has shipped, and it should close before the pattern
is ever extended to owner tokens. See `research/2026-08-24-deepgram-leak.md`.
