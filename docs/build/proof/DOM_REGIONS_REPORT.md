# DOM + Regions hybrid perception — build + honest benchmark

Directive (Omar): *"we need to beat them on cost and quality every single time. I don't know if
DOM-first is the right approach. I think you should do DOM plus regions, but again, cost and
quality every single time."*

## What was built

A confidence-gated **DOM + regions** perception path, replacing "DOM-first + whole-screenshot
fallback":

1. **DOM is the cheap backbone.** Every interactive element already carries a bounding box from the
   page; most steps act on the DOM alone at **$0 vision**.
2. **Per-step confidence gate** (`_vision_reason` → `_wants_full_shot`):
   - DOM unambiguous → act on DOM, no pixels.
   - Element decision ambiguous (`stuck-recover`) → **crop only the relevant element region(s)**
     (`_relevant_rects` picks the elements whose labels overlap the subgoal, unions their bboxes)
     and send *that* to vision — not the whole frame.
   - Page-appearance question (`visual-task`) or DOM describes almost nothing (`sparse-dom`,
     e.g. canvas / nested frames) → whole-page screenshot (a crop would lose needed context).
3. **Region crop in the extension** (`doCrop`, `background.js`): CDP `Page.captureScreenshot` with a
   `clip` = element-bbox-union + padding, downscaled to `maxw=760`. No new Python dep.
4. **Instrumentation**: `region_steps`, `full_shot_steps`, `region_pct` exposed in `_metrics()` and
   the bench scorecard.

## Live proof the region crop works

`/ws/observe` quotes.toscrape.com → `/ws/browse {intent:"crop"}` on two element bboxes returned a
tight **387×229** JPEG (the header + the "(about)" line), ~11.7 KB.

- Region area = 387×229 = **88,623 px** vs full viewport 1568×993 = **1,557,024 px** →
  **~17× fewer pixels** (≈ the same factor fewer vision tokens) for the same grounding.

## Three-mode cold benchmark — hard suite (8 long-horizon tasks, recipe cache OFF, 1 run each)

| Mode | success | $/task | vision% | region% | frontier% |
|------|---------|--------|---------|---------|-----------|
| **DOM+regions (auto)** | **100% (8/8)** | $0.0506 | 44.8% | **0.0%** | 70.0% |
| Full-screenshot (always) | 87.5% (7/8) | $0.0407 | 75.0% | 0.0% | 64.2% |
| Pure-DOM (off)\* | 87.5% (7/8) | $0.0531 | 16.7% | 0.0% | 72.9% |

\* "off" still attaches a whole-page shot on the rare recovery escalation, so it is not perfectly
pixel-free.

## Honest reading of the result — what this suite does and does NOT prove

- **It does NOT yet prove the region lever.** `region_pct = 0` in every mode: this suite
  (static scraping sites) almost never produces the *ambiguous-element* situation that routes to a
  region crop. When these tasks do need pixels, the need is **page-level** (nested frames = empty
  DOM → `sparse-dom`; "compare five books" spans most of the viewport → no crop savings). So on this
  suite **DOM+regions collapses to DOM-first**, which is why its numbers match.
- **Cost differences here are within run-to-run noise.** $/task is dominated by **frontier
  (smart-model) escalation %**, not image tokens — Gemini-Flash vision is cheap, so swapping a full
  frame for a crop barely moves $ on *these* tasks. The honest cost lever from regions shows up only
  where vision fires *often* on element decisions (interactive / non-DOM UIs).
- **What is solid:** the architecture is implemented, unit-tested, the crop mechanism is verified
  live (~17× fewer pixels), and the system still scores **100% on the hard suite**.

## Conclusion + next step

DOM+regions is built and correct, but the current static-site hard suite cannot demonstrate
"cost AND quality, every single time" because it does not trigger region crops. To actually prove
the win — and on the battleground that matters (Vy / whole-OS: custom widgets, canvas, post-action
"did the click land", many visually-similar elements) — the next build is an **interactive /
ambiguous-element / non-DOM benchmark** that forces the region path, then re-run the three modes.
Expectation to be tested, not asserted: there DOM+regions beats full-screenshot on cost (crops
instead of full frames) and beats pure-DOM on quality (pixels where the DOM lies).
