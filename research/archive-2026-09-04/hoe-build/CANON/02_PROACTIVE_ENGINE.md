<!-- CANON v1 · written 2026-07-02 by the HoE agent (post-Devin) · NEW documentation, not Devin's.
     On conflict with any doc outside CANON/ (except MISSION_LOCK.md for live mission status), THIS file wins. Fix errors HERE — never fork. -->

# 02 — THE PROACTIVE ENGINE (how "it acts on its own" actually works)

This is the brain's decision layer: the code that hears a line of your day and chooses
**act silently / ask you first / stay silent**. Read `CANON/01_WHAT_ANTICIPY_IS.md` for what
the product is; this file is how the deciding works, what it must FEEL like, and which of the
eleven historical decision-engines is the real one.

---

## 1. WHAT PROACTIVE MEANS HERE

Three behaviors, in priority order:

1. **Act-first on anything safe and reversible.** A reminder, a calendar hold, a draft
   (never a send), research, an un-purchased cart — it just DOES these. No permission-seeking.
2. **Ask-only-before-harm.** Anything detrimental — money, deleting, posting publicly, a
   binding send to a real human — is PAUSED and you get one question. It is never executed
   silently. Money is blocked outright until you confirm.
3. **Silent on non-tasks.** Vents ("I should just quit"), sarcasm, musing — nothing happens.
   Acting on a vent is the cardinal sin. The silence is engineered, not an accident.

This boundary is **"a scored gate, not a vibe"** (`ANTICIPY_DONE_VISION_2026-06-15.md` Part 2):
every candidate is routed by inspectable rules — reversible + no other person + no money =
silent-act; touches a human or hard-to-reverse = ask; money/login-wall = hard stop; vent = nothing.

**The marquee bar (Omar, 2026-07-02) — what "truly proactive" must feel like.** Reacting to a
typed command is table stakes. TRUE proactivity **derives the unspoken need**: it hears the
morning noise, realizes on its own that *the kids need pickup at 3*, then **researches the real
world through the browser** — where is the school, where will you be at 2:30, what's the drive
time — by actually browsing (no maps API, no hardcoded answer). Then it **acts** (a calendar
hold) and **texts you**: *"It's on your calendar — I've got it, or you this time?"* Derive →
research via the browser → act → one human text. That chain is the product. (Honest status:
not there yet — see §6.)

---

## 2. THE ONE PIPELINE (the consolidation target — this is law)

There is exactly ONE path from "a line of your day" to "a decision". All input types funnel
into it; nothing decides outside it.

```
input (typed / MP3 / listen-stream / extension)
  → ONE front door:  POST /owner/ingest        (main.py → control_core.owner_ingest)
  → ONE extractor:   proactive/decision_pipeline.py  (the M1-proven wearer-aware pass)
  → ONE gate:        proactive/harm.py               (detrimental→ask, money→block, safe→act)
  → ONE spine:       core/proactive.py ProactiveEngine (triage→context→harm→act/ask;
                                                        durable pending; fire-once trigger_tick;
                                                        annoyance budget)
  → channels + surfaces (channels/*, GET /owner/cards, GET /pending, POST /resolve)
```

In words: every input becomes the same stream at the front door (`/owner/ingest`,
`engine/anticipy_engine/main.py:877` as of 2026-07-02). The **extractor**
(`proactive/decision_pipeline.py`) makes one wearer-aware judgment — whose task is this, is it
real or a vent, what should happen — the pass the M1 battery proved 6/6. The **gate**
(`proactive/harm.py`) is the deterministic harm-line: detrimental → ask, money → block,
safe → act. The **spine** (`core/proactive.py::ProactiveEngine`) runs the loop: triage the
noise out, read memory context, apply the gate, then act or park a durable pending ask;
`trigger_tick` fires due/stale open loops exactly once; the annoyance budget caps how often
you're interrupted. Results surface as cards (`GET /owner/cards`), the needs-you list
(`GET /pending`), and your yes/no (`POST /resolve` — which RESUMES the exact paused action).

> **THE LAW: "No new decision code outside this pipeline. Any change to act/ask/silent
> behavior lands in one of these five files, or it is a fork."**
> The five: `main.py` (front door) · `core/control_core.py` (owner_ingest) ·
> `proactive/decision_pipeline.py` · `proactive/harm.py` · `core/proactive.py`.

---

## 3. THE GRAVEYARD TABLE — all 11 decision engines ever built, and the verdict on each

Over months, ELEVEN modules were built that decide (or look like they decide). This table is
the 2026-07-02 consolidation ruling on every one. If you find decision logic not listed here,
it is a fork — kill it or fold it in.

| # | Module | Verdict (2026-07-02 ruling) |
|---|--------|------------------------------|
| 1 | `core/proactive.py` (ProactiveEngine) | **LIVE — the spine.** The loop everything runs through. |
| 2 | `owner_mode.py` + `control_core.owner_ingest` | **LIVE — the shaper** (turns decisions into task cards). Being thinned; shaping only, never deciding. |
| 3 | `proactive/decision_pipeline.py` | **LIVE — the extractor.** The M1-proven wearer-aware pass. |
| 4 | `proactive/extract.py` ("the MOAT") | **LEGACY-FOLD** — its multi-task + vent judgment is being retired into #3. |
| 5 | `proactive/decider.py` (Room 1.5) | **LEGACY-FOLD** — the commitment second-opinion becomes an adapter onto #3. |
| 6 | `proactive/harm.py` (HarmLine) | **LIVE — the gate.** The one deterministic detrimental/money/safe policy. |
| 7 | `proactive/anticipate.py` | **BEING-WIRED** — real person-research ("who is Nicki?") exists but has no live caller yet; gets one in world_research. |
| 8 | `live_memory/` capture / duetime / press_go | **KEEP-SUBORDINATE** — produces open loops for the spine's trigger_tick; never decides. |
| 9 | `proactive/gateway.py` (ledger) | **KEEP — telemetry only.** The name is a trap: its own docstring says "it does not decide what the assistant should do". It decides NOTHING. |
| 10 | `proactive/engine.py` stub + its `brain.py` scaffold | **DELETE PENDING (FIX-01 / Phase 1; files still present 2026-07-02)** — dead scaffold ("proposals are always empty"), name-collides with the real spine. |
| 11 | `overnight/track_b/decider.py` | **DELETE PENDING (FIX-01 / Phase 1; file still present 2026-07-02)** — archival ancestor; its prompt already grew into #5. |

