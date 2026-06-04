# Room 6 — Frontend Wiring (everything works from the download)

## Recipe (from current practice, last-12-mo sources)
- Human-in-the-loop surfaces store pending decisions with status (pending / approved / rejected
  / expired); the app shows what's waiting and lets the human approve or deny with the decision
  logged. One-tap approve/deny routed to the phone is the unattended pattern.
- UX: when asking for approval, "explain the decision like a teammate, not a debug console" —
  don't dump the chain of thought. If the inbox gets noisy, reviewers rubber-stamp or bypass
  (so Room 5's budget matters here too).

## Design
- **Backend API (decisions flow brain → app → back):** `ControlCore.pending_asks()` lists the
  paused detrimental actions (action + human-readable reason + category); `ControlCore.resolve
  (ask_id, approved)` calls the engine's `resolve_ask` — the SAME round-trip the SMS reply uses.
  Exposed over HTTP as `GET /pending` and `POST /resolve` (alongside the existing `GET /glassbox`).
- **SwiftUI surface** (`MainView.swift`, existing dark/SF-Pro/champagne design system):
  - a **"Needs you"** Card polling `/pending` every 2s, each item showing the action + the
    one-line reason (teammate-style) with **Approve** / **Skip** buttons that POST `/resolve` and
    resolve the REAL paused goal;
  - the existing live **glass-box feed** ("what I'm doing / did") polling `/glassbox`.
- **Download/build:** `bash macapp/scripts/build_app.sh` → `macapp/dist/Anticipy.app`. If the
  build breaks, the likely culprit is the duplicate CLT `SwiftBridging` module.modulemap
  (reversible fix: rename it to `.bak`) — checked, currently in place.

## Test
`engine/scripts/test_frontend_api.py` (ControlCore, deterministic): a detrimental event PAUSES
and APPEARS in `pending_asks()`; `resolve(approved=True)` RESUMES the exact paused goal to done
and clears it from the surface; `resolve(approved=False)` drops a goal + writes the decline; the
glass-box carries the full trail (decision / ask_sent / ask_approved / ask_declined / goal_done).
Plus: the SwiftUI app (with the new surface) BUILDS — `Anticipy.app` produced.

## Sources
- StackAI — Human-in-the-Loop approval workflows (pending status): https://www.stackai.com/insights/human-in-the-loop-ai-agents-how-to-design-approval-workflows-for-safe-and-scalable-automation
- Cordum — Human-in-the-Loop AI: 5 production patterns: https://cordum.io/blog/human-in-the-loop-ai-patterns
- Permit.io — HITL for AI agents (best practices): https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo
- Cloudflare Agents — Human-in-the-loop patterns: https://developers.cloudflare.com/agents/guides/human-in-the-loop/
