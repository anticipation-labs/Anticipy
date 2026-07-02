# Plan: best-in-the-world QUALITY *and* cheapest-in-the-world PRICE, simultaneously

Directive (Omar): "We have to win on quality. Better to win on quality than price — but we win on
both: absolute best in the world on quality, simultaneously the absolute cheapest on price."

## 0. The honest crux: are quality and cost actually in tension?

Mostly **no** — and that's the whole reason "both" is possible:

- Most agent cost is **wasted on wrong turns** (a 30-step task that fails at step 8 and flails to 30
  pays for 22 useless steps). **Reliability is a cost lever**: catch the wrong turn at step 8 → fewer
  steps → cheaper *and* higher success. Same intervention, both axes.
- **Structured (DOM) grounding is both cheaper and more accurate** than pixels on any real-DOM page:
  zero vision tokens *and* ground-truth text instead of OCR that misreads. A vision-only frontier
  agent literally cannot be more accurate than reading the actual DOM string.
- **Recipe replay** on repeats is **$0 *and* deterministically correct** (replaying a verified trace).

The tension survives in exactly one place: a **novel, hard, one-shot** task, where exceeding a
frontier model needs test-time compute (best-of-N + verify) and/or the frontier model itself — which
costs. The plan's job is to (a) make that the *only* place we spend, and (b) make even that spend
**decay toward zero over time** via caching + distillation. That is the mechanism for winning both.

## 1. How we EXCEED frontier on quality (not just match it)

Renting a frontier model only gets us *to* the ceiling. To be **best in the world** we must beat a
single frontier pass. Four compounding levers, all of which a single-pass vision agent lacks:

1. **Best-of-N + verifier (test-time compute).** On a hard step/subgoal, sample N diverse candidate
   actions (cheap model), pick via a verifier, execute, **read-back verify the resulting state**, and
   fall through to the next candidate on failure. `pass@k >> pass@1` is the established way to exceed a
   single model's accuracy. We get pass@k *economics* by sampling on the cheap tier and reserving
   frontier for the verifier/tiebreak — quality of an ensemble at near-cheap cost.
2. **Verification-first, never-fake-done (already a strength).** Per-subgoal read-back catches
   compounding error early — the #1 long-horizon failure mode in the literature. Higher success AND
   fewer wasted steps.
3. **Structured DOM grounding + region confirmation.** Lower action-targeting error than pixel-only
   agents on DOM pages; DOM+regions adds pixel confirmation only where the DOM is silent (canvas /
   custom widgets) — so our grounding-error rate can be strictly *below* a vision-only frontier agent.
4. **Frontier-on-hard routing.** The rare genuinely-hard step is handled by the best available model,
   so our ceiling = the field's ceiling, while frontier fires on <~20-30% of steps.

Net quality = frontier ceiling (lever 4) + ensemble lift above it (lever 1) + fewer compounding
failures (lever 2) + lower grounding error (lever 3). That can sit **above** a single frontier agent.

## 2. How we stay cheapest in the world — every time

Stacked, each independent:
- **DOM-first**: most steps $0 vision.
- **Region crops** (built): ~17× fewer pixels than a full frame when pixels are needed.
- **Prompt caching**: ~90% off the static system prompt on every call. (Biggest untapped lever.)
- **DOM-delta + context compaction**: send only changed elements + summarized history → 50-70% token
  cut on long tasks.
- **Recipe replay**: ~$0 and correct on any repeat; parametrized keys (slots for query/user) so far
  more tasks hit the replay path.
- **Distillation (the curve-bender)**: every verified trajectory is private training data. Fine-tune a
  small actor on it → frontier-quality *routine* steps at near-zero marginal cost. Our $/task curve
  bends **down** as we run; the labs' stays flat at frontier vision prices.

The cost of quality (best-of-N + frontier) is bounded to hard steps and **amortized**: each hard step
we pay for produces a verified trace that distillation later makes free. So over time, quality stays
at the ceiling while its price decays toward zero.

## 3. Roadmap — measurable gates, in order (no step "done" without a real number)

- **Phase 0 — Get the real number (no faking).** Stand up WebVoyager (live, easier) → Online-Mind2Web
  (hard) → WebArena (self-hosted, reproducible). Report **success% *and* $/task** together.
  *Gate:* an honest baseline on ≥1 real hard benchmark, repeated ≥3×.
- **Phase 1 — Quality core.** frontier-on-hard routing; best-of-N + verifier on hard steps;
  verification-first per-subgoal; cross-frame / shadow-DOM observe (closes our known T6 gap).
  *Gate:* success% ≥ best published frontier agent on Online-Mind2Web, at ≤ its $/task.
- **Phase 2 — Cost core.** prompt caching; DOM-delta; context compaction; parametrized recipes.
  *Gate:* hold Phase-1 quality at **≥5× lower $/task**.
- **Phase 3 — Distillation flywheel.** harvest verified traces; fine-tune small actor; route routine
  steps to it. *Gate:* small actor matches frontier on routine steps; marginal $/task drops again.
- **Phase 4 — The class they score ~0 on.** authenticated-real-Chrome suite (logged-in personal/SaaS).
  *Gate:* published head-to-head where Operator/Mariner/Browser-Use can't even start.

## 4. The bar for honestly claiming "we won" (both axes)

On **Online-Mind2Web (hard) + WebArena**: success% **≥ the best published frontier agent**, at **≥5×
lower $/task**, **repeated ≥3×** (stability not luck) — *plus* winning the authenticated task class
outright. Until every one of those holds, the honest status is "on track," not "best in the world."

## 5. Honest risks
- Benchmark contamination/gaming (Berkeley RDI) — we measure clean, repeated, and report $/task.
- Frontier API cost + rate limits — bound frontier to hard steps; cache aggressively.
- Best-of-N adds latency — gate it to hard steps only; never on the easy majority.
- Distillation needs trajectory volume — flywheel is Phase 3, not day 1.
- We start at 0 on every hard benchmark — Phase 0 exists precisely to face that number.
