# Anticipy iOS app

Native SwiftUI app. Two ways in, one pipe out.

- PRIMARY: the phone's own microphone. `Anticipy/Audio/PhoneListener.swift`
  feeds Apple's speech recognizer (on-device where supported) and emits one
  line per utterance; the switch that starts it is the listen card in
  `Anticipy/Views/ContentView.swift`.
- HELD: the BLE pendant. `Anticipy/BLE/PendantManager.swift` receives Opus
  frames over the encrypted link and `Anticipy/BLE/OpusFrameAssembler.swift`
  reassembles fragments, but the app deliberately leaves `onOpusFrame` unset
  in `startPendantTranscription` (`Anticipy/AnticipyApp.swift`), so frames
  are dropped at the source. `Anticipy/Audio/LocalTranscriber.swift` is the
  intended on-device path; it accepts PCM, and there is no Opus decoder in
  the target. That decoder, and the capture bridge around it, is the open
  work. Raw audio never leaves the device (`design/LOCAL-FIRST.md`), and no
  cloud decoder substitutes for the missing local one. The whole boundary,
  the packet contract, and the division of work are in
  [docs/FIRMWARE-COLLABORATION.md](../../docs/FIRMWARE-COLLABORATION.md).

Both paths land in the same place: `AnticipySession.heard(...)` in
`Anticipy/AnticipyApp.swift`, which pushes an `events` row of kind
`transcript` carrying `source` = `phone_mic`, `pendant`, or `typed`. Triage
happens on the SERVER (`brain/worker.py`). The phone decides nothing about a
line beyond who probably said it; it shows the feed and the confirm cards,
and the hands do the work.

## Backend

The app talks to the Cloudflare API Worker at `https://api.anticipy.ai`
(`migration/workers/`, with D1 behind it) through
`Anticipy/Backend/AnticipyBackend.swift`: account auth, `events`, `jobs`,
browser pairing, connected apps. The wire shapes are the records API and
product routes described in `migration/spec/CONTRACT.md`. The earlier
PocketBase backend is gone; nothing in the app depends on it.

## Files

- `Anticipy/AnticipyApp.swift` — app entry and `AnticipySession` (both capture paths, polling, the feed).
- `Anticipy/Audio/` — the phone microphone path, capture policies, cursor and flush law, journal and tally.
- `Anticipy/BLE/` — the pendant link, frame assembler, radio and battery policies.
- `Anticipy/Backend/` — the API client, job receipts, the device (calendar) hand, connections, the connect handoff.
- `Anticipy/Views/` — the listen switch, transcript, dashboard, confirm cards, settings.
- `Widget/`, `UITests/`, `Tests/`, `Tools/`, `scripts/` — the lock-screen activity, UI tests, the `swiftc` logic suites, cue synthesis, App Store Connect helpers.

There is no phone-side triage client and no second copy of the prompt
contract; triage is server-side and stays there.

## Build (on a Mac with Xcode)

1. `cd app/ios && ./build_on_mac.sh` — checks for `xcodebuild`, installs
   `xcodegen` if missing, runs `xcodegen generate` from `project.yml`, and
   builds for the iOS Simulator. No signing and no team needed.
2. `project.yml` is the source of the project and of the Info.plist
   (`GENERATE_INFOPLIST_FILE: NO`; the BLE, microphone and speech usage
   strings and the background modes are declared there). Do not hand-edit
   the plist; regeneration erases it.
3. A DEVICE build needs a team (`DEVELOPMENT_TEAM` is read from the
   environment or picked in Xcode under Signing & Capabilities). The
   simulator build does not.
4. Exercise the pendant on a real iPhone; the simulator has no Bluetooth.

**The build number.** `CURRENT_PROJECT_VERSION` lives in `project.yml` and in
the committed `Anticipy.xcodeproj/project.pbxproj` (four occurrences) and
moves in the same commit as any source change; the last leg of the test
runner enforces it. Read the current number from `project.yml`.

## Tests

```sh
sh app/ios/Tests/run_all.sh
```

Every suite compiles the real pure-Foundation sources with `swiftc`; no
simulator. On a Mac with only the Command Line Tools, select an installed SDK
with `SDKROOT` ([docs/TESTING.md](../../docs/TESTING.md)).

## Shipping

iOS ships from CI, never from a laptop; see
[docs/HANDOFF-SHIP-IOS.md](../../docs/HANDOFF-SHIP-IOS.md) and
[docs/RELEASE.md](../../docs/RELEASE.md).

## Keys

- Speech vendor: there is no lane and no credential. The vendor websocket
  client was deleted, and the Worker's `POST /transcription/token` keeps
  refusing with its reason rather than answering 404, because a refusal that
  names its reason gets obeyed while a 404 gets retried. Enforced by
  `overnight/no_vendor_ears.py` and `Tests/run_local_ears_tests.sh`.
- Model provider: no key in the app. Every model call happens server-side.
- Vendor credentials do not belong in the phone. The account session token is
  a separate credential: `AnticipySession` currently stores `authToken` in
  `AppStorage` (UserDefaults), not Keychain. Migrating it to Keychain requires
  explicit handling of existing sessions, sign-out, account changes and tests;
  absence of a vendor key does not establish secure session-token storage.
