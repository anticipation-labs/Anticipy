# Proactive Engine — build log (branch `proactive/real`)

The third leg: act-first, harm-gated. Built room by room, test-gated, each green room
fast-forwarded into **local** main (no push). Skeleton being made real:
`core/anticipy_engine/core/proactive.py::ProactiveEngine` (wired via `control_core.feed()`).

## Merge / push policy (decided with Omar, 2026-06-04)
- **LOCAL main only — NO push to origin.** Omar wants everything collapsed onto one trunk
  (main), but no outward/Vercel side effects mid-build. He'll push to GitHub on purpose once
  the proactive engine is done and stable.
- One-time cleanup done: fast-forwarded local main from `ad0830f` (Next.js placeholder only)
  through the entire engine stack to `13c133c` (scaffold→core→hands→memory + eval harness).
  Pure ff, no force, no rewrite, no branch deletion, zero logic touched. Suite GREEN 21/21 at
  the new main.
- Per room: ff local main when the room + full suite are green. `proactive/real` is the
  working branch. Any non-clean ff → STOP and show, never force.

## DEFERRED (do NOT start during the 7 rooms — raise when Room 7's log is written)
1. **Harm-line should LEARN from approve/decline over time**, not just read a fixed category
   list. When Omar approves/declines an ask, that should sharpen where the line sits next time
   (e.g. always approves restaurant bookings >$200 → stop asking; always declines a kind of
   email → treat as more detrimental). This is the SAME signal as the Room 5 decline-capture —
   one system, not two. Build rooms 1–7 as specced first; wire the learning loop after Room 7.
2. **Memory's confidence signal is weak** (the 0.30 abstention finding, Memory Fix 2). The
   harm-line leans on it for the gray middle ("is this email binding?"). Where the harm-line
   depends on memory confidence and it's LOW → it MUST fall back to ASK (unsure-means-ask).
   That fallback must be **explicit and logged with a count** (built into Room 2), so we can see
   how often the weak signal forces an ask — that count tells us how badly we need the stronger
   confidence signal next.

---

## Room scorecards
(appended as each room goes green)

### Room 1 — Triage Gate (the bouncer) ✅
- **Built:** `proactive/triage.py::Triage` — deterministic high-recall bouncer. Positive
  signals: action verbs (word-boundary) + commitment/request/imperative/deadline regexes.
  Negative: empty / sub-2-token / pure-filler / bare observations. Cheap-model tiebreak for
  ambiguous events is behind the flag (live-only; fails OPEN; NEVER in CI). Wired as
  `ProactiveEngine._triage` (delegates), so dropped events never reach the gate → zero smart
  calls on the ~99%.
- **Test** (`test_triage.py`): replayed 39-event labeled stream (23 noise / 16 real, incl.
  tricky word-boundary "sending"≠send and intent-only "I should get back to Mom"). Realized:
  **recall on real = 16/16 = 1.000** (hard bar — nothing real dropped), **noise-drop = 23/23
  = 1.000**, **smart-model calls = 0** (cost spine).
- **Suite after:** 22/22 GREEN (21 + triage; `test_proactive` unchanged).
- Commit/main hash: see Commit stack (bottom).
