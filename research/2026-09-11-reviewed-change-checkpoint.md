# Reviewed-change checkpoint — September 11, 2026

No commit, push or deployment has been performed. The next approval is for the
following exact local commit scope on `cloudflare-backend`, never `main`.
Approval to commit is not a claim that physical audio or every connector works.

## Proposed commit 1

`fix(connectors): bound provider transport and account pagination`

The reviewed diff adds finite header/body deadlines, cancellation and bounded
page traversal; releases failed in-flight owner sessions; refuses partial lists;
and preserves uncertainty/no-blind-retry behavior. No consent or write-maturity
gate is loosened.

- `migration/workers/src/connections/provider.ts`
- `migration/workers/test/connections-provider.test.ts`
- `migration/workers/test/connections-provider-liveness.test.ts`
- `research/2026-09-11-connector-liveness-repair.md`

## Proposed commit 2

`test(harness): verify isolated task flows and preserve honest failures`

The diff adds the private capped model gateway and actual local task-flow rig;
checks result hashes, mirrored receipts, explicit owner filters and durable
deduplication; preserves failed synthetic observations; corrects obsolete
retired-carrier expectations; rejects empty/unknown scenario selection; and
hardens browser cleanup and connector-command transport. It changes test
infrastructure and acceptance documentation, not production model semantics.

- `migration/spec/contract_tests.py`
- `migration/workers/scripts/sms_contract_local.sh`
- `proof/audit/isolated_model_gateway.py`
- `proof/audit/run_isolated_task_flow.py`
- `proof/audit/run_connection_commands.ts`
- `proof/audit/run_connection_commands.test.ts`
- `proof/audit/run_real_browser.mjs`
- `proof/audit/run_real_browser_safety.test.mjs`
- `proof/audit/run_reply_wire.py`
- `proof/audit/run_server_work.py`
- `proof/run_conversational.py`
- `proof/run_e2e_scenarios.py`
- `tests/test_harness_honesty.py`
- `tests/test_isolated_model_gateway.py`
- `tests/test_isolated_task_flow.py`
- `tests/test_server_work_runner_honesty.py`
- `docs/HARNESS-ACCEPTANCE-TEJAS.md`
- `research/2026-09-11-e2e-variation-plan.md`
- `research/2026-09-11-approved-fixes-checkpoint.md`
- `research/2026-09-11-audio-cursor-repair.md`
- `research/2026-09-11-audio-provenance-followup.md`
- `research/2026-09-11-harness-honesty-repair.md`
- `research/2026-09-11-harness-honesty-independent-review.md`
- `research/2026-09-11-isolated-task-flow-smoke-review.md`
- `research/2026-09-11-task-receipt-oracle-repair.md`
- `research/2026-09-11-gateway-http-review.md`
- `research/2026-09-11-browser-runner-safety.md`
- `research/2026-09-11-browser-independent-semantic-review.md`
- `research/2026-09-11-connector-intent-runner-safety.md`
- `research/2026-09-11-connector-acceptance-readiness.md`
- `research/2026-09-11-live-model-independent-review.md`
- `research/2026-09-11-funded-variation-verification.md`
- `research/2026-09-11-reviewed-change-checkpoint.md`

## Explicitly not in this release-ready commit scope

The five pending `app/ios/**` files (cursor, cursor tests/runner, project.yml and
Xcode build number) stay local. Candidate 175 passes default logic tests, but
broad legacy speech fuzz remains red. Do not present it as fully repaired or
release it on the strength of the model results. Audio reports are included only
to document that unresolved local work, not to publish its implementation or
claim a release. Any eventual iOS commit must carry
its tests and both coordinated build-number changes together.

Do not include unrelated `desktop/`, `engine/`, `.wrangler/`, older research,
private `work/` traces/databases/tokens, browser output artifacts, or `.env`.
Stage only the reviewed named paths after approval, recheck the exact staged
diff for secrets and unrelated edits, and preserve all excluded working files.

## Evidence and remaining acceptance

The final full Python suite passed 3,506 tests with two intentional model skips;
the full local iOS logic gate passed; the new browser/connector safety suites
passed 35 and 55 tests respectively. Real-model evidence independently passed
15 server-work cases, three complete local task flows, five isolated browser
tasks and three connector-command fixtures. The original failed owner-list
harness run remains visible. See
[the funded-verification report](2026-09-11-funded-variation-verification.md).

Before a later push/release, recheck workflow triggers and exact source/CI
identity. Actual phone capture, visible in-app results, installed-extension
pairing, chosen-account OAuth and real provider reads are still separate gates.
API writes remain intentionally blocked by the unimplemented capability ledger;
do not change that constant to pass a demo. Begin real connectors with one
explicitly chosen dedicated account and synthetic read-only artifact.
