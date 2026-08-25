# The stranger gate searched for tokens; now it establishes behaviour

Fixes for the review in `.superpowers/sdd/stranger-gate-criticals.md` (review of
`edc08e61`). Scope held to `overnight/` and `tests/`, plus the count correction
in this gate's own report.

Files changed: `overnight/stranger_gate.py`, `tests/test_stranger_gate.py`,
`research/2026-08-24-stranger-gate.md`.

---

## The shape, which is what was actually wrong

Five of the six behavioural findings are one defect wearing five hats:

> **the leg searched for a TOKEN instead of establishing the BEHAVIOUR** —
> and a note documenting the absence contains the token.

That is why a `# TODO: honour CLOCK_QUIET…` retired the quiet-hours leg and a
`# NOTE: MediaUrl is not wired yet` retired the MediaUrl leg. Writing down that
the bug is still there was enough to make the gate say it was gone. Renaming a
literal into a constant did it. A sentence 200 characters past a call did it. A
comment naming a file did it.

The same defect fires the other way, and that half is worse: leg 6 went **RED**
on a real, working guard behind a helper name.

So the fix is not five patches. Leg 3 was already the proof of what a leg can
be — it lifts `func e164` out of `AnticipyApp.swift`, **compiles it and runs
it**, and asks the answer rather than the source. Every leg was moved as close
to that as its language allows:

| instead of | the leg now |
| --- | --- |
| searching a Python function's **text** for a name | reads its **syntax tree**, where comments and docstrings do not exist, and follows the calls it makes |
| searching Swift/JS **source** for a word | strips comments (and Xcode previews) first, so only shipped code answers |
| accepting any key that is **not a literal** | **resolves the constant** to the string it becomes, folding interpolation whose pieces are themselves constants |
| taking the **400 characters** after a call | **balances the parentheses** and reads the call's actual arguments |
| asking whether a view's name **appears** | asks whether it is **constructed** — in SwiftUI, put on screen |
| comparing only the files a zip **contains** | derives, from the manifest, **everything Chrome reaches**, and requires the package to contain it |
| trusting a **200** from production | requires the page to **be the guide** it claims to be |

Three shared helpers carry it: `strip_comments`, `balanced_args`/`split_args`,
and the `py_tree`/`py_functions`/`py_code_nodes` family. `strip_comments` was
verified against all 20 real Swift/JS files the gate reads: **zero non-comment
regions blanked**, length-preserving, idempotent.

---

## Every reproduction, before and after

Each was produced by mutating a **copy of the real file** and reading the leg's
verdict.

### C1 — leg 6 green on a comment that says the bug exists

Mutation: one line added to the real `maybe_welcome_new_owner` in
`brain/worker.py`.

```python
# TODO: honour CLOCK_QUIET_START/END here before we ever text a stranger.
```

```
BEFORE  baseline (real worker.py)   : RED  — "consults no clock"
BEFORE  + the TODO comment          : GREEN — "the welcome consults quiet hours before it speaks"
AFTER   baseline (real worker.py)   : RED  — "consults no clock"
AFTER   + the TODO comment          : RED  — "consults no clock"
```

### I7 — leg 6 red on the idiomatic correct fix (fixed first, per the brief)

Mutation: a real, working guard behind a helper — the natural shape, since
`worker.py` consults those constants in eight places.

```python
def _in_quiet_hours(now=None) -> bool:
    hour = time.localtime(now).tm_hour
    return CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END

def maybe_welcome_new_owner(...):
    if _in_quiet_hours(now): return False
```

```
BEFORE : RED  — "the very first text a stranger ever receives consults no clock"
AFTER  : GREEN — "the welcome consults quiet hours before it speaks —
                  a quiet-hours branch at brain/worker.py:244 that can stop the send"
```

The leg now asks one behavioural question: **can the clock stop this send?** It
accepts a quiet-dependent branch with an early exit, a quiet-dependent return, a
quiet-dependent local (`quiet = …; if quiet:`), a helper one or two calls deep,
or a branch that truly encloses the call — enclosure read off the tree rather
than off three lines of indentation. It still refuses a branch that consults the
clock and sends anyway (`if quiet: print("late")`), and it fails closed when
`worker.py` does not parse.

### C2 — leg 8 green on a comment saying `MediaUrl` is NOT wired

