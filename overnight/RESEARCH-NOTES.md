# Research notes, night of 2026-08-05

The research fan-out was cut off before it wrote its final reports, but two
agents had already confirmed findings worth keeping. Recorded here so the
work is not lost; both are FUTURE options, neither was built tonight.

## 1. The cross-device signal is real (confirmed on this Mac)

The idea: the machine Omar is dictating TO already knows he is dictating.
That is ground truth no acoustic model can match.

Verified, read-only, without writing to anything:

- **Wispr Flow is installed** — `com.electron.wispr-flow` (Electron app).
- **It keeps a local transcript history**: `flow.sqlite`, ~2.5 GB, with
  timestamps where `timestamp` = the moment the recording STARTED. The
  agent matched an entry's `07:06:09.400 UTC` to the app log's local
  `00:06:09.398` — so its history is precise enough to align against what
  the phone heard, second by second.
- Wispr ships its own read-only live-DB reader; there is a WAL-safe recipe
  for querying it without disturbing the app.
- **macOS names the app holding the microphone**: the system log carries
  `[[mic] Wispr Flow (com.electron.wispr-flow)]`.

**The last point is the generalisable one, and it is bigger than Wispr.**
"Which app currently holds the microphone" is not app-specific — it also
identifies a Zoom call, FaceTime, system dictation, any recorder. A signal
saying *he is currently speaking INTO an application* is exactly the
machine-directed evidence the `owes=machine` judgement is inferring today
from wording alone.

**Why it was NOT built tonight:** the phone is what hears him, and this
signal lives on the Mac — using it means the Mac publishing a "he is
talking to an app right now" flag that the phone or brain can see. That is
a real cross-device design (and a local-first one: a boolean, not audio),
but it is a bigger change than one night, and the language-only judgement
already kills the three real false fires. Right order: ship the judgement,
add the hard signal later as confirmation.

## 2. Data finding: the addressee field was already telling us

From the production-data agent, before it was cut off:

> **17 of 31 `act` decisions were on lines the system itself had labelled
> `addressee="person"`.**

Over half of everything she chose to act on, she had already judged was
NOT aimed at her — and acted anyway. That is the gap the `owes` question
closes: knowing who he was talking to was never wired to whether the work
was his to do.

## 3. Still unanswered (worth finishing)

- Do ANY shipping always-on wearables (Limitless, Bee, Friend, Omi, Plaud,
  Rabbit, Humane) act autonomously on inferred intent without a wake word,
  or do they all only record and summarise? The agent was mid-verification
  of Friend and Rabbit's "proactive" claims when it stopped. If the honest
  answer is "nobody does this", that is important context for how hard the
  problem is — and for the pitch.
- Apple/Amazon published device-directed-speech detection numbers, and
  whether their signals (ASR decoder confidence, prosody) are reachable
  from iOS's Speech framework.
