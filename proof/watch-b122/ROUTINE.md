# The cloud routine's instructions

A scheduled cloud agent runs this every three hours. It starts with ZERO
context and a fresh checkout, so everything it needs is here. Its prompt is one
line pointing at this file, which is deliberate: the instructions live in the
repo where they can be reviewed and versioned, not inside a routine config
nobody reads.

**READ-ONLY.** Never commit, push, or edit. This is an observation.

## Setup

    git checkout cloudflare-backend
    python3 -m pip install -q --user requests httpx tzdata pytest 2>/dev/null || true

## 1. `python3 overnight/tejas_gate.py`

**Expected: 7 legs PASS, leg 6 THE SPEAKER TAGGER IS LINKED FAILS.**

Leg 6 is red **on purpose**. The speaker engine was unlinked twice by controlled
experiment — builds carrying its frameworks were accepted and then silently
ceased to exist during App Store Connect processing, and the feature itself
measured actively harmful (195 distinct identities across 200 lines). Do not
call leg 6 a regression and do not propose fixing it. **Any other failing leg is
the finding.**

## 2. `python3 overnight/tape_gate.py`

**Expected: exit 1, `TAPE OUTSTANDING`, leg 2 red.** Red is this gate working —
it goes green only when the tape is *deleted*, never because somebody wrote it
down. Exit 2, `THE BOOKS DISAGREE`, is a real finding and must be reported.

## 3. `python3 overnight/firmware_gate.py`

**Expected: exit 2, `UNPROVEN`.** The pendant firmware is fixed in source and has
never been compiled — there is no cross-toolchain on any machine that touches
it. UNPROVEN is the honest steady state, not a failure. **Exit 1 `BROKEN` is a
real finding.**

## 4. `python3 -m pytest tests/ -q --ignore=tests/test_day_zero_oracle.py`

**Expected: ~2448 pass and exactly THREE failures**, all pre-existing
environment gaps:
- two in `tests/test_roster_parity.py` (missing module)
- one in `tests/test_segmenter_link_tape.py` (`co_lines` needs Python 3.10)

**A fourth failure is the finding.** Name it.

## 5. Telemetry — needs a secret this routine probably does not have

    python3 proof/capture_day.py --hours 24

If it prints `403` or "could not read the day", that is **expected and is not a
quiet day**. `ANTICIPY_SERVICE_TOKEN` lives in `.env.local`, which is gitignored
and therefore absent from a cloud checkout. Report it as
`telemetry: unauthenticated (no token in this environment)` and move on.

**Never report a sample you could not take as a healthy one.** That inversion —
an instrument reporting nothing as good news — is the specific failure this
repo has been burned by twice.

If it *does* return JSON, compare against the 2026-09-05T00:00Z baseline in
`README.md` (lines 82, thoughts 68, shard_rate 0.485, speaker_coverage 0.0,
sources `{"phone_mic": 82}`) and lead with any of:
- `shard_rate` moved more than 5 points (the Brief's worst recorded day is 54%)
- `sources` gained a `pendant` key — that lane has never delivered a row, ever
- `speaker_coverage` above 0 — somebody relinked the speaker engine; re-read
  `tejas_gate` leg 6 before treating it as good news
- `rows_unread` above 0 — the worker is falling behind

## How to report

At most **eight lines**. Lead with anything unexpected. If everything matches
the expectations above, say so in one line and stop — a quiet run is the normal
result and should read like one. Do not fix anything, do not run other gates,
and do not open a PR.
