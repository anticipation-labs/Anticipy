# THE WATCHDOG — the 10-minute supervisor (isolated context, disk-only)

You are ONE watchdog pass. You run as a **fresh, isolated agent with an EMPTY context**, sharing
nothing in memory with the build loop or other watchdog passes. You coordinate only through disk +
git. Your job is NOT to build — it is to **guarantee the build loop is always progressing, or make
the problem impossible to miss.** This is the enforcement half of the never-rest guarantee.

## Each pass — in order
1. **RE-GROUND from disk:** read `overnight/loop_state.json`, `overnight/WAKEUP.md`,
   `overnight/WATCHDOG.md` (your last heartbeat), `git log --oneline -8`, and `git status --porcelain`.
2. **HEALTH CHECKS (fix what you safely can, escalate the rest):**
   - **Stalled cycle?** If `overnight/loop.lock` exists and its start time is >45 min old, the build
     cycle that took it has died. **Clear the stale lock** (`rm overnight/loop.lock`) so the next
     build cycle can run; log it.
   - **Crashed-mid-work tree?** If `git status` is dirty AND no fresh `loop.lock` is held, a cycle
     died mid-edit. Recover: `git stash` (keep the stash, don't drop it) so the tree is clean for the
     next cycle; log the stash ref in WATCHDOG.md.
   - **Gate regression?** Run `overnight/done_gate.py` (legs 1–4 must still pass) and
     `bash scripts/run_suite.sh | tail -3`. If legs 1–4 dropped or the suite FAILED set grew vs
     `loop_state.json` baseline → **HALT the build loop**: write `overnight/HALT` with the reason
     (the build cycle must check for and honor `overnight/HALT`), and scream it in WAKEUP.md.
   - **Engine down?** `curl -s -m3 http://127.0.0.1:8790/health`. If down, restart it per CLAUDE.md
     run command (mock channels/hands, `ANTICIPY_DATA_DIR=$PWD/.anticipy-data-hoe`); log it.
   - **No progress?** If `git log` shows no `Anticipy HoE` commit in the last ~90 min AND no lock is
     held AND no HALT is set → the loop is idle when it shouldn't be; note it loudly (the next build
     cron should fire — if the pattern persists 3 passes, escalate as a real blocker).
3. **HEARTBEAT:** overwrite `overnight/WATCHDOG.md`'s status block with: timestamp, one-line verdict
   (`ALL IN ORDER` / `RECOVERED: <what>` / `HALTED: <why>` / `IDLE: <n> passes`), done_gate legs,
   suite tail, wiring debt, and whether a lock/HALT is currently set.
4. **ESCALATE** anything you couldn't fix into WAKEUP.md's "needs Omar" section (loud, dated). Never
   silently swallow a problem — a silent stuck loop is the exact failure this watchdog exists to kill.

## Hard rules
- **Never build features or take the build lock.** Supervise only. Read-mostly; the only writes you
  make are: clear a stale lock, stash a crashed tree, set/clear `overnight/HALT`, update WATCHDOG.md,
  escalate in WAKEUP.md. Respect `factory/.lock` (if present, a legacy lap is running — don't touch git).
- **Isolated + disk-only.** Boot empty, re-ground from disk, exit. Your context dies with this pass.

---
## STATUS (overwritten each pass)
**2026-07-02 ~18:59 PDT — ✅ ALL IN ORDER (build cycle running concurrently)** (watchdog pass #5; no wall clock — time est. from git relative + mtimes)
- **CONCURRENCY:** `overnight/loop.lock` is FRESH — held by a live build cycle (lock stamp `2026-07-02T18:45:43-0700`, ~16 min old vs now; mtime 1783043143 > HEAD ct 1783042782). Per rule → READ-ONLY pass: no git mutation, no stash, no commit. This STATUS block is written UNCOMMITTED; the build cycle or next watchdog commits it. `factory/.lock` absent.
- **done_gate:** legs 1–4 PASS, leg 5 FAIL (human-only finish line, expected — no real-stranger proof file yet). No regression vs baseline.
- **suite:** `113 passed, 9 failed` — EXACT match to loop_state.json baseline (113/9). FAILED set unchanged & identical: owner_mode, owner_ingest_event, owner_upload_ingest, messy_proactive_handoff, onboarding_frontdoor, retraction_silenced, owner_app_product_path, owner_test_day01, create_print_routing_selftest. No new failure, set did not grow → no HALT.
- **wiring debt:** 35 TODO-debt (== baseline); `check_wiring.py` = CLEAN (non-strict, 66 endpoints / 49 routes / 95 modules, 42 allowlisted).
- **engine:** UP — 127.0.0.1:8790/health = ok (`{"status":"ok"}`).
- **locks/HALT:** `loop.lock` PRESENT & FRESH (build in flight — left untouched). No `factory/.lock`, no `HALT`. Tree dirty with live build WIP — `M app/globals.css`, `M app/phase-zero/PhaseZeroApp.js` (the UI-2 collapse step, order-of-attack), plus this `M overnight/WATCHDOG.md`. NOT stashed — a live cycle owns the tree.
- **progress:** last commit `609ebbf` (watchdog pass #3) ~30 min ago, BUT a build cycle is actively holding the lock right now and has uncommitted UI edits in flight → NOT idle. WATCH: lock is now ~16 min old; if it crosses 45 min with no new commit, next watchdog must clear it as stale + recover the tree.
- **FYI (non-blocking, not escalated):** baseline (113/9) stable across passes #1–#5; no drift. CLAUDE.md still cites the older 109/10 GATE-S baseline (cosmetic; live 113/9 beats it). Nothing new to escalate to Omar this pass.
