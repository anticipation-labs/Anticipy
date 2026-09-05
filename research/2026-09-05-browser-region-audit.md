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
| 67 | `phoneField`/`identifierField`/`namedIdentityField`/`compactChoiceField`/`timeWindowField` | VIOLATION | **FIXED `448bc592`** | six classifiers deleted; `fieldKind` = declared ?? verdict ?? UNANSWERED, a FLOOR; 80-check suite, 6 mutations |
| 68 | `approvedBoolean` negation window | VIOLATION | **FIXED `ba12df46`** | window deleted; `boxVerdictJudge`, CEILING with an UNCLEAR hand-back; `box_verdict_gate.py` UNPROVEN until a paired credential exists; 4 mutations |
| 69 | date/time approval regexes | PARTIAL | **FIXED `ee7e4d6a`** | both regexes deleted; native temporal fields deferred to `unsupportedScopeVerdict`, FLOOR, undecided never cleared; 4 mutations |
| 70 | `login_wall.js` scored classifier | VIOLATION | **FIXED 2026-09-05** | sixteen regexes deleted; one CEILING question; golden set 66/66 live (OpenRouter direct — proxy UNPROVEN) |
| 71 | `looksLikeCaptcha` phrase list | VIOLATION | **FIXED `b0db7ec7`** | painted provider furniture (structure) → one question, CEILING, made safe by the challenge-frame click seatbelt; the 2026-08-16 badge page asks nothing; 7 mutations |
| 72 | `page_map.js` control-deletion keywords | VIOLATION | OPEN — design NEEDS-REWORK | read what a list is ATTACHED to |
| 73 | placeholder-option word list | VIOLATION (L) | OPEN — design NEEDS-REWORK | |
| 74 | `explicitRequestedCount`/`reportedRecordCount` | VIOLATION | **FIXED `9d83e056`** | DELETED with `completionCoverageScore`; the auditor is the only judge, taught three sentences; zero extra calls; 5 mutations |
| 75 | `goalMatchingElements` hoist | VIOLATION (L) | **FIXED `e961e023`** — DELETED | the planner already sees every control |
| 76 | `taskShape` as the only recall judge | VIOLATION | **FIXED `f8de9303`** | four-state floor, twin of `brain/research.py` |
| 77 | `supervised_read` narration filter | borderline | **FIXED `a3bc04e9`** | four wording legs deleted; `lineVerdict` one question, four states, FLOOR; byte/address/link budget stays as the carries-only seatbelt; 6 mutations + 1 |
| 78 | `detectsCodeWasSent` | VIOLATION | **FIXED** (commit "Where the code went is read by a model, not a phrasing regex") | regex + two word lists deleted; `whereCodeWent` four-state FLOOR over `codeSentJudge`; proof `test_code_sent_is_not_a_word_match.mjs`, 3 mutations |
| 79 | `extractCode` scoring | borderline | **FIXED** (commit "Which value is the code is read by a model, not ranked by a word list") | `CODE_CONTEXT`/`NOT_A_CODE`/`extractCode` and the askModel re-parse deleted; `readCodeVerdict` four-state FLOOR over `codeJudge`, `codeFromPage` shape+provenance containment on the reply; proof `test_code_read_is_not_a_word_match.mjs`, 4 mutations |
| 90 | intent journal before every click | **BRIEF DEVIATION** | **FIXED `8e6673ed`** (the crash-resume half) | see below |
| — | SSRF guard: loopback only | not in the audit | **FIXED `09ec97ad`** | Omi teardown item #04 |

Eight commits, three of them not from the audit at all (the SSRF guard, the intent journal, and a modelFetch retry found while tracing the model path).

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

