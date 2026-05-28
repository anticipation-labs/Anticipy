# Browser Agent Quality & Reliability — Tactics that Actually Win

**Author note**: This report is grounded in published results, shipped code, and benchmark numbers from late 2025 / early-to-mid 2026. Where I cite a number, the source is in the footnote line. Where I extrapolate (e.g. "expected gain in our setting"), I flag it explicitly with `[est]`.

**Anticipy current state (baseline for this report)**: Browser Use 0.11.13 + Patchright + Cerebras/Groq cascade, single-shot reactive loop, no caching, no verifier, ~3/5 PASS on simple Wiki/DDG/books.toscrape; near-0 on Gmail / Reddit / Calendar / authenticated x.com / authenticated Amazon.

---

## 0. Headline benchmark snapshot (May 2026)

These are the numbers anyone reporting "SOTA" should be measured against:

| Benchmark | SOTA score | System | Date |
|---|---|---|---|
| Online-Mind2Web | **97.0%** (291/298, 2 impossible excluded) | Browser Use Cloud `bu-max` (auto-research loop, agentic judge, Claude Agent SDK harness) | Apr 2026 |
| Online-Mind2Web | **90.53%** | Agent Browser Protocol (ABP) + Opus 4.6 | Mar 2026 |
| Online-Mind2Web | 78.7% (prior leader) | — | early 2026 |
| WebArena | **74.3%** | DeepSeek V3.2 | 2026 |
| WebArena | **71.6%** | OpAgent (Qwen3-VL-32B fine-tuned + Planner/Grounder/Reflector/Summarizer) | Jan 2026 |
| WebVoyager | **98.9%** | Jina (Om Labs) | 2026 |
| WebVoyager | 87% | Kura (planner/executor/critic debate, Claude-class) | 2026 |
| GAIA | **74.6%** | Claude Sonnet 4.5 + HAL scaffolding (scaffolding ≈ +30 absolute pts) | 2026 |
| OSWorld | **79.6%** | Mythos Preview | 2026 |

**One thing to internalize**: modern SOTA on hard browser benchmarks is now in the 90s, not the 60s. The agents that win are *not* doing it with one bigger LLM. They are winning with **deterministic step boundaries (ABP)**, **structured multi-agent cascades (OpAgent, Kura, WebPilot)**, **trajectory memory / workflow induction (AWM, WebCoach)**, and **agentic LLM judges as evaluators in a self-improvement loop (Browser Use)**.

Sources for the table: leaderboard.steel.dev; browser-use.com benchmark post; theredsix/abp-online-mind2web-results; codefuse-ai/OpAgent; Kura YC launch.

---

## C.1 SOTA browser-agent benchmarks — Top 3 winning techniques

### 1. **Agentic LLM-as-Judge (Mind2Web 2 / Browser Use auto-research)**

Benchmarks based on screenshot-string-match are dead. Browser Use's `bu-max` 97% used an **agentic judge built on the Claude Agent SDK** — a multi-step LLM that reads the trajectory + final state and renders a verdict. Mind2Web 2 published this as a methodology: a tree-structured rubric per task with avg 50 / max 603 nodes, hitting **99% human agreement**.

**Why it matters for us**: when we eventually score our own runs, do not rely on `assert "term" in page.text()`. Build a judge LLM with a per-task rubric. This is what unblocks self-improvement loops.

### 2. **Auto-Research / self-improvement harness via Claude Code in a loop**

Browser Use's specific technique: Claude Code given (a) a CLI to their eval platform, (b) a system prompt to run for 20 cycles, (c) parallel runs across a search tree of agent variants. Crucially: **train/validation split** so the loop overfits to train tasks, then candidate variants are validated on unseen tasks. They explicitly emphasize **"big bets over incremental tweaks"** to overcome run-to-run noise.

### 3. **Hierarchical SFT + online RL on a fine-tuned VLM (OpAgent)**

