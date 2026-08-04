# The Production Roadmap — every named problem, what the code does today, and the researched fix

Written 2026-08-04 after the first real all-day usage session. This is the
standing checklist. Nothing on it may be forgotten; each item is tackled one
at a time, and the whole system is retested after each. Items reference the
actual code so the next session can verify rather than trust.

The paradox Omar named is real: she hears everything, so every rule about
when to speak is wrong for someone. The resolution running through this
whole document is ONE principle: **never throw work away, and never push it
either — do everything, deliver it quietly, interrupt almost never.** The
app is her desk; SMS is her tapping you on the shoulder. Research always
happens; a text only happens when a moment is about to be missed.

---

## 1. How the memory actually works today (two-year-old version)

Code: `brain/memory.py`.

- Every line she hears becomes an **episode** (a timestamped quote).
- A model reads each line and pulls out **people, places, topics, and
  promises** ("I'll send Sarah the deck"). Those become nodes in a graph,
  wired together with timestamped edges (who-said-to-whom, what-about-what).
- **Promises are alive**: they're born "open", and when you later say "sent
  it", she matches the words and closes the loop. Open promises are her
  to-do list (`open_loops()`).
- **Recall** ("what did I tell Sarah?") starts at the names in your
  question, walks the graph two steps, full-text-searches every episode
  ever heard, and returns the newest relevant chain — with the original
  quote as proof.

So it is genuinely a temporal graph, not a JSON file and not RAG. What it
is **missing** is everything that makes memory feel like being KNOWN:

| Missing | Why it matters | Fix |
|---|---|---|
| **Consolidation** | Every mumble is kept raw forever; the graph fills with noise nodes ("blah", half-thoughts) that seed recall. | A nightly (and per-conversation-close) pass: an LLM reads the day's episodes and distills **stable facts** ("Omar's partner is X", "he prefers 7pm dinners", "works on Anticipy") into a `profile` table with confidence + provenance. Raw episodes stay for audit; recall and triage read the distilled layer first. This is how Letta/MemGPT and Gemini's memory work — the industry-converged answer. |
| **Salience / decay** | A grocery mumble and "my mom is in hospital" weigh the same. | Score each fact at extraction (importance 1–5, model-judged); recall ranks by importance × recency × relevance instead of just term hits. |
| **A person model (day zero)** | System 1.0 has no way to get to know you — nothing accumulates ABOUT Omar. | The consolidation layer above IS the person model, plus §8's day-one interview so it isn't empty on install. |
| **Dedup of near-identical facts** | The same plan restated five ways creates five nodes. | Consolidation merges on embedding-or-LLM similarity before writing. |

**Order: this is the #2 build item** (after §6, which unblocks everything
else being tolerable to test).

## 2. The gap problem — pausing 5 seconds mid-thought

What exists today (two layers, not yet joined):

- `anticipy_core.py`: triage carries the **previous line** as background if
  it's under 120 s old, plus the last 6 lines of the conversation, plus 4
  related memories.
- `segmenter.py`: a real conversation-boundary engine — 45 s of silence is
  free continuation, up to 5 min leans same-topic, topic-overlap +
  anaphora ("anyway, back to…") links across longer gaps, 20 min is a hard
  cut. All keyed on capture time, so pendant backlog can't shatter a
  conversation.

**The bug**: the live hearing path only uses the 120-second single-line
memory — the segmenter's much smarter boundary logic isn't feeding triage.
So a 5-second breath is fine, but a 70-second pause mid-plan makes her
treat the resumption as a new subject.

**Fix (small, high value)**: triage context = the current **segment's**
lines (segmenter already decides what belongs together), not "last line if
< 120 s". One wiring change plus tests; no new machinery needed.

## 3. The proactivity dial — "don't text me when it doesn't need to"

What exists today:

- Triage is deliberately eager ("err toward starting work" — `orchestrator.py`).
- The confirmation gate holds anything consequential.
- The clock (unprompted outreach) already has hard guardrails outside the
  model: at most one per 4 h, never 22:00–08:00, never without a quoted
  source (`worker.py`).
- A `may_say` dedup guard stops her asking the same thing twice.

**What's missing is the middle lane.** Today she has only two volumes:
silent (memory) or a text. The fix is **three lanes**:

1. **Ambient** (default): noted, remembered, visible in the app if you go
   looking. No push, no text. Most of the day lives here.
