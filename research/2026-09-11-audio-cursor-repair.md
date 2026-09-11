# Speech cursor pending-provenance repair — September 11, 2026

## Scope and status

Starting revision: `943cd79c9d380dfe2b363224908e089b5d7270f0`, branch
`cloudflare-backend`. User approved local fixes; root delegated only the cursor,
its tests/runner, and this report. Root owns the coordinated candidate-175 build
number changes. No commit, push, deployment, credential read, live service,
microphone, or physical-device action was performed in this lane.

**The specific pending-word regression is repaired locally. The broader cursor
fuzzer remains RED.** This is not a claim that every recognizer revision is
lossless, that the entire app is ready, or that the fix is installed on a phone.
The existing fuzzer/oracle/tolerances were not edited, and its nonzero exits
remain visible. Root explicitly approved freezing the narrow repair with that
unresolved boundary documented.

Read the branch README, AGENTS, CLAUDE, HARNESS-LAWS, iOS README and local
development instructions. Used `ecc:orch-fix-defect` and `ecc:orch-pipeline` to
preserve a red reproduction before changing production behavior and require
review. The skills did not authorize commits or a production release.

## Defect and general repair

Sent-only alignment could borrow a repeated occurrence that was still pending
to explain an earlier occurrence that had already been emitted. This moved the
boundary across real unsent words. The preserved seven-callback witness is:

```text
Friday                          [flush]
Friday Friday
Friday Fridays
doubles Fridays
doubles Fridays
doubles Fridays it
doubles kind Fridays it          [final flush]
```

Before: `Friday it`. After: `Friday kind Fridays it`.
Already-sent `Friday` is not retroactively rewritten into `doubles`; the new
insertion and surviving pending occurrence must be emitted exactly once.

`TranscriptCursor.revisedPendingBoundary(in:)` now transports the old
sent/pending split through a bounded edit alignment of the whole old and new
hypotheses. Pending context can cap an otherwise accepted sent-only boundary.
It does not relax the existing acceptance threshold, token similarity, banking,
reset, or word-meaning policy. The cap only applies when the old record still
describes the hypothesis, pending words survived, and the original placement
used alignment. When a cap leaves a pending suffix, the collapsed-record
`ranOut` flag is cleared so that suffix cannot be marked sent again.

The alignment uses the existing 64-token edit band and two rolling rows rather
than a full matrix. It prefers lower edit cost, more matching tokens, then the
earlier split. An insertion exactly at the old split remains pending. This is
occurrence provenance, not vocabulary-specific intent logic. Public API and
caller behavior are unchanged.

## Regression evidence

| Check | Result | Actual exit |
| --- | --- | --- |
| Original source with the new exact witness | 85/87; both new assertions fail | **1** |
| Frozen source, all original checks plus exact witness and 12 vocabulary/prefix variants | 99/99 | 0 |
| Frozen source with `--check-mutation` | 99/99, then removing the boundary cap from a temporary source copy fails the required behavioral assertion | 0 |
| Full candidate-175 iOS logic suite | Final `iOS logic gate: all suites passed`; build 175 bumped from 174 and not committed | 0 |

The twelve variants use three unrelated singular/plural pairs with sent-prefix
lengths 0, 1, 8 and 65, plus final capitalization/punctuation. All pre-existing
collapse, front-insertion, reset, duplicate and property assertions remain.
The default iOS gate already calls this runner, so the new exact regression is
included without removing or bypassing any other suite.

The mutation runner requires a successful mutant compile followed by nonzero
execution and the exact missing-pending-insertion assertion. A compiler error
cannot satisfy the negative control. It edits only a disposable source copy.

Frozen SHA-256 identities:

```text
c0c4a64c54397cb971746fcee9a6e2a9ac760f5aac618f37cb24f0a953d2bf7c  app/ios/Anticipy/Audio/TranscriptCursor.swift
b2dd23d3bd8c6e0f7ed4295637eb6d111e453f1f03f4b6c39ce9621ea91d16b6  app/ios/Tests/TranscriptCursorTests.swift
a920f944b690ef8972230d5129e649d6e5775063e1894b6b17be6974666410a7  app/ios/Tests/run_cursor_tests.sh
```

