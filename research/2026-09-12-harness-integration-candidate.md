# Harness integration candidate — 2026-09-12

Status: local repair candidate, not a production acceptance report.
Base: `e6161de267901b22ff93a401197c74e444d4d0eb` on `cloudflare-backend`.
Integration branch: `codex/integrate-harness-20260912`.

## What is integrated

- Browser iframe geometry, current hit-testing, heartbeat freshness, bounded
  active runs and lease-scoped cleanup. Covered or stale targets refuse a click.
- Initial connection-code delivery accounting, bounded OAuth recovery, and
  cancellation/Skip fencing. Semantic D1 readiness compares actual trigger
  bodies and uses repeat-safe additive migrations.
- API account ambiguity stays on the API lane. An answer replans the same task
  against current owner-scoped connections with the original question, answer,
  task context and revision. It preserves the selected account through failures
  instead of silently choosing another account or moving to the browser.
- A selected account disappearing before or during execution leaves a useful
  hold; stale arguments are cleared while the next owner reply can recover the
  API task. Cancelled, changed-owner and stale-presentation replies cannot win.
- Provider scope refusal is distinct from a dead credential. API effect checks,
  lease expiry and atomic settlement prevent unsupported writes or false
  completion receipts. **API writes remain unavailable without their ledger.**
- Native receipt rendering understands the actual server/browser/connected-app
  dialects without manufacturing evidence. Connected-app settings distinguish
  saved choices from effective capability, provide explicit false-only clearing,
  serialize mutations, reject stale-session responses and validate complete
  server acknowledgments. Uncertain saves require a fresh read before retry.
- The isolated model-test gateway requires explicit dollar and call limits.
  Focused memory/account diagnostics no longer print the affected private text
  or exception messages. This is not a comprehensive application privacy audit.

The candidate contains original product implementation and existing dependency
usage. No third-party onboarding or agent product code is imported. New Mac
personal-source scanning, memory-source grants and overnight execution are not
included in this repair release. The separately held audio cursor experiment is
also excluded: the candidate retains its base implementation and tests.

## Regressions and independent review

Tests were added against actual production sources before repairs. The account
journey uses the real Conversation, Worker router, SQL and API adapter with
synthetic model/vendor responses. It follows a typed answer through the chosen
account read, synthesis, and an effect-bound verified receipt.

Adversarial review reproduced three additional gaps beyond the initial tests:
loss of a previously named account, disappearance during replanning, and a stale
plan that parked on the API lane while still carrying a browser hand marker.
Those reproductions now pass; the final source was reviewed independently from
the author. Native consent/client changes and the build-only workflow received
separate review. Scripted model decisions are not evidence of live model quality.

## Candidate identity

- iOS/Mac source build: **176**, marketing version **1.1.1**. Both checked-in
  project-number files agree; this is not an Apple upload receipt.
- Browser extension: **0.18.2**. Manifest, runtime marker and native stale-version
  warning agree. A running 0.18.1 extension is identified as older.
- All three download aliases contain the same dependency-complete runtime graph
  and exact source bytes. SHA-256:
  `3e9c6e22ab13a38c03bdd5562e9d7566bb9bc03191441454deb5fadbb8a45b1a`.

## Verification ledger

Local checks disable automatic dotenv loading and outbound network access;
loopback is allowed only for isolated test services. Existing locked dependency
installs are reused. No live customer data or paid model call is used.

| Check | Result on candidate |
| --- | --- |
| Full iOS logic gate, including source build identity | Exit 0 |
| Full Mac source/logic gate | Exit 0 |
| Native source stability | All 351 app-tree files unchanged during verification |
| Real headless Chrome geometry/hit-testing fixtures | 7/7, exit 0, no non-fixture requests |
| Extension package/version/build-only workflow focused tests | 18 passed |
| Exact archive source bytes and alias equality | Exit 0 |
| Brain Worker fleet/lifecycle/erasure tests and types | Both exit 0 |
| Full API Worker suite and types | Both exit 0 |
| Full Python suite after CI fixture portability repair | 3,715 passed, 2 explicit live-model skips, exit 0 |
| Full extension suite | 88/88 suites, exit 0 |
| Actual iOS simulator compile in full Xcode | Passed on `1ea300617b2d988f51feccd8f34226226953a8fa`; native source unchanged by fixture follow-up |
| Actual unsigned universal Mac app build in full Xcode | Passed on the same native source |
| Installed extension, phone, selected live connector and real-model journeys | Not verified by these local checks |

The first local Chrome attempt stopped before launch because the default module
search did not find Playwright. The successful retry explicitly selected the
existing installed module; no dependency or browser was downloaded.
The Python run reports one pre-existing invalid-escape deprecation warning in
`test_research_query_is_not_a_verb_list.py`. Neither that warning nor the two
explicit live-model skips was suppressed. The 249 captured Worker/extension
source, test and schema hashes remained unchanged through their final runs.

The first [System invariants run](https://github.com/anticipation-labs/Anticipy/actions/runs/34711778391)
passed its Worker and actual Mac build jobs but failed five Python fixture
rewinds. This was reproduced on SQLite 3.51.0: an older engine bug mishandles a
comma inside a retained comment when `DROP COLUMN` removes the final column.
The fixture-only follow-up strips lexical comments before constructing its
temporary database while preserving quoted SQL byte-for-byte. No production
schema or migration was changed. Existing migration/replay/refusal assertions
remain, with added whole-schema, default, CHECK, foreign-key, index and trigger
parity checks. All **33 focused checks passed independently on SQLite 3.51.0 and
3.53.4**, followed by the full local Python result above. The follow-up still
requires its own CI result; consult the PR's current checks, not the earlier red
run, for that receipt.

The [actual iOS build-only run](https://github.com/anticipation-labs/Anticipy/actions/runs/34711778293)
passed both full native logic and simulator compilation. It did not sign,
upload or distribute a build.

## Build and rollout boundaries

The new `ios-candidate.yml` runs the full native logic gate and compiles the
committed simulator project on PRs into `cloudflare-backend`. It has read-only
repository permissions, no retained checkout credentials, no secrets, no signing
and no upload/invitation/distribution steps. The iOS shipping workflow is unchanged.

Before production promotion:

1. Require exact-source build-only CI and review its actual Xcode result.
2. Refresh deployed API/brain identity and settings. Apply only the two reviewed
   additive recovery migrations with the existing guarded applier; verify
   semantic readiness before dependent API code. Never replay the fresh schema.
3. Preserve the minute OAuth recovery trigger and existing capacity/state.
   Do not re-enable the old reminder backlog sweep or interrupt active owner
   work without reviewing the current rollout risk.
4. Verify deployed revision, schema, bindings and behavior. Check the live ZIP
   bytes and actual installed extension, not just a local version string.
5. Recheck available Apple build numbers and authorized existing audience, then
   use the deliberate release path. Availability is not phone installation.
6. Verify the selected live connector and handset/audio journeys. Keep missing,
   skipped or failed acceptance legs visible. Do not enable unsupported API
   writes or call the whole app end-to-end ready merely because CI is green.

Keep the working release available until this candidate passes those gates.
