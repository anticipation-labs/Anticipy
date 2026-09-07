# Anticipy for Mac becomes a window — 2026-09-07

Branch `issue-36-mac-meeting-notes`, off `cloudflare-backend` at `a216dae3`.

## The ask, and the card it was filed under

Issue #36 on GitHub is the task-board card "Build Anticipy phone call and
FaceTime recorder (iOS)": CallKit detection, a one-tap widget, a call rendered
as a conversation card in the phone's feed. Jose's brief on it is for that.

The instruction that came with the issue link on 2026-09-07 was different and
explicit: build the **macOS** app, "a simple Granola type of UI for when
you're on Zoom meetings and it takes notes", with proper onboarding,
documentation and Anticipy branding, on `cloudflare-backend`. This note and
the PR do what was asked. The iOS widget and the call card on the card's own
text are untouched and still open; the PR says so rather than closing #36
against work it does not contain.

## What existed

`app/macos` was a menu-bar-only recorder (LSUIElement, `.accessory`): a
popover with Start/Stop, an auto-start toggle, sign-in, and "Show recording in
Finder". The recorder underneath is sound and stays exactly as it was:
`MacListener` (microphone + Core Audio process tap, two on-device
SpeechTranscriber lanes), `MeetingArchive` (two `.caf` tracks + `meeting.json`
per meeting), `MeetingWatcher` + `MeetingOfferPolicy` (offer on a two-way
conversation, never record on its own), `CaptureStreamHealth` ("it started"
vs "it is recording"), `MacBackend` + `TranscriptWire` (rows to
api.anticipy.ai, source "mac", the JSONL queue, a 401/403 ends the session).
The transcripts it made were already on disk; nothing showed them.

## What this change adds

A window, on top of the recorder, that never touches the recorder's files:

