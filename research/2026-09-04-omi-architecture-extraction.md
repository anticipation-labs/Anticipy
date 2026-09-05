# What Omi actually does, read from source — 2026-09-04

Source: `BasedHardware/omi` at `44941c1`, sparse checkout of `backend/{utils,routers,
llm_gateway,pusher,database}`, `omi/firmware/omi/src`, `app/lib/services`, `sdks/device`.
Paired with the 43-page architecture teardown at commit `10eaf717f0`
(`~/Downloads/Omi-Architecture-Teardown.pdf`).

This file is the reference half: what Omi does and how, verified against source.
The port decisions live in `2026-09-04-omi-port-plan.md`.

**Read the claim-audit lines.** Several of the teardown's headline numbers do not
survive contact with the source, and one of the most-quoted ones is wrong in a way
that matters. Findings written by a model reading code quickly are a hypothesis
list, not a defect list — the teardown says so about its own 153 findings, and the
same discipline applies to it.

---

## 0. The shape, in one paragraph

Omi is five layers moving in one direction: a deliberately stupid pendant
(digitize, compress, transmit — nothing else), a phone that is a store-and-forward
relay and does not understand the audio it carries, a cloud ingest that turns sound
into attributed text, a memory subsystem that is the most carefully specified thing
in the repo, and a reasoning layer that is a `while` loop with no planner. The
single most important decision is where they chose to be dumb: a coin-cell battery
cannot run a language model, so every gram of intelligence lives on the far side of
a Bluetooth link, and every hard problem is solvable somewhere you can deploy a fix
on a Tuesday.

---

## 1. Capture — the part Anticipy is weakest at

**Hardware silence detection.** The T5838 mic has an acoustic-activity-detection
mode: PDM clock stopped, listening in analog, raising a WAKE line only when sound
crosses a threshold. The firmware drives it over a bit-banged single-wire protocol
(Nordic's FAKE2C, ~100 kHz out of two GPIOs). After 10 s where mean absolute sample
amplitude stays under 250, it writes the mic's mode registers (2.0 kHz low-pass,
75 dB threshold), clocks it >2.5 ms, and lets the PDM peripheral stop.

The threshold is **fixed in a register, not adaptive**. Conversational speech at 1 m
is ~60 dB against a 75 dB wake threshold — so the sleep/wake behaviour is tuned for
nearby raised voices, not ambient capture. In a loud room it never sleeps; in a
quiet one the first word or two is clipped while the PDM peripheral settles (20 ms
hard-coded settle + 800 ms guard).

**The ring chain.** T5838 → EasyDMA (4-block slab, 400 ms headroom, 6400 B/100 ms)
→ downmix `(L+R)>>1` → PCM ring (32000 B, 1.0 s) → Opus CELT → TX ring (5184 B,
640 ms, 32 frames, 2-byte length prefix) → BLE notify (~83 B, 50/s). Every stage is
fixed-size; nothing allocates at runtime.

Two details carry the engineering:
- **The 100 ms / 20 ms mismatch is deliberate.** The mic delivers 100 ms DMA blocks;
  Opus encodes 20 ms frames. Every mic callback triggers exactly five encoder runs
  back-to-back and five notifications leave in a burst. The stream is *not* evenly
  paced at 50 packets/s — it is five packets, then 100 ms of quiet, forever. A client
  that assumes smooth arrival will mis-measure jitter.
- **Opus is configured for latency, not quality.** `RESTRICTED_LOWDELAY` (no
  lookahead), complexity 3/10, and **DTX, in-band FEC, and packet-loss concealment
  all off**. That last group is consequential: a dropped notification is
  unrecoverable audio, with no application-layer retransmission.

Buffer asymmetry is the tell: one full second of PCM headroom *before* the encoder,
only 640 ms after it. The radio is the tighter deadline.

**Total elastic buffering, mic to radio: ~2.04 s.** A BLE stall longer than that is
permanent loss. Supervision timeout is 4–6 s — so an RF dropout costs up to 6 s of
audio before the link is even declared dead. Rows 1, 2 and 5 of the constraint table
compound: a 6-second fade exceeds a 2-second buffer on a codec with no error
correction, producing silent permanent loss that nothing in the system reports.

