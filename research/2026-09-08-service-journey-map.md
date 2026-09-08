# iOS → service → owner-result journey map

Date: 2026-09-08. Scope: source trace for the replacement “Anticipy in real life” guide, on the current `cloudflare-backend` working tree. Sections 1–5 record the initial read-only findings; section 6 records the subsequently authorized, bounded repair and local evidence. Existing concurrent patches are preserved. This is not a deployed-build attestation: no credentials were read, no real provider calls were made, and no live data was queried. The parent agent owns the iOS baseline and deployment decision.

## What reaches real implementation

The phone has production callers for connected-app discovery/OAuth, contextual task replies, approval/cancellation, and native calendar execution. The backend implements owner-scoped records, connection storage, provider calls, delivery attempts, and result records. Those legs must not be collapsed into “it works”: discovery is not OAuth completion, OAuth completion is not authorization to write, provider acceptance is not delivery, and a delivered question is not proof that a later “yes” approved its newest revision.

The most important confirmed gap at initial inspection was SMS approval's missing presentation identity, now repaired and tested locally in section 6. Two additional product gaps remain: the missing re-planning bridge after connecting an app for an existing browser-lane task, and the deliberately closed API-write maturity gate.

## 1. SendBlue inbound, outbound, and delivery

| Journey leg | Concrete production path | Owner/auth/state/evidence |
| --- | --- | --- |
| Phone app writes a reply | `AnticipyApp.swift:2976` → `writeAppReply` at 3291 → `AnticipyBackend.pushEvent` at 743 → `/api/collections/events/records` | Account Authorization; the record guard scopes the event to that account. An answer to a task card carries `reply_to_job_id`, `workflow_version`, `question`, and `goal` in event context. Stable external IDs support uncertain-write readback. |
| SMS enters | `migration/workers/src/index.ts` → POST `/sms/sendblue` → `routes/sendblue.ts:74` | Requires configured webhook secret and matching `sb-signing-secret`. Body must be an object. Wrong deployment destination is rejected when its from-number is configured. Group messages and empty/media-only replies are ignored, not passed to a model. Provider handle is the inbound idempotency key. |
| Resolve actual sender | `api/sender.ts:90`, `landInboundText` at 233 | Canonical owner-profile phone wins, including explicit revocation. Legacy account phone is only a fallback where the profile permits it. Ambiguous identity is not resolved by picking a row; storage/routing uncertainty returns retryable failure. Saves owner-scoped `sms_reply`, sender in `goal`, provider handle in `external_event_id`. |
| Consume durable inbound | `brain/worker.py:4334` `handle_inbound` → `connection_command` or `Conversation.on_reply` | SMS canonical phone is re-read before claiming; a revoked/changed sender cannot operate that account. App replies rely on the authenticated event writer instead. Connection commands have their own effect/retry fence. The normal conversation sees the original owner words. |
| Save response before sending | `brain/reply_delivery.py:35` `publish`; installed by worker bootstrap near 5081 | Owner checked; exact `reply:{incoming_event_id}` message and `reply-outbox:{message_id}` outbox are persisted/read back before provider contact. Outbound app text survives absent phone/transport. |
| Send task question | `brain/task_delivery.py:7`, `publish` at 46 → the same ReplyDelivery | Question identity currently hashes job ID, workflow version, status, and question. Before sending, current job owner/status/version/question must still match. Superseded pending questions are not sent. |
| Make one provider attempt | `brain/reply_delivery.py:80`; `brain/sendblue_arm.py:255` | Re-read canonical phone; optional final transport check; uniquely insert `reply-sms:{message_id}` notification attempt first. SendBlue credentialed API call returns handle/status. Accepted remains `sms_accepted`; ambiguous request/response remains `sms_unconfirmed` and is not blindly resent. Local/pytest/rig safety checks live in the transport. |
| Receive provider receipt | `routes/sendblue.ts:117` | Outbound receipts are not owner speech. Authenticated DELIVERED/READ advances exactly one matching persisted provider handle; ERROR/DECLINED records failure without downgrading an already-delivered attempt. No match or multiple matches grants nothing. |
| Recover missing receipt | `brain/reply_delivery.py:164` `reconcile_receipt` | Throttled read-only provider lookup for recorded accepted/unconfirmed attempts, exact handle and owner-linked message; positive terminal evidence only. No resend. |
| Show actual status | `AnticipyBackend.swift:917` plus `ReplyTextDeliveryPolicy`/task delivery policy | The phone independently reads owner-scoped delivery metadata, not just the capped conversation feed. A task question's receipt belongs to that question revision, not whichever revision the card now displays. |

