# Owner Action Engine Directive

Last updated: 2026-06-12.

This file is the current owner-facing product directive. Read it before `factory/TARGET.md`
in any interactive/foreman/product session.

## What Omar Changed

Omar does not want another narrow loop that optimizes one little brain test and leaves the
real product for later. The current goal is the working Action Engine:

- memory works
- proactive engine works
- onboarding works
- API hand works
- browser hand works
- voice/text loop works
- every input door feeds the same engine

Do not rename this into a vague "prototype" or "spine." The work is the Owner Action
Engine operating path.

## Human Product Target

Say the target this way, especially in watch/check-in sessions:

Omar opens the app, presses Go, types a messy note, or uploads a transcript/audio file.
The same proactive engine reads it like a competent human helper: it ignores vents and
jokes, catches real obligations, remembers useful facts, and turns the right lines into
clear task cards. The app shows what it understood, what it is going to do, what needs
Omar's yes, and what is blocked.

Then the system actually does the work it safely can do: calendar/reminder actions,
memory updates, drafts, browser research/cart preparation, and voice/text follow-up. Every
completed action writes a receipt with proof. Anything that touches another person asks
first. Anything involving payment, captcha, 2FA, or a real-world wall stops and hands Omar
the smallest possible next step. Money never executes automatically.

Done is not a hidden score. Done feels like Omar can dump a messy day into one app and see
the right things handled across UI, memory, proactive reasoning, API/browser hands, and
voice/text without babysitting a science project.

## Input Contract

These doors must all do the same thing:

- pay-to-try
- Start Listening
- MP3 drop/transcription
- pasted transcript/test transcript
- later: pendant/iPhone audio

All of them become observed transcript lines, then run through the same owner ingest path.
The first shared endpoint is:

```text
POST /owner/ingest
```

The first-run memory mesh endpoint is:

```text
POST /owner/onboard
```

Implemented files:

- `app/page.js`
- `app/api/owner/ingest/route.js`
- `app/api/owner/upload/route.js`
- `engine/anticipy_engine/owner_mode.py`
- `engine/anticipy_engine/owner_onboarding.py`
- `engine/anticipy_engine/core/control_core.py`
- `engine/anticipy_engine/main.py`
- `engine/scripts/test_owner_mode.py`
- `engine/scripts/test_owner_onboarding.py`
- `engine/scripts/test_owner_ingest_event.py`
- `engine/scripts/test_owner_upload_ingest.py`
- `engine/scripts/test_public_backend_path.py`

The contract is: ugly daily speech in, observed lines plus durable task cards out. Cards
are written into the real memory drawers, especially `open_loops`, with route,
disposition, action, source text, and proof.

## Transcript Standard

Do not test on clean commands like:

```text
Remind me to pick up the kids at 3.
```

That is not the product. The product is:

```text
yeah okay the coffee machine is being weird again...
school moved pickup to 3 today, please remind me before I forget
oh sure I'll just clone myself, that'll fix the schedule
Sam needs the revised decking before Friday; I told him I'd send it
that water-table thing for the birthday, put it in the cart if you find it, don't buy it
```

Most lines are noise. Some lines are vents or jokes. A tiny fraction become action cards.
Acting on a vent is still a product failure. Missing a real weak-signal task is still a
product failure.

## Routes And Cards

Every useful line becomes one of these card shapes:

- `do`: safe enough to run or queue, such as reminders, calendar protection, research,
  cart-only preparation, or open-loop capture.
- `ask`: a real task that touches another human or needs confirmation, such as drafting
  a message to Sam.
- `blocked`: a task that reaches payment, captcha, login, missing OAuth, or another hard
  wall. It can be prepared up to the wall, but not faked.
- `remember`: a profile/preference/relationship fact for memory.

Routes:

- `memory`
- `api`
- `browser`
- `voice_text`

Do not build a special handoff mode. Use explicit `ask` or `blocked` cards and keep them
durable in memory.

## What Exists Now

Existing real pieces:

- Memory drawers: `engine/anticipy_engine/memory/store.py`
- Live memory capture/inject: `engine/anticipy_engine/live_memory/`
- Proactive act/ask/silent engine: `engine/anticipy_engine/core/proactive.py`
- API hand: `engine/anticipy_engine/hands/api_hand.py`
- Browser hand: `engine/anticipy_engine/hands/browser_hand.py`
- Engine surface: `engine/anticipy_engine/main.py`

New owner path:

- `OwnerMode.ingest(...)` parses noisy transcript into task cards.
- `ControlCore.owner_ingest(...)` captures every observed line, writes every task card
  to memory/open loops with proof, and with `execute_actions=true` runs cards through
  the same proactive act/ask/silent engine used by `/event`.
