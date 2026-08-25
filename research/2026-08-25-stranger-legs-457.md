# Stranger gate legs 4, 5 and 7 — the three that lived in app/ios

2026-08-25 · branch `jose_anticipy_system` · build 82 → 83

`python3 overnight/stranger_gate.py`, legs 4/5/7, using the gate's own output.

    BEFORE                                   AFTER
    [4] fail  ONBOARDING BELONGS TO THE ACCOUNT     [4] PASS
    [5] fail  ENROLLMENT IS OFFERED                 [5] PASS
    [6] PASS  (untouched)                           [6] PASS
    [7] fail  THE VERIFIED RECEIPT IS WHAT IS SHOWN [7] PASS

Legs 1 and 9 are the LIVE pair and need a deploy; they were not this task and
are still red. Leg 2 flipped fail → PASS during the session from somebody
else's extension rebuild, not from anything here.

**None of this is proven.** HARNESS-LAWS Law 3: the ears have been dead ~32
hours, build 82 is compiled and installed on no phone, and every leg above is
marked `(tree)` — it reads this checkout, not the deploy. What is verified is
that the source now does the thing; what is unverified is that any human has
ever seen it. The section at the bottom says exactly what would settle each one.

---

## Leg 4 — the tour belongs to the account

`hasOnboarded` was stored under the one string `"hasOnboarded"`: one boolean for
the whole PHONE, and `signOut`, `signIn` and `createAccount` all left it alone.
Cable install is the only way onto a device today
(`research/2026-08-24-cold-stranger-walkthrough.md` Step 0), so a phone that
somebody has already opened this app on is the NORMAL case — the installer opens
it once to check it, and the stranger's sign-up then lands straight on the feed.
No microphone primer, so listening is never started, so she hears nothing all
week. The tour survived only as "Replay the welcome tour" in Settings.

`app/ios/Anticipy/FirstRunOwnership.swift` already existed, complete and
correct, sitting in the pbxproj with **zero call sites** and no tests. The
decision was written; nothing asked for it. That is the failure the gate's own
`_clears` helper exists for — a mention is not a clear.

What landed:

- `flagKey` / `ownerKey` declared once in `FirstRunOwnership`, and
  `AnticipyApp` + `AnticipySession` both bind `@AppStorage` to those constants.
  Two copies of the string is precisely how a rename leaves a clear that
  silently clears nothing — the accident `swift_string_behind` was written for.
- `signIn` calls `FirstRunOwnership.arriving` **synchronously, with no `await`
  between it and `accountID = id`**. That ordering is load-bearing:
  `AnticipyApp.task(id: session.isSignedIn)` fires `resumeSignedInAccount` the
  moment `accountID` lands, and `resuming` would ADOPT a flag `arriving` is
  about to clear. Sign-UP reaches this too — `signUp` ends in `signIn`.
- `resumeSignedInAccount` calls `FirstRunOwnership.resuming`, which ADOPTS the
  pre-upgrade flag rather than clearing it. A phone updating to this build has
  `hasOnboarded = true` and no owner recorded because the key did not exist. The
  tour can only be completed from behind the sign-in door, so the only account
  that could have earned it is the one signed in now: stamping it is a fact, not
  a guess. Clearing instead would make every existing owner redo first run for a
  bug that was never theirs.

The interesting input is the stale owner. `arriving` deliberately does not test
`hasOnboarded` first — an owner id left behind a CLEARED flag would otherwise
survive to be matched later, and the next person under that id would inherit a
tour they never saw.

## Leg 5 — enrolment is offered, and what that is really worth

**Read this part before believing the green.**

The mechanical defect was real and is fixed: `VoiceEnrollView` had exactly one
presentation site in the whole app — a sheet inside Settings, under "Your
voice", below Listening / Pendant / You. To reach it a stranger had to tap the
slider glyph in the Home toolbar and scroll past three sections with nobody
suggesting it. `research/2026-08-24-engine-options.md:254` records the cost:
`speaker` at 0% across 221 production events, cause "enrollment unreachable",
confidence "Certain" — the named cause of four of six bad acts on the only call
ever scored.