**The offline journal.** Disconnect the phone and the pendant journals to SD NAND: a
raw ring of fixed 444-byte records (4-byte big-endian UTC timestamp + 440 bytes
packed Opus), 36 per 16 KB batch, flushed after 1 s idle or when full. On reconnect
the phone issues commands on a separate storage characteristic and the pendant
streams the backlog in 36-packet chunks, advancing a durable read pointer every two
seconds so an interrupted sync resumes rather than restarts.

Five interlocks, three of which fail toward **losing** audio rather than storing
questionable audio — a consistent and defensible bias no user is ever told about:

| Guard | Value | Protects against |
|---|---|---|
| RTC validity gate | epoch >= 1700000000 | audio that can never be placed on a timeline |
| Write-error lockout | 5 consecutive | a dying SD card thrashing; all further audio dropped silently |
| Mount retry | 5 x power-cycle | cold-boot enumeration failure |
| Batch flush | 1000 ms idle | bounded loss window (<=1 s) if power is cut mid-write |
| Critical shutdown | 3500 mV | brown-out FS corruption during a write |

**The journal bug worth internalizing.** The SD fallback is gated on *"no connection
object exists"*, not on *"the send failed"*. So during a stalled-but-alive
connection, the pusher dequeues frames and discards them while the journal sits
unreachable. The connected callback also sleeps 1.3 s inside the Bluetooth RX thread
staggering PHY/MTU/conn-param negotiation, discarding ~1.4 s (~70 Opus frames) on
**every** reconnect — and iOS re-establishes the link many times a day. No counter
anywhere.

**BLE tuning.** 2M PHY, DLE to 251 B, L2CAP MTU 498, requested interval 7.5–15 ms,
with PHY/MTU/conn-param negotiation retried on a timer and the interval re-requested
if the phone grants anything slower than 30 ms — necessary, because iOS routinely
ignores the first request. Backpressure is an 18-in-flight semaphore (20 controller
buffers minus 2); past that the pusher retries 3x with a 1 ms sleep, then drops. No
counter is exposed for how often that happens.

**The packet.** 3-byte header, then payload: bytes 0–1 uint16 LE packet number
(wraps at 65535), byte 2 fragment index, bytes 3..N Opus CELT (~80 B typical,
160 B hard cap). The counter is the **only** loss-detection mechanism in the system:
a client that sees the sequence jump knows audio vanished but cannot ask for it
again.

**The interop trap.** Codec ID 20 means Opus in 10 ms frames; 21 means 20 ms frames.
Current pendants report 21. Both decode as "Opus 16 kHz mono", so a client that
ignores the distinction produces audio that sounds correct but runs at the wrong
rate — every timestamp downstream drifts by 2x. Anticipy's own firmware advertises
codec id 20 with 10 ms/160-sample frames; its iOS side documents id 20 as "Opus
16 kHz mono". Worth re-checking on real hardware before anything decodes.

**Concurrent BLE centrals: 1.** Every third-party SDK competes with the production
app for the single slot, and none of them documents this. An attacker holding the
one allowed connection makes the pendant drop frames rather than fall back to SD —
because the journal is gated on there being no connection *at all*.

**Every GATT characteristic uses plain read/write permissions** — no encryption or
authentication variant. Pairing is compiled in; nothing requires it. Any unpaired
central in range can subscribe to the audio characteristic and stream the wearer's
microphone, on a device with no screen to prompt on. (Anticipy is better here: its
audio notify characteristic is `PERM_READ_ENCRYPT` and requires a fresh
per-connection CCC write. Its DFU control point, however, is unauthenticated.)

---

## 2. Ingest, and what "who said that" actually costs

A socket connects to `/v4/listen` and is **authenticated before the WebSocket
upgrade is accepted** — so an unauthenticated client never gets a live connection to
burn resources on. The session is then bound to exactly one durable Firestore
recording-session record, which is what lets a dropped connection resume the same
conversation instead of starting a new one. That binding is the single most
portable idea in this layer.

