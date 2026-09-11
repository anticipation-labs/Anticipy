# Approved repair checkpoint — September 11, 2026

**Later resumed verification:** the funded local key is now saved and verified.
Real-model server work, three complete local task flows, five isolated Chrome
scenarios and three connector-command fixtures passed subsequent independent
review. See [the newer funded-verification report](2026-09-11-funded-variation-verification.md)
for the preserved initial harness failure, repairs, closed budget and remaining
device/OAuth/audio gates. The credential blocker described below is historical.

Branch `cloudflare-backend`, based on `943cd79c9d380dfe2b363224908e089b5d7270f0`.
The user approved the task-variation plan and local fixes. This checkpoint does
not certify the whole product or authorize a hidden deployment. No commit,
push, production mutation, real message, purchase, or TestFlight upload occurred
in this repair turn. Candidate iOS build **175 is local**, not installed build 174.

## Implemented and measured

| Repair | Evidence | Boundary |
| --- | --- | --- |
| Connector header/body hangs and endless page walks | 28 new liveness cases, full 44-command API gate and typecheck pass | Native local sockets and recorded providers, not live OAuth/tools |
| Speech pending-token provenance | Exact formerly failing witness plus 12 vocabulary/prefix variants; 99 cursor checks and mutation control pass | Broad fuzz remains red; no physical-phone performance proof |
| Default iOS gate | All suites pass on local candidate 175 | No local iOS SDK, archive, installed TestFlight or mounted SwiftUI proof |
| Honest reply-case selection, legacy signatures and retired-carrier contract | 30 focused regressions; independent review passes | Historical drivers remain unsuitable for production acceptance |
| Local SendBlue wire and isolated SMS runner | 21/21 actual-workerd cases, zero skips, exit 0; scratch state removed and ports closed | No actual SMS sent |
| Small-budget isolated model transport | 18 offline tests; peer review plus deadline and concurrent-reservation attacks pass | Zero paid calls; no current funded-key evaluation |
| Server-work runner safety | 6 offline tests; peer review passes | Test doubles for runner wiring, not model judgement |
| Isolated local task-flow rig | Independent actual-workerd publisher smoke 3/3 passes; fixture deletion confirmed and child processes stopped | Smoke does not execute reasoning or task formation |

Independent evidence and exact source identities:

- `research/2026-09-11-connector-liveness-repair.md`
- `research/2026-09-11-audio-cursor-repair.md`
- `research/2026-09-11-harness-honesty-repair.md`
- `research/2026-09-11-harness-honesty-independent-review.md`
- `research/2026-09-11-isolated-task-flow-smoke-review.md`

Root's full Python regression pass: **3,437 passed, 2 intentional live-model
skips, exit 0**, 127.56 seconds, in
`work/repair-full-python-20260911.7HW85G`. Additional runner guards added after
that collection pass are covered by a separate **73-case** network-denied suite.
The final complete rerun finished **3,457 passed, 2 intentional live-model skips,
exit 0**, 125.70 seconds, in `work/repair-final-python-20260911.dsSY6h`.
Five additional malformed-oracle cases were added after that run's collection;
the final 73-case focused run and Tom's independent 19-case runner pass include
them. No failing or skipped check was relabelled as success.

Root independently ran the isolated publisher smoke after reviewing Tom's
environment and process-cleanup repairs: `work/root-isolated-smoke-20260911.bkcKJL`,
result `work/isolated-task-flow-uh34gr9t/result.json`. Three cases passed with
fixture deletion; the actual publisher kept one answer when publication was
repeated with different text. It did not run paid models or create any task.
Root also corrected the future real-mode result oracle to use the actual
`Plan.source_event_ids` list, not a singular field, and require a verified
receipt with evidence. A regression builds the actual Plan/claim/succeed objects
and rejects a foreign input or unverified receipt. Real mode remains unexecuted.
Peer review then caught a malformed-oracle false positive (substring membership
in a scalar source string). Both lineage and receipt evidence now require
nonempty lists of nonempty strings, with exact source-ID membership; five
malformed-shape regressions pass. This is test-oracle hardening, not an app fix.
Root's direct read-only inspection of the fresh smoke D1 after cleanup found
**0 owners, 0 events, 0 jobs**. Ports **18555 and 18556 had no listener**.
The private scratch database and logs remain as evidence; only the newly
created synthetic test accounts and their records were deleted.

