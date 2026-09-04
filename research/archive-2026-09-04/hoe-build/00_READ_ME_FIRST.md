# 00 · READ ME FIRST — what this branch is (2026-07-04)

You are looking at branch **`hoe/build`** of Anticipy. This is the **live, current line of work** — it
is well ahead of `main` (which is an older, divergent lineage). Everything recent lives here.

---

## What Anticipy is (one line)
A proactive personal assistant — "Donna from Suits" — that listens to your real day, catches the
tasks you get told/asked to do (and silently ignores vents/sarcasm), and quietly handles them inside
your own real systems (your logged-in Chrome, calendar, email, voice), checking with you like a sharp
human before anything that spends money or can't be undone. Full truth: **`CANON/01_WHAT_ANTICIPY_IS.md`**.

## Where it runs (live right now)
- **Product UI** → Vercel: `https://anticipy-welcome.vercel.app`  (deployed from this working tree)
- **Engine (the brain)** → Railway: `https://engine-production-eb43.up.railway.app`
- The Chrome **extension** (`extension/`) is the "hands" — it acts on the user's real logged-in browser.

## Honest status (no spin — this is mid-rebuild)
- ✅ **The engine/brain is genuinely real** (audited live): it infers tasks, ignores vents, holds
  money server-side, remembers across turns, disambiguates people, and its acting spine fires **real**
  browser actions + real memory writes. Batteries: proactive 7/7, memory/context 11/11.
- 🔧 **The product experience around it is being rebuilt.** A cold walkthrough of the live site today
  still hits real problems (documented — see the plan): the theme reads muddy, onboarding leaks
  internal scaffolding, a dead API-connect page contradicts the browser-only design, and multi-user
  isolation is coded-but-mis-configured on the deploy. These are being fixed now, in order.
- ⏸️ **Paused-but-wired (by design):** voice (Twilio), autonomous nudging — flip on with a token.

## The bar for "done" (never shrinks) — `CANON/04_DEFINITION_OF_DONE.md`
> A **stranger** opens the URL and does the whole thing unassisted — premium site → runs in one step →
> onboarding scrapes + **calls them** to fill gaps → messy day → correct cards (tasks caught, vents
> ignored) → swipe changes real state → a browser errand runs on their real Chrome, **stops at
> money/login**, hands back → never spends without a yes, never acts on a vent, never fakes "done."

**Done = a recorded cold-run of that walkthrough by a fresh account. Not a green test suite.** The
reason every past "done" was wrong: it measured subsystems in isolation, never the cold first-run.

## The plan (from here to genuinely done)
Full plan: **`.claude/plans/cozy-chasing-comet.md`**. Seven phases, each accepted only by a live
cold-run of its walkthrough step:
0. Foundation — retraction-silence floor into the decision pipeline, memory name-parse, deps.
1. Multi-user real — Supabase email on, kill open-mode, session gate, per-user isolation + pairing.
2. Browser-only — delete the deprecated Arcade API-connect arm + the `/connect` page.
3. Onboarding — strip the dev scaffolding + wire the full scrape → call → profile → first-cards loop.
4. Brain you can trust — the correctness fixes above, proven on fresh-engine batteries.
5. Premium skin — one consistent theme; hide the dev/ops controls.
6. The browser errand actually acts — real receipt on the card, stops at money/login.
7. **THE GATE** — recorded cold-run of steps 1–7 on the deployed multi-user app, fresh account.

## Where to look
| Path | What |
|---|---|
| `CANON/` | The product truth, architecture, and the one definition of done. **Start with `CANON/00_START_HERE.md`.** |
| `.claude/plans/cozy-chasing-comet.md` | The active plan (the failure map + the 7 phases + the done gate). |
| `final/` | Deep research + specs: `final/browser/` (browser-agent research + plan), `final/UI_*` (UI specs + live punch-lists), `final/tests/` (proactive + context/memory batteries). |
| `app/` | The Next.js product UI (`app/phase-zero/PhaseZeroApp.js` is the whole app; `app/api/*` proxy to the engine). |
| `engine/anticipy_engine/` | The FastAPI brain: memory, the proactive loop, the hands, the channels. |
| `extension/` | The Chrome "hands" extension. |
| `overnight/` | Milestone proof harnesses (`m1_battery.py`, etc.) + `WAKEUP.md` (living status ledger). |
| `PENDING_FOR_OMAR.md` | Things that physically need the owner (Twilio token, Supabase toggle, safety pass). |

## Run it locally
```bash
# engine (the brain)
engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787
# app (the UI) — from repo root
npm install && npm run dev          # http://localhost:3000
# the test suite (stub-forced, deterministic)
bash scripts/run_suite.sh
```

## Branch note
This branch (`hoe/build`) is the source of truth for current work and is **ahead of / divergent from
`main`**. It is pushed here for visibility; it is **not** merged into `main` — that merge waits until
the cold-run gate (phase 7) passes and it's stable.
