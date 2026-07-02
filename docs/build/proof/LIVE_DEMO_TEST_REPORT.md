# Anticipy Browser Agent — Live Demo Test Report

**Date:** 2026-06-28
**What this proves:** the agent visibly advancing real web pages on screen (not console logs), each
answer judge-verified off the live page, with the cold-vs-warm cost lever shown live.

**Setup:** the agent drives the user's **real Chrome** over CDP. For this recording only, the
agent's working tab was brought to the **foreground** (`ANTICIPY_DEMO_VISIBLE=true`, since reverted)
so the camera can watch the page change. In production the same actions run in a **background tab**
(`active:false`) so the user's focus is never stolen. Recipe cache cleared before recording → all 3
task runs are cold.

---

## Results (4/4 passed)

| # | Task | Cold/Warm | Answer (judge-verified) | smart calls | $/task |
|---|------|-----------|--------------------------|-------------|--------|
| A | Wikipedia: Ada Lovelace birth & death dates | cold | born 10 Dec 1815, died 27 Nov 1852 | 3 | $0.0605 |
| B | Hacker News: title + points of the #1 story | cold | Claude Sonnet 5, 421 points | 2 | $0.0405 |
| C | Hacker News: open top story comments, title + count | cold | Claude Sonnet 5, 215 comments | 4 | $0.081 |
| C2 | Same as C, repeat run (recipe replay) | **warm** | Claude Sonnet 5, 215 comments | **0** | **$0.0005** |

**Warm vs cold on the identical task: $0.081 → $0.0005 = 162× cheaper, 0 planner LLM calls, same verified answer.**

---

## Evidence

### Task A — page navigated to the Wikipedia article and answered off the infobox
The foreground tab switched to the Ada Lovelace article the agent navigated to; the infobox shows
`Born 10 December 1815 … Died 27 November 1852`, which is the answer it returned.

![Task A — Ada Lovelace article](../../../../screenshots/ss_fdec6355.png)

### Task B — the ordinal trap, avoided
The true #1 story by **rank** is "Claude Sonnet 5" at **421 points** — but several stories on the
page have far more points (e.g. "Qwen 3.6 27B" at **1115 points**). A naive read-back answers the
highest-points item; the agent correctly answered the rank-1 item.

![Task B — HN front page, rank-1 vs higher-points trap](../../../../screenshots/ss_b2f9f584.png)

### Task C — multi-hop: real click from the front page into the comments page
The page advanced from `news.ycombinator.com/` to `news.ycombinator.com/item?id=48736605` via a real
CDP click (not a typed URL). The comments page for "Claude Sonnet 5" (215 comments) is shown.

![Task C — clicked through to the comments page](../../../../screenshots/ss_f7692ccf.png)

### Task C2 — warm replay landed on the same page in ~6s at $0.0005
Re-running the same multi-hop task replayed the recorded action-trace (`replayed:true`) with **0**
planner calls — page advanced to the identical comments URL almost immediately.

![Task C2 — recipe replay, same comments page](../../../../screenshots/ss_4a9368af.png)

---

## Honest scope note
These are real public sites (Wikipedia, Hacker News) and the navigation/clicks/verification are
genuine — but they are still short-horizon information tasks. They are **not** a public hard
benchmark (WebArena / Online-Mind2Web / OSWorld), where "best in the world" is actually decided and
where our measured score is still zero. This demo proves the mechanics (real CDP actions, DOM-first
read-back, ordinal discipline, judge verification, and the cold→warm cost collapse) are real, not the
"best in the world" claim.