### Delivery coverage and limitations

- `SendblueArm.status_callback` is only set from `SENDBLUE_STATUS_CALLBACK`; there is no constructor fallback URL. A provider dashboard webhook may be configured separately, but this trace did not inspect it. Receipt lookup is a distinct recovery mechanism, not proof the callback is configured.
- Brain task questions and normal chat replies use the shared durable reply ledger. The actual `/worker/connection-command` dispatcher also wraps its response in this ledger (`connections/dispatch.ts:106`); it is not the legacy/direct `wiring.ts` delivery callback. Other direct Worker sends in `connections/nudge.ts`, `connections/wiring.ts`, and `routes/connect_auth.ts` call `sendText` outside that ledger. They have their own nudge/code state, but the SendBlue receipt handler only correlates `reply-sms:` attempts. It cannot establish delivery of those direct sends merely because the provider returns success.
- Some job result/stall notices still use separate notification-attempt records (`worker.py:2400`, 2524, 2967–3008). Do not call all message delivery uniformly reconciled.
- The receipt handler's log/response still says “ignored status update” even when it updates a delivery attempt. That is misleading observability, not proof of lost receipt handling.
- An early callback can arrive before the sender saves its provider handle and be unmatched. Polling can recover a saved handle later. Lost handle persistence remains uncertain; it is not license to send again.
- No real inbound text, outbound delivery, callback, or handset receipt was proven in this trace.

## 2. Exact task approval and correction

### Existing paths

`AnticipyApp.confirm` selects a path through `AnswerRoutePolicy`: a typed answer goes to the same brain as SMS, while an explicit approval tap builds structured approval for the displayed plan (`approvalFields`, `AnticipyApp.swift:2779`). Cancellation removes authority through `cancellationFields` at 2943. A fresh retry creates a new request rather than rewriting failed history.

The generic backend writer is `AnticipyBackend.setJobFields` at 1049. It verifies HTTP success, but does not send an ETag. Native-calendar approval is stronger: `NativeCalendarHand.approveAndRelease` reads the exact version/scope and ETag, writes held approval, reads it back, and releases with a fresh ETag.

Backend `policy/workflow_guard.ts:280–525` checks the embedded and column copies agree, immutable owner/plan identity, legal transitions, version increases for changed scope, approval bound to version/scope, and running lease possession. `api/records.ts:566–658` offers real atomic compare-and-set through `If-Match`, including persisted authority fields in the SQL UPDATE predicate. It is optional: a caller that does not send it does not acquire its protection. A legacy row with no workflow ID takes an explicit guard compatibility escape hatch (`workflow_guard.ts:285`).

### Reproduced pre-repair SMS “yes to a presented revision” defect

1. `Conversation._classify` (`brain/conversation.py:1376`) reasons over owner words, recent thread, and current pending/open jobs, then names job IDs. It does not select immutable presentation IDs.
2. SMS gets no `reply_context`: its inbound event `goal` is the sender phone. Explicit app task-card replies do carry context; `_on_reply` at 475 pre-checks job ID/version/question/goal before the model call.
3. `_thread_from_record` at 1238 includes saved `anticipy_text` regardless of SMS delivery state. An app-visible but SMS-unsent/failed question can therefore look like something said in the SMS conversation. Reconstruction discards message/revision identity.
4. `_release` at 1680 fetches the *current* selected job and calls `approve_plan(... expected_version=workflow.version ...)` using that newly fetched version. This is not a comparison to the version the person was shown. `_requeue` at 1080 and the needs-user amendment branch have the same snapshot concern.
5. `_flip` at 2023 writes without `If-Match`. Even the explicit app context pre-check can become stale during model/network awaits. Ordinary guard checks reject some stale updates, but they do not replace an atomic expected-snapshot write.