**The reconciliation half of #90, built as the attack corrected it** (same
day, `extension/reconcile.js`). After a crash with an intent outstanding the
surviving tab is read once and ONE question is asked of a model on its own —
the #64 shape through `reconcileJudge` — in four states: APPLIED, NOT_APPLIED,
UNCLEAR, and NO_VERDICT for "nobody answered" (no intent, no tab, a tab on the
wrong host, an unreadable page, a model down, or any reply that is not exactly
one of the three tokens). The answer is written as `params._reconciliation =
{verdict, evidence, at}` — host, the intent's sentence, the page's url/title/
fingerprint, the token; never page text, never a field — beside a `needs_user`
row whose reason says what was found. Nothing in this path writes `done`,
`succeeded` or `queued`, for every verdict and both lease states: the attacker's
verdict stands, recorded here so it is not re-proposed — APPLIED with a live
lease would self-close on ONE 8-token call, below the bar the normal done path
holds (the step model's claim PLUS `verifyDone`), and a wrong APPLIED tells the
owner the table is booked when it is not. The Brief asks that the question be
ANSWERABLE, not self-acted; if a self-close is wanted later it must route
APPLIED through `verifyDone` as the second opinion. What stays deterministic is
seatbelt: the intent's tab is read only while its browser-session stamp matches
(the `resume_tab` rule), and only while that tab's host is the intent page's or
the first-after page's — a tab the owner moved to his bank is neither read nor
shipped. The intent record gained `step`, `tab`, `session` and an `after` half
(`{url, title, fingerprint, step, at}` of the first page read after the click,
written once, unthrottled, from the step's own checkpoint and never from the
journal tail). **The mutation testing found the erasure the attack predicted was
real**: the intent hook called `updateJob` bare and never told the trace
writer's closure `params`, so the next throttled trace write serialised a
`params` without `_effect_intent` — the row kept the flag and lost the intent.
Both writers now come from one `rowWriters` factory sharing one view of the
row; the pre-fix hook shape turns leg D red ("the last serialised params still
carry the intent" → `null`). Five mutations in `test_reconcile_after_crash.mjs`
(117 checks): unreadable reply → NOT_APPLIED (8 red), the model never asked (12
red), no-verdict written `queued` (6 red), the bare-write hook (10 red), the
host check removed (4 red). Still owed, and blocking a DONE on HANDS 1: the
phone (`app/ios/Anticipy/AnticipyApp.swift` `approvalFields`, the `ownerWords`
constant and the constant `reconciliation` dictionary) must cite
`_reconciliation.verdict === "not_applied"` and its evidence instead of its
constants, or the guard's retry leg is still satisfied by a string literal —
that is a control-flow change in Swift, not a constant swap, and was not made
here. Also not made: the in-run throw path still closes the tab in the loop's
teardown, so that site can only answer "the page it was on is gone"; the sweep
(a reclaimed worker, the tab still open) is the path that now reads.

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

**#67 form-field kind** (`448bc592`, built by a worktree agent from the reviewed
seven-point mechanism, verified independently before merge). Five functions
decided what a form field was FOR from the English words in its label — and
that classification chose which pre-submit rule ran, so it decided whether a
value was retyped, wiped, or submit-blocked in the owner's browser. Measured:
"Order comments" matched `identifierField` via `\border\b` and a comment
holding an approved code was cut to the bare code; a German "Kontakt" phone
bleed passed untouched. Now `fieldKind` = declared (type/autocomplete, exact
tokens) ?? one batched model verdict per form (no values ever shown) ??
UNANSWERED, as a FLOOR: on UNCLEAR/UNANSWERED every refusal fires and every
rewrite is withheld, and a floor-only flag ends the step by asking the owner
instead of wedging. Zero cost on an ordinary run. Independent re-verification
before merge: the six names survive only in the WHAT-WAS-HERE record; the
prompt carries exactly index/name/label/type/autocomplete/required; and the
agent's headline mutation held up under my hands — with retry and cache
removed, the loop still asked twice, one per step, so a COUNT-only pin would
have passed; the pin asserts adjacency and went red. That is the finding worth
the whole item: a green test that only looked load-bearing, caught by mutation
before it shipped.

**#78 `detectsCodeWasSent`** (built by a worktree agent from the reviewed
corrected mechanism). A phrasing regex over the rendered page decided whether
the page was SAYING a code had been sent, and two word lists decided the
channel — the verdict that decides whether the run offers to open the owner's
inbox at all. The function's own comment records the shape's live failure:
the two commonest wordings matched nothing until they were added by hand, and
"a one-time passcode is on its way" still matched nothing after. Now
`whereCodeWent` hands the whole page to `codeSentJudge` — one question on its
own, the page fenced in the user turn, shown up to page_map's own 6000-char
cap (the attack found the design's 4000 would have re-created the miss on
long pages) — and maps the token in four states; `tripOnOffer` is a FLOOR
over the verdict: no verdict is no offer and no ref, but still a hand-back
with a plain ask, never the stall. Asked only inside the code wall, once per
page state per run. **Mutation testing**: a `\bsent\b` sift put back in front
of the judge and the judge skipped both stall the "on its way" run for 19
steps with judge count 0; no-verdict read as EMAIL mints the offer and a live
ref on an empty reply, prose, "EMAIL." and UNSURE. Pre-existing and
unchanged: the plain-address regex names the tail `r@gmail.com` of a masked
`o***r@gmail.com` in the offer sentence; `looksReal` keeps it from steering
the URL. Not verified live (law 3).

