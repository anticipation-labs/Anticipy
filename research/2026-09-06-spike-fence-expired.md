# The spike fence is red, and nothing has been running it

Found 2026-09-06 while landing the Composio connect fixes. Two separate
defects, one inside the other.

## 1. `spike/two-hands/test/` is run by NOTHING

Seventeen test files. No `package.json`, no runner script, no gate leg, no
mention in `app/ios/Tests/run_all.sh` or any `overnight/*.py`. Grepped the
whole repo for a caller and found only prose references.

Run by hand, sixteen exit 0 and one exits 1. The red one has presumably been
red for as long as it has been true, and nobody could have known.

This is the fourth suite today written and left outside CI. The first three
were caught the same way — by running the runner and counting, not by reading
it. **Writing a test and not wiring it is the default outcome, not the unusual
one.** Anything that adds a suite has to add the runner line in the same
change, and the reviewer's job is to run the runner and watch the number go up.

## 2. The one red leg: production imports the week-1 spike

`no_production_imports.test.ts` — "the spike fence" — asserts nothing outside
`spike/two-hands` imports anything inside it. It fails on eight files:

    migration/workers/src/connections/nudge.ts
    migration/workers/src/connections/provider.ts
    migration/workers/src/connections/store.ts
    migration/workers/src/connections/wiring.ts
    migration/workers/src/connections/words.ts
    migration/workers/src/connections/due.ts
    migration/workers/src/routes/connections_api.ts
    (+ two of that Worker's own test files)

All eight import ONE file: `spike/two-hands/src/connections/contract.ts`.
The other spike modules (`links.ts`, `policy.ts`, `words.ts`,
`provider_composio.ts`) are named only in prose — "ported from" — which the
fence deliberately permits and which is Law 4 working.

So the violation is narrow and real: **the live Connections feature is built on
a contract file that lives in a directory named `spike`.** That directory's own
README invites deleting it, it has no build step and no install, and its fence
says out loud that nothing outside may depend on it.

### Why this cannot be fixed by moving the file

The fence has two legs and they point opposite ways:

  - INBOUND: nothing outside the spike may import in.
  - OUTBOUND: nothing in the spike may import out — including npm, because the
    README's "clone it and run the tests" claim dies the day it needs an install.

`contract.ts` is imported by ~20 files INSIDE the spike and 8 OUTSIDE it. Move
it to `migration/` and the spike's twenty importers break OUTBOUND. Put it in a
neutral third directory and the spike breaks OUTBOUND anyway. There is no
location that satisfies both legs, because the fence was written on the premise
that these two worlds never share code.

### That premise expired

The fence's header states it plainly: *"the owner's rule for week 1 is one
sentence: nothing here touches the backend until week 2."* It is week 2. The
Connections feature shipped. The contract graduated.

The fence is not wrong — it is measuring a rule that has ended. That is a
different thing from tape, and it must not be fixed by softening the predicate
until it goes green.

## The decision this needs, and it is the owner's

Three options, in the order I would rank them:

1. **Graduate the contract, retire the spike's runtime.** `contract.ts` moves
   to `migration/workers/src/connections/`. The spike's `src/` is retired to a
   historical record; its 1000+ tests over `links`/`policy`/`words` were the
   proving ground for code that has since been ported into the Worker and is
   now covered by the Worker's own 539 checks. Cost: we lose spike-side
   coverage of anything NOT ported. Someone must diff before deleting.

2. **Split the contract in two.** The parts production needs (types, the
   `TRIGGER_SCORE`/`LEVEL_THRESHOLD`/`SNOOZE_DAYS` tables) move to the Worker;
   the spike keeps its own copy. Cost: two copies of the numbers that decide
   when a person is asked to connect something, drifting apart silently. I do
   not recommend this.

3. **Retire the INBOUND leg for `contract.ts` alone**, in the fence itself,
   naming the file and the reason, with the OUTBOUND leg untouched. Cheapest
   and most honest about what is actually true today. Cost: the fence no longer
   stops the ninth import, and the tenth.

I have not done any of them. Until one is chosen the leg stays red, which is
the correct state — red is the fence working.

## What I did do

Added `spike/two-hands/run_tests.sh` so the seventeen files are RUN. The suite
is now visible and currently reports 16 green, 1 red, for the reason above.
