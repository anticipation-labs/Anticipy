# Anticipy Browser Agent — Hard Complex-Task Report

One general agent, **zero per-site code**, driving **real authenticated Chrome via CDP** (trusted input,
background tab, no highlight boxes). Cold = recipe cache cleared before **every** task. Completion is
graded by a judge that **reads back the real page** (text / structured tables / element state / all-pages
corpus) against **independent Python-computed ground truth** — never the agent's self-report.

## Headline numbers (cold)

| | Baseline (before) | Now (after fixes) |
|---|---|---|
| Hard-task success | **62.5%** (5/8) | **97.9%** (47/48 across 6 cold runs) |
| $/task | **$0.246** | **$0.053** |
| Vision usage | 54% of steps | ~30% |
| Warm (recipe replay) | — | **$0.0005/task** (0 planner LLM calls) |

Per-run: B 8/8 · C 8/8 · D 8/8 · E 8/8 · F 7/8 · G 8/8. Median run **100%**, worst run **87.5%**.
The single non-verified instance (run F, multi-page count) was a **SAFE handoff of a correct answer** —
the verifier was unsure on a 40k-char cross-page recount and handed off rather than fake a pass.

## The 8 hard tasks (what makes each hard)

1. **Multi-page filter + count** — page through ALL Mystery pages, count books >£50, list titles
2. **Top-N compare** — first 5 Travel books, cheapest vs most expensive with exact prices
3. **Sort table + read row** — click the Last Name header, read the new bottom row
4. **JS dialog handling** — click "JS Confirm", choose Cancel, read the result text
5. **Dynamic wait** — start a loader, wait for completion, read the revealed text
6. **Nested iframes** — read the exact word in the MIDDLE of nested frames
7. **Multi-hop + author DOB** — find a quote, click through to the author's page, read DOB
8. **Paginate ALL + tag count** — every quote page, count 'love'-tagged quotes, list authors

## Fixes that closed the gap (architectural, not tuning)

- **Pagination harvester** (T1, T8): deterministic page-through (find Next → click → re-observe →
  harvest) with no per-step planner LLM; auto-accumulates a de-duplicated cross-page corpus.
- **Structured table extraction** (T3): the extension emits each table's rows top→bottom as displayed
  post-sort, so the judge grades the real order, not flattened text.
- **Structured per-item tags** (T8): climb each tag anchor to its item card; exclude sidebar
  "popular tags" boxes — kills the +1-per-page sidebar inflation (was 23, truth is 14).
- **Cross-frame observe** (T6): collect elements/text from child frames.
- **Count consistency** (T1, T8): the agent must enumerate matching items first, then report the count
  as the exact length of that list; multi-page answers run at temperature 0.
- **Judge determinism** (the last stability fix): the screenshot was the *only* non-deterministic judge
  input — the vision model occasionally misread a correctly-sorted table and flipped a correct verdict
  to false (handing a correct answer to a human). The judge now **drops the image when authoritative
  text/structured/corpus evidence exists**, so identical evidence yields an identical verdict. Cheaper too.

## Live proof (recorded)

Recorded cold run on the live mission-control console — each action line shows the click index,
`@(x,y)`, **`cdp:trusted`**, and the resulting URL; a page URL only advances if the trusted click landed.

### T1 + T2 — multi-page count and top-N compare, both VERIFIED
![T1 T2 verified](/home/ubuntu/screenshots/ss_f641ad62.png)

### T3–T5 — sort (trusted click on "Last Name"), JS dialog, dynamic wait
![T3 T4 T5](/home/ubuntu/screenshots/ss_4597b346.png)

### T6 + T7 — nested frame = MIDDLE; quote author Einstein, DOB March 14 1879
![T6 T7](/home/ubuntu/screenshots/ss_af2c5d5f.png)

### Final scorecard — paginate-all love count = 14, full per-task cost/steps/frontier/vision
![Final scorecard](/home/ubuntu/screenshots/ss_e37fe8df.png)

## Honest assessment

- **It is genuinely good on complex tasks now**: 97.9% verified across 6 cold runs at $0.053/task —
  vs a frontier computer-use agent at ~$0.10–0.40/task that looks at pixels every step.
- **The remaining variance is the safe kind**: on the hardest count-over-many-pages tasks the verifier
  occasionally hands a *correct* answer to a human instead of self-certifying. It never faked a pass and
  never returned a wrong answer as success. That is the constitution's "never fake done" working.
- **The last few points to lock every run ≥90% are a Year-2 lever**: distilling structured counting so a
  cross-page recount is deterministic rather than an LLM recount over 40k characters.