Concrete counterexample: version 2 is texted, another channel revises it to version 3, and the owner answers the old text “yes.” The classifier may select the same job ID; `_release` fetches version 3 and approves it. Structural approval correctly binds to version 3 **after the wrong referent has already been chosen**.

### What the durable ledger can and cannot establish

The useful existing chain is:

```text
reply_outbox.text = task question snapshot
    → reply_outbox.goal = anticipy_text.id (exact rendered words)
    → notification_status.goal = that same message id
    → external_event_id = reply-sms:<message id>
    → provider_id + authenticated delivery result
```

This supports a small general fix, but the current snapshot has no goal, canonical plan ID, scope digest, effect key, or recipient binding. `updated` is processing time, not an authenticated provider presentation time. Delivered is evidence a handset received a message, not proof of which of several questions the owner meant. The current inbound contract also does not consume a provider quoted-message reference. It would be wrong to fabricate that capability or choose “the latest question” with a recency rule.

Minimal proposed seam:

1. Extend task-question metadata with immutable owner/job/plan/version/scope/effect/goal identity; retain exact rendered message and actual delivery attempt/recipient identity. Reuse the outbox, not a second message queue.
2. Supply the meaning model with actually delivered, owner/channel-scoped presentation candidates, their immutable IDs, exact words, and current task context. Let it select the referent(s), clarify ambiguity, or interpret a genuinely new request. Do not replace natural language understanding with a “yes” list.
3. Before granting authority, structurally require selected presentation identity to match the current canonical task. Carry the expected record/ETag through release, answer, and amendment into an atomic write. A current-job re-fetch must never silently substitute a newer version.
4. Missing/uncertain proof, stale scope, another owner, or multiple plausible referents must produce a truthful clarification and no task release. Legacy records with no binding do not magically become bound.
5. Test old delivered question → correction → “yes”; unsent/failed newer question; two pending questions; duplicate/delayed receipt; receipt read failure; owner/phone change; correction during classifier await and during final write; explicit app-context parity. Assert both unchanged task authority and the resulting owner-visible clarification.

Existing `tests/test_reply_delivery.py:221–246` proves task question sharing and pre-send supersession locally. It does **not** alone prove that later SMS approval uses the delivered revision. The subsequently added regression evidence is in section 6.

## 3. Connected apps / Composio