## Broad fuzz: explicitly not green

The fuzzer is a separate runner, already excluded from the default iOS gate.
Its printed `HEAD~1` comparator is embedded historical `OldCursor`, not the
current parent commit; the positive current-cursor assertions are still real.
For a same-revision comparison, the original cursor at `943cd79` was also
compiled with the unchanged fuzzer. No word-loss allowance was changed.

| Source / seed / schedules | STRICT unexcused losses | INSERTION unexcused losses | CHURN unexcused losses | Actual exit |
| --- | ---: | ---: | ---: | ---: |
| Original / 1234 / 30,000 | 0 | 0 | 5 in 5 schedules | **1** |
| Frozen repair / 1234 / 30,000 | 0 | 0 | 1 in 1 schedule | **1** |
| Frozen repair / 9001 / 30,000 | 0 | 2 in 1 schedule | 0 | **1** |
| Original / 42 / 100,000 | 0 | 7 in 4 schedules | 17 in 15 schedules | **1** |
| Frozen repair / 42 / 100,000 | 0 | 7 in 4 schedules | 5 in 4 schedules | **1** |

The initial seed-42 repair run preceded the final `ranOut` correction. A fresh
seed-42 run against the frozen hashes completed with the same counts and exit 1:
three INSERTION and two CHURN honesty-wall failures. All runs retain the
original 140 historical replay schedules, which pass.
The CHURN population intentionally banks under uncertain rewrites and still
emits extra words; do not infer zero duplication from the exact regression.
The frozen seed-42 repair emitted 92,090 extra CHURN words versus 91,802 for
the original, while reducing measured losses. That is a conservative-preserving
tradeoff, not a zero-flaw result or a measured physical-phone error rate.

### Unresolved observation/oracle boundary

Printed residual witnesses include shared-prefix windows and hidden
recognizer-window state. For example, seed-42 CHURN witness 14054 begins:

```text
we [flush]
we
we
we
we garage
we garage that
we garage that me
kind we garage that me [insertion at index 0]
```

The fuzzer knows that a second decode window began with another `we`; the
cursor receives only the callback strings. The exact same visible callbacks
can instead be a revision inserting `kind` before an already-emitted `we`,
which the existing front-insertion/nonduplication contract absorbs. A
text-only cursor cannot distinguish these histories by word meaning. The
fuzzer's per-window committed-position accounting resets its emitted count
while a shadowed shared prefix remains relevant to later insertion burial.

This is a concrete ambiguity worth resolving with recognizer segment/timestamp
provenance and an independently reviewed oracle contract. It is **not proof
that every residual is an oracle error**, and it is not permission to excuse
the current reds. The broad gate remains unresolved. No API expansion was made
in this narrow repair.

## Commands and logs

Commands ran from the product root with this process-local SDK and OS network
sandbox. The pure cursor commands deny all outbound network; the full suite
permits loopback only for local fixtures. No global SDK change or dotenv load:

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
PYTHON_DOTENV_DISABLED=1 CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV=false \
WRANGLER_SEND_METRICS=false npm_config_offline=true \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)(allow network-outbound (remote ip "localhost:*"))' \
  sh app/ios/Tests/run_all.sh