**#79 `extractCode`** (built by a worktree agent from the reviewed corrected
mechanism). A word list ranked the digit runs on an inbox page — labelled 100,
alone on a line 80, near `confirm|security|access|pin|…` 60 — and the winner
was typed into a live one-time-code field with `unquotedCode` satisfied by the
regex's own output; a model was consulted only when the regexes found nothing,
never when they found a wrong one, and its prose was then re-parsed by the
same regex. Measured (audit row 79): "Order #482130 confirmed" beat a
truncated real code and 482130 was submitted; the `confidence` field never
had a consumer. Now `readCodeVerdict` asks `codeJudge` one question on its
own — which value on this page is the code that site sent — in four states
(code / none / unclear / unread), and `codeFromPage` is the deterministic half
that stays: one token, 4-8 alphanumerics with a digit, present on the exact
4000-char slice the model was shown, either as a whole token or as one line
compacted. It can only refuse a reply, never choose between candidates — the
test says so the honest way round: the footer year passes provenance, and it
is the model's job not to name it. `runSideTrip` is a FLOOR: no judge means
no tab is opened; unread ends the trip at once as undecidable, never "keep
clicking through his mailbox"; UNCLEAR on the list page opens the message,
UNCLEAR on any later page stops. **Cost, said plainly**: every taken trip now
ships the list page (other senders' snippets included) to the model one to two
times, where a regex hit used to keep it on the machine — within the consent
the owner gave, and recorded here as a change. **Mutation testing**: a
labelled-code regex put back in front of the judge, the judge skipped for the
first digit run, unread read as none, and the provenance check bypassed each
went red on the pin and its companions, and each restore was byte-identical.
Not verified live (law 3).
**#70 `login_wall.js`** (2026-09-05, built by a worktree agent from the
reviewed corrected mechanism). Sixteen vocabulary regexes — sign-in verbs,
identifier and password words, card and code words, SSO phrases, money-gate
and subscription phrases, prices, an optional-account list, auth paths and
titles — plus an inline commit-verb list and two prose-length thresholds were
summed and the errand parked at WALL = 4, the hedge dropped at SURE = 6.
Measured on the audit's own example the day it was rewritten: "Members only
parking permits — $45 per year" in the sidebar of a permit form scored 3 + 1
= 4 and the errand was abandoned as a paywall one step from done. Now ONE
question (`WALL_QUESTION`) goes to a model on its own, four states come back,
and the loop parks only on an explicit WALL — a CEILING, so a timeout, a 500,
prose or an empty reply all fall through to the step model exactly as a null
did. WHEN it is asked is structure: page_map's sensitive mark (the DOM's own
type=password / cc-* / one-time-code attribute) or a page unmoved for two
steps; once per wall key per run, where the key deliberately ignores field
values (the attack found the stall fingerprint hashes them, which would have
re-asked a checkout on every keystroke). Nothing typed, no field value, no
query string and no owner profile rides into the question; controls are
reduced to index, role, label and the mark. `canContinueAfterOwner` (zero
callers) and the duplicate CHALLENGE regex went with it. **Two things the
mutation and live testing found.** First, the offline suite (204 checks) went
red under all six mutations — the named one (no-verdict returned as a wall),
the polarity flip (`!== "clear"`), the question skipped, the cache keyed on
the stall print, raw element lines sent, the stall trigger removed. Second,
and the one worth the whole item: the first LIVE run of the golden set
(`research/evals/login-wall-2026-09-05/`, 22 fixtures × 3) came back 15/22
WRONG with replies of `PAY`, `SS`, `SSO` and empty — the browser model,
`google/gemini-3.1-pro-preview`, is a thinking model and spent the 64-token
floor on reasoning before its one-word answer. Every truncated reply is a
no-verdict, and a no-verdict never fences: on the model it actually runs on,
the ceiling would have been a decoration while the offline suite stayed
green. Cap raised to 512 and pinned in the leg and the suite; re-measured
66/66. What is still UNPROVEN: the leg reached OpenRouter directly, not
`/agent/llm` — no paired-agent credential exists on this machine and the
`agents` table is malformed at HEAD — so the proxy's own path (its
`thinkingLevel: "low"` Google call) is unmeasured, and the other six
one-token judges, floored to 64 on the same model, are owed the same
measurement. See `research/evals/login-wall-2026-09-05/FINDINGS.md`.

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