- `POST /owner/ingest` exposes this path.
- `POST /owner/ingest-file` reads uploaded text or transcribed audio and feeds the same
  owner path.
- The local Owner Mode UI posts typed text and uploads through the frontend API proxies.
- `test_owner_mode.py` pins that pay-to-try, Start Listening, MP3, and transcript sources
  produce the same cards from the same ugly transcript.
- `test_owner_ingest_event.py` pins execution policy: safe API cards run through the
  existing proactive engine, ask cards become real pending approvals, browser cards need
  memory-resolved site/item proof, and checkout/payment cards stay blocked.
- `test_public_backend_path.py` pins the product story in one HTTP pass: messy transcript
  -> memory handoff -> safe execution -> pending approval -> resolve -> durable receipts
  -> money wall.
- `OwnerOnboardingIn` + `POST /owner/onboard` write identity, people, preferences,
  app-connection state, common stores/accounts, and missing-connection open loops into
  the same memory drawers.
- `test_owner_onboarding.py` pins first-run setup as durable memory, not a detached form.

## What Still Needs Building

Next work should move across the whole operating path, not one isolated brain score:

1. Replace the narrow regex shaper with a cheap model or hybrid extractor, but keep the
   current card contract, safety gates, and product-path tests.
2. Add a real messy owner-day eval with hundreds/thousands of useless lines and a tiny
   answer key. Do not use clean command prompts as the main grade.
3. Wire the onboarding UI to `POST /owner/onboard`, then connect live authorization checks
   to the stored connection records.
4. Expand live proof for public actions: API read-back, browser read-back, and voice/text
   confirmation proof should all land on the same durable card/open-loop record.
5. Run the guarded live voice/text confirmation path only with owner phone confirmation;
   credentials may exist, but live calls/SMS are still an explicit human-gated operation.
6. Harden real browser execution against hostile sites: signed-in session availability,
   captcha/2FA handoff, no-purchase wall, and honest one-tap handoff when automation
   cannot finish.
7. Production work: data retention/deletion, auth, packaging/deployment, observability,
   and recovery from interrupted local app/browser sessions.

## Verification

Run:

```bash
bash scripts/run_suite.sh
```

Focused owner test:

```bash
PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_owner_mode.py
PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_public_backend_path.py
```

Do not claim the public product is done from this alone. This proves the shared owner
intake, real memory handoff, proactive execution policy, pending approval, durable
receipts, upload path, and money wall are alive under deterministic mock/live-gated hands.

## Current Worktree Warning

This session also repaired Factory honesty accounting before the owner directive switch.
Dirty files from that repair may still be present:

- `factory/TARGET.md`
- `factory/bin/loop.sh`
- `factory/bin/scoreboard.py`
- `logs/factory/FAILURE_MODES.md`
- `logs/factory/RATCHET.json`
- `logs/factory/product_scoreboard.csv`

Do not revert them unless Omar explicitly asks.

## AMENDMENT 1 (foreman, 2026-06-10 20:30 PDT) — one machine, three actors, zero collisions

Ruling on this lane: ALIVE. It is the product surface the master plan called the Owner
Test, pulled forward — correct instinct, kept. These rules make it safe:

1. **Lock discipline is absolute for EVERY actor** (Factory laps, the 30-minute
   automation, interactive sessions): if `factory/.lock` exists, a lap is running —
   do NOT edit or commit ANY tracked file. Report status and stop. The lap's revert is
   `git reset --hard` and it will destroy interleaved work (ledger A1/C14, both observed
   live).
2. **Commit what you build, every session.** This lane's first pass left 16 files
   uncommitted, which would have made the 22:30 nightly refuse to start (dirty-tree
   guard). Build → suite green → commit, before the session ends.
3. **One honesty instrument, both lanes.** The "dirty transcript bank + answer key +
   brutal score" this directive asks for ALREADY EXISTS: factory/personas/ (8 dev + 4
   judge-only holdout messy days) + persona_score.py (self-proving, deterministic) +
   the adversarial judge. The owner ingest path gets scored by the SAME bank — next
   slice wires persona_run.py to drive /owner/ingest so owner cards are measured with
   worst-persona honesty, not vibes. No parallel scoreboard.
4. **Execution inherits the safety spine.** Cards with ask_required route through the
   engine's /pending + harm-line; money NEVER executes (hard stop); every executed card
   carries proof (artifact id + read-back) like every goal does today.
5. **The Factory stays the forcing system** for both lanes: laps, gates, judge, treadmill.
   factory/TARGET.md says what to build next; this file says what the product IS.