Now: `app/ios/Anticipy/Views/EnrollmentInvite.swift` is raised by
`OnboardingView.finish()` once the four beats are cleared, before the
celebration. Not a fifth beat — `design/day-zero.md:237-239` already removed one
page from this walkthrough for exceeding the ~70-second budget, so the four keep
their names, their count and their progress track.

**And on the shipping build it never appears.** `project.yml` unlinked
sherpa-onnx for the second time (commit `d3ccb133`), because builds 76-80
delivered ZERO rows to production and build 75 delivered 313. So
`VoiceEmbedderFactory.make()` returns nil, `SpeakerTagger.available` is FALSE,
`EnrollmentOfferPolicy.firstRun` answers `.cannot`, and first run offers
nothing. That is deliberate: twelve seconds of reading that can never produce a
profile is worse than not asking — it spends the one budget first run has to
teach a stranger that the product is broken.

So, precisely:

| | |
|---|---|
| What the leg proves | first run CONSTRUCTS `VoiceEnrollView` through a view it puts on screen. The mechanical unreachability is gone from the source. |
| What the product can do | nothing. `speaker` stays at 0% until somebody re-links the engine, and no amount of onboarding moves it. |
| What changes on the day it is re-linked | the invite is already standing in front of every new person instead of three scrolls deep in Settings. No further iOS work. |

**The leg has a blind spot, and it should be told.** `leg_5_enrollment_offered`
asks whether first run constructs the view; it cannot see the runtime condition
that decides whether the screen is ever raised. A future change that gates the
invite behind something wrong — or behind nothing at all — keeps the leg green
either way. `run_enrollment_offer_tests.sh` is the check that closes that half,
scoped to `finish()` with comments stripped, and it is where the honesty lives.

`EnrollmentOfferPolicy` is three-state on purpose. "She already knows your
voice" and "this build cannot learn anyone's voice" are different facts about
the product, and a bool collapses them — which is how a dead feature reads as a
finished one. The order matters too, and is tested: a profile left on disk by
build 75 (which HAD the engine) survives into 83 (which does not), so asking
`hasOwnerProfile` first would report "I know your voice" on a phone where every
tag comes back nil.

## Leg 7 — the verified receipt is what is shown

`backend/pb_hooks/workflow_guard.pb.js:662` refuses to move ANY job to `done`
unless the `receipt` column parses and carries `verified: true`, an
`effect_key` matching the job's, and a non-empty `evidence` array. The app
decoded none of it. The done card was fed `result` — free text the extension
composed **about its own success** — while the thing the server actually checked
sat unread in the same row. The stranger could not tell a receipt from a
sentence, which is the entire promise of that card. Moment 31: "Done without
proof doesn't exist."

Half was already done: commit `5ec26d7f` added `let receipt: String?` to
`AgentJob`. Decoding a column nothing renders changes nothing anybody can see.

What landed:

- `app/ios/Anticipy/Backend/JobReceipt.swift` — parses the column. Nothing is
  inferred from a malformed receipt; a phone is not the place to decide what
  half a proof means.
- `JobReceiptPolicy.doneCard` takes `receipt:` and `effectKey:`. **`hasReceipt`
  changed meaning**, and that was the bug: it used to mean "the result string is
  not empty". A sentence is not a receipt. It now means the server verified
  this, bound to this row's own effect.
- `DoneCard` renders `ReceiptProof`: where it was checked, whether a photograph
  was deposited, and the full proof index verbatim behind one tap. When there is
  no verified receipt the card SAYS SO rather than going quiet.

The engine's words still lead — ex 77 wants the confirmation number first and ex
126 forbids editing it — but they no longer decide whether the card reads as
proven. Evidence entries are never rewritten, summarised, or dropped for looking
wrong; an unknown tag degrades to `.other` and is still shown.

