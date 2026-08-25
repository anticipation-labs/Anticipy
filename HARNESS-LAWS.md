# THE HARNESS LAWS

**If you are an AI agent working in this repo, this file outranks your instincts.**
Before you write code, read the six laws. If a change you are about to make
adds pattern-matching over natural language to decide behavior, STOP, flag it
to the person who asked, and propose the Law-5 alternative instead. Any agent —
reviewer, fixer, intern, frontier model — that sees a violation and does not
flag it has failed the task, whatever else it did.

Why this file exists: this codebase spent three months in a loop — spot the
mess, patch it with string checks, lose context, rediscover the mess, patch
again. The patches are the mess. The measured result is the Tejas call
(research/evals/call-2026-08-23-tejas/): 137 decisions, six actions, five
wrong, zero questions asked, one invented human being.

---

## LAW 1 — No pattern-match may decide MEANING.

No regex, verb list, word count, or string check may decide what a human's
words mean or what the assistant should do about them. Meaning belongs to a
model given full context. The verb list `_READ_ONLY_RE` deciding a timezone
conversion was "consequential" (brain/anticipy_core.py) is the canonical
violation: a regex doing understanding's job, and doing it backwards.

Pattern-matching is legitimate in exactly three places:
- **Senses** — audio plumbing, timestamps, transport. Not meaning.
- **The seatbelt** — checking a plan's *effect channel* (does it send, pay,
  delete, post?). Checking what a plan TOUCHES is structure; checking how a
  sentence was WORDED is a violation.
