# FIX-01 — One pipeline: delete the dead engines, consolidate to one extractor
<!-- status: IN-PROGRESS | milestone: M1 durability | created: 2026-07-02 | updated: 2026-07-02 -->

## Why (2–3 sentences, no jargon)
The codebase carried ELEVEN versions of the proactive engine — two live ones that overlap, four
competing "did-they-commit" judges, and a dead scaffold whose class name collides with the real
engine, so every new session risked building on the wrong one. This fix deletes the dead ones and
funnels everything through ONE pipeline: one front door → one extractor → one safety gate → one spine.

## Human check (how Omar verifies without a terminal)
Open `CANON/02_PROACTIVE_ENGINE.md` — the graveyard table says which engine is THE one. Then type a
messy day into the app (localhost:3100) — cards still appear exactly as before; nothing feels different,
because only dead code left.

## Step 0 — Preconditions  [x]
**Baseline (2026-07-02, post-FIX-00):** suite `110 passed, 10 failed` (FAILED: owner_mode
owner_ingest_event owner_upload_ingest messy_proactive_handoff onboarding_frontdoor
retraction_silenced owner_app_product_path premium_copy owner_test_day01 create_print_routing_selftest)
· wiring gate `WIRING: CLEAN (65 endpoints / 45 routes / 103 modules checked, 49 allowlisted incl.
45 TODO-debt)` · GATE-M fresh-engine: M1 6/6, M2 PASS, M3 ALL PASS.
**WIRING PROOF:** pasted above (2026-07-02).

## Step 1 — Delete the dead brain scaffold (9 modules)  [x]
**What I did:** deleted `brain.py`, `proactive/engine.py` (+ its `__init__` re-export — kills the
ProactiveEngine name collision), and the scaffold's exclusive dependency cluster: `actions/` (whole
package: layer/gate/connector/browser/__init__) + `capture/intake.py` + `model/client.py` +
`engine/scripts/test_actions.py` (not in the suite). Burned their 7 `TODO(FIX-01 delete)` allowlist lines.
**Honest correction along the way:** the gate had also tagged `core/workers/{browser,connector}.py`
for deletion — WRONG: they are the suite's mock workers (BrowserStub/ConnectorStub), re-exported by a
product `__init__` and used by 20+ suite tests. Restored both and allowlisted them as permanent
test-infrastructure with an honest justification.
**Proof command:** `PYTHONPATH=engine engine/.venv/bin/python -c "import anticipy_engine.main"` +
`grep -rn "from .engine import ProactiveEngine|anticipy_engine.brain" engine/anticipy_engine --include='*.py'`
**WIRING PROOF (2026-07-02):** `import OK`; grep empty.

## Step 2 — Delete the broken /hands/compose-email endpoint  [x]
**What I did:** the endpoint imported `hands/cdp_client`, a module that DOES NOT EXIST — every call
500'd (a lie in the API surface). Deleted the endpoint + its model; left a tombstone comment pointing
at FIX-13 (the REAL compose hand, to be built through the browser-hand path). Burned its allowlist line.
**Rollback:** `git revert` the Phase-1 commit.
**Proof command:** `grep -n "compose-email" engine/anticipy_engine/main.py` (only the tombstone) + import probe.
**WIRING PROOF (2026-07-02):** import OK; gate now enumerates 64 endpoints (was 65).

## Step 3 — Delete overnight/track_b/decider.py  [x]
**What I did:** the archival ancestor of `proactive/decider.py` (out-of-tree research seed). Scorer kept
(data artifact; doesn't import it).
**WIRING PROOF (2026-07-02):** `git rm` clean; no suite/engine references.

## Step 4 — The gates  [x]
**Command:** suite + wiring gate + GATE-M (fresh engine, fresh data dir).
**WIRING PROOF (2026-07-02):** suite `110 passed, 10 failed` — FAILED set byte-identical to Step-0 ·
wiring `WIRING: CLEAN (64 endpoints / 45 routes / 94 modules checked, 43 allowlisted incl. 37
TODO-debt)` — debt burned 45→37 · GATE-M: `M1 BATTERY: 6/6 pass`, `M2 COPY: PASS`,
`M3 INTEGRATION: ALL PASS`.

## Step 5 — Phase 2: ONE extractor (consolidate MOAT + Room-1.5 onto decision_pipeline)  [x]
**What I did:**
- **2a** factored the deterministic stub branch into `_deterministic_expand()` (byte-identical) +
  `ANTICIPY_MOAT_FALLBACK` flag, default legacy. GATE-S 110/10 byte-identical; GATE-M all green.
- **2b** live A/B, fresh engine, `ANTICIPY_MOAT_FALLBACK=0`: `M1 BATTERY: 6/6 pass`, `M2 COPY: PASS`,
  `M3 INTEGRATION: ALL PASS` (2026-07-02).
- **2c** deleted the second model brain: `proactive/extract.py` + `_expand_tasks_with_model` +
  `_build_from_day_tasks` + `_expand_per_line` (−266 lines in control_core + the module). The fork
  now reads: decision_pipeline OR `_deterministic_expand` — never a second model. The flag was
  removed (moot). **Honest bump:** `preview_moat_rescue` broke — it monkeypatched the deleted
  function to simulate the model; adapted its injection seam to `_deterministic_expand` (same lock,
  same 3 assertions) → PASS. GATE-S back to 110/10 byte-identical. GATE-M fresh post-deletion:
  6/6 · PASS · ALL PASS.
- **2d** `decide_line()` adapter added to decision_pipeline (one line → ACT/ASK/SILENT/UNAVAILABLE;
  one-way safe: block/ask/follow_up→ASK, never ACT; mixed→safest). `Decider.decide` delegates ONLY
  behind `ANTICIPY_DECIDER_BRAIN=pipeline`; **default stays legacy** — the legacy prompt encodes
  single-line narration-vs-handoff distinctions tuned against a live probe bank that NO LONGER
  EXISTS in-repo, so a flip without a rebuilt validation bank would be plausible-but-unproven.
  Mapping unit-verified 6/6 (act→ACT, block→ASK, ignore→SILENT, third-party→SILENT, mixed→ASK,
  unavailable→UNAVAILABLE).
- **2e** (owner_mode shrink) deferred — optional, lowest priority, separate step when taken.
**WIRING PROOF (2026-07-02):** pasted per sub-step above; final suite tail:
`==== SUITE: 110 passed, 10 failed ==== FAILED: <byte-identical baseline set>`.

## Deferred (explicit, so nothing silently drifts)
- **Decider brain flip** (`ANTICIPY_DECIDER_BRAIN=pipeline` as default): BLOCKED-ON a rebuilt
  single-line probe bank (the old probe_decider.py evidence is gone). Until then legacy stays.
- **2e owner_mode shrink**: one dead branch per commit, GATE-S each — when prioritized.
