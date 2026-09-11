# Harness acceptance: from local repair to a verified device

**Latest evidence (September 10–11):** the tester confirmed one real SendBlue
reply on the iPhone, and microphone-tagged build-174 inputs reached the backend.
These supersede the older SMS/install-pending notes below, but do not certify
the full device workflow. The latest [variation assessment and repair plan](../research/2026-09-11-e2e-variation-plan.md)
records fresh stress-test failures and the still-unpaired/unconnected account.
Current diagnostics UI is **Settings → Listening → Listening activity**.

**Release update (September 11):** connector deadlines and harness honesty fixes
are pushed at `c05d614a`; the API release was independently verified. The new
private TestFlight **1.1.1 (175)** is now available to the owner's existing private
group and the approved pilot, with the already-released 174 iOS behavior. The
experimental pending-speech repair is **excluded** after independent
review found increased callback cost and unresolved extra-word tradeoffs. Broad
cursor fuzz is still red; real device/connector acceptance remains outstanding.
See the [175 release ledger](../research/2026-09-11-testflight-175-release.md) for
the exact build, CI and Apple readback. Installation of **175 on the phone is
still unconfirmed**; update through TestFlight before recording new build-175
acceptance results. The funded key was verified in the capped
isolated run: 15 server-work cases,
three complete local task flows, five isolated Chrome tasks and three connector
intent fixtures passed real-model testing and independent review. This does not
certify actual OAuth or all live product paths. See the
[latest funded-verification report](../research/2026-09-11-funded-variation-verification.md) and
[approved-fixes checkpoint](../research/2026-09-11-approved-fixes-checkpoint.md).
The historical release notes below concern build 174, not the new release.

Historical September 10 release context (not the status of build 175):
The API and brain are deployed and verified; TestFlight **1.1.1 (174)** is
available to the approved private pilot and, after correcting its missing build
assignment, the owner's existing private group. The owner reports 174 visible
and updating; completed installation is not yet confirmed. Current evidence
and limits are in
[the release ledger](../research/2026-09-10-harness-release.md).

Before a new live session, use the latest verified build in the release ledger
and confirm that number on the phone. The later capped funded-model run
supersedes the old local HTTP 402 blocker; it does not certify every deployed
provider or authorize resetting an exhausted test budget. Do not repeatedly
submit messages while diagnosing provider failures.

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

## 2. Verify the latest release, this phone's access and installation

Use the [175 release ledger](../research/2026-09-11-testflight-175-release.md)
for the new private build. The following paragraph preserves the historical
174 handoff and the access issue to check for on every later build.

Full Xcode/iOS SDK is missing on this Mac. Foundation harness builds and the
actual engine's macOS-framework typecheck are not a full iOS application build.
For candidate `7968926e`, the actual committed simulator build passed CI, the
API and brain deployments passed verification, and the approved TestFlight
release completed as **1.1.1 (174)**. Do not upload again to diagnose a phone
still showing 172; first check its Apple account, tester/group access and update
availability. The owner's private group initially contained only 169 and 172;
174 has now been attached and Apple shows it as Testing. The owner reports the
174 update in progress; completed installation remains unconfirmed. For future
releases, another pilot group's
successful assignment is not proof of this particular account's access.

The following trigger rules are for future releases, not instructions to repeat
this completed release:

A qualifying push to `cloudflare-backend` touching `app/ios/**` or
`.github/workflows/ios-testflight.yml`, without `[ship]` in its commit subject,
runs the iOS logic gate and unsigned simulator compile. A backend-only push
does not satisfy that workflow's path filter. Do **not** manually dispatch
`ios-testflight.yml` as a build-only check: dispatch explicitly requests upload.
Do not push to or merge main. Recheck workflow triggers before any later push.

For a future candidate, require successful exact-commit CI and release approval
before uploading or deploying. Verify the actual resulting release identity:
Apple collision handling can change a source build number. Always distinguish
Apple availability from the version actually installed on the physical phone.

## 3. One consented, controlled live session

Agree the account, time window, harmless test inputs and permitted external
effects first. Do not reset an existing account or inject jobs to manufacture
success. In-app inputs can independently generate SMS, so authorize the send
before initiating even a greeting on a configured live account.

Do not use `proof/audit/live_reply_probe.py` unchanged as a zero-provider-send
canary. It temporarily clears its synthetic profile's phone, but answers remain
in a pending outbox; restoring the phone permits a later delivery sweep to send
them. Its constant `real_messages_sent=0` is not measurement. A genuinely
phone-disabled persistent fixture or an explicitly approved SMS session is
needed; never fabricate delivery state or delete outboxes to force a pass.

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
