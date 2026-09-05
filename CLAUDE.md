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
`overnight/are_the_ears_live.py`, `overnight/firmware_gate.py`,
`overnight/box_verdict_gate.py`, `overnight/login_wall_gate.py`.

`box_verdict_gate.py` and `login_wall_gate.py` (both 2026-09-05) are UNPROVEN
(exit 2) for one reason, and it is not theirs: the live `/agent/llm` proxy
needs a paired browser credential, and production's `agents` table is
malformed (`research/2026-09-05-agents-table-malformed.md`), so no credential
can be minted until the repair switch is thrown. They are the instruments that
will say whether the 512-token reply floor is enough over the proxy's own
Gemini path; until they exit 0, every judge in the browser region is
repo-green and question-green, not Law-3 done.

`firmware_gate.py` is UNPROVEN (exit 2) on purpose, and that is a third state,
not a soft fail. The pendant's capture path was fixed in source on 2026-09-04 —
routine backpressure used to switch the microphone off for the rest of the
connection — and NONE of it has been compiled: there is no west, no
arm-none-eabi-gcc, no Zephyr and no firmware CI on this machine, and the source
receipt still reads artifact_built=false. Host-compiled checks over the pure
halves pass (`firmware/source/tests/run_firmware_tests.sh`), which is a
precondition and not an answer. Do not read those passing as the firmware
working, and do not turn this leg green with anything short of a build, a flash,
and a pendant that streams.

`are_the_ears_live.py` exists because the ears went deaf for 30 hours and
nothing noticed. `is_the_brain_live.py` exits 0 on exactly that shape — every
rule it has is an over-speaking rule, so it cannot see silence. The new leg uses
the count of rows the SERVER wrote as its control: a quiet night is quiet on both
halves, deaf ears are quiet on one. It reports UNPROVEN rather than green when
the control is absent.


`tape_gate.py` is law 2's expiry, and it is **RED right now on purpose**. Red is
the law working. Green means the tape is GONE, not that somebody wrote it down —
so never soften one of its predicates to reach green. It also prints what it
cannot see: tape nobody marked and nobody registered. Only an audit finds that;
the last one is `research/2026-08-24-law1-audit.md`.

Field map: `docs/BRIEF.html` is the one document — what we are building, the
definition of done, the fifty moments, and every screen with file refs.
`docs/BOARD-STATE-2026-08-24.md` is the twelve harness cards as the board
actually has them, with what each asks for and where it stands.
Live-deploy rule: verify with overnight/is_it_live.py-style checks after every
deploy — `railway up` reports success while failing.
