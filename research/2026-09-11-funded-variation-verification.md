# Funded task-variation verification — September 11, 2026

Work remains on `cloudflare-backend`, based on `943cd79c`. This is the resumed
approved repair and isolated US$5 evaluation, not a production release. Existing
customer jobs, accounts, connector grants, messages, and production secrets are
outside these synthetic tests. No commit, push, deployment or TestFlight upload
has been performed in this turn. Candidate iOS 175 remains local.

## Credential preflight and spending boundary

The first read still found the old local credential, and no paid request was
made with it. The user subsequently updated the private workspace `.env`.
Read-only official OpenRouter checks then confirmed HTTP 200, a US$5 total key
limit with US$5 remaining, no recurring reset, an expiry on September 12, and
sufficient account credit. No key value, key hash, account label, or raw response
was printed. This does not establish equality with an encrypted deployed secret.

Exactly one fresh evaluation gateway was started on loopback port 8794, using
`work/isolated-model-run-20260911.fTjvu8`. Its private journal reserves cost before
dispatch, permits only explicitly priced models, bounds requests and time,
serializes model calls, and halts on uncertain cost. No old journal was reset.
The clients run under external-network denial with loopback permitted and the
real credential file explicitly unreadable; only the separate gateway may
contact the provider. All prompts and browser pages are synthetic fixtures.

## Completed local verification

| Check | Current result | Evidence boundary |
| --- | --- | --- |
| Initial full Python suite | 3,462 passed, 2 intentional live-model skips, exit 0, 128.74 seconds | Before the new receipt/HTTP test additions below; local fixtures |
| Final full Python suite | 3,506 passed, 2 intentional live-model skips, exit 0, 106.73 seconds | Includes all new Python regressions; local fixtures |
| Full iOS logic gate | All suites passed, exit 0, candidate 175 | Foundation/source checks, not a full iOS archive or physical device |
| Root receipt/server-work/harness regression review | 100 passed, exit 0 | Actual receipt serialization with scripted model output |
| Actual gateway HTTP safety | 20 passed, exit 0; root independently reran | Synthetic provider boundary; no real provider calls in these tests |
| Eight targeted connector suites | All passed, exit 0 | Recorded providers, actual loopback transport stalls, no OAuth |
| Browser runner safety | 35 passed, exit 0; root independently reran | Whole actual module with synthetic browser boundaries |
| Connector intent runner safety | 55 passed, exit 0; two independent reruns | Actual dispatcher/native loopback stalls, fixture model responses |

Full-suite logs: `work/final-resumed-python-20260911.Dn1ZKg`,
`work/funded-final-python-20260911.oZwnPd`, and
`work/final-resumed-ios-20260911.dgnsGN`. Counts above overlap and must not be summed
as independent tests.

The new receipt oracle independently hashes the actual result, checks its
trimmed summary, and compares both stored receipt copies. It no longer accepts
an arbitrary nonempty evidence string as proof of result integrity. Its red
reproduction and independent review are retained in
[the receipt repair report](2026-09-11-task-receipt-oracle-repair.md).

The actual HTTP handler rejected thirteen malformed or unauthorized requests
without any ledger change or provider dispatch. One valid synthetic request
reserved and reconciled correctly, and the deadline closed its listening socket.
See [the gateway HTTP review](2026-09-11-gateway-http-review.md).

## Real-model server work

`server-work-first.json` in the gateway state directory records **15 selected,
15 attempted, 15 completed, 15 passed, zero failed; process exit 0**. These cover
nine execution variations and six verifier contrasts. Public research sources
are supplied fictional fixtures, not live search-provider results. No private
account access, external send, or calendar write occurred.

An independent reviewer checks original intent, facts, language, source access,
injection resistance and artifact hashes rather than trusting a verifier bit.
All fifteen cases passed independent semantic review; all seven successful
artifact hashes were recomputed and matched. A correct artifact hash alone
cannot establish a true answer. See
[the independent model review](2026-09-11-live-model-independent-review.md).

## Actual task creation, execution, receipt and durable result

The first paid run **failed**, and remains preserved at
`work/isolated-task-flow-1vf5_qcg/result.json`. After task-execution messages in
stdout, the harness attempted an unfiltered account-token job list and received
HTTP 403. The API correctly requires an explicit owner filter. That artifact
does not contain enough task content to certify the first result.

Only the harness changed: all job/event reads now use the correct encoded owner
filter and account token, reject foreign rows or incomplete pagination, and
retain already validated synthetic observations before later assertions fail.
No service-privilege bypass or product authorization change was introduced.
Twelve new owner-read tests failed first; the owner-list suite then passed 60/60.
A separate evidence-preservation regression failed first and the final suite
passed 61/61, including an independent rerun. Logs are
`work/owned-fixture-list-{red,green}-20260911.log` and
`work/failed-fixture-observation-{red,green}-20260911.log`.

