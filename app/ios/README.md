# Anticipy iOS app

Native SwiftUI app. Receives Opus audio from the pendant over BLE
(protocol verified on real hardware), streams it to Deepgram for live
transcription, triages every line via OpenRouter (ignore / act / ask),
queues actions as jobs for the Chrome extension, and shows confirm cards
before anything irreversible.

## Files
- `Anticipy/AnticipyApp.swift` — app entry + session state
- `Anticipy/BLE/PendantManager.swift` — CoreBluetooth link (background capable)
- `Anticipy/Audio/TranscriberClient.swift` — Deepgram realtime STT websocket
- `Anticipy/Brain/BrainClient.swift` — OpenRouter triage + job queuing
- `Anticipy/Backend/AnticipyBackend.swift` — pairing/events/jobs (PocketBase)
- `Anticipy/Views/ContentView.swift` — transcript + confirm-card UI

## Build (on the Mac)
1. Xcode → New Project → iOS App → name `Anticipy`, interface SwiftUI.
2. Drag the `Anticipy/` folder contents into the project.
3. Target → Signing & Capabilities:
   - add **Background Modes** → check *Uses Bluetooth LE accessories*.
   - set your Apple Developer team.
4. Info.plist: add `NSBluetoothAlwaysUsageDescription`
   ("Anticipy connects to your pendant to hear your day").
5. Run on a real iPhone (BLE does not work in the simulator).

## TestFlight
1. Product → Archive → Distribute App → App Store Connect → Upload.
2. appstoreconnect.apple.com → TestFlight → add yourself as internal tester.
3. Install TestFlight on the phone, accept the invite.

## Keys
- Deepgram API key → `TranscriberClient.connect(apiKey:)`
- OpenRouter API key → `BrainClient(apiKey:)`
Store both in Keychain in production; never commit them.