OpAgent's 71.6% WebArena: Qwen3-VL-32B trained in two phases — multi-task SFT on Planning / Acting / Grounding subsets, then online RL in a live web environment with a hybrid reward (WebJudge for outcome + Rule-based Decision Tree for progress). They report a **10.7-point absolute lift** over the same base model without RL.

**For Anticipy**: we're not going to fine-tune. But the architecture (Planner + Grounder + Reflector + Summarizer as four distinct LLM roles) is replicable in pure prompt engineering on Cerebras/Gemini.

---

## C.2 Test-time scaling (Best-of-N, Reflexion, ToT)

### 1. **Best-of-N + LLM verifier — when there's any way to run N trajectories**

`Scaling Test-time Compute for LLM Agents` (arXiv 2506.12928) measured: BoN with N=4 went from **35.3% pass@1 → 60.5% pass@4** on Online-Mind2Web (MolmoWeb). On WebArena-Lite, majority voting from N=1 → N=20 went 38.8% → 43.2% but with **diminishing returns past N=8**.

**Key gotcha for our single-shot use case**: when the user is sitting there waiting, you can't do N=4 in series. But you *can* do **N=2 in parallel** for the first action of any task — which is where most failures actually happen (wrong URL, wrong site).

### 2. **CATTS — Confidence-Aware Test-Time Scaling**

Same paper (arXiv 2602.12276): instead of always doing N=20, sample N=3, measure entropy/margin, only run additional rollouts when entropy > 0.3 ("contentious step"). Reports **47.9% accuracy with 405K tokens vs 920K for uniform majority voting** — same accuracy at 56% the cost.

This is the *practical* version of best-of-N. We can implement this without redesigning the agent loop.

### 3. **Hierarchical Reflexion (NOT single-agent Reflexion)**

The MAR paper (arXiv 2512.20845) found that single-agent Reflexion suffers "degeneration of thought" — the same model that made the mistake reflects and reinforces the same mistake. Multi-Agent Reflexion (different personas + judge synthesizer) gets **+3 pts on HotPotQA, +6.2 on HumanEval pass@1**.

**Implication**: our current disabled `verifier.py` and `reflect` routes were on the right track, but the reflector MUST be on a *different model than the executor*. If executor is Cerebras-hosted, reflector should be Gemini or Claude — otherwise it just rubber-stamps.

### Tree of Thoughts: skip it for browser tasks

ToT works for math/logic. For browser tasks the WebPilot MCTS variant exists but adds 10-50× latency and the wins are mostly absorbed by AWM-style trajectory caching at lower cost. Not worth it for a real-time agent.

---

## C.3 Multi-agent patterns — where they actually pay off

### 1. **Planner / Executor split (Agent-E pattern) — net positive**

Agent-E hit 73.2% on WebVoyager (+20% over text-only, +16% over multi-modal baselines) by splitting **planner (sees only goal + URL history)** from **browser navigation agent (sees DOM)**. Specific technique: planner is "insulated from overwhelming and noisy DOM details" — it deals only in subtasks. The navigator deals only in element interactions.

When this pays off:
- Tasks with >3 sequential steps
- Tasks involving irreversible actions (sending email, posting comment)
- Multi-site research (HN→Wikipedia is exactly this case)

When it costs without paying off:
- Single-step queries ("go to wikipedia and tell me X")
- Already-known URL with single click

### 2. **Planner / Grounder / Reflector / Summarizer (OpAgent pattern)**

OpAgent's four-role split is more granular and produces SOTA WebArena scores. The Reflector specifically analyzes "did the previous action move us toward the goal" and is invoked **between** every step, not just at end. The Grounder is a **separate vision-language model** that takes the planner's instruction ("click the search button") + screenshot and outputs xy coordinates.

**Key insight**: separating Planner (Gemini3-Pro class) from Grounder (Qwen2.5-VL-72B class) lets you spend reasoning tokens on planning without spending them on pixel-coordinate prediction. We can mimic this with: Cerebras for planning, Browser Use's existing index-based DOM extraction as the "grounder" (no vision needed since we have indices).