```

Using the same SDK and deny-all-outbound sandbox:

```sh
sh app/ios/Tests/run_cursor_tests.sh --check-mutation
sh app/ios/Tests/run_cursor_fuzz.sh 30000 1234
sh app/ios/Tests/run_cursor_fuzz.sh 30000 9001
sh app/ios/Tests/run_cursor_fuzz.sh 100000 42
sh app/ios/Tests/run_cursor_bench.sh
```

Actual command exits were retained separately from `tail` output. Fresh logs:

- `work/ben-cursor-repair-red-20260911.log`
- `work/ben-cursor-final-mutation-20260911.log`
- `work/ben-cursor-final-fuzz1234-20260911.log`
- `work/ben-cursor-final-fuzz9001-20260911.log`
- `work/ben-cursor-final-fuzz42-20260911.log`
- `work/ben-cursor-full-ios-candidate175-20260911.log`
- `work/ben-cursor-prototype-bench-20260911.log`
- `work/ben-cursor-compare.DYuzFQ/original42.log`
- `work/ben-cursor-compare.DYuzFQ/originalbench.log`

Original source was exported read-only from Git into the ignored comparison
directory using `apply_patch`. An initial stdin-based compile failed to link;
it did not execute a test and was not counted as a fuzz failure. The corrected
file-based compile succeeded and produced the original seed-42 results above.

The informational initial-repair benchmark measured 800 words / 1,310 callbacks
at mean 0.2165 ms and worst 5.7183 ms when flushing about every 30 words; never
pausing measured mean 0.1497 ms and worst 0.6038 ms. The benchmark has no pass
threshold and runs on a shared Mac, not a phone. A zero exit is not a latency
certification.

The same informational benchmark compiled against the original `943cd79`
cursor measured the 800-word flush case at mean 0.1030 ms, worst 2.4548 ms;
never-pausing mean 0.1559 ms, worst 0.6605 ms. The repair adds measurable work
to the alignment/flush workload (approximately twice the mean in these two
runs), while the no-pause workload was similar. These were not controlled
phone measurements; a real handset performance check remains appropriate.
Do not claim zero runtime overhead or hide the growth shown by the benchmark.

## Release limits

The compatibility recognizer emits partial strings and exercises this cursor
path. The iOS 26 Analyzer emits settled phrases with its own finalization
boundary; it does not make the partial-result defect irrelevant because legacy
mode remains reachable by compatibility settings and fallback.

The required pre-edit full iOS baseline passed on the same starting revision
in `work/ben-e2e-audio-baseline-20260910.yp9DkQ`. No iOS SDK is installed here;
pure-source and macOS framework tests do not constitute an iOS archive,
TestFlight upload, mounted SwiftUI test, or physical capture/reply validation.
The complete local-vs-device limitations remain in
`research/2026-09-10-e2e-audio-variation-review.md`.

The full candidate-175 suite completed with exit 0. It still explicitly reports
that `SettingsHomeView` and the ASWebAuthenticationSession/Safari half of
`ConnectSession` were not compiled without an iOS SDK. Independent root source
review is in progress. The separate fuzz gates remain red despite the passing
default suite.

## Additional bounded peer review: isolated model gateway

At root's request, independently reviewed `proof/audit/isolated_model_gateway.py`,
`tests/test_isolated_model_gateway.py`, and the imported budget/preparation and
dotenv-parser code. No edits were made to these files in this lane. This was
a scoped local peer review, not an exhaustive security scan.

Found and reproduced a run-end deadline gap: a request admitted shortly before
the overall deadline could still take the transport's full 90 seconds. An
offline actual-handler fixture with 20 ms remaining and a 60 ms synthetic
transport returned success after the deadline. Root repaired it by rechecking
after durable reservation and passing `min(90, remaining)` to the bounded
transport, scheduling server shutdown at the run deadline, and giving the
keyless public pricing fetch a 20-second total deadline and 8 MB bound.

After those changes, independent tests passed **18/18, exit 0** with all outbound
network denied (`work/ben-isolated-gateway-recheck-20260911.log`). Three additional
injected-transport checks also passed against the actual gateway implementation:

- Actual gateway plus actual HTTP transport cancels a slow mocked provider at
  the remaining run deadline; the unknown $1 reservation stays committed and
  the ledger is halted.
- Sixteen concurrent synthetic operators dispatch exactly five $1 completions;
  no sixth request reaches the provider fixture, and the ledger is exactly $5.
- Expiry occurring during durable reservation refuses dispatch and retains the
  reservation rather than falsely refunding it.

No real key, model request, or production data was used. Selected-key parsing is
data-only and checks one private regular descriptor; the key only enters the
fixed OpenRouter Authorization header, never command arguments or ordinary
diagnostics. Redirects/environment proxies are disabled. Reservation is durable
and serialized before dispatch; missing/invalid cost retains the unknown hold.
A reported cost greater than its reservation records the observed amount and
halts, rather than claiming a refund or concealing a provider pricing breach.
Raw synthetic prompts/results are retained in the private local trace directory;
this is not a zero-retention test tool. No remaining blocker was identified in
this bounded review; provider billing behavior and live model results are not
proven by these mocked transport tests.
