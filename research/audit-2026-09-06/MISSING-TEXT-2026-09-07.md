# Question shown in the app, absent from Messages

## What was verified

The owner's screenshot at 00:30 on September 7 shows a proposed calendar task
and the question, “I still need when it ends.” The corresponding live task was
created at 07:26:48 UTC (00:26:48 America/Vancouver). It remains
`awaiting_confirm`, with zero execution attempts and no approval or receipt.
No calendar write is recorded for this task.

The current profile has the owner's saved phone. The owner's live worker status
names Sendblue as the selected texting provider, and its container is running
the previously verified source hash. The Sendblue lines endpoint returns 200
and includes the configured sending number. These checks prove configuration
and availability of the lookup; they do not prove an outbound message attempt.
The owner's nine events at inspection contain no `anticipy_says` question.
Private, scoped API readbacks are in `work/audit/missing-text-*.json`.

## Why the displayed label is misleading

`ConfirmJobCard.notificationRoute` in
`app/ios/Anticipy/Views/ContentView.swift` maps a valid saved phone directly to
`textAndApp`. That selects “Updates: In app · I'll also try text.” It does not
inspect provider configuration, a send attempt, a deferred notification, or a
delivery receipt. The question comes from the persisted job's `result`, which
can be visible without any outgoing text.

## Night-time suppression

`brain/worker.py::SPEAK_ONCE` returns `defer` for `ambient_act` from 22:00 to
08:00 local time, before contacting a provider. The corresponding ambient
proposal path in `brain/anticipy_core.py::hear` keeps the card and clears the
outgoing text on that verdict. A meeting digest can also be deferred.

`missing-text-policy-proof.json` records a replay of the production function
with the clock frozen at the actual task time. It returns `defer` without any
HTTP call. This reproduces the mechanism consistent with the observed card and
missing text. The exact original suppression decision is not stored on the
task, and the original container log was not retrieved; do not present this
as a recovered delivery trace or a proven Sendblue failure.

## Incorrect interpretation is a separate problem

The saved proposal explicitly records this assumption:

> interpreting 'got added' as 'gotta add it' and 3 PM as today based on the sudden realization

The source quote says “the kids we got added to calendar for 3 PM.” The model
changed a possible report of completed work into a new calendar proposal,
combined it with accounting work, and treated a missing end time as the next
question. It did not first resolve whether any new event was wanted. The
transcript may itself be ambiguous; ambiguity does not substantiate that
assumption. No regex exception is an acceptable fix.

## Correct behavior required

- Interpret completion versus a new request with a model and the surrounding
  conversation. Preserve uncertainty instead of silently changing the words.
- Make notification timing explicit for questions produced during active phone
  listening. The present ambient night policy conflicts with the owner's
  expectation of receiving the question by text while testing at night.
- Persist pending/deferred/attempted/failed/provider-confirmed delivery states
  and render the actual state in the app. A saved phone is only a prerequisite.
- Keep successful provider submission distinct from handset delivery, and
  verify the corrected flow through the owner's phone.

This turn performed scoped live reads, a deterministic reproduction, and the
required pre-edit iOS suite. It made no runtime or iOS source changes, did not
send a diagnostic text, and did not cancel or execute the owner's proposed task.