The new `proof/audit/isolated_model_gateway.py` reads only an explicitly selected
private dotenv's OpenRouter key as data. It does not source the file or adopt a
backend/owner default. It reserves the maximum priced model context plus bounded
output before each request, serializes dispatch, caps cumulative usage at US$5,
caps calls at 100, and closes the run at 30 minutes. A lost response or unverifiable
cost retains its reservation and halts further calls. Redirects, inherited proxies,
paid add-ons, unsupported models and oversized requests/results are refused.
Each run uses a new private journal; old evidence is never reset. The provider
must still honor its documented pricing cap; these tests are not a billing guarantee.

The existing reply, server-work and real-Chrome fixture runners now accept an
explicit isolated state/gateway (CLI for Python, `ANTICIPY_AUDIT_STATE_DIR` and
`ANTICIPY_AUDIT_GATEWAY_URL` for Chrome). Server calls are serial and an inherited
Gemini key cannot bypass the gateway. Error bodies are not printed. Chrome's
historical `--backend` path remains a separate live workflow and was not used.

## Blocking real-model evaluation: two different OpenRouter accounts

Read-only official API checks were made against the key in the user-selected
workspace-root `.env` file without exposing its value, label,
hash or raw provider response:

- `/api/v1/key`: HTTP 200 (key authenticates).
- `/api/v1/credits`: HTTP 200, remaining credit nonpositive.
- The existing company-browser Credits page visibly showed a funded account.

Authentication success is not proof of funded completion access. The local key
cannot currently fund this evaluation. No paid completion was attempted, no
existing key was rotated, and no Cloudflare secret was changed. The user was
asked to save a key from the funded account (a US$5-limited test key is sufficient)
as `OPENROUTER_API_KEY` in the same private file, never in chat. Cloudflare secret
presence is not proof that this local key matches its encrypted deployed value.
The user replied with approval, not confirmation that a key had been saved.
The company-browser API-key form is prepared with name “Anticipy isolated
harness - Sep 11”, a **US$5 total limit**, **one-day expiry**, and **no reset**.
Creation was not submitted. The tab is preserved for the user's credential
creation and saving step; existing production/pilot keys remain unchanged.

Official references used for these read-only checks and model-pricing retrieval:
[current API key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key),
[credit balance](https://openrouter.ai/docs/api/api-reference/credits/get-credits),
[model catalogue](https://openrouter.ai/api/v1/models).

## Still unresolved — do not present these as passed

1. Broad cursor fuzz: repaired seed 1234 still reports one CHURN word loss;
   seed 9001 reports two INSERTION losses; seed 42 reports seven INSERTION and
   five CHURN losses. The original oracle and thresholds are unchanged. Hidden
   decode-window identity creates a concrete ambiguity, but that does not prove
   all residual failures are oracle errors. Recognizer provenance and physical
   fallback capture remain follow-up work. The repair also adds measured work
   to the alignment-heavy benchmark; phone performance is not certified.
2. Real-model task formation, varied task execution and real-model browser
   behavior await the funded local test key. Local fixture success must not be
   relabelled as paid-model or whole-product success.
3. No paired browser agents or connector grants were present in the last scoped
   readiness read. New OAuth/account choices still belong to the user. Their
   preexisting active job remains untouched; pairing it casually could run work.
4. Installed-device behavior, real-provider OAuth, and precise post-release
   identities require separate acceptance after the reviewed-diff/commit gate.

ECC defect-fixing and regression-testing skills shaped the red-before-green
checks and independent reviews. Workers guidance shaped bounded streaming I/O.
The defect workflow's separate pre-commit checkpoint still applies; no release
claim is made merely because the local default suites are green.

Final Git check: branch remains `cloudflare-backend`, HEAD remains `943cd79c`,
and `git diff --check` plus the coordinated build-number check pass. Changes
remain written locally, unstaged and uncommitted. Unrelated preexisting files
and research notes are preserved. All processes started for these tests have
finished; no local server or paid gateway is left running by this turn.
