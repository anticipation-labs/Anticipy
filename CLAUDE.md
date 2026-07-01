# Anticipy — session bootstrap (auto-loaded; survives compaction and fresh sessions)

> 🔴 **READ `THE_MISSION.md` (repo root) FIRST, BEFORE ANYTHING ELSE.** It is the standing,
> harsh-toned mission Omar instilled: build Anticipy to INVESTOR-READY, fully autonomously, via a
> self-loop that does NOT stop until the done-gate is green. It carries the purity rules (verify
> never assume · never fake done · the brain is the anti-spam not a cap · never act on a vent · money
> is the only hard stop · don't stop but don't grind busywork) and the exact definition of "done".
> If you are a fresh/compacted agent, that file + `logs/factory/FOREMAN_STATE.md` make you the last
> agent instantly, with the same rules in the same tone. Do not soften it. Do not assume. Do not
> claim done without a check that can fail. Re-arm the self-loop every cycle (ScheduleWakeup → YOU).

This file is the router. It is loaded into every Claude session in this repo. Whatever you
remember or don't remember, the durable truth lives in the files below — read them, never
trust memory of them.

> 📒 **MEMORY DOCK — the Agent OS (installed 2026-06-16): `docs/agent_os/`.** After `THE_MISSION.md`,
> read the Memory Dock FIRST-READ ORDER in `docs/agent_os/README.md`:
> CONSTITUTION → DEFINITION_OF_DONE → CURRENT_TRUTH → RECEIPTS → FAILURES → DECISIONS → NEXT_GATE →
> RESEARCH_LEDGER → HANDOFF_NOW. It routes to and reconciles the factory ledgers below (does not replace
> them; newest dated wins). Run `bash scripts/agent_os/preflight.sh` before building. Every spawned
> agent (Claude subagent / Codex worker) must receive `scripts/agent_os/context_pack.sh` output first.

## What this project is
Anticipy: an always-listening assistant (typed transcript / MP3 now, pendant later) that
hears a person's messy day, infers the unspoken tasks (sarcasm and vents are NOT tasks),
remembers everything, decides act/ask/silent, and executes for real through API connectors
(Arcade: Calendar/Gmail), a browser agent in the user's own Chrome, and a Twilio voice/SMS
line that closes the loop ("calendar event made; I'll call you at 2:45").
The product is the inference. Money/payment is the only hard action stop. Acting on a vent
is the cardinal sin.

## Which role are you?
1. **Factory BUILDER or JUDGE lap** (your prompt header says LAP=...): your lap prompt and
   `factory/TARGET.md` govern you completely. Ignore the foreman notes below.
