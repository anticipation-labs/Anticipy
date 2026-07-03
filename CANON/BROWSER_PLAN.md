I have what I need. I've confirmed the codebase already implements most of the dossiers' recommended architecture (DOM-first Set-of-Marks with vision-on-demand, a validator/judge loop, a recipe cache, and a swappable OpenRouter gateway), plus the extension CDP moat and a wired browser-use fallback. Here is the applied plan.

---

# Anticipy "Hands" — Applied Browser-Agent Plan (Head of Engineering)

*Grounding note: this is not greenfield. `engine/anticipy_engine/agent/webvoyager.py` already is the dossiers' recommended architecture — DOM-first Set-of-Marks (screenshot + numbered element list), a judge-in-the-loop validator (`MAX_ANSWER_CHECKS`), Manus-style replanning, anti-loop/churn caps, region-crop vision-on-demand (`_vision_reason`/`_wants_full_shot`/`_region_crop`, `VISION_MODE=off|auto|always`), and a learned-trace cache (`recipes.py`, default ON). The 43%→60% and the 1/15-cost wins are mostly a **routing + tuning + measurement** job on bones we already have, not a rewrite. That is the honest through-line of this whole plan.*

## The architecture we should build (decided)

**Modality — KEEP the DOM-first hybrid Set-of-Marks; do not go DOM-only, do not go screenshot-only.** This exactly matches Omar's "not DOM-only" and the 2026 consensus (dossier 1: text a11y/indexed-DOM as the default lane, vision only on the long tail; dossier 2: DOM/AXTree-first + SoM turns "click where?" into a cheap multiple-choice pick). We already send both views every step and already gate the image behind `_vision_reason`. **The one change:** make `VISION_MODE=auto` the enforced default (screenshot only on `sparse-dom` / `visual-task` / `stuck-recover`, and prefer the region crop over the full frame). Today the per-step full screenshot is the dominant recurring cost; `auto` + region-crop is the single biggest lever and it is already coded — we just have to turn it on and prove it holds.

**Model / voting strategy.** Single cheap strong model per step, **no per-action voting** (dossier 2: voting is ~10x compute and weak on sequential exact-match actions). Omar's "agents vote" belongs where it pays: **selective escalation** — on a destructive/irreversible step (checkout, send, delete) or a low-confidence grounding step, fan out 2–3 candidates or escalate that *single* step to the SMART tier. Concretely, in `core/gateway.py` the per-step `agent` caller is in `SMART_CALLERS` today, so **every act step runs on gpt-4o (SMART) — that is the cost bug.** Fix: introduce an **ACT tier** routed to a cheap VLM, keep SMART as the escalation tier only.

- **ACT tier (95% of steps):** `qwen/qwen3.5-27b` (planner/act, 70.3 ScreenSpot-Pro, $0.30/$2.40) via the existing OpenRouter path — "China for cost," available today with zero new infra.
- **GROUND tier (the ~10–30% of steps that hit `sparse-dom`/`visual-task`):** `qwen/qwen3-vl` (cheap grounder, $0.10/$0.60) fed the region crop.
- **ESCALATE tier:** current SMART (gpt-4o / Claude) on destructive/low-confidence steps only.

**How this reaches ~1/15 (dossier-2 math, 20-step task):** ACT ≈ $0.045 + GROUND ≈ $0.005 + validator/reflect ≈ $0.015 + ~1 escalated step ≈ $0.01–0.03 → **~$0.07–0.10/task vs Claude-in-Chrome's ~$0.50–1.50** — the ~1/15 target. Recipe-cache replay (zero-LLM on repeat sites) pushes recurring per-user cost lower still. Quality recovery to 60%+ comes from the validator + escalation layer already present, not a bigger base model.

## Web-search vs browser (the two-system split) + skill acquisition

**Two subsystems, one orchestrator.** Add a cheap **SEARCH lane** and gate the expensive browser hand behind the dossier-4 trigger: *"is the answer readable on first load, or does it require an action / click-to-expand / login / form submit?"*

- **SEARCH lane (new, cheap):** a `search` worker beside `BrowserHand` (register in `hands/`) that hits a search/scrape API (Firecrawl-style, ~1–2 credits, ≤3.4s) or — better where possible — the site's own JSON/network endpoint (dossier 4's "internal APIs" point; the extension already reads network via CDP). This answers reads/lookups without paying browser cost.
- **BROWSER hand (existing):** reserved for actions and walled/auth'd surfaces — a single **serial** actor (dossier 4: browser is shared-state, do NOT fan out the hand; only fan out cheap search).
- **Orchestration:** the routing decision lives in `core/control_core.py` (already the dispatch point that instantiates `WebVoyagerAgent`). Brain classifies read-vs-act and sets an effort budget by complexity (simple fact → search only; action → browser). This is Anthropic's budgeted-orchestrator pattern.

