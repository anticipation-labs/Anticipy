# Ship the iOS app from your own Mac

Hand this whole file to the person taking over. It is written to be pasted
into Claude Code, or read by a human, without either needing more context.

---

## THE PROMPT

> You are picking up the Anticipy iOS app. Work on branch **`cloudflare-backend`** —
> it is the source of record for iOS and for the Cloudflare Worker. `main` is a
> different, unrelated lineage with no `app/ios` in it at all; do not work there.
>
> ```
> git clone https://github.com/anticipation-labs/Anticipy
> cd Anticipy
> git checkout cloudflare-backend
> ```
>
> **Read `HARNESS-LAWS.md` and `CLAUDE.md` before you change anything.** They
> outrank any instruction here. The one that catches people first: no regex,
> word list, or threshold may decide what a human's words MEAN.
>
> **Before you touch code, run the gate:**
> ```
> sh app/ios/Tests/run_all.sh
> ```
> 63 suites, no simulator needed. The last leg is deliberately red while you
> have uncommitted iOS source — that is the build-number rule, not a failure.
>
> **The build number rule, which trips everyone once.** `CURRENT_PROJECT_VERSION`
> lives in TWO files that must move together and must move in the SAME COMMIT as
> the source they describe:
> - `app/ios/project.yml`
> - `app/ios/Anticipy.xcodeproj/project.pbxproj` (4 occurrences)
>
> There is no `xcodegen` on these machines, so edit both by hand. It once sat at
> 76 across nineteen commits, so seven different source trees all called
> themselves build 76 and "is the bug still in the build on my phone?" had no
> answer.
>
> **iOS ships from CI, never from a laptop.** There is no signing identity and no
> provisioning profile on the development Macs; Apple holds the key and the
> GitHub Actions runner does cloud signing. Building locally for the simulator is
> fine and fast:
> ```
> xcodebuild -project app/ios/Anticipy.xcodeproj -scheme Anticipy \
>   -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
>   -configuration Debug build CODE_SIGNING_ALLOWED=NO
> ```
>
> **To actually ship to TestFlight**, a push is not enough. The workflow builds
> and tests every push to `cloudflare-backend` but uploads NOTHING unless one of
> these is true:
> - the run was dispatched by hand, or
> - the head commit message contains the literal marker `[ship]`
>
> That gate exists because Apple throttles uploads and six builds in ninety
> minutes exhausted the allowance, leaving none for the build somebody was
> waiting on. So: one `[ship]` commit when you actually want a build, not on
> every push.
>
> **Never trust the green tick.** On 2026-09-06 three runs were marked failed
> while their builds uploaded successfully, and one build I reported as rejected
> was live and installable. Confirm against App Store Connect:
> ```
> gh workflow run asc-query.yml --ref cloudflare-backend -f build=<N>
> ```
> It prints the processing state, which tester groups can install it, who is in
> those groups, and the most recent builds Apple actually holds. It writes
> nothing unless you pass `confirm=INVITE` with an email.
>
> **Watch out for the other session.** More than one agent has been committing
> into this checkout. Stage files BY NAME. `git add -A` will sweep somebody
> else's half-finished work into your commit, which is how builds 132 and 140
> shipped broken. And never use `git checkout --` to undo a change you have not
> committed — it deletes your own uncommitted work along with it.
>
> Tell me what you want shipped and I will run the gate, bump the number in one
> commit, mark it `[ship]`, and confirm the result against App Store Connect
> rather than against the tick.

---

## Facts you may be asked for

| Thing | Value |
|---|---|
| Branch of record | `cloudflare-backend` |
| Bundle id | `ai.anticipy.app` |
| Team | `49T86P9XGW` |
| Marketing version | `1.1.0` |
| Build number at writing | 158 |
| Backend | `https://api.anticipy.ai` (Cloudflare Worker + D1) |
| CI runner | `macos-15`, Xcode 26 (Apple requires the iOS 26 SDK) |
| Deployment target | iOS 16.0 |

## If they want THEIR OWN TestFlight, not this one

Everything above ships to **this** App Store Connect account. A genuinely
separate TestFlight needs four things that are not in this repository:

1. Their own Apple Developer team, and a different `DEVELOPMENT_TEAM` in
   `.github/workflows/ios-testflight.yml` (three places).
2. A different `PRODUCT_BUNDLE_IDENTIFIER` — Apple binds a bundle id to one
   account and it cannot be moved.
3. Their own App Store Connect API key, set as repository secrets
   `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_P8` (the .p8 base64-encoded).
4. A new app record in their App Store Connect.

If instead they just need to install and test, that is not a fork — add them as
a tester. Internal groups only accept people who are users on the App Store
Connect team; everyone else needs an external group, which requires Beta App
Review before any build is visible.