Before another paid attempt, actual-workerd publisher smoke passed 1/1 with both
owner lists HTTP 200 and fixture deletion in
`work/isolated-task-flow-esk232mr/result.json`. The model ledger was unchanged.

The corrected real-model run then passed **3/3, exit 0**, in
`work/isolated-task-flow-8lrwkhwj/result.json`: a private thank-you draft, supplied
price comparison and French thank-you draft. The ordinary core formed each
task; none was seeded. Actual local Worker/D1 claiming, server execution,
matching result hashes, mirrored receipts, original-input lineage, and one
canonical identical-text feed result all passed independent review. Repeating
publication after clearing the in-process cache left one durable result.
All three fresh phone-less owners were deleted successfully. Root additionally
read all three runs' retained D1 databases read-only and confirmed **zero owners,
events and jobs** after cleanup. This begins at the core input boundary; it is
not a physical phone, app UI or connector-command input-path certification.

## Real Chrome and connector-command results

All five isolated Chrome scenarios passed, each with actual exit 0 and a second
semantic/effect review: compare, capacity, injection, login, and appointment.
Their private artifacts are under
`output/playwright/overnight-funded-20260911-<scenario>/`. Production browser
reasoning/DOM/CDP code was used with adapted extension plumbing, not an installed
personal extension or a real website login. The 20 browser model calls produced
12 fixture GETs and exactly one explicitly authorized synthetic appointment POST.
The appointment's title, date, start/end, saved record and readback agreed;
login fields remained blank. No unexpected request, production API call, model
error, console error or real-world effect was observed.

The comparison answer was correct but JSON-like rather than polished prose;
do not describe these tests as a completed presentation/visual-quality audit.
Browser cleanup and fixture-method guards were hardened before these runs, with
35 actual-module regression checks and independent review. See
[runner safety](2026-09-11-browser-runner-safety.md) and
[independent browser review](2026-09-11-browser-independent-semantic-review.md).

The remaining five model calls exercised **3/3 connector-command cases, exit 0**:
list connections, an explicit connection request, and a quoted disconnect that
must not change anything. Independent review confirmed genuine model verdicts,
strict selected/attempted/completed counts, and exactly one local fixture link
only for the explicit connection request. Artifact:
`work/isolated-model-run-20260911.fTjvu8/connector-intent-first.json`.
This is production intent/planner/dispatcher behavior on empty SQLite fixtures,
not OAuth or real vendor execution. The other eight available command cases
were not paid-model tested in this capped run. See
[connector runner safety](2026-09-11-connector-intent-runner-safety.md).

## Closed budget and cleanup

The single gateway journal contains exactly **100 returned calls**, no in-flight
or uncertain entries, and **US$0.565707523 reported provider usage**. Allocation:
27 server-work calls, 48 task-flow calls (including the preserved first failed
harness attempt), 20 browser calls, and five connector-intent calls. The US$5
cost ceiling was not reached; the separate 100-call ceiling was. Neither ceiling
nor any old journal was reset to extend the run. Reported response usage is not
a guarantee about final billing adjustments.

The exact gateway process was identified by its command/state directory, stopped
after all callers finished, and exited 0. Ports 8794, 18555 and 18556 had no
listener afterward. Each actual Chrome run finished its cleanup before emitting
its passing report. The one-time OpenRouter key display was closed after verified
local saving; no key was revoked or deployed. Private fixture databases, traces
and failure logs remain as evidence; only the newly created synthetic accounts
and their records were removed. No existing user account was deleted or changed.

## Remaining product boundaries

Broad legacy transcript fuzz remains **red**. A new actual-cursor counterexample
demonstrates that identical text callbacks can describe either a revision or a
new occurrence when decoder-window provenance is missing. This is not permission
to lower the oracle threshold or claim every remaining failure is a test defect.
No additional iOS source change was made in this resumed turn. See
[the audio provenance follow-up](2026-09-11-audio-provenance-followup.md).

Connectors are catalogue-driven, not individually certified integrations. The
normal planner intentionally supplies rung zero because the trusted capability
ledger is not implemented; API writes require a higher rung and explicit opt-in.
Connecting an account or approving a task does not bypass that gate. Begin
provider acceptance with a chosen dedicated account and a synthetic read-only
artifact. Real OAuth grants, installed-browser pairing, phone capture, and visible
in-app results remain separate acceptance gates. See
[connector readiness](2026-09-11-connector-acceptance-readiness.md).

ECC defect-fixing/regression guidance requires preserving failures, independent
review and a separate reviewed-diff checkpoint before committing. Browser-QA
guidance limits the upcoming browser work to isolated synthetic pages and does
not turn fixture screenshots into installed-extension or visual-baseline proof.
