# The lock screen

**2026-09-06.** Build 144. Ships behind no flag.

Asked for by name, with a screenshot: Wispr Flow's lock-screen capsule — a
tinted pill above the torch and camera, the app's mark and name on the left,
one live number under it, controls on the right. "This is the exact design that
I want." So the anatomy is theirs and everything inside it had to be decided
here, because the thing Anticipy would put on a lock screen is not a word count.

## What it is

`ActivityKit`. One activity, five faces, one button.

| Reason | Line | Mark | Button |
|---|---|---|---|
| listening | `3 things heard · 2:07` | breathing | stop |
| offline | same, plus `keeping it on this phone` | breathing | stop |
| paused | `Paused` | still | stop |
| working | `Working on something` | still | opens the app |
| waiting | `Waiting on you` | still | opens the app |

Nothing else is a reason to be on somebody's lock screen. When none of the five
holds, `LiveActivityPolicy.reason` returns nil and the activity ENDS — eight
seconds of linger so a finish is visible, then gone.

## The two rules, and why they are code rather than prose

A Live Activity is the most privileged surface this product has. It sits on a
LOCKED phone, in front of whoever picks it up, without the owner choosing to
look. Two things follow, and both are enforced by
`Tests/run_live_activity_tests.sh` rather than only written in a header.

**One: it never quotes anybody.** Not a line, not a fragment, not a goal's
wording. An always-on microphone that prints what it heard onto a locked screen
is the single worst thing this product could do, and it would be one careless
`Text(job.goal)` away. The enforcement is structural: `ContentState` — the
struct that actually crosses into the widget process — has no field that can
carry a sentence. It holds an `Int`, a `Bool`, a `Date?` and one closed set of
wire words. The suite fails on any other `String` in it, on the controller
touching `goal`/`result`/`transcript`/`partial`, and on the view naming any of
them.

**Two: it never approves.** "Nothing sends without your OK" has always meant an
OK given with the consequence in front of you. A lock-screen button is a one-tap
yes on a surface too small to carry the consequence, pressed by whoever is
holding the phone — not necessarily its owner. So the capsule may SAY something
is waiting and may OPEN the app at it. `LiveActivityPolicy.Action` has two cases,
`stopListening` and `openApp`, and the suite fails on a third that commits
anything, on a second lock-screen intent, and on any intent named for approving.

This is the one place the design deliberately departs from the reference. Wispr's
pill carries two controls; ours carries one.

## Three decisions worth keeping

**Listening outranks everything.** When the microphone is open and a job is also
waiting, the capsule says listening. An activity showing "Waiting on you" over a
live microphone would hide the more important fact behind the more interesting
one. Paused outranks offline, because a stopped microphone has nothing to send
anywhere.

**The offline line is not a comfort.** `keeping it on this phone`, not "syncing
soon". Somebody whose phone has no signal should learn it on the lock screen
rather than an hour later.

**No app group, and no push token.** The widget extension has never had a shared
container — `project.yml` records that as what keeps provisioning from refusing
on a fresh account. The stop button works anyway because `LiveActivityIntent`
(iOS 17+) runs in the APP'S process, posts a notification, and the session
decides what stopping means. `Activity.request` passes `pushType: nil`: nothing
off this phone can write to this capsule. iOS 16.1–16.x get the capsule with no
button, since interactive controls arrived in 17.

## The defect the first render caught

The view does not print the policy's `detail` while the microphone is live. It
draws the count beside `Text(started, style: .timer)` so the app is never woken
once a second to push a number a timer can derive — a Live Activity updated that
often is one iOS throttles and then stops delivering, which is how these end up
frozen on other people's phones.

That optimisation silently ate the offline qualifier. The first simulator render
showed `3 things heard · 2:07` on a phone with no signal: the exact reassuring
lie `.offline` exists to refuse, produced by a performance decision three files
away. Crammed back onto one line it truncated to `3 things h… · 2:07 · keeping
it…`, which is the same omission plus visible damage. It has its own line now.

`LiveActivityPolicy.qualifier(_:)` exists so `face` and the live view compose the
same piece, and the suite fails if the view stops calling it. No amount of
reading would have found this; it took a render.

## The second defect, found the same way

Build 144 went onto a simulator and the Dynamic Island showed a gold dot
floating in black with no shape around it. The island is not a themed surface —
it is a cut-out in the display, and it is black in every appearance — so the
mark's ink outline, both text lines and the stop button's ink circle were all
ink on black. The lock-screen capsule sits on cream and was fine; nothing in
this file distinguished the two grounds.

`ActivityMark` takes its stroke colour as a parameter now, and every island
region passes cream. Build 145. Same lesson as the offline qualifier: neither
was findable by reading.

## The third defect, and it is the one that mattered

The owner saw the five-face harness sheet and read it as the app's behaviour:
five capsules stacked on one lock screen. It was not — the app holds ONE
activity and `reason` picks one of five faces for it. But the complaint sent me
back to the request path, and there was a real version of the bug sitting in it.

**A Live Activity outlives the process.** iOS keeps it on the lock screen
through a force-quit, and it is still there when the app comes back. The
controller's handle is not: it is an instance property and returns nil. The
guard read `if activity == nil { request }`, so every relaunch asked "is my
handle nil?", got yes, and requested a SECOND capsule beside the one already on
screen. A third after the next force-quit. Nothing in the app could see them,
and nothing on the phone could clear them but a reinstall.

Measured on a simulator: four launch-listen-force-quit cycles under builds
144/145 left **four** distinct activity ids in `liveactivitiesd`. The same four
cycles under 146 leave **one**, reused — `822C3CF5…` updated each time rather
than replaced.

The question is now put to iOS rather than to a local variable:
`adoptExistingActivity()` takes back whatever `Activity<…>.activities` holds and
ends anything past the first, and it runs before the one request site. Four
source facts guard it, including that the adoption happens BEFORE the request —
adopting after requesting is adopting the one you just made.

The same run added a count, because a single capsule has to carry what it
replaced: `3 waiting on you` rather than `Waiting on you` with two more hidden
behind it. Still a count, still never a name.

## Proof

* `sh app/ios/Tests/run_live_activity_tests.sh` — 131 walked checks plus 14
  source facts. Every source fact was mutation-tested: each was broken on
  purpose and confirmed to exit 2.
* `xcodebuild … -scheme Anticipy` — app and widget extension both compile.
* Layout looked at, not assumed: a throwaway harness compiled the REAL
  `LockScreenActivityView` into a simulator app and rendered all five faces at
  lock-screen width. That is what found the truncation above.

**Not proven, and Law 3 says so.** No capsule has appeared on a real lock screen
yet. `Activity.request` needs a signed build on a device in a listening state,
and this suite is repo-green, not field-green. What IS proven: the policy, the
wire round-trip, the layout, and that both targets build.
