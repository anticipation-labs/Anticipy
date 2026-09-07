# Every phone number — the four defects, and the TestFlight build that carries the fix

Started 2026-09-06. Commissioned by the owner: "make the browser agent and the
Sendblue test work for every phone number ... make every part of the product
functional and ship me the app on my TestFlight."

The owner authorised all four fixes below and asked for the TestFlight build to
go up *after* they land, not before. On live SMS the owner's words were "IT
SHOULD TEXT ALL THE PHONE NUMBERS THAT SIGN UP" — that is a statement about
product behaviour (every account that signs up is reachable), not an
instruction to blast proof texts at strangers' handsets. No unsolicited text is
sent to any number that did not sign up.

## D1 — sign-up refuses a normally-typed number  (iOS, SHIP-BLOCKER)

`app/ios/Anticipy/Views/AuthView.swift:491` gates the Start button on
`session.e164(phone) != nil`. `AnticipyApp.swift:1483 e164()` returns nil for
any raw string that does not begin with `+` or whose digits do not begin with
`00`. A tester typing `(604) 555-0142` — the way almost every North American
writes their own number — passes `looksReachable` (the helper line says the
number is fine) and fails `e164` (the button stays dead), with no message
naming the problem.

The strictness itself is correct and `overnight/stranger_gate.py` leg 3 exists
to keep it: guessing `+1` for a bare London number is how `2079460958` became
`+12079460958`. The defect is that there is no way for the person to say which
country they are in, so the only accepted input is one they have to know to
type.

## D2 — an inbound text resolves to nobody unless the stored string matches byte for byte  (Worker)

`migration/workers/src/pb/sender.ts` resolves the sender with
`WHERE "phone" = ?1` — exact SQL string equality — and
`migration/workers/src/pb/records.ts:424` stores the phone exactly as it was
typed. Any account whose row holds `604-724-5161`, `(604) 724-5161` or
`+1 604 724 5161` can never be matched against the `+16047245161` the carrier
delivers. The route answers `200 {ok:true, dropped:"no owner"}` and the person
is never replied to.

A phone number is a routing address, not an identity (sms.pb.js:160-163), so
canonicalising one is address plumbing, not meaning: legal under HARNESS-LAWS
law 1, in the same sense as the audio plumbing exemption. Ambiguity must still
fail closed — two accounts canonicalising to the same address is `ambiguous`,
never a pick.

## D3 — owners past the brain cap get no brain

`ANTICIPY_MAX_OWNER_WORKERS` is spent in id order by
`migration/workers/brain/src/plan.ts`. Every owner past the cap is unserved:
their speech lands in D1 and nothing reads it, so they are never texted at all.
"Text all the phone numbers that sign up" is false for anyone past the cap.

## D4 — the served browser-agent package is not the source

`overnight/stranger_gate.py` legs 1 and 2 are RED: the extension package served
at version 0.15.0 differs from `extension/` in `background.js`. Every tester who
installs the browser agent installs code nobody wrote. Fix is mechanical:
`sh extension/build-zip.sh`, commit, deploy.

## Order of work

1. D4 (mechanical, unblocks the stranger gate's first two legs)
2. D2 (Worker; no client can be correct while the server drops the reply)
3. D1 (iOS)
4. D3 (brain cap)
5. Gates, then the build-number bump and the TestFlight push

## D5 — the build that carries every fix cannot be uploaded today  (SHIP-BLOCKER, not a code defect)

Found while checking what the owner's phone is actually running, after they
reported that the Home listen control does not stop and that stopping only
works from Settings. That defect was already fixed in `0b791d69` ("iOS 154:
stop actually stops, and the dashboard shows the task") — the capture face's
✕ fired no listening callback, left `keepListening` true, and, because
`mode = .capture` only happens on a false→true edge of `listening`, made the
one working stop unreachable afterwards.

The fix has never reached a phone. App Store Connect holds **156 VALID** as its
newest build (uploaded 2026-09-06 16:18 PDT from `4f79aee8`, which predates the
fix), and both internal testers have it INSTALLED. Every run since has failed at
the upload step with the same answer:

    Validation failed (409) Upload limit reached. The upload limit for your
    application has been reached. Please wait 1 day and try again.

Four consecutive runs (34066548548, 34067154502, 34067183444, 34067737546), all
offering build 157, all refused. The cause is the workflow itself: `on: push`
with `paths: ['app/ios/**']` uploaded a build for every commit, and five iOS
commits landed inside fifty minutes. The scarce daily allowance was spent on
intermediate commits, leaving none for the one a person was waiting on.

Fixed in the workflow: a push still builds and runs `app/ios/Tests/run_all.sh`,
and the six steps that talk to Apple are gated on an explicit ship — a manual
`workflow_dispatch`, or `[ship]` in the commit message. The 409 now names itself
in the run's error rather than reading as a signing problem, because four runs'
worth of reading "Apple refused the upload" points at the archive, which was
fine every time.

**What is still owed:** dispatch `ios-testflight.yml` once Apple's window
resets, and confirm the resulting build is VALID and visible to the Internal
group. Nothing in the tree can shorten that wait.

## Status

- [x] D4 — zips rebuilt from source (`e7fdf8fc`); stranger leg 2 green, leg 1 needs the deploy
- [ ] D2 — `migration/workers/src/pb/phone.ts` written, callers not yet moved onto it
- [ ] D1
- [ ] D3
- [x] D5 — upload gated on an explicit ship; the 409 names itself
- [ ] TestFlight build above 156 VALID
