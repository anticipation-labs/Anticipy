# Shipping the iOS app

The iOS-specific facts and steps. The ordered release runbook, including the
API and brain steps that usually precede an app build, is
[RELEASE.md](RELEASE.md).

## Where the app ships from

- Branch of record: `cloudflare-backend`. `main` has no `app/ios` at all.
- iOS ships from CI, never from a laptop: no development Mac holds a signing
  identity or a provisioning profile. The runner signs with the App Store
  Connect API key held as repository secrets; `.github/workflows/ios-testflight.yml`
  names them, and no value is in the tree.
- Bundle id, team, runner image and Xcode version are read from that
  workflow, not from this document.
- Marketing version and build number live in `app/ios/project.yml`; read
  them there. The 2026-09-13 TestFlight release recorded on the
  [readiness board](EOD-READINESS-2026-09-13.md) was 1.1.1 (176).

## Before a build

```sh
sh app/ios/Tests/run_all.sh
```

Every suite compiles the real sources with `swiftc`; no simulator. The last
leg is deliberately red while iOS source has moved since the build number
last did — that is the build-number rule, not a failure.

**The build-number rule.** `CURRENT_PROJECT_VERSION` lives in both
`app/ios/project.yml` and `app/ios/Anticipy.xcodeproj/project.pbxproj` (four
occurrences) and moves in the same commit as the source it describes. Edit
both by hand; the committed `pbxproj` is what CI builds. It once sat at one
value across nineteen commits, so seven different source trees all called
themselves the same build and "is the bug still in the build on my phone?"
had no answer.

Building locally for the simulator needs no signing and is a fine compile
proof on any Mac with Xcode:

```sh
xcodebuild -project app/ios/Anticipy.xcodeproj -scheme Anticipy \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -configuration Debug build CODE_SIGNING_ALLOWED=NO
```

## Uploading to TestFlight

A push is not enough. Every push to `cloudflare-backend` touching `app/ios/**`
builds and runs the gate but uploads **nothing** unless one of these is true:

- the run was dispatched by hand (`ios-testflight.yml`), or
- the head commit's subject contains the literal marker `[ship]`.

Apple throttles binary uploads on a rolling 24-hour window and bursts trip it
faster: one `[ship]` commit when a build is actually wanted, not on every
push. The workflow's final step says plainly which of the two happened.

## Confirming against App Store Connect

Never trust the green tick: runs have been marked failed while their builds
uploaded, and a build reported as rejected has been live and installable.

```sh
gh workflow run asc-query.yml --ref cloudflare-backend -f build=<N>
```

With `confirm` blank it is read-only: processing state, which groups can
install, who is in them, and the complete existing audience.
`confirm=ASSIGN_EXISTING` (email blank) links existing testers to that exact
build and creates no invitation. `confirm=INVITE` or `INVITE_EXTERNAL` with an
email enroll a tester; external groups need Beta App Review before any build
is visible.

## Working in a shared tree

Stage files by name and commit path-limited (`git commit -- <paths>`);
`git add -A` has swept another session's half-finished work into a shipped
build before. Never `git checkout --` a change you have not committed.

## A separate TestFlight, not this one

Everything above ships to this App Store Connect account. A genuinely
separate TestFlight needs four things that are not in this repository: another
Apple Developer team (and a different `DEVELOPMENT_TEAM` in the workflow), a
different `PRODUCT_BUNDLE_IDENTIFIER` (Apple binds a bundle id to one
account), that team's own App Store Connect API key as the `ASC_KEY_ID`,
`ASC_ISSUER_ID` and `ASC_KEY_P8` repository secrets, and a new app record.
Someone who only needs to install and test is a tester, not a fork.
