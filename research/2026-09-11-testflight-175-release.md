# Private TestFlight release candidate 175 — September 11, 2026

## Scope and current status

The owner explicitly requested a new private testing build now, with further
stress testing afterward. Existing private-pilot delivery is authorized. This
is not an App Store public submission or a claim of whole-product perfection.

Starting branch: `cloudflare-backend`; starting commit:
`c05d614a7597ee9b03aef3cf791bfb274e3d6751`, freshly matched to origin.
No changes to `main`, database migrations, API/brain redeployments, model calls,
real messages, microphone capture or connector account operations are included.
All unrelated local files and the scratch-only provenance experiment stay out.

The initial five-file candidate is frozen in
`work/ios-release-20260911.YWZXlO/candidate-175.patch`, SHA-256
`06030a66b84ff4ce96fdad4b5b6ce961021a6cb6c949bd586a996acdba8a59cf`.
It contains the pending-word cursor repair, regression/mutation checks, and the
coordinated 174-to-175 build-number bump. **That audio candidate is excluded
from the release.** The three experimental cursor files remain local, unchanged.

The selected release contains only the coordinated build-number change and
truthful documentation. Its iOS application source and tests are byte-identical
to the already-released build-174 source at `7968926e`. It uses the backend fixes
already deployed at `c05d614a`; rebuilding does not itself change the backend or
repair additional voice behavior. The user was informed of this distinction.

## Fresh pre-release evidence

- **Selected, nonexperimental release source:** repeated the entire 73-runner
  iOS logic gate in the clean detached worktree; actual exit **0** and final
  `iOS logic gate: all suites passed`. Log: `selected-source-logic.log`.
  Its metadata-only diff SHA-256 is
  `c2a276d0835ed15341877f0ec4d404eca013179b4b88d58e5ce8c1baac7f9896`.
  The root checkout's two selected metadata files match this diff exactly.
- Fresh public API health read: HTTP/body **200**, revision `c05d614a`, version
  `e0c3cdd5-621d-4f91-8d1a-4795ba1d30fe`, `cache-control: no-store`.
  This verifies release routing/health, not every model or connector operation.
- The following cursor results concern the **excluded experimental candidate**,
  not a newly included fix in build 175:
- Full local `app/ios/Tests/run_all.sh`: actual exit **0**, all 73 registered
  runner invocations completed; final `iOS logic gate: all suites passed`.
- Cursor suite: **99/99** checks; removing the cap from a temporary copy fails
  the exact missing-pending-insertion assertion. Mutation runner exit **0**.
- The process-local macOS 26.5 SDK and network-denying sandbox were used;
  loopback was allowed only for the complete suite's local fixtures. No dotenv
  sourcing or live services were required. This is not an iOS simulator build.
- Independent release-helper checks: **28 passed**, plus build-number guard.
- Read-only Apple query [34569194505](https://github.com/anticipation-labs/Anticipy/actions/runs/34569194505)
  succeeded at starting SHA. Build **174** is latest, valid and unexpired;
  internal/external states are `IN_BETA_TESTING`. The existing owner's private
  group is private, contains one tester and is attached to 174. Apple reports
  that tester's state as installed; future installation must still be confirmed
  on the actual phone.

Logs live in the ignored directory `work/ios-release-20260911.YWZXlO/`.
They include `ios-logic.log`, `cursor-mutation.log` and `apple-before.log`.
No credential values are included in this report.

## Why the experimental cursor patch is held

The broader cursor fuzz suite remains red. Independent paired testing shows
fewer lost words but additional emitted words under recognizer churn; text-only
callbacks cannot resolve every occurrence-identity ambiguity. This is a
preservation/duplication tradeoff, not a zero-regression result.

The fresh paired comparison covered 160,000 identical generated histories:
unexcused lost words decreased from 33 to 15, with no newly losing histories;
churn produced 437 additional extra words and 83 newly-extra histories. All
original broad-gate exits remain **1**. Full frozen-source logs and comparison:
`work/cursor-release-20260911/REVIEW.md`.

More decisively, independent optimized Swift measurements reproduced a
main-thread callback slowdown: revising the penultimate token of an 800-word
sent prefix with two pending words took at least 17.85 ms in the candidate versus
0.554 ms in the committed baseline. At 2,048 words it was 50.96 versus 1.46 ms.
The whole-hypothesis alignment initializes full-length rows repeatedly despite
its edit band. These are Mac synthetic timings, not a measured phone latency,
but they identify a newly introduced algorithmic risk. The patch is not shipped.
See the [independent hold decision](2026-09-11-audio-candidate-hold.md).

The original frozen patch, tests, report and scratch prototype are preserved.
No fuzz threshold, oracle, privacy constraint or release check was weakened.
The clean selected-source gate runs in `/tmp/anticipy-ios175-release.3KEVyY`,
with no experimental source or unrelated working files.

## Release sequence

The reviewed workflow requires a normal push without a ship marker to run the
actual committed simulator compile first. Only after its exact-SHA verdict may
one manual shipping dispatch be used. Manual dispatch is never a build-only
check. The uploaded number, Apple processing and audience access must be read
back independently; overall CI success alone is insufficient.

The existing automatic pilot step targets a different private group from the
owner's. The new exact build must also be attached to the already-existing owner
group; no public testing link or App Store role change is intended. Keep build
174 available while the owner tests the new release.