### 3. **Critic / Debate over each action (Kura)**

Kura's claim of 87% WebVoyager + 31% over Computer Use comes from a **planner/executor/critic debate loop where each agent has different DOM/vision context**. The critic can veto an action before it executes. This is the multi-agent pattern we'd want when we're about to take an irreversible action (send email, post comment, click "buy now").

### When multi-agent hurts (the 17× error trap)

The "Why your multi-agent system is failing" thesis: naive bag-of-agents systems compound errors multiplicatively. **Critical rule**: critics must have **veto authority that triggers retry within the team**, not re-planning from scratch. Otherwise each agent's 90% reliability multiplies down to ~50% across 5 hops.

### Browser Use's own planner mode

Browser Use 0.11.13 ships a planner mode but it's off by default. Turn it on for: tasks with >3 steps, tasks where you've already failed once, irreversible actions. Leave it off for: single-step lookups, known-URL navigations.

---

## C.4 Observation compression / structured DOM

### 1. **Accessibility tree over raw DOM — 80-93% token reduction**

Hard data: full DOM = 8K-40K tokens/step depending on page (YouTube home is ~800K). Accessibility tree = 1.5K-4K tokens/step. **Vercel's agent-browser reports 93% less token usage**, **Stagehand v3 reports 80-90% reduction** by switching from raw DOM to Chrome AxTree.

This is the single biggest cheap win available. Browser Use uses index-based DOM today, which is decent but still bloated on heavy SPAs. Switching to AxTree would dramatically improve our reliability on Gmail, Calendar, and any modern React app.

### 2. **FocusAgent — LLM retriever over AxTree**

arXiv 2510.03204: a small LLM (GPT-4.1-mini) reads the AxTree + task goal and selects only the relevant lines. Reports **51% pruning at 51.5% success vs baseline 53% (essentially zero accuracy loss for half the tokens)**, sometimes 80% pruning. Bonus: it also blocks prompt-injection attacks (banner/popup) because injected content rarely scores as task-relevant.

**This is the second-cheapest reliability win after AxTree.**

### 3. **OmniParser V2 (vision fallback for canvas / iframe / shadow-DOM)**

For pages where AxTree fails (Sheets canvas, Figma, some games), OmniParser V2 takes a screenshot, returns structured GUI elements with semantic descriptions. **0.6-0.8s inference on A100/4090**. Use it as a fallback when AxTree returns <5 interactive elements but the screenshot clearly has a usable interface.

### Set-of-Mark (SoM) annotation

If you go vision-based, SoM (numbered bounding boxes injected by JS over the screenshot) is the proven way to ground "click element #5" instead of letting the model guess xy. Microsoft's `microsoft/SoM` repo is the canonical implementation. Critical for any vision-only fallback path.

### Don't: full HTML, semantic HTML, or markdown

All three were tried in 2024-2025 papers. Either they explode tokens (HTML) or lose interactability metadata (markdown). AxTree won the architectural race.

---

## C.5 Verification — "did the agent actually do it"

### 1. **Assertion over browser state, not LLM claim ("Jest for agents")**

Quote from agent-browser docs: *"A step does not succeed because the model says it did; it succeeds because an assertion over browser state passes."*

Concrete pattern for our hard tasks:
- **Gmail compose**: after `send`, navigate to Sent folder, verify last message subject == drafted subject.
- **Calendar event**: after save, query `/api/calendar/v3/events` (or scrape calendar view) and confirm the event date/title appear.
- **Reddit comment**: after post, verify the comment appears in `/api/comments/{thread_id}` response with our authenticated user as author.
- **Authenticated cart**: after "add to cart", call `/api/cart` (or scrape cart page) and confirm count incremented and item present.

This is the single biggest reliability gain available for our specific failure modes. Browser Use does NOT do this by default — its `done` action just trusts the model. Stagehand has it built into `extract()` with Zod schema validation.