| Phone or service caller | Route and authority | Downstream state / result |
| --- | --- | --- |
| Settings and onboarding list/discovery | `ConnectedAppsClient.swift:170–243` → authenticated `/me/connections`, `/catalog`, `/signals`; `routes/connections_api.ts:1610` resolves owner from session | `handleList` at 733 reads only that owner's real connections; catalog uses provider metadata. Unknown storage/provider state is not an empty successful list. |
| Explain permissions and ask to connect | client `/sentences` and `/link`; model + real catalog | `SettingsHomeView.startConnect` and onboarding present disclosure through `ConnectSession`; only a fresh affirmative tap opens the handoff. URL must be Anticipy's allowlisted connect host. |
| Browser OAuth start | `/c/<token>` and `/c/<token>/go`; `connect.ts:1292`, `connect_auth.ts` | Single-use stored link binds owner/toolkit; token alone is not a user credential. Account session or link-scoped phone-code session is required. The provider URL is created on the server. |
| OAuth completion | `/c/<token>/done`; `connect.ts:1694` | Provider response is checked for the same owner/toolkit; callback success text alone is not proof. Persist connection with writes OFF. Store failure does not become a connected success screen. |
| Lost/slow callback | `connect.ts:2773` → `connections/wait.ts:277` under `ctx.waitUntil` | Bounded polling checks real provider account identity and uses the same connection write. `CONNECT_WAIT_MS=0` disables this backup explicitly. |
| Return to phone | `anticipy://connected/...` → `AnticipyApp.swift:215` → `ConnectSession.handleCallback:353` → `ConnectHandoff.parseDone` | Opaque attempt, toolkit, lifetime, and current owner bind the callback. A deep link is a hint, not an account row. Settings rebuilds/re-reads the server list (`SettingsHomeView.swift:177`); onboarding advances its connect queue. |
| Toggle writes / disconnect | client `/writes`, `/disconnect`; route handlers at 931/1007 | Owner-scoped live row checks and conditional writes; provider revoke and local deletion are distinct outcomes. Partial disconnect is reported rather than erasing an unrevoked account from the UI. |
| Expiration callback | `routes/connections_webhook.ts:679` | Signed/timestamp-checked provider webhook marks the exact connection as needing reconnection. This is not the successful OAuth-completion route. |
| Text “connect that app” | worker `/worker/connection-command` → connection dispatch / `connections/wiring.ts` | Service auth plus stored inbound event owner, contextual model command, durable dispatch/effect fence, current phone checked before outbound. No blanket writes consent is inferred from connection consent. |
| Browser task missing access | `worker.task_access_offer:1241` → `/worker/task-access` → `connections/task_access.ts` | Service token, owner-scoped stored job/source/thread, actual catalog and connections. Model can offer a specific account the owner identified; it does not guess an account from “my calendar.” Offers only, no private data access or task release. |
| Execute an API step | `brain/hands.py` at mint → `/hands/api/connections` and catalog → `worker.run_api_jobs` → `/hands/api/run` | Owner-scoped service routes, claimed current workflow, catalog/effect checks, connection writes gate, provider execution, persisted outcome. Read data continues to synthesis; uncertain writes park instead of replaying. Existing stale-plan patch rejects goal/source/owner/version mismatch and rechecks immediately before provider dispatch. See `2026-09-08-api-connection-route.md`. |

### Missing bridge and intentionally closed paths

- `connectDeps.onConnected` is `writeConnection` (`connections/wiring.ts:435–480`). It records the connection and nudge state. It does not re-plan a waiting job. The iOS deep-link path refreshes connected-app UI, not task execution.
- The regular hand chooser is invoked by `anticipy_core.py:1084` during job minting; `worker.task_access_offer` only asks about access. No source call was found that moves the *already queued* browser task to a freshly planned API lane after OAuth. Therefore “connect this app and this waiting task continues without Chrome” is not yet a proven product path. Minimal fix is an owner-scoped resumable task/access relationship and a fresh model hand plan against the current authorized task after verified connection; not a blanket callback queue flip.
- `brain/hands.py:1192` always builds context with `rung=NO_LEDGER_RUNG` (0); `_floors:550` requires API write rung ≥3 as well as `writes_enabled`. Planner-generated API writes are currently routed to browser despite the settings switch. Do not remove that gate merely to make the demo green: a real capability/authorization policy and write receipts must replace it deliberately.
- A successful connection has reads available to the API planner; it grants neither arbitrary writes nor guaranteed compatibility with every requested action. Empty catalog, unknown connection state, or stale API plan yields truthful fallback/hold, not a fake success.
- The connected-app UI and callback routes are real callers, not dead showcase screens. The missing leg is task continuation after connection, not OAuth UI existence. All actual provider/OAuth/revocation behavior remains live UNPROVEN here.

## 4. Native calendar from the iPhone

`AnticipyApp.swift:1367` invokes `NativeCalendarHand.run` from the signed-in refresh loop. This is a real device executor, not the Chrome/calendar web UI. The helper's pending-job query paginates independently of the 30-card feed and rejects other owners/lanes.

`NativeCalendarHand.swift:23` approval requires current account, exact workflow version/scope, and ETag. `run` at 49 requires the app's calendar grant, operating-system permission, typed device-calendar declaration, and a writable target. Queued jobs are claimed with a UUID lease and ETag, then read back. Account, permission, claim, version, and scope are revalidated before the non-await EventKit effect.

