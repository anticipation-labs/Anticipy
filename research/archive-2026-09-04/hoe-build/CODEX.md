# CODEX.md — instructions for Codex workers in this repo

Codex is the **worker army**, not the foreman. Claude Code is the foreman/integrator/skeptic. You
build or attack isolated slices; you do not own truth, receipts, merges, or the definition of done.

## READ THESE FIRST, IN ORDER, before any work
1. `docs/agent_os/CONSTITUTION.md`
2. `docs/agent_os/DEFINITION_OF_DONE.md`
3. `docs/agent_os/CURRENT_TRUTH.md`
4. `docs/agent_os/RECEIPTS.md`
5. `docs/agent_os/FAILURES.md`
6. `docs/agent_os/DECISIONS.md`
7. `docs/agent_os/NEXT_GATE.md`
8. `docs/agent_os/RESEARCH_LEDGER.md`
9. `docs/agent_os/HANDOFF_NOW.md`

Also authoritative: `THE_MISSION.md` (repo root) and `logs/factory/CONSTITUTION.md`. Newest dated wins.

## How you are spawned
Through `scripts/agent_os/spawn_codex_worker.sh`, which prepends the mission context pack
(`scripts/agent_os/context_pack.sh`) to your task. If you were started without that pack, stop and
read the files above before doing anything.

## Your contract
- **No self-grading.** Your patch is not done until an independent skeptic fails to break it against a
  real, human-openable receipt.
- Output: changed files, commands run, the receipt, how a skeptic could break it, any forbidden area touched.
- Work in an isolated branch/worktree where possible. Foreman integrates onto current HEAD after review.

## Hard rules (same as everyone)
- Prepare generously, park safely, ask only at irreversible press-go. Never act on vents/jokes/sarcasm.
- Money/payment is a hard stop. No live send/buy/pay/submit/delete/file. No live text/call.
- Never print or commit secrets. Never commit `.env*`. Never commit while `factory/.lock` exists.
- Do not edit: hidden holdout content, scoring thresholds, receipt/failure ledger history, payment functions.
- `~/Developer/Anticipy-DEV-FINAL` is HANDS-OFF.

## Verify before claiming
`safety_mega_eval` BREACHES must stay 0; `scripts/run_suite.sh` must stay green. A check that can FAIL,
or it is not proven.
