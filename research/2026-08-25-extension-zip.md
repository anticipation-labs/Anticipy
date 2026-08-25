# The extension zip: rebuilt from source, and why a version number never saw it

2026-08-25 — closing legs 1 and 2 of `overnight/stranger_gate.py`.

## What was wrong

`backend/pb_public/anticipy-claude-version-extension.zip` was the artifact a
deploy would ship. Against `extension/` it was:

- **missing 1 file** — `private_places.js` (the second-door lock), and
- **stale in 5 more** — `agent_loop.js`, `background.js`, `config.js`,
  `side_trip.js`, `supervised_read.js` differed byte for byte from source.

Leg 2 named only the missing file, because `zip_against_source()` reports
`missing` before `differing`. The one-line failure understated the artifact by
five files. Worth remembering when reading any gate that stops at its first
predicate: the message is the first thing wrong, not everything wrong.

The zip was **not broken** — its internal import graph had zero unresolved
edges, so Chrome would have loaded it. It was simply an older build: the copy
of `agent_loop.js` inside it has **zero** references to `private_places`, while
the source's has four, including a static `} from "./private_places.js";` at
line 18. So the packaged extension ran fine with the second door absent.

And its `manifest.json` was **byte-identical to the source's**, both `0.11.0`.
Verified with `cmp`, exit 0.

That is the whole finding: **a version number is invariant under exactly the
change you want to detect.** It is a hand-written claim copied unchanged into
every build. The stale zip and the fresh source agreed on the number and
disagreed on the code, so `staleExtension()` — which compares numbers — could
never speak, and any deploy check comparing versions would have gone green
while production served code with the second door missing.

## The fix

`extension/build-zip.sh` was verified before being relied on, not after. It
derives the package from Chrome's own entry points — the manifest's service
worker, its popup, `onboarding.html`, then every relative import to a fixed
point, plus files pushed via `chrome.scripting.executeScript({files:[...]})`.
Nothing is remembered in a list. It then asserts the packed version matches
source and refuses to emit a zip with a broken module graph.

    sh extension/build-zip.sh

Result: 20 files, 271006 bytes, `0.11.0`.

    before  16758684a4f6d4fc947b488cafaf897efdfe1ec228083460c6bf07ced857560d  19 files  239409 B
    after   0299df7a7847d4544ff8f46177d1c517321254e558aeb4fd1a635578d4333787  20 files  271006 B

All three aliases (`anticipy-claude-version-extension.zip`,
`anticipy-extension.zip`, `anticipy-codex-version-extension.zip`) carry the
same bytes, as the script intends.

### Proof the rebuild fixed it — not the version, the content

The manifest version is `0.11.0` before AND after, so it proves nothing. What
was actually checked:

1. `private_places.js` is present in the zip (`test -f`, exit 0).
2. `agent_loop.js` **inside the zip** now carries the import:
   `18:} from "./private_places.js";`. `side_trip.js` inside the zip
   references it twice.
3. Every one of the 20 packaged files `cmp`s clean against its source file.
   **TOTAL_DIFFERING=0.** No subset, no orphan, no drift.
4. The build is byte-reproducible: two consecutive runs produced the identical
   SHA-256. This matters for the proposal below — a content hash is only a
   usable comparator if the same source always yields the same bytes.

## Gate: before -> after

    [1] THE HANDS ARE DOWNLOADABLE (LIVE)     FAIL -> FAIL   (unchanged, and cannot change here)
    [2] A DEPLOY WOULD SHIP THE SOURCE (tree) fail -> PASS

Leg 2 now reads: *"backend/pb_public/anticipy-claude-version-extension.zip is
extension/ at 0.11.0, 20 files, nothing Chrome reaches is missing, imports
complete."*

### Leg 1 is still red, and the rebuild did not touch it

Leg 1 reads **production**. Verified independently of the gate:

    GET https://backend-production-61e0a.up.railway.app/anticipy-claude-version-extension.zip
    HTTP 200, 122423 bytes, 12 files, manifest version 0.8.4
    sha256 0d8e0fe22f0eb0d8ce0632855d6edcf545ece508224285d695c8000c40b09ccb

Production serves **0.8.4 with 12 files**. The tree now has 0.11.0 with 20.
Nothing in this checkout changes what that URL returns. The stranger still
installs 0.8.4, the app still tells them to press Reload to get 0.11.0, and
Reload still re-reads a folder on their own disk. **Leg 1 closes on a deploy of
`backend/pb_public` and on nothing else** — HARNESS-LAWS Law 3: repo-green is
not done, and this repo has served stale code twice.

