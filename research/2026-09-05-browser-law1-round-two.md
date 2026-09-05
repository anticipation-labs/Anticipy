# Browser region, law-1 round two — the seven findings and what each cost

**Date:** 2026-09-05
**Branch:** `cloudflare-backend` (cluster E1)
**Source of the findings:** `research/2026-09-05-completeness-audit.md`, rows
F05–F08, F10, F24, F36.
**Prior rounds:** `research/2026-08-24-law1-audit.md` (the ledger),
`research/2026-09-05-browser-region-audit.md` (round one, audits #63–#80).

Round one took the meaning decisions out of the browser region's *gates*. This
round is what round one's own "still open" section warned about: the residue.
Seven places where a regex, a word list, or a threshold was still deciding what
somebody's words MEANT — and in five of the seven, the measured cost was not
theoretical.

## The seven

| # | Where | What decided meaning | What it cost, measured |
|---|---|---|---|
| F05 | `runAgentGoal`, the spawned-tab door | the fifth navigation door asked a loopback-only check while the other four asked `navigationRefusal` | a narrower authorisation than the four doors beside it |
| F06 | `comparisonNames`, `completionShapeGap` | a parse of "Compare … for A, B and C" refused any claim not containing the owner's spelling of each name; a sibling counted URLs against the number of names | a correct three-carrier answer citing "Bell:" was refused as "omits: Bell Canada"; three correct prices from one page were refused as "requests 3 direct URLs but the result contains 1"; at eight rejections the owner was texted that a finished errand could not be verified |
| F07 | `sideTripDeps.clickText` | `purpose` split into words over three letters; the first inbox row containing ANY of them was clicked | on a realistic mailbox the picker opens row 4 — a *different site's* week-old code — when the message the errand needs is row 7. It then reads it. |
| F08 | `commitControl`, `cookieLike` | a start-anchored reversible-prefix regex ran BEFORE the commit test | with `explicitSubmit` true: "Continue and pay" → not a commit; "Next: Place order" → not a commit. A read-only run would have pressed them. |
| F10 | `completeNamedValue` | seventeen hard-coded connectives decided whether a capitalised neighbour was part of a name | the brain writes `Task: {goal}. …`, so the goal's own leading verb — Email, Text, Call, Ask, Order — read as a missing name part. "Task: Email Coast Dental…" holding "Coast Dental" was a DECIDED refusal: PRE-SUBMIT BLOCK, `stuckStreak`++, an optional field wiped. |
| F24 | the done-rejection recovery | six regexes over the verifier's PROSE chose the recovery | an Escape keypress inside a live modal because a rejection said "missing"; five seconds and a second audit call on a rejection saying "waitlist"; scroll-or-research decided by phrasing |
| F36 | the financial-errand refusal | two ANDed word lists over the goal | **see below — worse than the audit recorded, and the fix is a deletion** |

## F36 is the one to read twice

The audit filed F36 as a NOTE and offered two acceptable resolutions, the
cheaper being "file it in the law-1 ledger as LEGAL — seatbelt-with-cost,
recording the two measured false refusals". Measuring it before writing that
entry is what changed the disposition.

The guard was:

    /\b(bank(ing)?|brokerage|credit\s*card|crypto\s*(exchange|wallet))\b/i
  AND /\b(log\s*in|sign\s*in|password|statements?|transfers?|balance|accounts?)\b/i

Run against ten realistic errands (the set is in
`extension/tests/test_financial_errand_is_a_verdict.mjs`, which keeps the two
lists as the only remaining copy so the old behaviour stays measurable):

| | count | examples |
|---|---|---|
| refused, correctly | 2 | "log into the bank and download my statements" |
| **refused, wrongly** | **3** | "update the bank account on my payroll portal"; "email the accounts team the credit card receipt for the hotel"; "update my credit card on the Netflix account" |
| **not refused, wrongly** | **1** | **"find my Chase balance and tell me"** |

That last row is why this stopped being a ledger entry. The guard exists to stop
the agent operating somebody's bank account, and it **fails open on a named
bank**, because "Chase" is not in the first list. It stopped three errands it
was never meant to stop and waved through the one it was written for.

HARNESS-LAWS law 1 does permit pattern matching in the seatbelt — but the
seatbelt is *what a plan touches*, and a goal's **wording** is not what it
touches.

**What replaced it: nothing. That is the finding.**

`BLOCKED_DOMAINS` already refuses `chase.com` and sixteen others at *every*
navigation. It is fail-closed, needs no model, and matches on the HOST of a
navigation — which is exactly the touch-based seatbelt law 1 permits, and its
own comment at `agent_loop.js:3105` says so. So the goal-wording pre-check was a
redundant optimiser sitting in front of a correct guard. Its only genuine
benefit was skipping a wandering search on the two errands in ten it read
correctly. Its cost was refusing three outright.

**A model judge was built for this and then removed, and that is worth recording
as carefully as the fix.** `financialErrandJudge` asked one question, four
states, ceiling polarity, and it fixed the accuracy. It also put one model call
at the front of **every** browser run — latency and money on every errand — to
save a wasted search on two errands in ten, in front of a guard that would have
refused them anyway. And it broke 22 of 93 extension suites, because an extra
`fetch` at the top of `runAgentGoal` consumes the first scripted reply in every
suite that scripts a sequence. That breakage was the signal, not the obstacle: a
change that invasive needs a benefit proportional to it, and this one did not
have one.

The honest trade is to let "log into the bank" start, search, and be refused
when it tries to navigate. That wastes a run. The old code wasted the owner's
errand.

**What the deletion costs, stated rather than discovered later:** a genuine
financial errand now burns a few model steps before `navigationRefusal` stops
it, where it used to be refused instantly. The refusal still happens, with the
same wording, from the guard that was always doing the real work.

## The shape every fix took

The same one, because it is the house shape and it is in HARNESS-LAWS:

1. **One question, asked on its own**, about one thing, with only what that
   question needs. `rowJudge` sends the clickable rows and our own purpose
   string, never page text as instruction. F10's name judge sends the owner's
   sentence and one word out of it and nothing else — no field value, no label,
   no page text, no profile — because the ambiguity lives entirely in his words.
   (F36 is the exception that proves the rule: the right answer there was not a
   better question but no question at all.)
2. **A four-state answer**: yes / no / unclear / no-verdict.
3. **The caller compares the verdict.** Never re-reads the sentence. Where a
   sentence still has to be told apart from another (`officialRecordEvidenceGap`
   writes two findings and the caller must distinguish them), producer and
   classifier now share a constant — `UNOPENED_SOURCE_GAP` — so a regex is not
   guessing at prose this file itself wrote.
4. **Polarity is chosen and stated.** A FLOOR where the verdict licenses an
   ACTION (clicking into a mailbox, pressing Escape on a live page, sleeping
   five seconds). A CEILING where the verdict would REFUSE an errand and a
   fail-closed guard already stands behind it.

## Two process findings, worth more than any single fix

**A pin that breaks on unrelated edits is a pin that gets loosened in a hurry.**
`test_box_verdict.mjs` pinned the exact argument list of four
`unsupportedScopeVerdict` calls. F10 threaded a `names` judge through them and
the pin went red while the property it protects — every scope verdict seeing the
box verdicts — was completely untouched. Whoever hits that mid-merge loosens it,
and the next real removal walks through. Re-pinned by property: there are four
calls, and every one of them passes `boxes`.

**A test that serves a wait instead of asserting it can hide behind its own
timeout.** The F24 suite drove the `still_loading` path a dozen times, each
sleeping five real seconds, ran 143s, and blew `run_all.mjs`'s 120s per-suite
cap. It **passed standalone and failed in the runner**. Long waits are now
compressed and counted, which is strictly better evidence: `seen.longWaits`
proves the pause happened, where elapsed time only proved something was slow.
14.8s.

And one that nearly cost a false clean bill: the F07 harness first matched
`getBoundingClientRect` to stub the element-centre call. That string also
appears inside the page-map function, so `mapPage` returned a point instead of a
page, `clickText` bailed before asking anything, and **every assertion read
"clicked nothing" — which is exactly what a correctly working FLOOR looks
like.** A suite that cannot tell a working floor from a broken harness proves
nothing. The stub now matches the exact helper name.

## Mutation testing

Every fix was verified by breaking it and confirming a test went red, restoring
from an absolute-path backup, and confirming `diff -q` byte-identical.

| fix | mutation | checks red |
|---|---|---|
| F06 | comparison-name parse back in front of the auditor | 15 |
| F06 | the two goal-word triggers restored | 7 |
| F06 | the teaching deleted from the auditor prompt | 4 |
| F10 | the seventeen-word list back in front of the judge | 37 |
| F10 | the judge never asked | 22 |
| F10 | no-verdict read as a pass instead of the floor | 9 |
| F24 | the closed set stops being closed | 6 |
| F24 | the floor inverted to a ceiling | 10 |
| F24 | `still_loading` fires on any gap | 1 |
| F24 | `source_unvisited` stops gating the direct navigation | 2 |
| F07 | the word list comes back | 24 |
| F07 | the floor inverts (anything not NONE clicks) | 9 |
| F07 | containment removed | 3 |
| F07 | an unreachable judge clicks the first row | 1 |

F36 is a deletion, so it has no mutation of its own. Its leg is
`test_financial_errand_is_a_verdict.mjs`, which keeps the two deleted
predicates as the only surviving copy, re-measures them on the ten errands
every run, and fails if either half comes back — the word lists OR a per-run
judge in their place.

**One mutation that did NOT go red, recorded because it matters more than the
ones that did:** prefixing F06's teaching sentence with two characters left
every substring assertion satisfied. The mutation that counts for prompt
teaching is *deleting* the sentence, not damaging it. Any future suite pinning
prompt content should assume the same.

## Cost added to an ordinary run

- **F36**: one model call at the start of every run. It is the only judge that
  needs neither page nor profile, and its answer is one word.
- **F07**: one call, and only on a side trip that reached an inbox list — a path
  that already exists because the run is blocked on a one-time code.
- **F10**: nothing, unless a capitalised word stands beside a form value; then
  one call per distinct word per run, memoised on (word, sentence).
- **F06**: **zero** added calls. The two measured shapes ride into the auditor's
  existing prompt as teaching.
- **F24**: zero. The token rides in the auditor's existing JSON reply.

## Status

`run_all`: 93 suites, all passing. Two new:
`test_row_is_a_model_verdict.mjs` (F07) and
`test_financial_errand_is_a_verdict.mjs` (F36).

**This is repo-green, which HARNESS-LAWS law 3 says is not done.** The judges in
this region run over the `/agent/llm` proxy, and the instruments that would prove
the 512-token reply floor is enough over the proxy's own Gemini path —
`overnight/box_verdict_gate.py` and `overnight/login_wall_gate.py` — are UNPROVEN
(exit 2) until a paired browser credential can be minted. Until they exit 0,
every judge added here is question-green, not live-green.
