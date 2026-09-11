# Anticipy task-variation E2E repair plan — 2026-09-11

## Scope and gate

User wants the app and harness working end to end across task variations and
cannot join a call. Work is on `cloudflare-backend` at `943cd79c`, never main.
This is a **large/cross-cutting** repair. The defect-fixing orchestration skill
requires a plan approval before implementation and a separate pre-commit gate.
The user approved this repair plan with “i approve all the fixes make it
perfect.” Local implementation and isolated model evaluation (at most US$5)
are now in progress. The separate reviewed-diff/pre-commit checkpoint remains.
No commit, push, release or deployment has occurred in this repair turn.

No phone call is needed for local repairs. Device and OAuth evidence cannot be
manufactured by a server-side test. Existing account data, pending speech, jobs,
provider attempts and one-use test journals must remain untouched.

## Fresh evidence, not a whole-product pass

| Layer | Measured result | Important boundary |
| --- | --- | --- |
| Python/local-D1 | 3,389 passed, 2 live-model skips; exit 0 | Local fixtures, not current real-model judgement |
| Default iOS logic | All suites passed; build 174 | No local iOS SDK or mounted SwiftUI/device test |
| Audio lifecycle | 68 + 169 checks and 21 mutation controls passed | Controlled recognizer callbacks |
| Extra cursor fuzz | **RED**: 5 unexcused losses in 10,000 CHURN sequences in seed-1234 30,000-schedule run | Not a measured physical failure rate; default gate excludes this test |
| Isolated cursor witness | **RED** against the actual production cursor | Newly inserted unsent word disappears after revised partials |
| API | All 44 registered test commands and typecheck passed | Recording providers/local SQLite |
| Browser extension | 84 suites passed | Includes mocks, not installed-extension proof |
| Real Chrome geometry | 2/2 passed | Isolated DOM/CDP, not complete reasoning/queue pairing |
| Extension package | All three ZIPs match source 0.18.1 | Installed and live-served versions remain separate |
| Local workerd LLM wire | 20 passed, 2 legacy-source checks skipped; exit 0 | Real workerd plus fake model provider, no paid call |
| Local workerd SendBlue selection | 14 passed, 1 failed; exit 1 | Failure is obsolete cross-carrier expectation of HTTP 200 from retired Twilio route; actual response is 410 |

Independent reports:

- `research/2026-09-10-e2e-audio-variation-review.md`
- `research/2026-09-10-e2e-browser-connectors-review.md`
- `research/2026-09-10-e2e-backend-harness-review.md`

Root's LLM wire log: `work/e2e-llm-wire-20260911.IXuRTC`. It ran under
external-network denial, loopback-only transport, dotenv/telemetry disabled and
real credential-file read denial. The runner removed only its freshly seeded
local fake-agent rows and stopped its own processes. Ports 8791/9797 were
confirmed no longer listening. The two skipped assertions refer to absent
legacy PocketBase hook source, not a successful live-provider assertion.

Root's SendBlue wire log: `work/e2e-sendblue-wire-20260911.Pu74v8`. The original
`TestSendblueInbound` selection includes `test_both_carriers_land_the_same_row_shape`,
which expects the intentionally retired `/sms/inbound` to accept a Twilio input.
It instead returned `410 messaging_endpoint_retired`. Preserve this failed run;
repair the obsolete test to assert retirement/no database effect rather than
re-enable a retired carrier or silently omit it. The other 14 cases passed,
including signatures, configured sender, empty/media/group handling, unknown/
ambiguous owner refusal, one durable row and duplicate-handle deduplication.
Only fresh local 555-number fixtures were used. The runner deleted its own
local fixture rows and new disposable SMS state directory; test evidence logs
remain. Ports 8792/8793/9391/9392 were no longer listening afterward. No actual
messages were sent and no cloud database was mutated by these wire tests.

## Live account readiness snapshot

An exact-ID/email identity guard resolved the consenting tester once. Read-only
D1 counts showed **0 paired browser agents, 0 connector rows, and 1 active job**.
The job was neither read for content nor modified. Pairing a browser to this
existing account can cause existing work to run, so do not casually pair it as
a status probe. Use a separate phone-disabled fixture for autonomous testing.

The first metadata read returned unavailable. A separate SELECT 1 succeeded,
required schema columns were present, and the subsequent owner-scoped count
read succeeded. No authentication, schema or provider outage was diagnosed
from that transient unavailable result. No messages or audio were read.

