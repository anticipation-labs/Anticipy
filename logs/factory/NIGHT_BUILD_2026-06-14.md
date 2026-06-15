# ANTICIPY — AUTONOMOUS NIGHT BUILD (2026-06-14 → morning 2026-06-15)
**Single source of truth for the overnight loop. Each 3-min heartbeat tick reads THIS first.**
Omar is asleep; a critical investor meeting is in the morning. Mandate: finish the buildable work
and — above all — **never break the demo.** The worst acceptable outcome is "some slices unfinished."
The unacceptable outcome is "the demo is broken / a claim is fake."

## KNOWN-GOOD BASELINE (the floor the loop must NEVER drop below)
- Green commit: **c0925cd** — tagged `night-baseline-green`. Suite 77/77, mega-eval 0 breaches.
- To restore the demo to a guaranteed-bootable state at any time: `git checkout night-baseline-green`.
- Demo stack live: engine `:8787` (ws connected), web `:3000` (200). Do NOT kill these.

## HARD INVARIANTS (violating any is worse than doing nothing)
1. **HEAD and the WORKING TREE must STAY green.** Commit a slice ONLY after BOTH:
   `bash scripts/run_suite.sh` is fully GREEN, and
   `ANTICIPY_MODEL_PROVIDER=stub ANTICIPY_HANDS_MODE=mock ANTICIPY_CHANNELS_MODE=mock PYTHONPATH=engine engine/.venv/bin/python engine/scripts/safety_mega_eval.py` exits 0.
   If a change can't be made green: `git restore` the touched files + delete any new files so the
   working tree returns to the last green commit (the demo boots from the working tree — keep it green),
   mark the slice BLOCKED in the progress log, move on.
2. **Never** `git reset --hard` or discard committed work. **Never push to origin** (no overnight deploy —
   the live site must not change before the meeting). **Never** kill the demo engine `:8787` or web `:3000`
   (test new endpoints on a DIFFERENT port, e.g. 8799).
3. **Never** place a live Twilio call/SMS (Omar is asleep — a night call is catastrophic). **Never** spend
   money. **Never** act on a vent. Money + cardinal-sin stay sacred.
4. **Never** touch `factory/` control plane, `personas/`, the scoreboard, `scripts/realday.sh`, or read
   `factory/personas/holdout/`. Leave `factory/.halt` in place — do NOT kickstart the nightly Factory laps
   (they're saturated and would no-op/re-halt; this loop is the PRODUCT build, not the metric loop).
5. **Receipts, never claims (Law 4 + Law 5).** Every slice: build → suite GREEN + floor 0 → an INDEPENDENT
   skeptic agent tries to refute the receipt and FAILS → commit locally → append a receipt to
   `logs/factory/RECEIPTS.md` + a line to the PROGRESS LOG below. Label anything that needs Omar's real
   Chrome / real account / real days as **"live-proof pending Omar"** — do not fake it.

## PER-TICK PROCEDURE
1. Read this file + `git log --oneline -6`. Continue from current state; never redo a finished slice.
2. If a build is already in flight (a background suite/skeptic running), just check status and let it
   finish — don't start conflicting work.
3. Do ONE concrete step of the current slice. Verify per the invariants. Commit if green. Log it.
4. Then end the turn — the next heartbeat tick or a background-task completion continues.

## SLICE QUEUE (build in order; skip any step that needs Omar, note it, move to the next)
- [ ] **Slice 1 — Onboarding Chrome-scrape → per-person mesh** (the MIDDLE; the "custom to every person"
      piece). Approach (per recon): (a) ENGINE side, fully buildable+testable now — an ingestion endpoint
      that accepts a discovered-connections payload and builds the mesh via the existing
      `owner_onboarding` model + the now-wired token vault (each discovered service → a profile card + a
      "Connect X" open-loop + route); test with a simulated extension payload. (b) EXTENSION side — a new
      `discover_connections` intent in `extension/background.js` that DOM-scrapes which services the user
      is logged into (reuse `doObserve` + the auth-wall detector). Extension code is written but its LIVE
      proof needs the extension reloaded in Omar's real Chrome → label "live-proof pending Omar".
      Anchors: `engine/anticipy_engine/owner_onboarding.py`, `main.py` (/owner/onboard ~782, /ws/extension
      ~1389), `extension/background.js:64-74,211-273,104-106`.
- [ ] **Slice 2 — browser-use CDP attach to the logged-in Chrome + route action cards.** Add a
      `connect_over_cdp` option to `hands/browser_use_runner.py` (BrowserSession cdp_url=) so the proven
      agent can act in a Chrome launched with `--remote-debugging-port` (reuse the native-bridge pattern
      at `core/native_bridge_link.py:817-889`). Verify the CDP-attach MECHANISM autonomously (launch a
      Chrome with a throwaway profile + debug port, attach, do a READ). Route action-shaped `browse_task`
      cards to `browse_act` behind an env flag at `hands/browser_hand.py:162,288`. The logged-IN proof
      needs Omar's Chrome → "live-proof pending Omar".
- [ ] **Slice 3 — 5-day Owner Test harness + selftest.** Build the scorer/runner under `factory/owner/`
      (NOTE: only `factory/owner/expected/` content is data, not control-plane — do not touch other
      factory/ files) OR under `engine/scripts/`: takes a day transcript + expected key → scores
      catch/false/harm/e2e with a self-proving planted quartet (model on `persona_score`'s selftest).
      Running Omar's REAL 5 days needs his days + red-pen → "pending Omar".
- [ ] **Continuous — keep docs current:** RECEIPTS + this progress log + (at the end) the morning report.

## STOP CONDITION
When every buildable slice is DONE or BLOCKED: write `logs/factory/MORNING_REPORT_2026-06-15.md` (honest
done/partial/blocked with receipt pointers, demo-readiness verdict, Omar's remaining human-only bundle),
then `CronDelete` the heartbeat job and idle. Do NOT grind no-op ticks.

## OMAR'S REMAINING HUMAN-ONLY BUNDLE (carry forward to the morning report)
- Notarize: `xcrun notarytool store-credentials anticipy-notary --apple-id omarkebrahim@gmail.com --team-id 49T86P9XGW` (app-specific password) → then `bash macapp/scripts/sign_and_notarize.sh`.
- One OAuth tap for Google Calendar/Gmail (live API arm proof).
- One supervised ~15-min voice run (reply "YES <code>" to a test SMS) → makes voice actually true.
- His 5 real days + ~20-min holdout red-pen (Owner Test honesty bar).

## PROGRESS LOG (append-only; newest at bottom)
- 2026-06-14 ~night start — baseline c0925cd green (77/77, floor 0). Loop armed (3-min heartbeat).
  Slice queue set. Building Slice 1 next.
