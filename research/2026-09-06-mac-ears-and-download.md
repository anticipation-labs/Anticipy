# The Mac recorder: where its words went, and what /download hands over — 2026-09-06

Issue #37 (the "Build Anticipy macOS app" card) reached the board as BUILT.
Jose's brief on the issue split it into two jobs: the download is broken, and
recordings go nowhere. This file is what was measured before anything was
changed, what was changed, and what this machine could not verify. Law 4:
it lives here and not in a chat.

## Measured, before the change

`curl -sI https://www.anticipy.ai/download` answers 200 with
`Content-Type: application/x-apple-diskimage`. That 200 is written by hand:
the site's `src/app/download/route.ts` (aniticipy-web) has a HEAD handler
that returns fixed headers without touching the file. A GET is what a
stranger does, and a GET redirects twice —

    /download  → 302 /dl/Anticipy_1.0.0_aarch64.dmg
               → 302 https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/Anticipy_1.0.0_aarch64.dmg
               → 200, 2 516 712 351 bytes, Last-Modified 30 May 2026

— to the May build of the old desktop app at version 1.0.0. Not a 404 on
this day, as the brief measured earlier the same day; the wrong product.

The Mac recorder itself is live: `https://api.anticipy.ai/mac/Anticipy-for-Mac.zip`
answers 200, 388 070 bytes, sha256
`079aee239d2e55665490913ecfdc6a241dd020aceeca9256f8ea66034a820f36` — byte for
byte the committed `backend/pb_public/mac/Anticipy-for-Mac.zip` and the hash
in `research/2026-09-01-unified-release-handoff.md`. Unzipped: 1.1.0 (119),
Developer ID Application: Omar Ebrahim (49T86P9XGW), `codesign --verify
--deep --strict` clean, `spctl -a` accepted as Notarized Developer ID,
`stapler validate` OK, universal (x86_64 arm64). Nothing on the public site
links to it; `api.anticipy.ai/mac.html` does.

`strings` on that binary: `https://backend-production-61e0a.up.railway.app`.
`PocketBase.swift` defaulted to the Railway PocketBase the Worker replaced;
the phone had already been migrated off it (`AnticipyApp.swift` rewrites the
old URL on launch). Every meeting build 119 recorded was posted, with a
Railway session token, to a backend the brain no longer reads. That URL now
answers 404 for `/mac/Anticipy-for-Mac.zip` and the Worker answers 403 for a
token it cannot verify — and the Mac client treated every non-2xx as "retry
later", so those rows sat in `~/Library/Application Support/Anticipy/unsent.jsonl`
forever under a menu that said signed in.

The rows it built also stamped `source` as `mac_mic` / `mac_system` and
`device_id` as a random UUID, so even had they arrived, no gate could have
counted a Mac or named the build that spoke.

`overnight/are_the_ears_live.py` had no per-ear line at all. The brief says
it has one for the phone and the pendant; it did not.

`overnight/stranger_gate.py` leg 1 is the Chrome extension's download. There
was no leg for the Mac.

## Changed (this branch)

- `app/macos/Anticipy/Capture/TranscriptWire.swift` — pure Foundation: the
  ear is `"mac"`, the side of the call is `speaker` (`owner` / `other`, which
  the brain reads), the device is `mac-b<CFBundleVersion>` the way the phone
  stamps `iphone-b<build>`, and the row is exactly the eleven columns the
  phone posts. Out-of-order instants collapse onto the end, as the phone's
  `CaptureEnvelope` does.
- `PocketBase.swift` — defaults to `https://api.anticipy.ai`; builds the row
  through the wire; a 401/403 ends the drain pass and drops the session so
  the sign-in door reappears. Rows stay on disk under their owner.
- `MacApp.swift` — asks the wire which side spoke; no per-channel source.
- `app/macos/Tests/run_transcript_wire_tests.sh` + `TranscriptWireTests.swift`,
  `app/macos/Tests/run_all.sh`, and a `mac` job on `macos-15` in
  `.github/workflows/system-invariants.yml`. The Mac suites had no runner in
  CI before this.
- `overnight/are_the_ears_live.py` — "heard by the phone / pendant / Mac"
  lines over the same window with the same probe exclusion. The verdict is
  unchanged. `tests/test_ears_hear_the_mac.py` pins the `"mac"` string to
  the Swift wire's.