2. **Desk delivery**: work she did on her own (research results, options
   found, drafts) lands as a quiet card in the app — the feed IS the
   deliverable. One gentle push notification at most ("left two options on
   your desk"), batched, never SMS.
3. **Shoulder tap** (SMS): reserved for (a) confirmations she's blocked on,
   (b) answers to things you texted her, (c) genuinely time-critical items
   (the 7pm booking is in 2 h and unconfirmed). Model proposes, a
   deterministic rule decides: SMS only if blocked-on-you OR deadline < N
   hours.

This resolves the Wispr-Flow paradox exactly as Omar stated it: *"I would
prefer that we send it anyway"* — yes, the research always runs and always
lands on the desk; it just doesn't buzz his phone unless a beat would
otherwise be missed.

Later (v2): the dial **learns** — replies, taps, and ignores adjust
per-category thresholds. Not built until the three lanes prove themselves.

## 4. The "Heard" log — transcripts are not a product surface

Omar: *"I don't want a log of everything I said… that stuff should happen
in the background; the only thing that should pop up is actionable."*

Fix (iOS, `ContentView.swift`):
- Home shows **only**: her greeting, the listen control, actionable cards
  (things needing OK / things she delivered), and the chat thread with her.
- The raw HEARD stream moves behind a small "everything I've heard" screen
  (reachable from Settings/history) — it must exist for trust and
  correction, but it is an audit log, not the living room.
- Checkmark micro-moments stay (they're the "she's alive" signal) but decay
  quickly instead of accumulating as a wall of bullets.

## 5. In sync everywhere — app chat and SMS are one conversation

Today the SMS thread and the app's view of her drift apart. The
`conversation.py` store is already the single history; the app needs to
read/render the same thread (and sending from the app should join it), so
whichever surface you look at shows the same her. One store, two windows.

## 6. Research must never use Omar's browser — FIRST BUILD ITEM

Tonight's tab flood happened because ALL work — even read-only research —
runs through the paired Chrome extension on his machine.

Fix: a **server-side research arm** in the worker:
- Read-only goals (the `_READ_ONLY_RE` class in `anticipy_core.py`) are
  executed in the worker via the **Brave Search API** (2,000 free
  queries/mo, then $5/mo tier) + page fetch + LLM summarization. Results
  land on the desk (§3 lane 2).
- The browser extension is reserved for jobs that genuinely need HIS
  logged-in browser: bookings, forms, purchases — always through the
  confirmation gate, always visible.
- Guardrail already shipped tonight (ext 0.2.3): even browser jobs stop
  themselves after 18 fruitless steps on one page and sweep every tab they
  spawn, every step.

This one change removes most of the "my computer is possessed" feeling and
makes proactive research free to do liberally, which §3 depends on.

## 7. Speaker recognition — who is even talking?

Today: none. The phone/pendant mic transcribes everyone equally; her
speaker-attribution problem is real ("her talking to another person issue
instead of talking to a computer").

Honest assessment: on-device voice-print diarization is a hardware/DSP
project (pendant v2 territory — the Omi/Limitless products solve it with
enrolled voice profiles). What we CAN ship now, in order:

1. **Addressee classification** (cheap, now): a triage pre-stage answering
   "is the owner talking to ME / to another person / dictating to a
   machine / mumbling to himself?" — using conversational cues the model
   already sees. Dictation and third-party speech default to the ambient
   lane (§3), never to actions. This alone kills the Wispr-Flow false
   fires.
2. **Enrolled voice profile on iPhone** (next): Apple's Speech framework
   exposes per-utterance voice analytics; a lightweight "is this Omar?"
   gate keeps other voices as context-only, never as HIS commitments.
3. **True diarization** on the pendant hardware (later).

## 8. Day zero — she has no way to know you

Fix, two parts:
- **The interview**: onboarding ends with her asking five human questions
  (who matters to you, what do you do, what should I never touch, how do
  you like to be reached, what's coming up this month) — written straight
  into the profile layer (§1). Feels like meeting a person; seeds the
  memory so day one isn't amnesiac.
- **Imports with permission**: contacts + calendar read-only on iOS. Names
  she hears then resolve to people she can spell, and "tomorrow at 7" can
  check against a real calendar.

## 9. Browser jobs must never take the foreground

The agent's working tab is already created `active: false` inside a
collapsed tab group (`agent_loop.js`), but paths remain that surface tabs:
the needs_user hand-back calls `tabs.update(active: true)`, spawned
target=_blank tabs open wherever Chrome pleases, and the pairing/onboarding
page opens focused. Rule: **nothing she does may steal focus, ever.**
Hand-backs should badge the extension icon + notify instead of seizing the
screen; spawned tabs are swept (shipped in 0.2.3); audit every
`tabs.create`/`tabs.update`/`windows.update` call for focus effects.

## 10. Privacy & security

Named, deliberately last per Omar. Already in place: token-guarded API,
owner-scoped reads, sealed anonymous access, confirmation gates, financial
domain blocklist, daily DB backups (added tonight). The remaining work
(E2E encryption of transcripts at rest, delete-my-day, on-device-only
mode) is scheduled after the experience work above.

## How this gets built: an agent fleet, gated by evidence

The work above is parallelized across Claude Code agents on the Mac, each
working an isolated copy of the repo from a written brief (context,
constraints, definition of done, tests that must pass). The orchestrator
(Devin) writes the briefs, manages the fleet, and GATES every result: the
offline suites, integration, and a live production proof — the same
evidence bar as the 2026-08-04 end-to-end test — before anything merges.
Perfection defined: never backwards; every merge accelerates an item on
this list or retires a newly found real problem.

---

## Order of attack (one at a time, whole-system test after each)

1. **§6 research arm off his browser** — removes the biggest daily pain, enables generous proactivity.
2. **§7.1 addressee classification** — kills false fires from dictation/other people.
3. **§3 three-lane delivery** — the proactivity dial that resolves the paradox.
4. **§1 memory consolidation + profile layer** — she starts to know him.
5. **§4 Heard-log redesign + §5 one-conversation sync** (one iOS build).
6. **§2 segment-fed triage context** — pauses stop shattering thoughts.
7. **§9 never-foreground audit** (small; can ride along with any extension change).
8. **§8 day-zero interview + imports.**
9. **§7.2 voice profile gate**, then **§10 privacy hardening.**

Rule for every item: design → build → offline tests → live production proof
(the kind run tonight for signup/browser) → only then the next item.