Pipeline: auth+bind → server-side Opus→PCM decode → Silero VAD gate → STT socket
(Soniox / Deepgram / Parakeet / Velma-2, 30 ms chunks) → speaker ID → persist
segments onto the live conversation every 0.6 s. Provider selection is a
**connection-time** decision, not per-utterance: once a socket is open, a dead STT
provider terminates the client connection rather than silently degrading.

**Speaker attribution** is the subtlest part. STT providers hand back labels that
are only meaningful within one socket — provider "speaker 1" after a reconnect may
be a different human. So the backend never trusts a provider label directly: it maps
each `(scope, speaker)` pair into a small conversation-local integer, re-hydrating
IDs already stored on the conversation, and **stamps a new provider epoch on every
reconnect**. That is what stops a mid-conversation network blip from silently
renaming everyone.

Separately, a voiceprint check (0.45 similarity against the enrolled profile)
decides whether a turn is you. A distinct, more permissive clustering threshold
groups unknown short clips, capped at eight centroids; when the cap is full a new
speaker is force-merged into the nearest centroid — but **the merged clip is kept
out of that centroid's running mean**, so a ninth speaker cannot drag an existing
person's voiceprint away. Thoughtful defensive design, and also unavoidably wrong
output presented without qualification: the transcript shows a confident speaker
label for a merge the system knows was forced.

**This whole subsystem is illegal for Anticipy.** It is server-side diarization on
raw audio. What survives the local-first law is the *discipline*, not the
implementation: conversation-local ids rather than provider labels, and an epoch
stamped on every reconnect so a blip cannot renumber people.

**Cost is set by the VAD gate, not the socket**: 300 ms pre-roll, 4 s hangover, 0.65
speech threshold. The gate's default differs between the code and the production
chart, so cost behaviour differs by environment.

**Conversation lifecycle.** A background task polls every 5 s against a
client-configured silence timeout, clamped 120 s – 4 h (a user cannot get faster
finalization than two minutes of silence). When silence wins, finalization is
admitted through a Firestore outbox transaction that picks exactly one route — the
mechanism that guarantees a conversation is finalized once even if the socket died,
the pusher restarted, and a Cloud Tasks worker retried simultaneously.

**Live transcripts fight Firestore's write model.** The 0.6 s persistence loop
rewrites the *entire* segment array into one document, twice per 600 ms — exceeding
the ~1/s per-document soft write limit by design and approaching the 1 MiB ceiling
on long conversations. A 4-hour conversation is a real ceiling, approached
deliberately.

---

## 3. Memory — "the part they rebuilt on purpose"

The teardown calls this the part most worth copying. Having read it, that is right,
with one correction to its arithmetic.

**Nothing is born long-term — with one exception that matters.** Enforced in the
durable patch contract rather than by convention: `memory_contracts.py:538`
raises `"Long-term memory cannot be created directly; promote an existing
Short-term item"`. But read the CONDITION on :537, not just the raise — it is
`initial_tier == long_term AND ledger_schema_version != "knowledge_ledger.v1"`.
Omi's newer knowledge-ledger rows are therefore *born durable* and never enter
the short-term elevation loop at all (`canonical_memory_adapter.py:1142-1146`
returns `long_term` for them outright). The invariant is real on the legacy path
and already superseded on the new one, so anyone citing this as "Omi never
creates long-term directly" is quoting a rule Omi's own newer schema is exempt
from. That weakens it as a precedent for us, not strengthens it.

**How to verify these citations, because they look fabricated.**
`backend/models/` is tracked at `44941c1` but is NOT in the sparse working
checkout, so `ls` and a worktree grep both come back empty. Read it with
`git show HEAD:backend/models/memory_contracts.py`. A reviewer on this repo
concluded this citation was dead by checking the worktree alone; the file is
619 lines and the phrase is on 538.
The intake adapter *clamps* a caller's durability intent back to short-term rather
than trusting it (`canonical_memory_adapter.py:1142-1162`): product and API callers
may express intent, but only the admission pipeline may create long-term rows.

