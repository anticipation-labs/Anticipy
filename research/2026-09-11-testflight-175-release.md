# Private TestFlight release 175 — September 11, 2026

## Scope and current status

**Released: 1.1.1 (175), available to the owner's existing private group and the
approved pilot.** Apple installation eligibility is verified; installation of
175 on the owner's phone and new physical stress-test results are not yet
confirmed. This is a private TestFlight release, not an App Store submission.

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

The independently reviewed five-file release patch has SHA-256
`eb6111dda7f8dff8fe54510c59a4d4ef57d8c957b5b7ce9eb46a6c583f3bc48f`.
It was committed and pushed only to `cloudflare-backend` as
`2aa46746a656481a2df032924532f266f8a2ec64` with no upload marker.
The exact-commit [build-only CI run 34569707889](https://github.com/anticipation-labs/Anticipy/actions/runs/34569707889)
**passed**, including the complete iOS logic gate and actual simulator build.
It skipped every upload/signing/distribution step, as intended. After rechecking
the remote branch tip, one explicitly authorized
[shipping run 34570320203](https://github.com/anticipation-labs/Anticipy/actions/runs/34570320203)
was dispatched. Its verified head SHA is the same `2aa46746`. That shipping run
**passed** in 13m34s: tests, simulator compilation, signed archive, upload,
processing and the configured private-pilot handoff all succeeded.

Apple confirmed marketing version **1.1.1**, source/upload build **175**, with no
number collision or relabeling. Upload reported `UPLOAD SUCCEEDED with no errors`;
processing became `VALID`. The configured private pilot was read back as
`IN_BETA_TESTING`, `ready_to_install: true`, private and assigned, with automatic
notifications enabled. This does not prove a notification reached a handset.
Its tester-level `INSTALLED` state is not proof of installing 175.

The exact build was then attached to the already-existing owner group using the
explicitly approved helper in
[owner-access run 34571363972](https://github.com/anticipation-labs/Anticipy/actions/runs/34571363972),
also on `2aa46746`. It succeeded. Readback confirmed build **175**, `VALID`,
`expired=False`, external/internal `IN_BETA_TESTING`, and
`ready_to_install: true`. The owner's private external group contains the same
one tester; no new group, App Store role or public link was created. The complete
build readback lists the existing Internal, owner-private and approved-pilot
groups, all with public links off. The owner was told to update in TestFlight;
physical installation of 175 has not been inferred from tester-level metadata.

Final evidence files: `build-only-result.json`, `build-only-ci.log`,
`shipping-result.json`, `shipping-ci.log`, `owner-access-result.json`, and
`owner-access-ci.log` under the ignored release-evidence directory. No additional
binary upload was used to fix group access. No previous build was expired.

Additional selected-source checks completed after that push: analyzer lifecycle
**169 checks** and **10 compiled behavioral mutations**; capture lifecycle
**68 checks** and **11 compiled behavioral mutations**. Both runners exited **0**.
The mutated copies were disposable; none entered the app source. Logs are
`selected-analyzer-mutations.log` and `selected-capture-mutations.log` in the same
ignored release-evidence directory. These execute production method bodies with
controlled OS edges, not real microphone or Apple speech-model sessions.

The reviewed workflow requires a normal push without a ship marker to run the
actual committed simulator compile first. Only after its exact-SHA verdict may
one manual shipping dispatch be used. Manual dispatch is never a build-only
check. The uploaded number, Apple processing and audience access must be read
back independently; overall CI success alone is insufficient.

The existing automatic pilot step targets a different private group from the
owner's. The new exact build must also be attached to the already-existing owner
group; no public testing link or App Store role change is intended. Keep build
174 available while the owner tests the new release.

## Local continuation boundary

The shared checkout intentionally retains the three uncommitted experimental
cursor/test/runner files at their original reviewed hashes. They are not the
released source. After the 175 metadata commit, the final build-number leg will
correctly reject that dirty iOS source until a future reviewed source change is
assigned its own new build number. Use a clean checkout of the release commit
to reproduce the green release gates; never include the experiment with a
blanket stage or relabel its results as build-175 behavior. No local work was
discarded to make the release look clean.

Final independent release review reconfirmed all three exact-SHA CI/Apple runs,
owner-group eligibility and the unchanged held-source hashes. The disposable
clean test worktree was removed after validating it contained only this task's
two metadata edits and no untracked files. Its source remains reproducible from
Git; all gate/release logs remain in the ignored evidence directory. No local
test server or workflow watcher from this release is left running.
