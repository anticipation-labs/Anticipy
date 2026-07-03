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
**2026-07-02 ~20:40 PDT — 🔧 RECOVERED: app :3100 stale-`.next` 404 auto-fixed to 200** (watchdog pass #15; no wall clock — time from epoch `date +%s`=1783049976 + git `%cr`/`%ct` + file mtimes)
- **CONCURRENCY:** Pass BOOTED with `overnight/loop.lock` ABSENT, `factory/.lock` ABSENT, `overnight/HALT` ABSENT → NO build cycle running → free to mutate. Git tree CLEAN at boot (no crashed tree, no stash needed). Re-verified all locks ABSENT + tree clean immediately before committing this heartbeat.
- **done_gate:** legs 1–4 PASS, leg 5 FAIL (human-only finish line — "NO PROOF FILE", expected; no real-stranger day yet). No regression vs baseline. (leg1 welcome http=200 + premium hero; leg2 app→engine /api/health=200; leg3 caught kids=True + email-Sarah=True, vent-'quit' silenced, 2 cards; leg4 brain held 3/3.) Note: ran AFTER app recovery so leg1 didn't false-fail on the boot-time 404.
- **suite:** `113 passed, 9 failed` — EXACT match to loop_state.json baseline (113/9). FAILED set unchanged & identical: owner_mode, owner_ingest_event, owner_upload_ingest, messy_proactive_handoff, onboarding_frontdoor, retraction_silenced, owner_app_product_path, owner_test_day01, create_print_routing_selftest. Set did not grow → no HALT.
- **wiring debt:** 35 — RE-MEASURED this pass: `WIRING: CLEAN` (66 endpoints / 49 routes / 95 modules checked, 42 allowlisted incl. 35 TODO-debt). Matches baseline.
- **engine:** UP — 127.0.0.1:8790/health = 200 `{"status":"ok","service":"anticipy-engine","version":"0.1.0"}`.
- **app :3100:** 🔧 RECOVERED — booted serving `/welcome`=404 (the recurring stale-`.next` flake) with NO lock held. Fix per LOOP note: killed the :3100 listener (pid 9452) + `rm -rf .next` + restarted ONE `nohup npx next dev -p 3100` (new listener pid 10865). `/welcome` came back 200. One transient `/welcome`=404 mid-pass right after next compiled `/_not-found` (a known dev-recompile blip, self-resolved) — final multi-probe = 5/5 stable 200, plus `/`=200 and `/setup`=200. UI healthy at end.
- **locks/HALT:** all ABSENT at end of pass (`overnight/loop.lock`, `factory/.lock`, `overnight/HALT`). Nothing stashed — tree was clean at boot.
- **progress:** NOT idle — last `Anticipy HoE` build commit `7cfd25a` (UI step 4 — Setup absorbs /download) ~12 min ago. Loop advancing: order-of-attack on UI-5 Connect wire-in (substeps_remaining: UI-5,6,8,9 + delete /mp3,/go-to,/great,/done). Healthy.
- **FYI (non-blocking, not escalated):** Nothing new for Omar. The :3100 stale-`.next` flake is environmental (already in loop_state known_issues + recovered here); NOT a code regression, so not escalated. needs-Omar list unchanged (leg 5 = real stranger carried a real day; load the extension in real Chrome; one fresh Twilio token) — all human-only, already in HUMAN_QUEUE.md / WAKEUP.md. Baseline (113/9, wiring 35, legs 1–4) flat across passes #1–#15; no drift. CLAUDE.md still cites the older 109/10 GATE-S baseline (cosmetic; live 113/9 supersedes it). Nothing to escalate this pass.
