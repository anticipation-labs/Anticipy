# Harness acceptance: from local repair to a verified device

This is the remaining acceptance sequence for the September 10 local candidate,
not a claim that production or the installed phone has these changes. Current
evidence and limits are in [the release ledger](../research/2026-09-10-harness-release.md).

## 1. Finish the local gate first

Use the network-denied commands in [Local development](LOCAL-DEVELOPMENT-TEJAS.md#offline-verification).
The ordinary iOS gate now includes the analyzer boundary, account-bound Stop,
queued callback/erasure and receipt-progression regressions. Two extra negative
control runs deliberately break temporary copies and require named failures:

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
  /usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)' \
  sh app/ios/Tests/run_analyzer_lifecycle_boundary_tests.sh --check-mutations
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
  /usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)' \
  sh app/ios/Tests/run_capture_lifecycle_tests.sh --check-mutations
```

These need this Mac's installed SDK path. They do not activate a microphone,
download speech assets, invoke a model, send a message or inspect an account.
Do not turn on `ANTICIPY_HANDS_LIVE` to eliminate the intentional model-test skips.

## 2. Compile, then release deliberately

Full Xcode/iOS SDK is missing on this Mac. Foundation harness builds and the
actual engine's macOS-framework typecheck are not a full iOS application build.
The next release gate is the committed simulator build in CI (or full Xcode
locally). The owner approved committing/pushing the reviewed named files and,
after CI passes, TestFlight distribution to the existing private pilot group.

A qualifying push to `cloudflare-backend` touching `app/ios/**` or
`.github/workflows/ios-testflight.yml`, without `[ship]` in its commit subject,
runs the iOS logic gate and unsigned simulator compile. A backend-only push
does not satisfy that workflow's path filter. Do **not** manually dispatch
`ios-testflight.yml` as a build-only check: dispatch explicitly requests upload.
Do not push to or merge main. Recheck workflow triggers before any later push.

Only after CI succeeds under that release approval: release the reviewed
iOS and relevant backend components, verify their identities, and confirm the
build actually installed on the phone. Source currently names 1.1.1 (174);
Apple collision handling can change an upload number. The last user-confirmed
installed build was 172, which does not prove this candidate is installed.

## 3. One consented, controlled live session

Agree the account, time window, harmless test inputs and permitted external
effects first. Do not reset an existing account or inject jobs to manufacture
success. In-app inputs can independently generate SMS, so authorize the send
before initiating even a greeting on a configured live account.

| Leg | Controlled test after release approval | Evidence required / failure boundary |
| --- | --- | --- |
| Physical audio | Say a harmless phrase, immediately turn Listen off; start again and repeat it. Also test pause/resume and a real interruption. | Each separately spoken phrase appears once, no stale session text, mic actually stops. Settings → Listening → “Find out what listening actually did” supplies structural timing/gap evidence. A finalization warning is failure, not a successful capture. |
| In-app answer | Type one approved greeting and wait; do not repeatedly resubmit. | Exact input id → stored answer → visible answer. A generic unavailable reply means the classifier path failed, even if HTTP and the queue are healthy. |
| SMS | Approve one message to the account's confirmed international-format number. | Exact answer → outbox → attempt → matching provider handle/status, plus handset receipt. `SENT`/accepted is not device delivery. An unconfirmed attempt must not be resent to force green. |
| Browser | Confirm the installed extension version, pair only the approved account, and use a harmless read-only page task. | Actual installed-extension execution and a matching visible result/receipt. The isolated geometry test proves click coordinates, not pairing, real login or all-site automation. |
| Connectors | Inventory the account's real connections and verify each required connector with a harmless read-only operation on agreed test data. | Owner, connection identity, granted scope and observed result must agree. An authorized sample write needs separate consent and a provider receipt; “connected” alone is not end-to-end evidence. |
| Privacy | Keep account-switch, stale callback and erasure races in local fixtures first. | Do not use “Forget this phone” or delete real pending speech just to reproduce a test. Any device erasure test needs explicit consent and a disposable account. |

## 4. Diagnose the first missing link; do not mask it

For an approved account/time window, inspect metadata only: exact ids,
decisions, timestamps and linkages. Never dump event `text` or raw logs as a
shortcut; other event types can contain private content there. New classifier
diagnostics use the exact input key `reply-diagnostic:<input-id>` and a closed
category/model-role/optional numeric HTTP status. SMS diagnostics live inside
the already-owned attempt and contain the same bounded category/status shape.

- No input event: inspect local capture, queue, authentication and transport.
- Input marked unavailable: read the new diagnostic for the correct model role;
  address the evidenced provider/configuration/budget/parse failure, then run
  one newly authorized test. Never guess or rotate a secret based on its presence.
- Stored answer absent from the app: inspect exact receipt identity and refresh.
- Unconfirmed SMS with no handle: preserve the no-duplicate fence. Absence of a
  receipt is not proof that a send never occurred. Do not blind-retry it.
- Accepted SMS with a handle: a separately authorized exact-handle status read
  can establish provider state; handset receipt establishes what the user saw.
- Connector/browser refusal: identify owner, scope, route or execution evidence;
  never bypass consent or enable an unverified write path to pass the demo.

Historical failures cannot acquire diagnostics retroactively. In particular,
the user's earlier unavailable answer and handleless unconfirmed SMS remain
unexplained until a controlled reproduction supplies new evidence.

Still intentionally unproven: every live connector, actual iPhone audio/model
timing, authenticated browser workflows and provider delivery. Pendant decoding
is disabled in the product and is not included in phone-audio readiness. A
missed negative SMS callback may leave accepted/unconfirmed status because
lookup reconciliation only upgrades confirmed delivery; adding negative-state
reconciliation requires an atomic delivered-preserving update. Older receipt
badges also depend on the existing bounded metadata window.
