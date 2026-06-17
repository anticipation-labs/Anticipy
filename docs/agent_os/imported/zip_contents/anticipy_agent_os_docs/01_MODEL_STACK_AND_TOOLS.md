# 01 — Model Stack and Tools

## Final decision

Use a **multi-model, multi-agent stack**. Do not bet the company on one model or one agent. The builder and the skeptic should often be different model families, because same-family self-review produces blind spots.

## Build-time agents

### Primary builder: OpenAI Codex App / Codex CLI with GPT-5.5-class models

Use Codex as the main build swarm because it is designed for parallel coding agents, worktrees, Git workflows, and long-running autonomous tasks.

Settings:

- Routine code patches: `medium` or `high` effort.
- Hard architecture, refactors, safety gates, browser/API integration: `xhigh`.
- Always use isolated worktrees for independent builders.
- Never allow a builder to modify eval answer keys, receipt ledgers, or scoring logic unless the task is explicitly “eval owner” and separately reviewed.

Why: Codex’s current docs describe worktrees, cloud environments, and parallel agents as first-class, and OpenAI’s Codex prompting guide recommends high/xhigh effort for hardest autonomous tasks.

### Primary skeptic / reviewer: Claude Code Opus 4.8, xhigh

Use Claude Code Opus 4.8 as independent skeptic, architecture reviewer, and de-slop critic.

Settings:

- `xhigh` effort for skeptic passes.
- Dynamic workflows for large, multi-agent critique or broad codebase review.
- Force it to find falsification evidence, not summarize.

Why: Claude Opus 4.8 is described by Anthropic as suited for advanced coding and agentic workflows; using it as a different-family skeptic reduces same-model agreement bias.

### Foreman / architect

Use GPT-5.5 Pro or Claude Opus 4.8 depending on environment availability. The foreman is not the main coder. The foreman owns:

- current truth,
- gate selection,
- agent spawning,
- receipt review,
- merge/revert decisions,
- user-visible summaries,
- no-slop enforcement.

The foreman must not blindly trust a builder’s report.

## Runtime model router

Use **OpenRouter** as the runtime router, with explicit fallback chains and live endpoint verification.

Important: the old failure pattern was “provider says OpenRouter but base URL points to Gemini.” Therefore every boot must run a real route check:

```bash
python scripts/verify_model_route.py   --expect-provider openrouter   --expect-base-url https://openrouter.ai/api/v1/chat/completions   --expect-paid-route true   --prompt 'Reply exactly: BRAIN ALIVE'
```

If this fails, do not build. Fix routing first.

### Runtime roles

Use these model tiers, verified at boot against OpenRouter `/models` before use:

```yaml
runtime_models:
  cheap_filter:
    primary: google/gemini-2.5-flash-lite
    purpose: cheap classification, simple extraction, first-pass triage
    guardrail: may never authorize irreversible action
  smart_reasoner:
    primary: openai/gpt-5.5
    fallback_1: anthropic/claude-opus-4.8
    fallback_2: deepseek/deepseek-v4-flash
    purpose: ambiguous intent, planning, browser task decomposition, difficult memory handoff
  high_stakes_judge:
    primary: openai/gpt-5.5-pro if available, otherwise anthropic/claude-opus-4.8
    purpose: safety/reversibility/money/legal/medical judgment, gate reviews
  browser_agent_model:
    primary: openai/gpt-5.5
    fallback_1: anthropic/claude-opus-4.8
    purpose: browser-use/computer-use planning, page understanding, recovery
  voice_transcript:
    batch_mp3: openai transcription API or Deepgram Nova-3
    streaming: Deepgram Flux/Nova-3 or OpenAI realtime speech-to-text
```

### Fallback policy

Use fallbacks for outages, rate limits, and model failures. Do not silently fall back to a lower-capability model for high-risk decisions. If fallback changes risk level, route to “prepare and park” or “needs human.”

## Browser arm

### Decision

Use **browser-use** as the open-source browser agent, driven by our OpenRouter model. Do not continue reinventing a toy browser agent as the primary hand.

Architecture:

- `browser-use` runs in a separate Python 3.11+ service/venv.
- Main engine can remain Python 3.10 if needed.
- Communicate via a local subprocess/HTTP bridge with JSON I/O.
- Use Playwright/CDP/Chrome extension for the user’s real Chrome context.
- Browser arm can prepare reversible state but cannot press irreversible buttons.

### Why separate service

browser-use may require a newer runtime and dependencies. Keeping it separate avoids breaking the main engine environment.

### Browser modes

1. **Read-only scrape mode:** profile building, onboarding, evidence gathering.
2. **Prepare mode:** fill forms, add cart items, prepare return flows, draft content.
3. **Press-go mode:** disabled by default. Only explicit user approval can trigger final submit/send/buy. Money remains hard stop.

## API arm

Use direct APIs/OAuth where possible. Browser is fallback, not default.

Recommended structure:

- Arcade/Composio/MCP-style integration layer for common apps.
- Native direct integrations for mission-critical apps: Google Calendar, Gmail drafts, Outlook, Slack, CRMs, legal/accounting tools.
- Per-user connection map built during onboarding.
- Every write must have independent read-back.

## Desktop app and website

- Web front door: Next.js on Vercel.
- Download page: Vercel-hosted, explicit signed download link.
- Desktop app: Tauri unless current repo is already deeply Electron. Tauri gives a small native app, sidecars, and signing/notarization support.
- Chrome extension: MV3 extension + Native Messaging / local bridge.
- Mac distribution: Developer ID signing + notarization.

## Voice and listening

Do not let voice block the core.

- MP3 upload: batch transcribe.
- Live mic/device: streaming transcribe.
- Phone/text: Twilio or equivalent.
- Voice loop is an arm, not the product. The product is the memory→intent→prep→park→receipt loop.

## Non-negotiable tool checks before work starts

Every session must verify:

1. Current git branch and status.
2. Latest `CURRENT_TRUTH.md` and `RECEIPTS.md`.
3. OpenRouter route with a real paid call.
4. Browser bridge state: extension connected? browser-use service healthy?
5. Test suite baseline.
6. Running processes and ports.
7. Whether laptop is on AC power if long-running loops are expected.
