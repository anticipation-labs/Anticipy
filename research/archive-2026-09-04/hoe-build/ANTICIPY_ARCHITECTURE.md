# Anticipy — Technical System Architecture

*The engineering design of record. Every claim about the running system is grounded in
`engine/anticipy_engine/` at the cited file:line; where the system does not yet do a thing,
this document says so plainly (Section 7). Two naming notes up front, because both names
appear in the tree and only one of each is real:*

- *The wired proactive brain is **`core/proactive.py::ProactiveEngine`** — constructed by
  `core/control_core.py:231`. The similarly-named `proactive/engine.py::ProactiveEngine.tick`
  is a **vestigial scaffold stub** (`proposals = []`, `proactive/engine.py:25`) that nothing
  on the hot path calls. When this document says "the engine decides," it means
  `core/proactive.py`.*
- *There are two memory subsystems: the four-drawer store under `memory/` (the durable
  substrate) and the `live_memory/` capture+inject layer that writes into and reads out of
  it. Both are real; Section 4 maps them.*

---

## 1. System overview

Anticipy is a **local-first FastAPI hub** (`main.py`) that binds to `127.0.0.1` only
(`main.py:11`, `:130`) and routes every input — typed transcript, uploaded MP3, live Mac-mic
audio, or an inbound SMS — through one inference brain that decides **act / ask / silent**, then
executes through three "hands" (API, browser, voice/SMS) and records everything to a durable
memory and an inspectable glass-box log.

