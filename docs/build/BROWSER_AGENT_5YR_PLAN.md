# Anticipy Browser Agent — 5-Year Technical Architecture Plan
### "Better than frontier (OpenAI / Claude / Manus) on the tasks that matter, at ~1/10th the cost"

*Grounded in: Browser-Use (SOTA ~89% WebVoyager), WebVoyager (vision-only ~59%), OpenAI
Operator/CUA, Anthropic Computer-Use, Google Project Mariner + Gemini computer-use API, Manus
(multi-agent planner/executor), Stagehand, and the arXiv survey 2511.19477. Builds on our existing
CDP-via-extension stack (`engine/anticipy_engine/agent/webvoyager.py`, `extension/`,
`core/browser_link.py`).*

---

## The thesis (read this first — it's the whole strategy)

You do **not** beat OpenAI/Claude/Manus by training a bigger model. You beat them on **system
design + data**, on a deliberately narrowed front:

1. **They run a blind, fresh, remote browser.** Operator/Mariner/Browser-Use-cloud spin up a clean
   VM browser with no access to your real logged-in accounts, and they *look at pixels every step*.
   We drive the user's **own authenticated Chrome via CDP** and read the **DOM/accessibility tree
   first**. That's faster, cheaper, and can actually do personal tasks (real Gmail, real bank,
   real Amazon order history) that they structurally cannot.

2. **They pay frontier token prices on every single step.** We call the frontier model *rarely* —
   only for genuine novelty/recovery. Cheap models, deterministic replay of learned recipes, and
   (eventually) our own distilled model handle the other 90% of steps. **Cost per successful task
   is the product of fewer calls × cheaper tokens.**

3. **They don't remember you between runs.** Every Operator session starts from zero. Our agent
   accumulates per-user memory + a self-healing recipe library, so the *second* time it does a task
   it's near-free and near-instant. **The moat is the compounding data, not the model.**

**Honest scope of the claim (so we never lie to ourselves — the cardinal rule):**
- ✅ **True:** we beat them on **cost** (target 10×), on the user's **recurring authenticated
  tasks**, and on **personalization + follow-through**.