Mutation: one line in the real `text()` in `brain/voice_arm.py`.

```python
# NOTE: MediaUrl is not wired yet; see WIRE IT ALL step 1.
```

```
BEFORE  baseline    : RED  — "the outgoing text has no way to carry a picture"
BEFORE  + the NOTE  : GREEN — "the outgoing text can carry the evidence picture"
AFTER   baseline    : RED
AFTER   + the NOTE  : RED
AFTER   + MediaUrl actually in the posted payload : GREEN
```

The leg now finds the `Messages.json` POST in the tree, takes its `data=`
payload, and asks whether **that** can carry `MediaUrl` — as a dict key, as a
key written into a local before the post, or through a payload-builder function
it follows. A docstring inside that builder saying `MediaUrl is not wired yet`
does not answer (`py_code_nodes` drops bare string expressions).

### C3 — leg 4 green when the key literal moves into a constant

Mutation: `@AppStorage(OnboardingKeys.hasOnboarded)` plus
`static let hasOnboarded = "hasOnboarded"`. This is the failure **leg 3's own
comment predicts** — "the grep goes green the day the literal moves into a
constant" — reproduced inside the leg that was rewritten to fix it. The codebase
already writes keys that way (`@AppStorage(AppTheme.key)`), so it is the likely
accident, not a contrived one.

```
BEFORE  baseline                       : RED
BEFORE  + key moved into a constant    : GREEN — "a key that is not a device-global constant"
AFTER   baseline                       : RED
AFTER   + key moved into a constant    : RED  — "…which is the one string \"hasOnboarded\" on every install"
AFTER   + the constant is account-scoped : GREEN
AFTER   + the key interpolates a runtime accountID : GREEN
AFTER   + signOut removes the key      : GREEN
AFTER   + the key interpolates ANOTHER CONSTANT ("onboarded-\(Build.channel)") : RED
AFTER   + a key nothing declares       : RED (fails closed, "cannot follow")
```

The leg resolves the key to the string it becomes and folds interpolation whose
pieces are themselves constants, so "it interpolates" is no longer a free pass.
A `var` is deliberately **not** folded — `@AppStorage("accountID") var accountID
= ""` is a run-time value, and folding its default would turn the account-scoped
fix red, which is the same wrong fire as I7.

**Found while fixing, same disease, not in the review:** the lifecycle half took
`literal in lifecycle`, so a comment in `signOut` reading
`// hasOnboarded is deliberately NOT cleared here` turned leg 4 green
(reproduced: **GREEN before, RED after**). And a line-level "the name plus an
`=`" would have accepted `if hasOnboarded == true`. The leg now wants an actual
assignment to the flag or a removal/write of the key.

### I4 — leg 5 satisfied by first run merely NAMING a file

Mutation: one comment appended to the real `OnboardingView.swift`.

```swift
// Enrollment still lives in SettingsView() — not offered here.
```

```
BEFORE  baseline           : RED
BEFORE  + the comment      : GREEN — "first run offers enrollment through SettingsView"
AFTER   baseline           : RED
AFTER   + the comment      : RED
AFTER   first run constructs VoiceEnrollView       : GREEN — "presents enrollment directly"
AFTER   first run constructs an invite view        : GREEN — "through EnrollmentInvite"
AFTER   a PreviewProvider constructs it            : RED  (found while fixing)
AFTER   a file that only MENTIONS it in a comment  : RED — "NOTHING in the app presents it"
```

