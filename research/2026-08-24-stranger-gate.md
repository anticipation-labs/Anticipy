# The stranger walkthrough, turned into a gate that cannot forget

**Date:** 2026-08-24 · **Tree:** `/Users/josegaelcruzlopez/Desktop/anticipy-omize`
· **Branch:** `jose_anticipy_system` · **Scope held:** `overnight/` and `tests/`
only. `app/ios/**`, `brain/**` and `extension/**` were read, never written.

**Source:** `research/2026-08-24-cold-stranger-walkthrough.md` — nine dead ends
on the path a cold stranger walks. An audit is true on the day it is written.
This is the half of it a machine re-checks on every run.

**What landed:**

- `overnight/stranger_gate.py` — nine legs, two of which read LIVE.
- `tests/test_stranger_gate.py` — 49 mutation tests; every leg driven to red and
  back to green against a synthetic tree.
- `overnight/done_gate.py` leg 6 — **message and comment only.** No new checks,
  no new failure modes, no network dependency added to the scoreboard.

---

## Why a new file rather than more of `done_gate` leg 6

Leg 6 has exactly one claim: *a real person who is not Omar lived this*. It is
the only leg in the repo that cannot be satisfied by code, and that is its
value. Folding nine mechanical checks into it costs three things:

1. **It stops meaning what it says.** A leg 6 that fails because the extension
   is three versions behind no longer reads "no stranger has done this". The
   day a proof IS signed, leg 6 would keep failing for reasons that have
   nothing to do with the stranger, and the person reading `Work ONLY this leg`
   would be sent at the wrong thing.
2. **It drags the network into the whole scoreboard.** Two of these legs must
   read production (Law 3). `done_gate` legs 1, 2 and 5 are offline and
   deterministic; leg 4 already needs a backend and that is one dependency too
   many to double.
3. **The two questions have different lifetimes.** `stranger_gate` asks *is it
   worth asking somebody?* and goes green when the product is fit to hand over.
   Leg 6 asks *did somebody actually do it?* and goes green once, forever. They
   are read together and they are not the same leg.

So leg 6 keeps its single claim and now **points at** the new gate in its
failure message, the way `tejas_gate` leg 2 was made to point at `tape_gate` in
`bd93df3c` — comment and message only, no polarity change, no new failure mode.

---

## What is pinned, and the mutation that proves it

Every leg was reproduced by hand first, then watched going red against the real
tree and green against a real fix applied to a copy of the real files. The
mutation tests in `tests/test_stranger_gate.py` are the durable version of that
against synthetic trees; the real-file run is recorded under each leg below.

| # | Leg | Reads | Red today because |
|---|-----|-------|-------------------|
| 1 | THE HANDS ARE DOWNLOADABLE | **LIVE** | prod serves 0.8.4, app demands 0.11.0 |
| 2 | A DEPLOY WOULD SHIP THE SOURCE | tree | committed zip is 5 files stale against its own source |
| 3 | A FOREIGN NUMBER SURVIVES SIGN-UP | runs the shipped Swift | `e164("2079460958") == "+12079460958"` |
| 4 | ONBOARDING BELONGS TO THE ACCOUNT | tree | `@AppStorage("hasOnboarded")` is device-global and nothing clears it |
| 5 | ENROLLMENT IS OFFERED | tree | one presentation site, and it is Settings |
| 6 | THE FIRST WORDS RESPECT THE NIGHT | tree | `maybe_welcome_new_owner` consults no clock |
| 7 | THE VERIFIED RECEIPT IS WHAT IS SHOWN | tree | `AgentJob` never decodes `receipt` |
| 8 | THE DONE-TEXT CAN CARRY THE PHOTO | tree | no `MediaUrl` anywhere in the repo |
| 9 | THE GUIDE NAMES SCREENS THAT EXIST | **LIVE** + tree | guide sends the stranger to a deleted screen |

### Leg 1 — the hands are downloadable (LIVE)

Reproduced: `python3 overnight/is_it_live.py` reports `FAIL served 0.8.4, source
0.11.0` and `FAIL differs: served 251359 chars, source 340935`. Confirmed by
hand — `GET /anticipy-claude-version-extension.zip` returns a 12-file package
whose manifest says 0.8.4, while `AnticipyApp.expectedExtensionVersion` is
`0.11.0`. The banner tells the stranger to press Reload; Reload re-reads the
folder on disk and cannot fetch a version nobody serves.