### 2. **Force the agent to QUOTE actual values from the page**

Mind2Web 2's rubric design enforces this: every claimed extraction must cite a source span. The simple version we can implement: after `extract`, call a verification step that asks "show me the raw text on the page where you found '${claimed_value}'" — if the agent can't quote it, mark the task FAIL.

This kills the most common hallucination pattern in our current logs (agent says "I found the answer" without the answer actually being on the page).

### 3. **Required-fields validation via schema (Stagehand `extract` + Zod)**

Stagehand's `extract()` takes a Zod schema and the LLM is *forced* to populate every field; missing fields → null + retry. For our extraction tasks this is a drop-in pattern: define the schema for each task type ("Reddit comments" = list of {author, text, score, timestamp}), force the agent to fill it, fail-loudly on null.

### Hierarchical verification (Agent-E "change observation")

Agent-E's specific trick: after every action, the system returns linguistic feedback like *"a popup has appeared with 3 buttons"* — which forces the agent to acknowledge the state change before next action. Reduces "I clicked the button" hallucinations because the env tells the agent what actually changed.

---

## C.6 Production reliability tactics

### 1. **Provider circuit breakers + ordered fallback (Salesforce Agentforce pattern)**

Concrete spec we can implement in <1 day on top of our existing cascade:
- Track failures per provider in a 60s sliding window.
- If failure rate > 40% within window → **trip breaker, route to fallback for 60s cooldown**.
- After cooldown, send **one probe** request. If it succeeds, restore. If not, extend cooldown to 120s.
- Failure types that count: 429 (rate limit), 5xx, timeouts, **and consecutive same-tool-call no-progress** (loop detection).

We already have something like this in `app/models.py`; the gap is the no-progress loop detection.

### 2. **Action caching / trajectory replay (Stagehand pattern)**

Stagehand caches `(method, normalized URL, DOM hash, project_id)` → resolved selector. On subsequent runs:
1. Hash the page snapshot.
2. If hash + URL match a cache entry, **execute cached selector with no LLM call**.
3. If not, miss → normal LLM path → write new cache entry.

Reports **up to ~80% wall-clock speedup** on repeat workflows. Cache entries are 48h TTL.

For our case: every Anticipy user re-does the same 5-10 tasks (compose to same recipient, check same calendar, search same site). Cache the action sequence per (task_template_hash, site_hostname, user_id) and replay. **This alone probably saves 30%+ of LLM cost and >50% of failures from "the agent re-derived a different (worse) plan this time"**.

### 3. **Idempotency keys for irreversible actions**

The agent retry pattern: `idempotency_key = sha256(workflow_run_id, step_index, action_type, target_url)`. Pass this through to the actual side-effect call (gmail send, comment submit). If the LLM decides to retry the whole sequence, the dedup at the email/comment API prevents double-send.

For browser actions where there's no API (e.g., clicking a button), the equivalent is: **wait for the side effect to be observable before deciding the action failed**. Common bug: agent clicks "Send", gets a 1.5s timeout waiting for confirmation, retries, sends twice. Fix: instead of timeout-then-retry, poll the page state for up to 10s, only retry if no change observed.

### Trajectory caching / Agent Workflow Memory (AWM)

arXiv 2409.07429 reports **+24.6% relative success on Mind2Web, +51.1% on WebArena** by inducing reusable workflows from past trajectories. Specific technique:
- After a successful task, summarize the action sequence as a "workflow" (parameterized).
- On a new task, if it matches an existing workflow signature, prepend that workflow to the LLM context as a hint.
- WebCoach (arXiv 2511.12997) is the 2025 update: same idea, vector-DB indexed, FAISS HNSW-128 retrieval, top-K=5 episodes. Reports **+14 pts on WebVoyager** for Skywork-38B.

### Progressive timeouts

Standard SRE pattern, explicitly cited in browser-use's own docs: start tight (5s), expand on retry (5→10→20s), capped exponential backoff with jitter to avoid thundering herd. Browser Use already does some of this; the gap in our config is per-action-type tuning (a click should retry faster than a navigation).

