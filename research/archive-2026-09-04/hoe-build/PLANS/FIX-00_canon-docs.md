# FIX-00 — One truth: CANON docs + PLANS system + the wiring gate
<!-- status: DONE | milestone: docs foundation | created: 2026-07-02 | updated: 2026-07-02 -->

## Why (2–3 sentences, no jargon)
The repo had ~238 markdown files with at least SEVEN each claiming to be "the source of truth," so
every new session read a different bible and the two documents that actually mattered got missed.
This fix creates ONE front door (`CANON/`), marks everything else as archive, and installs an
automated gate so "built but never wired" can never happen silently again.

## Human check (how Omar verifies without a terminal)
Open the repo folder. There is a `CANON/` folder at the top. Open `CANON/00_START_HERE.md` — it
tells you in plain English what Anticipy is, what to read, and how the agent works. Open any old
doc like `THE_MISSION.md` — the first line says SUPERSEDED and points you back to CANON.

## Step 0 — Preconditions  [x]
**Baseline (2026-07-02):** suite `==== SUITE: 109 passed, 10 failed ====  FAILED: owner_mode
owner_ingest_event owner_upload_ingest messy_proactive_handoff onboarding_frontdoor
retraction_silenced owner_app_product_path premium_copy owner_test_day01
create_print_routing_selftest` · GATE-M (fresh engine :8791, fresh data dir): M1 6/6, M2 PASS,
M3 ALL PASS · HEAD `a1f2028`.
**WIRING PROOF:** pasted above (2026-07-02).

## Step 1 — Write the 7 CANON files  [x]
**What I did:** wrote CANON/00,01,02,03,04,05,99 — each grounded in the real source docs, ≤250 lines,
CANON v1 header on every file.
**Proof command:** `wc -l CANON/*.md` and `for f in CANON/*.md; do head -1 "$f" | grep -q "CANON v1" || echo BAD:$f; done`
**WIRING PROOF (2026-07-02):** 107/150/167/129/84/97/123 lines (all ≤250); zero BAD lines.

## Step 2 — Banners on legacy docs + router pointers  [x]
**What I did:** SUPERSEDED banner on 20 legacy authority docs; banner-with-honor on the 3 source gems
(ANTICIPY_SOURCE_OF_TRUTH.md, ANTICIPY_DONE_VISION_2026-06-15.md, notes/proactive_log.md); README
start-here + MISSION_LOCK pointer → CANON/00.
**Proof command:** the 23-file loop `head -3 "$f" | grep -q SUPERSEDED || echo NOT-BANNERED:$f`
**WIRING PROOF (2026-07-02):** loop output empty — all 23 bannered.

## Step 3 — CLAUDE.md rewrite (the session router)  [x]
**What I did:** replaced the four contradictory "READ X FIRST" banner stacks (121 lines) with one
reading order: CANON/00 → MISSION_LOCK → active PLANS file. Kept non-negotiables, run commands,
concurrency rule. Added the fresh-engine GATE-M protocol (learned 2026-07-02).
**Proof command:** `wc -l CLAUDE.md` and `head -6 CLAUDE.md`
**WIRING PROOF (2026-07-02):** 44 lines; head shows the CANON router.

## Step 4 — PLANS scaffolding  [x]
**What I did:** PLANS/00_OVERARCHING.md (status board FIX-00…19 + rules R1–R5 + supervision guide)
+ PLANS/_TEMPLATE.md (the non-coder step template) + this file.
**WIRING PROOF (2026-07-02):** files exist; board lists 20 FIX rows; template has all required boxes.

## Step 5 — The wiring gate  [x]
**What I did:** factory/bin/check_wiring.py (3 checks: endpoint→product-caller, route→UI-caller,
orphan/test-only modules; conservative matching; --quiet/--strict/--list) + factory/wiring_allowlist.txt
(4 permanent entries + 45 TODO(FIX-NN) debt lines = the verified plumbing map). Reconciled the gate's
5 newly discovered seams into CANON/03 §5 + the PLANS board as FIX-14…18 (wiring-strict moved to FIX-19).
**Proof command:** `engine/.venv/bin/python factory/bin/check_wiring.py --quiet; echo exit=$?` and `--strict`
**WIRING PROOF (2026-07-02):** `WIRING: CLEAN (65 endpoints / 45 routes / 103 modules checked,
49 allowlisted incl. 45 TODO-debt)` exit=0 · strict: `WIRING: 45 unwired — FAILS` (by design).

## Final step — The gates + commit  [x]
**Command:** `bash scripts/run_suite.sh | tail -3` (fail-set must equal Step-0 baseline; wiring_gate
appears as a NEW pass) then the ordered commits (CANON → banners+pointers → CLAUDE.md → PLANS → gate).
**WIRING PROOF (2026-07-02):** `==== SUITE: 110 passed, 10 failed ====  FAILED: owner_mode
owner_ingest_event owner_upload_ingest messy_proactive_handoff onboarding_frontdoor
retraction_silenced owner_app_product_path premium_copy owner_test_day01
create_print_routing_selftest` — 109→110 = exactly the new wiring_gate pass; FAILED set
byte-identical to the Step-0 baseline.
