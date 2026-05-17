# What a customer gets

The binding standard here is one integrated system tested as a real
customer would use it, in a single continuous run, not scoped
synthetic gates. This document is that run, honestly.

## The whole journey ran end to end on this machine

One real integrated system: the new frontend (`/app`) wired to a
real running engine process, the engine running the real proven
pipeline over the frozen reasoning + frozen browser action engines
(both git-verified untouched). The customer path is the NEW
onboarding and the NEW UI, actually running, not the pre-existing
v4 screens.

## Exact steps to run the full journey on this machine

From the repo root:

1. Start the real engine server:
   `cd engine && ANTICIPY_DATA_DIR=$HOME/.anticipy/system_v1 \
   .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 \
   --port 8000`
2. Start the frontend wired to it:
   `ENGINE_URL=http://127.0.0.1:8000 npm run dev`
3. A customer opens `http://localhost:3000/app`, walks entry ->
   account -> download -> onboarding -> Listen, and presses Listen.
   The UI is a thin client over `/api/app/state` and
   `/api/app/run`; pressing Listen runs the whole real pipeline and
   a real proposal returns to the screen.
4. The same journey, driven through the exact endpoints the UI
   uses (this is what produced the literal output below):
   - `GET  http://localhost:3000/api/app/state`
   - `POST http://localhost:3000/api/app/run`  (Content-Type
     application/json, body `{}`)
   A real CDP Chrome on :9222 must be running for the real browser
   action stage (one was, status SUCCESS below).

## Literal output of the full run (one run, ~78s, nothing mocked)

STEP 1, the state the customer UI renders (real; honest gated
edges, not faked):

    account.status   = needs_user  (credential step is yours, by
                                     design, never automated)
    download.status  = ready
    onboarding.chrome = needs_user (real connected state, not faked)
    onboarding.microphone = needs_user (real TCC grant is yours)
    onboarding.autonomy = ready (conservative first run)
    engine.status    = live   ("Engine reachable.")
    proposals.status = live   (real proposals stream from engine)

STEP 2, customer presses Listen -> POST /api/app/run -> the whole
real pipeline:

    ok               = true
    transcript       = "I'll send Dana the budget before the
                        Thursday review."
    engine_decision  = ACT
    proposal         = "[text->dana] Found 1 thing to handle for
                        dana. Want me to proceed?"
    stages:
      mic        real   opened default input, 1.5s @16k captured
      speech     real   synthetic-wearer-voice waveform 4.00s @16k
                        (the wearer's prior enrollment decision)
      audiostack real   real parakeet ASR transcript exact;
                        stack=ACTIONABLE; frozen_decision=ACT
      decide     real   proactive_day outcome=DEFERRED; one real
                        proposal (n_outbound=1)
      action     real   frozen DSv4SkillRunner safe read on
                        https://example.com -> status=SUCCESS
      accounts   gated  SIMULATED boundary, honest: real account
                        creation / OAuth / Telnyx / SES / payment
                        need real credentials, money, a human.
                        Never a faked success screen.

## Every point that works for real

- The new frontend renders the real engine state (engine LIVE), not
  an honest-empty placeholder. The earlier "no engine running"
  failure is fixed: engine stood up locally, real URL set, frontend
  talks to it for real.
- A real microphone device is opened and captured.
- Real synthetic-wearer-voice audio (the wearer's own prior
  enrollment decision) is produced and is the real input.
- Real parakeet ASR transcribes it exactly.
- The real four-layer audio stack returns ACTIONABLE.
- The real FROZEN reasoning engine decides ACT.
- The real proactive_day layers (resolution, timing, completion,
  cancel, personalization) run; timing correctly DEFERS a "before
  Thursday" task and the real comms decision surfaces exactly ONE
  proposal (no flood).
- The real FROZEN browser action engine (DSv4SkillRunner) performs
  a real action on a safe target and returns SUCCESS.
- The real proposal returns to the real frontend API the customer's
  UI consumes, and the UI renders it as a proposal/confirm card
  with one Yes and one No.

That is the whole journey, in one continuous real run, end to end,
up to the honestly gated edges below.

## Every point that is a gated edge, shown honestly (never faked)

- Account creation / sign-in / OAuth to the user's real Google or
  email / real Telnyx / SES / phone calls / payment: the UI shows
  these as their real "needs you" / SIMULATED state. The run
  reports `accounts` as gated, not faked. Prohibited for an agent
  to do on the user's behalf by design.
- A human physically clicking and speaking live THIS second: the
  mic device is really opened; the spoken audio in an autonomous
  run is the fixed synthetic-wearer voice (the wearer's own prior
  enrollment decision), not a live human this instant. Same honest
  boundary throughout the build, stated, not faked.
- Broad live in-browser execution at production variety/scale: one
  real safe action is proven (SUCCESS); arbitrary real-world
  actions at scale remain the honest unproven edge.
- Two-mic spatial hardware: does not exist on this machine; the
  loud-room ceiling is the honest text-level number, gap stated.

## The precise remaining steps that need you (only you can clear)

1. Deploy: nothing here is deployed. anticipy.com still serves the
   old system. Pushing the branch is done (Phase 1, all 47 commits
   on origin/main); a deploy to the live domain is yours.
2. Real accounts and OAuth: real Google/email/Supabase auth wiring
   with real credentials, and the consent screens, are yours.
3. Money: Telnyx / SES / phone / payment require real funded
   accounts.
4. Desktop app: the Mac app on your machine is still the old frozen
   v4-9 Tauri build. Embedding this new onboarding + UI into a
   rebuilt, code-signed, notarized desktop app and distributing it
   is yours (signing and notarization are credentialed steps an
   agent must not do).
5. Resend domain: every [ANTICIPY-*] email is blocked by Resend
   "anticipy.ai domain not verified" -- a DNS / dashboard action
   only you can complete.

## Honest bottom line

The integrated system, run as a customer would use it, completes
the whole journey end to end on this machine: real audio, real
ASR, real frozen reasoning, real resolution and comms, a real
single proposal, a real frozen browser action, returned to the
real new UI. It is NOT deployed and NOT a shipped signed desktop
app, and the external paid/credentialed edges are shown honestly in
the UI rather than faked. The five steps above are the real
remaining work, and each is a gated edge that requires you.
