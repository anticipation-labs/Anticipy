# Current Mac window and browser distribution

Source of record: `cloudflare-backend`. Starting local and fetched remote HEAD
were both `9039b83a`; no merge was needed. Unrelated developers' untracked files
were left alone.

## What Tejas already merged

- PR #59 (`776cbab5`): the Mac posts to `https://api.anticipy.ai`, emits
  `source=mac`, preserves capture times and owner/other speaker attribution.
- PR #62 (`e9648808`): the front-facing meeting library, live meeting view,
  local notes, onboarding, Settings, guide and Dock icon. `MacRuntime` owns
  transcript delivery outside any view, so closing a window does not sever it.
- PR #61: PocketBase retirement renamed the Mac client to `MacBackend` and
  moved the served ZIP into `migration/workers/public/mac/`.

## Actual distribution failure

Live `/mac/Anticipy-for-Mac.zip` was still build 119 (1.1.0), 388,070 bytes,
SHA-256 `079aee239d2e55665490913ecfdc6a241dd020aceeca9256f8ea66034a820f36`.
Its plist had `LSUIElement=true` and its executable named the retired backend,
not `api.anticipy.ai`. The merged source and shipped app were different.

The browser archive already matched repository version 0.18.0, SHA-256
`4e409dcec8fa01669fe07fb60e83ef14870bf6cd0327a9db7a65e346b2a4690a`.
A current download does not automatically replace an old unpacked Chrome install.

## Surgical delivery repair, build 171

MacBackend owns session and queue state on the main actor, yields during
network I/O, snapshots credentials for a drain, and ignores stale-session
responses. The final offline line retries without requiring more speech.
A persisted capture UUID becomes the event primary key; a lost response is
resolved by reading back the exact owner-scoped capture, preventing duplicates.
Concurrent new lines are preserved. Malformed queues are retained and show a
Settings error. No rules interpreting human words were added.

Both shared build-number files moved to 171. This changes the Mac build; it
does not authorize or imply a new TestFlight upload. iOS release 170 remains
separate from this Mac distribution repair.

## What connects to what

Mic/system audio → local speech transcription → MacRuntime → MacBackend →
Cloudflare authenticated events API → the brain's transcript reader. Speaker,
capture start/end and account identity travel with the original text. The
existing brain produces follow-up work through the phone and messaging system.
The Mac's manually typed meeting notes and raw recordings remain local; this
release does not pretend it has a Mac task inbox or note-to-brain sync.

## Evidence before publishing

- Pre-edit iOS and Mac suites passed.
- Post-edit iOS suites, complete Mac suites and full SwiftUI typecheck passed.
- Seven behavioral tests compile the actual MacBackend and simulate offline
  final speech, accepted-but-lost responses, concurrent append, account switch,
  current token rejection, corrupt disk queues and false 200 responses.
- The real compiled MacBackend sent owner and other-speaker captures to the
  live API. Both persisted with original clocks, a repeated ID was rejected,
  owner-scoped readback succeeded, and the successful probe account was erased.
  This transport probe does not claim to measure a new brain/model decision.
- A universal arm64/x86_64 Developer-ID-signed build launched into the new
  four-step onboarding window. No microphone recording or user login was
  required for this launch check.
- `build_release.sh` now uses the reviewed project instead of running xcodegen
  in the shared checkout. CI can notarize a checksum-pinned local signature
  with existing Apple credentials; private signing keys remain on the Mac.

Reproducer: compile `LiveBackendProbe.swift` with `MacBackend.swift`,
`TranscriptWire.swift` and `MeetingLinePolicy.swift`, then pass `--live`.
Use `sh app/macos/Tests/run_all.sh` for the offline suites.

## Publication

Apple accepted build 171 (1.1.1), ticket
`4deaee84-257a-46d5-8602-6243b27034f2`. CI run `34179162484` passed all Mac
tests, notarization, signature, version and Gatekeeper checks. It failed only
because GitHub Actions is not permitted to create pull requests. Its release
branch was fast-forwarded into `cloudflare-backend` without conflict.

The checked-in notarized archive SHA-256 is
`c27dd01e3257e2d8df99e2f5ff1a80f943b53eab01a5d9ab8431bed8186e1cbb`.
Local re-verification also passed codesign, stapler and Gatekeeper. Worker
publication is a separate deployment; see `docs/HANDOFF-NOW.md` for its status.
