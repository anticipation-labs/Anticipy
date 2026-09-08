# Anticipy for Mac

The meeting recorder: both sides of a call as two local tracks, transcribed on
device, the words sent to the same brain the phone feeds. The user-facing guide
is [docs/MAC-APP-GUIDE.md](../../docs/MAC-APP-GUIDE.md); this file is for
whoever works on the code.

## Shape

```
AnticipyMac/                 the app (macOS 26, SwiftUI + AppKit)
  MacApp.swift               scenes: the window, the guide, Settings, the menu bar item
  MainWindow.swift           library sidebar, meeting detail, live view, the offer banner
  OnboardingView.swift       first run: welcome, sign in, permissions, ready
  SettingsView.swift         Cmd+comma
  GuideView.swift            the in-app guide (mirrors docs/MAC-APP-GUIDE.md)
  MacTheme.swift             every colour, font and spacing in the app; nothing else names one
  MeetingStore.swift         the library on disk; the only writer of owner.json
  MacListener.swift          one meeting session: microphone + system audio + two transcribers
  SystemAudioCapture.swift   the Core Audio process tap and the stream meter
  MacSpeechPipeline.swift    one on-device SpeechTranscriber lane
  MeetingArchive.swift       the recorder's folder: two .caf tracks + meeting.json
  MeetingWatcher.swift       offers when a two-way conversation is held by an app
  MacBackend.swift           sign-in, the JSONL queue, the post to api.anticipy.ai
  Assets.xcassets            the app icon
Anticipy/Capture/            pure Foundation policies the recorder runs under
  MeetingOfferPolicy.swift   when to OFFER (never to record) — Law 1 plumbing
  MeetingLinePolicy.swift    final phrases into one bounded line
  CaptureStreamHealth.swift  "it started" vs "it is recording"
  TranscriptWire.swift       the row a line becomes (source "mac", device "mac-b<build>")
Anticipy/Library/            pure Foundation policies the window runs under
  MeetingLibrary.swift       reading a meeting folder back, titles, clocks, grouping, Markdown
  OnboardingRoute.swift      which screen opens; what a permission row may say
Tests/                       swiftc-compiled suites, one runner each, all in run_all.sh
Tools/                       release build, capture probes
```

Two files in a meeting folder, two authors: the recorder writes `meeting.json`
and the audio; the window writes `owner.json` (title, notes). Neither edits
the other's file, so the recorder's tests and the library's tests read the same
bytes and a folder is never half-owned.

## Run the suites

```sh
sh app/macos/Tests/run_all.sh
```

Every suite compiles the real sources with `swiftc` against the macOS 26 SDK,
so it runs on any Mac with the Command Line Tools and no Xcode, including the
CI runner. `run_app_shell_tests.sh` type-checks the whole app and holds the
theme contract (no view names a colour) and the guide contract (in-app guide
and docs have the same sections). Whether the app still BUILDS is answered by
the `mac` job in `.github/workflows/system-invariants.yml`, which runs
`xcodebuild` on macOS 15 with Xcode 26.

## Build

The Xcode project is shared with the phone and generated from
`app/ios/project.yml`; the `AnticipyMac` target lists these sources. The build
number is `CURRENT_PROJECT_VERSION` there and in the committed `pbxproj`, and
it moves in the same commit as any source change or the iOS build-number gate
refuses. A release is `app/macos/Tools/build_release.sh` on a Mac with the
Developer ID identity, or the `Mac release` workflow.

## Rules that bite here

- **No audio leaves the Mac.** `run_capture_core_tests.sh` scans for a network
  destination on an audio path and fails the build if it finds one.
- **Law 1.** Nothing here decides what words mean. Titles are the owner's or
  the app's label; there is no summariser. Summaries belong to the brain.
- **Detection offers; the click records.** `MeetingOfferPolicy` can only say
  "offer". Auto-start is an explicit owner setting, off by default.
- **"It started" is not "it is recording".** Core Audio succeeds without a
  privacy grant and delivers zeros; `CaptureStreamHealth` is what tells the
  owner, in those words.
- **The queue is the truth about sync.** A row leaves `unsent.jsonl` only
  after the API returns its exact stored capture. Its stable ID makes retries
  safe after response loss; the last offline line retries without new speech.
  A current-session 401/403 reopens sign-in. An old session's response cannot
  sign out a newer account, and unreadable queue files are retained with a
  visible error in Settings.

The release script builds the committed Xcode project without regenerating it.
`mac-release.yml` can either build using the repository's Developer ID secrets,
or notarize a reviewed local signature supplied as a draft-release asset. The
latter pins both the source commit and archive SHA-256 and uses the existing
Apple CI credentials, without exporting the local signing key. Both modes
verify Apple's ticket and open a PR replacing the Worker-served Mac ZIP.
