# Every Omi subsystem, and what we did about it — 2026-09-04

The completeness check on "cherry-pick from the teardown to upgrade the pendant
system." Source reference is `2026-09-04-omi-architecture-extraction.md`; this
file is the ledger of decisions, including the declines, because a decline that
is not written down gets re-proposed every session.

**Law-3 status, corrected 2026-09-05 00:00Z.** This file first said the ears had
been silent 89h and that nothing here could be observed live. That was true when
measured (~2026-09-04 16:00) and was FALSE within hours — which is exactly the
staleness this document exists to complain about, so it is corrected here rather
than quietly.

`done_gate` leg 1 SHE HEARS YOU now PASSES. `are_the_ears_live.py`: 68 lines of
speech in 24h, newest 0.0h ago, from **`iphone-b122`** — the build these iOS
changes went into. The brain is processing them: of 165 transcript rows, 155 are
stamped `ignore` and 10 `act`, with **zero** unprocessed.

One reading to head off, because the gate output invites it. The control half
reads "rows the SERVER wrote in the last 24h: 0", and beside 68 lines heard that
looks like a dead brain. It is not. That control counts rows carrying
`device_id="anticipy-brain"` — outbound work — and a day she correctly judged as
all-ignore writes none. `is_the_brain_live.py` reports "keeping its promises" on
the same data while showing 0 messages, and it would say that over a genuinely
dead brain too, because every rule it has is an over-speaking rule. Neither
instrument is lying; neither answers "is the brain processing". The decision
breakdown above is the query that does.

Still true: the firmware changes are further back than repo-green — unbuilt,
unflashed, and `firmware_gate.py` reports UNPROVEN.

## The ledger

| # | Omi subsystem | Anticipy state | Verdict |
|---|---|---|---|
| 01 | Pendant firmware | fork of Omi's OLD Friend fw, no journal, no VAD, no PM | **PARTIAL — done what is possible without hardware** |
| 02 | The BLE link | 3-byte header, seq counter, `PERM_READ_ENCRYPT` | **DONE + already ahead** |
| 03 | The phone relay | HTTPS + poll, WAL, gap assembler | **DONE — 3 fixes** |
| 04 | Ingest / STT / speaker | on-device Apple STT, no VAD, tagger unlinked | **DECLINED, deliberately** |
| 05 | Memory | SQLite temporal KG, no vectors | **DONE — 4/5 already built, board corrected** |
| 06 | Reasoning + bounds | ~13 single-question calls, NO bounds | **OPEN — the largest remaining gap** |
| 07 | Action / tools | seatbelt, digest-bound approval | **DECLINED — ours is the control group** |
| 08 | Pusher / blast wall | none | **OPEN — but premature** |
| 09 | Model gateway | env-var model, no retry, no fallback | **DONE in repo (`8230819d`), NOT LIVE** — truncation flag, 3-attempt retry, ordered transports with a 60 s dead-primary memory; `is_the_gateway_live.py` exits 1 until a worker with both keys and `ANTICIPY_LLM_ORDER` runs |
| 10 | Proactivity | 0 asks in 137 decisions; caps checked not reserved | **DONE in repo, NOT LIVE** — 10a no-verdict-below-the-floor (`3c36d2f7`, `unattributed_lane_live.py` UNPROVEN); 10b reserved slot per uninvited text at four doors (`41ab8015`, `is_the_brain_live.py` reads the slots, UNPROVEN until a deployed worker writes one). The "research results and clock texts flow around it" line was stale: research has been desk-only since `cd4a490f`; clock texts now reserve too |
| 11 | Apps / extensibility | none | N/A — no third-party surface |
| 12 | MCP | none | N/A |
| 13 | Desktop eye | macOS meeting capture, different design | N/A |
| 14 | Persistence | PocketBase + per-owner SQLite | N/A — different stack |
| 15 | Trust model | 4 principals, guard.pb.js | **PARTIAL** |

## What was actually changed