**Exactly one terminal route per item.** A batched consolidation call returns
`promote | archive | review | reject` per pending id. The exhaustiveness is not
hoped for — it is checked by set equality **before the first mutation**
(`canonical_consolidation.py:1150-1166`): an omitted item, a duplicated item, or an
invented id fails the whole batch atomically. An unknown route string cannot even
parse (Pydantic `Literal`), so there is no `else` branch that could silently accept
one. If the model fails repeatedly, a bounded retry budget (3) escalates to a forced
`review`; if even that cannot commit, a quarantine; and a TTL backstop forces
`reject` on anything that reaches policy expiry unrouted.

**The server-authored receipt.** This is the mechanism worth stealing outright. A
promotion requires a `PromotionAdmissionReceipt` whose id is
`"padm_" + sha256(canonical_json(identity_payload))[:32]`, self-derived and
self-checked. The model **cannot mint one**: `ConsolidationAgentDecision` has no
receipt, hash, or revision field at all — the receipt is not in the model's output
surface. Every component is server-supplied: `memory_id` and `source_item_revision`
from the authoritative Firestore row, `output_content_hash` computed server-side,
`evidence_ids` intersected against the item's actual evidence (raising if the
model's set drifted), `graph_plan_hash` derived. At commit, `valid_promotion_admission`
re-checks all of it against the **transactionally re-read** row, so any concurrent
edit invalidates the receipt. And a valid receipt is necessary but not sufficient:
it must arrive on a `synthesis` operation, which only the consolidation planner emits.

**Partial promotion is not representable.** One Firestore transaction advances the
operation journal, the apply control state, the state head, the commit journal, the
item(s) *including every superseded row*, the graph assertion (or its deletion), any
review-queue conflict, the projection and vector outbox events, and staged evidence.
There is a fault-injection test that fails the *last* write and asserts
`db.docs == original_docs`.

**The outbox pattern for derived views** — the other thing worth stealing. Search
indexes drift; that is a fact of distributed systems, not a bug to fix. So the
canonical transaction writes only a Firestore row plus outbox events; a bounded
worker drains them, reloading the canonical item before every external write. On
*read*, Pinecone/Typesense hits are candidates only: each is hydrated by id against
`users/{uid}/memory_items/{id}` and passed through a twelve-clause staleness ladder
(projection commit, account generation, item revision, source commit, content hash,
vector updated-at) plus a live access-policy check. Four independent reasons a stale
vector row can produce a candidate but never an answer, the strongest being that
**the vector metadata carries no content at all** — only a content hash. Even a
fully-trusted stale row has no text to leak. Correctness does not depend on the
outbox draining; a stuck outbox costs recall, not truth.

**A read-only legacy adapter instead of a bulk backfill.** `HistoricalMemoryAdapter`
has no create/update/delete methods, deliberately. Mutating a legacy item
materializes it into the canonical store *with the same public id* and writes a
durable suppression override **before** cleaning up the old row. So every crash
window over-suppresses rather than under-suppresses: the failure mode is "the legacy
bytes are still on disk but permanently invisible" — a garbage-collection debt, not
a privacy hole. Closed rows (`invalid_at` or `superseded_by` set) are refused as
migration input outright, which is what stops a superseded legacy row resurrecting.
No bulk migration was ever required.

### Claim audit — memory

