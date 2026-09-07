# Native iPhone calendar repair — 2026-09-07

## What was disconnected

`app/ios/Anticipy/Backend/CalendarHandPolicy.swift` could validate a structured
calendar plan, but no EventKit writer consumed its decision and the phone poll
never claimed `device_calendar` jobs. There was a second independent blocker:
the app's generic approval wrote approval and release together, while
`migration/workers/src/policy/research_lane.ts` deliberately rejects that
combination on the native lane. A calendar writer alone would not fix delivery.

## What changed

- `NativeCalendarExecution.swift` implements a store protocol and actual
  write/undo execution, with exact title, start, end, calendar and minted URL
  marker readback. It also builds canonical claim, approval-record and completion
  fields, preserving the server's approval decision.
- `NativeCalendarHand.swift` connects the protocol to EventKit and owner-token
  backend requests. The approval record is first written while the task remains
  held; a separate release follows. Both use a fresh server ETag. Claiming also
  uses If-Match, preventing two devices from winning the same task concurrently.
- `AnticipyApp.swift` invokes the native hand asynchronously after an authenticated
  refresh and uses the calendar-specific two-write approval handoff. Account,
  token and backend identity are rechecked before effects. Native task polling
  pages its own outstanding queue, independently of the newest thirty home cards.
- The unused contact extraction regex block in `approvalFields` was removed.
  `confirm` routes ordinary typed answers through `AnswerRoutePolicy.toTheBrain`;
  calendar execution never interprets human wording or fills missing dates.
- Both build declarations are 166, and both new production sources are manually
  registered in the Xcode project. No xcodegen or device signing was used.

Existing app calendar consent and current OS full access are both required.
Polling never surprises the owner with a permission dialog. Missing permission
or invalid plan data leaves a visible held task rather than claiming completion.
No calendar notes, attendees, locations, phone numbers or email addresses are
read by the executor.

## Recovery and limits

An existing matching marker prevents a duplicate save. A duplicated marker or
an event whose title/time changed is held, never overwritten. Interrupted work
may verify an existing write while its own lease remains valid; it cannot replay
an effect. Expired leases and failed readback move to `needs_user` with
`effect_uncertain=true`. An undo whose marker is absent before removal cannot
claim success: the event might have moved outside the approved lookup window.

The initial write uses the iPhone's default writable calendar. An existing marker
is resolved back to its original calendar if the default later changes. Local
calendars are explicitly reported as local-only. This does not establish that a
remote CalDAV server preserves custom event URLs, or that a calendar is synced
to a particular web account. That remains a physical-device/provider check.

## Evidence

- Unsigned **iOS Simulator build succeeded**. Log:
  `work/audit/native-calendar-build.log`.
- **27 executable Swift checks** cover save/readback, duplicate prevention,
  changed-event refusal, marker loss, interrupted effects, undo ambiguity,
  owner isolation, lease fields and bound receipts.
- **9 Swift-to-Worker checks** feed bodies emitted by the real Swift transition
  code into the actual Worker lane/workflow policies. They prove the combined
  approval/release is rejected, separate approval then release is accepted,
  native claims and receipts are accepted, and wrong-lease/browser claims fail.
  Run `sh app/ios/Tests/run_native_calendar_execution_tests.sh`.
- **Real EventKit simulator proof passed**, using a newly created simulator and
  a fixture-only calendar. The production EventKit adapter saved and read back
  an event, retried without duplication, verified from a new store instance,
  removed by its own marker and independently checked absence. The fixture
  calendar and isolated simulator were removed. Evidence:
  `research/overnight-2026-09-07/native-calendar-simulator.json`.
- Reproduction: `sh proof/audit/run_native_calendar_simulator.sh`. This requires
  the installed iOS 26.5 runtime and an Apple Silicon Mac. It pre-grants calendar
  access only on the newly created simulator, so it does not test permission
  prompt UX. It never uses the developer's existing simulator or calendars.
- Full iOS logic gate: **all suites passed, exit 0**,
  `work/audit/native-calendar-full-ios.log`. The first attempt was invalidated by
  a source edit during compilation; the fresh run after source freeze passed.
  Its final leg recognized build 166 as newly bumped from 165. The source and
  build number must still land together in the parent's path-limited commit.

This is an implemented and simulator-verified native executor, **not yet a
physical-phone or TestFlight verification**. No production calendar was changed,
and no paid model call was used.

Apple API references checked:
[EventKit store](https://developer.apple.com/documentation/eventkit/ekeventstore)
and [full calendar access](https://developer.apple.com/documentation/eventkit/ekeventstore/requestfullaccesstoevents(completion:)).

## Subsequent delegated text-status UI repair

The parent requested a small factual delivery badge after reviewing the new
backend reply outbox. `ReplyTextDeliveryPolicy.swift` reads notification metadata;
`ReplyTextDeliveryBadge.swift` displays it beneath actual assistant replies and
question cards in `ConversationDashboard.swift` and `ContentView.swift`.

The join requires all three of: the current owner, `goal == message.id`, and the
exact `reply-sms:<message.id>` or `reply-outbox:<message.id>` correlation key.
Old job notifications cannot become a new question's receipt. Notification and
outbox records are fetched separately from the capped conversation feed; neither
request delays displaying the answer. The asynchronous callback rechecks account,
token and backend before repainting, and sign-out clears the visible statuses.

| Recorded fact | Badge |
|---|---|
| Pending outbox, no attempt record | Text queued |
| Provider accepted | Text delivery pending |
| Explicit delivered state | Text delivered |
| Attempt outcome unknown | Text not confirmed · reply is saved here |
| Explicit failure | Text delivery failed · reply is saved here |
| Explicit skipped/mock | Text not sent · reply is saved here |
| Missing, unreadable or unknown metadata | No delivery claim |

The existing quiet-hours task caption is unchanged. Acceptance is never called
delivery. The UI does not invent a delivery callback: the backend must actually
record `sms_delivered` before that badge appears.

After this additional source change: **17 delivery-policy checks passed**, backend
error-message tests passed, account-race tests passed, dashboard tests passed,
app-reply write tests passed, and the complete unsigned simulator app build
passed again (`work/audit/reply-text-calendar-build.log`). These checks occurred
after the earlier full-gate pass; CI should run the full gate on the final commit.
