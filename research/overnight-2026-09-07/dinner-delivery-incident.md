# Dinner-task delivery and guidance incident — September 7, 2026

**This incident is primarily an Anticipy scheduling, workflow and status-display failure. SendBlue delivered the observed follow-up promptly once Anticipy submitted it.** This is not a reliability certification for all SendBlue traffic or evidence that every pre-migration flow worked correctly.

The investigation used the owner's supplied screenshots, authenticated reads of the exact task and owner-scoped events, a read-only SendBlue message query filtered to that owner's number and the incident window, and current source. No messages, approvals, bookings, provider switches, restarts or production patches were issued by this investigation.

## Timeline — Vancouver time

| Time | Evidence |
|---|---|
| 08:00:03, 08:00:22, 08:16:49 | The owner's three daily proactive-outreach slots were consumed: two task-question reservations and one clock reservation. A reservation does not prove a message delivered. |
| 13:47:22 | Relevant dinner input reached the API. The separate loading incident documents the brain backlog. |
| 13:53:09 | Dinner task created, almost six minutes after input. |
| 13:53:49 | Task held as `awaiting_confirm`; its saved parameters still asked for dinner time, but the workflow's `required` list was empty. The displayed result also retained an older location question despite the updated goal already naming West Vancouver. |
| 14:01:10.606 | A recorded owner tap approved workflow version 2. The investigator did not perform this approval. |
| 14:01:14 | The research executor claimed the task. |
| 14:01:15.320 | The executor refused the consequential workflow and returned the generic account/device blocker. Task became `needs_user`. |
| 14:01:29.056 | Anticipy saved a text-attempt record for the new blocker. |
| 14:01:34.201 | Anticipy saved `sms_accepted`. |
| 14:01:34.597 | SendBlue's message record has this send timestamp. |
| 14:01:36.309 | SendBlue's last-update timestamp reports `DELIVERED`, iMessage, no error. The supplied Messages screenshot independently shows the matching text. |

The provider query returned one message in the owner's incident window, with `hasMore=false`. There is no provider record of the original missing-time question in that window. The observed follow-up's send-to-delivered-update interval is **1.712 seconds**. Anticipy's attempt-record-to-provider-delivery interval is about seven seconds. Neither supports attributing the earlier multi-minute silence to provider delivery delay.

## What is broken

### Hidden outreach suppression

`brain/worker.py:4757` treats an `awaiting_confirm` task without `_question_invited=true` as proactive. It applies quiet/meeting checks and, at line 4909, requires a daily outreach reservation. The persisted pre-approval dinner record had no invited flag; all three reservations were already taken that morning. That cap was sufficient to prevent a proactive text even with a working sender. This was daytime; nighttime alone cannot explain the silence.

After approval, the task became `needs_user`. That question is treated as a response to authorized work and can bypass the proactive cap. This explains the change from a silent card to a later text after the user tapped Approve. No durable suppression-reason record is exposed on this card, so the user cannot distinguish policy deferral from delivery failure.

### The task-card label is not its receipt

`app/ios/Anticipy/DashboardPolicy.swift:67` computes `notificationCaption` from a notification schedule. A current daytime schedule yields the literal label “Text delivery unconfirmed”; the function takes no task ID or message receipt. `Views/ContentView.swift:2600` renders it on the card.

Direct chat replies have newer per-message receipt tracking. Task questions still go through `ask_about_stuck_jobs`, recording `job-sms:question:...` attempted/accepted states without retaining the provider message handle. The SendBlue callback lookup in `migration/workers/src/routes/sendblue.ts:127` matches `reply-sms:` records and their saved `provider_id`. Consequently, the earlier direct-reply repair does not complete receipt tracking for this task-question path. This is an integration gap in the repair, not a reason to distrust the user's observed message.

### Missing facts and approval disagree

Before approval, the saved task parameters still contained one missing-time question, while `_workflow.required` was empty and state was `awaiting_approval`. The UI offered Approve because structured workflow state said it could. Its prose said information was missing. Approval cannot supply a dinner time, and no word-based UI rule should attempt to infer missing fields from that prose. The structured plan, its missing facts and its displayed question must agree after every context update.

### Wrong executor, followed by an unusable request

The saved hand selection described public restaurant-availability research. The task nevertheless represented a consequential workflow and was assigned `lane=research`. `brain/server_work.py:108` correctly refuses to perform consequential work in a text/research executor, but emits the generic “account or device action” fallback. The question composer then paraphrased that fallback as a request for the owner to handle something, without identifying an account, device, URL or concrete action.

The record has no completion receipt. It does not establish a reservation or a specific login problem. The user should not be sent looking through account settings to solve a routing mismatch. Reading availability and actually making a reservation need correctly scoped steps and executors, with required facts settled before final approval.

### The earlier test message was misattributed

“Got it, your delivery check came through” came from the earlier authorized, assistant-operated production delivery test. It was not evidence that the app independently ran an automatic test. The later generated reply attributing it to an app automation was misleading. No such test was initiated during this investigation.

## Direction

1. Keep the provider decision separate from this incident: the observed SendBlue delivery succeeded promptly. Switching to Twilio would retain the hidden suppression, wrong executor, missing-fact disagreement and misleading label.
2. Give every task question and chat reply a shared durable message identity and delivery lifecycle, preserving the provider handle. Display withheld, queued, accepted, delivered, failed and unknown from recorded facts, including a specific policy reason when withheld. Do not blindly resend an uncertain attempt.
3. Keep required facts, task version, displayed question and approval eligibility synchronized. Use model/context interpretation of the actual conversation; enforce consistency over structured state. A natural question here would ask what time dinner should be, while retaining the already supplied West Vancouver context.
4. Match each plan step to a capable executor before dispatch. If a real connection is required, ask for that named connection and provide its actual handoff. A capability mismatch must trigger replanning or a truthful internal failure, not an invented chore for the user.
5. Repair the speech-processing backlog documented in the loading incident. All delivery timestamps should expose whether time was spent awaiting interpretation, awaiting permission, queued locally or waiting on the provider.

The public [SendBlue status page](https://status.sendblue.com/) exposed a generic normal-status announcement alongside loading/error placeholders and did not establish a fresh account-specific health verdict. The primary evidence here is the authenticated message record, obtained through the documented [message-list API](https://docs.sendblue.com/api-v2/messages/). Its [status API](https://docs.sendblue.com/api/resources/messages/methods/get_status) and [callback documentation](https://docs.sendblue.com/getting-started/sending-messages/) distinguish queued/accepted/sent/delivered states; Anticipy's displayed state must maintain that distinction.

[Sanitized incident measurements](dinner-delivery-incident-evidence.json). Raw owner and provider responses remain in ignored local `work/audit/dinner-delivery-private.json` and `work/audit/dinner-provider-private.json`. No product change or deployment was made during this diagnosis.