- `overnight/stranger_gate.py` — leg 10 (tree): the committed zip is not
  older than the Mac source, by git order rather than by build number
  (the Mac's number is the iOS number by design). Leg 11 (LIVE): a GET of
  `/download`, four bytes first, must be a zip and must be the committed
  bytes. Mutation tests in `tests/test_stranger_gate.py`.

## Proved against production — 2026-09-07

The wire was driven against api.anticipy.ai with the REAL Swift code: the
harness compiled `PocketBase.swift`, `TranscriptWire.swift` and
`MeetingLinePolicy.swift` with swiftc and used `PocketBase.signIn` (the call
the app makes) and `TranscriptWire.body` (the row the app posts). A
throwaway owner was signed up the way the phone does, two rows were posted
under `device_id="e2e-mac-2026-09-07"` — the prefix are_the_ears_live.py
excludes, exactly as the phone probe uses — read back, and the account was
deleted through `/me/delete`, which removed its rows. Every check passed:

    sign-up answers 200, returns an owner id
    PocketBase.signIn succeeds against the Worker; the session names the owner
    POST events (owner) answers 200 — every column accepted
    POST events (other) answers 200 — every column accepted
    both rows readable by their owner; kind=transcript; source="mac";
      device_id e2e-mac-2026-09-07; capture_started_at == spoken_at < capture_ended_at
      kept: source=mac speaker=owner started=2026-09-07T04:36:07.807Z ended=2026-09-07T04:36:11.007Z
    a stale token is REFUSED: 403 — so the app drops the session
    /me/delete answers 200; deleted: events 2, everything else 0
    the local session is cleared (Keychain item gone)

So the row shape is accepted by the Worker column for column, the ear and
speaker survive storage, the envelope survives, and the build-119-token case
answers 403 rather than hanging in the queue. What this does not prove is
the microphone: no meeting was recorded and transcribed here.

## Second pass — 2026-09-07

- The committed Xcode project lists `TranscriptWire.swift` (four lines
  mirroring MeetingLinePolicy's, not a regenerated project: this machine's
  xcodegen 2.46.0 rewrites 300 lines of ids and drops two Info.plist keys).
- `overnight/tape_gate.py`: `.caf` (and `.aiff`, `.aif`, `.m4a`) are data.
  The five sound files from iOS 151 had turned legs 1 and 6 red and the
  `test` job with them on every push to cloudflare-backend. RED LEGS is back
  to "2 (by design)".
- `system-invariants.yml`'s mac job now runs `xcodegen generate` and an
  unsigned universal `xcodebuild` of AnticipyMac after the suites, and checks
  the binary names api.anticipy.ai and not railway.app. The suites compile the
  pure halves; only xcodebuild says the APP builds.
- `mac-release.yml` (dispatch-only): `build_release.sh` on a macos-15 runner
  with the Developer ID identity imported from `MAC_SIGNING_P12_BASE64` and
  notarization through the `ASC_*` key TestFlight already uses; opens a PR
  committing the zip. Registered on `main` by its own PR (#60), as the other
  dispatch-only workflows were.

## Blocked here, by policy, and what each takes

The harness refused two actions and they are now one human step each:

1. **Merge anticipation-labs/aniticipy-web#1.** Vercel deploys `main`; then
   `curl -sI -L https://www.anticipy.ai/download` must end at
   `api.anticipy.ai/mac/Anticipy-for-Mac.zip` with 200 `application/zip`, and
   `python3 overnight/stranger_gate.py` leg 11 goes green against build 119.
2. **Merge #60 into `main`**, add `MAC_SIGNING_P12_BASE64` and
   `MAC_SIGNING_P12_PASSWORD`, dispatch `Mac release` on cloudflare-backend,
   merge the PR it opens, then `cd migration/workers && npm run deploy` — the
   Worker serves the zip as a static asset, and nothing short of a deploy
   changes what /mac/ hands over. Leg 10 goes green at the merge, leg 11 at
   the deploy.
3. **Record a meeting on the rebuilt app**, signed in as a real owner, and
   run `python3 overnight/are_the_ears_live.py` with `ANTICIPY_SERVICE_TOKEN`:
   the "heard by the Mac" line counts it. That is the screenshot the brief
   asks for, and it needs a person at a Mac.

Not done on purpose: deploying the Worker from this laptop. `wrangler whoami`
shows a logged-in account here, and a deploy would ship every Worker change
on the branch since the last one, not just the zip.

## The state the gates will report, honestly

- Leg 11 is RED: `/download` serves the DMG. The fix is one redirect in
  aniticipy-web's `src/app/download/route.ts` (a separate PR), and its
  HEAD handler must redirect too instead of answering 200 for a file it does
  not serve. Green only after that deploys and the leg is re-run.
- Leg 10 goes RED the moment this branch is committed: the Mac source moved
  after build 119. It stays red until `app/macos/Tools/build_release.sh` is
  run on the lab Mac — Xcode, the Developer ID identity and the notary key
  are there and nowhere else — and the printed zip is committed over
  `backend/pb_public/mac/Anticipy-for-Mac.zip` and the Worker deployed.
- "Heard by the Mac" reads 0 until that build is installed and a meeting is
  recorded on it.

## Not verified on this machine, and why

- `build_release.sh`: Command Line Tools only, no Xcode, zero signing
  identities, no `notarytool`. The whole app does type-check with `swiftc
  -typecheck -target arm64-apple-macos26.0` against SDK 26.5, and all three
  Mac suites pass, which is a precondition and not a build.
- A real meeting → a row with `source="mac"` → the ears gate counting it:
  needs the rebuilt app and `ANTICIPY_SERVICE_TOKEN`; neither is here. The
  live ears gate reads 403 on this machine. The wire itself is proven above.

## One thing deliberately not done

The phone's `CaptureSourcePolicy` draws no badge for an unknown source, on
purpose. A "Mac" badge in the iOS feed is one `case` and one test away and
belongs to whoever next touches that file, not to the Mac's wire.
