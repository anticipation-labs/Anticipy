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
`overnight/done_gate.py`, `overnight/tape_gate.py`, `overnight/stranger_gate.py`,
`overnight/are_the_ears_live.py`.

`are_the_ears_live.py` exists because the ears went deaf for 30 hours and
nothing noticed. `is_the_brain_live.py` exits 0 on exactly that shape — every
rule it has is an over-speaking rule, so it cannot see silence. The new leg uses
the count of rows the SERVER wrote as its control: a quiet night is quiet on both
halves, deaf ears are quiet on one. It reports UNPROVEN rather than green when
the control is absent.


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

**`git commit -- <path>` only works on TRACKED files.** A new file must be
`git add`ed first, then committed path-limited. Otherwise you get
`pathspec ... did not match any file(s) known to git` and, if you are not
reading exit codes, you conclude you committed when you did not.

## Three traps that cost real work on 2026-08-25

All three share a shape: the failure is silent and the surviving output looks
like success.

**`git checkout -- <file>` does not restore an untracked file.** It fails, and
in a mutate-test-restore loop that failure is easy to miss — the mutations then
STACK, the second landing on top of the first, and every result after that
point is measuring a file nobody intended. Back new files up with `cp` first.

**In zsh, a `&&` chain ABORTS when a glob matches nothing.** An audit's
`unzip ... && check ...` one-liner silently no-oped: unzip never ran, the
checker walked an empty directory, and it reported a clean bill of health on a
bundle it had never opened. Run the steps separately and check each exit code.

**Read the exit code of the command, not of the pipeline's last stage.**
`sh run_tests.sh 2>&1 | tail -6; echo $?` reports `tail`'s status, which is
essentially always 0, so a suite exiting 2 reads as green. Capture with
`out=$(sh run_tests.sh 2>&1); rc=$?`. This is how a red privacy gate — one that
had correctly detected its own blindness and refused to pass — was reported as
"both suites green".