| Teardown claim | Verdict |
|---|---|
| Nothing born long-term | CONFIRMED (`memory_contracts.py:537`) |
| 20 items per model call | CONFIRMED (`DEFAULT_CONSOLIDATION_BATCH_THRESHOLD = 20`) |
| Up to 25 calls per pass | CONFIRMED as a cap (bare literal `"25"`, no named constant) |
| **"= 500 items per pass"** | **REFUTED in practice.** `run_canonical_consolidation` fetches without a limit, so it gets `DEFAULT_CONSOLIDATION_QUERY_LIMIT = 250`, not `MAX_..._LIMIT = 500`. Real ceiling ~13 calls / 250 items. The 25-batch cap only binds if someone raises the query limit. |
| Receipt contains uid / generation / batch id / timestamp | **REFUTED** — it contains none of these. It is a content-and-revision binding, not a session token; uid/generation fences live one layer out in `MemoryOperation` vs `MemoryControlState`. |
| Receipt contains hash + decision id | CONFIRMED (`output_content_hash`, `graph_plan_hash`, self-derived `receipt_id`) |
| Model cannot mint a receipt | CONFIRMED — no such field exists on the decision schema |
| 48 h window, 24 h urgency threshold | CONFIRMED (`DEFAULT_SHORT_TERM_TTL = 48h`; `EXPIRY_ADJUDICATION_LOOKAHEAD = TTL/2`, derived, not a literal) |
| Deadline work never starves | CONFIRMED, and stronger than described: a 20 h cooldown skip is overridden by **two** independent conditions — `>10` active short-term rows, or membership in the last-24h expiry band |

Governance weight is real: locked invariants with ids, a seven-day freeze before a
rule can be locked, per-stage control documents that must contain exactly
`{"enabled":false,"generation":1}`, a rollback floor mandating the dual-format
reader stay deployed. Rigorous, and a very large amount of machinery for one product
surface. The operational documentation for it runs longer than most startups' entire
backend. Copy the receipt and the outbox; do not copy the governance.

---

## 4. Reasoning — there is no reasoning engine

The most useful negative result in the teardown. There is no planner, no
chain-of-thought scaffold, no state machine, no LangGraph. The repo *had* one and
deliberately deleted it. What replaced it:

```
while True:
    response = model(system_prompt, messages, tools)
    if no tool calls: break
    results = run_tools_in_parallel(response.tool_calls)
    messages += results
```

No iteration cap. The model decides implicitly whether it needs information. So
"how does Omi reason" is really two questions: what does the model see, and what
stops it. Correctness rests entirely on the model plus the bounds around it — there
is no plan, no reflection step, no self-critique, no verification pass.

**The bounding envelope** (the part Anticipy has none of): 25 tool calls per turn,
8 concurrent executions, 500k context ceiling, 120k input budget, loop detection
over the last 3 calls by canonicalized parameters, 25 s setup deadline, 25 s
first-token deadline, 20 s idle heartbeat, **150 s hard turn deadline** — the real
backstop; everything else is an attempt to fail more gracefully before reaching it.
Before results re-enter context: 60,000 characters shared, 100 conversations, 300
memories, 200 action items, with a truncation instruction appended telling the model
to narrow its query.

**The loop-detection special case** is the elegant bit. An exact repeat normally
raises an error. But if the repeated call is a conversation retrieval and
conversations were already collected, it does not error — it stubs the remaining
calls with *"Relevant conversations are already collected. Answer the user from that
context without calling this tool again."* The model is **redirected instead of
failed**. That shape is portable to a system with no tool loop at all.

**Every exit path guarantees text.** If the loop produces nothing, a canned message
is streamed. If the model errors, the apology is routed through the *same buffer* as
real answer text so it survives into the persisted reply. If the 150 s deadline
fires mid-stream, whatever already reached the user is kept rather than discarded.
The user never gets a blank bubble. Small thing; almost nobody does it.

**Prompt-cache economics shape the architecture.** The current time is deliberately
kept out of the system prompt — the prompt carries the literal string
`"(see <current_datetime> in the latest user message)"` and the real timestamp is
injected into the last user turn, because the system prompt sits behind a cache
breakpoint and a microsecond-resolution timestamp would invalidate the entire cached
prefix on every request. Same motive explains the odd history window
(`10 + ((total - 10) % 8)` — 10 to 17 messages, moving only at 8-message boundaries)
and the frozen, never-reordered tool list. (Anticipy independently discovered the
same lever: moving its grounding sentence from the top to the bottom of the system
prompt made triage 5x cheaper.)

