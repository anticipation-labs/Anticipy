# NEXT GATE — exactly one, with objective receipts

## ACTIVE: Gate A — Truth & continuity (closing now)

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