Presentation sites are now files that **construct** `VoiceEnrollView`, the hop
is to types the site file actually declares whose own body constructs it (not to
the file's name, which was only a guess at what it declares), and first run must
construct one of those. Xcode previews are blanked alongside comments: a
`PreviewProvider` builds every view in the app and ships to nobody, so a preview
would otherwise have been a door.

**A fail-open the fix would have opened, closed before shipping.** Once the hop
followed declared types, first run constructing `SettingsView()` — a "Settings"
button in onboarding — would have satisfied the leg, because `SettingsView`
declares a type that constructs `VoiceEnrollView`. That is the complaint, not
the repair: Settings is where enrollment already is, three scrolls down. The hop
skips `SETTINGS`, with a test.

### M8 — leg 7's 400-character window

```
BEFORE  baseline                                     : RED
BEFORE  receipt decoded, card unchanged              : RED
BEFORE  + a comment 200 chars away saying it is NOT rendered : GREEN
AFTER   the same three                               : RED, RED, RED
AFTER   the receipt actually passed to the card      : GREEN
AFTER   `evidence: rendered` where `let rendered = format(job.receipt)` : GREEN
AFTER   `placeholder: "no receipt yet"`              : RED
```

The leg balances the call's parentheses, splits its arguments, blanks string
contents, and follows a bare identifier one hop back to the `let` that computed
it — so a rendered `receiptText` counts and a sentence does not. The server-side
half now strips JS comments too, so a commented-out `receipt.verified` check
cannot keep the leg alive after the server stops demanding one.

### I5 — leg 9's LIVE half failing open on a wrong-shaped 200

```
BEFORE  tree clean + LIVE empty 200 body        : GREEN
BEFORE  tree clean + LIVE unrelated page        : GREEN
BEFORE  tree clean + LIVE the real broken page  : RED  (correct)
BEFORE  setup.html renamed away                 : GREEN (the tree half checked nothing)

AFTER   tree clean + LIVE empty 200 body        : RED — "is not the install guide: 0 bytes and no link to …"
AFTER   tree clean + LIVE unrelated page        : RED — "is not the install guide: 43 bytes …"
AFTER   tree clean + LIVE the real broken page  : RED  (unchanged)
AFTER   tree clean + LIVE the fixed guide       : GREEN
AFTER   setup.html renamed away                 : RED — "is not in this tree … move the leg with it"
```

Leg 1 never had this hole because it **parses** what it downloads. The shape
check here is the same idea and is not an arbitrary landmark: the setup page is
the page that hands a stranger the extension, so it must link `ZIP_NAME`. The
`continue` past a missing guide file is gone.

Also found while fixing: `_app_names` read `beatNames` and `Section("…")` out of
raw source, so a **commented-out** `beatNames = ["Your hands on the computer"]`
would have put a deleted screen back on the list of screens the app has and
retired the dead pointer that names it. Comments stripped; pinned by a test.

### M9 — leg 3 red on a modifier change

```
BEFORE  private / static / public nonisolated func e164( : RED — "could not find `func e164`"
AFTER   the same, plus `private static`                  : RED — "e164('2079460958') returns '+12079460958'"
                                                           (it compiled and RAN it)
AFTER   the fix behind `public func`                     : GREEN
```

It failed **closed**, which is the gate's rule — but a repair that fixed the
`+1` guess *and* marked the function private left the gate red on a fixed
product. All modifiers are now accepted and stripped before compiling.

---

## Judgement call 1 — what completeness means for a zip (I6)

**Reproduction.** A package containing only `manifest.json`:

```
BEFORE  leg 1 : GREEN — "serves 0.11.0, byte for byte the source the app pins, 1 files"
BEFORE  leg 2 : GREEN — "is extension/ at 0.11.0, 1 files, imports complete"
```

Every byte in it matched the source. It was still not the extension.

**The argument.** "The files it contains match" is a statement about the files
it contains, and a subset satisfies it vacuously. The 2026-08-13 failure —
`workflow_state.js` left out, MV3 worker dead at load, every fresh install
sitting forever with no pair code — was caught by the import belt only because
the missing file had an import edge pointing at it. Remove the edge and the
belt is blind, which is exactly the manifest-named case: `background.service_
worker` and `action.default_popup` are imported by nothing and loaded by Chrome.

**The answer adopted:** *a package is the source when every file in it IS the
source AND it contains everything the source declares it needs.* The authority
for "needs" is not a list — a hand-written list is the thing `build-zip.sh`'s
own comments say nobody can keep in step. It is **Chrome's entry points followed
to a fixed point**: the manifest's service worker, popup, icons, content scripts
and web-accessible resources; `<script src>` inside those pages; every relative
import; every file pushed in with `executeScript({files:[…]})`; every asset
named by a literal `chrome.runtime.getURL`. `source_closure()` is that
derivation, deliberately the same one `extension/build-zip.sh` uses, so the gate
and the builder cannot disagree.

```
AFTER   leg 1 vs a manifest-only zip   : RED — "a SUBSET of the extension: 19 file(s) …"
AFTER   leg 2 vs a manifest-only zip   : RED — same
AFTER   leg 1 vs the complete package  : GREEN — "all 20 files Chrome reaches from manifest.json"
AFTER   popup.html omitted (imported by nothing) : RED
AFTER   page_map.js omitted (injected, never imported) : RED
AFTER   a manifest naming no entry points : RED, fails closed
```

**It earned its keep on the first run.** Against the real tree, leg 2 now
reports that the committed zip is missing `private_places.js` — a module
`extension/agent_loop.js` imports today. The old belt could not see it: it reads
imports out of the **packaged** `agent_loop.js`, which is stale and does not
contain the import. The closure reads the **source**.

## Judgement call 2 — does the stale-prod sentence belong in the gate? (M11)

**Yes.** Every leg printed `(LIVE)` or `(tree)` and the footer named the
device-shaped blind spots, but READY said *"every prerequisite a machine can
check is standing"* and then talked only about devices and people. The one thing
a green here most needs qualifying — that seven of the nine legs read a
**tree**, and this repo has twice served something else — appeared only in a
research file nobody reads at the moment they read a green.

A blind spot that lives in the report is a blind spot for whoever did not read
the report. Law 3 exists because repo-green was mistaken for done twice. So
READY now says it, in front of the person who just earned the green:

```
READY — every prerequisite a machine can check is standing.
READ THAT NARROWLY: 7 of these 9 legs (legs 2, 3, 4, 5, 6, 7, 8) read THIS
TREE, not production. They prove the repo. Only legs 1 and 9 survive a
bad deploy, and production has served stale code twice — the
extension at 0.8.4 against an app demanding 0.11.0, and the
setup page. A green here is a green against code that may not
be running (HARNESS-LAWS Law 3: repo-green is not done).
Nor is it done. done_gate.py leg 6 still needs a real person
on their own accounts, carried through a real day.
```

The counts are **computed from `LEGS`**, never written down — a hand-written
number is precisely what rotted in M10. Two tests drive `main()` with a
synthetic `LEGS` and assert the arithmetic changes with it.

The footer also now names leg 6's one honest blind spot out loud: the leg
establishes that the clock **can** stop the welcome, not that the guard points
the right way. A backwards condition reads identically in a syntax tree;
separating them needs the clock moved, which is a running worker, not a gate.

## The corrected leg count (M10)

`research/2026-08-24-stranger-gate.md` said *"five of nine legs going green
proves the repo"* and its "Cannot check LIVE" enumeration named 2–7, omitting
**leg 8 entirely**. Corrected to **seven — legs 2, 3, 4, 5, 6, 7 and 8** — with
leg 8 given its reason alongside leg 6 (the worker has no served artifact), and
a dated note saying the number is now computed by the gate rather than
remembered in prose.

## The UNDO restraint stands

Untouched, and it is the principle the rest of this work is built on: *"a leg
searching for `func undo` would be pinning a name this gate invented, and would
fire wrongly the day somebody ships it as 'Put it back'."* C1–I4 are what
happens when a leg pins a token the product never committed to. Every anchor
added here is one the product or the platform already owns — Chrome's manifest
keys, Twilio's `MediaUrl`, the app's own `@AppStorage` key, the `ZIP_NAME` the
setup page already serves. No new names were invented.

---

## What could not be walked past, still standing

Re-verified after the rewrite, not assumed:

- **Leg 1's LIVE polarity.** `cannot verify` on every unreachable shape; version
  behind pin, pin rotted behind source, orphaned files, differing bytes, broken
  imports, no readable manifest version — all still red, each naming the URL.
- **Leg 3 compiles and runs the shipped `e164`** and refuses the lazy fix
  (`REFUSES_EVERYTHING` still red on "typed IN FULL").
- **Leg 4 reads which flag `AnticipyApp` routes on** and is still not satisfied
  by Settings' "Replay it" button.
- **Leg 5 fails closed** on a missing view, a missing 26MB model, a missing tree
  and zero presentation sites.
- **Leg 6's twelve-line-window bug stays gone** — and the sibling-at-the-same-
  indent and thirty-lines-away tests still pass against true enclosure.
- **Every `read()` path** still raises `LegFailed` with *"do not delete the leg,
  the check rots silently without it."*

## Can a leg still be talked out of its verdict?

Not by prose, a rename, a neighbouring sentence, a preview or a subset — those
are the ones pinned above, each in both directions. Three things a reader should
know are still true, stated rather than hidden:

1. **Polarity, leg 6.** The leg establishes that quiet hours *can* stop the
   welcome. A condition written backwards, or one made unreachable
   (`if False and CLOCK_QUIET_START <= hour: return False`), reads identically
   in a syntax tree. Separating them needs the clock moved — a running worker,
   not a gate. Printed in the footer every run.
2. **Leg 8 asks only that the parameter be plumbed** — `"MediaUrl": None` in
   the payload passes. That is its stated contract: whether the picture is the
   right one is a human's judgement, not a gate's.
3. **Leg 5's hop is one level.** First run → invite → enrollment passes; first
   run → A → B → enrollment does not. Deliberate: each hop is a place the leg
   could be fooled, and the leg's message names exactly what passes.

Everything else in each leg now fails closed: an unparseable `worker.py`, an
unresolvable `@AppStorage` key, a manifest naming no entry points, a missing
guide file, a `doneCard` whose parentheses do not close, a `text()` whose
payload cannot be read, `swift` off PATH, production unreachable.

## Verification

- `python3 overnight/stranger_gate.py` — **8 of 9 red, NOT READY, first failing
  leg 1.** Leg 3 is **green, and not by anything done here**: another agent
  landed `DiallingCode.swift` and removed the `+1` guess mid-session. Proven
  rather than asserted — today's gate against the **committed** `AnticipyApp
  .swift` is RED (`e164('2079460958') returns '+12079460958'`) and against the
  **working tree** is GREEN (`2079460958 -> nil`). The leg went green because
  the product got fixed, which is the leg working.
- `python3 -m pytest -q tests/test_stranger_gate.py` — **91 passed** (was 49).
  42 new mutation tests, every one of them a colour watched in both directions.
- `python3 overnight/tejas_gate.py` — **8/8.**
- `python3 overnight/tape_gate.py` — red by design, untouched (exit 2).
  `overnight/consolidation_gate.py` — red by design, untouched (exit 1).
- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
  --ignore=tests/test_day_zero_oracle.py -p no:cacheprovider` — **1596 passed,
  0 failed** at commit time. Mid-session it read 1576 passed / 1 failed, the
  one being `tests/test_evidence_host.py` against a
  `backend/pb_hooks/evidence.pb.js` another agent had not landed yet; it went
  green when they landed it. Nothing in `overnight/stranger_gate.py` or
  `tests/test_stranger_gate.py` is imported by it.
- `strip_comments` proven on all 20 real Swift/JS files the gate reads: zero
  non-comment regions blanked, length-preserving, idempotent.

## What is left for another tree

Unchanged from the original report — everything this gate is red about lives
outside `overnight/`:

- `app/ios/Anticipy/AnticipyApp.swift` — `hasOnboarded` is still one string for
  the whole phone (leg 4). Either key it to the account or clear it in the
  lifecycle. (`e164`, leg 3, is now **done**.)
- `app/ios/Anticipy/Views/OnboardingView.swift` — the enrollment invite (leg 5).
  The leg accepts either first run constructing `VoiceEnrollView` or first run
  constructing a view that does.
- `app/ios/Anticipy/Backend/AnticipyBackend.swift` + `Views/ContentView.swift` —
  decode `receipt` and pass it to `JobReceiptPolicy.doneCard` (leg 7).
- `brain/worker.py` — the quiet-hours guard on `maybe_welcome_new_owner`
  (leg 6). **A helper is fine now**; the branch only has to be able to stop the
  send. A held welcome must still go out in the morning.
- `brain/voice_arm.py` — `MediaUrl` in the `Messages.json` payload (leg 8). A
  payload builder is fine; the leg follows it.
- `extension/build-zip.sh` needs re-running and the result committed (leg 2) —
  **and it is now more urgent than the report knew**: the committed zip is not
  just five files stale, it is missing `private_places.js` entirely, so
  deploying it as-is would ship an extension whose `agent_loop.js` imports a
  module Chrome cannot find. Then deploy the backend (leg 1).
- `backend/pb_public/setup.html` and `extension/onboarding.html` — the two dead
  pointers, in the tree and in production (leg 9).