| Piece | File | Tested by |
|---|---|---|
| Reading a meeting folder back: manifest + owner sidecar, titles (owner's word, then the app's label, then "Meeting"), durations in words, elapsed clocks, day headings, newest-first grouping, Markdown export | `app/macos/Anticipy/Library/MeetingLibrary.swift` (pure Foundation) | `run_meeting_library_tests.sh` — 42 checks, compiled beside the REAL `MeetingArchive` so the manifest shape is proven by the two meeting |
| Which screen opens; what a permission row may say; the buttons a denied permission can offer | `app/macos/Anticipy/Library/OnboardingRoute.swift` (pure) | `run_onboarding_route_tests.sh` — 16 checks |
| The library on disk, watched; the only writer of `owner.json`; Trash, never delete | `AnticipyMac/MeetingStore.swift` | type-checked; the policy underneath is the tested part |
| Brand tokens for macOS (the phone's `Theme.swift` values, `NSColor` dynamic providers), button styles, the mark, the breathing dot | `AnticipyMac/MacTheme.swift` | theme contract scan in `run_app_shell_tests.sh`: no other Mac file names a colour |
| Sidebar (Now / Today / Yesterday / weekday / date), meeting detail (editable title, transcript with You/Others and clocks, notes saved as typed), live view (clock, both wires' one sentence, settled lines, grey-italic partials), the offer banner, the account card with the pending-line count | `AnticipyMac/MainWindow.swift` | type-checked |
| First run: welcome, sign in (skippable, the library is not a door), permissions with live state read from the system, ready with the auto-start switch | `AnticipyMac/OnboardingView.swift` | route + sentences tested; view type-checked |
| Settings (account, auto-start, light/dark under the phone's key, meetings folder, version) | `AnticipyMac/SettingsView.swift` | type-checked |
| The guide, in the app and in `docs/MAC-APP-GUIDE.md`, same sections in the same order | `AnticipyMac/GuideView.swift`, `docs/MAC-APP-GUIDE.md` | guide contract in `run_app_shell_tests.sh` |
| The app icon: the pendant mark on ink, ten macOS sizes, rendered from a script | `AnticipyMac/Assets.xcassets` | icon count in `run_app_shell_tests.sh` |
| The app as a regular app (Dock icon, window), the menu bar item kept; the transcript push and auto-start wired in `MacRuntime`, alive for the whole run, NOT in a view | `AnticipyMac/MacApp.swift`, `Info.plist` | LSUIElement scan in `run_app_shell_tests.sh` |

`MacBackend` gains one published number, `pendingCount`: rows in
`unsent.jsonl`, updated on every queue write. It is the only thing the app can
honestly say about sync, because a row leaves the queue on a 2xx and on
nothing else.

Build number 167 → 168 in `project.yml` (both places) and the committed
`pbxproj` (all four), with the ledger entry. The pbxproj was hand-edited (new
file references, a Library group, a Resources phase for the Mac target with
the asset catalog, `ASSETCATALOG_COMPILER_APPICON_NAME`); `xcodegen generate`
into a scratch copy produced the same membership, so `project.yml` and the
committed project agree.

## Decisions worth writing down

- **No summariser.** A Granola-shaped app is expected to write notes for
  you. Law 1 forbids a heuristic doing that, and the model that could is the
  brain the transcript is already sent to. The notes pane is the owner's own
  words; the guide says the brain acts on the transcript through the phone
  and texts. If a "what Anticipy made of this meeting" panel is wanted, it
  is a read of the brain's rows for the meeting's window, and it needs a
  served owner to prove against, which a throwaway probe owner is not.
- **Onboarding is not a door.** Once walked, the library opens signed in or
  not. Recordings work on this Mac alone, and a session the server dropped
  (the 401/403 path) must not lock a person out of their notes. Sign-in is a
  card in the sidebar instead.
- **System audio is explained, not gated.** macOS has no API to request the
  audio-capture grant ahead of a tap; the first recording asks. The
  permissions beat says so in as many words rather than pretending a button.
- **Two authors, two files.** `meeting.json` is the recorder's; `owner.json`
  is the window's. Neither reads the other's writes, so the recorder's tests
  and the library's tests hold on the same bytes, and a folder is never
  half-owned.
- **The window is not the wire.** The transcript push lived in the window's
  `onChange`. A closed window would have silenced the Mac. It is in
  `MacRuntime` now, with a posted-count so a line is never sent twice.

## Verified

- `sh app/macos/Tests/run_all.sh`: six suites green (capture core, meeting
  archive, transcript wire, meeting library, onboarding route, app shell).
- `sh app/ios/Tests/run_build_number_tests.sh`: "build 168, bumped from 167".
- `overnight/tape_gate.py`: leg 2 red by design, as before.
- CI `mac` job (macOS 15, Xcode 26, unsigned universal `xcodebuild`): see the
  PR checks. That job is the only place this app is actually BUILT; this
  machine has the Command Line Tools and no Xcode.

## Not verified, and why

- **Nobody has run the window.** No Xcode here, so no screenshot and no
  click. The type-check and CI's build prove the code compiles against the
  macOS 26 SDK; they do not prove a `NavigationSplitView` looks right or
  that `openWindow` from the status item's label works on every macOS build
  (the fallback when it does not: the window is still there until closed,
  and the menu bar keeps recording).
- **Law 3's live leg for the Mac** is `are_the_ears_live.py`'s "heard by the
  Mac" line, which needs a real meeting on a real Mac running this build
  and a `MAC_SIGNING_*` release. That is the same human step #37 already
  lists.

## How to finish it (a person with the lab Mac)

1. Open the PR's branch in Xcode, run `AnticipyMac`, walk first run, record
   a call, watch the sidebar. Screenshot into the PR.
2. Dispatch "Mac release", merge the zip PR, `cd migration/workers && npm run deploy`.
3. `python3 overnight/are_the_ears_live.py` with `ANTICIPY_SERVICE_TOKEN`
   after one real meeting: the "heard by the Mac" line goes green.
