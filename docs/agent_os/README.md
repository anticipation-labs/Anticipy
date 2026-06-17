# Anticipy Agent OS — the Memory Dock (read this first)

This folder is the **durable operating system** for everyone (Claude foreman, Claude subagents,
Codex workers, future/compacted you) building Anticipy. Continuity is not model memory — it is
these files on disk + git history. If you remember nothing, read these and you are the last agent
again, with the same mission and the same rules.

## FIRST-READ ORDER (every session, before any work)

1. `CONSTITUTION.md` — the supreme law (mission + hard stops + no-slop).
2. `DEFINITION_OF_DONE.md` — the finish line; never shrink it.
3. `CURRENT_REALITY_CHECK.md` — the exact app/repo/engine/routes Omar tests + mock-vs-live map.
4. `CURRENT_TRUTH.md` — what is proven vs not, right now (mutable, updated every run).
4. `RECEIPTS.md` — append-only ledger of what is actually proven done.
5. `FAILURES.md` — failure modes + tripwires; do not repeat them.
6. `DECISIONS.md` — product/architecture decisions with dates.
7. `NEXT_GATE.md` — the one next gate and its objective receipts.
8. `RESEARCH_LEDGER.md` — research lanes + decisions (not dumps).
9. `HANDOFF_NOW.md` — exact resume state for the next agent.

Then run `bash scripts/agent_os/preflight.sh` and read its output before building.

## Relationship to the existing repo docs (NOT a replacement — a router)

This repo already has deep, hard-won truth. The Memory Dock **routes to and reconciles** it; it does
not delete or override it. On any conflict, the **newest dated** doc wins.

- `THE_MISSION.md` (repo root) — Omar's harsh-toned standing mission + purity rules. Co-authoritative
  with `CONSTITUTION.md` here. Read it.
- `logs/factory/CONSTITUTION.md`, `logs/factory/RECEIPTS.md`, `logs/factory/FAILURES.md`,
  `logs/factory/FOREMAN_STATE.md`, `logs/factory/HANDOFF_2026-06-15.md` — the factory regime's
  detailed ledgers. The Agent-OS files summarize and point to these; the factory ledgers remain the
  deep record.
- `.claude/OWNER_ACTION_ENGINE.md` — Omar's product directive.
- `autopilot/*` — an older build regime (referenced by the legacy `AGENTS.md`). Superseded by the
  factory regime + this Memory Dock where they conflict; kept for history.

## Imported material

`imported/anticipy_agent_os_all_docs.md` and `imported/zip_contents/` — the "Anticipy Autonomous
Build Kit" (dated 2026-06-17) Omar provided. The Agent-OS files here are the working instantiation
of that kit, grounded in this repo's verified reality.

## The one rule that prevents the recurring failure

**No capability counts as done until an independent skeptic fails to break it against a real,
human-openable receipt.** Not "tests pass." Not "the builder says so." Not "it worked in a mock."
Prepare generously, park safely, ask only at the irreversible press-go. Never act on a vent. Money
is the only hard stop.