- ⚠️ **Not true (and we won't pretend):** a smaller model won't beat a frontier model on a *novel,
  one-shot, arbitrary* task. For those we *call* the frontier model — as a rare component, not the
  default. "Better than frontier" means **better product economics and better real-life task
  completion for our user**, not a bigger brain.

The 10× math: DOM-first perception (~3× cheaper than screenshot-every-step) × model routing
(~3× cheaper by doing routine steps on small models) × recipe-replay/cache (steps that cost $0 on
repeat) × prompt caching (~90% off the static prompt). Stacked, 10× is conservative once recipes hit.

---

## The architecture (the spine that every year builds on)

```
                 ┌─────────────────────────────────────────────────┐
   TASK  ───────▶│  PLANNER (smart model, called rarely)            │
 (from the       │  goal → subgoals → re-plan on failure →          │
  proactive      │  done / blocked / ask-human                      │
  brain)         └───────────────┬─────────────────────────────────┘
                                 │ subgoal + working memory
                                 ▼
   ┌──────────────┐   ┌──────────────────────┐   ┌────────────────────┐
   │ RECIPE CACHE │──▶│  ACTOR (cheap model)  │──▶│  EXECUTOR (CDP)     │
   │ replay known │   │  obs → ONE action     │   │  click/type/nav via │
   │ traces, $0   │◀──│  (DOM-first, vision   │   │  chrome.debugger in  │
   │ LLM on hit   │   │   only when ambiguous)│   │  the user's Chrome   │
   └──────────────┘   └──────────────────────┘   └─────────┬──────────┘
            ▲                                               │ page state
            │ record successful trace              ┌────────▼──────────┐
            └──────────────────────────────────────│  PERCEPTION       │
                                                    │  a11y/DOM tree +  │
   ┌────────────────────┐                           │  set-of-marks shot │
   │ VERIFIER (read-back)│◀──────────────────────────┤  (fallback)       │
   │ goal actually met?  │                           └───────────────────┘
   │ wall → ask human    │
   └─────────┬───────────┘
             │ outcome + trajectory
             ▼
   ┌────────────────────┐
   │ MEMORY (per user)   │  what worked, preferences, recurring tasks → compounds
   └────────────────────┘
```

Action space (small + universal, like Gemini computer-use / CUA): `navigate, click, type, select,
scroll, key, wait, ask_human, done`. No per-site verbs, ever. URL is inferred, never a lookup table.

---

## Year 0 — Foundation & Parity (months 0–6)
**Goal: a clean, honest, general agent that matches frontier on common tasks and already undercuts
them on cost.**

- VM self-test harness: unpacked extension in our Chrome, prove it drives real sites, record it.
- **Rip ALL hardcoding** (Amazon-return recipe, commerce recipe, keyword→site map, owner-TLD
  baking, demo subsystem) and the over-aggressive money/credential *refusals* (behind one
  `ANTICIPY_BROWSER_UNLOCKED` flag; keep only the SSRF/private-IP security guard).
- **Hybrid perception**: build the DOM/accessibility-tree extractor, make it the primary input;
  keep the set-of-marks screenshot as the vision fallback.
- **Planner + Actor split** with a working-memory scratchpad.
- **Model routing**: cheap model per step (`MODEL_CHEAP`), smart model on plan/recover (`MODEL_SMART`).
- **Verifier**: completion = read-back the resulting page, never self-report. Walls → ask human.
- **Proof gate:** a return-style task AND a brand-new site it's never seen, back-to-back, zero
  site-specific code, on video.
- **Metrics from day one:** task success %, steps/task, **$/successful task**, % frontier-model
  steps, human-intervention rate, p50/p95 latency. (We can't beat what we don't measure.)

## Year 1 — Reliability & the Learning Flywheel (months 6–18)
**Goal: beat frontier on cost for real, match on success for the user's recurring tasks, and start
compounding.**

- **Learned-recipe library**: record successful traces keyed by (site, task-type), replay them with
  **zero LLM calls**, self-heal (fall back to live reasoning) when the page diverges.
- **Caching + compaction**: prompt-cache the static system prompt (~90% off hits); compact stale
  observations to keep the context window flat on long tasks.
- **Robustness pass** (where agents actually die): wait-for-stable-DOM, retries/backoff,
  scroll-to-find, iframes, shadow DOM, new tabs, native JS dialogs, captcha/2FA/paywall walls.
- **Trajectory → memory loop**: outcomes feed the per-user memory so asks get fewer over time.
- **Eval harness**: run our own WebVoyager-style benchmark nightly + the user's real recurring
  tasks; track $/task vs. an Operator/Claude baseline so the 10× claim is *measured*, not asserted.

## Year 2 — Personalization Moat & Distillation (months 18–30)
**Goal: collapse cost further with our own small model, and make the agent *yours* in a way the
generalists can't copy.**

- **Distill our own actor**: fine-tune a small open model (Qwen/Llama-class) on our accumulated
  *successful* trajectories. It replaces the cheap-model actor on familiar task shapes → per-step
  cost drops toward zero, latency drops, and we stop renting most of our inference.
- **Vertical skills, fetched autonomously**: the agent pulls a "skill" (legal, finance, Google
  Sheets…) when a task needs it — a retrieval layer over a skills library, invisible to the user.
- **Multi-tab / parallel subgoals** (the Mariner capability) for research/compare tasks.
- **Personalization**: preferences, defaults, people-who-matter, and recurring-task templates make
  *our* completion rate on *your* life exceed any cold generalist.

## Year 3 — Self-Improving Network (months 30–42)
**Goal: the flywheel turns without us pushing it.**

- **Privacy-preserving fleet learning**: successful (sanitized) trajectories across users improve
  the shared planner/actor and the recipe library — a network asset that grows with usage. Held-out
  privacy rules enforced (no raw personal content ever leaves the user's boundary).
- **Proactive ⇄ browser fusion**: the proactive brain hands tasks straight to the agent, the agent
  reports proof back, follow-ups are scheduled (3-days-later durability), all through the gateway.
- **Recipe marketplace (internal)**: the most-used discovered recipes become first-class, audited,
  fast paths — still discovered, never hand-authored per site.

## Year 4 — Near-Zero Marginal Cost & Always-On (months 42–54)
**Goal: routine steps cost essentially nothing; the agent is ambient.**

- **On-device / edge small models** for routine actor steps → near-zero marginal inference cost;
  frontier model reserved for true novelty.
- **Always-on capture** (pendant / OS-level) feeds the proactive brain → the agent acts in the
  background and closes loops before you ask.
- **Reliability SLAs**: success%, intervention rate, and $/task hit product-grade targets with
  monitoring + auto-rollback of bad recipes.

## Year 5 — A Specialized Web-Action Model (months 54–60)
**Goal: own the model layer for our domain.**

- **Anticipy web-action foundation model**: distilled from years of real, verified trajectories —
  **SOTA on the tasks our users actually do**, at a fraction of frontier cost. The moat is the
  data + recipes + memory we accumulated, which a generalist lab can't replicate without our usage.
- Frontier APIs become an optional fallback for the long tail, not the engine.

---

## What makes this *defensible* (why a frontier lab can't just do it)
1. **Real authenticated Chrome** — they're structurally cloud/remote; we're in the user's session.
2. **Compounding private data** — per-user memory + verified trajectories they don't have.
3. **Recipe library + distilled model** — our cost curve bends down over time; theirs is flat at
   frontier token prices.
4. **Proactive integration** — the browser agent is one organ in a body (capture → infer → ask →
   act → prove → remember → follow up), not a standalone tool. The product is the *whole loop*.

## The non-negotiables carried through all 5 years
- No hardcoding, ever (recipes are *discovered*, never hand-authored per site).
- Never fake "done" — completion is read-back; a wall is `needs_human`.
- Measure everything ($/task, success%, %frontier-steps) — the 10× claim must stay *proven*.
- Privacy/security first — SSRF guard stays; no raw personal content leaves the user boundary.
