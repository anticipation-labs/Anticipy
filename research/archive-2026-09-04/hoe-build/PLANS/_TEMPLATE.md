# FIX-NN — <plain-English title>

<!-- status: OPEN | milestone: M? | created: YYYY-MM-DD | updated: YYYY-MM-DD -->

## Why (2-3 sentences, no jargon)

<What is broken or missing today, why it matters to the product Omar is trying to ship, and what will be true when this fix is done. Write it so someone who has never opened the code nods along.>

## Human check (how Omar verifies the whole fix without a terminal)

<One concrete thing Omar can do with his own eyes/hands — open the app, click X, say Y, receive a text — that only works if this fix is real. No commands, no logs.>

## Step 0 — Preconditions [ ]

**What I'm doing:** Making sure we're on the right branch with the engine alive, and recording the baseline so "not worse" has a number attached.

**Command to run:**
```bash
git branch --show-current
curl -s http://127.0.0.1:8787/health
```

**Expected output:** The branch name for this plan (e.g. `hoe/build`) on the first line, and a small JSON health blob (e.g. `{"status":"ok",...}`) from the engine on the second.

**What BROKEN looks like:**
- `curl: (7) Failed to connect ... Connection refused` → the engine isn't running. Start it with: `cd engine && .venv/bin/python -m app.main` (or the repo's documented engine start command), wait ~5 seconds, retry the curl.
- Wrong branch name → stop; check out the plan's branch before doing anything else.

**Baseline (defines "not worse"):**
```bash
bash scripts/run_suite.sh | tail -3
engine/.venv/bin/python factory/bin/check_wiring.py | tail -3
```
Paste BOTH tails below. The suite's failing tests here = the baseline fail-set; the wiring failure count here = the baseline count. Every later step is judged against these two numbers.

**WIRING PROOF:**
```
<paste real output + date here — Step 0 is NOT done until this box is filled>
```

## Step N — <one plain-English action> [ ]

**What I'm doing (plain English):** <One sentence a non-coder understands. One action only — if you need "and", it's two steps.>

**Files touched:** <exact paths>

**Command to run (copy-paste, one block):**
```bash
<exactly ONE proof command — the single command whose output proves this step worked>
```

**Expected output (what GOOD looks like):** <the literal line(s) you expect to see, or a short description precise enough that Omar can eyeball-match it>

**What BROKEN looks like (2-3 realistic failures, each with meaning):**
- `<realistic error output 1>` → <what it means and what to do>
- `<realistic error output 2>` → <what it means and what to do>
- `<realistic error output 3>` → <what it means and what to do>

**Rollback (written BEFORE the step runs — R5):** `git checkout -- <files>` if uncommitted, or `git revert <sha>` once committed. <Note anything else to undo: a migration, a cron entry, a config line.>

**WIRING PROOF (step is NOT done until this box holds real pasted output + date):**
```
<paste real output + date here>
```

## Final step — The gates + commit [ ]

**What I'm doing:** Proving the repo is not worse than Step 0, then committing the code and this plan file together.

**Command to run:**
```bash
bash scripts/run_suite.sh && engine/.venv/bin/python factory/bin/check_wiring.py
```

**Expected output:** suite fail-set ⊆ baseline; wiring failures < baseline count (or equal, never higher).

**Then commit (the plan file rides WITH the code it proves):**
```bash
git add -A && git commit -m "FIX-NN: <plain-English title>"
```

**WIRING PROOF:**
```
<paste both gate tails + the commit sha + date here>
```