---

## C.7 Specific projects that have shipped this

### 1. **Browser Use Cloud `bu-max`** — 97% Online-Mind2Web

**What's special**: not the browser layer (still index-based DOM) but the **agent harness rewritten as a coding agent** (Claude Code can write Python parsing inline), the **agentic judge** for eval, and the **auto-research loop** for self-improvement. Open question: how much of `bu-max`'s win is just "Claude Opus 4.6/4.7 at the wheel". My read: ~half of the gain is the harness, half is the model.

### 2. **Stagehand v3 (Browserbase)** — 89-90% common-task reliability

**What's special**: 
- AxTree-based observation (80-90% token reduction)
- Action caching with selector validation against page-hash drift
- Three primitives `act()` / `observe()` / `extract()` that compose better than a single `agent.run()` loop
- Self-healing: cached selector → DOM check → if drift, re-derive via LLM
- Server-side cache shared across users in same project

**Cost gotcha**: 10K extractions/day = $50-200 in LLM fees vs $0 for Playwright. Caching mitigates this but doesn't eliminate.

### 3. **Agent Browser Protocol (ABP)** — 90.53% Online-Mind2Web

**What's special**: not a multi-agent system or a fine-tuned model. It's a **browser layer that freezes JS + virtual time between agent steps**. Every action returns a "settled" state (engine-defined boundary) — agent never races the browser. Built on Chromium input injection, ships event log + before/after screenshots per action. **Works with Claude/Codex/OpenCode out of the box** (model-agnostic).

This is a *substrate* improvement that the multi-agent papers and the SOTA-LLM papers can both ride on top of. It's what makes Opus 4.6 score 90% on a benchmark where the same model with raw Playwright scores 70%.

### 4. **OpAgent (CodeFuse AI)** — 71.6% WebArena

Open source, fine-tuned Qwen3-VL-32B, four-agent architecture (Planner/Grounder/Reflector/Summarizer). Released Jan 2026. Code is on GitHub. **The architecture is the lesson; the fine-tuned weights are nice-to-have.**

### 5. **Anthropic Computer Use / Claude Opus 4.6**

Per Anthropic: 38.1% on OSWorld, 58.1% on WebArena (raw), 87% on WebVoyager. Their reliability tactic is **letting Claude write Python to express orchestration logic** instead of natural-language tool invocations. Quote: *"Loops, conditionals, data transformations, and error handling are all explicit in code rather than implicit in Claude's reasoning."* This is the same insight Browser Use lifted into `bu-max`. Implementation: give the agent a Python sandbox tool, encourage it to write loops in code, not in prose.

### 6. **OpenAI Operator (CUA)**

Vision+RL fine-tuned GPT-class model. Notable for the gap between WebVoyager (87%) and OSWorld (38%) — it's a web agent first, computer agent second. Their published reliability tactic: "instruction hierarchy" (system > developer > user > tool > screenshot), and confirmation prompts on sensitive tasks.

### 7. **Manus**

Sandboxed Firecracker microVM per session via E2B. Planner + multiple executor agents. Real reliability blocker per community reports: **short tasks work, long tasks break**. Same pattern we're seeing.

---

## The "10x reliability" stack — top 5 highest-leverage tactics for Anticipy

Picked for a Python/FastAPI + Browser Use + Cerebras/Groq stack with a real user waiting. Ordered by **expected reliability gain per day of work**.

### #1. End-state assertion verifier per task type — 1-2 days, +25-40 pts on hard tasks `[est]`

Replace `done` action's "trust the LLM" with **per-task-type assertion**:
- Email → check Sent folder for matching subject+recipient.
- Calendar → re-fetch event list, confirm new event present.
- Comment → re-fetch comment list, confirm authored by us.
- Cart → re-fetch cart, confirm item present and count.
- Search → confirm extracted text actually appears in current page DOM.

