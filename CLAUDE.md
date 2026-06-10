# Anticipy — session bootstrap (auto-loaded; survives compaction and fresh sessions)

This file is the router. It is loaded into every Claude session in this repo. Whatever you
remember or don't remember, the durable truth lives in the files below — read them, never
trust memory of them.

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
   - `logs/STATE.md` — current regime, what's proven, baseline numbers, dead ends
   - `factory/TARGET.md` — current phase + work list (you own this file)
   - `logs/factory/FOREMAN_STATE.md` — where the last foreman session left off
   - `logs/factory/product_scoreboard.csv` (tail) — what the nightly laps did
   - `factory/ESCALATION.md` — if present and OPEN, resolving it is priority one
   - `PENDING_FOR_OMAR.md` — what's waiting on the human
   The approved master plan: `~/.claude/plans/oh-my-god-everybody-iterative-puffin.md`

## The Factory (the forcing system — how all building happens)
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
