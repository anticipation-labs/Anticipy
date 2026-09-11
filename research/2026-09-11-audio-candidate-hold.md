# Audio candidate held from private build 175

Independent, offline review on 2026-09-11. No application edits, microphone use,
customer-data access, provider/model calls, Git writes, or deployment were performed
by this reviewer. The coordinator requested this evidence note after deciding to
exclude the experimental cursor changes from the private release.

## Exact candidate and baseline

Baseline: `c05d614a7597ee9b03aef3cf791bfb274e3d6751` on `cloudflare-backend`.
The reviewed immutable five-file `candidate-175.patch` has SHA-256:

`06030a66b84ff4ce96fdad4b5b6ce961021a6cb6c949bd586a996acdba8a59cf`

Its cursor source has SHA-256:

`c0c4a64c54397cb971746fcee9a6e2a9ac760f5aac618f37cb24f0a953d2bf7c`

The patch contains the cursor, its unit tests/mutation runner, and coordinated
174-to-175 build-number changes in the Xcode project and generator configuration.
It contains no new authentication, account, network, persistent-storage, or
capture-lifecycle logic. The reviewed cursor remains reachable through the legacy
speech recognizer, including the fallback from the iOS 26 engine.

## Introduced performance regression

The new `revisedPendingBoundary(in:)` scans the entire previous hypothesis.
At reviewed source lines 417–420, every old-token row allocates and initializes
three arrays of `n + 1` entries. Although the computed cells use a 64-token band,
the row initialization is not band-limited. The pass also revisits the entire
agreeing prefix, unlike the existing sent-record alignment's prefix fast path.

`PhoneListener` dispatches recognition callbacks to the main queue at lines
1175–1185 and calls `cursor.observe` at line 1381. This additional work therefore
affects foreground responsiveness and speech callback processing.

Independent reproducible witness, using the same driver for both source versions:

1. Create `N` tokens named `term0` through `term(N-1)`; observe and flush them.
2. Observe the original hypothesis with `pending speech` appended, without flushing.
3. Replace the penultimate original token with `changed`, leaving the pending
   suffix intact. Time only this `observe` call.
4. Repeat three times with fresh cursors, then check that the pending suffix is
   retained, reset clears sent/pending counts, and a new phrase emits independently.

Both versions were compiled with `swiftc -O` and the installed macOS 26.5 SDK in an
external disposable snapshot, with network denied and writes confined there.
The driver and test processes returned exit 0; the timing evidence, rather than a
pre-existing timing assertion, establishes the regression.

| Previous sent tokens | Candidate minimum / maximum ms | Baseline minimum / maximum ms |
| --- | --- | --- |
| 200 | 3.570 / 3.801 | 0.149 / 0.166 |
| 800 | 17.851 / 18.037 | 0.554 / 0.581 |
| 2,048 | 50.960 / 51.836 | 1.455 / 1.515 |
| 4,096 | 114.939 / 116.542 | 2.926 / 2.941 |
| 8,192 | 247.488 / 249.785 | 5.945 / 6.049 |

At 800 words this specific late-revision path is approximately 32 times slower.
The longer cases characterize growth; they are not evidence that a real phone
regularly receives such hypotheses. The synthetic similarly spelled tokens
exercise the existing fuzzy-token comparison. Shared-Mac measurements are not
iPhone latency measurements or a universal callback-time bound.

Reusing rolling-row arrays would remove the repeated full-row allocation, but it
would not by itself avoid comparing the agreeing prefix. No performance repair
was attempted in this release review, and no claim is made that this proposed
optimization alone would restore baseline latency.

## Correctness and test evidence

The independently executed frozen mutation runner returned exit 0:

- All 99 candidate cursor checks passed.
- Removing the pending-boundary assignment in a temporary copy compiled
  successfully and failed the required missing-insertion behavioral assertion.
- The benchmark driver's pending-suffix and reset-isolation controls passed for
  both baseline and candidate at every tested size.

The new seven-callback regression is useful: after flushing `Friday`, the sequence
`Friday Friday`, `Friday Fridays`, `doubles Fridays`, `doubles Fridays`,
`doubles Fridays it`, `doubles kind Fridays it` must retain the pending insertion
and occurrence. The candidate emits `Friday kind Fridays it` in that focused
case. This does not establish zero loss or zero duplication for arbitrary speech.

The existing broader fuzz failures must be compared against the actual committed
baseline. They are not automatically regressions introduced by this patch, and
they must not all be dismissed as oracle defects. The earlier audio repair report
also records an extra-word tradeoff. The separate paired semantic review owns the
fresh broad-fuzz comparison; this note does not claim to reproduce its results.

## Release verdict

**Hold the experimental cursor changes from private build 175.** The independently
observed main-thread performance regression warrants revision before this patch
is included. The patch-risk review's mutation and caller-boundary checks influenced
this decision; green focused tests alone were not treated as release proof.

Preserve the three experimental cursor/test/runner files for follow-up. The
coordinator's selected release plan is a fresh build number with the committed,
source-equivalent-to-build-174 iOS application behavior. That plan still requires
its own exact-artifact build and distribution checks. This note does not claim
that build 175 has been uploaded, installed, or physically tested, nor that the
baseline speech path is flawless.
