# Full-system defect audit — 2026-09-01

Scope: the live Railway backend and worker, the production job/event stores,
the iOS listening and answer paths, server-side research, SMS delivery, the
paired Chrome agent, the served extension and Mac artifacts, and the repository
scoreboards. This is an evidence record, not a claim that software can be
proved to contain no future defect.

## Fixed in this pass

### Speech rows collapsed onto one old start time

Production evidence from build 113 showed three rows created within 0.8 seconds
with the identical `capture_started_at` (`2026-09-01T05:00:14.974Z`). The rows
ended at different instants, so this was not an offline queue restamping the
same row. `PhoneListener.absorbRecognized` delivered a banked decode window but
left `pendingSince` alive; the replacement tail inherited the old window's
start.

`4eb753f4` clears that boundary after the banked delivery and adds the exact
replacement-window shape to `TranscriptFlushPolicyTests`. Build 121 contains
the repair. The old production rows remain historical evidence; the live
turn-envelope scoreboard can only prove the repair after build 121 records a
new replacement-window burst on a phone.

### A typed answer could be cancelled on the phone and hidden from the brain

The iPhone carried phrase lists that decided `forget it`, `already booked`, and
similar text meant “end the errand.” A match cancelled locally and prevented
the owner's sentence from reaching `Conversation.on_reply`. Separately, the
brain's model-offline refusal fallback looked only at `awaiting_confirm`, so it
could not cancel a `needs_user` errand.

`4eb753f4` deletes the phone classifier, routes every non-empty typed answer as
one `app_reply`, and makes the fallback consult `_open_work()`. A regression
test proves a model-offline `forget it` cancels work parked for information.
The two old rule-based fallbacks are recorded as retired tape by `f6d697bf`.

### Read-only research died when Brave exhausted its quota

The old failed job `yv6n30bisjbkkce` predated this release. A live provider
probe reproduced Brave HTTP 402. The worker had a second configured search
provider available locally but no provider chain, so a quota incident failed
the entire research lane.

`4eb753f4` adds a provider-neutral Brave → Tavily chain for both read-only jobs
and preflight procedure research. Provider errors log only status, never owner
text or credentials. `TAVILY_API_KEY` is configured on the production worker;
a deliberate invalid-Brave probe fell through and returned a cited Tavily
result. Browser automation is still the fallback only when no server-side
provider is configured.

### Duplicate active jobs and missing commitment identities

The production queue held five active rows for three distinct commitments;
three represented the same “clock initiative” commitment. Two later duplicates
were cancelled through the canonical workflow and the three surviving rows were
backfilled with their commitment keys. Post-repair counts: three active rows,
zero duplicate active commitment identities, zero missing commitment keys.
The structural prevention shipped in `044ef695` and its PocketBase-compatible
form in `84acbdcc`.

### Worker startup cried about a deliberately blank child phone

Supervised children intentionally start without an inherited phone and then
load the account-bound canonical route. The warning ran before that refresh,
so every healthy child printed a phone failure and then printed the corrected
number seconds later. `4eb753f4` refreshes before the startup verdict and avoids
an immediate duplicate profile read.

### Pending work could be reclassified from goal wording

Production has zero nonterminal rows missing `consequence`. The legacy fallback
re-derived an absent value from goal prose, recreating the effect classifier at
read time. `4eb753f4` now uses the stored structural value and fails closed if
it is absent; tests prove opposite-looking goal sentences take the same safe
branch.

### iOS Release warnings

`bf02aaee`/build 121 replaces the deprecated Bluetooth category option, removes
an obsolete throwing wrapper, and stops carrying mutable weak captures into
concurrently executing callback closures. The quiet Release build now exits
zero with no compiler output.

## Verified healthy

- Full Python suite: **2,440 passed**.
- Full iOS logic gate: **all suites passed**, including 49 transcript-flush
  cases and 34 capture-envelope cases.
- Unsigned Release device build for the app and widget: **BUILD SUCCEEDED**;
  the final quiet build emitted no warnings.
- `overnight/is_it_live.py`: source, Railway-served extension files, ZIP and
  current unpacked folder matched byte-for-byte; exactly one Anticipy extension
  was enabled.
- `overnight/are_the_ears_live.py --hours 48`: 85 build-113 phone rows found.
- `overnight/is_the_brain_live.py`: backend health, question limits, quiet
  hours, unsolicited-message limit, duplicate wording and worker fingerprint
  passed.
- `overnight/no_vendor_ears.py`: passed.
- Consolidation gate, run inside the production worker volume: all four legs
  passed; schemas were current and every active store had consolidated within
  24 hours.
- Production Railway backend and worker were both running successfully before
  this release.
- After a fresh fetch, `origin/jose_anticipy_system` contained no unseen Jose
  commits. This branch is the repository's configured TestFlight release branch.

## Open findings that code alone cannot honestly close

### SMS delivery registration

One affected destination (not the founder's removed/reset number) has eight
Twilio failures with error 30034 and no delivery receipts. That is an A2P
registration/business-console block, not a transport exception that code can
repair. App notifications remain the canonical in-product channel; optional
SMS will not become reliable for that destination until the Twilio sender is
properly registered.

### Speaker tagging / voice identity

The speaker-tagging model exists in source, but the distributable engine is not
linked. Earlier Sherpa/ONNX XCFramework experiments caused cloud/TestFlight
builds to disappear, and removing them restored distribution. Apple's current
native SpeechTranscriber APIs expose timing/confidence but no speaker identity.
The honest next step is either the exact Apple rejection artifact for a new
packaging experiment or a distributable Core ML embedding implementation; the
old dependency must not simply be re-added to a release.

### Chrome extension activation

The served and unpacked files are version 0.11.2 and match. The running Chrome
session still reported 0.11.1 until Chrome reloads the unpacked extension.
Unpacked developer extensions do not provide a silent consumer auto-update
channel; a Chrome Web Store or managed distribution path is required to remove
that manual activation step.

### Evidence that requires a real person/device

- A cold-stranger onboarding run has not yet supplied the final human proof.
- Historical build-113 timestamp rows cannot be rewritten into build-121 proof;
  a new spoken replacement-window burst is required after TestFlight install.
- Phone audio behavior alongside real YouTube playback still requires a handset
  session; simulator and compiler gates cannot prove iOS route arbitration.

## Release identities

- Product repair: `4eb753f4`
- Tape retirement: `f6d697bf`
- Warning-clean build 121: `bf02aaee`
- Release branch: `jose_anticipy_system`
