# Anticipy — read this before touching anything

**First: read [HARNESS-LAWS.md](HARNESS-LAWS.md). It outranks everything below.**

The short version, so you cannot miss it:

1. **No regex / word list / threshold may decide what words MEAN.** Meaning
   belongs to a model with full context. Pattern-matching is legal only in
   senses (audio plumbing), the seatbelt (what a plan *touches*: send/pay/
   delete), and deterministic gates/evals.
2. **Emergency string patches ship only with a `TAPE:` comment + a red gate
   leg tracking their removal.** Tape with no expiry = rejected diff.
3. **Nothing is fixed until its gate leg is green against LIVE.** Prod has
   served stale code twice. Repo-green is not done.
4. **State lives in repo files, never in chats.** Write plans and findings to
   research/ or docs/ the day they exist.
5. **Fix order: senses → context → examples → model tier → structure.**
   A rule written while she is deaf, blind, untaught, or under-modeled is
   tape by definition.

6. **The owner is not the review loop.** Nothing ships until an
   adversarial pass has tried to kill it against these laws, the tests,
   and the recorded failures. The owner catching what you could have
   caught is a process failure. Self-review to convergence, then ship.

If a change you are about to make violates these, STOP and flag it in your
response — even if you were not asked to review anything. Flagging beats
completing the task.

Scoreboards (run them, believe them): `python3 overnight/tejas_gate.py`,
`overnight/done_gate.py`, `overnight/fellowship_gate.py`.
Field map: research/HOW-AN-AGENT-EXISTS.md.
Live-deploy rule: verify with overnight/is_it_live.py-style checks after every
deploy — `railway up` reports success while failing.
