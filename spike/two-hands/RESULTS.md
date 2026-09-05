# Two Hands — week 1, what is proven and what is not

**Verdict: UNPROVEN.** `tasks/run_ten.ts` exits 2 and prints UNPROVEN, today,
on this machine, because there is no Composio account, no connected app and no
`COMPOSIO_API_KEY`. That is the honest steady state, it is not a soft fail, and
it is not a pass. HARNESS-LAWS law 3: *nothing is fixed until its gate leg is
green against the LIVE system*, and this is further back than repo-green — it
is a gate that has never had a live system to run against.

Everything below is split along that line, because the whole failure mode this
repo keeps repeating is a green suite being read as a working product.

---

## 1. What IS proven

Everything in this section is settled by tests that need no key, no account and
no network:

    cd spike/two-hands && node --experimental-strip-types --test test/*.test.ts

**The run below is a measurement with a date on it, not a property of the
directory. Re-run it before quoting it.** Measured 2026-09-05 15:52 local:
**507 tests, 506 pass, 1 fail** — and the one red is named at the bottom of this
section rather than rounded off, because a count in a results file that nobody
re-ran is the same defect class as a green leg that proves nothing. Four suites
were being written to in the same round this was measured in, so a re-run
minutes later legitimately returns different numbers; the command is the
authority and this table is a snapshot of it.

| suite | tests | what it settles |
|---|---:|---|
| `test/signature.test.ts` | 33 | one step hashes the same way twice, everywhere; and the effect-channel floor |
| `test/provider_fake.test.ts` | 49 | every vendor failure mode is reachable without a vendor |
| `test/provider_composio.test.ts` | 53 | the adapter's shape, against the docs — **not** against Composio |
| `test/router.test.ts` | 102 | the five routing rules, including that a score never licenses a hand |
| `test/ledger.test.ts` | 77 | the ladder climbs on outcomes and falls on failures |
| `test/observer.test.ts` | 66 | hosts and counts leave the extension; bodies, titles and URLs do not |
| `test/onboarding.test.ts` | 95 | when to ask, how often, and what the message may promise |
| `test/integration.test.ts` | 8 | the seven parts are true at the same time, plus the defects still pinned |
| `test/no_production_imports.test.ts` | 8 | the spike fence, both directions, with legs driven against violations planted in the tree |
| `test/run_ten.test.ts` | 16 | the week-1 gate's key-free half: the ten load, and no placeholder — any case, padded or not — survives a fill |

**The one red leg, and it is red for the RIGHT reason:**

- `observer.test.ts` — "the finished-step lifecycle is wired by shipped code, not
  only by this file". `summarizeAndForget` is exported and documented as the call
  a finished step should use, and nothing the spike ships calls it: the one site
  that knows a browser step is over is `browserOutcome` in `src/index.ts`, and it
  calls plain `summarize`, so the trace it just read stays in the service worker.
  The leg closes by WIRING it, never by relaxing the assertion. Nobody owned
  `src/index.ts` in the 2026-09-05 round, which is exactly why it is still red.

**The two red legs this section used to name are both closed, and neither was
closed by relaxing an assertion.** They are recorded because the way each one
went red is the argument for keeping legs like the one above:

- `signature.test.ts` — "verifySignatureHash is called by shipped code, not only
  by this file" was red because the guard against a swapped `signature_hash` was
  exported, documented, and called by nothing. It is now wired in `src/router.ts`
  (~:743): a signature whose hash this process cannot re-derive gets rung 0 and
  never the API hand, because a hash we cannot reproduce means we do not know
  WHICH capability this is, and an unknown capability has earned nothing. Note
  the shape it shares with the red leg above — same defect, same fix, one file
  apart.
- `integration.test.ts` — the story's rung-3 write step pinned FINDING 2 below
  at the wrong answer (`requiresConfirmation === undefined`). The router now
  sets the flag, the pin went red on the next full run, and the assertion was
  flipped to `true` rather than the behaviour reverted. That is a pin doing the
  job a TODO cannot: it noticed. See §5 FINDING 2 for what is and is not fixed.

Three claims in that list are worth stating on their own, because they are the
ones the exercise was actually for:

1. **No pattern decides a routing outcome.** Stated narrowly, because the
   sentence that stood here — "there is no app list, no verb list and no
   `match_threshold` anywhere in `src/`" — was too wide, and the code moved
   under it until it was false. There is no app list and no `match_threshold`;
   `match_threshold` appears once in `src/`, inside `contract.ts`'s LAW1 note,
   quoting the line of the spec it declines to follow. **There are two verb
   lists, both in `src/signature.ts`, and one of them has real consequences.**
   `VERBS` validates the enum at run time (types are stripped, so it is the
   only thing making `sig.verb` mean anything). `verbSideEffectFloor` maps a
   verb to an effect channel: `send`, `delete` and `pay` floor to
   `irreversible`, everything but `read` to `write`. It is legal under
   HARNESS-LAWS law 1 for what it decides — not what the owner meant, but what
   a step TOUCHES — which is the seatbelt clause verbatim; and it is a FLOOR, so
   a planner may ratchet a step stricter by declaring one and can never buy the
   loose end back. It landed 2026-09-05 and it is why a delete confirms: built
   the intended way, with no declaration, a delete used to come out `write` and
   nothing on either hand ever asked. The defensible form of this claim is **no
   pattern reads the owner's WORDS**, not "no list of strings exists", and the
   ROUTER holds the stronger version — it reads neither an app string nor a
   verb (`router.test.ts` scans its source for literal app comparisons and for
   `app_hint`; `grep '\.verb' src/router.ts` is empty). The only thing that can
   put a step on the API hand is a `MatchJudge` verdict of exactly `"yes"`,
   read only through `contract.ts`'s `judgeLicensesApi`. `unclear`,
   `no-verdict`, a thrown judge, a thrown vendor and a thrown ledger all
   collapse into one browser branch, so the router cannot mistake the absence
   of an objection for permission. `router.test.ts` renames every app string in
   a fixture — candidate, connection and prior alike — and asserts the hand, the
   rung, the score and the confirmation flag come back unchanged. Not
   byte-identical, and that wording was wrong here for a week: `reason` is a
   sentence written for a person and it NAMES the app on purpose, so comparing
   it would fail on a router that is behaving perfectly. The four fields
   compared are the ones anything downstream branches on.
2. **A retrieval score cannot license a hand — but the routed proof of it
   points the SAFE way, and that is a hole.** The fixture does rank
   `GMAIL_DELETE_THREAD` (0.91) **above** `GMAIL_ARCHIVE_THREAD` (0.89) for the
   ARCHIVE step, both over 0.75, on purpose: a "take the top hit over the
   threshold" rule destroys the owner's mail there. What is proven about that
   ordering is that the VENDOR returns it — `provider_fake.test.ts` asserts the
   two slugs come back in that order and stops. **Nothing routes it.** The step
   `integration.test.ts` drives is the DELETE one, whose retrieval is the mirror
   image (ARCHIVE 0.90 above DELETE 0.87), and there it asserts the judge was
   asked about the top-scored candidate and that it was passed over — so the
   direction that is actually routed is the one where following the score
   ARCHIVES a thread the owner said to destroy. Wrong outcome, no lost mail.
   This paragraph claimed the opposite until 2026-09-05. The missing leg is
   specified in §9; until it exists, "a score cannot destroy anything" is proven
   of the fixture and unproven of the router.
3. **The spike touches nothing.** Nothing under `spike/two-hands` imports
   `brain/`, `extension/`, `migration/`, `backend/`, anything else outside this
   directory, or any npm package. Nothing outside imports the spike. Both
   directions are legs, not intentions — and as of 2026-09-05 the detector is
   run against a violation PLANTED IN THE TREE, one file at a time, in every
   shape and every file extension it claims to cover: the leg writes the module,
   requires legs 1 and 2 to go red naming it, deletes it, and requires them
   green again. That is a stronger sentence than the one that stood here before,
   and it had to be: the fence was scanning `.ts` files only and demanding
   whitespace after `import`, so `import{x}from"../../brain/llm.ts"` and any
   `.js`, `.mjs` or `.cjs` file walked straight through it with all five legs
   green (§9).

The story in `test/integration.test.ts` is the product, end to end, on the fake
provider: a cold owner, a browser run, a nudge with earned evidence, a
connection, three shadow reads with parity, promotion to rung 2, an API-only
fourth read, a write refused until opt-in and then confirmed at rung 3, a
delete where the judge passes over the top-scored candidate, an API failure that
changes hands inside the same task, and a second failure that demotes and
re-opens shadow. A person can read it top to bottom.

---

## 2. What is NOT proven — the entire live column

- **Nothing has ever called Composio.** Every endpoint path, request field and
  response field in `src/provider_composio.ts` came from `docs.composio.dev`,
  fetched 2026-09-05. Doc-green is not repo-green and repo-green is not done.
  The first live search will probably rename something.
- **No signature has been matched to a real tool.** Ten hand-written read
  signatures say the shape holds. They say nothing about whether Composio has a
  tool for any of them.
- **The judge has never answered a real question.** Every verdict in every test
  came from a table keyed by signature hash and tool slug.
- **The ladder has never seen a real outcome.** Every rung in the repo was
  earned from a stub's numbers. The 5-candidate budget, the 0.15 latency weight
  and the cost weight of 1 are guesses that only a measured run can defend.
- **The Observer is not wired to Chrome.** It takes injected plain event
  objects; there is no `chrome.webRequest` listener and no message plumbing.
- **`InMemoryLedger` is in memory.** The ladder resets on restart until a D1
  store lands behind `LedgerStore`.

`run_ten.ts` can be pointed at a stand-in (`COMPOSIO_BASE_URL`,
`TWO_HANDS_OPENROUTER_URL`) so the measuring loop itself can be executed. That
was done once, on 2026-09-05, and it is the only reason the ten-task loop, the
seatbelt, the table and the results writer are known to run at all. **A
stand-in run can never exit 0**: `simulated` forces UNPROVEN whatever the ten
rows say, prints a banner top and bottom, and stamps the results file. A gate
that could go green against a fixture would be law 3 defeated by its own
instrument.

---

## 3. What the owner must do before the gate can run

In this order. The harness names each one as it blocks.

1. **Create a Composio account** (Pro, for the Tool Router search endpoint).
2. **Connect the four apps through a Connect Link** — Google Calendar, Gmail,
   Notion, Slack — under one Composio `user_id`. `provider.connectLink()` mints
   the link; `hands.onboarding.connectLink()` is the same call through the
   assembled facade.
3. **Set the keys.**
       export COMPOSIO_API_KEY=...      # the vendor
       export OPENROUTER_API_KEY=...    # the judge, the argument fill, the grade
4. **Set the owner id** — `TWO_HANDS_OWNER` must be the Composio `user_id` the
   connections were made under. This is the single easiest thing to get wrong:
   a wrong id returns an empty connection list, which reads exactly like "he
   connected nothing", so the harness names the variable in that message rather
   than only reporting the absence.
5. **Fill in the people.** `tasks/ten_read_tasks.json` carries `{{TOKENS}}` —
   `PERSON_A`, `PERSON_B`, `SENDER_INVOICE`, `NOTION_TOPIC`, `SLACK_CHANNEL`,
   `SLACK_SEARCH`. Write `tasks/ten_read_tasks.local.json`:

       { "PERSON_A": "...", "PERSON_B": "...", "SENDER_INVOICE": "...",
         "NOTION_TOPIC": "...", "SLACK_CHANNEL": "...", "SLACK_SEARCH": "..." }

   Nobody on this machine knows who he emails or which channel he reads, and a
   gate that asked his accounts about an invented colleague would grade the API
   hand wrong for a fact about the fixture. The harness refuses to run with a
   token unfilled and never guesses one. The refusal is a SWEEP over the whole
   task after filling, not a list of fields: whatever a token sits in — the
   prompt, an input value however deeply nested, the expected effect, the
   grading rubric, a key name, a field added to the file next month — an
   unfilled one stops the run. Case does not save it either: `{{person_a}}` and
   `{{PERSON_A}}` are one hole, reported and filled under the uppercase name, so
   the keys above are the only spelling he ever has to write. A token in a
   HASHED field (the `object`, or an input KEY name) is not a hole at all and
   exits BROKEN by name: filling it would move the signature hash and file the
   run under a capability nothing else computes.
6. **Run it.**

       node --experimental-strip-types tasks/run_ten.ts

   The gate is **9 of 10 correct AND p50 under 3 seconds**. Exit 0 only if both
   are met, exit 1 if the run happened and failed, exit 2 if it could not
   happen. It writes `results/<timestamp>.json` and prints a ten-row table —
   and it prints no table at all when there is nothing to put in one.

That file `tasks/ten_read_tasks.local.json` has his colleagues' names in it.
It is not read by anything else and does not need to be committed.

---

## 4. What the gate will tell you, and what it will not

**It will not tell you the answers were complete.** Every task carries an
`only_the_owner_can_confirm` line, and those are printed after the table and
never scored. An events list that returns three of his four events looks
identical to a complete answer: no field in any response says a calendar was
skipped. That is the characteristic failure of the API hand and no model
reading a response can see it. A human settles those or nobody does.

**It will not tell you the API hand is cheaper.** Composio documents no
programmatic premium flag on the tool object, so `premiumVerdict` returns
`null` for every candidate on the live API today and the only thing excluding
anything is a caller-configured toolkit set, empty by default. `allowPremium:
false` is currently a promise the adapter cannot keep on its own. The cost
column shows `—`, never `$0.0000`, when nobody declared a price: the difference
between "this was free" and "nobody told us" is the whole of that argument.

**It measures the API call's own latency.** `api_ms` is the gate's leg, because
that is what rule 5 compares the two hands on. The whole-step median — search,
judge, argument fill, execute, grade — is printed beside it and will be much
larger. That is what the owner actually waits, and a gate that only ever showed
the fast half would be hiding the executor's costs inside a number labelled
"the API hand".

**Correctness is a grader model's verdict, not his.** Four states, floor
polarity, only `"yes"` counts; `unclear`, `no-verdict` and an unreachable
grader all score zero, so the gate cannot go green on a dead model.

---

## 5. Findings from assembly

Three seams did not exist until `src/index.ts` was written. Each is a place
where every part was individually correct and the assembled system did nothing.

- **SEAM 1 — nobody told the ledger what the judge said.** The rung 0→1 gate is
  "a candidate the judge vouched for, on an app the owner connected", and it
  fires from `noteCandidate` — which the router never calls, because it holds a
  `Ledger` and `Ledger` has no writer for `api_candidates`. Unassembled, every
  pair sits at rung 0 for ever and the API hand is unreachable no matter how
  well it works. Fixed by `recordingJudge`.
- **SEAM 2 — `ExecResult.error.kind` never reached the ledger.** `Outcome`
  carries only free-text `failReason`, and the ledger rightly refuses to sniff
  prose for "401". Drop the kind and an expired refresh token records as
  "other", two of them demote a working capability, shadow re-opens, and the
  agent drives the browser for a week re-earning ground it never lost. Fixed by
  `apiOutcome()`, pinned by its own test.
- **SEAM 3 — the owner connecting an app never reached the ladder.**
  `onboarding.markConnected` now writes the consent AND `ledger.setConnection`.
  Without it he taps the link, the vendor knows, the ladder does not, and the
  nudge he just accepted buys him nothing.

Three defects were **pinned, not fixed**, in `test/integration.test.ts` — each
asserting what the system does today with a comment saying what it ought to do,
so the leg goes red the day somebody fixes it. **One of the three (FINDING 2) is
now fixed, and the pin is how anybody found out.** Two are still open.

- **FINDING 1 — a write capability can never reach rung 3 on its own.**
  Rung 1→2 is paid for in shadow parity matches; rule 4 forbids ever shadowing
  a write (a shadow run does the step twice, which on a send is two emails);
  and `clean_reads` counts only read-classified runs on the same pair. So the
  gate that unlocks writes cannot be satisfied by a write capability. The
  integration story stands the pair up with `setRung` and says so. The fix is a
  design decision nobody has made: either writes inherit the rung of a read
  pair in the same app, or the write ladder is climbed by confirmed assisted
  runs rather than by shadow. It is not a one-line change and it should not be
  made by whoever notices it next at 2am.
- **FINDING 2 — CLOSED 2026-09-05. Rung 3 means "assisted, every one
  confirmed", and the decision now says so.** As reported,
  `requiresConfirmation` was set for `irreversible` steps only, so an executor
  reading a rung-3 write decision performed the write without asking, at
  exactly the rung the ladder invented to make it ask. Two things fixed it and
  the order matters, because **the first one nearly buried the finding**:
  - `send` was floored to `irreversible` in `verbSideEffectFloor`
    (`src/signature.ts`), which is right on its own merits — the browser hand
    already gates `send` through `commitControl`, so the two hands were doing
    observably different things for one step. But the integration story's write
    step is a `send`, so this alone turned the pin green while the defect stood
    for every other write verb. **The illustration this section used to give
    stopped exhibiting the defect before the defect was fixed.** A defect that
    loses its example is not fixed; it is unwatched.
  - The real fix is in `src/router.ts` (~:817) and it reads the RUNG, not the
    verb: anything `irreversible` confirms on any hand at any rung, and any
    `write` confirms at rung 3. Rung 4 is where a write stops asking, which is
    what "auto writes" means and why it costs three confirmed writes with a
    verified effect to get there.
  The leg that keeps it honest is deliberately an `update` — the write verb
  with the least alarming name, and the one that archives somebody's mail —
  because widening the irreversible floor again would make a `send`-shaped test
  pass while `update` ran unasked. `router.test.ts` carries both halves ("rung 3
  confirms an ordinary write, not only an irreversible one" and "rung 4 is where
  an ordinary write stops asking"), and `integration.test.ts` asserts the story's
  rung-3 write carries the flag.
- **FINDING 3 — `account_hint` is carried, asked about, and ignored.** The
  router takes the first ACTIVE connection for the matched app. With work and
  personal Gmail both connected — normal, not an edge case — "send it from my
  personal address" runs against whichever the vendor lists first.
  `onboarding.accountChoice` is written, tested, correct, and reachable as
  `hands.onboarding.accountChoice` — and invoked by nothing: the router never
  reads `account_hint` at all. It is not wired because it returns `must-ask`
  whenever accounts are untagged, `ConnectedApp` has no `kind` column, and no screen exists that
  would ever ask — so wiring it today would take the API hand out entirely, a
  guard that guards nothing by being infinitely strict. **The fix is a column
  plus a one-time question, in that order.** This is the highest-risk unwired
  seam in the spike.

---

## 6. Contract gaps, collected

`src/contract.ts` was fixed before anything was built, which was right. Six
things it has no room for turned up in six different modules; they are listed
here because law 4 says state lives in files, and these were about to live only
in six agents' return values.

1. **`Outcome` has no error kind and no side effect.** The first decides
   whether a token expiry costs a demotion; the second decides whether a run
   counts as a read or a write. Both are worked around by
   `LedgerOutcome extends Outcome`, and **`apiOutcome()` is the only supported
   way to build one** — a caller writing the row by hand will drop `failKind`
   and will not find out for a week.
2. **`ToolCandidate.score` is a required number and Composio returns an
   ordering.** The adapter emits 0, −1, −2 — negative on purpose so a future
   reader cannot mistake it for a confidence. The honest shape is `rank`
   required, `score` optional.
3. **`Provider.search` cannot say "the vendor was down".** It returns an array,
   so a vendor outage and "this owner has no API for this step" are the same
   empty list. `run_ten.ts` wraps the provider to tell them apart, because for a
   GATE one is a measurement and the other is not.
4. **`ExecResult` has no room for "cost unknown"** and `CapabilityStats.
   cost_usd_total` is a required number. A ledger that totals unknown as zero
   reports the API hand as free.
5. **`ConnectNudge` has no ask counter and no decline counter,** so "a second
   decline is never-again" and "re-ask once" are unimplementable against the
   type as written. `onboarding.ts` widens the row instead — `NudgeRecord
   extends ConnectNudge` with optional `asks` and `declines` — and it survives
   today only because the in-memory table stores whole objects. **On D1 they are
   two columns somebody has to add**, and without them the feature becomes
   nagware while every test still passes. What is actually pinned, in
   `onboarding.test.ts`, is the full ask → decline → re-ask at 14 days →
   decline → `never-again` sequence, plus a bare-contract-row case (no counters
   at all) proving the verdict degrades to the timestamps rather than throwing.
6. **`ShadowRun` cannot be joined back to the pair it is evidence about** — it
   has `run_id` and `step_id` and no `user_id`/`signature_hash`/`app`.

One correction that is **not** a gap, and **it has been settled** — this
paragraph used to end by asking somebody to settle it, which was already stale
when it was written. `TraceSummary.hosts` documents "eTLD+1 only" and then gives
`mail.google.com` as an example of a kept host, which is its own
counter-example. The Observer follows the rule and drops the example, so Gmail,
Calendar and Drive collapse to `google.com`. Two things settle what that costs:

- `principalHost` (`src/observer.ts`) now puts **at most one** host in the
  array, by a stated precedence — most top-level navigations, then most writes,
  then most requests, then lexicographic so a tie breaks the same way twice. The
  old summary listed every registrable domain the step touched, which on a
  modern page is the app plus its CDN, its fonts, its analytics and whoever
  bought the ad slot: a description of the PAGE, and through it of the person,
  when the router asked one question and needs one answer. The field stays an
  array because `contract.ts` was fixed before the parts were built.
- The worry that the collapse "decides whether they are one app or three in
  `CapabilityStats.app`" is **wrong as of `src/index.ts`**: `browserOutcome`
  takes `app` from its caller and is forbidden by name from deriving it from
  the trace, because a host→app table would not be a lookup, it would be a guess
  about what the step MEANT written as a list of app names. Nothing routes on
  `hosts`; it is evidence for learning.

The remaining cost is stated rather than pinned: a step that genuinely touched
two apps reports one, and on the request-count tiebreak a busy asset host can
still win a step that had no navigation and no write. The `observer.test.ts`
assertion this paragraph used to point at has changed shape to match — it no
longer just checks that three Google subdomains collapse, it drives a fourth
host (Stripe) through the same summary as the control, and asserts both halves:
one app named, and the losing host counted but unnamed. Read here, not edited:
`src/observer.ts` and `test/observer.test.ts` were owned by another pass on
2026-09-05 and were being rewritten while this was written down. Re-check the
two bullets above against the file before quoting them.

---

## 7. The thing nothing here enforces

Key-set sensitivity is load-bearing and is also the biggest hazard in the
design. `{title,start,end}` and the same plus `attendees` **should** be
different capabilities, because the second one emails three humans. But
`{to,subject,body}` and the same plus `cc` should **not** be, and they split
into two rungs today. One rule resolves both and it belongs in the planner's
prompt, not in any file here: **emit the keys the step REQUIRES, not the keys
you happen to have values for.** If the planner writes `cc: null` because its
JSON template has a cc field, every optional field doubles the rung count and
shadow mode never closes. It is invisible until the ledger stops promoting, and
no test in this spike can catch it. It needs a prompt line plus an eval, or a
gate leg counting distinct rungs per (app, verb).

## 8. Privacy, stated because week 1 is the first thing that touches real mail

- Tool **responses** — his actual inbox, calendar and Slack — are sent to the
  grader model. That is the same boundary the brain already crosses every time
  it hears him, and it is the only way to grade an answer. Written down here so
  nobody discovers it later.
- The **judge** is sent input KEY NAMES only, never values, matching what the
  Composio adapter sends to retrieval. His recipient, subject and body have no
  business in a "which tool is this" question.
- `results/*.json` carries **no response body**. A 16-hex sha256 prefix and a
  byte count identify a payload without quoting it; the grader is instructed to
  describe shape rather than content, and its prose is truncated and passed
  through a redactor before it is written. A results file is a record that gets
  committed, and a committed record must not be his mailbox.

---

## 9. What an adversarial pass found in the instruments (2026-09-05)

Seven defects, all of one class: **a check that reported green while proving less
than it claimed.** That class comes first because it is the one that lets every
other class through — the fence, the blocker and the results document are what
everything else in this spike is trusted on. Six are closed with legs that go
red without the fix. The seventh is open and needs a file that pass did not own.

The last three were found by a SECOND adversarial pass over the first one's own
work, which is the point of law 6: the fix for the placeholder blocker shipped
with a hole in it and a test that could not see the hole, and nobody but another
adversary was going to notice.

- **THE FENCE DID NOT HOLD — two independent holes, both live, five legs green.**
  The specifier scanner required whitespace after the keyword
  (`(?:import|export)\s`), so `import{x}from"…"` and `import*as x from"…"` were
  not imports as far as it was concerned; and `spikeSources()` walked `.ts` only,
  so any `.js`, `.mjs` or `.cjs` file in the spike was never opened at all. An
  adversary planted five violating imports of `brain/` and the suite stayed
  green. Both are fixed — the keyword may now be followed by whitespace, `{` or
  `*` (three characters, named, because a bare `\s*` starts reading
  `importantly from "x"` as an import and a fence that fails on prose gets
  deleted), and the walker opens every extension the runtime would load. The
  proof is a new leg 6 that plants one violating module at a time INSIDE the
  spike, in seven shapes across four extensions, and requires legs 1 and 2 to go
  red naming that file and green again once it is gone.
- **THE INBOUND LEG'S LAST ASSERTION WAS `assert.ok(mentions >= 0)`.** A
  tautology over a `let mentions = 0` counter, sitting exactly where the leg's
  only control belonged — on the side this fence's own header calls "the side
  that actually matters". `importedBy` is empty in two different worlds: one
  where every mention of the spike outside it is prose, and one where the
  scanner read no line at all (renamed directory, empty walk, changed needle),
  and the leg could not tell them apart. It now requires `mentions > 0`, and a
  new leg 5b drives the assertion itself: it must throw on a scan that
  classified nothing, and throw on a real inbound import.
- **THE GATE'S PLACEHOLDER BLOCKER LOOKED AT TWO FIELDS.** `substitute()` filled
  `{{TOKEN}}` in the prompt and in top-level string values of `signature.inputs`.
  `expected_effect`, `object` and the whole `how_to_grade` rubric were never
  filled and never checked — and all three go to a model verbatim, the rubric to
  the GRADER. So the gate would call the owner's real Gmail and then score the
  answer against a rubric naming `{{PERSON_A}}`, and report a number for it. The
  filler now walks the whole task (values at any depth; keys are left alone
  because they are hashed), and the blocker is a sweep over the serialized
  result, so a field added to `ten_read_tasks.json` next month is covered without
  editing the filler. `test/run_ten.test.ts` is new and is the first test of the
  gate's key-free half; `run_ten.ts` now runs its `main()` only when it is the
  command, so that half can be imported without firing a run.
- **THE FIXED BLOCKER WAS UPPERCASE-ONLY, AND ITS TEST COULD NOT SEE THAT.**
  `PLACEHOLDER` was `/\{\{([A-Z0-9_]+)\}\}/g` — while a SECOND, any-case copy
  (`PLACEHOLDER_ANY_CASE`) existed a dozen lines below and was read by the
  hashed-field refusal alone. The gap between the two copies is exactly the hole
  the shared-constant comment above them said could not happen: `{{person_a}}`
  in the prompt, in `expected_effect` or in the grading rubric was not a
  placeholder as far as the gate was concerned, so it was neither filled nor
  swept, and the row ran against the owner's real Gmail and was SCORED against a
  rubric naming a literal token. Mixed case is not exotic here — `makeSignature`
  lower-cases `object`, so a hand-typed `{{PERSON_A}}` comes back out of it as
  `{{person_a}}` with nobody choosing that. **The test could not have caught it:
  its oracle `leftoverPlaceholders` was a character-for-character copy of the
  pattern under test**, so the stub and the code were wrong together and the leg
  reported clean. Both are fixed: one case-blind `PLACEHOLDER`, one `tokenName`
  normalising to the uppercase spelling the owner is told to write in the local
  file, `PLACEHOLDER_ANY_CASE` deleted; and the test's oracle is now
  `/\{\{[^{}]*\}\}/g` — the adversary's question, strictly wider than the pattern
  under test, which is the property a copy cannot have. Legs: a lower-case token
  blocks when unanswered and fills when answered, `tokensIn` reports it in the
  case he fills, and the hashed-field refusal is still case-blind with the second
  regex gone.
- **AND THE PADDED FORM `{{ PERSON_A }}` WAS INVISIBLE IN EVERY DIRECTION AT
  ONCE.** Found by the widened oracle immediately after it was widened, which is
  the argument for widening it. The spacing every templating language on earth
  accepts made the token cease to exist for the harness: `tokensIn` did not list
  it, so the owner was never asked for it; `substitute` neither filled it nor
  reported it, so nothing blocked; and the literal `{{ PERSON_A }}` went to the
  judge and to the GRADER. Measured before the fix, not reasoned about — a probe
  printed `tokensIn []`, `missing []`, and the raw braces in both the prompt and
  the rubric. `PLACEHOLDER` now tolerates the padding and FILLS it, rather than
  merely refusing it, because the owner has an answer for that token and the run
  can just work. **The known residual, written down rather than fixed:** a brace
  pair the filler cannot name at all — `{{first-name}}`, `{{PERSON A}}`, `{{}}` —
  is still neither filled nor reported. Closing it means a second, wider pattern
  for the BLOCKER only (the floor shape: fill what is unambiguous, refuse
  anything that still looks like a hole), and probably a BROKEN exit rather than
  a missing-token list, since there is no key the owner could write to close one.
  That was not built here: nobody has ever written one, and inventing a refusal
  for a shape with no recorded instance is how a guard grows into an outage. The
  inside of the pattern deliberately stays `[A-Za-z0-9_]` for the same reason —
  a looser one starts reading ordinary prose as a hole.
- **THE SWEEP THAT §5 CREDITS FOR "NOT A LIST OF FIELDS" WAS UNTESTED.** Delete
  the sweep line and the whole suite stayed green: the test written for it
  (`note_to_the_grader: "ask about {{PERSON_A}}"`) is reported by the deep
  FILLER, which walks every string value at any depth, so it never reached the
  sweep at all. A leg for `fillDeep` wearing the sweep's name. The sweep's own
  cases are the two the filler CANNOT report, both now pinned and both verified
  red with the sweep removed: a token in a KEY, which `fillDeep` is forbidden to
  touch because input key names are hashed; and an answer that is ITSELF a
  placeholder, because `String.replace` does not re-scan what a replacement
  function returned — a half-pasted line in `ten_read_tasks.local.json` is
  exactly what that looks like. The control beside them is that a good answer
  carrying single braces (`Dana {Whitfield}`, `has:link {from:dana}`) still fills
  and still runs: a sweep that refused every brace would be an outage wearing a
  guard's name.
- **OPEN — nobody routes the destructive direction.** See §1 claim 2. The test
  that would make that claim true is not written, and it belongs in
  `test/integration.test.ts`, which this pass did not own. What it has to do:
  take the ARCHIVE signature (`FIXTURE_SIGNATURES.archive_thread` from
  `src/provider_fake.ts` — verb `update`, side effect `write`, and the SHIPPED
  fixture already ranks `GMAIL_DELETE_THREAD` 0.91 above `GMAIL_ARCHIVE_THREAD`
  0.89 for it, so no `withRetrieval` override is needed and adding one would
  destroy the point), give the judge table an entry mapping that hash to
  `GMAIL_ARCHIVE_THREAD` only, stand the pair up at rung 3 with the write opt-in
  the way the story's send step does, and `decide()`. Then assert three things:
  the judge was ASKED about `GMAIL_DELETE_THREAD` (proving the top hit was
  considered and refused, not merely unreached), the decision's tool is
  `GMAIL_ARCHIVE_THREAD`, and no decision on that signature ever carries
  `GMAIL_DELETE_THREAD` — including the run where the judge vouches for nothing,
  which must land on the browser with no tool rather than on the top score.
  A fourth is worth having now that FINDING 2 is closed: `archive_thread` is an
  `update`, which floors to `write`, so at rung 3 the decision must also carry
  `requiresConfirmation: true`. That is the case the router leg deliberately
  covers with an `update` too, and asserting it here ties the routed proof to
  the confirmation rule rather than leaving them to be re-derived apart.
  Until that leg exists, `provider_fake.test.ts` proves the fixture is dangerous
  and nothing proves the router survives it.