Plain-English takeaway for Omar: the real system is **#1 + #2 + #3 + #6** with #7 joining.
Everything else either feeds it (#8), watches it (#9), or is history (#4, #5, #10, #11).

---

## 4. THE MEASURED RECORD (dated — never trust an undated score)

**The Room 1–7 scorecard** (`notes/proactive_log.md`, Room 7 eval,
`engine/scripts/proactive_eval.py` on a labeled day of 14 act / 14 ask / 10 ignore — as of
that log's date, branch `proactive/real`):

| Metric | Score | Meaning |
|---|---|---|
| act-precision | **1.000** | everything it acted on was safe to act on |
| act-recall | **1.000** | it acted on every safe task (no permission-begging) |
| over-ask | **0.000** | zero unnecessary interruptions on the labeled day |
| harm-catch recall | **1.000** | every detrimental action was caught and asked |
| **SILENT-HARM** | **0** | the HARD gate: nothing harmful ever executed silently |

The eval self-proves first (a PLANTED silent-harm must be caught before any score is trusted),
and it earned its keep: the first run exposed a real triage gap (act-recall 0.571), which was
fixed generally and re-measured to the numbers above.

**The M1 battery — 6/6 PASS, 2026-07-02** (fresh-engine protocol; proof pasted in
`MISSION_LOCK.md`): mom/plant→ask · Sarah/deck→ask · judgment→ask · the compound traffic line
splits correctly (kids-pickup→do and NOT money-flagged; the $4,200 invoice→blocked, never
dropped) · dinner-with-no-restaurant→ask-for-slot · sarcasm→ignored and logged.
Replay: `ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 python3 overnight/m1_battery.py`
(fresh engine + fresh `ANTICIPY_DATA_DIR` — the batteries are state-sensitive).

---

## 5. CADENCE + TRUST (how it earns the right to interrupt, and to act)

- **The annoyance budget** (`proactive/budget.py::AnnoyanceBudget`): engine-initiated ASKS are
  capped per rolling day — default **5/day** (verified in source 2026-07-02; the number is
  configurable and explicitly Omar's taste call). Silent safe acts cost nothing; only
  interruptions spend budget. You asking is never suppressed. A declined ask teaches it: that
  action-type is suppressed next time (and a suppressed detrimental is neither executed nor
  asked — no silent harm, no annoyance).
- **The trust ladder** (M3, PASSED 2026-07-01): per-task-type trust — **promote after 5 clean
  reps** (an ask-type it has done cleanly 5 times stops asking), **demote on rejection**, and
  **irreversibles cap at CONFIRM** forever (no amount of trust unlocks them). Proof:
  `overnight/m3_integration_test.py` — ALL PASS 9/9, including trust promoting a web ask→do
  after 5 clean reps and the $4,200 spend staying CONFIRM even in Full-Send mode.
- **The two invariants** that override every autonomy mode: **money always confirms** and
  **irreversible always confirms.**
- **Deferral note (per MISSION_LOCK, 2026-07-02):** the deeper safety/money-gating PASS is
  deliberately deferred — Omar + Devin do that pass manually, LAST. Do not build new gates now;
  the operational floor still holds (no irreversible real-account or money action while Omar
  is unattended — prepare-and-park instead).

---

## 6. THE HONEST WOUNDS (2026-07-02 — what is NOT true yet)

1. **Reactive-in-origin.** Today every decision starts from an ingested line. It derives
   NOTHING unspoken yet — the §1 marquee (kids-need-pickup inferred, not stated) does not
   happen. FIX in flight.
2. **Zero real-world research code.** No module browses to answer "where's the school /
   what's the drive time". `anticipate.py` researches PEOPLE (memory + email) and even that
   has no live caller yet (§3 #7). The browser-research leg of the marquee chain is unbuilt.
3. **Twilio never fired live.** Every channel proof is mock. One real SMS/call to Omar's
   phone (needs his creds + a number) remains the one-time human unblock — queued in
   MISSION_LOCK's NEEDS-OMAR list.
4. **13 unwired seams** — modules that exist but nothing calls. Full list: `CANON/03` §5.
5. **Decline-memory is RAM-only.** The learned "he said no to this type" set and the trigger
   fire-once set live in process memory (verified in `budget.py` 2026-07-02 — zero
   persistence calls). Restart the engine and it forgets your declines.
6. **No style learning.** It doesn't yet learn HOW you like things (tone, timing, which
   recipients are casual) from your approve/decline history — the harm-line is a fixed policy
   (the Deferred-1 learning loop from `notes/proactive_log.md`, still unbuilt).

When any of these changes, fix THIS file (dated) — never fork a new doc.