1. **#68 `approvedBoolean`** — whether ticking a checkbox counts as approved.
2. **#69 date/time approval** — which calendar cells may be clicked; comment at
   ~:908 records a live near-miss.
3. **#71 `looksLikeCaptcha`** — abandons the run; comment records a live
   incident that scrapped a real reservation.
4. **#72 `page_map` control deletion** — deletes real controls before the model
   sees them.
5. **#70 `login_wall`** — parks the errand and texts the owner.
6. **#74, #73, #77** — medium/low, in that order (#78 and #79 closed, above).
5. **#78, #79, #73** — medium/low, in that order.

## What was NOT verified, said plainly

- No live browser run. Every change is repo-green. The extension has a
  `hostile_checkout.html` fixture and a manual proof for never-foreground; a
  real errand on a real site with these changes has not been run.
- **Deployed 2026-09-05 04:15Z (`fd538eaf`)**: `is_it_live.py` now says "served
  0.12.0, source 0.12.0 … identical … all packaged files identical". The
  paragraph below is the state BEFORE that deploy, kept as written. What the
  deploy then exposed — the `agents` table malformed since before the 4th, so
  no browser install can authenticate until it is repaired — is in
  `research/2026-09-05-agents-table-malformed.md`.
- **Production served extension 0.8.4 until the deploy above.** `is_it_live.py` was run after the six
  commits and the number is not "six commits behind" — it is three minor
  versions behind, and `stranger_gate` leg 1 had been saying so in its own
  words: *the banner tells the stranger to press Reload to get 0.11.2; the only
  download in the product serves 0.8.4.* Every browser-region fix in this
  session, and every one since August, is unreachable by any real user. Worse,
  the COMMITTED zip said 0.11.2 and did not contain it: five of today's files
  differed from what was inside, and `staleExtension()` compares numbers, so
  nothing in the product could see the gap. The artifact was rebuilt from
  source with `extension/build-zip.sh` (which refuses a version or module-graph
  mismatch), bumped to 0.12.0 at all four pinned sites, and `stranger_gate`
  leg 2 went FAIL → PASS: "is extension/ at 0.12.0, 21 files, nothing Chrome
  reaches is missing". The deploy is a separate, outward-facing act and was
  not run inside this commit.
- The eleven open items have reviewed designs, not code.