If assertion fails, **don't return success** — retry up to 2 more times with modified plan ("Sent folder is empty, the email did not actually send, try again").

**Why #1**: This directly attacks our biggest current failure mode (agent says "I sent the email" but didn't). All seven hard tasks listed in the brief have a verifiable end state. None of our current failures would say "I sent the email" if this layer existed.

Cost: 1 day per task type × 6-7 task types ≈ 1-2 weeks total, but the first 3 task types (email, calendar, comment) cover 90% of value and ship in ~1 day each.

### #2. AxTree observation + FocusAgent retriever — 2-3 days, +10-15 pts + 50-70% token reduction `[est]`

Switch Browser Use's DOM extraction to Chrome AxTree (Stagehand path) and add a tiny retriever LLM that pulls the relevant lines for each task. Drops token usage 50-90%, drops cost similarly, and **specifically helps on Gmail, Calendar, x.com — the SPAs where raw DOM is huge and noisy**.

Browser Use 0.11 doesn't expose this directly but you can build it as a wrapper: take the AxTree from CDP, hand it to a small fast LLM with the goal as prompt, return the trimmed tree. ~200 lines of code.

### #3. Trajectory cache + workflow memory (AWM-style, replay-first) — 2-4 days, +10-20 pts on repeat tasks `[est]`

For each (user_id, task_template, hostname) successful task, store the action sequence. On a new task that matches signature:
1. Try the cached sequence first (no LLM call beyond match).
2. After each step, validate selector still resolves (page-hash check).
3. On any mismatch, fall back to LLM agent loop.

Because Anticipy users will repeat similar tasks (email same recipient, check same calendar weekly), this is multiplicatively valuable: **second time = much faster, much more reliable, costs $0 in LLM**.

Implementation reference: Stagehand caching + WebCoach EMS structure. Use Supabase for storage (we already have it).

### #4. Multi-agent split: Planner (cheap fast model) + Executor (Browser Use) + Critic (different model) — 3-4 days, +5-10 pts `[est]`

Three concrete LLM roles:
- **Planner**: Cerebras Qwen — gets goal + URL history only, outputs subtask list. <500 tokens per call.
- **Executor**: existing Browser Use loop on Cerebras/Groq.
- **Critic**: **must be a different model** — Gemini 2.5 Flash is fine. Sees executor's last action + current state, votes "PROCEED" or "RETRY/ABORT". Especially before irreversible actions (send, post, buy).

Avoid the 17× error trap by giving the critic real veto authority and *not* re-planning from scratch on critic-NACK — just retry the current step with the critic's reasoning prepended.

We have most of the routes (`verifier.py`, `proactive` packages) already wired but disabled. Re-enable with this architecture.

### #5. Provider circuit breaker + DOM-drift retry + idempotency keys — 1-2 days, +5-10 pts on flaky-network/flaky-page conditions `[est]`

Three tactical hardening items in one batch:
- Sliding-window failure tracking per provider (we have partial); 40% threshold trips breaker, 60s cooldown, single probe.
- Page-hash drift check before any action: if the page changed since the last screenshot, **re-extract the DOM** before clicking, don't trust the index.
- Idempotency key on every irreversible side effect; deduplicates on retry. For browser-only actions, replace timeout-then-retry with poll-state-then-retry (5-10s observation window).

These are unsexy but each one closes a distinct class of failures we're seeing in `engine_failure_log.md`.

### Why these 5, not the others

- **Best-of-N / CATTS**: Real but expensive (latency + cost) for a real-time UX. Defer until #1-#5 ship.
- **OpAgent-style fine-tuning**: Months of work, requires a training stack we don't have. Not ROI-positive in 2026 for our scale.
- **ABP-style frozen browser substrate**: Worth tracking but Anticipy isn't a browser-substrate company. Adopt it later if Browser Use starts shipping it (or if ABP's protocol becomes standard).
- **Vision/SoM/OmniParser**: Real for canvas-heavy apps, but those are *not* in our top-7 hard tasks. Defer until a user actually needs Sheets/Figma.
- **Agentic judge eval**: Critical for self-improvement loops, but we don't have the eval infrastructure yet to make use of it. Build it after #1 ships (since #1 needs assertion infra anyway).

