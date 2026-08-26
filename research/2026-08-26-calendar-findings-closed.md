# The 21 calendar findings, closed — 2026-08-26

Three adversarial reviews refused to approve rung 0 and filed 21 findings. The
repair agents were killed mid-task by a stall timeout; a second workflow
finished the job. This records what actually closed, and the one finding that
was wrong.

## Measured after the repair

| Check | Result |
|---|---|
| `tests/test_device_lane_routing.py` | 78 passed, exit 0 |
| full python suite (less the playwright module) | **2306 passed**, exit 0 |
| `node extension/tests/run_all.mjs` | 67/67, exit 0 |
| `sh app/ios/Tests/run_calendar_hand_tests.sh` | pass, exit 0 |

The guard part was **approved** outright. Lane and executor each went through a
close pass.

## The finding that was wrong, and how that was settled

The lane's re-review filed a CRITICAL against `research_lane.pb.js:403`: that
the act leg was unguarded because `extension/tests/test_device_lane.mjs`
"contains no goal-invariance test at all".

**Disputed, with proof.** The act leg reads `declaredActTypes` — a declaration,
never the goal — so Law 1 is respected structurally rather than by test. And the
suite does catch a regression: planting the classic violation, an early return
admitting any row whose goal contains the word "calendar", turned the node suite
RED (1/67 failed, exit 1). Restored from a cp backup, `git diff` empty, 67/67
green again.

Two things worth keeping from that:

**A missing test is not an open hole, and the severity should say which it is.**
The code was never wrong here; the claim was that nothing would catch it going
wrong. Those want different words, because "critical" spends someone's day.

**The finding had no owner, which is a defect in how the work was split.** It was
filed by the LANE's reviewer against the GUARD's test file, and the guard had
already been approved and closed. Nobody was assigned it, so nobody would have
fixed it. When one part's reviewer files against another part's files, the
finding needs re-routing, not just recording.

## Still open

`app/ios/Anticipy/AnticipyApp.swift:1644-1656` writes `status: "queued"` and
`approval` in ONE patch dict, against `research_lane.pb.js:555-559`. The owner
is legitimately the approver here, so this is not obviously wrong — but the
approver and the executor are the same credential on that write, and no test
pins the order the server evaluates them in. Unowned by every agent in both
workflows, because it lives in neither the lane's, the guard's nor the hand's
files.

## Unchanged, and still the only thing prose cannot settle

Whether an `EKEvent` written locally reaches calendar.google.com, and whether
the field carrying our minted id survives the CalDAV round trip. One device
test. Nothing here has been deployed: `research_lane.pb.js` is deliberately held
back from production and every gate above is repo-green only, which Law 3 says
is a claim and not proof.
