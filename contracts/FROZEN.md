# FROZEN.md — invariants (frozen)

These are the project's load-bearing constraints. Workers and judges must respect all of them. Violations are auto-rejected by the judge.

## Brand

- Typography: **DM Serif Display** (headings, 400), **IBM Plex Sans** (body, 400/500), **IBM Plex Mono** (code, 400). No other fonts.
- Palette: `#0C0C0C` (charcoal), `#F5F0EB` (cream), `#6B635B` (warm gray). No other colors. No `#FFFFFF`, no `#000000`. No purple gradients. No glassmorphism.
- Em-dashes are banned in all user-facing copy, code comments, commits, and prose. Use periods or commas.
- Forbidden tokens in user-facing text: "TODO", "FIXME", "placeholder", "lorem", "coming soon", "powered by AI", "AI-generated", "beta", "early access", "revolutionary", "game-changing", "next-generation".
- Motion: 240ms ease-out for most transitions. No spring physics. No parallax. No bounce.
- No emoji in headings. Emoji in user-typed content only.

## Architecture posture

- **No Apple Developer account ($99 not authorized).** Ad-hoc code signing. Pre-explain the unverified-developer dialog on the download page.
- **No email verification at signup.** Email + password. Random emails accepted. This is intentional — it lets agents and synthetic strangers sign up cleanly.
- **No subscriptions, no paid OpenRouter tiers above standard.** Build cost is on Omar's Codex subscription. Runtime cost is per-task as below.
- **Engine runs locally on the user's Mac.** Cloud (`anticipy.ai`) only serves the website, auth, and the DMG. No cloud LLM calls for engine work.
- **Local Chrome, not cloned profile.** The engine opens a new tab in the user's already-running Chrome for Gmail/Calendar actions. If Chrome is not running, it launches Chrome with `--remote-debugging-port=9222` and prompts the user via the menu bar to attach.

## Runtime model picks (per `docs/COST_BUDGET.md` from prior bootstrap, preserved here)

- Text reasoning: `deepseek/deepseek-chat-v4-flash` via OpenRouter
- Long-context text: `moonshotai/kimi-k2.6-instruct` via OpenRouter
- Vision (last resort): `moonshotai/kimi-k2.6-vision` via OpenRouter
- Cheap classifier: `google/gemini-flash-2.5` via OpenRouter
- Embeddings: `text-embedding-3-small` via OpenRouter
- Local transcription: `parakeet-mlx` on Apple Silicon

**Banned at runtime:** GPT-4o, GPT-5/5.x, Claude Opus (any version), Claude Sonnet (any version), Gemini Pro. Per-task hard ceiling: $0.002 across 100k complex tasks per heavy user per year = $200/user/year.

## Build-time model picks (this build system)

You (the dispatching Codex session) run on Omar's existing Codex subscription. Use whatever model your CLI defaults to. Spawned sub-sessions inherit unless explicitly overridden.

## Frozen paths

Engine code at these paths exists from prior work and may not be edited without writing a verifier first that demonstrates the missing/broken behavior:

- `engine/app/action_engine/`
- `engine/app/proactive_day/`
- `engine/app/anticipy/`

To edit a frozen path: planner writes a task that explicitly includes "create verifier first, then edit frozen path." The judge enforces this — frozen-path diffs without a corresponding verifier addition are auto-rejected.

## External services

- **Vercel** — `anticipy.ai` website. Auto-deploy on push to main.
- **Supabase** — project `handlit`. Auth (email+password no verification), Postgres with RLS. Service role key in `.env.local` and Vercel env. **Must be the same Supabase across both** (a prior failure mode).
- **R2 (Cloudflare)** — bucket `anticipy-downloads`, public URL `https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev`.
- **OpenRouter** — all LLM calls. Key in `.env.local` and Vercel env.
- **Test Gmail** — IMAP credentials in env. Used by regression checks to confirm real drafts land.

## Vercel env vars

The orchestrator verifies on first cycle that Vercel has the same `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENROUTER_API_KEY`, `NEXT_PUBLIC_R2_PUBLIC_URL` as the local `.env.local`. Mismatches are a setup blocker — write to `state/decisions/queue.md` with a default of "pull from .env.local and push to Vercel via `vercel env`."

## What this file is not

Not a comprehensive spec. The product spec is what the planner reads when it explores the codebase. This file is just the load-bearing constraints. If something here conflicts with something the planner finds in the codebase, this file wins.