**Scope is fail-closed, and that is the transferable principle.** When you ask from
inside a specific conversation, the prompt says "Answer ONLY using this
conversation" **and** the tools independently intersect their date bounds against
it. An empty intersection returns an error rather than widening the search. Prompt
instructions alone would be a suggestion; enforcing it in the tool layer makes it a
rule.

**Identity never comes from model output.** The authenticated user id is injected
through the runnable config, never parsed from the model's arguments. A prompt
injection can make the model call a tool; it cannot make it call one as somebody
else. Correct architecture, applied consistently.

---

## 5. Action — and the gap that defines the difference between the products

"Taking action" is not a special subsystem. It is the same tool-calling mechanism
used for retrieval; some tools just happen to change the world. 34 core tools, ten
of which mutate state, four of which reach outside Omi into Google Calendar.

> **NO WRITE ACTION REQUIRES CONFIRMATION.** There is no approval step, no preview,
> no dry-run, and no undo anywhere in the tool layer. The only thing between the
> model deciding to delete your calendar and your calendar being deleted is prose in
> a docstring asking it to be careful. For preferences the instruction is explicitly
> the opposite: *"Do NOT ask for confirmation — just save it silently."*

This is a deliberate product stance, not an oversight — Omi is built to feel
frictionless. But the blast radius of one hallucinated tool call is bounded only by
what the tools can reach. The sharpest edge: `delete_calendar_event` accepts a bare
date range with no title filter, searches up to 50 events in the window, and deletes
every match in a loop. Its own docstring admits it. Within one turn the model has a
25-call budget with **no read/write distinction** — 25 such deletions is inside
normal operating limits. Calendar writes are also not idempotent: creation POSTs
carry no idempotency key and the HTTP layer retries 3x on 5xx and timeouts, so a
Google timeout arriving after the event was created produces a duplicate.

**This is the axis on which Anticipy is already ahead, by a wide margin.** The
seatbelt — version-and-digest-bound approval, two non-interchangeable doors for
speech vs. gesture, the same law enforced in Python *and* in a PocketBase hook *and*
in the extension, a receipt that fails closed without verified evidence — is a
different category of thing from a docstring. Nothing in this section should be
ported. It is the control group.

---

## 6. Pusher — the blast wall

A second backend process most descriptions never mention. While listen turns audio
into text, everything else that wants a copy — third-party apps, developer webhooks,
private-cloud archiving, voice-profile extraction — is handled by `pusher`. It
exists because those consumers are slow and untrustworthy in ways transcription is
not: a webhook can hang 30 s (read timeout 30 s, connect 2 s, and with retry delays
`(1, 5, 30)` a fully-hung endpoint occupies its caller ~156 s). If that ran inside
the listen socket, transcription would stall behind someone else's broken server.

**The hot-path decoupling is one line**: `transcript_send` is a plain
`deque.extend`. The STT loop's only contact with the entire webhook world is a
non-blocking append; the socket send happens on a separate task once a second.

Wire protocol: six opcodes in, one out. Anything outside the set closes the
connection with code 1003.

| Opcode | Meaning |
|---|---|
| 100 | **heartbeat/keepalive** (bare 4 bytes, resets the LB idle timer) |
| 101 | raw audio: 4-byte header + 8-byte float64 timestamp + PCM16 |
| 102 | transcript segment (JSON) |
| 103 | conversation id (raw UTF-8, *not* JSON) |
| 104 | finalize |
| 105 | speaker sample (120 s minimum age, consumer-side) |
| 201 | result — server→client only, best-effort, explicitly NOT authoritative |

**Bounded queues with an eviction counter** — the observability pattern worth
copying. Transcripts 50 deep, audio 20, speaker samples 100, private-cloud 20. When
full, `append_bounded` does `queue.popleft()` — **oldest evicted** — and increments
`pusher_queue_drops_total{queue}` plus `pusher_queue_dropped_bytes_total{queue}`.
The underlying `deque(maxlen=N)` would evict anyway; `append_bounded` exists purely
to make it *observable*. That is the whole point, and it is exactly what Anticipy's
silent drops need.

