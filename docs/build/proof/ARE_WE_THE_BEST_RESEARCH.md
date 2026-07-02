# Are we the best browser agent in the world? — deep research, honest answer

**Short answer: No — not provably, and "100% certainty" does not exist in this field.**
Below is what the public record actually says, why our current proof does not establish #1, and the
concrete, non-magical path to genuinely get there. (I discarded the obviously fabricated "future model"
names some AI-Overview snippets invented — e.g. "Claude Mythos 5", "GPT-5.4 Pro", "WebTactix"; I only kept
numbers traceable to the original benchmark papers/leaderboards.)

---

## 1. The benchmarks that actually decide "best in the world" — and the real numbers

There is no single "browser agent score." Four benchmarks matter, and they disagree on purpose:

| Benchmark | What it tests | Human | Best agents (verifiable) | Why it matters |
|---|---|---|---|---|
| **WebVoyager** (643 tasks, live real sites) | end-to-end web tasks, self/auto-graded | ~89% | hybrid agents (e.g. Browser-Use) ~**89%** | The "easy real" bar. High scores here are *not* impressive. |
| **WebArena** (self-hosted real-style sites) | long, multi-step, functional correctness | ~78% | climbed ~14% (2023) → **~58%** (OpenAI CUA/Operator, Jan 2025) → ~70%+ (best 2025 multi-agent) | The classic "are you actually competent" bar. |
| **Online-Mind2Web** ("An Illusion of Progress?", arXiv 2504.01382) | dynamic, *live*, realistic web | high | easy ~**80%**, medium ~**54%**, **hard ~35%** | Built *because* WebVoyager scores were misleading. Frontier agents **drop drastically** here. This is the honest bar. |
| **OSWorld** (real Ubuntu/Win/macOS desktop) | full computer use, GUI grounding | ~72.4% | original best **12.2%** → frontier ~38% (CUA) → some 2025 systems crossed ~72% | The hardest, broadest. Shows GUI grounding is the wall. |

Two more findings that matter more than any leaderboard row:
- **OSWorld-Human (arXiv 2506.16042):** even when agents *succeed*, they take **1.5×–2.7× more steps than
  humans** — an efficiency gap nobody markets.
- **Berkeley RDI, "How We Broke Top AI Agent Benchmarks":** leaderboard numbers are routinely
  contaminated/gamed. "Every week a new model tops a benchmark" → treat any single number with suspicion.

**Takeaway:** the frontier itself is roughly **35% on hard live web tasks and ~58–74% on WebArena**, not
100%. Anyone claiming a browser agent that "beats everyone with 100% certainty" is either testing on easy
tasks or lying.

---

## 2. Why our current proof does NOT make us #1 (the honest gap)

1. **We measured ourselves on the *easiest possible* tier.** books.toscrape.com, the-internet.herokuapp.com,
   quotes.toscrape.com are static sandboxes literally built to be scraped — that is **WebVoyager-easy or
   below**. Our 97.9% there is real but it is the bar where *Browser-Use already sits at ~89% and nobody is
   impressed*. The benchmarks that separate the field (Online-Mind2Web hard ~35%, OSWorld) we have a
   **measured score of zero** because we have not run them.
2. **No public, reproducible submission.** "Best in the world" is a *public* claim. We have an internal
   scorecard on private tasks. The labs publish on shared benchmarks with held-out grading. Until we post a
   number on WebArena / Online-Mind2Web / OSWorld, the claim is unfalsifiable — which means it doesn't count.
3. **Our wins are economic/deployment, not "smartest brain."** Lowest $/task, real *authenticated* Chrome,
   ~$0 repeat-task replay. That is a genuine, defensible edge — but it is not the same claim as "highest
   success rate on novel hard tasks," and I won't blur the two.

---

## 3. "Everybody has the same tools" — this is the most important sentence, and it favors us

You're right: the base model, CDP, DOM/accessibility tree, set-of-marks screenshots — all commodity.
**That means the model is NOT the moat.** When the brain is a commodity, the winner is decided by the layer
*around* it. So the way to genuinely be #1 is to win the parts trillion-dollar labs structurally *cannot* or
*will not* copy:

- **Authenticated real Chrome.** Operator, Mariner, Browser-Use-cloud run a *fresh remote browser* with no
  access to your real logged-in Gmail/Amazon/bank/SaaS sessions. They literally cannot do a logged-in
  personal task without re-auth. We run in the user's own Chrome. On the tasks real people actually pay for,
  their score is effectively **0% (can't start)** and ours isn't. *This is the single most winnable front.*
- **Compounding private data → distillation.** Every verified trajectory we run is training data for a
  **small distilled action-model**. The labs sell one general model at flat frontier prices; we bend the cost
  curve *down* over time and specialize on the tasks our users repeat. Two years of verified traces on real
  authenticated tasks is a dataset they don't have.
- **Per-user memory + self-healing recipe library.** The second time a task runs it's near-free and more
  reliable. Their agent forgets you between runs by design (privacy/stateless cloud).
- **Verification + "never fake done."** Most leaderboard pain is *confidently wrong* answers. Our judge reads
  the real page and hands off rather than fake — which is exactly what enterprises need and what the
  "reliability gap" literature says is missing.

---

## 4. The concrete path to genuinely become #1 (not impossible — specific)

**Phase A — Stop grading ourselves on toy sites. Get a real number (weeks, not years).**
1. Stand up the **WebArena** self-hosted env and run our agent end-to-end → first honest hard number.
2. Run **Online-Mind2Web** (the live, realistic, anti-gaming benchmark) → this is the one to win publicly;
   it's where everyone else collapses to ~35% on hard.
3. Publish the methodology + cost alongside accuracy. **Nobody else reports $/task next to success%.** That
   combined metric ("success per dollar") is a leaderboard we can *define and win*.

**Phase B — Close the accuracy gap where frontier is weak (the actual research).**
4. **GUI grounding** (the OSWorld wall): better element→coordinate accuracy via the accessibility tree +
   set-of-marks fusion; this is the #1 cause of failures across all four benchmarks.
5. **Long-horizon recovery:** durable subgoal memory, per-subgoal read-back, dead-end detection + replan —
   the 30-step tasks are where everyone dies, including frontier.
6. **Frontier-on-hard routing:** call a true frontier model *only* on the novel/recovery moments; cheap model
   does the rest. Raises the ceiling without raising cost.

**Phase C — The moat that makes the lead permanent (the 1/10 cost + can't-be-copied part).**
7. **Distill** a small actor model on accumulated *verified* trajectories → frontier-quality routine steps at
   near-zero marginal cost. This is the cost curve bending down while theirs stays flat at frontier prices.
8. **Authenticated-task benchmark of our own:** real logged-in personal/SaaS tasks where remote-browser
   competitors score ~0 because they can't even authenticate. Win the front they can't enter.

**Definition of "we're the best" (so it can actually be proven):**
> A public, reproducible number on **Online-Mind2Web (hard) and/or WebArena** that is **at or above the best
> reported frontier agent**, achieved at **≥5–10× lower $/task**, run **repeatedly** (stability, not luck),
> *plus* a class of authenticated real-Chrome tasks competitors structurally cannot perform at all.

We are not there. We have the right architecture and a real cost/deployment edge — but the claim only becomes
true when we post a competitive number on a hard public benchmark. That's the next build, and it's doable.
