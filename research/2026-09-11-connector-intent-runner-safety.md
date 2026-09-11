# Connector intent runner safety — 2026-09-11

Tom's harness-only change, under the parent's approved local-fix scope. Product
source, accounts and provider semantics are unchanged. No real model/gateway
token, live API, OAuth, SMS, connection, commit or deployment was used here.

## Scope and preserved behavior

`proof/audit/run_connection_commands.ts` retains all eleven original fixture
messages, prior context, expected intent outcomes and serial execution. It still
uses the production dispatcher/query/matcher with the real SQLite-backed D1
schema and an isolated fixture catalogue. Its owner has no phone or connected
provider account. The model remains the production connector default,
`anthropic/claude-sonnet-4.6`; the harness does not change model meaning or add
vendor-specific product behavior.

This is a security-sensitive standard-sized harness change: explicit input,
credential-file, filesystem-evidence and fetch boundaries, plus tests. The
regression-first orchestration skill guided reproduction and the independent
review handoff. Commit/deployment remains outside this lane.

## New boundaries

- Require `ANTICIPY_AUDIT_STATE_DIR` to name an existing absolute private directory
  and `ANTICIPY_AUDIT_GATEWAY_URL` to name an explicit HTTP loopback chat endpoint
  with a port. No legacy state/port fallback, credentials/query/fragment,
  ambiguous numeric host, or external URL is accepted.
- Accept a bounded simple evidence label, optional unique known `--cases` list,
  and integer `--max-calls` from 1 through 64 (default 32). Each selected case is
  attempted once; production model questions retain their existing behavior
  within that shared call ceiling. The gateway's own dollar/call/lifetime gates
  remain authoritative and are not reset or edited.
- Read only that directory's private, same-user regular `gateway-token`, with
  no-follow open and bounded single-line HTTP-token validation. No `.env` loads.
  Invalid CLI inputs are rejected before token access or product imports.
- Reserve a fresh mode-0600 report with exclusive creation before model work.
  Persist selected/attempted/completed counts and partial failures through the
  retained descriptor. An existing report is never overwritten and a failed
  label is not automatically rerun. An interrupted partial JSON file may be
  incomplete, but still exists and blocks reuse; it cannot masquerade as a
  completed passing report.
- Intercept only the fixture catalogue's exact toolkit GET shapes and the
  existing OpenRouter chat POST shape. Catalogue replies are local fixtures.
  The sole native fetch goes to the approved loopback gateway with the local
  gateway token; original headers are not forwarded and redirects are refused.
  Unknown provider execution/session/account, API or SMS requests fail closed.
- Charge the local call counter before native invocation. Unexpected requests,
  cap exhaustion, cancellation, uncertain transport outcomes or malformed model
  response envelopes latch a failure, even if product code catches the error.
  No retry is added and later cases stop after transport failure.
- Bound headers and body together to 95 seconds per request, preserve upstream
  cancellation, cap actual streamed response bytes at 4 MiB and request bytes
  at 900,000. Actual native loopback stall tests confirm abort cleanup. This is
  a per-request bound, not a claim of a 95-second whole-run deadline.
- Suppress raw product logs while dispatching synthetic cases and print only
  fixed case/outcome/count projections. Exceptions, provider body, token and
  generated link values are not printed or written into the report.
- Require exact selected results, intended local link count, unchanged expected
  fixture job count and no connections/agents. A transport-successful response
  with no actual model message cannot pass. The dispatcher's explicit
  `left alone (no-verdict)` outcome is not counted as a passing negative-intent
  case; a safe product non-action is not proof that classification worked.

## Regression evidence

- Initial pre-repair suite: exit **1** at module import because the old script
  performed CLI/token work on import and exposed none of the new testable
  boundaries. Recorded in `work/tom-connector-runner-red-20260911.log`; this is
  not represented as 50 individually executed red assertions.
- Envelope-specific red: four actual HTTP-200 malformed/empty-message cases
  failed their refusal assertions before the envelope guard was added.
  `work/tom-connector-runner-empty-response-red-20260911.log`, exit **1**.
- Real-dispatcher oracle red: `ordinary-greeting` with a scripted model
  `no-verdict` returned overall success before the availability predicate. The
  assertion expected exit 1 and observed 0. Along with the four envelope cases,
  that run had five failures: `work/tom-connector-runner-no-verdict-red-20260911.log`,
  exit **1**.
