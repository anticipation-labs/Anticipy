# Anticipy — session bootstrap (auto-loaded; survives compaction and fresh sessions)

> 🧭 **THE ONLY READING ORDER** (everything else is archive — do not follow older "read X first" banners):
> 1. **`CANON/00_START_HERE.md`** — what Anticipy is, how the system works, how the agent operates.
> 2. **`MISSION_LOCK.md`** — the live mission: milestones, PASS tests, STATUS TABLE, NEEDS-OMAR.
> 3. **The active plan in `PLANS/`** (see `PLANS/00_OVERARCHING.md` status board).
>
> Conflict rule: product/architecture/done questions → CANON wins. Live status → MISSION_LOCK wins.
> The ~174 legacy .md files are indexed in `CANON/99_SUPERSEDED_INDEX.md` as historical.

## What this project is (one line)
Anticipy: a proactive assistant that ambiently hears a person's messy day, infers the unspoken
tasks (vents are NEVER tasks), acts in their real systems through the browser, checks in like a
human, and remembers. Full truth: `CANON/01_WHAT_ANTICIPY_IS.md`.

## Non-negotiables (every role, every session)
- ALWAYS TEST BEFORE SAYING DONE. "Done" is a check that could have failed and did not, with the
  output pasted. A claim of done without a reproducible result is a violation.
- MAKE THE PIECES WORK TOGETHER, NOT PLUMBED SEPARATELY. One spine (Event → memory → decide → act
  → verify → close the loop). Nothing is "built" until it is WIRED — `factory/bin/check_wiring.py`
  enforces this; a plan step isn't done until its WIRING-PROOF box is filled (see `PLANS/`).
- Research before guessing. Real artifacts only (`[Anticipy test]` labels, drafts never auto-sent,
  carts never checked out, read-back as the only completion proof).
- Acting on a vent is the cardinal sin. Money/irreversible = confirm (note: per Omar 2026-07-02
  the deeper safety-gating PASS is deferred to a final manual pass — don't build new gates now).
- Never claim a milestone without its PASS output pasted in MISSION_LOCK's STATUS TABLE.

## Run commands
- Engine: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`
- Suite (GATE-S): `bash scripts/run_suite.sh` — baseline 2026-07-02: 109 passed / 10 failed;
  the FAILED name-set may NEVER grow (byte-diff the tail line against the baseline in the plan).
- Milestone batteries (GATE-M): `overnight/m1_battery.py` (6/6), `m2_copy_test.py` (PASS),
  `m3_integration_test.py` (ALL PASS) — ALWAYS against a FRESH engine + FRESH `ANTICIPY_DATA_DIR`
  (they are state-sensitive; a reused data dir gives false failures — learned 2026-07-02).
- Wiring gate: `engine/.venv/bin/python factory/bin/check_wiring.py` (`--strict` fails TODO debt,
  `--list` dumps the authoritative endpoint enumeration).

## Concurrency rule (learned the hard way)
While `factory/.lock` exists, a factory lap is running: DO NOT COMMIT — the lap's revert is
`git reset --hard <base>` and would destroy interleaved commits. Check first: `ls factory/.lock`.

## Session end
Update `CANON/05_CURRENT_STATE.md` (same commit as any status-changing work) and the active
`PLANS/` file's proof boxes. MISSION_LOCK's STATUS TABLE stays the ledger of record.