---

## Cost vs gain summary table (for prioritization)

| # | Tactic | Days | Reliability gain on hard tasks `[est]` | Per-task cost change |
|---|---|---|---|---|
| 1 | End-state assertion per task type | 1-2 days for first 3 types | **+25-40 pts** | +1 LLM call/task, ~5% cost |
| 2 | AxTree + FocusAgent retriever | 2-3 days | +10-15 pts | **-50 to -70% tokens** |
| 3 | Trajectory cache (AWM/Stagehand) | 2-4 days | +10-20 pts on repeat | **-90% on cache hits** |
| 4 | Planner/Executor/Critic split (3 different models) | 3-4 days | +5-10 pts | +30-50% cost (3 calls) |
| 5 | Circuit breaker + DOM-drift + idempotency | 1-2 days | +5-10 pts | flat |
| Σ | All five | ~10-15 dev days | **+55-95 pts compounded `[est]`** | net cost roughly flat (caching offsets multi-agent) |

---

## What I'd ship Monday morning

1. **Day 1**: Write the end-state verifier for Gmail compose + Reddit comment + Calendar event. These are the highest-value tasks where we currently say "success" and didn't actually do it.
2. **Day 2-3**: Wire AxTree extraction + FocusAgent retriever, drop into Browser Use as `dom_extraction_strategy="axtree"`. Re-run the 5-task harness, expect token costs to drop and Gmail/Calendar tasks to become tractable.
3. **Day 4-5**: Trajectory cache schema in Supabase (Anticipy already has it for `engine_tasks`); successful sequences get stored, new tasks check cache first.
4. **Day 6-8**: Re-enable `verifier.py` and `critic` routes with the *different model than executor* rule; gate irreversible actions.
5. **Day 9-10**: Idempotency key infra + DOM-drift check + circuit breaker tightening.
6. **Day 11+**: Eval harness with agentic judge so we can measure ourselves like Browser Use measures themselves.

---

## Key sources

- Browser Use SOTA writeup — https://browser-use.com/posts/online-mind2web-benchmark
- Steel.dev leaderboard — https://leaderboard.steel.dev/
- Agent Browser Protocol — https://github.com/theredsix/agent-browser-protocol
- Stagehand v3 + caching — https://www.browserbase.com/blog/stagehand-v3 / https://www.browserbase.com/blog/stagehand-caching
- OpAgent (WebArena 71.6%) — https://github.com/codefuse-ai/OpAgent / arXiv 2602.13559
- Agent-E (WebVoyager 73.2%, hierarchical, change observation) — arXiv 2407.13032
- Mind2Web 2 + agent-as-judge — arXiv 2506.21506
- Online-Mind2Web ("Illusion of Progress") — OpenReview id=6jZi4HSs6o
- AWM (Agent Workflow Memory) — arXiv 2409.07429
- WebCoach (cross-session memory) — arXiv 2511.12997
- FocusAgent (AxTree retriever) — arXiv 2510.03204
- Test-time scaling for agents — arXiv 2506.12928 / arXiv 2602.12276
- WebPilot (MCTS + hierarchical reflection) — arXiv 2408.15978
- MAR (multi-agent reflexion) — arXiv 2512.20845
- Reflexion original — arXiv 2303.11366
- SeeAct / SeeClick — arXiv 2401.10935 / OSU-NLP-Group
- OmniParser V2 (Microsoft) — github.com/microsoft/OmniParser
- Set-of-Mark — github.com/microsoft/SoM
- Kura YC launch — ycombinator.com/launches/MGd-kura
- Salesforce circuit breaker pattern — salesforce.com/blog/failover-design
- Patchright stealth — grokipedia.com/page/Patchright
