# Missing execution access stays visible at night

Observed source defect: report_stalled_work returned during quiet hours before
persisting an app explanation. A queued browser task also waited for a time
threshold before explaining that no browser was online. Phone-stall notices used
a different send-first path and fuzzy goal matching, so missing phone delivery
or a storage outage could hide the app result or conflate separate tasks.

Repair: browser and phone notices use one durable app-first function, keyed by
exact job identity and observed status. Quiet hours record SMS deferral after
saving the notice, without claiming a sending attempt. The next daytime sweep
may attempt one copy if the task remains stalled; restarts cannot repeat it.
A queued browser task can explain unavailable access immediately. A running
browser or phone task retains its existing grace period. Notices do not move
or complete jobs. Browser wording no longer claims an unpaired browser closed.

Verification:136focusedchecks passed; full Python3101passed2skipped
(work/audit/overnight-stall-full.log). New parameterized tests cover both lanes,
night→day, two sweeps, restart deduplication, primary storage, deferred versus
attempted events, and unchanged job state. Earlier canonical phone revocation
and write-outage cases remain covered. Live verification follows deployment.