`NativeCalendarExecution.swift` uses an operation marker and exact calendar/title/time evidence. A create is saved then read back; completion requires exactly one matching event. Recovery of an already-running task verifies without repeating save/remove. Undo targets the exact marker/calendar record; absence before an unproven undo is not proof that this executor removed it. A missing/uncertain receipt parks `needs_user`/effect-uncertain rather than declaring success or blindly retrying.

Result fields and receipt are persisted to the job with the claim/ETag, then the normal owner-scoped job/feed/result path exposes them. Permission refusal produces an actionable question; no iPhone heartbeat is invented from the browser agent table. Worker `report_unclaimed_device_work` describes device-lane waiting rather than asking the owner to open Chrome.

Local test surfaces exist in `app/ios/Tests/CalendarHandPolicyTests.swift`, `NativeCalendarExecutionTests.swift`, and `migration/workers/test/native-calendar-wire.test.ts`. Their evidence is not a real iPhone permission dialog, actual EventKit event, TestFlight build, or retained device receipt. Those remain UNPROVEN in this trace.

## 5. Verification and next smallest work

1. Repair presentation-bound authority first. Preserve contextual understanding and general new-request behavior; do not turn all SMS into a guessed task approval. Prove both no unintended task release and a visible owner response.
2. Add an integration proof of original task → access offer → OAuth completion → fresh current-plan routing → receipt/result. Decide explicitly whether that capability is API reads only or includes a separately authorized write path.
3. Reconcile direct connection/nudge/code sends with durable provider acceptance/delivery evidence where product copy relies on delivery. Do not rerun an uncertain send merely to obtain a green indicator.
4. For real demonstration readiness, run the phone build against the intended non-production test owner and retain exact event/job/connection/receipt identities. Exercise multiple natural conversations, changed mind, app closed, browser absent, reconnect failure, and delivery uncertainty. A passing helper suite cannot substitute for those journeys.

No deploy, environment mutation, app-code edit, or live/provider request was performed during the initial mapping phase.

## 6. Authorized bounded repair — local evidence, not a live shipping claim

After the iOS baseline passed, the parent authorized fixing the presented-revision defect. Source changes are confined to that service/approval seam and its prerequisites:

- `brain/reply_authority.py`: one independent, four-state model question selects which delivered presentation(s) the owner means. The model does not grant authority. `selected`, `none`, `ambiguous`, and `unavailable` remain distinct; only exact supplied presentation identities can progress. No yes-list, recency selection, or phrase rule was introduced.
- `brain/task_delivery.py` now binds question metadata to owner, job, plan, version, goal, scope, effect, status, and question. `brain/reply_delivery.py` retains a hash of the exact actual SMS destination in the uniquely claimed provider attempt. New snapshot fields are checked again before sending a pending task question. Old metadata is not guessed into the new authority contract.
- `migration/workers/src/routes/reply_presentations.ts`, wired into `index.ts`: service-only, read-only POST `/worker/reply-presentations` accepts exactly owner and inbound event IDs, then reads the actual persisted sender/time. It SQL-joins exact owner-scoped outbox/message/attempt records. Only real `sms_delivered` attempts with a nonempty provider handle and matching recipient digest qualify. All six creation/update timestamps must precede the inbound timestamp strictly; late receipts or later-edited message/snapshot rows cannot retrospectively grant authority.
- The new read selects **all delivered revisions of current open tasks**, not a guessed latest one. Unrelated lifetime history does not consume the candidate limit; 1,005 unrelated message chains are a regression fixture. More than 200 active-task presentation candidates explicitly returns incomplete/unknown. Recent delivered message context has a separate 40-message bound. Storage refusal or malformed result arrays returns 503, not an empty known history.
- `brain/conversation.py`: real SMS reconstruction excludes unreceived assistant messages, including cached app-only messages. Release, answer/amend, and requeue bind to the selected exact snapshot and carry its ETag through the write. The explicit app-card context is retained across model awaits too. A stale/unknown referent yields an owner-visible clarification, not approval of whatever version a new read happens to find. Successful held-task corrections publish their newly saved question snapshot with the actual reply so the next “yes” can refer to the new version. Genuine independent requests still reach normal reasoning. Per-turn authority is reset and cannot leak into a later spoken-answer helper call.
- `policy/guard.ts` plus `api/records.ts`: account clients cannot create, edit, delete, or cross-kind-transform `reply_outbox`, `notification_status`, `anticipy_text`, or `sms_reply`. Production creator inventory found phone/extension readers, not legitimate creators of these kinds; Python/Worker service paths create them. Normal account input and owner reads remain available. The SQL UPDATE/DELETE also checks the **current** kind atomically, so a service conversion between guard read and write cannot be overwritten. Service/superuser access and account-erasure lifecycle remain intact.
- `api/records.ts`: the existing ETag and SQL compare-and-set now include the actual question, version, effect, lease, receipt, uncertainty, and consequence fields. Relying on `updated` alone missed same-millisecond question changes. No new write endpoint bypasses the existing workflow/auth guards.
- `connections/dispatch.ts`: shared SMS attempts retain the same recipient digest and the actual provider-observation update time. A final canonical phone lookup after claiming and immediately before provider contact refuses revoked/changed destinations. An unknown lookup retains uncertainty without calling or retrying the provider; the saved app answer remains available. This closes the real dispatcher path, not just a helper's direct-send path.