Not deployed here. That is the owner's call. After `railway up`, re-run
`python3 overnight/stranger_gate.py` — the gate, not the tests.

## What a deploy check should compare

The version check is exactly the kind of leg that passes while the thing it
guards is broken, so it is worth writing down what would not have.

**The failure mode, stated generally:** a deploy check must compare something
that *changes when the thing you fear changes*. A version string is written by
hand and copied verbatim by the build, so it is constant across every stale
build. It is not weak evidence of freshness; it is **zero** evidence. Note that
`build-zip.sh`'s own `PACKED != VERSION` assert is, within a single run, close
to a tautology — the build copied that file — so it catches a corrupted copy or
a hand-edited artifact, and must never be read as "this zip is current."

**What to compare instead: the bytes, along the whole chain.** There are three
links, and a check that verifies fewer than all three can pass while the
stranger's install is broken:

    source tree  ->  rebuild  ->  committed zip  ->  bytes production serves

- `source -> committed zip` is leg 2's job, and it now passes.
- `committed zip -> live` is unverified by anything today, and it is where the
  0.8.4 sits.

Since the build is reproducible, both links collapse into **one comparison**:
rebuild the zip from the checked-out source into a temp dir, take its SHA-256,
`GET` the live download URL, take that SHA-256, and require equality. One
equality subsumes version, missing files, stale files, orphaned files,
hand-edits, and a deploy that reported success while uploading nothing. It
cannot be satisfied by a number somebody typed.

**But a hash alone is not a report.** "Hashes differ" tells a tired person
nothing about what to do. On mismatch the check should print the per-file
verdict `zip_against_source()` already computes — missing / differing /
orphaned, plus unresolved imports in the packaged graph — because those name
the file to fix.

**Two specific holes to close in what exists now:**

- `overnight/is_it_live.py` compares live bytes for exactly one file,
  `agent_loop.js`. That is better than a version check and still would not have
  caught tonight's bug: `private_places.js` was **absent**, and an absent file
  is not a differing file. A single-file spot-check has the same shape of blind
  spot as a version check, only smaller. It should compare the full file set,
  not a representative.
- Nothing anywhere asserts `committed zip == rebuild-from-source-right-now`.
  Leg 2 compares the zip's *contents* to source, which is equivalent in
  practice, but the cheaper and more direct statement is: run the build, and
  fail if `git status` shows the artifact changed. A deploy should never be the
  thing that discovers the artifact was stale.

**One property worth preserving deliberately:** `build-zip.sh` normalizes
timestamps to 1980-01-01 and sorts entries so identical source yields an
identical SHA-256 on any machine. That reproducibility is load-bearing for
every hash comparison above. Anything that reintroduces build-time
nondeterminism — a timestamp, a filesystem ordering, a temp path in the
archive — silently turns the strongest available deploy check back into a
version string.

### A deploy check must prove it actually compared something

Added after the fact, because the near-miss is the same shape as the bug.

Any check of this kind ends in "unzip the artifact, walk the files, compare."
All three of those steps can silently do nothing, and a loop over nothing
reports no differences — which is indistinguishable from a clean artifact.
An audit on 2026-08-24 ran `unzip … && check …`, the unzip never ran, the
checker walked an empty directory, and it passed the bundle. (In zsh a `&&`
chain aborts when a glob matches nothing; the failure was invisible because
nothing printed.)

So the check must assert its own coverage, not just its own verdict:

- run the steps separately and read **each command's** exit code — not the
  exit code of a pipeline ending in `| tail` or `| head`, which is
  essentially always 0 and reports the pager's success, not the checker's;
- after extracting, assert the file count is **nonzero and equal to what the
  source closure expects** before comparing anything;
- have the check print `COMPARED=n` alongside its verdict, so "0 differences"
  can never be read without the number of files that produced it.

The verification behind this document was run that way: `COMPARED=20,
DIFFERING=0, ORPHANED=0`, against the bytes extracted from the committed git
object rather than the working tree. As a negative control the same loop was
pointed at an empty directory and reported `COMPARED=0`, failing its guard —
confirming the checker distinguishes "nothing wrong" from "nothing checked."

This generalizes past zips. A green leg means the predicate did not fire; it
does not mean the predicate ran. Coverage is part of the result.
