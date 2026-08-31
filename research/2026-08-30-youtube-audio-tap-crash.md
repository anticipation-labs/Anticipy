# YouTube audio-route crash: device finding and fix

## Finding

This was an app abort, not iOS suspending Anticipy for memory or background
limits. The connected iPhone contained Anticipy crash reports from builds 75,
109, and 111 with the same main-thread path:

`AVAudioEngineImpl::InstallTapOnNode` -> `AVAudioNode.installTap` ->
`PhoneListener.configureAndStartEngine` -> `PhoneListener.recoverAudio` -> the
`AVAudioSession.routeChangeNotification` observer.

The two newest crashes occurred on 2026-08-30 at 20:18:24 and 20:18:45 while
build 111 was installed. Both were `EXC_CRASH / SIGABRT`; neither appeared in a
Jetsam report. That closes the earlier hypothesis that a long YouTube session
merely caused background suspension.

The old route handler rebuilt synchronously inside AVAudioSession's
notification callback. It stopped one `AVAudioEngine`, called `removeTap`, and
immediately called `installTap` on the same input node. AVAudioNode permits only
one tap on a bus and reports violations with Objective-C `NSException`, which
Swift's `try?` cannot catch. The repeated production stack ends at exactly that
exception boundary.

## Fix

- Route and media-reset notifications schedule one coalesced rebuild on the
  next main-queue turn, after the notification callback has returned.
- Every retry/recovery retires the entire old `AVAudioEngine` and creates a new
  engine/input bus. It never performs remove-and-reinstall on the same node.
- Tap ownership is explicit, so Stop removes a tap only when that exact engine
  successfully installed it.
- The one `installTap` call sits inside a tiny Objective-C exception boundary.
  If AVFAudio still rejects a valid-looking format during route churn, the app
  marks capture suspended and the existing watchdog retries with another fresh
  engine instead of allowing the exception to abort the process.
- Recovery now swaps the speech request only after the new engine actually
  starts; a rejected tap cannot create a recognizer that hears nothing.

## Proof available before release

`app/ios/Tests/run_audio_recovery_tests.sh` checks the route/rebuild structure
and executes the Objective-C boundary with both a normal operation and a thrown
`NSException`. The normal iOS policy suites and a full simulator build remain
the compile/regression gates. The final hardware proof is to install the new
TestFlight build, leave Anticipy listening, start and stop YouTube repeatedly,
and confirm no new Anticipy crash report appears.
