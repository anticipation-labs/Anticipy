# 08 — Research Protocol

## Why this exists

A recurring failure was researching a little, then assuming. Another failure was doing broad research once and never updating it. This protocol makes research concrete and bounded.

## When research is required

Research before decisions involving:

- current model availability/pricing/routing,
- browser agents,
- app signing/notarization,
- Chrome extension/Native Messaging/CDP,
- OAuth/app verification,
- voice/transcription,
- legal/privacy constraints,
- any tool/library version.

## Research shape

Do not do “100 searches” as theater. Do multi-agent research with lanes.

Example lanes:

1. Model/runtime routing.
2. Browser/computer-use agents.
3. API integration/auth platforms.
4. Desktop packaging/signing.
5. Chrome extension/local bridge.
6. Voice/transcription.
7. Security/prompt injection/privacy.
8. Eval harness/agent reliability.

Each lane gets at least 8–12 searches or official doc reads, unless the answer is found in a primary source earlier.

## Source quality

Use primary sources first:

- official docs,
- official API references,
- official GitHub repos,
- standards/specs,
- vendor release notes.

Use blogs/news only for trend/context, not implementation truth.

## Required output per research agent

```markdown
# Research lane: <topic>

## Decision
Use <tool/model/architecture> because <reason>.

## Evidence
- Source 1: <URL> — what it proves.
- Source 2: <URL> — what it proves.

## Risks
- <risk>

## Build implications
- file(s) affected
- env vars
- tests/gates

## Confidence
High / medium / low, and why.
```

## Anti-taper mechanism

The foreman creates a research checklist with all lanes. A decision cannot be marked researched until every lane is either:

- completed,
- explicitly irrelevant,
- blocked with explanation.

## Research-to-build rule

Research must produce a build decision. If it ends as a giant summary with no decision, it failed.

## Current baseline decisions from research

- Build agents: Codex for parallel code work; Claude Opus-class agents for independent skepticism.
- Runtime routing: OpenRouter with explicit paid-route verification and fallbacks.
- Browser arm: browser-use as primary open-source agent; Playwright/CDP/extension bridge around it.
- App: Vercel + Next.js front door; Tauri desktop app unless repo already dictates Electron.
- Audio: OpenAI/Deepgram for transcription; do not let audio block proactive core.
- API arm: direct OAuth APIs plus Arcade/Composio/MCP-style auth/tool layer.
- Verification: independent read-back and hidden evals.