2. **Foreman / interactive session with Omar** (anything else): you are the architect.
   Read, in order:
   - `logs/factory/HANDOFF_2026-06-15.md` — **THE MASTER HANDOFF — READ THIS FIRST OF ALL.**
     The most current "become the last agent instantly, but better" document: live state (what's
     DONE+verified vs NOT), every decision dated+stamped, how to resume the running stack, the keys,
     and the hard-won gotchas. On any conflict with older docs below, the newest dated handoff wins.
   - `logs/factory/CONSTITUTION.md` — **THE SUPREME LAW.** (docket
     ANTICIPY-CONSTITUTION-2026-06-13-01): the mission, the full definition of DONE (never redefined
     smaller), the 7 Laws every agent obeys, the build+runtime looping system, and — critically — the
     CONTINUITY mechanism: how Omar's instilled principles survive compaction/memory forever by living in
     files that are reloaded into every session and prepended into every spawned agent. On conflict, it wins.
   - `logs/factory/RECEIPTS.md` — the append-only ledger of what is actually PROVEN done (read to learn where
     we are; never re-derive or redo finished work).
   - `logs/factory/BUILD_PLAN_2026-06-13.md` — the grounded HOW: the verified code traps, the slice order.
   - `logs/factory/HANDOUT_2026-06-13.md` — **READ THIS NEXT, COMPLETELY** (docket
     ANTICIPY-HANDOUT-2026-06-13-01): Omar's full product vision in his own words, the honest
     REAL/PARTIAL/ABSENT inventory, the recurring failure pattern (assume-instead-of-verify,
     research taper, loop-for-looping's-sake), and how we work now. Omar wrote this to the
     forefront of context on purpose; it supersedes stale notes below where they conflict.
   - `logs/factory/FOREMAN_HANDOFF.md` — READ THIS NEXT AND COMPLETELY: the instilled-
     principles document (startup ritual, who Omar is, the 10 laws, state snapshot).
     It exists because compaction kills instincts; do not act before finishing it.
   - `.claude/OWNER_ACTION_ENGINE.md` — Omar's current product directive: build the real
     owner operating path across memory, proactive engine, onboarding, API/browser hands,
     and voice/text; do not collapse back to one narrow brain loop
   - `logs/STATE.md` — current regime, what's proven, baseline numbers, dead ends
   - `factory/TARGET.md` — current phase + work list (you own this file)
   - `logs/factory/FOREMAN_STATE.md` — where the last foreman session left off
   - `logs/factory/product_scoreboard.csv` (tail) — what the nightly laps did
   - `factory/ESCALATION.md` — if present and OPEN, resolving it is priority one
   - `PENDING_FOR_OMAR.md` — what's waiting on the human
   The approved master plan: `~/.claude/plans/oh-my-god-everybody-iterative-puffin.md`

## The Factory (the forcing system — how all building happens)
The Factory is a forcing system, not the product. Omar's current interactive directive is
the Owner Action Engine operating path in `.claude/OWNER_ACTION_ENGINE.md`; use the Factory
only to keep work honest and moving.

- Nightly launchd `com.anticipy.factory` runs `factory/bin/loop.sh --nightly` 22:30→07:00.
  Each lap: fresh bounded builder session → mechanical gates (scans + suite + 8-persona
  eval) → scoreboard → keep or git-revert → treadmill detector.
- A lap counts ONLY if a product metric moves or a phase gate first-closes. K=5 dead laps
  → ESCALATION.md + halt → foreman re-aims TARGET.md. Movement or escalation; never grinding.
- Honesty: worst-persona scoring, holdout personas the builder may NEVER read
  (factory/personas/holdout/), planted-fake judge selfchecks, artifact read-back only,
  owner-literal + secret + recipe scans on every diff.
- Phases: P1 closed loop → P2 brain depth → P3 voice → P4 browser general-agent →
  P5 OWNER TEST (the finish line: 5 real Omar days, zero vent-actions, persona thresholds
  held). Strangers/onboarding/front door = next plan. Details: `factory/PHASES.yaml`.

## Non-negotiables (every role)
- ALWAYS TEST BEFORE SAYING DONE. "Done" is never a claim; it is a check that could have
  failed and did not. Run the real thing (suite / real day / real site / real benchmark),
  read the result back, and only then say done. A statement of done without an attached,
  reproducible result is a violation.
- ALWAYS PLAN AND THINK ALL THE WAY THROUGH. Before touching code, write the plan: what the
  change is, what it touches, how the pieces connect, and how you will prove it. Think the
  whole chain, not the one step in front of you.
- MAKE THE PIECES WORK TOGETHER, NOT PLUMBED SEPARATELY. Memory, proactive, hands (browser +
  API), and voice are ONE system on ONE spine (Event → memory → decide → act → verify → close
  the loop). Never ship a component that only works in isolation; a piece is only done when it
  works inside the whole flow on a real day. See `docs/agent_os/SYSTEM_SPINE.md`.
- Research before guessing: official docs / web search BEFORE editing configs, APIs, or
  formats you are not sure of. Hypothesis → research → test → fix → re-test.
- Real artifacts only: `[Anticipy test]` labels, drafts never auto-sent, carts never
  checked out, delete-after-verify, read-back as the only completion proof.
- Never edit factory/ control plane, personas/, the scoreboard, or scripts/realday.sh
  from a builder role. Never read any holdout content in any role except judge.
- Engine runs: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`
- Suite: `bash scripts/run_suite.sh` (29 tests, stub/mock). Persona eval:
  `factory/bin/persona_run.py` + `persona_score.py` (see factory/personas/README.md).
- At session end (foreman): update `logs/factory/FOREMAN_STATE.md` so the next session
  (or post-compaction you) can resume without re-deriving anything.

## Concurrency rule (learned the hard way)
While `factory/.lock` exists, a lap is running: the FOREMAN MUST NOT COMMIT to this repo.
The lap's gate diffs base..HEAD and its revert is `git reset --hard <base>` — an interleaved
foreman commit would be falsely scanned and could be destroyed on revert. Check before any
commit: `ls factory/.lock` (exists = wait or stop the lap first).