The effect binding is re-checked on the phone rather than trusted: the row and
the receipt travelled separately to get here, and a receipt for a different
effect is the one shape that would let a photograph of one action vouch for
another. Rows predate the `effect_key` column, so nil/empty means "this row does
not say", which is not a mismatch.

### Law 1 note, because this parses tagged strings

`JobReceipt` splits `url:…`, `title:…`, `shot:…`, `evidence:…` on the first
colon. That is **deserialization of a format this product writes to itself**
(`verificationEvidence`, `captureMilestone`, `depositEvidence` in
`extension/`) — not a pattern-match deciding what a human's words mean. No
value is ever interpreted, only labelled, and an unrecognised tag is shown
verbatim rather than guessed at. Flagged here rather than left for a reviewer
to wonder about.

---

## Method, and what it caught

TDD throughout: each suite was written first and shown RED for the right reason
before any implementation. Then every behaviour was mutated in place and shown
able to fail. **Three of those mutations passed and exposed weak checks**, which
is the only reason they are worth the time:

1. `if false, let proof = card.proof` — a whole-file grep for `card.proof`
   still matched. The check catches DELETION, not disabling; that limit is now
   written into `run_job_receipt_tests.sh` instead of implied.
2. Deleting `hasOnboarded = false` from `signIn` left `run_first_run_tests.sh`
   GREEN, because the identical line in `resumeSignedInAccount` matched. The
   check is now scoped to the `signIn` declaration by brace-counting — the same
   thing `stranger_gate.swift_span` does, for the same reason.
3. Replacing the whole `EnrollmentOfferPolicy.presents(...)` call with `if true`
   left `run_enrollment_offer_tests.sh` GREEN, because a doc comment two lines
   above still named the policy. **A comment retiring the check that tracks the
   thing it describes** — the exact defect `stranger_gate.py`'s header records
   five times over. Now scoped to `finish()` with `//` comments stripped.

Untracked new files were backed up with `cp` before every mutation. One
mutation was restored with `git checkout --` early on and destroyed the
implementation under it, not just the mutation; everything after that was
restored from the backups.

## Pre-existing red found on the way, NOT fixed here

`app/ios/Tests/run_all.sh` fails at `run_watchdog_policy_tests.sh` with a
compile error — `ListenSessionFacts` is not passed to that suite's `swiftc`
invocation, so `ListenJournal.swift` cannot compile and `ListenEvent` fails
`Equatable`. It was red before this session touched anything.

Because `run_all.sh` is `set -eu`, **everything after that line is unreachable**:
`run_resume_policy_tests`, `run_control_policy_tests`,
`run_interruption_contract_tests` and `run_build_number_tests` have not run from
`run_all.sh` for as long as this has been broken. All four pass individually.
The three suites added here were inserted EARLY, before the broken one, so they
actually execute — but a suite nobody can reach is a suite nobody has, and that
is somebody's next job. `run_phone_number_tests.sh` is also not registered in
`run_all.sh` at all.

## What is still unproven, and what would settle it

Every leg above is `(tree)`. Nothing here has been seen by a person on a device.

- **Leg 4** — install 83 on a phone that already has the app, sign out, sign up
  as somebody else, and check the tour appears. Then update an EXISTING owner's
  phone to 83 and check it does NOT. The second half is the one that would hurt
  if it is wrong, and adoption is the only thing standing between it and every
  current owner redoing first run.
- **Leg 5** — cannot be settled at all until sherpa-onnx is re-linked, and that
  is gated on reading the App Store Connect processing rejection that commit
  `9069765a` demanded and `6e277694` skipped. Until then the honest statement is
  "first run would offer it", not "first run offers it". `speaker` stays 0%.
- **Leg 7** — needs one real done row with a receipt reaching a phone. The
  fixture in `JobReceiptTests.swift` is written to the shape
  `extension/workflow_state.js:122` emits, but a fixture agreeing with the
  source I read is not the same as the wire agreeing with the app.

None of it moves until somebody installs a build. The ears have been dead ~32
hours and that is still the thing in front of everything else.
