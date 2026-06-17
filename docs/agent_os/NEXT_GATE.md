# NEXT GATE — exactly one, with objective receipts

## ✅ CLOSED 2026-06-16
- **Gate A — Truth & continuity:** Memory Dock committed; route/suite/safety/reality re-verified
  (suite GREEN 90/0, `safety_mega_eval` 0 breaches, reality 6/7 me-verifiable). See R-2026-06-16-A.
- **Browser arm "prepare when confident"** (Omar's decision) + b82e660 regression fixes landed (`f05d453`).
  See R-2026-06-16-B + FAILURES F-011.

## ✅ CLOSED 2026-06-16 (cont.)
- **Gate 1 — app → real brain → visible cards:** driven in Chrome at localhost:3000, transcript →
  Caught/Waiting/Left-for-you sections, vents silent, money parked. See R-2026-06-16-C. (Engine was a
  stale 500ing process; restarted on fixed code, channels=mock.)

## ✅ CLOSED 2026-06-16 — Gate 2: duplicate-obligation collapse
Engine-side semantic consolidation; proven in the real app UI (8-line → 4 cards, vents silent, money
parked, NO duplicates). Commit `0320127`. See R-2026-06-16-D + F-012. (Also recovered from ENOSPC:
freed caches → 8.3Gi.)

## 🎯 CERT QUEUE (release-certification packet, 2026-06-17)
1. **10k cert (running):** on completion, triage `critical_failures.jsonl` (1 nondeterministic slip
   expected), fix root or tighten engine, then **rerun the full 10k with the 11-type harness**
   (incl. wrong_account) → 0 critical → record receipt.
2. **Follow-up scheduling (CONFIRMED GAP, packet 06):** the engine has timed reminders (`remind_ts`/
   `trigger_tick`) but does NOT auto-create a follow-up check after handling a task ("I set a follow-up
   for two weeks"). Build: when an obligation is handled/parked and warrants a check, schedule a
   future follow-up trigger + surface it; add a harness `follow_up` scenario+check. Critical class:
   "follow-up missing when required."
3. **MP3 + listening same-brain (packet 05):** `owner_upload_ingest` covers upload; confirm listening
   path parity in a cert run, not just unit.
4. Owner-gated (Gmail/Twilio/deploy/signing/5-days) → PENDING_FOR_OMAR.md.

## (earlier) Gate 3 — memory/profile handoff (DONE via intent layer; see R-2026-06-16-E)
- **Goal:** plant context earlier in the day; a later VAGUE reference resolves to the RIGHT thing
  (not the wrong obligation); ambiguous references ask/park, never wrong-act; memory generous but inert.
- **Receipt (real app):** transcript where line A establishes context ("the Henderson contract came in")
  and line B refers vaguely ("get that thing reviewed by Friday") → ONE card "review the Henderson
  contract", NOT a kid-pickup or a fabricated referent. A truly-ambiguous reference → clarify/park, not act.
- **Where:** `proactive/extract.py` already resolves references from rolling context; verify + harden,
  add a deterministic test, prove in the UI. Keep suite GREEN + `safety_mega_eval` 0.

## (superseded) earlier active note — dedup over-extraction
- **Why:** the live UI shows the same task 2–3× (Amazon ×3, Sam ×2, pickup ×2) = spam (Omar's #1 ban).
  See FAILURES F-012. Safe (all parked, vents silent) but feels dumb.
- **Receipt:** an eval transcript where one action is stated + confirmed across ≥2 lines yields exactly
  ONE card; suite stays GREEN; `safety_mega_eval` 0 breaches; re-driven in the UI shows no duplicates.
- **Where:** `engine/anticipy_engine/proactive/extract.py` (moat split) + `control_core._spine_card`
  (the "Confirm task:" variant + confirmation-as-new-task). Dedup must be SEMANTIC (same action/target).

## OTHER candidates (Omar-gated; he gave blanket approval + Chrome auth)
- **Gate D — Gmail draft prepare-and-park (live):** create a `[Anticipy test]` Gmail DRAFT (reversible,
  never sent), re-read by ID, delete. **BLOCKED:** only Google Calendar is connected; needs Omar to
  authorize Gmail (Arcade `gmail.compose`) — he offered to tap an auth tab. Receipt: draft ID + read-back.
- **Gate E live — real-site browser auto-cart:** prove the throwaway-browser auto-cart actually runs on a
  real site (read/cart only, money/checkout guard). Receipt: final URL + screenshot/DOM + guard log.
- **Off-localhost / inbound-text / 5-day owner test:** Omar-gated (see CURRENT_TRUTH).

---

## (historical) Gate A — Truth & continuity — receipts that were required

**Goal:** the Memory Dock exists, the mission cannot be forgotten, and the claimed-proven state is
re-verified by failable checks (not trusted from prior reports).

**Receipts required (each must be able to FAIL):**
1. Memory Dock committed to `factory/build` (no `factory/.lock` present at commit time). ✅ when SHA exists.
2. `bash scripts/agent_os/preflight.sh` runs clean: repo/branch/lock-halt printed, engine `/status`
   reachable, secret-scan finds no tracked `.env*`. → output saved under `docs/agent_os/`.
3. **Suite green:** `bash scripts/run_suite.sh` → PASS count recorded (expected ~89–90/0).
4. **Cardinal-sin floor:** `safety_mega_eval` → **BREACHES 0** (run independently).
5. **Reality gate:** `factory/bin/reality_check.py` → record N/8 (honest, not gamed).
6. **Model route:** a real call confirms provider/base-url/model without printing secrets, returns fast
   (RESEARCH_LEDGER lane 1). If route is broken, that becomes the gate before any build.

**Skeptic criteria:** docs don't redefine done smaller; no receipt is claimed without a check that ran;
the live-engine `channels=live` watch-item is recorded (no autonomous sends).

When 1–6 pass → Gate A closed → append to RECEIPTS.md → pick the on-deck gate below.

---

## ON DECK (pick after Gate A, foreman's call from re-verified truth)

Highest-leverage, safe, autonomously-provable candidates (no live external send, no DEV-FINAL):

- **Gate D (API arm — Gmail draft prepare-and-park):** create a `[Anticipy test]` Gmail **draft** via
  the API arm (reversible, never sent), re-read it by ID, then delete it. Extends the proven calendar
  read-back pattern to email. Receipt: draft ID + independent read-back JSON (redacted) + cleanup proof.
- **Engine-side over-asking fix (F-008, brain core):** one rambling vent over-generates many asks; the UI
  scrubs/dedupes but the engine still emits them. Fix at the source (cadence/dedupe in the proactive
  engine), gated on `safety_mega_eval` BREACHES 0. This is real core work (PRD NF8–NF12).
- **Browser arm decision (Gate E groundwork):** evaluate adopting `browser-use` vs hardening the
  in-house agent (RESEARCH_LEDGER lane 2) — research → decision, not a rebuild yet.

**Do NOT** start: live channel sends, off-localhost deploy, DEV-FINAL commits, the 5-day owner test —
those are Omar-gated (see CURRENT_TRUTH).