The spine is a five-room pipeline (the "rooms" are the codebase's own term). An event enters,
and each room can only ever make the decision **safer** (push it toward SILENT/ASK), never more
aggressive — that one-way property is the structural guarantee behind the cardinal-sin rule.

```
                          ┌──────────────────────────────────────────────────────────────┐
   CAPTURE                │                     THE INFERENCE BRAIN                        │
 (words only,             │                  (core/proactive.py::ProactiveEngine)         │
  never acts)             │                                                                │
                          │   Room 1        Room 1.5       Room 2          Room 2.6        │
 Mac mic ─┐               │  ┌───────┐     ┌────────┐    ┌────────┐      ┌──────────┐      │
 (ffmpeg, │   transcribe  │  │TRIAGE │ ──► │DECIDER │──► │HARM-   │ ───► │ DEBOUNCE │      │
  8s win) │   (Whisper,   │  │ regex │     │cheap   │    │LINE    │      │ money    │      │
 MP3 up   ├─► local,      ├─►│ shape │     │LLM     │    │determ- │      │ retract  │      │
 typed    │   noise-gate) │  │ recall│     │commit? │    │inistic │      │ window   │      │
 SMS in  ─┘               │  └───────┘     └────────┘    └───┬────┘      └────┬─────┘      │
                          │   drop ~99%    SILENT/ASK/        │ act/ask/       │           │
                          │   junk         ACT/UNAVAIL        │ block          │           │
                          │                   │              ┌▼─────────────┐  │           │
                          │   reads memory ◄──┴──────────────│  decision    │◄─┘           │
                          │   context for the gray middle    └──┬───────────┘              │
                          └─────────────────────────────────────┼──────────────────────────┘
                                                                 │
                  ┌──────────────────────────────────────────────┼─────────────────────────┐
                  │  ACT                  ASK (Room 4/5)          │  BLOCKED                 │
                  │  orchestrator         pending + budget        │  money / never-execute   │
                  │  start_goal           SMS/app round-trip      │  receipt, no steps       │
                  └───────┬──────────────────────┬───────────────┴──────────────────────────┘
                          │                       │
            ┌─────────────▼─────────────┐   ┌─────▼────────────────────────────────┐
            │         THE HANDS         │   │   CHANNELS (the loop-closer)          │
            │  api_hand   browser_hand  │   │   text.py (SMS) call.py (voice)       │
            │  Arcade     your Chrome   │   │   inbound poll: YES/NO resolves asks   │
            │  +read-back +nav-wall     │   │   "I'll call you at 2:45"              │
            └─────────────┬─────────────┘   └─────┬─────────────────────────────────┘
                          │                       │
                          ▼                       ▼
            ┌───────────────────────────────────────────────────────────────────────┐
            │  MEMORY  (memory/store.py: 4 SQLite drawers + cosine vector index)      │
            │  profile · open_loops (the commitment ledger) · history · derived       │
            │  written by live_memory/capture.py · read by live_memory/inject.py      │
            └───────────────────────────────────────────────────────────────────────┘
                          ▲                                            │
                          │  Room 3: TriggerWatcher ticks the ledger ──┘  (the alarm clock —
                          └──── what makes it anticipatory, not just reactive)
```

**Room-by-room (all in `core/proactive.py::on_event`):**

| Room | File | What it does | Failure direction |
|---|---|---|---|
| 1 — Triage | `proactive/triage.py` | Cheap regex **speech-act-shape** classifier; drops the ~99% of ambient lines that aren't actionable. Zero model calls in stub. | Recall-biased: when unsure, **PASS** (a dropped real task is unrecoverable; junk dies cheaply downstream). |
| 1.5 — Decider | `proactive/decider.py` | One cheap-LLM call: *did the person actually commit?* Returns `ACT/ASK/SILENT/UNAVAILABLE`. **Live-only** (None in stub, `core/proactive.py:94`). | Biased to SILENT; an unread line (`UNAVAILABLE`) **never acts** — it defers for a bounded retry (`:176`). |
| 2 — Harm-line | `proactive/harm.py` | Deterministic, inspectable policy: *is this detrimental?* Confident-no → ACT; money/destroy/etc. → BLOCK; unsure → ASK. | Fail-safe ASK on anything unclassified (`harm.py:354`). |
| 2.6 — Debounce | `proactive/debounce.py` | Holds an ambient **money-transfer** command one breath (240s / 2 events) so a spoken retraction can kill it before it ever asks. | On money, fails toward **silence**, never act. |
| 3 — Trigger | `proactive/trigger.py` | The alarm clock: ticks the open-loop ledger against the clock; a due commitment fires **exactly once** through the same harm-line. | Mark-before-act (`core/proactive.py:558`): a crash mid-fire loses the firing, never double-fires. |
| 4/5 — Channel + Budget | `channels/`, `proactive/budget.py` | Sends the ASK; caps proactive interrupts (3–5/day soft, hard boot/window guard). | Over-budget → suppressed (not executed *and* not asked). |

The two sacred rules are enforced structurally, not by prompt:
- **Vent = cardinal sin.** Every negative shape in triage (`_VENT_STRONG`, `_CONDITIONAL_VENT`,
  `_DELEGATE_VENT`, `_TRAILING_HEDGE`, …) is checked **before** any positive cue, and the decider
  + harm-line can only downgrade. A vent that reaches capture is written to the *inert* remember-list
  but **refused** entry to any active drawer (`live_memory/capture.py:166`).
- **Money = the only hard stop.** `NEVER_EXECUTE_CATEGORIES = {"money"}` (`core/proactive.py:52`);
  an approved money ask is still blocked (`:474`); a send carrying any money signal cannot be
  downgraded to a casual auto-send (the MONEY INTERLOCK, `harm.py:385`); and the browser nav-wall
  hard-denies banking/payment hosts (`core/navwall.py:238`).

---

## 2. How the implied / contextual inference is computed, end to end

This is the founder's moat and the **honest weak point of the current build**. The three tiers
from the product brief map onto the engine as follows:

- **Explicit** ("remind me to call the dentist at 3") — fully handled. Triage's
  `_INTENT`/`_REMIND_REQ`/imperative shapes catch it; the decider confirms commitment; the
  harm-line routes a reminder to ACT.
- **Vented / sarcasm** ("I should just quit and move to the woods") — fully handled, and the
  most-hardened path. `_VENT_FRAME`/`_CONDITIONAL_VENT` (`triage.py:121`, `:133`) silence it at
  Room 1; if it somehow survives, the decider's prompt explicitly classes vents as SILENT
  (`decider.py:119`), and capture refuses it a durable drawer.
- **Implied / contextual** (a real obligation never said as a command, often not even aimed at
  the assistant) — **partially handled, and only along certain shapes.** This section traces
  exactly what fires and what doesn't.

### 2.1 The shapes the engine *does* catch today

Triage already encodes several conventionalized implied-obligation frames as positives —
these are felicity-condition tests in disguise (the research's point):

- **Reported promise** (`_RP_FRAME`, `triage.py:251`): *"Sam needs the decking by Friday; I told
  him I'd send it."* A first-person `told/promised/said … I'd <verb> <content>` frame is a real
  owned commitment. The implementation is genuinely careful — it denies backshift narration
  ("I told him I'd **sent** it" = already done, `_RP_PARTICIPLES`), deferral ("I'd think about
  it"), regret/retort ("…didn't I?"), habitual ("every week I told him…"), and vows
  ("I'd be a better person"). This is the closest thing to true implied-tier reasoning in the
  codebase.
- **Ownerless delegation** (`_DELEGATE`, `triage.py:496`): *"someone should chase the vendor"* —
  voicing an unowned task **is** the handoff — unless it's destructive hyperbole
  (`_DELEGATE_VENT`).
- **First-person deadline obligation** (`_DEADLINE` + `_FIRST_PERSON`, `triage.py:681`): a
  "deadline" with skin in the game ("my filing deadline is Thursday") passes; third-party
  narration ("the paralegal flagged the deadline") does not.
- **Spoken task idioms with no clause-initial verb** — `_CAL_PUT`, `_LIST_PUT`, `_CART_PUT`,
  `_CAUSATIVE_GET`, `_GET_TO_TAIL`, `_BENEF_TAIL`: *"that goes on the calendar,"* *"get the
  waivers to the front office by noon."*

For any of these that survive, **due-time grounding** turns the spoken deadline into a concrete
trigger. `live_memory/duetime.py::parse_due` deterministically resolves "before Friday," "at 3,"
"tonight," "in two hours" against the **utterance's own clock** (`meta.observed_at`, never engine
processing time — `duetime.py:8`), and `capture.py:170` stamps `due_ts` and
`remind_ts = due_ts − 15min` onto the open-loop. Room 3's `TriggerWatcher` then fires the reminder
exactly once when `remind_ts ≤ now` (`trigger.py:38`). **That is the mechanism for "surface it
later, cold"** — but only for a line that triage already promoted *and* that carried a parseable
time anchor.

### 2.2 The scoring gate that exists — and the one signal it's missing

The only place a real **numerical confidence threshold** lives is the harm-line's send path
(`harm.py:391`):

```
downgrade a SEND to an auto-ACT  ⇔  (not abstain) AND top_relevance ≥ send_casual_floor (0.66)
                                     AND the recipient is a casual contact
```

`top_relevance` and `abstain` come from memory retrieval (`live_memory/inject.py:86`): the cosine
of the best active memory to the query, with a calibrated abstain floor (live 0.66, fit on a
held-out slice by Youden's J — `inject.py:36`). When memory can't confidently vouch, the path
**fails safe to ASK** and flags `memory_forced` so the system counts how often weak confidence
forces a question. This is the **template the implied tier should generalize** — and today it does
*not*: the decider returns a bare `ACT/ASK/SILENT` word with **no confidence number, no memory of
prior commitments, and no reasoning about who said it to whom** (`decider.py:147`). The single
load-bearing signal the implied tier needs — *directedness/ownership* (was this aimed at the user,
by a relevant person?) — has **no axis anywhere in the pipeline**. The decider's prompt even
instructs it to treat words spoken to a present third party as SILENT (`decider.py:100`), which is
correct for the wife-says-"grab-the-kids" case *only if* the relationship makes it binding — a
judgment the engine cannot currently make because it has no social graph wired into the decision.

### 2.3 Memory's role, and the recurrence substrate

Memory contributes to the implied tier in three ways today, two real and one latent:

1. **Gray-middle resolution** (real): `inject.py` assembles per-query context (semantic +
   keyword + recency + importance over profile/history/derived, plus *all* open loops always),
   and the harm-line reads it to resolve casual-vs-binding sends and cart targets.
2. **The inert remember-list** (real, and the honest safety valve): every kept line is *also*
   written generously to a **separate, pull-only table** with **no due/remind/trigger field**
   (`live_memory/capture.py:116`, `remember.py`). Nothing on any background loop reads it, so it
   can never fire. A daily review enriches it display-only with an inferred `{task, people,
   due_phrase, confidence}` that **never** reaches the decider/harm-line/trigger
   (`main.py:619` docstring). This is exactly "prepare-then-park": the catch is preserved cold,
   surfaced only on an explicit owner pull or press-go (`main.py:638`).
3. **Recurrence inference** (latent): `live_memory/infer.py` derives routines/recurring people by
   frequency (`min_count=3`, confidence capped `< 1.0`, never promoted to a stated fact —
   `infer.py:40`). It is frequency-only and cold; it is **not** consulted by the act/ask decision.

### 2.4 The end-to-end implied path, honestly

```
utterance ─► triage shape match? ──no──► dropped from the ACTIVE path
                  │ yes                   (still written to the inert remember-list,
                  ▼                         pull-only, can never fire — the cold catch)
            decider: real commitment?  (cheap LLM, no confidence, no social signal)
                  │ ACT/ASK
                  ▼
            harm-line + memory (top_relevance/abstain) ─► act / ask / block
                  │
                  ▼
            if it carried a parseable deadline → due_ts/remind_ts stamped →
            Room 3 fires it cold at remind_ts ("surface it later")
```

**Verdict:** the *cold-surfacing machinery* (remember-list + due-time grounding + trigger) is
built and real. The *recognition* of a genuinely implied obligation is only as good as triage's
shape lexicon plus a confidence-free decider — there is **no directedness/ownership scoring and no
confidence number on the implied decision**. Closing that gap (a directedness axis + a generalized
confidence threshold modeled on the harm-line's `send_casual_floor`) is the single highest-value
brain change, and it is **not yet done**.

---

## 3. The capture layer — and the noise gating that prevents garbage→spam

Three intake surfaces converge on one ingestion path (`main.py::owner_ingest`,
`core.owner_ingest`):

| Surface | Entry | Mechanism |
|---|---|---|
| Typed transcript / text upload | `POST /owner/ingest`, `/owner/ingest-file` (`main.py:719`, `:725`) | UTF-8 read; staged-path + size + SSRF-style guards. |
| MP3 / audio upload | `/owner/ingest-file` → `capture/transcribe.py` (`main.py:748`) | Local ffmpeg + Whisper; never a cloud STT call. |
| Always-on Mac mic | `POST /listen/start` → `capture/mac_mic.py` (`main.py:778`) | ffmpeg `avfoundation` records rolling 8s windows; each is transcribed locally and fed to `owner_ingest(execute_actions=True)`. |
| Inbound SMS (the loop back) | `channels/inbound.py` poller (`main.py:113`) | YES/NO resolves a pending ask; free speech re-ingests. |

**Noise gating is layered — it is the defense against the garbage-in → spam-out failure, and it
runs at three depths before a single decision is made:**

1. **Acoustic / Whisper-level** (`capture/transcribe.py`): ffmpeg `silencedetect` segments speech
   from silence (`-35dB`, 1s min — `transcribe.py:158`) so silence is never transcribed; and every
   Whisper segment is dropped if `no_speech_prob ≥ 0.85`, `avg_logprob ≤ −1.25`, or
   `compression_ratio ≥ 2.8`, or it looks repetitive (`_drop_segment`, `:294`). This kills the
   single worst ambient-mic failure: **Whisper hallucinating stock phrases on near-silence.**
2. **Mic-window-level** (`capture/mac_mic.py:32`): an explicit `_NOISE` set
   (`"you", "thank you", "thanks for watching", "bye", …`) plus a `len < 4` floor (`:42`) discards
   exactly the phrases Whisper invents in a quiet room, so a silent room **never fabricates a task**.
3. **Keep/drop gate** (`live_memory/capture.py::should_keep`, `:46`): drops empty/short pure-filler
   before classification.

Only past all three does a line reach triage (Room 1), which drops ~99% of the *remaining*
non-actionable speech with zero model calls. The net effect: the always-listening loop can run on
a real, noisy room without each ambient mutter becoming a candidate action — and even a candidate
that slips through still has to clear the decider, the harm-line, *and* the interrupt budget before
it can ever interrupt the user.

**Pendant:** `capture/pendant_phone.py` exists as the future surface; the mic path is the
shipping always-on capture today. Both emit the same `CaptureEvent` through the same sink, so the
brain is surface-agnostic.

---

## 4. Memory + the per-person mesh

**Substrate** (`memory/store.py`): one local SQLite DB, four **isolated drawers** keyed by `kind`
(never merged), plus a cosine vector index that scans stored per-row embeddings (`store.py:147` —
"fine at single-user scale; swap for sqlite-vec later"):

| Drawer | Kind | Role |
|---|---|---|
| `profile` | `profile_fact` | Slow-changing facts about the user **and their people**. |
| `open_loops` | `open_loop` | The **deterministic commitment ledger** — state `open/waiting/done`, retrieved without embeddings so a ball is **never silently lost** (`inject.py:64`). |
| `history` | `history` | Timestamped episodic append-log, embedded for recall. |
| `derived` | `derived` | Inferred routines/people **with confidence < 1.0**, never promoted to stated fact. |

The DB self-heals: on open it runs `PRAGMA integrity_check`, and on corruption it quarantines the
bad file (`.corrupt-<ts>`) and rebuilds, surfacing `recovered_corruption` to the readiness checklist
(`store.py:90`, `main.py:421`).

**Write path** (`live_memory/capture.py`): keep/drop → classify into a drawer → extract people →
dedupe → write, **plus** the parallel inert remember-list write (Section 2.3). The cardinal-sin
guard here is structural: a vent-shaped line is refused entry to an active drawer even if it
matched a `_PROFILE`/`_COMMIT` cue (`capture.py:166`).

**Read path** (`live_memory/inject.py`): hybrid retrieval — `0.55·semantic + 0.30·keyword +
0.10·recency + 0.05·importance` (`inject.py:79`) over the fuzzy drawers, with **all** active open
loops always prepended (the spine), fit to a char budget. It returns `top_relevance` + `abstain`
(the calibrated semantic-confidence signal the harm-line consumes).

**Per-person mesh — what's real vs. aspirational:** people are first-class — extracted on capture
(`extract_people`, `capture.py:88`), counted into recurring-person derived facts (`infer.py:76`),
and used by the harm-line's casual-recipient check. The **API-credential** mesh is genuinely
per-person: `hands/token_vault.py` lets each user authenticate Arcade with **their own**
short-lived vault token rather than a shared key (`api_hand.py:156` `_live_client`), and onboarding
writes a per-service connect-loop (`main.py:843` `/onboard/discover`). What does **not** yet exist
is a relationship graph that feeds *directedness* into the inference decision (Section 2.2) — the
mesh stores who recurs and whose token to use, but the brain does not yet reason about whether a
given line was an obligation *to the user from a specific person*.

---

## 5. The action arms, the read-back proof, and the money hard-stop

A decision to ACT hands a `Goal` to the orchestrator, which drives `Step`s to the hands. Two arms:

### 5.1 API hand (`hands/api_hand.py`) — Arcade: Gmail / Calendar / Slack
A **dumb executor**: it receives a fully-resolved, already-gated job and does it; it never decides
who someone is or whether to act (`api_hand.py:7`). **Mock by default; live only when explicitly
set.** The defining property is **independent read-back as the only proof of done**:

> The write call's own echo is **never** trusted ("the actor must not grade its own homework",
> `api_hand.py:58`). After a write succeeds, the hand issues a **second, independent**
> `tools.execute` against a read tool and confirms the just-written id actually appears — twice
> (`READ_BACK_READS ≥ 2`, `:35`) via `confirm_stable_artifact` (`agent/proof.py`). If the read-back
> can't re-observe it, the result is **failed/needs_human, never success** (`:487`).

The duplicate-send hole is closed structurally: a write whose side-effect already fired but wasn't
confirmed is recorded in `_fired` and a retry **re-verifies, never re-executes** (`:277`, `:334`).
Unverified read tools are left as `None` so the path **fails closed** rather than inventing an
Arcade tool name (`:451`). A live calendar write with no concrete `start_datetime`/`end_datetime`
is blocked outright (`:599`).

### 5.2 Browser hand (`hands/browser_hand.py`) — the per-person 10% with no API
Drives a WebVoyager agent inside the user's own logged-in Chrome over an authenticated WebSocket.
It **never fakes success**: no screenshot/proof → failed (`:277`); login-wall/captcha → handed back
(`:282`); the form arm **fills to the submit screen and stops** — a clean prepare returns
`needs_human` with the filled-field read-back, and a reported submit is refused as impossible by
construction (`_handle_prepare_form`, `:166`, `:193`).

This arm sits squarely on the "lethal trifecta" (real credentials + untrusted page text + exfil
channels), so the defense is **code-level, not prompt-level**: `core/navwall.py::nav_block_reason`
runs at the bridge on **every** navigate the model emits and hard-denies (a) non-http(s) schemes
incl. `file://`/`chrome://`/`javascript:`, (b) private/loopback/cloud-metadata hosts incl. DNS-rebind
(SSRF), and (c) **banking/payment/credential** destinations by keyword + curated brand list
(`navwall.py:94`, `:238`). It is **fail-closed** on any parse error. The entry endpoints add a
second SSRF gate (`main.py::_assert_public_agent_url`).

### 5.3 The money hard-stop — defense in depth
Money is the **only** hard action stop, enforced in five independent places so no single bug can
auto-spend:
1. Triage's `_COUNTERMAND`/`_HARD` keep pure money commands gated.
2. Harm-line `_HARD` "money" category overrides everything → ASK/BLOCK (`harm.py:113`, `:297`).
3. The **MONEY INTERLOCK** forbids a money-signal send from being downgraded to a casual auto-act,
   even with high memory confidence (`harm.py:385`).
4. Room 2.6 debounce holds an ambient transfer one breath for a retraction (`debounce.py`).
5. `NEVER_EXECUTE_CATEGORIES={"money"}` blocks it at decision time **and even after an explicit
   YES** (`core/proactive.py:52`, `:474`) — an approved money ask still lands a refusal receipt.
6. The browser nav-wall denies payment hosts (`navwall.py`).

### 5.4 Closing the loop — voice/SMS (`channels/`)
`channels/text.py` (SMS) and `channels/call.py` (voice) deliver the ask and the "I'll call you at
2:45" reminder. The call uses a **natural Polly neural voice** (default `Joanna-Neural`, never the
robotic default — `call.py:52`) and can upgrade to a two-way Twilio ConversationRelay socket when a
public `wss://` URL is configured (`call.py:56`), falling back to a one-shot `<Say>` that "can never
strand a call mid-turn." Inbound replies are polled (`channels/inbound.py`); a YES resumes the
**exact** paused goal to done, a NO drops it and records the decline so Room 5 suppresses that
action-type next time (`core/proactive.py:478`).

---

## 6. Data model + storage

**Everything is local-first.** The hub binds to loopback; memory is a single SQLite file under
`.anticipy-data/` (gitignored; `ANTICIPY_DATA_DIR` overrides — `store.py:34`). No cloud database.

**Core envelopes** (`core/envelopes.py`): `Event` (a captured utterance + `meta` carrying the
utterance clock `observed_at`/`timezone`), `Goal` → `Step` (with `GoalState`, `StepState`, and a
`Risk` of `low/needs_confirm/ask_human`), `Job`/`Result` (the frozen worker contract:
`{success, failed, needs_human}` — explicitly *not* to be extended; "needs another worker" is
expressed as `failed + output.needs_other_worker=True` so reroutes happen on the existing path,
`api_hand.py:9`).

**`MemoryItem`** (`shared/schema.py`, persisted by `store.py:119`):
`id, kind, text, fields, people[], timestamp, updated_at, provenance, confidence, importance,
status, embedding(JSON)`. Key conventions:
- `open_loop.fields` carries `due_ts`, `remind_ts`, `capture_key` (dedupe), and `fired_at` (the
  durable fire-once stamp that survives restart — `trigger.py:38`).
- `derived.confidence` is always `< 1.0` and `provenance="inferred"` — never promoted (`infer.py:40`).
- The inert remember-list is a **separate table**, deliberately *not* a drawer, with no temporal
  fields (`remember.py`).

**Durable side-files for crash-safety** (all atomic write-then-rename, all fail toward silence):
- the decider **outage queue** (`_deferred_path`) so a restart during a quota window doesn't eat
  unread lines (`core/proactive.py:311`);
- the **pending-ask map** (`_pending_path`) so an owner's YES/NO still matches after a restart, and
  only re-loads entries whose goal is still `waiting` (`:331`).

**Observability:** `core/glassbox.py` is an append-only activity log (`GET /glassbox`) and
`core/scorecard.py` a health readout (`GET /scorecard`) — decisions, categories, `memory_forced`
counts, model cost. These are the audit substrate; `main.py:421` `/readiness` and `/connect`
surface what's live vs. mock without ever exposing a secret value.

---

## 7. The honest gap list — built vs. stubbed vs. missing

**BUILT and verified (real code, real guards):**
- The five-room brain with the one-way safety property (`core/proactive.py`); triage's deep
  speech-act shape lexicon; the deterministic harm-line; the cardinal-sin and money guards in
  multiple independent layers.
- Local capture: Mac-mic always-on (`capture/mac_mic.py`), MP3/Whisper (`capture/transcribe.py`),
  three-layer noise gating.
- Four-drawer local memory with corruption self-heal; hybrid retrieval with a calibrated
  abstain/confidence signal; the **inert remember-list** (the prepare-then-park safety valve);
  due-time grounding + the fire-once trigger (the cold-surfacing machinery).
- API hand with **independent two-read read-back** and duplicate-send protection; browser hand
  that never fakes success; the code-level **nav-wall** (SSRF + sensitive-host hard deny).
- Voice/SMS loop with a natural voice and durable, restart-safe ask resolution.

**STUBBED (scaffold present, real logic absent):**
- **`proactive/engine.py::ProactiveEngine.tick`** — the named "primary loop" is a stub:
  `proposals = []` (`proactive/engine.py:25`). The real proactive loop is the event-driven
  `core/proactive.py` + Room 3 trigger; there is **no autonomous "scan memory and propose"
  generator** wired end-to-end. The "surface it later" path works only for lines that already
  became time-stamped open loops.
- **Live-mode enrichment seams** marked `TODO(live)` in `capture.py:145`, `infer.py:57`,
  `inject.py:91` — the cheap-model gate/extraction, richer routine inference, and ambiguity
  escalation are scaffolded but run as deterministic rules today.
- **Slack/Docs read-back tools** left as `None` (`api_hand.py:79`) — those write paths fail
  closed until the verified Arcade read tool is wired.

**MISSING (the real frontier to the Owner Test):**
1. **The implied-tier social signal.** No *directedness/ownership* axis anywhere; the decider has
   **no confidence number and no memory of prior commitments** (`decider.py:147`). The wife's
   "grab the kids" / the sister-conversation prescription are caught only if they happen to match a
   triage shape *and* carry a parseable deadline — not because the engine reasoned that a relevant
   person handed the user an obligation. This is the moat, and it is the biggest gap.
2. **Ambient-mic catch-rate is unvalidated.** The noise gating exists, but real-world overlapping
   speakers, partial utterances, and room noise are unproven against the engine's clean-transcript
   tuning. Catch-rate on messy live audio is the unmeasured number.
3. **A starved brain.** The decider/enrichment seams are gated on a real model provider; on the
   free tier (429s, 60s+/call) the decider frequently returns `UNAVAILABLE` and the engine fails
   toward silence — correct safety behavior, but it caps the implied tier in practice. Funding the
   model is a prerequisite only the owner can clear.
4. **No proactive digest generator.** The product's "one calm end-of-day digest" is a goal, not a
   shipped surface — `proactive/engine.py::tick` is the slot where it would live, and it is empty.
5. **Premium product shell.** Out of architectural scope, but load-bearing for the Owner Test:
   the current surface is the localhost dev console; the felt-product layer is a separate plan.

**One-line bottom line:** the *safety architecture* (cardinal-sin guard, money hard-stop, read-back
proof, nav-wall, restart-safe loops) is real, layered, and verified; the *cold-surfacing plumbing*
is real; the **inference that recognizes a genuinely implied, socially-directed obligation** — the
product's whole reason to exist — is the one thing still mostly missing, and everything in Section 2.2
is the spec for building it.
