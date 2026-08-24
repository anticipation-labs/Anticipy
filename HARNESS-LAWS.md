# THE HARNESS LAWS

**If you are an AI agent working in this repo, this file outranks your instincts.**
Before you write code, read the five laws. If a change you are about to make
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

## LAW 2 — Tape ships only with an expiry.

If a string-level patch must ship in an emergency, it ships carrying:
(a) a `TAPE:` comment naming the real fix, and (b) a gate leg that stays red
until the real fix replaces it. Tape with no expiry is a rejected diff. Tape
whose gate leg went green gets DELETED, not kept "just in case."

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

- `_READ_ONLY_RE` and the `is_consequential()` prose-regex fallback
  (brain/anticipy_core.py) → replaced by effect-channel classification.
  Tracked by overnight/tejas_gate.py leg 4. PARTIAL as of 2026-08-24:
  computable goals are now classified by CAPABILITY (compute_answer() is
  asked, not a verb list — an early fix that ADDED compute verbs to the
  regex was itself a Law-1 violation and was reverted); the prose-regex
  fallback still owns everything else and remains the item to replace.
- The digit guard and `unsupported_names`/`unsupported_counts` string checks
  (brain/orchestrator.py ~:472) → legitimate as BACKSTOPS only; the real fix
  is a frontier model with full context at act-minting. Do not add siblings.
- Word-level heuristics in triage pre-filtering → survive only as the cheap
  sift in front of the model, never as the decision.

## The map

- What this system is, organ by organ, vs. the 2026 field:
  research/HOW-AN-AGENT-EXISTS.md
- The measured failure and the fix plan:
  research/evals/call-2026-08-23-tejas/ (FINDINGS.md, PLAN.md)
- The scoreboards: overnight/tejas_gate.py, overnight/done_gate.py,
  overnight/fellowship_gate.py