- **Gates and evals** — deterministic tests of outcomes (overnight/*.py).
  Measuring is not programming.

**What the fix looks like, so the next agent reaches for it instead of tape.**
There are now four worked examples in the tree of a meaning question taken off
a pattern and given to a model: `party_verdict` (whose promise is this?),
`ends_in_the_world` (does this plan end in an action?), `check_sufficiency`
(what would you have to be told first?) and `work_is_licensed` (does anything
he said license preparing this?) — all in brain/orchestrator.py. The shape is
the same every time: **ONE question, asked on its own**, never a ninth key in
an existing JSON reply, because a field among many loses (measured: seven
cases, zero moved); a **four-state** answer, because "no" and "nobody
answered" are different things and a bool can only carry two of them; and the
caller comparing the verdict. Whether the missing state refuses or waves
through is decided by which way the check points — a FLOOR (does anything
authorize this?) must refuse without a verdict or it lifts itself; a CEILING
(is this positively forbidden?) must not fence without one or it never lifts.
Getting that backwards is how a fence becomes a wall, and how a wall becomes
a decoration.

## LAW 2 — Tape ships only with an expiry.

If a string-level patch must ship in an emergency, it ships carrying:
(a) a `TAPE:` comment naming the real fix, and (b) a gate leg that stays red
until the real fix replaces it. Tape with no expiry is a rejected diff. Tape
whose gate leg went green gets DELETED, not kept "just in case."

The leg is **overnight/tape_gate.py**, and the comment must name it — a `TAPE:`
comment pointing at a leg that tracks something else reads as compliant and
enforces nothing (audit item #21). Mind the polarity: the leg must go RED
BECAUSE THE TAPE EXISTS. A leg that fails when the tape is REMOVED is a
regression pin — legitimate, sometimes necessary, and not an expiry.
overnight/tejas_gate.py leg 2 is one, was read as the other, and that is how
this repo ran 8/8 green with five undeclared pieces in the tree.

## LAW 3 — Nothing is fixed until its gate leg is green against the LIVE system.

Repo-green means nothing. Production has served stale code at least twice
(extension 0.3.3 live vs 0.3.9 in source; a brain that acted on "Dr. Evans"
while the repo's own guard would have caught it). Every deploy is followed by
a byte-or-behavior check against the live URL (overnight/is_it_live.py
pattern). A fix that was never verified live is a fix that will be
"re-discovered" as a bug next month — that is where the three-month loop
came from.

## LAW 4 — State lives in files, never in chats.

Plans, findings, and decisions go into repo files (research/, docs/, gates)
the day they are made. A conclusion that lives only in a conversation will be
re-derived — wrong — by the next session. The gates are the loop-breaker:
a red leg does not forget, does not rot, and does not get re-litigated.

## LAW 5 — The fix order is fixed: senses → context → examples → model tier → structure.

Before writing ANY rule, ask in order:
1. **Is she deaf?** (senses: capture, speaker attribution, vocabulary)
2. **Is she blind?** (context: judging 4-word scraps instead of whole
   conversations)
3. **Is she untaught?** (examples: brain/EXEMPLARS.md wired into the prompt)
4. **Is she too cheap?** (tier: frontier model on the few decisions that
   become actions — cents per day)
5. Only when none of those apply is structure even a candidate — and then it
   must be seatbelt-shaped (effect channels), never meaning-shaped.

A rule written while 1–4 are unfixed is tape by definition.

## LAW 6 — The owner is not the review loop.

Nothing ships until an adversarial pass — yours or a fleet's — has tried to
kill it: against these laws, against the tests, against the recorded
failures. The owner catching a violation you could have caught yourself is
a PROCESS failure and gets logged as one. This law exists because on
2026-08-23 an agent shipped a verb-list fix, was caught by the owner,
shipped a calculator-sniff fix, was caught again, and only then built the
right thing — three drafts, two of them reviewed by the one person whose
time the whole product exists to protect. Self-review to convergence,
then ship.

---

## Known standing tape (legacy — scheduled for removal, do not extend)

**This list is one of three books, and all three must agree. The other two are
the `TAPE:` comments in the shipped code, and the registry in
overnight/tape_gate.py — which is the leg that tracks every entry below and
stays RED until the tape is DELETED.** Run it: `python3 overnight/tape_gate.py`.
Adding a piece of tape means three edits, in three files, in one diff. That is
the price, and it is deliberate: for four months the only cost of tape was a
comment nobody could check, and the repo accumulated five undeclared pieces
(research/2026-08-24-law1-audit.md).

The `[tape:…]` tag on each bullet is the anchor overnight/tape_gate.py leg 5
matches. Do not remove one without retiring its registry entry in the same
diff.

- `[tape:read_only_re]` `_READ_ONLY_RE` (brain/anticipy_core.py) — the default
  hold/run split for every goal that arrives with no effect-channel
  declaration. → Replaced when effect-channel classification owns the split
  outright and an undeclared goal is re-asked of the model instead of guessed
  at by wording. PARTIAL as of 2026-08-24: computable goals are now classified
  by CAPABILITY (an early fix that ADDED compute verbs to the regex was itself
  a Law-1 violation and was reverted); the prose regex still owns everything
  else. **It carried no `TAPE:` comment in code until this was written down —
  and tejas_gate leg 4, which this ledger named as its tracker, is GREEN while
  the regex is still deciding. That is the failure Law 2 exists to prevent,
  committed by this file.**
- `[tape:compute_fallback]` the `if compute_answer(g):` fallback inside
  `is_consequential()` (brain/anticipy_core.py) — on an undeclared goal the
  calculator is sniffed, and if it can answer, a held goal flips to unattended.
  → Dies with the effect-channel rewrite, when triage always declares
  `touches` and nothing reaches a capability sniff.
- `[tape:shard_too_thin]` `shard_too_thin()` (brain/anticipy_core.py) — a word
  count decides a line is too thin to act on; the brake fitted after "At 5:15"
  minted a meeting with a person nobody had mentioned. → Deleted the day
  segment-granularity triage ships and shards stop being decision units.
  NOTE: tejas_gate.py leg 2 is a REGRESSION pin on this guard (red if it is
  removed early), not an expiry. The expiry is tape_gate.py leg 2.
- `[tape:pending_class]` the prose fallback in `_pending_class()`
  (brain/anticipy_core.py) — rows minted before the `consequence` column
  existed get their consequence re-derived from goal prose. → Expires when no
  pending row can predate the column.
- `[tape:third_person_drop]` the DEGRADED-path third-person drop in
  asking.question_line (live composer absent → third-person items are dropped
  rather than texted to the owner about himself). → Expires when the composer
  owns person-flipping explicitly. The live path passes them through untouched.
- `[tape:answer_ends_errand]` `AnticipySession.answerThatEndsTheErrand`
  (app/ios/Anticipy/AnticipyApp.swift) — three phrase lists ON THE PHONE
  (`whole`, `declines`, `handled`) decide that a typed answer MEANS "call this
  errand off": the job is written `cancelled`, the owner's own sentence is
  filed as the evidence they cancelled it, and the brain never sees the line.
  Law-1 audit item #55, severity H. The only consumer is
  `AnswerRoutePolicy.route`, where its only job is to short-circuit
  `.toTheBrain`. → Deleted the day every typed answer becomes one `app_reply`
  and `on_reply` decides. **BLOCKED ON brain/, not on app/ios/**: `_classify`'s
  offline fallback (brain/conversation.py) reads `_pending()` —
  `awaiting_confirm` only — so with the model unreachable a "forget it" typed
  at a `needs_user` card returns intent=chat and "Nothing's queued up on my end
  right now" while the errand keeps running. Deleting the phone rule before
  that fallback can see `_open_work()` trades a Law-1 violation for a
  cancellation that silently does not happen, which is worse. First entry in
  this ledger that is not one of the audited five and not in brain/; see the
  comment on its registry entry for why it carries no `audit_item`.

Not tape, but adjacent, and still not to be extended:

- The digit guard and `unsupported_names`/`unsupported_counts` string checks
  (brain/orchestrator.py ~:472) → legitimate as BACKSTOPS only; the real fix
  is a frontier model with full context at act-minting. Do not add siblings.
- Word-level heuristics in triage pre-filtering → survive only as the cheap
  sift in front of the model, never as the decision. The 2026-08-24 audit
  disputes this line: it found several of them returning a final Decision with
  no model call, which makes them the decision, not a sift.

## The map

- The measured failure and the fix plan:
  research/evals/call-2026-08-23-tejas/ (FINDINGS.md, PLAN.md)
- Where the laws are actually enforced:
  research/2026-08-24-law1-audit.md — 61 Law-1 violations, 30 of them able to
  do or prevent a real-world action, and the five pieces of undeclared tape
  overnight/tape_gate.py now holds by name.
- The scoreboards:
  - overnight/done_gate.py — is the product done
  - overnight/tejas_gate.py — does the next call like the Tejas call work
  - overnight/tape_gate.py — Law 2: is there tape, and does anything track it.
    RED is this gate working. It goes green when the tape is GONE.

**Two files this section used to name do not exist and never have** (checked
with `git log --all`, 2026-08-25): `research/HOW-AN-AGENT-EXISTS.md` and
`overnight/fellowship_gate.py`. CLAUDE.md and AGENTS.md still cite both. A law
file that points at a scoreboard nobody can run teaches the next agent that
the citations here are decorative — which is Law 4 failing inside the file
that declares Law 4. Either build them or strike them everywhere; do not leave
them half-cited.