### Local verification ledger

| Gate | Observed evidence |
| --- | --- |
| `tests/test_sms_presented_revision.py` | Initial production-path reproducer: 14 failed, 2 passed before the repair. Expanded 32-case suite passes. Covers old delivered revision followed by correction, unsent/failed/accepted/unknown messages, sender/plan/scope/effect mismatch, missing legacy binding, explicit app-context race, missing ETag, stale write CAS, and correction → delivered new question → approval. Meaning and provider responses are explicit fixtures; real Conversation, workflow transitions, and durable message code run against local SQLite. |
| `test/server-event-evidence.test.ts` | Agent's initial account-evidence reproducer: 28 failed → 38 passed; additional guard-to-write race: 8 failed → 46 total passed. Includes full Worker auth/router/records SQL, ordinary input lifecycle, cross-owner checks, service/superuser paths, and atomic update/delete kind fences. |
| `test/reply-presentations.test.ts` | 79 passed, including real Worker dispatch, authenticated-before-read, all six timestamp boundaries, malformed/unknown D1 responses, owner/recipient/key joins, all active revisions, over 1,000 unrelated chains, and explicit active-candidate overflow. |
| `test/job-approval-race.test.ts` | Same-timestamp question mutation returned 200 incorrectly before the field expansion; 22 checks pass afterward, including every newly protected identity field. Runs the actual record SQL over SQLite. |
| `test/connection-dispatch.test.ts` | Final-phone guard mutation: all three new revoked/changed/unknown cases failed without it; 13 checks pass with it. Provider fetches are captured fixtures, not actual sends. |
| Adjacent Python verification | `tests/test_sms_presented_revision.py tests/test_reply_delivery.py tests/test_one_answer_path.py`: 80 passed. Additional answer/spoken/untextable path set: 45 passed. |
| Final local integrated verification | `npm_config_offline=true .venv/bin/python -m pytest -q -rs`: 3,155 passed, 2 skipped in 41.74s. Both skips are explicitly opted-in live model/tool probes; no production environment was supplied. Full Worker `npm test`, Worker `npm run typecheck`, and repository `git diff --check` exited 0. These are local fixture/source checks, not live-provider proof. |

Operational limits: missing endpoint, old question metadata, uncertain receipt, failed identity read, or failed precondition stays unapproved. That may require reviewing the current card, not repeating an ambiguous old SMS. An initial approval already dispatched to an executor cannot be retroactively revoked merely by a later reply; existing execution/cancellation/uncertain-effect protocols still own that boundary. The new service route and brain caller must be rolled out coherently and then verified against actual non-production-owner SMS/receipt/result evidence before anyone claims the SMS journey is fixed live. This task performed no deploy, push, or real delivery.
