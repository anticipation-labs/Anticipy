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
**2026-07-02 ~21:07 PDT — ✅ ALL IN ORDER: clean handoff from build 55a399c (UI step 5); everything flat at baseline** (watchdog pass #18; no wall clock — time from epoch `date +%s`=1783051647 + git `%ct`/`%cr` + file mtimes; ~4.5min after pass #17's 1783051380)
- **FREE PASS (no lock), NOTHING TO FIX:** Booted with `overnight/loop.lock` ABSENT, `overnight/HALT` ABSENT, `factory/.lock` ABSENT — no build cycle running, cleared for full checks. Git tree was **CLEAN** (`git status --porcelain` empty) — pass #17 committed its own heartbeat (`ca5ba1c`) so no stray dirt to stash. No stale lock to clear, no crashed tree to recover, no HALT to honor. Engine + app both already healthy at boot ⇒ no restart/recovery needed this pass.
- **done_gate:** legs 1–4 **PASS**, leg 5 FAIL (human-only finish line — "NO PROOF FILE", expected; no real-stranger day yet). No regression vs baseline. (leg1 live welcome http=200 + premium hero; leg2 app→engine /api/health=200; leg3 caught kids=True + email-Sarah=True + vent-'quit' silenced, 2 cards; leg4 brain held 3/3.)
- **suite:** `113 passed, 9 failed` — EXACT match to loop_state.json baseline (113/9). FAILED set byte-identical & unchanged: owner_mode, owner_ingest_event, owner_upload_ingest, messy_proactive_handoff, onboarding_frontdoor, retraction_silenced, owner_app_product_path, owner_test_day01, create_print_routing_selftest. Set did NOT grow → no HALT.
- **wiring debt:** 35 (baseline; not re-measured — no build edits landed since pass #17 to change it).
- **engine:** UP — 127.0.0.1:8790/health = 200 `{"status":"ok","service":"anticipy-engine","version":"0.1.0"}` (healthy at boot; no restart).
- **app :3100:** UP — `/welcome`=200 at boot (single probe; front door held from pass #17's decisive recovery). No `.next` flake this pass; no restart needed.
- **locks/HALT:** `overnight/loop.lock` ABSENT; `factory/.lock` ABSENT; `overnight/HALT` ABSENT. Nothing stashed.
- **progress:** NOT idle. Last `Anticipy HoE` build commit `55a399c` (record UI step 5 — Connect wired-in) epoch 1783050920 = ~12 min before this pass — well under the 90-min idle threshold; no lock held ⇒ the cycle finished cleanly and the next build cron should fire. Loop advancing; healthy. Next buildable per WAKEUP = UI step 6 (Onboarding fold).
- **FYI / escalation:** No new problems this pass — the front door held 200 (the pass-#17 stale-`.next` flake did NOT re-recur in this handoff). Standing caveat still open (in WAKEUP.md): the Next 15.5.19 dev `.next` chunk-pruning flake has been recurring per-handoff and may eventually need a real fix (pin/upgrade Next, or serve `/welcome` from a prod build) — environmental, not a code regression, gates unaffected. needs-Omar list unchanged (leg 5 = real stranger carried a real day; load the extension in real Chrome; one fresh Twilio token) — all human-only, already in HUMAN_QUEUE.md / WAKEUP.md. Baseline (113/9, wiring 35, legs 1–4) flat across passes #1–#18; no drift. CLAUDE.md still cites the older 109/10 GATE-S baseline (cosmetic; live 113/9 supersedes it).