Earlier direct evidence remains narrowly valid: the tester confirmed receiving
one SendBlue reply, and six recent microphone-tagged build-174 transcripts
reached the backend and were processed. Those observations do not identify
every captured word, verify all task types, or supply missing connector grants.

## Approved task_list

1. **Connector liveness repair.** Add failing tests for stalled headers,
   stalled response body, release of failed per-owner session-in-flight state,
   and endless distinct pagination cursors. Introduce explicit finite transport
   and traversal bounds, abort actual pending I/O, and preserve safe diagnostic
   redaction. Never silently return partial account lists. Never retry an
   ambiguous write or treat a timeout as proof that nothing happened. Require
   all existing owner/permission/race tests plus an independent security review.
2. **Speech revision preservation.** Promote the concrete seven-callback
   witness into regression coverage; fix general cursor alignment/provenance,
   not particular words. Require multiple deterministic fuzz seeds, no lost
   newly spoken words, and all existing nonduplication/Stop/account-lease tests.
   Re-run the full iOS gate; any iOS source repair needs coordinated build-number
   changes and real simulator CI before release. Do not attribute this known
   fallback/partial-result issue to today's Analyzer test without evidence.
3. **Make evaluation fail honestly.** Reject unknown/empty case selections
   before credentials/network work; repair stale `_queue_job` overrides for
   the current `touches` contract. Record attempted/completed/passed/failed/
   skipped counts, exact source identity, first failure and actual process
   exit. A suite selecting zero cases must never pass. Preserve negative
   controls and historical failed evidence. Replace stale Twilio acceptance
   assertions with the intentional retired-route/no-effect contract.
4. **Run real-model task variations with isolated state/effects.** Reuse the
   strongest existing local Worker/D1 reply, server-work and real-Chrome
   fixture runners after reviewing their gateway/credential/budget setup.
   Current local model credentials must not be assumed equivalent to the
   funded Cloudflare secret. Proposed new evaluation spend ceiling: US$5,
   enforced by reservation before each call, with bounded calls/tokens/time.
   Use a bounded funded transport; stop at its declared cap and never reset an old reservation journal to force another
   attempt. No customer profile, inbox, calendar or phone is part of the rig.
5. **Exercise complete orchestration, not only single-hop fixtures.** Cover
   ordinary input → task formation → queue/claim → allowed hand → verified
   result → one durable reply through actual production functions. Retain
   stable input/job/receipt linkage. Separately label mocked provider boundaries,
   real models, real browser DOM, deployed services and physical UI evidence.
   A directly seeded job is queue-to-hand coverage, not brain-to-task proof.
6. **Deliberate release and remaining real-provider acceptance.** Present the
   reviewed diff/commit scope before commit. Verify precise build/deployment
   identities after any approved release. Then pair a chosen isolated browser
   account and test required connectors against agreed synthetic artifacts.
   Account selection and new OAuth grants remain user decisions; do not enable
   API write maturity gates to make a demo appear successful.

## Variation acceptance matrix

| Variation | Required observation |
| --- | --- |
| Greeting / paraphrase / multilingual private draft | Useful canonical answer, no invented task or external send |
| Research / comparison / changed source facts | Correct facts and sources; revised values supersede earlier ones |
| Missing information / ambiguous contact | Ask only for the missing owner choice; never invent it |
| Contextual yes / unrelated or quoted yes | Approve only the intended current workflow revision |
| Correction / partial answer | Preserve supplied changes and remaining unanswered questions |
| Cancel / already handled | Correct task cancelled; no late execution or unintended revival |
| Missing browser / disconnected app / login wall | Honest setup/needs-user state, never false completion |
| Provider timeout / malformed response / payment failure | Bounded failure, durable useful state and no blind write retry |
| Duplicate input / lost response / delayed delivery callback | One logical result and effect; exact-owner stable correlation |
| Prompt injection / false success banner | Untrusted content cannot change authority; completion needs evidence |
| Speech repeats / revised partials / Stop/restart | No new-word loss, replay duplication, stale-session or cross-account delivery |

First-attempt failures remain in the report even if a later repaired candidate
passes. No claim of all vendors, arbitrary tasks, perfect reliability, or App
Store submission readiness is made by these tests.