- **`a4f9f2f1` airtime lost survives the process.** Teardown item 08 ("turn the
  packet counter into a loss metric"). The assembler already measured gaps and
  dropped them on the floor; they are now a journal event a day folds into two
  numbers. The invariant worth the test: a gap does not count as hearing.
- **`c7d4a039` the unsent queue had no bound.** One JSON array in one
  UserDefaults string, re-encoded whole per append, unbounded. Now 2000 lines,
  newest kept, and the overflow is recorded rather than silent.
- **`3eb67cec` a queued line leaves the disk only once the server confirms it.**
  `flushUnsent` opened with `unsent = []` — the durable queue emptied before a
  single row was posted, then a network round trip per row. iOS killing a
  backgrounded app mid-loop lost every unconfirmed line. Not from the teardown;
  found by an adversarial pass over the same file.
- **`8351f119` routine backpressure switched the microphone off.** Teardown item
  07's cousin. A full ring or one congested BLE interval reached
  `transport_audio_fault`, which kills capture for the connection. Now drops one
  frame and steps the sequence so the phone still sees the hole.
- **`d56bf864` the LIBRARY card listed four finished things as missing.**
- **`30f3a7dd` a half-sentence went to his phone.** Teardown item 14.

## The declines, with reasons

**04 — server-side diarization. ILLEGAL, not merely unwanted.** Omi maps
provider labels to conversation-local ids and stamps a provider epoch per
reconnect, then runs a 0.45 voiceprint check with an 8-centroid cap. All of it
runs on raw audio in the cloud. `design/LOCAL-FIRST.md` forbids that outright.
What survives the constraint is the *discipline* — conversation-local ids and an
epoch per reconnect — not the implementation.

**04b — re-linking the speaker tagger. `tejas_gate` leg 6 is RED and should
stay red for now.** It is unlinked deliberately, twice, by controlled
experiment: builds 46/47 carrying the frameworks were accepted and then ceased
to exist during App Store Connect processing; build 48 without them validated in
two minutes. Build 76 put it back as a Swift package — same binary xcframework
by another route — and builds 76–80 delivered zero rows ever. It was also
*measured actively harmful*: 195 distinct identities across 200 lines, the owner
recognised twice. `project.yml` sets the precondition for re-adding it (read the
processing rejection first) and that has not been met. Making this leg green
would be the wrong move.

**06 — Omi's AAD silence gate. IMPOSSIBLE, not declined.** Omi's is nRF5340 +
T5838 silicon: register map, FAKE2C bit-bang, WAKE pin. This board is an
nRF52840 driving a plain PDM mic through `nrfx_pdm`. There is no AAD hardware.
The Brief requires wake-on-sound duty cycling; on this board that is a *hardware*
decision, not a firmware one. Worth knowing before anyone plans against it.

**07 — the tool/action layer. Ours is the control group.** Omi has no
confirmation on any write anywhere; `delete_calendar_event` takes a bare date
range and deletes every match in a loop, inside a 25-call budget with no
read/write distinction. Anticipy's seatbelt — version-and-digest-bound approval,
two non-interchangeable doors for speech and gesture, the same law enforced in
Python, in a PocketBase hook and in the extension — is a different category.
Nothing here is a candidate.

**05b — the outbox pattern. Premature.** It protects derived views from
answering by themselves. Anticipy has no derived view of memory: one mention of
"vector" in the whole file and it is the doctrine arguing against one. Building
it would be machinery for a problem that does not exist.

**05c — the promotion receipt. Guards a step we do not have.** Omi's receipt
stops a model minting authority for its own output. Anticipy already fails
closed at every equivalent point: an invented episode id is filtered out, a fact
with no traceable source is dropped (`if not eps: continue`), the cursor
advances only on success, a poison batch is skipped after three strikes. And
Omi's set-equality conservation is per-*item* routing — every pending item gets
exactly one route — whereas Anticipy's consolidation is per-*batch* distillation
where 200 episodes legitimately yield ~5 facts. Conservation is meaningless
against that shape.

**08 — pusher. Right idea, wrong scale.** The blast wall exists because slow
third-party webhooks would stall transcription. Anticipy has no third-party
webhook surface. The *pattern* worth keeping is already ported in miniature: a
bounded queue that evicts the oldest and increments a counter, which is what
`c7d4a039` does.

## What is genuinely still open, ranked

1. **Proactivity (10).** The measured failure is the worst in the product: 0
   asks in 137 decisions while taking 6 actions, 5 wrong. Omi's two orderings
   are the fix and both are cheap: a missing confidence defaults BELOW the floor
   so absent signals are ignored rather than optimistically accepted, and the
   budget is RESERVED before the model call rather than checked after, so a
   burst cannot outrun the limiter. Anticipy checks its cap, and only on one
   outbound path — research results and clock texts flow around it.
2. **Reasoning bounds (06).** No call ceiling, no wall-clock deadline, no token
   budget anywhere on the judging path. Omi's 150s hard deadline is the real
   backstop and everything else is graceful degradation before it.
3. **Prompt-injection fencing at triage (10b).** Omi's judge prompt declares
   candidate text untrusted data whose embedded instructions must be ignored.
   Anticipy needs that sentence *more*: its untrusted input is the transcript of
   the owner's life, and it has an approval gate an injected instruction would
   like to talk past. The memory sinks are already fenced; triage is not.
4. **Gateway retry and fallback (09).** A Gemini failure does not fall through
   to OpenRouter. Note Omi has the same hole for a worse reason — every lane
   ships `max_attempts: 1` with the retry machinery built and configured off.
5. **Firmware flash journal (01).** The single largest source of silent capture
   loss, and hardware-blocked: no toolchain, and the shipped `.uf2` does not
   match its own receipt hash.

## The one thing to do first, regardless

Get the phone carrying again. `done_gate` leg 1 has been red for 89 hours, and
until it is not, every item above is unverifiable by construction — including
the six changes already made.
