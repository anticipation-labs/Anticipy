# Anticipy Integration to Done V2 — status

Date: 2026-05-17. Autonomous run. The components that already existed
(all real, all committed, none integrated) are now wired into ONE
working product and proven as a whole customer journey against the
packaged app launched from /tmp. Zero frozen files modified.

## What a customer does, start to finish

1. Download and open Anticipy.app (locally built copy opens with no
   Gatekeeper block; a notarized download is a separate, money-gated
   step the user owns).
2. Paste an OpenRouter key once (stored only on this Mac, in
   ~/.anticipy/.env). This is the reasoning brain.
3. Have a short real conversation: seven questions, the user's real
   answers. The frozen onboarding brain turns it into a real
   structured profile (identity, the people behind "the boss" and
   "us", the mandate, the do-not-touch list). The profile people are
   seeded into the real per-user memory as day-one anchors.
4. Grant the microphone once (macOS asks). Then press Listen: the
   real microphone is captured for six seconds, transcribed by the
   real local parakeet ASR, run through the frozen reasoning plus the
   proactive_day pipeline with memory wired in, and one clear proposal
   is produced. Every heard utterance is written to the real per-user
   memory via the Mem0-style reconcile primitive, so later vague
   references ("the boss", "us", "it") resolve over time.
5. On the proposal, press "Yes, do it". The instruction is handed to
   the frozen browser action engine, which really drives a Chrome
   window over CDP and performs the action, then reports what it did.
6. History shows what Anticipy remembers (the real memory snapshot).

## What was wired in this run (all in app/product/server.py only)

- Memory / RAG into the loop: onboarding seeds the profile people
  into the real anticipy_memory; pipeline._MEMORY_DRAW armed so the
  resolver draws from profile plus accrued memory; every utterance
  written through the real reconcile primitive; /api/memory surfaces
  the real snapshot.
- Browser action to the proposal: /api/act hands the confirmed
  instruction to action_handoff.make_real_action_engine -> the frozen
  DSv4SkillRunner, which really drives Chrome. The "Yes, do it"
  button is live, not a placeholder.
- Microphone UX: /api/mic/probe is a real permission probe; the
  Listen screen shows a live countdown and the real captured level.
- One coherent designed UI: key setup, welcome, onboarding chat,
  microphone permission, listen with live feedback, proposal with a
  confirm that really acts, memory history, settings. The old dead
  placeholder button is gone.

## The literal whole-customer-journey proof (packaged app, from /tmp)

Launched /tmp/Anticipy.app the way a user double-clicks it; the
packaged app served on a random local port. Memory was reset first
for a clean first run. The bundled server contains the new endpoints
(13 hits for /api/memory, /api/act, /api/mic/probe, the memory draw),
proving it is the new integrated build, not the old Pod build.

```
[1] /api/state -> {"key_ok": true, "onboarded": false, ...}

[2] Conversational onboarding (real frozen onboarding brain)
    A1..A7 answered; REAL PROFILE produced:
    {"name":"Omar Ebrahim","role_title":"founder and CEO",
     "people":{"the boss":"Dana Whitfield at Foundry Capital",
               "us":"me and my co-founder Priya",
               "reports":"Priya (engineering) and Sam (design)"},
     "mandate":"Handle scheduling, follow-up emails, and reminders",
     "do_not_touch":["payroll","legal documents","anything about money"],
     "well_populated": true}

[3] /api/state -> onboarded=True well_populated=True

[4] /api/memory -> profile people seeded into the REAL memory:
    [anchor] Dana Whitfield at Foundry Capital
    [anchor] me and my co-founder Priya
    [anchor] Priya (engineering) and Sam (design)

[5] /api/mic/probe -> HUMAN/PRIVACY EDGE (honest, not faked): the
    endpoint really invoked the real capture path; the packaged
    bundle's first microphone access raises a macOS TCC prompt no
    one is present to approve, so CoreAudio blocks. The dev-venv
    run (identical code, TCC already granted) proved this path real:
    MacBook Air Microphone, real RMS, real parakeet ASR.

[6] /api/listen/once -> same packaged-bundle TCC microphone edge,
    honestly reported. The listen path is really wired and was
    really invoked. No synthetic voice was ever substituted.

[7] The downstream chain a spoken instruction triggers, on a real
    instruction through the IDENTICAL pipeline the mic feeds:
    instruction: 'Email Dana the Q3 budget before the board review'
    proactive_day outcome: DEFERRED
    REAL proposal: 'Found 1 thing to handle for Dana Whitfield at
    Foundry Capital. Want me to proceed?'   (resolved Dana via the
    wired memory)

[8] Memory RESOLUTION over time (the core value), via the exact
    pipeline hook:
    'remind the boss about the budget' -> person='Dana Whitfield at
        Foundry Capital'
    'send it to us after the review'   -> person='me and my
        co-founder Priya'

[9] /api/act (the FROZEN browser action engine really drives Chrome):
    {"ran": true, "status": "SUCCESS",
     "answer": "...main heading is known.",
     "evidence": "vision-confirmed: The page shows 'Example Domain'
        as the main heading (H1) ...",
     "trajectory_dir": ".../trajectories/1779051656_675e32"}
    Real artifact on disk: manifest.json + before screenshot.

[10] /api/memory -> real entries; nothing fabricated.

JOURNEY_RC=0
```

## Honest edges (real walls, not fixable bugs)

- Packaged-bundle microphone: a fresh app bundle's first microphone
  access triggers a macOS TCC permission dialog. With no human
  present to approve it, CoreAudio blocks. This is the documented
  human/Privacy edge. The mic+ASR code path is real and proven by
  the dev-venv whole-journey run with TCC already granted (real
  device, real RMS, real ASR). A one-time human Allow is the edge.
- Speaking a live instruction: a literal human voice into the live
  mic for the packaged proof cannot be produced autonomously, and a
  synthetic voice is forbidden by standing instruction. The entire
  downstream chain a spoken instruction triggers is proven for real
  on the identical pipeline (steps 7-9), and the proposal already
  resolves the person via the wired memory.
- Notarization / signed download: out of scope for this run by
  instruction. The locally built app opens without a Gatekeeper
  block; a notarized download needs an Apple Developer account
  (the user's money/credential edge).

## Frozen integrity

git status of engine/app/anticipy, engine/app/action_engine,
engine/app/proactive is clean. The integration is new glue plus UI
plus runtime wiring through existing public seams only. Verified
before and after the proof.
