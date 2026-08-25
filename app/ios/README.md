# Anticipy iOS app

Native SwiftUI app. Two ways in, one pipe out.

- PRIMARY: the phone's own microphone. `Audio/PhoneListener.swift` feeds Apple's
  speech recognizer (on-device where supported) and emits one line per utterance.
  The switch that starts it is `listenCard` in `Views/ContentView.swift:475`.
- MUTE: the BLE pendant. `BLE/PendantManager.swift` still receives Opus frames
  (protocol verified on real hardware) and **nothing consumes them** —
  `startPendantTranscription` leaves `onOpusFrame` nil, so they are dropped at
  the source. `Audio/TranscriberClient.swift` used to stream them to a speech
  vendor's websocket; it is deleted. design/LOCAL-FIRST.md rule 1: "RAW AUDIO
  NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone."
  Closing it cost nothing that worked: production events with `source="pendant"`
  is ZERO, ever, against 229 from the phone microphone.
  What would make the pendant speak again is `Audio/LocalTranscriber.swift` —
  43 lines, zero call sites, wants `AVAudioPCMBuffer` while the pendant emits
  Opus `Data`, and there is no Opus decoder in the target. That decoder is the
  work; it is not started.

Both paths land in the same place: `AnticipySession.heard(_:from:)` in
`AnticipyApp.swift:258`, which pushes an `events` row of kind `transcript` carrying
`source` = `phone_mic`, `pendant`, or `typed` (`AnticipyApp.swift:249-255`, pushed at
`:273-275`). Triage happens on the SERVER, in `brain/worker.py`. The phone decides
nothing about a line beyond who probably said it; it shows the feed and the confirm
cards, and the Chrome extension is what actually acts.

## Files
- `Anticipy/AnticipyApp.swift` — app entry + `AnticipySession` (both capture paths, polling, feed)
- `Anticipy/Audio/PhoneListener.swift` — phone mic → Apple speech recognizer; the primary input
- `Anticipy/BLE/PendantManager.swift` — CoreBluetooth link (background capable)
- `Anticipy/Audio/LocalTranscriber.swift` — the INTENDED on-device pendant path; not wired (see above)
- `Anticipy/Backend/AnticipyBackend.swift` — pairing/events/jobs (PocketBase)
- `Anticipy/Views/ContentView.swift` — Listen switch, transcript, confirm-card UI

There is no `Anticipy/Brain/`. It held `BrainClient.swift` — a phone-side
OpenRouter triage client with its own copy of the system prompt, hardcoded to
`deepseek/deepseek-v3.2` — which had zero call sites and still compiled into
every binary, so it sat in the dSYMs of builds b18 through b30 looking live.
Deleted 2026-08-24. Triage is server-side and always was by then: `brain/worker.py`
owns it. Do not re-create a second copy of the prompt contract here.

## Build (on the Mac)
1. `cd app/ios && ./build_on_mac.sh`
   It checks for `xcodebuild`, installs `xcodegen` via Homebrew if missing, runs
   `xcodegen generate` to produce `Anticipy.xcodeproj` from `project.yml`, then builds for
   the iOS Simulator. That build needs no signing and no team, which is what makes it a
   usable compile proof on any Mac.
2. Do NOT hand-edit the project or the Info.plist, and do not drag files into a new Xcode
   project — both are generated. `project.yml` sets `GENERATE_INFOPLIST_FILE: NO` and
   declares the plist under `targets.Anticipy.info`, so the BLE/mic/speech usage strings
   and the `bluetooth-central` + `audio` background modes live there (`project.yml:69-78`).
   Anything you edit by hand is erased by the next `xcodegen generate`.
3. A DEVICE build needs a team; the simulator build does not. `project.yml:14` sets
   `DEVELOPMENT_TEAM: "$(DEVELOPMENT_TEAM)"`, so either export your Team ID before
   generating or open `Anticipy.xcodeproj` and pick the team under Signing & Capabilities.
4. Exercise the pendant on a real iPhone: the simulator has no Bluetooth. The phone-mic
   path is the one that needs no hardware at all.

## TestFlight
1. Product → Archive → Distribute App → App Store Connect → Upload.
2. appstoreconnect.apple.com → TestFlight → add yourself as internal tester.
3. Install TestFlight on the phone, accept the invite.

## Keys
- Speech vendor: **there is no lane and no credential.** The app used to POST
  `transcription/token` for a short-lived JWT and open a vendor websocket with it.
  Both halves are gone: the client method and `TranscriberClient` are deleted, and
  the server route answers 410 GONE with its reason
  (`backend/pb_hooks/transcription_token.pb.js`). It is kept refusing rather than
  deleted because a 404 reads as "wrong URL" and gets retried, while a refusal that
  names its reason gets obeyed.
  Enforced by `overnight/no_vendor_ears.py` and `Tests/run_local_ears_tests.sh`.
- OpenRouter: no key in the app at all. Every model call happens in the backend worker.
- So there is nothing left for the phone to keep in its Keychain. A vendor key appearing
  in this app is a bug, not a configuration step.
