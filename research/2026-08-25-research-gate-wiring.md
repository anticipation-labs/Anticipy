# The research gate has a caller — where the procedure store lives, and what the hold costs

Date: 2026-08-25 · Branch: `jose_anticipy_system`
Spec: `docs/superpowers/specs/2026-08-25-hands1-skills-reach.md` §4, §5
Prior build: `research/2026-08-25-hands1-build.md` §3.1–3.4 (what was named and not built)
Laws that bind: `HARNESS-LAWS.md` 1, 2, 3, 4, 6

**Status.** `brain/research.py:research_gate` now has a production caller whose
verdict decides whether a browser may claim the row.
`tests/test_research_gate.py::test_UNWIRED_the_research_gate_is_not_called_by_
anything_that_runs` is **GREEN**, and green because the gate is in the path, not
because its name was written down — its sibling leg
(`test_the_unwired_leg_is_not_fooled_by_the_gate_being_MENTIONED`) is what makes
that a distinction the scanner can hold.

**And none of it is verified against LIVE, so by Law 3 all of it is a claim.**
§6 lists exactly which legs would have to go green against production before any
of this counts. Nothing here was deployed.

---

## 1. The open question, settled: the procedure store is owner-scoped, and it is SQLite

Spec §4.3 called this "the one genuinely open question" and recommended
owner-scoped first. §4.4 priced a PocketBase collection at a migration plus
three registration points. **It is neither of those halves quite as written:
the store is owner-scoped, and the backing is the per-owner SQLite the worker
already opens, not a new collection.**

`brain/memory.py` — a new `procedures` table in `SCHEMA`, one row per shape, and
a `ProcedureStore` adapter reachable as `Memory.procedures()`.

### Why owner-scoped

§4.3's own argument, taken as it stands. An un-owned shared store is the better
object — it holds only public-web knowledge, it has nothing personal to delete,
and the second owner to dispute a Hydro bill pays nothing — **and it is a
cross-owner poisoning surface where the per-profile version is not.** The blast
radius of a bad procedure is misdirection about where to open, contained by the
fence, the exclusion from approved scope, and `is_researchable` re-checked on
the model's own `start_url` by the caller. "Containable for one owner" and
"containable for all of them" are different sentences, and the second is
unproven. The product has one owner, so the compounding across owners is worth
exactly nothing today. Ship the reach; earn the sharing.

**The scoping is the FILE, not a column.** One SQLite per owner
(`brain/supervisor.py:93`, mode 0o700). Nobody has to remember to add a
`WHERE owner = ?`; two owners are two databases.

### Why SQLite rather than the collection §4.4 priced

Every one of §4.4's four costs is paid by somebody remembering, and this store
avoids all four:

| §4.4's cost | PocketBase collection | Per-owner SQLite |
|---|---|---|
| the migration | one file, 48→49 | `CREATE TABLE IF NOT EXISTS` reaches an existing database — how `vetoed_facts` shipped |
| `guard.pb.js:416` hard-coded list | absent from it = 403 to the phone | not a collection; nothing to register |
| `account_delete.pb.js` `OWNER_TABLES` | a table missed here left personal residue surviving a delete (that file's own header) | deleted by the delete that removes the owner's directory |
| a retention sweep | 5 GB volume, filled once, every byte charged ~8× by backup rotation | `MAX_PROCEDURES = 60` + the 30-day TTL, both already in `research.py` |

The store speaks `get`/`set` on one key holding one map — **the interface
`chrome.storage.local` gives the browser half** — because `brain/research.py` is
a PORT of `extension/learn.js`, and a port that has to be handed a
different-shaped store is not a port any more, it is a second implementation.
The rows underneath are per-shape so `sources` stays queryable; provenance
nobody can inspect is provenance in name only (§4.3 leans on inspectability).

### What it costs if this is wrong

Three things, and all three are recoverable:

1. **No compounding across owners.** Owner two pays for research owner one
   already paid for. Costs one Brave search + one model call per shape, per
   owner, per 30 days. Worth nothing today (one owner); worth something at scale,
   and that is the measurement whoever revisits this has to bring.
2. **A procedure dies with the owner's state volume**, where a collection would
   survive in `pb_data`. Bounded at 60 shapes / 30 days, and ordinary use rebuilds
   it — the same "small recoverable loss" §4.2 accepts for recipes.
3. **A future shared store is a swap, not a rewrite.** `remember_procedure` and
   `recall_procedure` take an injected store; moving to a collection means
   writing a second adapter and paying §4.4's four costs. Nothing about the
   record format changes. **Whoever does it must name what changed about the
   poisoning argument, not merely that it would be cheaper.**

---

## 2. The wiring: `brain/anticipy_core.py`, at the one line that mints a row

`Anticipy._research_gate(goal, touches, lane)` → `(GateVerdict, procedure)`,
called from `_queue_job` immediately after `lane = job_lane(goal, params)`.

```
recall (free sift, then the model floor)  ->  research_gate(touches, procedure, gate_can_run)
       gate_holds_the_browser(verdict)    ->  lane = RESEARCH_LANE
       verdict + why + procedure          ->  params, on the row
```

**Law 1 is structural here, not promised.** The gate takes no goal parameter, so
it cannot read prose it was never handed; `test_the_gate_is_never_handed_the_goal`
asserts the goal string appears nowhere in what the gate was called with. The
goal is used on the way IN — to build the shape key, and to ask the one question
about whether a remembered procedure applies — which is a lookup's job and a
model's, never a decision made by reading the words.

**Where it sits in `_queue_job`.** After the whole dedupe/merge ladder, on the
mint path only. Not one line of the retraction / open-plan / lineage-sibling /
`_same_pending` / `_refines_pending` sequence was touched, and
`test_the_gate_is_not_asked_at_all_on_a_merge` pins that a card assembled over
five turns buys one gate, not five, and cannot have its lane rewritten by the
last fragment of the conversation.

### The hold reuses `lane="research"`, deliberately

§5.5 names two enforcement points any third lane value must be added to, and
that is the trap: **a new lane string is excluded by neither.**
`research_lane.pb.js:101` only rewrites polls that do not mention `lane`, and the
shipped extension's own filter says `lane!="research"` — so a `research_first`
lane would be claimable by every extension in the wild, including the ones that
can never be updated. Client code cannot be recalled.

So the hold uses the one value both points already exclude. What distinguishes a
parked browser errand from a genuine read-only question on that lane is
`params._research_gate.handback`, written by the worker at mint on a lane no
claimant can reach. A flag is only admissible because
`research_lane.pb.js` refuses every browser claim there — nothing that could
benefit from setting it can get at the row.

### And a gate in front of the research lane would be a loop

`_research_gate` returns `NOT_REQUIRED` when `lane` is already non-empty. Without
that guard an undeclared read-only lookup — which `job_lane` correctly sent to
the server's own arm — would be marked `handback`, researched, and handed to his
Chrome. That is the 2026-08-02 tab flood, minted by the thing that exists to
prevent tab floods. It is the mutation that survived the first round (§4, M7) and
`test_an_undeclared_LOOKUP_is_not_marked_as_a_held_browser_errand` is the leg
added because it did.

---

## 3. The other half: the hold has to let go

A hold with no release is a parked errand, and a parked errand is worse than an
unresearched one — worse *silently*. `brain/worker.py:run_preflight_research`
polls the research lane, and for every marked row:

- reads how the task is done (`learn_procedure`, the goal as the question — only
  the QUESTION travels, never the row's `source`, which is a transcript);
- writes it into the owner's store, so the next errand of that shape is free;
- hands it to the row as `params.procedure`;
- clears the marker and **PATCHes the row back to the browser lane.**

**It hands back on every path.** Researched, blank, keyless, model-less, or
crashed mid-read. Nothing is claimed — no lease, no `claimed_by`, no workflow
transition — because this annotates a queued row rather than executing a plan,
so a worker dying mid-read costs nothing and nothing has to sweep up after it
the way `release_stranded_research` sweeps up after a claim.

`run_research_jobs` skips marked rows, and runs after the pre-flight. Two layers,
so one failing does not reopen the hole — the doctrine `research_lane.pb.js`'s
own header states. **The uncovered bug that leg found: before the skip existed,
`run_research_jobs` would answer a held booking with a summary of the open web
and mark it `done`.** An errand that never happened, reported as finished.

### And the hands have to receive it

Without the browser reading `params.procedure` the pre-flight is pure cost: the
run would wait for the server to read the pages and then pay to read them again,
on his machine. So:

- `extension/learn.js` — `cleanProcedure()`, extracted from `learnProcedure`'s
  tail so there is **one door**, not a second cleaner. The twin of
  `_clean_procedure` in `brain/research.py`, field for field. Every field copied
  by name, no spread, the `start_url` re-checked rather than inherited.
- `extension/agent_loop.js` — on a local cache miss, a downlinked procedure goes
  through that door, is *stored*, and is then **read back out of the cache**, so
  `recallProcedure`'s liveness rules decide whether it counts exactly as they do
  for anything else. Storing it is not a side effect: the shape has been paid for.
- `extension/background.js` — `procedure` passed through from params, and added to
  `ownerFactsFromParams`'s NEVER list. It is an object, so the type filter drops
  it today; named anyway, because "it happens not to be a string" is not a rule
  anybody can rely on.

Nothing is widened on the browser credential. This is the surface `params.memory`
already uses (§4.5).

---

## 4. What is proven, and how

Every new file was RED before its implementation existed. Beyond that, eight
line-level mutations, each applied in place, run, and restored **from a `cp`
backup** — see §7, the process failure.

| # | Mutation | Result |
|---|---|---|
| M1 | `lane = RESEARCH_LANE` removed — the hold itself | 4 failed |
| M2 | `gate.pop("handback")` removed — the marker is never cleared | 2 failed |
| M3 | `run_research_jobs`'s skip removed | 1 failed (the research arm answers a booking) |
| M4 | downlinked `start_url` trusted instead of re-checked | 2 failed (loopback + bank) |
| M5 | the store answers any key | 1 failed |
| M6 | `can_run` forced true — a dead gate holds | 2 failed |
| M7 | the `if lane:` guard removed | **SURVIVED** — see below |
| M8 | the answering model asked the stripped string again | 1 failed |

**M7 survived the first round and that is the most useful thing in this table.**
The behaviour was real and had no leg that could fail: a declared read reached
`NOT_REQUIRED` by a different route, so the guard was invisible.
`test_an_undeclared_LOOKUP_is_not_marked_as_a_held_browser_errand` was written
for it and M7 now fails.

**Counts, with the exit code of the command and not of a `tail`:**

- `python3 -m pytest tests/ --ignore=tests/test_day_zero_oracle.py` →
  **2169 passed, exit 0** (baseline before this work: 1 failed, 2136 passed,
  exit 1 — the one failure being the UNWIRED leg). `test_day_zero_oracle.py`
  cannot be collected in this environment (`ModuleNotFoundError: playwright`),
  which is pre-existing and unrelated.
- `node extension/tests/run_all.mjs` → **65/66 suites pass, exit 1**. The one
  failure is `test_account_delete_flow` (24 checks, "no such collection:
  evidence"), pre-existing since `0d2ee640`; it reads only
  `backend/pb_hooks/*.pb.js`, and this diff touches no backend file.

**The scoreboards, unchanged by this work** — every failing leg is outside the
diff:

- `overnight/tejas_gate.py` → exit 1, first failing leg 6 (the speaker engine is
  not linked into the Xcode target).
- `overnight/done_gate.py` → exit 1, first failing leg 6 (no cold stranger has
  been carried through a real day).
- `overnight/tape_gate.py` → exit 2. Leg 2 RED by design; leg 3 RED (the audited
  five are still undeclared) — both pre-existing. **Leg 1 passes: no new marker,
  none orphaned.** No tape was added by this work: no regex, no word list and no
  threshold decides anything here.

---

## 5. The `_QUERY_PREFIX` repair, reviewed — right, and incomplete

Asked to confirm commit `5189e777` rather than assume it. **The direction is
right and the four measured regressions are gone**, checked by running it rather
than reading it:

```
"Compare the two quotes from the movers" -> unchanged
"Price check the Sony a7 IV"             -> unchanged
"check on my passport application"       -> unchanged
"Find me a dentist open Saturdays"       -> unchanged
"research: opening hours of the aquarium" -> "opening hours of the aquarium"
"researching: the market" / "priced: the item" / "checkers: the game" -> unchanged
```

The mandatory separator is the right rule and its pin
(`test_the_separator_is_mandatory_not_optional`, which asserts the `?` cannot
come back) is the right shape for a leg. The docstring's honesty about `or g`
and `count=1` being unreachable is exactly what Law 4 asks for.

**But the repair stopped one line short, and the residual is the same defect.**
`run_research` handed the stripped string to *both* Brave and `_summarize` — so
the question the answering model was asked had been rewritten by the word list:

```
"compare: the two quotes from the movers"
  -> Brave gets      "the two quotes from the movers"    (right — search terms are plumbing)
  -> the model was ASKED "the two quotes from the movers" (wrong — comparing IS the task)
```

Which is the original failure exactly, now needing a colon to reach. Deciding
what string goes into a search engine is the carve-out Law 1 makes for senses;
deciding what question gets answered is meaning. **Fixed** (`asked` = the goal;
`query` still goes to Brave), with a leg that fails when it is undone (M8).

Two smaller findings, recorded and **not** fixed, because neither is a Law-1
question and both are cheaper to leave than to churn:

- `research:opening hours` (no space after the colon) is not stripped. The
  pattern requires `\s+` after the separator. Costs one un-stripped label on a
  search Brave tolerates.
- The separator class is `[:\-—]`; an en-dash `–` (U+2013) is not in it.

One thing fixed in passing: the docstring is now `r"""`, which removes a
`SyntaxWarning: invalid escape sequence \s` that the repair introduced and that
a future Python will make an error.

---

## 6. What is NOT done, and what would have to be true for this to count (Law 3)

**Nothing here has run against production.** The legs that would have to go green:

1. A world-touching job minted in production carries `params._research_gate` with
   `verdict: "research"` and `lane: "research"`, and no extension claims it.
2. The same row appears on `lane: ""` on a later pass with
   `_research_gate.handback` gone and `_research_gate.researched` recorded either
   way. **The hold letting go is the leg that matters most; a red here is a
   parked errand.**
3. A second errand of the same shape returns `verdict: "satisfied"` with no
   research pass in the worker log.
4. A row's `params.procedure` appears in the run's history as
   `agent: the server looked this up before handing it over`.
5. `BRAVE_API_KEY` absent in production ⇒ every verdict is `open` and no row is
   ever held. **This is the safe default and should be checked first**, because
   it is the state a key rotation puts the product in.

**Known limits, named rather than discovered later:**

- **The blast radius of the polarity.** §5.4 says an undeclared goal researches,
  and four of the six `_queue_job` call sites pass no `touches`. In production
  with a live model and a Brave key, most first-run browser errands will now pay
  one research pass. That is the card's "research, ALWAYS", and it is affordable
  only because recall stopped being gated — but it is a real change in what the
  product spends, and §7 of the spec pre-registers the abandonment rule:
  *if first-run `needs_user` on world-touching shapes does not fall and
  first-run steps-to-`done` does not fall, remove the gate rather than widen it.*
  Nothing measures that yet. The single missing quantity is "was a procedure in
  hand", which `_research_gate.researched` now puts on the row — the counter is
  not built.
- **A held row raises no stall notice.** `report_stalled_work` skips this lane,
  correctly, because the errand does not need his browser yet. If the handback
  PATCH fails repeatedly the row is stuck with a log line and no text. The log
  line says so by name.
- **A merged card keeps the procedure the mint recalled.** `_merge_into` writes
  `dict(cur_params, **params)`, so `procedure` and `_research_gate` survive a
  merge that changed the goal — the same behaviour `capture_source` and `memory`
  already have, and for the same reason. The extension then caches that record
  under the *merged* goal's shape. The server-side floor would refuse it on a
  later recall; the browser-side copy would not. Contained by the same
  `is_researchable` re-check everything else is, and worth closing when §6 aging
  is built.
- **Spec §6 (aging: degrade, do not delete) and §7 (the hold-out) are still not
  built**, exactly as `research/2026-08-25-hands1-build.md` §3.5 left them.
- **The three registered pieces of tape in `job_lane`'s path are untouched.**
  `_READ_ONLY_RE` still decides browser-vs-research routing. This gate does not
  consult it and does not inherit it (§5.4) — it is a second question asked of
  the same row, and retiring the tape is still the effect-channel rewrite's job.

---

## 7. Process (Law 6)

One failure worth writing down, because the next agent will be told the same
thing and may make the same mistake. Restoring a mutation with
`git checkout -- <path>` **discarded every uncommitted change in that file**, not
just the mutation — the whole `anticipy_core.py` wiring, silently, with a clean
`git status` as the only symptom. The task brief warned that `git checkout --`
does not restore an untracked file; the sharper version of that rule is that on a
*tracked* file it restores HEAD, which is worse, because it looks like it worked.
Everything after that point was backed up with `cp` first and restored from the
copy. Eight mutations, no further loss.

---

## 8. The served bytes, and the half of the staleness this does not close

Editing `extension/` makes `backend/pb_public/*.zip` — what users actually
install — stale against the source. Rebuilt with `sh extension/build-zip.sh`
(commit 4, below), and verified by unzipping rather than by byte count: the
packed `learn.js` carries `cleanProcedure` and the packed `agent_loop.js` carries
the downlink.

**The version is still 0.11.0, and that is the half left open.**
`staleExtension()` compares NUMBERS, so an install already on 0.11.0 cannot see
that the 0.11.0 it holds is different code — which is the exact shape of the
2026-08-11 failure (0.3.3 served against 0.3.9 in source, with the documented
repair path *downgrading* him into bugs he had just been told were fixed).
Closing it means bumping three hand-copied values —
`extension/manifest.json`, `app/ios/Anticipy/AnticipyApp.swift`,
`app/ios/Tests/StaleExtensionTests.swift`, held together by
`tests/test_extension_version_pin.py` — and that is a release decision, in the
iOS app, well outside this task. **Flagged, not taken.** Until it is taken, §6's
leg 4 (a run's history saying `the server looked this up before handing it over`)
can only be checked on a fresh install.
