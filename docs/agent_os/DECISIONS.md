# DECISIONS — product + architecture decisions (with dates)

Append-only. Each: the decision, date, why, and what it forecloses.

## Product (Omar's law)

- **2026-06 — Prepare generously, park safely, ask only at press-go.** If it's not harmful, do the prep
  automatically; never press the irreversible button.
- **2026-06 — Never act on vents/jokes/sarcasm.** Cardinal sin.
- **2026-06 — Money/payment is the only hard stop.** Never auto-spend.
- **2026-06 — The brain is the anti-spam; message caps/throttles are BANNED.**
- **2026-06 — "Done" is lived use by a stranger off a real URL, proven by receipts** — never "tests pass"
  or "machinery exists." Report only live-proven + owner-trusted.

## Repo classification (foreman, 2026-06-16)

- **Autonomous build surface = `~/Anticipy`** (`omize10/Anticipy-executor-working`, `factory/build`):
  full-stack `app/` + `engine/` + `macapp/` + `extension/`. The loop builds here; it is clean and safe
  to commit (when no `factory/.lock`).
- **`~/Developer/Anticipy-DEV-FINAL` (`omize10/Anticipy`, anticipy.ai) is HANDS-OFF.** It has Omar's
  uncommitted work; the download/website path will be wired with Omar, not clobbered autonomously.
  - _Why:_ `THE_MISSION.md` rule 6 + uncommitted owner work on `rebuild/spine-clean`. Resolves the
    kickoff's "find the product repo" by sensible default without risking Omar's active work.

## Build/runtime stack (from the kit; re-verify in RESEARCH_LEDGER before betting on a slug)

- **Foreman/integrator/skeptic:** Claude Code Opus 4.8 (this agent).
- **Worker army:** Codex CLI (`codex exec --json`) for parallel builders/skeptics in worktrees;
  `FACTORY_AGENT=codex` is the factory default. Codex cannot self-grade or redefine done.
- **Runtime router:** OpenRouter with verified base URL + paid-route check; explicit fallbacks. A
  fallback that changes risk level routes to prepare-and-park / needs-human.
- **Browser arm:** the kit recommends **browser-use** (open-source, our OpenRouter model, isolated
  Python 3.11+ service via local bridge) instead of the in-house WebVoyager agent. NOT yet adopted —
  decision pending evaluation (RESEARCH_LEDGER lane 2). Current arm is the in-house one (works for the
  round-trip receipt).
- **API arm:** direct OAuth + Arcade/Composio/MCP-style layer (Arcade already used for onboarding scan).
  Every write requires independent read-back.
- **App shell:** Next.js front (already in `app/`); desktop app exists (`macapp/`, "Anticipy Execute"
  running). Kit suggests Tauri for a new app — do NOT switch stacks without cause; current app runs.
- **Audio/voice:** OpenAI/Deepgram transcription; Twilio voice/SMS. Audio must not block the proactive core.

## Process

- **2026-06 — One honesty instrument:** `safety_mega_eval` is the canonical cardinal-sin/money floor,
  run independently by the foreman (never trusted from an agent).
- **2026-06 — Concurrency:** never commit while `factory/.lock` exists.
- **2026-06-16 — Memory Dock installed** at `docs/agent_os/` as the unifying router over the existing
  factory + autopilot regimes (reconcile, don't delete).