- Final focused run: **55 tests passed, 0 failed, 0 skipped, exit 0** in
  `work/tom-connector-runner-final-20260911.log`. Includes real native loopback
  header and body stalls, body cancellation, invalid destination/selector/token,
  HTTP-error privacy, call-budget latching, actual dispatcher success, consumed
  label and partial-failure evidence controls.
- Existing `connection-dispatch.test.ts`: actual exit **0** in
  `work/tom-connector-runner-dispatch-20260911.log`.
- Worker TypeScript project: actual exit **0** in
  `work/tom-connector-runner-api-typecheck-20260911.log`. The root audit script
  itself is runtime-checked by the focused Node suite; the Worker project
  typecheck does not claim to include this separate audit file.
- All runs used scrubbed environments, dotenv off, npm offline and macOS
  external-network denial with loopback allowed. No paid call was made.

## Reviewed invocation shape (parent only after independent review)

Run from the repository root with the parent's existing gateway directory and
gateway URL explicitly supplied through the two environment names above:

```sh
node --experimental-strip-types proof/audit/run_connection_commands.ts FRESH_LABEL \
  --cases list,ordinary-greeting,quoted-command --max-calls 8
```

No literal private state path or token is included here. Use the same funded
gateway, not a newly created budget. This measures model intent and fixture
database effects only; it is not an OAuth test, real account read, real
disconnection, browser task or full connector acceptance.

## Frozen files for independent review

| File | SHA-256 |
| --- | --- |
| `proof/audit/run_connection_commands.ts` | `0a341c9c2dd02421b78ada7cc49e1429cf5fbb35f9c82726ec8d3e9960d93504` |
| `proof/audit/run_connection_commands.test.ts` | `e4f7fceb1d964c8b1c88b1f75a56298ea492c92f7e29156f368a266031c83cc9` |

Metadata reviewer independently checked the exact frozen hashes and reran all
55 focused tests under external-network denial with loopback allowed: actual
exit 0, no source edits or paid calls, no blocking finding. Root independently
reviews the patch and owns any funded execution.

Implementation references: Node's signal composition/cancellation API and
exclusive/no-follow file-open flags; no dependency was added.
[AbortSignal documentation](https://nodejs.org/api/globals.html#abortsignalanysignals),
[file-system flags](https://nodejs.org/api/fs.html#file-system-flags).

## Independent review of the parent's paid result

Tom subsequently read only the final artifact at
`work/isolated-model-run-20260911.fTjvu8/connector-intent-first.json`; no gateway
token, raw request traces, account data or additional model calls were accessed.
Artifact SHA-256:
`e5132ccd380da77016a5a9cf1d5c3e6927830ce1a889c9015891db01d996fb98`.
The current wiring source hash matches the artifact's
`45546271274a05d1deeb6208732c28183c05abd7ee9136f6fd037c89b6b81db8`;
the frozen runner/test hashes above still match current files.

| Exact selected case | Observed intent | Local links | Local replies | Model calls | Review |
| --- | --- | --- | --- | --- | --- |
| `list` — asks what apps are connected | `list_connections` | 0 | 1 | 1 | Correct list intent against the empty synthetic owner |
| `connect` — explicitly asks to connect Zellibrix for team notes | `connect` | 1 | 1 | 3 | Correct local authorization-link preparation; OAuth was not performed |
| `quoted-command` — quotes a disconnect instruction while explicitly asking to leave connections alone | `not_for_us` | 0 | 0 | 1 | Correctly left connection management untouched; this dispatcher does not itself prove the requested explanation was answered elsewhere |

Summary is internally consistent: three selected in the original order, three
attempted once, three completed, three passed, five model calls out of the five
allowed, all `model_verdict_available` values strictly true, `failure=null`, and
no HTTP failure. The original fixture text/prior context and expected outcomes
match the source. No case is being excused as a cap failure or silently omitted.

The reviewed fetch boundary supplies only local catalogue fixtures and forwards
only model POSTs to the parent's metered loopback gateway. Its passing predicates
also require zero connected accounts/agents and no extra jobs. This supports
**model-intent and local fixture-effect PASS**, not a real connected-account read,
send, OAuth completion, disconnection, browser execution, or all-connector claim.
The artifact omits generated reply text, so this is not a separate prose-quality
assessment of the list/link reply.

The parent independently reported actual process exit **0**, five connector
calls, and closure of the shared gateway after exactly 100 returned calls with
no uncertainty. Tom did not read that gateway's private ledger or independently
recount the other 95 calls. The five-browser output assessment belongs to Ben's
separate independent semantic review. No further calls were requested or made.
