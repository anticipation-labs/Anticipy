# Harness honesty repair — 2026-09-11

Scope: local harness fixes only, on `cloudflare-backend` after the `943cd79c` baseline. No model/provider calls, deployed resources, customer data, environment secrets, Git writes or deployments were used. These changes are not new evidence of phone/audio use or live task completion.

## Defects and repairs

1. `proof/audit/run_reply_wire.py` previously filtered an unknown selector into zero cases and used `all([])`, which could report success after reading the gateway credential. Omitted selection now explicitly means all cases; empty, unknown and duplicate names fail with CLI exit 2 before reading the credential or creating a fixture. Selected/completed names and counts are emitted, and empty, partial, duplicate, failed or non-boolean-pass results cannot be green.
2. The reply wire runner accepts an explicit `--state-dir` and loopback-only `--gateway-url` for a fresh bounded audit. Unsafe labels/URLs/parallelism and missing, empty or malformed HTTP credentials fail before fixture writes. Defaults remain compatible. Model failure output is limited to a fixed category and validated numeric status; raw response bodies and original exception messages are not emitted by this wrapper.
3. Both historical `proof/run_conversational.py` and `proof/run_e2e_scenarios.py` overrides rejected the current `touches` argument. Their signatures now accept it, preserve declared effect metadata, hold `world` effects, and reject unknown effects or unsupported non-null action declarations before sending a job. They are explicitly labelled historical drivers: the signature repair does **not** make their legacy environment loading, account selection, browser effects, simulated approvals or cleanup production-safe. They were not executed.
4. `migration/spec/contract_tests.py` still expected an active Twilio route. All six retirement cases now assert the current `410` / `messaging_endpoint_retired` response and no matching local event, including signed owner text and replay. Synthetic signatures need no actual Twilio credential. The former two-active-carrier comparison now requires no Twilio row and a complete canonical SendBlue row. No SendBlue case was removed or skipped.
5. `migration/workers/scripts/sms_contract_local.sh` used the preexisting default D1 state and recursively removed a fixed bare-state directory. It now creates unique temporary state for both Workers, passes that exact state into the D1 oracle, disables dotenv, process-env inclusion, metrics and package downloads, and uses `--env-file /dev/null` to suppress Wrangler `.dev.vars` loading. Only its newly created database directories are removed; its log is retained. Missing committed assets fail instead of calling the obsolete asset-build command.

## Actual checks and evidence

| Check | Actual result | Evidence |
| --- | --- | --- |
| Fresh pre-change full Python baseline | 3389 passed, 2 explicitly live-model-gated skips; exit 0 | `work/e2e-backend-review-python-20260911T035554Z.log` |
| Regression first: original selector, override and carrier contracts | 15 failed, 3 obsolete Twilio-credential skips; exit 1 | `work/harness-honesty-red-20260911.log` |
| First focused repaired slice | 27 passed; exit 0 | `work/harness-honesty-green-20260911.log` |
| Full real-workerd SMS wire, fresh local D1 | 21 passed, 0 skipped, 307 unrelated deselected; exit 0 | `work/harness-honesty-sms-wire-20260911.log` |
| Combined first attempt with accidental deny-all network fence | 235 passed, 1 failed because the intended local mock-provider socket was denied; exit 1, no code change for this | `work/harness-honesty-combined-20260911.log` |
| Combined slice with localhost exception | 236 passed; exit 0 | `work/harness-honesty-combined-loopback-20260911.log` |
| Final combined slice with three added malformed-token cases | 239 passed, 0 skipped; exit 0 (includes 30 focused harness cases) | `work/harness-honesty-combined-final-20260911.log` |

The combined slice runs harness honesty, conversation integrity, inbound reply failure durability, SendBlue arm, SMS delivery diagnostics, task revision and reply delivery. Shell syntax and scoped `git diff --check` pass. The real-workerd run exercised six retired-carrier and fifteen SendBlue cases. Both Worker and inspector port pairs were verified closed afterward, and both temporary state directories were verified absent. Its workerd log remains in the unique temporary directory recorded in the wire log. Preexisting `.wrangler/state` and fixed bare-state directories were not touched.

All executions used a scrubbed environment and an OS-level external-network deny policy. Loopback was allowed only where needed for actual local workerd/D1 or the local mock provider. Approved secret-file locations were additionally denied. The two historical drivers were tested by compiling only their queue overrides, not importing/executing their old bootstrap paths. Fake-result tests cover runner plumbing, not model quality.

## Frozen review boundary

| File | SHA-256 |
| --- | --- |
| `proof/audit/run_reply_wire.py` | `66947636719561a76b241db71ed7e1925d85990fc158857f5a42d68ed365e1c6` |
| `proof/run_conversational.py` | `2b575ffe0748e89f03feaae19927d84eee8266e6838e533d8de089033b19dbdd` |
| `proof/run_e2e_scenarios.py` | `779d9e7f9d7d8c8a232fc8abee4e801a955b7e33a58cc3d7cd238d529cfe2a8f` |
| `migration/spec/contract_tests.py` | `5238656875f63bf4e889a584bc1ec14ebde6ced44954831774ab1928b3599966` |
| `migration/workers/scripts/sms_contract_local.sh` | `9f7b31f5dd4e172cfb3b05a251c7741d5938b34fda647b0ee5a08390e951284c` |
| `tests/test_harness_honesty.py` | `a37a50ecda0f6150ed234c36a3b7ab0a8378989824a23ce1c13a12da6dd094c3` |

Independent review completed by Tom: frozen hashes matched, all 30 focused cases passed independently with exit 0, and shell syntax plus scoped diff checks passed without blocking findings. See `research/2026-09-11-harness-honesty-independent-review.md`. Commit/publication is outside this agent's scope. A fresh full-suite aggregate is the coordinator's release gate; the earlier 3389 baseline is explicitly pre-change. No live model or browser/device success is claimed here.