**Finalization under a durable claim.** Opcode 104 spawns a task that must first win
a Firestore transaction checking identity, checking the conversation is not already
terminal, bumping a lease epoch, and taking a **1500 s** lease. The task is
process-scoped, not session-scoped, so it survives the listen socket closing
immediately afterward — and the 201 reply is best-effort, so if the listener already
hung up the Firestore transition still stands. *The database is the truth; the
acknowledgement is a courtesy.*

**Degradation is the right shape.** When pusher is down, a pod-level circuit breaker
(20 failures / 30 s window / 60 s cooldown) trips, sessions mark themselves
degraded, and a reconnect loop retries 6 times with exponential backoff **and**
multiplicative ±25% jitter, then a 60 s cooldown, then a single probe. Transcription
keeps working the entire time — you just lose realtime app delivery until it
recovers. The core loop survives when the periphery dies.

### Claim audit — pusher

| Teardown claim | Verdict |
|---|---|
| Opcode 100 = "session setup, 8–48 kHz" | **REFUTED.** 100 is a heartbeat, a bare 4-byte frame whose handler is `continue`. Sample rate is a handshake **query parameter**, validated at admission with close code 1008 — unrelated to opcode 100. |
| Unknown opcode closes the connection | CONFIRMED, mechanism differs — `frame_header` raises, the loop unwinds, `finally` closes with 1003 |
| Shared 20 MiB per-session budget across the three queues | **PARTIAL.** `BUFFERED_AUDIO_MAX_BYTES = 20 MiB` is exact and per-session, but transcript and speaker-sample queues pass no `byte_budget` — they are bounded by item count only. The budget covers the audio paths. |
| Oldest evicted, counter increments | CONFIRMED, exactly |
| 1500 s lease, epoch bump, process-scoped | CONFIRMED, exactly; and the transaction has three more gates the teardown omits (BYOK admission, generation fencing, live-lease rejection) |
| 6 retries, backoff + jitter, 60 s cooldown, single probe | CONFIRMED, exactly. Nuance: there are **two nested retry layers** — the 6-attempt session machine wraps an inner 5-attempt connect with its own additive jitter, so worst case is ~30 socket attempts before DEGRADED. |
| "Slow webhooks must not stall the hot path" rationale | **Not stated anywhere in the checkout.** The referenced doc is absent from the sparse tree. The in-repo rationale for the separate image is **memory/OOM** (jemalloc, RSS growth from bytearray churn). The mechanism is real; the stated motive is inference. |

---

## 7. The model gateway

~50 model-calling jobs, none of which names a model. Each names a **feature**, and a
routing layer decides what runs. Every call resolves to a lane `omi:auto:<feature>`
and goes to an in-cluster gateway that picks the provider, enforces one absolute
deadline, records the attempt, and prices it. **Raw model names are rejected
outright** — you cannot ask for "gpt-5.6-luna", only for "the conversation-structuring
lane". Provider is declared explicitly per feature and never inferred from the model
name, which prevents a whole class of routing accidents.

Three things make it more than indirection:
- **BYOK changes the route.** Your key arrives as a header, is fingerprint-checked
  against an enrolled hash, and can switch both provider and model for that call —
  and is marked `not_omi_cost` in the ledger. Omi never spends its own key on your
  request and never bills itself for it.
- **Every attempt is priced.** An immutable ledger row costed from a rate card,
  splitting cached from uncached input tokens. A model with **no rate card is
  recorded as `unpriced`, never as zero.** That distinction is the difference
  between a cost system you can trust and one that quietly under-reports.
- **Rollout is per-lane** — shadow, canary, active — with canary sampling hashing
  the route id *together with the request content*, so the same request
  deterministically stays on the same side instead of flickering mid-conversation.

