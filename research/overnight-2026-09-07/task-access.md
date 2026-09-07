# A blocked task can ask for the account it needs

The browser fallback knew that private sources required access, but the blocked
task could only ask the owner to open Chrome. The integration request existed
as a separate text command, with no path from the queued task to that request.

The worker now asks `/worker/task-access` about a queued task before composing a
generic browser notice. The route accepts only the service identity plus stored
owner/job IDs. It loads that owner's task, original source events, conversation
and actual connections. One model identifies the missing app; a second selects
an exact result from the live integration catalog. No app-name list or keyword
classifier decides meaning. The catalog search cannot grant account access.

The result is a contextual question, saved through the shared app-first task
notice path. It does not connect an app, mint a link, grant write permission or
change the job's execution state. A normal contextual acceptance goes through
the existing connection-command route and gets a fresh consent link. Waiting to
mint avoids a night-time link expiring before its owner wakes. Missing models or
catalog access leave the existing browser explanation available.

## Evidence and limits

- First real-model run: 8 of 11 passed. The model selected an invented calendar
  provider from a generic request, dropped a valid task beside quoted hostile
  text, and failed to search an unfamiliar named app. Failures are preserved in
  `work/audit/overnight-task-access-model-1.json`.
- Context and contrast examples corrected those distinctions. The second run
  passed all 11 using the actual production connection model through the metered
  gateway, with a fictional catalog and no execution effects. Evidence:
  `work/audit/overnight-task-access-model-2.json`.
- Eight route/planning checks cover owner isolation, caller-prose rejection,
  invalid model output, nonexistent catalog IDs, already-connected accounts,
  model outage, and a real SQL route offer that creates no consent link and
  leaves the job queued. The complete API suite and typecheck pass.
- Two worker tests cover persistence, no repeated model request for an existing
  notice, quiet hours, service outage fallback and unchanged task status.
  Full Python: 3,105 passed, two skipped.

This covers explicit queued browser tasks. It does not yet supply arbitrary
multi-step API execution or a provider choice the owner never identified.
Production deployment and a phone-disabled live worker observation are required
before claiming the new path is live. An in-app connection link must also be
tappable; that UI verification is being handled separately.