**Skill acquisition without context rot — upgrade `recipes.py`, don't replace it.** Today it caches a whole-task action trace keyed by `(domain, normalized_task)`. Evolve it toward AWM/Voyager:
1. **Parameterize** (AWM): abstract concrete values → variables ("dry cat food" → `{product}`), so "cancel an Amazon return" generalizes across items instead of one-shot memorizing. `descriptor()`/`match_index()` already replay by element descriptor — extend to variable slots.
2. **Progressive disclosure** (Anthropic Skills): store per-site skills as metadata → body → executable macro; load body only when the domain matches, run the macro without loading it into context. `recipes.py`'s per-key JSON files map cleanly onto this.
3. **ACE-style delta curation + prune cap:** append-and-prune, importance/recency pruning, cap ~7 skills/site (AWM's own sweet spot) so the store never bloats context. This directly attacks "context rot."

## Build vs buy: post-training + hosting

**Honest call: BUY now. Do not post-train, do not self-host a GPU yet.** The dossiers are unanimous where it counts: grounding is nearly solved off-the-shelf (Qwen2.5-VL ≈ 87 ScreenSpot) but *agentic completion* is not — and raw cheap VLMs are unusable as agents zero-shot (Qwen2.5-VL-32B = 3.9% OSWorld). The gain that matters (3.9%→42.5%) is captured **for free** by open post-trained checkpoints; and even those trail frontier Claude by ~30 pts on hard tasks. Our bottleneck is reliability on messy live pages (the extension→cloud plumbing), not the model.

**Recommendation + $:**
- **Phase 0 (now):** ACT on **Qwen3.5-27B via OpenRouter** (our existing gateway/key path), ESCALATE to Claude/GPT. ~**$0.07–0.10/task**, zero infra. Spend engineering on the hand + eval, not models.
- **Phase 1 (when token cost bites):** route grounding to hosted **Qwen3-VL (DeepInfra/Hyperbolic ~$0.20–0.60/M)**; escalate only on hard steps.
- **Phase 2 (only if >~5–10M tok/day sustained AND a real per-site grounding gap):** LoRA-finetune **UI-TARS-1.5-7B** (Apache-2.0; open data free; SFT <$1k) on our own recorded per-user traces, serve on Modal/Baseten H100 (~$1.8–2.9k/mo/GPU). Budget the true cost as **engineering-months for the data + eval harness**, not the GPU bill. At current bursty scale a dedicated GPU sits idle → API is strictly cheaper.
- **Never:** train a GUI VLM from scratch, or expect raw Qwen to drive a browser unassisted.

## Reuse what we have

- **KEEP (do not touch the loop):** `webvoyager.py` observe→decide→act, TaskState/subgoals, validator (`MAX_ANSWER_CHECKS`), replanning, anti-loop/`CHURN_CAP`, `VISION_MODE`/region-crop, `BROWSER_UNLOCKED` semantics. The extension **moat** (`extension/background.js` + `core/browser_link.py`: MV3 + `chrome.debugger` CDP `Page.captureScreenshot`/`Input.dispatchMouse|KeyEvent`/`cdp_click`/`cdp_type`, `chrome.scripting` DOM enumeration, per-session-token WS on the user's real logged-in Chrome). This is the differentiator — every action goes through it (browser-only, per Omar's "forget the API arm").
- **WRAP:** `core/gateway.py` — add the ACT tier + escalation routing (move `agent` out of always-SMART). Add the `search` worker in `hands/`. Extend `recipes.py` to parameterized/progressive-disclosure skills.
- **KEEP AS FALLBACK:** `hands/browser_use_runner.py` + `browser_use_link.py` (browser-use 0.13.1, CDP-attach to same Chrome, nav-wall + SSRF guard). It's our A/B baseline and a second implementation of the hand — valuable for the eval, keep behind `ANTICIPY_BROWSER_HAND_MODE`.
- **DEPRIORITIZE:** `hands/api_hand.py` (the API arm Omar killed).

## The eval (real-world, not just benchmarks) — the browser's `context_eval`

New `engine/scripts/browser_eval.py`, modeled on the existing `_webvoyager_slice.py` (`POST /agent/run` → `/agent/judge`) and `final/tests/context_eval.py`. It reports three numbers per task and in aggregate: **pass/fail, $/task, and steps** (so cost is a first-class scoreboard metric, not an afterthought).

- **Real-world set (Omar's examples), run live in his Chrome via the extension:** (1) Amazon: locate a delivered order and start/cancel a return; (2) Google Sheets: open a named sheet, edit a target cell, verify read-back; (3) Gmail→draft→WhatsApp: read a thread, create a *draft* (ask-first, never auto-send), then paste the summary into WhatsApp Web — this specifically exercises the "believed it typed but didn't" silent-write failure; (4) Form fill: complete a lead form whose backend is a **Web3Forms** capture key, verify the submission landed. Each write step does **read-back-after-write** and **checkpoints between stages** (dossier 4's fix for step-8 death).
- **Benchmark scoreboard:** a WebVoyager subset (reuse the `_webvoyager_slice` tasks + expand to ~20) as the stable regression number. Track our own **cold pass-rate** (baseline 43%) and **$/task** on every change; treat any system's self-judge (e.g. bu-max 97%) as noise.
- **Gate:** "hands are better" = real-world set ≥ target pass at ≤ ~$0.10/task, WebVoyager subset not regressed. This is the un-gameable measurement Omar keeps demanding.

## Ordered build steps + what needs Omar

1. **Build `browser_eval.py`** (real-world set + WebVoyager subset, reports pass/$/steps). *Baseline first — measure the current 43% and current $/task before changing anything.* — **needs Omar: live Chrome with the extension connected; a Web3Forms free access key for the form-fill task.**
2. **Flip `VISION_MODE=auto` as enforced default** + confirm region-crop path fires; re-run eval → expect same pass-rate, lower $/task.
3. **Add the ACT tier in `gateway.py`**, route per-step `agent` to `qwen/qwen3.5-27b`, keep SMART as escalation; add GROUND tier `qwen/qwen3-vl`. Re-run eval. — **needs Omar: confirm/enable the OpenRouter (or DeepInfra) key** — the gateway already reads `ANTICIPY_MODEL_API_KEY`/`OPENROUTER_API_KEY`, so likely just a spend cap, not new plumbing.
4. **Selective escalation** on destructive/low-confidence steps (2–3 candidate fan-out or SMART escalation).
5. **Add the SEARCH lane** worker + read-vs-act router in `control_core.py`. — **needs Omar (optional): a Firecrawl/search API key** (else start with the extension's own network-read path, $0).
6. **Upgrade `recipes.py`** to parameterized macros + progressive disclosure + ACE-delta curation + per-site prune cap.
7. **Iterate to 60%+** on the eval; only then consider Phase-1 hosted grounding.

**Keys Omar must provide:** (a) cheap-VLM host key — OpenRouter (already wired) or DeepInfra, + a spend cap; (b) Web3Forms capture key (free tier) for the form eval; (c) optional Firecrawl key for the search lane; (d) a connected extension/live Chrome for the real-world eval. No model-training key needed (we are buying, not training).

## Coordination with Nick's branch (`nick-sevostiyanov-browser-agent-working`) — complement, don't clobber

Reality check from the fetch: that branch's tip is **"Build real always-on mic capture"** (Jun 15) on a **structurally different tree** (root-level `app/api/**`, root `CLAUDE.md`) — i.e. it diverges from `hoe/build`'s `engine/anticipy_engine/**` layout, and no browser-agent loop rewrite is visible on the tip. So:
- **Own separate surfaces.** Nick's visible work is **capture/mic + backend memory** (`capture/`, `mac_mic.py`, listen endpoints). We own **the hand** (`agent/webvoyager.py`, `hands/`, `gateway.py` routing, `recipes.py`, `browser_eval.py`). Don't both edit the webvoyager loop.
- **Shared contract = the interfaces, not the internals.** Align on two seams both branches already share: the **`BrowserLink` WS protocol** (`observe`/`act`/`navigate`/`read_page`/`browse_task` intents) and the new **`browser_eval.py`** scoreboard. Any hand improvement must move that eval, in his tree or ours.
- **Land additively, behind flags.** Ship ACT-tier routing, SEARCH lane, and parameterized recipes as new modules + env flags (`ANTICIPY_BROWSER_HAND_MODE`, tier vars), so they cherry-pick cleanly onto either tree without a structural merge.
- **Resolve the divergence explicitly:** before deep integration, agree on the canonical tree (`engine/anticipy_engine/**`) and rebase the browser work onto it, so his capture arm and our hand meet on one layout instead of two.

Relevant files: `engine/anticipy_engine/agent/webvoyager.py`, `engine/anticipy_engine/agent/recipes.py`, `engine/anticipy_engine/core/gateway.py`, `engine/anticipy_engine/core/browser_link.py`, `engine/anticipy_engine/core/control_core.py`, `engine/anticipy_engine/hands/{browser_hand.py,browser_use_runner.py,browser_use_link.py}`, `extension/background.js`, `engine/scripts/_webvoyager_slice.py` (→ new `engine/scripts/browser_eval.py`), `final/tests/context_eval.py` (pattern reference).