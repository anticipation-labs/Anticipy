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
`overnight/done_gate.py`, `overnight/tape_gate.py`, `overnight/stranger_gate.py`.

`tape_gate.py` is Law 2's expiry and is **RED on purpose**. Red is the law
working; green means the tape is GONE, not that somebody wrote it down. Never
soften one of its predicates to reach green.

The gates load `.env.local` themselves (since `8a58e14e`) and print to stderr
which credentials they picked up, by name. Before that, `done_gate` reported
"no model key, so her judgement cannot be measured" with the key sitting in the
same directory, and — because it tells you to work only the first failing leg —
sent agent after agent at the wrong leg. If you see no stderr notice, no file
was found and a red "cannot be tested" leg is real.

Field map: `docs/BRIEF.html` is the one document — what we are building, the
definition of done, the fifty moments, and every screen with file refs.
`docs/BOARD-STATE-2026-08-24.md` is the twelve harness cards as the board
actually has them.
Live-deploy rule: verify with overnight/is_it_live.py-style checks after every
deploy — `railway up` reports success while failing.

## When more than one agent is working in this tree

**Stage by path. Never `git add -A`, `git add .`, or `git commit -a`.**

Those commands commit whatever is in the index, and the index is shared. On
2026-08-25 two workers made this mistake independently within an hour: each ran
a selective `git add`, then a bare `git commit`, and each swept up files a
*different* live agent had already staged — half-finished code, including a
deliberately-red TDD test, landing inside a commit whose message described
something else entirely.

Both were repairable the same way, and the repair is worth knowing:

    git log -1 --pretty=%B > /tmp/msg          # keep the message
    git reset --soft HEAD~1                    # index restored exactly as it was
    git commit -F /tmp/msg -- <only your paths>

`git commit -- <paths>` commits those paths and nothing else, whatever else is
staged. Use it every time. The other agent's work stays staged and untouched.

Check `git status --porcelain` before committing: if files outside your brief
are staged, someone else is mid-task in this tree and a bare commit will take
them.
