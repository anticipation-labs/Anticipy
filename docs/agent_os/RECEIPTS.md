# RECEIPTS — append-only ledger of what is PROVEN done

A receipt is a human-openable artifact + an independent skeptic verdict. No receipt, no done.
This file is append-only. The deep historical ledger is `logs/factory/RECEIPTS.md` +
`logs/factory/FOREMAN_STATE.md`; entries below are the Agent-OS summary (re-verify before trusting).

---

### R-2026-06-16-A — Memory Dock (Gate A continuity) installed
- **Gate:** A — Truth & continuity.
- **Commit:** (this session — see git log for SHA).
- **Artifact:** `docs/agent_os/{README,CONSTITUTION,DEFINITION_OF_DONE,CURRENT_TRUTH,RECEIPTS,FAILURES,DECISIONS,NEXT_GATE,RESEARCH_LEDGER,HANDOFF_NOW}.md` + `scripts/agent_os/*.sh` + `CODEX.md` + updated `CLAUDE.md`/`AGENTS.md` first-read pointers. Imported kit in `docs/agent_os/imported/`.
- **Receipt:** `bash scripts/agent_os/preflight.sh` output committed under `docs/agent_os/` (see preflight log) — repo/branch/lock-halt/engine-status/suite captured.
- **Skeptic verdict:** pending integrator pass; see HANDOFF_NOW.
- **Limitation:** docs route to existing factory ledgers; they do not re-prove past receipts.

---

## Imported prior receipts (from `logs/factory/*`, FOREMAN_STATE 2026-06-15/16) — RE-VERIFY before relying

These were reported proven-live by prior foreman sessions. They are imported for continuity, NOT
re-proven this session. Treat as "claimed live; re-check with a failable test before building on top."

- **Calendar API arm (Gate D, partial):** real `GoogleCalendar.CreateEvent` executed + read-back by ID
  + `DeleteEvent` (3 `[Anticipy test]` artifacts created and cleaned). Read-back is the proof, not the
  write response.
- **Reminder voice/text (Gate G, partial, supervised):** one time-due reminder delivered to Omar's
  phone — Twilio SID, status=delivered, exactly one (no flood).
- **Cardinal-sin floor (Gate C safety):** `safety_mega_eval` CORPUS 157, **BREACHES 0**, run through the
  real `/owner/ingest` split path with `execute_actions=True`. Wired into `scripts/run_suite.sh`.
- **Core messy-day slice (Gate C):** run-on vent+tasks paragraph through `/api/owner/ingest` → real tasks
  caught (incl. implied third-party), silent on the vent, money blocked. Suite green 89–90/90.
- **Onboarding scan (Gate F, partial):** `/onboard/scan_api` discovered Google Calendar connection;
  `onboard_discover` glassbox event emitted only on a real non-empty scan.
- **Premium shell (UX):** `factory/bin/check_premium_copy.py` 0 leaks; standing suite gate.
- **Browser money backstop:** `test_purchase_guard.py` — 27 money controls blocked, 24 cart/nav allowed.
- **Browser round-trip (Gate E, partial):** web task → texted ask → YES → visible browser → result text
  (commit `b82e660`).
