# The browser region, re-audited against the code as it stands — 2026-09-05

The 2026-08-24 Law-1 audit found seventeen constructs in `extension/` where a
pattern decides what words MEAN (items #63–#79, its section 8). This is that
list re-verified against the code eleven days later, with every item's
disposition, plus one item the audit did not have (#90, a Brief deviation).
Sixteen items were each verified against current source, a Law-1-compliant
design was written for every open one, and each design was attacked on five
fronts before anything was built. This file is the ledger; the workflow
transcript is the evidence.

**What "perfect" means here, and does not.** Nothing in this file is Law-3 done
unless it says so: every change is repo-green with mutation-verified tests, and
none has been observed against a live browser run. The extension runs in the
owner's logged-in browser with `<all_urls>` and the debugger, so the bar for
"verified" is a real errand on a real site, and that has not happened today.

## The ledger

| # | construct | was | now | evidence |
|---|---|---|---|---|
| 63 | `inboxAuthorized` word lists | VIOLATION, worst in repo | **FIXED before this session** | offer-ref + model judge, `side_trip.js` |
| 64 | `questionShaped`/`pageFailure` | VIOLATION | **FIXED before this session** | model call at `agent_loop.js` ~5539 |
| 65 | `completionContradiction` | VIOLATION | **FIXED `43f96128`** | regex ceiling deleted; auditor owns the verdict; 4-leg suite |
| 66 | `isAuthored` | VIOLATION | **FIXED before this session** (`c30157ee`) | |
| 67 | `phoneField`/`identifierField`/`namedIdentityField`/`compactChoiceField`/`timeWindowField` | VIOLATION | **BUILDING** — worktree agent, 7-point corrected mechanism | see below |
| 68 | `approvedBoolean` negation window | VIOLATION | OPEN — design NEEDS-REWORK | own-question box verdict |
| 69 | date/time approval regexes | PARTIAL | OPEN — design NEEDS-REWORK | typed native date/time half |
| 70 | `login_wall.js` scored classifier | VIOLATION | OPEN — design NEEDS-REWORK | one CEILING question |
| 71 | `looksLikeCaptcha` phrase list | VIOLATION | OPEN — design NEEDS-REWORK | provider-markup sift + model |
| 72 | `page_map.js` control-deletion keywords | VIOLATION | OPEN — design NEEDS-REWORK | read what a list is ATTACHED to |
| 73 | placeholder-option word list | VIOLATION (L) | OPEN — design NEEDS-REWORK | |
| 74 | `explicitRequestedCount`/`reportedRecordCount` | VIOLATION | OPEN — design NEEDS-REWORK | |
| 75 | `goalMatchingElements` hoist | VIOLATION (L) | **FIXED `e961e023`** — DELETED | the planner already sees every control |
| 76 | `taskShape` as the only recall judge | VIOLATION | **FIXED `f8de9303`** | four-state floor, twin of `brain/research.py` |
| 77 | `supervised_read` narration filter | borderline | OPEN — design NEEDS-REWORK | closest to a data-egress seatbelt |
| 78 | `detectsCodeWasSent` | VIOLATION | OPEN — design NEEDS-REWORK | |
| 79 | `extractCode` scoring | borderline | OPEN — design NEEDS-REWORK | parsing a machine code out of prose |
| 90 | intent journal before every click | **BRIEF DEVIATION** | **FIXED `8e6673ed`** (the crash-resume half) | see below |
| — | SSRF guard: loopback only | not in the audit | **FIXED `09ec97ad`** | Omi teardown item #04 |

Six commits, two of them not from the audit at all.

## The two that were not Law-1 findings

**The SSRF guard covered this machine and not the owner's network** (`09ec97ad`).
`loopbackTarget` was written for a mail catcher on localhost and did that well.
But a page the agent is reading can steer it to anything the owner's network
reaches — the router at 192.168.1.1, a NAS, a work VPN host, or on a cloud
desktop the metadata service at 169.254.169.254 that hands out credentials —
and none of those is loopback. Measured against WHATWG: 10.x, 172.16.x,
192.168.x, 100.64.x, 169.254.x, 0.1.2.3, [fe80::1], [fc00::1] and [::] all
walked past. The one form worth naming is IPv4-mapped IPv6, which Omi's own
guard also misses: WHATWG serialises `[::ffff:127.0.0.1]` as `[::ffff:7f00:1]`,
so a guard looking for dotted digits inside the brackets sees nothing; the low
32 bits are now decoded and judged as the IPv4 address they are. A seatbelt
under Law 1 — it checks what a plan TOUCHES — with the ranges written as CIDR
from Omi's `http_client.py` so a reviewer checks them against the RFCs.

**A retry after a crash re-sent the submission the flag existed to prevent**
(`8e6673ed`). The Brief promises "an intent journal written before every click,
so 'did the send actually happen?' is answerable after any crash", and the
board marked it done. What was written before the click was one boolean. The
two keys the at-most-once gate refuses repeats by lived in a Set created empty
on every run — including the run that resumes a job whose worker was reclaimed
between the click and the receipt. That run re-sent. The mechanism was already
half-built: `agent_loop` handed `(decision, state)` to `onBeforeExternalEffect`
and the wrapper in `background.js` was `async () => {…}`. Now the intent
`{doing, url, sig, digest, at}` — never a form value — goes to disk beside the
flag, seeds the Set on resume, and the owner's card says what to look for.

What #90 still lacks, and deliberately: the reviewed design also proposed a
post-crash *reconciliation* — read the surviving tab, ask a model whether the
effect landed, and self-close the row as done on APPLIED. The attacker's
verdict is recorded here so it is not re-proposed: APPLIED with a live lease
would self-close on ONE 8-token call, below the bar the normal done path holds
(the step model's claim PLUS `verifyDone`), and a wrong APPLIED tells the owner
the table is booked when it is not — a new world-reaching write where today
every crash path parks and the owner looks. The Brief asks that the question be
ANSWERABLE, not self-acted. If a self-close is wanted later it must route
APPLIED through `verifyDone` as the second opinion.

## The three Law-1 fixes, and what the mutation testing found

**#65 `completionContradiction`** (`43f96128`). Three verb lists over the
agent's own result sentence returned `verified:false` from `verifyDone` before
`mapPage` and before the auditor sixty lines below ever ran. Recorded on
2026-08-25 as acceptable because fail-closed; it was not — fail-closed is none
of Law 1's exemptions, and under the polarity rule this was a CEILING fencing
with no verdict. Measured: "Booked. The confirmation email was not sent to the
address on file" → false, mapPage 0, audits 0 — a finished booking rejected,
and the loop then re-attempted it. The auditor already owned the question; the
three alternations ride into its prompt as examples now. Zero added calls.

**#75 `goalMatchingElements`** (`e961e023`). The Law-1-compliant fix was
deletion, not a second model call: the planner already receives the whole map,
and "which control serves this step" is its primary output. A second call would
ask the same model the same question over the same context and paste the answer
back with nothing comparing it. The pin reads the bytes sent to the model.

**#76 `taskShape` as the only recall judge** (`f8de9303`). The shape key is a
sorted word set, blind to direction by design — and so "savings to checking"
and "checking to savings" are one key, and the loop replayed whatever collided
on the owner's real accounts. The key keeps its job as the sift; one question
goes to a model as a FLOOR, in the exact shape `brain/research.py` already
built. **The mutation testing found a weak pin**: a source grep for "no bare
`recallProcedure(` call" was tried first, and a mutation that reached the bare
function through a destructured alias walked straight past it. A grep pins
spelling. It was replaced with a behavioural test that drives the real loop
against a seeded collision with a judge that says NO — with the judge flipped
back to YES as the control — and that catches the alias bypass. Recorded
because it is the shape the laws warn about, and it was in a test I had just
written.

## What is still open, and in what order

The eleven NEEDS-REWORK designs all failed the attack on the same front:
**the gate leg, not the mechanism.** In every case the model question was
judged genuinely one question on its own, the polarity was right, and the
remaining deterministic half was a real seatbelt. What failed was the proof —
a test that would be green-by-construction, a missing loop-level pin, an
unswept sibling (#67's `timeWindowField`), or a "stays deterministic" half that
quietly still read wording. Each has a corrected mechanism written down in the
workflow result; none should be built from the original design.

Ranked by blast radius, which is what should order the work:

1. **#67 form-field kind** — BUILDING. Decides what the pre-submit auditor
   rewrites, wipes and blocks, in the owner's browser, on the step before a
   send/pay/book. Seven-point corrected mechanism; four mutations specified.
2. **#68 `approvedBoolean`** — whether ticking a checkbox counts as approved.
3. **#69 date/time approval** — which calendar cells may be clicked; comment at
   ~:908 records a live near-miss.
4. **#71 `looksLikeCaptcha`** — abandons the run; comment records a live
   incident that scrapped a real reservation.
5. **#72 `page_map` control deletion** — deletes real controls before the model
   sees them.
6. **#70 `login_wall`** — parks the errand and texts the owner.
7. **#74, #78, #79, #73, #77** — medium/low, in that order.

## What was NOT verified, said plainly

- No live browser run. Every change is repo-green. The extension has a
  `hostile_checkout.html` fixture and a manual proof for never-foreground; a
  real errand on a real site with these changes has not been run.
- `is_it_live.py` — whether the SERVED extension matches source — was not run
  today; the extension version was not bumped, so the shipped 0.11.2 is now
  behind source on six commits. That is the exact "prod served stale code"
  shape Law 3 names, and it needs a version bump and a deploy, not a commit.
- The eleven open items have reviewed designs, not code.
