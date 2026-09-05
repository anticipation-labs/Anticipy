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

**Expected failures depend on the Python version — check it first**, with
`python3 --version`:

| environment | expected failures |
|---|---|
| Python >= 3.10 (this cloud container is 3.11) | **2**, both `tests/test_roster_parity.py`, cause: **numpy not installed** |
| Python 3.9 (the author's laptop) | **3** — the same two, plus `tests/test_segmenter_link_tape.py`, which needs `co_lines` (3.10+) |

Roughly 2443 pass and 6 skip. **A failure outside that table is the finding.**
Name it.

This table is corrected from the first run, which is worth recording because the
watcher got it right and the instructions had it wrong. The briefing originally
said "expect exactly THREE" with no version condition; the cloud container runs
3.11, correctly produced TWO, and the run investigated the difference rather
than reporting a phantom regression or silently accepting a mismatch. It also
identified the missing module as numpy, which the briefing had left vague.

## 5. Telemetry — needs a secret this routine probably does not have

    python3 proof/capture_day.py --hours 24

If it prints `403`, "could not read the day", or a connection error, that is
**expected and is not a quiet day**. Report it as
`telemetry: unavailable from this environment` and move on.

TWO separate reasons it cannot work here, and the second is the one that
settles it. `ANTICIPY_SERVICE_TOKEN` lives in `.env.local`, which is gitignored
and absent from a cloud checkout — that one a secret could fix. But the first
run failed earlier than auth, with
`HTTPSConnectionPool(host='backend-production-61e0a.up.railway.app', port=443):
Max retries exceeded` — the sandbox could not reach the host at all. So supplying
the credential would buy nothing, and the security trade of putting a token with
read/write across every owner's data into a routine config is not worth making
for a call that cannot connect. **Live telemetry stays a local job.**

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