And the finding that surprised the auditors: **every shipped lane has
`max_attempts: 1` and an empty fallback list**, the HTTP clients carry no SDK-level
retry, and the backend sets `max_retries=0` where the client it replaced defaulted
to 1. A single 429 or 5xx fails the request outright, across ~48 features, with no
failover. The machinery for retries and last-known-good routing is fully built and
configured off — a reliability regression from the path it replaced, confirmed under
verification. Anticipy has the same hole for a simpler reason: it never built the
machinery.

---

## 8. Proactivity — the most conservatively built thing in the product

Everything else is reactive. The proactive engine decides to interrupt you, and its
design is mostly a stack of reasons to stay quiet.

Pipeline: the same model call that writes the conversation summary extracts tasks
tagged with confidence and owner → a hard floor where **capture AND ownership must
both clear 0.80** → route by source → **budget reserved before any model call** →
judge.

Two orderings are the whole lesson:
1. **Anything missing a confidence score defaults to 0.5 — below the floor.** Absent
   signals are silently ignored rather than optimistically accepted. The polarity is
   the point.
2. **The budget is reserved *before* the model is called, not after** (10/day,
   2/30min), so a burst of activity cannot outrun the limiter. Anticipy *checks* its
   cap instead of reserving it, and only on one outbound path — which is precisely
   how research results and clock texts flow around a 3/day ceiling.

The judge is one model call over at most 20 candidates, prompted to select **zero to
three** items and only when acting now is materially better than acting later, with
*"empty is the default answer"*. And it explicitly frames the candidate text as
**untrusted user data whose embedded instructions must be ignored** — a real
prompt-injection defence on a surface where the content came from your own recorded
conversations. Anticipy needs that sentence more than Omi does: its untrusted input
is the transcript of the owner's life, and it has an approval gate an injected
instruction would love to talk past.

A separate, older "mentor" pipeline runs off the live transcript with its own
suppressions: relevance thresholds 0.60–0.92 by frequency setting, a five-minute
minimum gap enforced in **both** local memory and Redis, a shared daily cap of nine,
and a final critic that can veto a draft after it is written.

The honest read: two independent proactive systems with separate budgets, separate
storage and separate suppression logic, both heavily throttled, one shipping with an
empty judge in production — the expensive shortlist is built and then not acted on.
The conservatism is admirable; the duplication is not.

---

## 9. The three things to take, per the teardown's own conclusion

> Push intelligence off the constrained device entirely — resist every temptation to
> be clever in firmware; **bound your agent loop rather than planning it** — a call
> ceiling, a wall-clock deadline, result size caps, and a guaranteed answer on every
> exit path will outperform an orchestration framework; and **make derived state
> re-verify against an authority** — the moment a search index can answer a question
> by itself, you have two sources of truth and one of them is wrong.

The failures cluster in the seams — between a guard and the action it guards,
between a doc and the code it describes, between a hardened path and its unhardened
sibling. One bug shape recurred across four unrelated subsystems and survived the
pass designed to kill it:

> **The guard and the action look at different things.** Ownership checks the URL
> path while the write reads the body. The SD journal checks whether a connection
> object exists while the pusher checks whether a send succeeded. The codec check
> asks whether bytes came back rather than whether the value is trustworthy. The
> SSRF filter checks an IPv4 form while the connection accepts an IPv6 one.

That is worth building a check around rather than fixing four times — and it is a
shape Anticipy should grep itself for, since its own `workflow_guard.pb.js` exists
precisely because "a check that runs only in the Python that minted the plan is not
a check, it is a comment."

---

## Method note

Three subsystem reads were run against the sparse checkout, each asked to quote real
code and to flag where the teardown does not match source. Several load-bearing
definitions live in `backend/models/`, which is tracked at `44941c1` but not
materialized by the sparse checkout; those were read from the git object store via
`git show HEAD:<path>` and line numbers are the blob's.

Two subsystem reads (firmware capture chain in depth, and the agent-loop bounding
envelope in depth) were cut short by a session rate limit and re-run separately;
where this document states a firmware constant without a `file:line`, it is from the
teardown and **not yet independently confirmed against source**. Those are the lines
to verify before anyone writes code against them.
