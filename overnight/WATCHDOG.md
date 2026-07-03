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
   - **App down / `.next` flake?** `curl -s -m5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3100/welcome`.
     If NOT 200 (the recurring stale-`.next` 404/500 — environmental, not code), fix it so the UI never
     sits broken between cycles: kill the `:3100` listener (`lsof -tiTCP:3100 -sTCP:LISTEN | xargs kill`),
     `rm -rf .next`, restart `nohup npx next dev -p 3100 > logs/next_dev_3100.log 2>&1 &`, wait for
     `/welcome`=200; log it as RECOVERED. (Safe mid-build — it doesn't touch git.)
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
**2026-07-02 ~19:51 PDT — ✅ ALL IN ORDER** (watchdog pass #10; no wall clock — time est. from git `%cr`/`%ct` + file mtimes)
- **CONCURRENCY:** a build cycle IS RUNNING this pass — `overnight/loop.lock` PRESENT & FRESH (age ~5 min at re-check, content epoch `1783046729`), `factory/.lock` ABSENT. Per the concurrency rule I stayed READ-ONLY on git: NO stash, NO commit, NO lock clear. Live cycle is mid-edit (`git status` = `M app/globals.css`, `M app/phase-zero/PhaseZeroApp.js` — UI step 3 "Sign" in progress). Fresh lock ⇒ this dirty tree is a LIVE cycle, NOT a crash ⇒ did NOT stash (correct). This STATUS block written UNCOMMITTED (build cycle or next pass will carry it).
- **done_gate:** legs 1–4 PASS, leg 5 FAIL (human-only finish line — "NO PROOF FILE", expected; no real-stranger day yet). No regression vs baseline. (leg1 welcome http=200 + premium hero; leg2 app→engine /api/health=200; leg3 caught kids=True + email-Sarah=True, vent-'quit' silenced, 2 cards; leg4 brain held 3/3.)
- **suite:** `113 passed, 9 failed` — EXACT match to loop_state.json baseline (113/9). FAILED set unchanged & identical: owner_mode, owner_ingest_event, owner_upload_ingest, messy_proactive_handoff, onboarding_frontdoor, retraction_silenced, owner_app_product_path, owner_test_day01, create_print_routing_selftest. Set did not grow → no HALT.
- **wiring debt:** 35 TODO-debt (== baseline); `check_wiring.py` = CLEAN (non-strict, 66 endpoints / 49 routes / 95 modules, 42 allowlisted incl. 35 TODO-debt).
- **engine:** UP — 127.0.0.1:8790/health = `{"status":"ok","service":"anticipy-engine","version":"0.1.0"}`.
- **app :3100:** HEALTHY — `/welcome`=200 (5/5 re-probes), `/`=200. First probe caught a **transient 404** (concurrent build's in-flight compile: `.next` written 76s prior, `/_not-found` compiled, `/welcome` had been 200 immediately before) — re-probed 5× and it self-healed to 200. Did NOT `rm -rf .next` (it was an in-flight compile, not a stale-between-cycles flake, and nuking would collide with the live build). No recovery action needed.
- **locks/HALT:** `overnight/loop.lock` PRESENT & FRESH (build active), `factory/.lock` ABSENT, `overnight/HALT` ABSENT. Nothing stashed (fresh lock ⇒ live cycle, not a crash).
- **progress:** NOT idle — last `Anticipy HoE` build commit `273a052` (UI step 2) ~27 min ago (within the 90-min window) AND a cycle is actively editing right now. Healthy and advancing.
- **FYI (non-blocking, not escalated):** baseline (113/9, wiring 35) stable & flat across passes #1–#10; no drift. Known env issues unchanged (SSR hydration mismatch; dev `/api/*` 503; transient in-flight `.next` 404 during compiles) — all in loop_state known_issues, zero gate impact. CLAUDE.md still cites the older 109/10 GATE-S baseline (cosmetic; live 113/9 supersedes it). Nothing new to escalate to Omar this pass.