The leg checks three things at once, because version equality alone was already
proved insufficient (0.8.2 once shipped with none of that day's code): the
served version equals the app's pin, the pin equals the source manifest, and
**every packaged file is byte-identical to `extension/`**. That last check is
also what makes the supervised-read dead end visible — the live package is
missing `supervised_read.js`, `config.js`, `side_trip.js` and four more, which
is why the mail read can never complete no matter what the app does. It also
re-runs `build-zip.sh`'s import belt: a package missing a module it imports
kills the MV3 worker at load.

Mutation, against the real `extension/` source: a zip built from the current
source served → **GREEN** (`serves 0.11.0, byte for byte the source the app
pins, 20 files`); the committed zip served → **RED** (`5 file(s) differ byte for
byte`). Six more shapes in the tests: version behind the pin, bytes differing,
missing imported module, pin rotted behind source, production unreachable, and
the pin constant renamed away.

Production unreachable is **red**, deliberately. This is the leg that exists to
read LIVE; with production down there is nothing to check.

### Leg 2 — a deploy would ship the source (tree)

Leg 1's instruction is "redeploy". This leg asks what a redeploy would actually
hand over. Reproduced: `backend/pb_public/anticipy-claude-version-extension.zip`
packs `agent_loop.js` at 320,430 bytes against a source of 346,286, plus
`config.js`, `side_trip.js`, `supervised_read.js` and `background.js` — while
`manifest.json` is byte-identical, so both report 0.11.0 and `staleExtension()`,
which compares numbers, can never see it. Deploying it would turn leg 1 green
while shipping code nobody wrote.

Mutation, real files: committed zip → **RED**; the same zip rebuilt from source
→ **GREEN** (`20 files, imports complete`).

### Leg 3 — a foreign number survives sign-up (executes the shipped Swift)

`AnticipySession.e164` prepends `+1` to any bare 10-digit number. Reproduced by
**running the shipped function**, not by reading it: the leg lifts `func e164`
out of `AnticipyApp.swift` by brace-balancing, compiles it standalone, and calls
it. `e164("2079460958")` — a real London landline — returns `"+12079460958"`.
`e164("07700900123")` returns `"+07700900123"`, and no E.164 country code begins
with 0, so that number cannot be dialled by anyone.

A grep for `"+1"` would have been the easy version and it is the wrong one: it
goes green the day the literal moves into a constant while the stranger's number
is still being rewritten. Executing the real function cannot be fooled that way.
When `swift` is not on PATH the leg **fails** rather than falling back to the
grep — stated in the message.

The leg also refuses the lazy fix: `e164("+442079460958")` must still come back
unchanged, so returning nil for everything is red.

Mutation, real file: shipped → **RED**; with the NANP branch replaced by `return
nil` and the `+0` case refused → **GREEN** (`2079460958 -> nil, 07700900123 ->
nil, and a fully-typed +44 survives`). Five shapes in the tests including
"refuses every foreign number" and "the function is gone".

### Leg 4 — onboarding belongs to the account (tree)

`@AppStorage("hasOnboarded")` at `AnticipyApp.swift:9`, keyed by nothing.
Reproduced: the routing branch is `else if hasOnboarded { HomeView() }`, and
`grep -rn hasOnboarded app/ios --include=*.swift` finds it in exactly four
places — the declaration, the routing, `hasOnboarded = true` on finish, and
`Button("Replay it") { hasOnboarded = false }` in Settings. Nothing in
`signOut`, `signIn` or `createAccount` touches it.

The leg follows the flag the App actually routes on to its declaration rather
than assuming a name, and accepts **either** shape of fix: an account-derived
key, or a clear in the account lifecycle.

The first draft of this leg had a real bug the mutation tests caught: it read
the key with `@AppStorage\(([^)]*)\)`, which stops at the first `)` — so an
account-scoped key of `"hasOnboarded-\(accountID)"` made the leg report "cannot
find the declaration" and go **red on the very fix it was asking for**. It now
balances parentheses. That is precisely the 3am wrong fire the brief warned
about, found by writing the green test.

Mutation, real file: shipped → **RED**; `removeObject(forKey: "hasOnboarded")`
added to `signOut` → **GREEN**; key changed to `"hasOnboarded-\(accountID)"` →
**GREEN**. A test also proves the leg is *not* satisfied by Settings' "Replay
it" button, which writes the same flag and is not an account boundary.

### Leg 5 — enrollment is offered (tree)

Reproduced: `grep -rn VoiceEnrollView app/ios --include=*.swift` outside
`build/` returns the definition and **one** other line —
`SettingsView.swift:584`. Not onboarding, not the finale, not Home. The 26MB
`speaker-embedding.onnx` ships in every build.
`research/2026-08-24-engine-options.md:254` records the consequence as measured:
`speaker` 0%, cause "enrollment unreachable", confidence "Certain."

The leg enumerates every presentation site and requires one of them to be first
run — `OnboardingView.swift` or `OnboardingFinale.swift` — directly, or one hop
through an invite view those files put on screen (which is the planned fix:
`EnrollmentInvite.swift`, Task 4 of
`docs/superpowers/plans/2026-08-24-voice-capture.md`). It also fails if the
model stops shipping: offering a twelve-second read that can never produce a
profile is worse than not offering it.

Mutation, real files: shipped → **RED** (`one presentation site … SettingsView`);
a sheet added to `OnboardingView` → **GREEN**. Tests also cover the invite
indirection, no site at all, and the model missing.

### Leg 6 — the first words respect the night (tree)

Reproduced: `worker.py:53` declares `CLOCK_QUIET_START, CLOCK_QUIET_END = 22, 8`
and consults it in eight places. `maybe_welcome_new_owner` — the first text a
stranger ever receives — is not one of them, and neither is its call site on the
60-second profile beat at `worker.py:~3177`.

The leg accepts the guard inside the function, or **enclosing** the call: on the
call's own line, or within three lines above it at a strictly shallower indent,
which in Python means the call is inside it.

The mutation tests caught the first draft here too. It took a twelve-line
window, and went **green** on a synthetic worker where the only `CLOCK_QUIET`
was an unrelated night-digest check thirty lines away. That is the exact failure
this repo found four times on 2026-08-24 — a leg satisfied by a guard near the
sentence it meant to read. It now reads the *indent*, not the distance: a
`CLOCK_QUIET` line at the same indent as the call is a statement beside it, not
a guard around it, and there is a test pinning that.

Mutation, real file: shipped → **RED**; a quiet-hours return added at the top of
`maybe_welcome_new_owner` → **GREEN**.

### Leg 7 — the verified receipt is what is shown (tree)

Reproduced: `workflow_guard.pb.js:203-210` refuses any `done` transition without
a receipt whose `verified` is true, whose `effect_key` matches, and whose
`evidence` array is non-empty; `pb_migrations/1700000025_job_workflows.js:21`
adds the column. `struct AgentJob` (`AnticipyBackend.swift:5-31`) declares
sixteen fields and `receipt` is not one of them, and
`ContentView.swift:1889` feeds `job.result` into `JobReceiptPolicy.doneCard`.

The leg checks the server still demands it (if that stops being true the leg
says "re-point me" rather than going on asking the app to render something
nobody verifies), that `AgentJob` decodes it, and that the done-card call site
is fed it. Decoding a column nothing renders changes nothing a stranger sees, so
that middle state is red too, with its own message.

Mutation, real files: shipped → **RED**; `let receipt: String?` added to
`AgentJob` → still **RED** (`decoded but not rendered`); the doneCard call also
passed `job.receipt` → **GREEN**.

### Leg 8 — the done-text can carry the photo (tree)

Reproduced: `grep -rn MediaUrl --include=*.py --include=*.js --include=*.swift .`
returns nothing. `VoiceArm.text` posts `From`, `To`, `Body`.

The anchor is not a name this gate invented — `MediaUrl` is Twilio's own
parameter and the only way an image reaches a phone on this channel. The leg
reads the body of `text()` specifically, not the file: a test proves it is not
satisfied by a `MediaUrl` in the neighbouring `call()` method.

Mutation, real file: shipped → **RED**; `MediaUrl` added to the POST data →
**GREEN**.

### Leg 9 — the guide names screens that exist (LIVE + tree)

Reproduced: `backend/pb_public/setup.html:237` tells the stranger *"You're
already on the right screen — the one headed 'Your hands on the computer.'"*
That screen was deleted when the browser left first run; `beatNames` is
`["Hello", "How I work", "May I listen?", "Where to reach you"]`. Line 243 says
to find *"Browser agent"* in Settings; the section is `Section("Your computer")`.
`extension/onboarding.html` repeats the first one.

**This is worse than the audit recorded:** the audit read it as live-only drift
("the live setup.html is itself the older page"). It is wrong in the tree as
well — the repo copy carries both dead pointers. Redeploying `pb_public` fixes
neither.

The two pointers are held BY NAME, the way `tape_gate` leg 3 holds the audited
five, because a leg that tried to find dead pointers in prose by pattern would
match nothing and pass in silence. Each is cross-checked against the app on
every run: bring the screen back and the item retires itself without anybody
editing the gate. Both the tree copy and the deployed copy are checked, and
production unreachable is red.

Mutation, real files: shipped guide → **RED** (five findings: tree, extension
copy, and both deployed); guide rewritten **and** the rewrite deployed →
**GREEN**; guide rewritten but **not** deployed → **RED** (Law 3). Tests also
cover the screen coming back, and `beatNames` being renamed away.

---

## What is NOT pinned, and why

**Four of the nine dead ends are deliberately left to a human.** A leg that
cannot fail is worse than no leg — and so is a leg that fires wrongly.

1. **Dead end 4 — no consent artifact, no `STOP` handler, no A2P 10DLC.**
   10DLC registration is not a repo artifact at all; it lives in a Twilio
   console. `STOP` is handled by Twilio's own Advanced Opt-Out for many
   accounts, so a leg demanding a keyword branch in `sms.pb.js` could be
   demanding a bug. This one needs a person to look at the account and decide
   what the product's own record of consent should be. **It is the highest
   real-world exposure in the audit and it has no gate.**

2. **Dead end 5 — `MockTransport.send` returns truthy, so a credential-less
   worker records texts as delivered.** The honest fix is a *visible signal*
   (the feed must not say "I texted you" when the transport is a mock), not a
   return value. Pinning "MockTransport must return falsy" would be wrong —
   every test in the suite depends on it being usable — and pinning the feed's
   wording is a judgement about meaning, which Law 1 keeps away from patterns.
   Worth a leg once somebody decides what the signal is.

3. **Dead end 6 — nothing asks for the browser until an errand is already
   stuck** (`ContentView.swift:221-223` requires `!handling.isEmpty`). This is a
   *documented design decision*, not drift: `design/day-zero.md:237-239` moved
   the browser out of first run on purpose to protect the ~70-second budget, and
   `OnboardingView.swift:14-20` records it. The audit is right that it costs the
   stranger their first day; that is a product argument, and a gate is the wrong
   place to have it.

4. **UNDO, and the clean-day counter.** Both are certain absences — case
   -insensitive `undo` across all 45 Swift files returns comments and two
   strings that *deny* undo; `clean_day|cleanDay|"clean day"` returns three
   prose matches. But neither has an anchor. There is no column, no symbol, and
   no external API name to pin to — unlike `receipt` (a server-enforced column)
   or `MediaUrl` (Twilio's own parameter). A leg searching for `func undo` would
   be pinning a name **this gate invented**, and would fire wrongly the day
   somebody ships it as "Put it back". They stay in the walkthrough and in WIRE
   IT ALL until a design names them.

Also unpinned, and unpinnable from `overnight/`: everything in the audit's own
"what I could not determine without a device" — whether the cable install
succeeds, whether the provisioning profile outlives the week (a free profile
expires in 7 days, which is exactly the length of a stranger week), whether the
Twilio account is trial, and whether production's worker is this worker. The
gate prints all of this every run rather than letting a green be read as
complete — the habit copied from `tape_gate.py`.

---

## Which legs check LIVE, and which cannot

**LIVE:** legs 1 and 9. Both fail rather than pass when production is
unreachable, and there is a test for each proving it.

**Cannot check LIVE, stated plainly:**

- Legs 3, 4, 5 are about the **iOS app**, which has no served artifact — there
  is no URL to compare a build against. `is_the_brain_live.py` exists because
  the worker has the same problem. The only live proof for these is a device.
- Leg 6 is about the **worker**, same reason. Its guard could in principle be
  probed by watching a real welcome arrive at 2am, which is a week, not a gate.
- Leg 7's server half **is** effectively live-adjacent (`workflow_guard.pb.js`
  was probed as deployed by the walkthrough); its app half is not.
- Leg 2 is by definition about the tree — it is the pre-deploy check that makes
  leg 1 fixable.

Per Law 3: **five of nine legs going green proves the repo, not the product.**
Only legs 1 and 9 survive a bad deploy.

---

## What can only be fixed in a tree I do not hold

Everything this gate is red about, except leg 9's `backend/` half and leg 2's
artifact. Listed so nobody looks for it here:

- `app/ios/Anticipy/AnticipyApp.swift` — `e164` (leg 3) and `hasOnboarded`
  (leg 4).
- `app/ios/Anticipy/Views/OnboardingView.swift` — the enrollment invite (leg 5).
- `app/ios/Anticipy/Backend/AnticipyBackend.swift` + `Views/ContentView.swift` —
  decoding and rendering `receipt` (leg 7).
- `brain/worker.py` — the quiet-hours guard on `maybe_welcome_new_owner`
  (leg 6).
- `brain/voice_arm.py` — `MediaUrl` (leg 8).
- `extension/build-zip.sh` needs re-running and the result committed (leg 2),
  then the backend deployed (leg 1). Neither is a code change; both are the
  cheapest work in front of the stranger week, exactly as the walkthrough
  concluded.
- `backend/pb_public/setup.html` and `extension/onboarding.html` — the two dead
  pointers (leg 9). **Correction to the audit: this is a source bug, not only a
  deploy bug.** Both phrases are in the committed files.

Two further things found while reproducing, both worth someone's attention and
neither fixable from `overnight/`:

- **The audit's dead end 8 is half stale.** Its second cause — "`queueJob` never
  sets `workflow_id`, so a supervised read is invisible to the claim filter" —
  is true of the **live 0.8.4** extension. The *source* extension has a separate
  path for it (`extension/background.js:~1075` explains that the stale sweep
  filters `workflow_id!=""` and a supervised read carries no workflow, and
  handles it). So dead end 8 collapses into leg 1: deploy the current extension
  and it goes away. It is not a second bug to fix.
- **`is_it_live.py` fails on a dirty tree.** Its "no uncommitted changes
  masquerading as shipped" row is red whenever any agent is mid-edit, which on
  this branch is always. `stranger_gate` deliberately does not copy that check —
  it is a hygiene signal, not a stranger-facing one, and mixing it in would make
  the stranger scoreboard permanently red for a reason that has nothing to do
  with the stranger.

---

## Verification

- `python3 overnight/stranger_gate.py` — 9 legs, all red, first failure leg 1.
- `python3 overnight/tejas_gate.py` — **8/8 before and after.**
- `python3 overnight/tape_gate.py` — red by design, untouched, still red.
- `python3 -m pytest -q tests/test_stranger_gate.py` — **49 passed.**
- Full suite before this work: **1287 passed, 1 failed.** After:
  **1339 passed, 1 failed** — the same one,
  `tests/test_earls_live_failures.py::test_needs_user_questions_are_never_swallowed_into_fallback`,
  an assertion about `extension/agent_loop.js` that another agent is editing.
  Not mine, and red at baseline.

**Churn note, for whoever reads the git history.** Mid-session another agent's
uncommitted edit to `brain/orchestrator.py` removed `owner_is_party` while
`brain/anticipy_core.py` still imported it, which broke collection for 73 test
files and `tejas_gate` leg 2 for everyone. It resolved when they landed the
change; the numbers above are from after. Recorded because a bisect through this
window will find a tree that does not import, and it was not this work: nothing
in `overnight/stranger_gate.py` or `tests/test_stranger_gate.py` imports
`brain/` at all.
