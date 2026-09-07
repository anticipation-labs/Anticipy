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


## Live observation

Deploy34132224974 verified8of8 workers running
bfe77b293e457fe56ecc17923ece8d9241369367ef39959a486c0b512842abad.
The initial fresh .invalid fixtures did not run: production deliberately excludes
reserved test domains from discovery. Both were erased; failed logs are retained.
The first also exposed a missing owner predicate in the probe's feed query,
which returned403 and was corrected. Those failures are fixture failures, not
proof of a customer account's brain failing.

The designated served probe qeuy6sv1raof9rw was verified as an existing .invalid
fixture with a fictional555phone. Its phone was temporarily cleared, and one
fresh read-only browser job was seeded. The actual worker persisted exactly one
notice in12.31seconds while leaving the job queued: "I can't open the appointment
page because your Chrome browser isn't connected. Can you check Settings > Browser
in Anticipy to make sure it's paired and online?" The task was then cancelled,
and only the fixture's captured fictional phone was restored. No real message
was sent. Evidence: work/audit/overnight-stall-designated-1.json and the two
preserved failed fixtures. Reproducer: proof/audit/live_stall_probe.py.

## Backlog coverage

The browser and phone reporters previously inspected only the first5/10 oldest
rows. Already-notified pending tasks could occupy those pages forever. Both now
use the existing bounded paged reader, with exact owner scope and lane checks.
Tests exercise25 tasks over nine pages for each lane.138 focused checks and the
full Python suite (3103 passed,2 skipped) pass. The PocketBase runtime fixture
now provisions its own temporary test administrator before startup, avoiding an
unwanted installer tab on the developer's Mac. Live seven-task verification is
required after deployment; none of these checks sends to a real phone.
