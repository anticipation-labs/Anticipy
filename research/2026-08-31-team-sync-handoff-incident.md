# Team-sync handoff incident — 2026-08-31

## What the owner saw

After Anticipy heard a team-sync request, the iPhone showed a prepared card.
Tapping `Send it` changed nothing visible on the Mac, no SMS arrived, and the
job remained stuck. A separate transcript produced unrelated quantum research.

## Live production evidence

- At audit time, job `y6epuw0ekxoc6qe` was still `queued`, on
  `lane="research"`, approved, and had never been claimed (`attempts=0`).
- The worker repeatedly logged that its preflight handback PATCH was refused
  with HTTP 403.
- `research_lane.pb.js` refused the worker's `research -> browser` handback
  because the hook made every lane value immutable after minting.
- The paired browser agent is healthy on extension `0.11.1` and Chrome 151,
  but both its poll and the server correctly hide research-lane rows from it.
- The account has an email address and no phone number. The worker composed a
  notice, recorded the in-app fallback, and never attempted a Twilio send.
- The stored plan has no typed act declaration, no required facts, and no
  calendar facts. Its goal names only next Monday; no start time, end time, or
  attendee/invitation scope was retained.

## Root causes and repairs

1. **The research gate held but could not release.** Preserve global lane
   immutability. Permit one authenticated worker-only handback when the stored
   row is queued research work carrying `_research_gate.handback=true`, the
   request clears that marker, and the request changes only `lane` and
   `params`. Drive the actual hook for both the allowed transition and every
   nearby rejection.
2. **A draft looked approvable.** Keep real required facts on consequential
   plans. A draft card asks for details and routes the answer through the brain;
   it does not call the gesture-approval path. Only an `awaiting_approval` plan
   presents approval.
3. **The phone calendar hand had no live declaration path.** Ask a dedicated
   model question, with the complete heard line, task, and current local time,
   whether the exact effect is an owner-calendar write. Only an explicit typed
   calendar artifact selects the phone lane. Missing, malformed, false, or
   unavailable answers leave the existing browser lane unchanged.
4. **The phone calendar hand lacked executable artifacts.** A calendar plan
   carries resolved `calendar_title`, `calendar_start`, and `calendar_end`
   facts, or names those facts as required. It also carries a pre-minted event
   tag and an undo plan that addresses that exact tag. Later answers update the
   typed facts and their provenance-held values before approval.
5. **An STT/model invention became quiet work.** A configured strong model now
   re-judges every extracted goal, including the contradictory `ignore + goal`
   shape that creates quiet research. A strong `ignore + no goal` removes the
   invented work before any row is minted.
6. **The channel was hidden from the owner.** Onboarding and Profile state
   plainly that an account without a number receives in-app alerts only. A
   number enables texts as well; the app does not claim a text was sent when
   Twilio was never called.
7. **The approval wording described the wrong operation.** A completed held
   plan says `Approve`; a plan waiting on information says `Send answer`.

## Existing adjacent repairs that must be re-proved in this release

- Build 115 replaced repeat-forever SwiftUI transactions in `BreathingDot`
  and `WaveBars` with time-derived scale/opacity, fixing the one-dot/three-bar
  screen drift shown in `IMG_4340–42`.
- The YouTube route-change crash was traced to duplicate AVAudioEngine tap
  installation and repaired with coalesced fresh-engine rebuilds plus an
  Objective-C exception boundary.

## Release proof required

- Focused Python tests for preflight handback, calendar declaration, draft
  answer flow, and strong re-triage pass.
- The real PocketBase JS hook is executed for allowed and forbidden handbacks.
- iOS policy tests prove draft/approval copy and routing; simulator compilation
  proves the app paths build together.
- Full Python, extension, and iOS suites pass, then pass again after repair.
- Backend and worker deploy from the exact pushed commit; live health, worker
  logs, hook behavior, and browser heartbeat are checked after deployment.
- A new TestFlight build is uploaded from that commit and App Store Connect
  reports it valid before it is described as available.

## Containment before deployment

Before deploying the handback exception, job `y6epuw0ekxoc6qe` was re-read
from production and confirmed unchanged: queued research, canonical workflow
queued, approved, zero attempts, and the durable handback marker still set. It
was then transitioned through the canonical workflow to `cancelled` while it
was still invisible to the browser. The final live row is `cancelled`, retains
`lane="research"`, has zero attempts, and says to ask again with a start time
and duration. This prevents the repaired hook from releasing the old,
under-specified request into Chrome.
