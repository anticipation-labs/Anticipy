# Browser Agent — Year 0 Steps 5 & 6 Test Report

**Date:** 2026-06-28
**Branch:** `devin/full-frontend-ui` (commit `60116cd`)
**What:** Instrumentation harness (Step 5) + generic proof on brand-new sites (Step 6).
**Agent:** one general observe→plan→act→verify loop, DOM-first perception, model routing, read-back judge. **Zero site-specific code.**

---

## Step 5 — instrumentation harness (`engine/scripts/browser_bench.py`)

Runs a task set through the live engine + read-back judge and aggregates a scorecard:
`success%`, `human_intervention%`, `avg_cost_usd`, `avg_steps`, `avg_vision_pct` (DOM-first health),
`avg_frontier_pct` (% smart-model calls).

### Cold scorecards (fresh engine restart each pass), 5 tasks across 3 brand-new sites

| Pass | success% | human% | $/task | steps | vision% | frontier% |
|------|----------|--------|--------|-------|---------|-----------|
| A    | **100.0**| 0.0    | $0.0528| 1.8   | 70.0    | 62.0      |
| B    | 80.0     | 20.0   | $0.0292| 2.4   | 4.0     | 39.2      |

- Tasks 1–4 (quotes ×2, books ×2) **PASS every run**. A clean pass = **0% vision, ~$0.02/task** (pure DOM-first).
- Task 5 (hard multi-part Wikipedia fact) passes ~3–4/5; on the off run it **hands off honestly** (judge catches the incomplete answer) — **never fakes done.**

### Robustness fixes surfaced by the harness
- **Cold-start vision inflation:** `_observe_ready` now waits until the DOM reaches the vision threshold (≥`MIN_DOM_ELEMENTS`), not merely ≥1 element.
- **Page-text budget 1800→4000 chars:** content-heavy pages front-load nav/TOC chrome, pushing the answer out of the old window.
- **Multi-part answer completeness:** prompt now requires covering EVERY part; plus a SMART-tier completeness re-ask that fires once when a multi-cue task returns a <160-char answer.
- **Nav-block diagnostics:** the blocked URL is surfaced from the wall into the agent history.

---

## Step 6 — generic proof on brand-new sites (recorded, 3/3 PASS)

Same agent, zero per-site code, driving **real Chrome via CDP** (the "Anticipy (the hands) started debugging this browser" banner is visible throughout).

### Test 1 — read first quote off quotes.toscrape.com (brand-new site)
Answer: *"The world as we have created it… — Albert Einstein"* — judge-verified. **PASS**

![quotes.toscrape](/home/ubuntu/screenshots/ss_ae4e0897.png)

### Test 2 — read title + price off books.toscrape.com (different brand-new site)
Answer: *"A Light in the Attic, £51.77"* — judge-verified. **PASS**

![books.toscrape](/home/ubuntu/screenshots/ss_32900ec0.png)

### Test 3 — multi-step navigation: open Travel category, count books
Agent clicked into `.../category/books/travel_2/`, read "11 results", answered **"11"** in 2 steps — judge-verified. **PASS**

![books.toscrape Travel](/home/ubuntu/screenshots/ss_eb980930.png)

---

## Safety suite — no regression
`agent_proof`, `browser_safety_loop`, `purchase_guard`, `browser_prompt_injection`, `navwall`, `browser_hand` — all green.

## Honest gaps (carried to Year 1)
- Cold-start vision is still run-to-run variable (Pass A avg 70% vs Pass B avg 4%); vision is a *fallback* and even when it fires the answers are correct + judge-verified.
- The hard multi-part Wikipedia task sometimes **detours to Google to "search"** instead of reading the page it's already on, which introduces login-walls/vision. That's a Year-1 robustness behavior (search-detour discipline); today it fails *honestly* (hands off, never fakes done).
