# Anticipy Browser Agent — Permanent Research Log

**Path:** `final/browser/RESEARCH.md` · **Status:** canonical reference · **Compiled from** two rounds of deep research (landscape, perception, control, reliability, skills, cost/models, search+testing, extension/CDP) cross-referenced against the live codebase at `/Users/omarebrahim/Anticipy-devin`.

**How to read this.** Sections 1 is the machine-local audit (what to build ON). Sections 2–9 are the external research by topic, each ending in a **Decided position**. Section 10 is the consolidated source index. Confidence is flagged inline as **[HIGH]** (multi-source / primary), **[MED]** (single strong source or protocol-dependent), **[LOW]** (vendor self-report / fast-moving leaderboard).

**The one guardrail that shapes everything:** *guarantee the measurement, not the outcome.* Proxies ("108/0 suite" while the hand couldn't open a tab) fooled this project many times. Every "done" and every skill admission in this document is gated on a **functional read-back of real world state, actively re-verified**, never a model self-claim.

---

## 0. Decided positions (the TL;DR table)

| # | Question | Decided position |
|---|---|---|
| D1 | Which codebase is canonical? | **`~/Anticipy-devin` branch `hoe/build`** — WebVoyager brain + MV3 `chrome.debugger` hand + browser-use read arm. The only stack that drives the user's real Chrome with trusted events, has a real vision-first loop + deterministic guards, and carries a live receipt. |
| D2 | Keep `webvoyager.py` or rewrite on browser-use? | **Keep, but split it.** Neither pure-keep (HoE) nor rewrite (Nick). Refactor the monolith into 5 named roles over an explicit `RunState`; browser-use survives ONLY as the read-only research arm, never the actor. Let the eval scoreboard, not opinion, decide any deeper swap. |
| D3 | Perception modality? | **Hybrid, DOM/AX-first, pixels on demand.** Distilled AX-tree + Set-of-Marks index is the default planning substrate; a specialist grounding VLM on tiled/cropped screenshots is the execution surface. DOM-only and pixel-only are both rejected. |
| D4 | Control topology? | **Hierarchical single-orchestrator, NOT a swarm.** One writer owns the one live tab. Plan-once/re-plan-on-failure → ReAct executor → external verifier → deterministic guards. |
| D5 | Who verifies? | **External + deterministic, environment-grounded. The acting model may NEVER grade itself.** Read-back post-conditions first, VLM validator for canvas, frontier judge only for final answers. |
| D6 | Safety enforcement? | **Deterministic code, not prompting.** Land Nick's `action_guard.py` (money/credential/irreversible/captcha, 15/15, pure-stdlib). LLM plans; it cannot override a code gate. Also the prompt-injection firewall. |
| D7 | Human gate trigger? | **Blast-radius, not confidence.** Irreversible actions (send/pay/print/delete) always pause → text → resume with the *specific artifact* surfaced. A paused task is NOT a completed task. |
| D8 | Model routing? | **Five tiers:** search+Haiku (read) → Qwen3-VL 235B (plan) → UI-TARS-1.5-7B (ground) → Opus 4.8 (escalation, ≤2/task capped) → recipe-replay (~$0). Target ~$0.02–0.03/task cold, ~$0.002–0.008 warm. |
| D9 | Build/buy inference? | **Buy via API < ~30–50M tok/day.** Self-host only the 7B grounder on Modal L40S past that. Never self-host Opus/235B. LoRA only on proven per-surface failure logs. |
| D10 | Transport to Chrome? | **MV3 extension + `chrome.debugger`/CDP on the user's real profile.** Trusted `isTrusted=true` input. NOT remote-debug-port (dead on default profile since Chrome 136), NOT native-messaging cookie access (malware pattern). |
| D11 | Skills? | **Acquire-before-task, never hardcode.** Lift (parameterize+decompose) → admission gate (execute-and-check + held-out) → delta-store → retrieve-before-task with hard rerank → prune/merge. Curation is the whole ballgame (+16.2pp vs −1.3pp for blind self-gen). |
| D12 | Eval? | **`context_eval`: functional postconditions, actively re-probed, two lanes (replay-CI vs live-canary), multi-objective scorecard (success + cost-of-pass + hand-launch-rate + injection-refusal).** |

---

## 1. Codebase landscape & the canonical foundation (machine-local audit)

### 1.1 Ranked inventory of what exists on the machine

**#1 — `~/Anticipy-devin` (branch `hoe/build`, HEAD `ddc7187`) — KEEP (canonical).** The live product arm.
- **Brain:** `engine/anticipy_engine/agent/webvoyager.py` (1,928 lines). Vision-first Set-of-Marks (numbered boxes on a screenshot) + parallel "VISIBLE ELEMENTS" DOM index every step. Full Task-State-Controller: PLAN → per-step STATE injection → code-computed PROGRESS/NO_CHANGE/REGRESSION labels → anti-loop signatures → COMMIT-to-target → re-plan (Manus/Mariner pattern) → judge-in-the-loop answer verification. Deterministic guards: `PURCHASE_GUARD` (money hard-stop), `_CREDENTIAL_FIELD` (never type into pw/OTP/card), `CHECKOUT_URL_RE`, prompt-injection defense (page text = untrusted). Model routing via `ModelGateway` (CHEAP/SMART).
- **Hand:** `extension/background.js` (1,358 lines), MV3, perms `["storage","alarms","scripting","tabs","tabGroups","debugger"]`, `<all_urls>`. Drives Chrome via `chrome.debugger` (CDP) → trusted events: `Input.dispatchMouseEvent`, `Input.insertText`, `Input.dispatchKeyEvent`, `Page.captureScreenshot` (JPEG q55, works on backgrounded tabs), `Storage.clearDataForOrigin` (clean reset), auto-handles `Page.javascriptDialogOpening`. Primitives `doObserve`/`doAct`/`doCrop`. Runs inside an isolated "Anticipy" tab group.
- **Transport:** `core/browser_link.py` — authenticated WebSocket (`/ws/token` → `/ws/extension?token=`), 20s pings + alarm backstop, auto-reconnect, state in `chrome.storage`. Worker `hands/browser_hand.py` refuses success without a screenshot; `prepare_form` never submits.
- **Read arm:** `hands/browser_use_link.py` + `browser_use_runner.py` + `.bu-venv` (**browser-use 0.13.1**). Read-only research via throwaway Chromium (fresh empty profile) or CDP-attach; SSRF loopback guard; money/login hard-stops.
- **Live receipt (real, not proxy):** `docs/guarantee/proof/F_browser.json` — LIVE cart-prep on scrapingcourse.com: navigate→scroll→"Add to cart"→STOP before checkout, 7 steps / 80.8s, 208,867-byte screenshot. Guards proven: 27 money-controls blocked / 24 cart-nav allowed; injection "navigate to evil.com" ignored. Suite: **106 passed / 1 failed** (the 1 fail is a copy test, not browser). Repo's own `CANON/BROWSER_PLAN.md`: WebVoyager benchmark **~43% today, target 60%**, concluding *"webvoyager.py already IS the recommended architecture; the gap is routing/tuning/measurement, not a rewrite."*

**#2 — `~/Developer/Anticipy-DEV-FINAL` — SALVAGE PARTS.** Older but parts-more-advanced transport: engine talks CDP **directly** to a LaunchAgent-managed real-clone Chrome on `localhost:9222` (no MV3), via loopback bridge on `:7777`. Do NOT adopt the transport (MV3 is the better hand). Port these parts into #1:
- `engine/app/action_engine/humanlike.py` (116 lines) — **best anti-bot primitive on the machine:** cubic-Bézier mouse curves + Gaussian inter-event/typing delays, deterministic under seeded RNG. Devin's extension uses instant CDP clicks — this is a drop-in upgrade to `cdpClick`/`cdpType`.
- `engine/app/action_engine/vision_router.py` (196 lines) — **4-tier cost-escalation router** off 4 cheap signals, zero extra LLM calls. Exactly the "add cheap ACT tier + escalation" lever.
- `engine/app/action_engine/vision_image_prep.py` (67) — Gemini tile-cost math + downscale/ROI-crop.
- `engine/app/coldstart/cdp_walker.py` (635) — generic background-tab row scraper (Gmail/Calendar/Drive, no per-site selectors) for cold-start inhale.

**#3–#6 — SCRAP.** `~/Anticipy` (predecessor mirror of devin, 1,035-line background.js — diff/history only; `~/Desktop/Anticipy-executor-working` symlinks here); `~/Desktop/Anticipy-Browser-Hand` == `~/.anticipy/extension/anticipy-v6` (byte-identical 824-line background.js; **synthetic content-script clicks** `.click()`/`dispatchEvent`, **0 `chrome.debugger`** — untrusted events real sites reject, the exact failure CDP replaced); graveyard `extension` (716-line CDP intermediate); v4 skeletons (0 CDP, 0 SoM).

### 1.2 The Nick-vs-HoE conflict (and its resolution)

Two teammates edited the **same** `webvoyager.py` and the **same** extension in divergent directions on non-shared branches, reaching **opposite** verdicts on the same evidence:
- **HoE (`hoe/build:CANON/BROWSER_PLAN.md`, 2026-07-03):** *keep webvoyager; 43→60% is routing/tuning/measurement, not a rewrite; build `browser_eval.py` first.*
- **Nick (`origin/nick-sevostiyanov-demo/site:ai-guidance/REWORK-BROWSER-AGENT.md`, 2026-07-02):** *retire webvoyager, rebuild on browser-use (0.13.x, MIT, 97% Online-Mind2Web on bu-max cloud).* But Nick's REWORK doc honestly admits **they don't yet know WHY** Omar rejected the approach. And what Nick actually coded was a **third** thing (`vision_agent.py` mandatory-vision loop + `action_guard.py`), stranded in a **gitignored `engine-checkout/`**, never landed. Nick's live wins: Reddit Join, YouTube subscribe from a vague description. Canonical still-failing case: Gmail compose end-to-end (fill → SEND).
- **The tie-breaker:** Omar's live verdict 2026-07-02 **rejected the set-of-marks approach** — one day before HoE re-committed to keeping it.

**Resolution (adopted throughout this log):** keep webvoyager as the orchestrator skeleton but **stop treating it as a monolith** — split into 5 owned roles (§4). Make perception hybrid, **not SoM-only** — DOM/AX index is the default but real pixels (`doCrop`/full-shot) are first-class at tier2/tier3 (likely what "SoM is wrong" actually meant). **Land `action_guard.py` now** (approach-agnostic, tested, fills a real hole — hoe/build has no code-level money stop). **Build the eval scoreboard first** and decide keep-vs-replace by numbers, not opinion.

---

## 2. The external landscape (SOTA, systems, benchmarks)

**Health warning:** cross-vendor benchmark numbers are barely comparable. Browserbase measured Gemini 2.5 Computer Use at 79.9% WebVoyager vs Google's reported 88.9%; OSWorld ships raw vs "Verified", single-attempt vs pass@k, 15-step vs 100-step. Treat point scores as ±5–10 pts unless the protocol is pinned.

### 2.1 SOTA verdict (mid-2026)
- **OS/desktop (OSWorld):** Claude leads as a *model* (Sonnet 4.6 ≈72.5% Verified, Sonnet 5 ≈81.2%); scaffolded *systems* (Simular Agent S2 72.6%, H Company Surfer 2 77% pass@10) at the system level. Human baseline 72.36% — frontier models now sit at parity. Anthropic trajectory: <15% (late 2024) → 42.2% (Sonnet 4) → 61.4% (Sonnet 4.5) → ~72.5% (4.6) → 81.2% (Sonnet 5). **[HIGH on ≤4.6; MED on Sonnet 5 = Verified variant]**
- **Web/browser (WebVoyager):** **saturated** — Browser Use 89.1%, Surfer 2 97.1%, "Alumnium" 98.5%. Dead as a differentiator.
- **Browser at low latency/cost:** Google Gemini 2.5 Computer Use (purpose-built, powers Project Mariner).
- **GUI grounding (ScreenSpot-Pro):** frontier VLMs mid-80s (Claude Opus 4.8 ~87.9%, GPT-5.4 ~85.4%, Gemini 3.1 Pro ~84.4%); open leader MAI-UI 32B 67.9%. Rocketed from ~19–31% (early 2025) to mid-80s in 18 months.
- **Open-source native GUI agent:** UI-TARS-2 (ByteDance) — 47.5% OSWorld, 88.2% Online-Mind2Web, 50.6% WindowsAgentArena, 73.3% AndroidWorld.
- **Deep research (GAIA/BrowseComp):** Claude in HAL harness (GAIA 74.6%); BrowseComp led ~0.84–0.87 by frontier Claude/Gemini.

**One-line answer:** a two-horse race — **Anthropic (desktop/OS + reasoning) vs Google (browser + latency)** — with **ByteDance UI-TARS the open-weights frontier**. The honest finding: **the scaffold now moves scores as much as the model** (GAIA ±7 pts from harness alone; top OSWorld *systems* beat the top *model* via retries/validation/pass@k).

### 2.2 Per-system notes (what to steal)
- **UI-TARS-1.5/2:** native end-to-end VLM, **unified cross-platform action space**, System-2 CoT, two-tier memory, RL data flywheel (on-device unobtrusive annotation → SFT accept/override → multi-turn PPO). RL alone added +10.5 OSWorld / +8.7 AndroidWorld. *Steal: unified action space + the flywheel economics.*
- **OpenAI CUA/Operator (Jan 2025):** OSWorld 38.1, WebArena 58.1, WebVoyager 87.0. Category-defining but passed on every axis. Reference baseline.
- **Anthropic Claude computer use + Vercept/Vy acquisition (Feb 25 2026):** Vy was a Mac-native vision-first desktop agent whose differentiator was a **perception + state-awareness/continuity layer** (modeling app structure *over time*, not each screenshot fresh). Founders incl. Ross Girshick (R-CNN). **This acquisition is the strongest signal that the "memory of application state" layer is the current frontier.**
- **Google Gemini 2.5 Computer Use / Mariner:** browser-specialized, explicitly NOT desktop-optimized — the "speed over generality" bet; best accuracy-per-second (~70%+ at ~225s).
- **DOM/hybrid frameworks:** Stagehand (deterministic-first Playwright, LLM only when ambiguous); Skyvern 2.0 (Planner→Actor→Validator, #1 write-heavy on Web-Bench, WebVoyager 85.85%); Agent-E (hierarchical planner + browser-navigator + flexible DOM distillation, WebVoyager 73.2%); Browser Use (WebVoyager 89.1%).
- **Chinese open grounders:** Qwen3-VL-235B (SOTA-class open grounding), AutoGLM (GLM-4.5V), MAI-UI 32B (#1 open ScreenSpot-Pro 67.9), GUI-Owl-7B (54.9 SS-Pro, beats UI-TARS-72B at 1/10 size). **China is winning the open grounding-model race** — these are the cheap perception engines the West's frameworks run on.

### 2.3 Benchmark health map
| Benchmark | Tests | SOTA (2026) | Status |
|---|---|---|---|
| **OSWorld** | Full OS desktop | Claude Sonnet 5 ~81% Verified; systems 77–82%; human 72.36% | **The one that matters for desktop.** Watch raw vs Verified vs pass@k |
| **WebVoyager** | 643 live-web READ | 89–98% | **Saturated / retired as discriminator** |
| **WebArena** | 812 self-hosted long-horizon | ~68.7% base (Claude); ~71–74% scaffolded; IBM CUGA 61.7% | Live. **Discard any ≥90% figure** (a bogus 95.6% surfaced) |
| **Online-Mind2Web** | Realistic live-web, human-verified | Gemini 2.5 CU 69.0% official; UI-TARS-2 88.2% (diff protocol) | **Protocol-fragmented — don't cross-compare vendors** |
| **GAIA** | 450 reasoning+tool | Claude Sonnet 4.5 in HAL 74.6% | **Measures the harness as much as the model** |
| **WebGames** | 50+ trivial-for-humans | GPT-4o 41.2% vs human 95.7% | **Brutal; clearest "agents still can't do basic web" signal** |
| **ScreenSpot-Pro** | High-res pro GUI grounding | frontier mid-80s; open MAI-UI 67.9 | Fastest-moving (19→87 in 18mo) |
| **BrowseComp** | 1,266 hard retrieval | ~0.84–0.87 | **The unsaturated deep-research frontier** |

### 2.4 The 3 architectures worth stealing
1. **Native end-to-end VLM + unified action space + multi-turn RL data flywheel** (UI-TARS-2 / Gemini 2.5 CU) — the frontier for generality/grounding.
2. **Hierarchical Planner → Actor/Grounder → Validator with DOM distillation** (Agent-E / Skyvern 2.0 / OpAgent 71.6% WebArena) — wins **write-heavy/transactional** tasks; reliability + interpretability + cheap grounding.
3. **Thin frontier model + fat orchestration/state-awareness layer** (HAL harness + Vercept's perception-continuity + Browserbase infra) — the scaffold moves scores as much as the model.

**Decided position (landscape):** for a browser-only agent on the user's real Chrome, build **#2 + #3, not a raw pixel end-to-end agent.** Deterministic-first hybrid (DOM when available, vision fallback), Planner/Validator loop with an approval gate before writes, a persistent per-site state/memory layer, first-class wall handling — because Web-Bench proves auth/CAPTCHA/proxy walls, not model IQ, are where real-web agents die. Perception via an open grounding model or Claude computer-use, not a from-scratch VLM.

**Sources:** [UI-TARS-1.5](https://seed.bytedance.com/en/blog/bytedance-seed-agent-model-ui-tars-1-5-open-source-achieving-sota-performance-in-various-benchmarks) · [UI-TARS paper](https://arxiv.org/html/2501.12326v1) · [UI-TARS-2](https://arxiv.org/html/2509.02544v1) · [OpenAI CUA](https://openai.com/index/computer-using-agent/) · [Operator](https://openai.com/index/introducing-operator/) · [Anthropic Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5) · [Coasty OSWorld 2026](https://coasty.ai/blog/osworld-benchmark-results-2026-ai-agents-ranked) · [Vellum Sonnet 5](https://www.vellum.ai/blog/claude-sonnet-5-benchmarks-explained) · [Anthropic acquires Vercept](https://www.anthropic.com/news/acquires-vercept) · [TechCrunch Vercept](https://techcrunch.com/2026/02/25/anthropic-acquires-vercept-ai-startup-agents-computer-use-founders-investors/) · [Gemini Computer Use](https://blog.google/innovation-and-ai/models-and-research/google-deepmind/gemini-computer-use-model/) · [Browserbase harness](https://www.browserbase.com/blog/evaluating-browser-agents) · [Skyvern Web-Bench](https://www.skyvern.com/blog/web-bench-a-new-way-to-compare-ai-browser-agents/) · [Agent-E](https://arxiv.org/html/2407.13032v1) · [ByteTunnels framework comparison](https://bytetunnels.com/posts/browser-agent-frameworks-compared-browser-use-vs-stagehand-vs-skyvern/) · [Qwen3-VL](https://arxiv.org/pdf/2511.21631) · [MAI-UI](https://github.com/Tongyi-MAI/MAI-UI) · [GUI-Owl](https://arxiv.org/html/2508.15144v2) · [Web agent leaderboards](https://awesomeagents.ai/leaderboards/web-agent-benchmarks-leaderboard/) · [WebGames](https://arxiv.org/html/2502.18356v1) · [ScreenSpot-Pro leaderboard](https://gui-agent.github.io/grounding-leaderboard/) · [BrowseComp](https://openai.com/index/browsecomp/)

---

## 3. Perception stack

**The hard requirement:** DOM-only is a dead end (breaks on canvas apps like Sheets/Figma/Canva, non-WCAG sites, cross-origin iframes; is the biggest cost driver — raw DOM trees exceed 1M tokens, ~$40 for one 20-step task on GPT-4.1). But pure-pixel is also wrong (loses stable refs, semantic labels for safety gating, off-screen context). The 2026 answer is a **layered hybrid**.

### 3.1 The four modalities (accuracy AND cost)
| Modality | Accuracy | Cost |
|---|---|---|
| **Raw DOM/HTML** | most info, drowns model, misses visual state | **Worst** (>1M tok, ~$40/task) — unusable without distillation |
| **Accessibility (AX) tree** | compact, semantic, full-page global context in one request, enables **safety gating on labels**; fails on non-WCAG/canvas | **Best text option** — cheap, stable |
| **Raw screenshot** | universal (canvas/PDF/games), true visual state; weak at precise bbox on dense tiny elements | moderate, grows fast with resolution — the **hidden cost sink** |
| **Set-of-Marks** | numbered bboxes → simplified action space; materially lifts multimodal accuracy; clutters on dense pro UIs | screenshot + modest text index |
| **Pixel/coordinate grounding** | **current SOTA execution path** — decouples "what" from "where" | one small-VLM call/action (~7B, self-hostable) |

**Key finding [HIGH]:** raw screenshots to a *generalist* model are terrible at grounding — Qwen2-VL-7B and GPT-4o score **<2%** on ScreenSpot-Pro full-screen. The screenshot only becomes powerful paired with a **grounding-specialized** VLM.

### 3.2 The grounding-model landscape
**Specialist grounders (deploy these):**
- **UI-TARS-1.5-7B** — 61.6% ScreenSpot-Pro, self-hostable, on OpenRouter.
- **Holo1.5 (H Company)** — open 3B/7B/72B; **Holo1.5-7B ≈57.9% SS-Pro vs 29.0% for Qwen2.5-VL-7B** (~2×); does localization + UI-VQA (state reading); built for the Surfer-H policy/localizer/validator split.
- **GTA1 (Salesforce)** — planner/grounder decoupling + test-time scaling; 7B 50.1% SS-Pro, 72B 58.4%, 32B ~63.6%.
- **Jedi / OSWorld-G line** — 4M-example dataset via UI decomposition; multi-scale, compositional generalization.
- **UGround/OS-Atlas** — earlier, cheap, historically important (now surpassed).

**Frontier generalists that now also ground:** Claude Opus 4.8 tops SS-Pro at **0.879** (July 2026); Qwen3-VL-235B leads OSWorld-G at **0.683**; Qwen3.5-122B top open on SS-Pro at **0.704**.

**Takeaway:** you no longer *must* pair a frontier planner with a tiny grounder to get good clicks — but the **specialist-grounder split remains the cost-optimal design** (offload every click to a self-hosted 7B, reserve frontier for reasoning).

### 3.3 Cost engineering (decides economic viability)
- **DOM distillation:** strip presentational classnames/decorative markup → compressed DOM ≈ or cheaper than AX tree. Cap snapshots (~50k chars) + range re-request. **Semantic trimming with a cheap model** (Gemini Flash Lite): keep ALL interactive elements, summarize repetitive lists to ~5 items → **~57% total task cost cut** despite ~34% more tool calls.
- **Screenshot cost = resolution management (the silent killer):** OpenAI 512² tiles ≈170 tok+85 base; Gemini 768² tiles = 258 tok each; **a 4K screenshot ≈16k tokens** (naive patching >50k). Mitigate: downscale to grounder-native res, **crop-then-zoom** on the ROI, thumbnail-plus-tile, visual-token pruning.
- **Caching + history compression (biggest multi-step wins):** prefix caching cut a 100-request workflow **~89%** (74.9% cache hits in a real shopping task); conversation compression keeps last ~40–50 actions verbatim, summarizes older → tokens stabilize **~12.6k instead of growing past 43k after 15 steps**. Reference architecture: a 30-step checkout ran at **$0.145 total (~$0.005/step)**, ~85% success on WebGames (vs ~50% prior; 95.7% human).

### 3.4 Decided position (perception)
Four-layer hybrid:
- **L0 element index (primary planning substrate):** distilled AX tree + compressed DOM, one request, stable versioned refs, cheap-model semantic trimmer. **This is where safety policy is enforced** (block clicks on delete/refund/transfer by label).
- **L1 pixel grounding (primary execution surface):** specialist grounder (**Holo1.5-7B or UI-TARS-1.5-7B**, self-hosted) on a downscaled/cropped tile — mandatory for canvas/PDF/game/non-WCAG.
- **L2 Set-of-Marks as a selective bridge:** when the AX tree enumerates the target, overlay SoM IDs (cheaper/more reliable than free coordinates); fall to raw coords only when enumeration misses; avoid on dense pro UIs.
- **L3 VLM validator:** small VLM reads post-action screenshot to confirm the click landed.
- **Model assignment:** planner = frontier over distilled AX; grounder+validator = self-hosted 7B over tiled screenshots → **~$0.005/step** at SOTA click accuracy.

**Sources:** [ScreenSpot-Pro paper](https://arxiv.org/abs/2504.07981) · [SS-Pro leaderboard](https://llm-stats.com/benchmarks/screenspot-pro) · [grounding leaderboard](https://gui-agent.github.io/grounding-leaderboard/) · [OSWorld-G](https://arxiv.org/abs/2505.13227) · [OSWorld leaderboard (Steel)](https://leaderboard.steel.dev/leaderboards/osworld/) · [Holo1.5](https://www.hcompany.ai/blog/holo-1-5) · [Surfer-H+Holo1](https://arxiv.org/pdf/2506.02865) · [GTA1](https://www.alphaxiv.org/overview/2507.05791v2) · [Building Browser Agents](https://arxiv.org/html/2511.19477v1) · [VisualWebArena](https://arxiv.org/html/2401.13649v2) · [WebVoyager](https://arxiv.org/pdf/2401.13919) · [Image token cost (Roboflow)](https://blog.roboflow.com/image-token-cost-vlm/)

---

## 4. Control architecture — "who drives"

**Bottom line [HIGH]:** a **hierarchical single-orchestrator design, not a swarm.** One persistent planner owns the task and context; a thin ReAct executor acts on the page; a reflector/verifier gates each subtask on **real environment signal**; and **deterministic code, not an LLM, enforces safety and correctness at the execution layer.** Parallel "specialist hands" only for read-only, independent sub-work — never on a single stateful browser session. In one line: **Plan once and re-plan on failure → ReAct to act → verify against the environment (not the model's own opinion) → escalate Retry → Re-plan → Decompose.**

### 4.1 Evidence by question
- **ReAct vs plan-and-execute vs hierarchical:** pure ReAct is adaptive but myopic and expensive; plan-and-execute is cheap but rigid. The winner combines them — plan-and-execute strategically, ReAct tactically, plus a critic/re-plan step ("Reason-Plan-ReAct"). Web-specific: modern frameworks decouple into **Planner / Grounder / Reflector / Summarizer.** [HIGH]
- **Single vs multi-agent:** multi-agent often backfires — UC Berkeley MAST catalogs 14 failure modes (context collapse, hallucination cascades, coordination overhead). A well-tuned single agent with linear context beats a naive swarm. Multi-agent wins only as **orchestrated specialization under load** (clinical study: orchestrated held ~90.6%→65.3% over batch scale while single collapsed 73.1%→16.6%). Keep **one orchestrator owning the context thread**; delegate only independent read-only sub-work. **A live browser session is single-threaded state — never put multiple agents on one tab.** [HIGH arch, MED scaling number]
- **Voting / self-consistency:** near-flat on strong models — **+0.4% HotpotQA, +1.6% MATH-500 across 20 samples** (vs +18 pts on GSM8K in 2022); cost scales ~linearly, sometimes *declines* at high N. Reserve multi-path sampling only for steps that demonstrably exceed single-pass reliability. For web agents, best-of-N helps **only with a verifier**, useful band **~3–16 rollouts**, not unbounded. [HIGH]
- **Reflection:** external/learned feedback works (Reflexion 91% pass@1 HumanEval) but is **bounded by evaluator quality**; **intrinsic self-correction with no external signal frequently degrades performance** (Huang et al. ICLR'24). The verifier must be grounded in the environment or a separate critic — never the same model second-guessing itself. [HIGH]
- **Decomposition + re-planning:** WebDART (Planner/Executor/Reflector) **+9.6 pts on WebChoreArena (31.2 vs 21.6)**; ablation took Shopping **18.8%→26.5% while cutting steps 32.9→18.2** — higher accuracy *and* lower cost, because re-planning discovers shortcuts. Recovery ladder that generalizes: **Retry → Re-plan → Decompose.** [HIGH]
- **Production engineering (WebGames ~85%, 45/53 vs ~50% prior, 95.7% human):** safety/correctness = deterministic code (element-version verification, domain allowlisting, keyword blocking); perception = hybrid AX + selective vision; context compression mandatory (43k→12.6k tokens, ~70% cost cut); batched actions cut tool calls 74% / time 57%. [HIGH]

### 4.2 The Anticipy five-role loop (grounded in the real code)

**Verdict:** one orchestrator drives; **five *roles*, not five agents**; four are deterministic code; only two ever spend an LLM call, only one the frontier model. **THE HARD RULE — single writer:** exactly one ACTOR owns the one live tab-group per task; no other role emits an `act`.

| Role | LLM? | Model | Backing code |
|---|---|---|---|
| **PLANNER** — owns task, subgoals, re-planning (strategic only) | Yes, rare | SMART (frontier) | `webvoyager._plan/_replan` |
| **SKILL-FETCHER** — per-host recipe lookup + match | **No** | — | `recipes.py` |
| **ACTOR** — one subgoal → one page action (tactical only) | Yes | CHEAP → escalate | `webvoyager._act` + `background.js` |
| **VERIFIER/CRITIC** — did the world change? deterministic read-back first | Mostly no | det → CHEAP → SMART tie-break | `_sig`, `proof.py`, port `vision_verifier.py` |
| **GUARD/ESCALATOR** — router + safety firewall + recovery ladder + human gate | **No** | — | port `action_guard.py` + `vision_router.py` |

**Shared state = one orchestrator-owned blackboard (`RunState`).** Generalizes today's scattered `TaskState`+`history`+`committed`+`_trace` locals. Only two fields are ever set from an LLM's mouth (`subgoals`, the ACTOR's chosen `action`); **every control field** (`label`, `sub_stuck`, `no_progress_streak`, `tier`, `budgets`, verdict pass/fail) is computed by code from environment signal. That discipline is what makes the loop cheap *and* reliable.

**The main loop = a fixed 9-phase guarded step** (replacing the implicit `plan→act→act`):
```
(1) OBSERVE   Actor→hand: observe_ready() → OBSERVATION (never act on a not-ready page)
(2) LABEL     Guard(code): diff(last_sig, obs.sig) → PROGRESS/NO_CHANGE/REGRESSION; update counters
(3) WALL CHECK Guard(code): classify_wall(obs.text) → login/captcha/2FA/paywall → HANDOFF
(4) DONE CHECK Guard(code): subgoal postcondition met? → advance / task done
(5) ROUTE     Escalator: tier = vision_router.decide_tier(RunState)  (tier0..3)
(6) PROPOSE   tier0→recipe replay (0 LLM); tier1→ACTOR(CHEAP,text SoM); tier2→ACTOR(CHEAP,+ROI crop); tier3→ACTOR(SMART,full shot) | recovery ladder
(7) PRE-GATE  Guard(code): action_guard.classify(action,obs) BEFORE side-effect → money/cred/irreversible/off-domain → BLOCK|HANDOFF
(8) ACT       Actor→hand: act(action)
(9) VERIFY    Verifier(code): read-back postcondition on real DOM → pass: breadcrumb+advance; fail: RECOVERY LADDER
```
Phases 2,3,4,5,7,9 are **pure code / zero LLM**. Net: roughly **one cheap LLM call/step + a frontier call every several steps.**

**Escalation tiers** (`vision_router.decide_tier`, one tier per firing signal): tier0 replay ($0) → tier1 DOM+SoM text (1 CHEAP call) → tier2 ROI-crop vision (1 CHEAP + `doCrop`) → tier3 frontier+recover (`no_progress_streak≥3`, 1 SMART + full shot).

**Recovery ladder** (cheapest first, on VERIFY-fail): (0) deterministic re-observe+re-act → (1) tactical escalate tier → (2) within-episode REPLAN when `sub_stuck≥2` → (3) DECOMPOSE → (4) HANDOFF/STOP.

**Voting policy — deliberately narrow:** no per-step voting ever; best-of-N (N=3, verifier-selected) only at the **final-answer judge or one high-blast decision**, and only when the first pass is low-confidence. Test-time compute is spent on re-planning and verification, not ensembling clicks.

### 4.3 Anti-patterns explicitly rejected [HIGH]
Swarm on one tab (context collapse/hallucination cascade) · model grades itself · per-step voting/self-consistency · one-shot rigid plan · safety by prompt · "handoff = success" · fixed sleeps (wait on a condition, re-observe before asserting) · browser-use as the actor.

**Sources:** [ReAct/plan-execute/reflection patterns](https://dev.to/gabrielanhaia/react-plan-and-execute-or-reflection-the-three-agent-patterns-every-engineer-needs-in-2026-355p) · [4 single-agent patterns](https://theaiengineer.substack.com/p/the-4-single-agent-patterns) · [reasoner-planner + ReAct](https://arxiv.org/html/2512.03560v1) · [production browser agent](https://arxiv.org/html/2511.19477v1) · [WebDART](https://arxiv.org/html/2510.06587v1) · [single-vs-multi under load](https://www.medrxiv.org/content/10.1101/2025.08.22.25334049.full.pdf) · [MAST: why multi-agent fails](https://galileo.ai/blog/multi-agent-llm-systems-fail) · [self-consistency diminishing returns](https://arxiv.org/abs/2511.00751) · [test-time scaling for web agents](https://arxiv.org/pdf/2602.12276) · [Reflexion](https://arxiv.org/pdf/2303.11366) · [self-reflection can degrade](https://arxiv.org/pdf/2405.06682) · [Huang et al. self-correct](https://arxiv.org/abs/2310.01798) · [WebVoyager](https://arxiv.org/pdf/2401.13919)

---

## 5. Reliability & the "thousand contingencies"

### 5.1 Why the agent dies at step 8 of 12 (compounding-error mechanism)
- **Per-step reliability compounds multiplicatively with no natural recovery loop.** 95%/action → **0.95^10 ≈ 60%** clean completion of a 10-step task. Step 8 is where accumulated probability catches up *and* early drift has silently poisoned the context. [HIGH]
- **Self-conditioning / error cascade:** long-horizon perf is "fundamentally constrained by the self-conditioning effect, whereby errors accumulated from the agent's own past generations progressively degrade future predictions." The **root-cause step** (earliest divergence) matters more than the visible final failure. [HIGH]
- **Execution/grounding is the bottleneck, not planning:** even with **perfect human plans**, web-agent task success is only **36.4%**, low-level completion 38.5%. And [MED, single source]: **34.2%** of actions produce **no DOM change** (silent no-ops), **32%** of `goto` target **hallucinated URLs**, **10.4%** of failures repeat an identical failed action 3+ times, **16.7%** occur **outside the required site**.
- **Infrastructure eats ~40% of failures before reasoning starts** (Web Bench, 5,750 tasks/452 sites): proxy/IP blocking, CAPTCHA, OAuth bot-detection. **WRITE tasks fail dramatically more than READ.** For a personal-assistant that *acts*, you live entirely in the hard 40%/WRITE regime. [MED]

**Reframe:** the failure is not a smarter-model problem — it's the **absence of a per-action verify-and-recover loop.**

### 5.2 The nine contingency subsystems (failure → detection → recovery)
1. **Per-action read-back / post-condition verification (the keystone).** Do NOT use the model to grade itself — ReFlect audited 100 self-reflections: **90 flagged zero errors** ("model wrote 'my reasoning appears correct' regardless"). Replacing self-critique with an **external deterministic harness** added **+13pp avg, +29pp on Claude Sonnet 4.5**. Concrete deterministic post-conditions: after click→assert URL/DOM/title changed; after type→**re-read `.value` == intent**; after submit→assert a success token. HANSEL "breadcrumbs": verifiable snapshots at critical transitions, checked immediately. Validate BEFORE execution too (schema + sanity-bounds + scope). [HIGH]
2. **Stuck/loop detection (deterministic, non-LLM):** action-hash `(tool,args)` dedup; no-change detection (DOM/URL/screenshot diff unchanged k steps); hard max-iteration + token/cycle budget ceilings. ReflexGrad cadence: refine every 3 steps, 5 consecutive low-progress → causal replan [MED thresholds].
3. **Error recovery ladder (cheapest first):** T0 deterministic self-heal (mark failed edge infinite-cost, re-route — 0 LLM) → T1 tactical retry+backoff+jitter → T2 within-episode replan → T3 backtrack/search (VLAA-GUI's Stop/Recover/Search modules; LATS/ToT) → T4 compensating transactions (sagas). Within-episode recovery (ReflexGrad/ReFlect) beats next-trial (Reflexion) for a live assistant. [HIGH]
4. **Environmental interrupts as first-class events (detector + handler + resume):** modals/cookie/paywall (7 canonical types → dismiss → resume; FutureAGI gates ≥75% dismissal, ≥90% within a week); CAPTCHA (detect via console events, wait for solve — Browserbase emits `browserbase-solving-started/finished`; for the user's own accounts, **pause → hand to human**, ToS-safe); login/session expiry (detect re-auth screen; ranked handlers: cookie/profile sync → password-manager autofill → TOTP → email/SMS poll → human handoff); 2FA (auto-TOTP only if you hold the secret, else hand off); rate-limit/Cloudflare (429/JS-challenge → backoff+escalate, **never retry into a ban**).
5. **Dynamic content / wait-synchronization** (the silent killer behind 34.2% no-ops): **never fixed-sleep; wait on a condition** (element present+visible+enabled+stable, or network-idle), re-observe before asserting.
6. **Hallucinated clicks / grounding errors:** constrain the action space + reject non-existent actions at a validation gate; require the target present+visible in a *fresh* observation; multimodal element-attribution check; domain-allowlist for off-site drift.
7. **Silent-write failures ("thought it typed, nothing entered")** — the most dangerous class because **"the most dangerous failures look exactly like success."** Definitive fix = read-back (§1). Circuit breakers on *quality*, not HTTP status (a tool returned 200 but the agent failed 76%). Structured per-span tracing.
8. **Checkpointing between stages:** persist exact state at every boundary (DB-backed, not in-memory). LangGraph checkpointer + `thread_id` cursor. **Idempotency footgun:** on resume, code before the interrupt **re-executes** — every pre-checkpoint side effect must be idempotent or you double-send/charge/print.
9. **Graceful human-handoff (pause → ask → resume):** `interrupt()` suspends+checkpoints, `Command(resume=value)` continues. **Trigger on RISK not confidence** ("90% sure about a read-only query can proceed; 90% sure about deleting prod data must ask"). Handoff must carry full context. **A paused task is NOT a completed task** — "handoff = success" is a lie the metrics tell.

### 5.3 The anti-fragility architecture (mapped to Anticipy's code)
The reliability design extends existing files, not parallel structures: it wraps every action in a **mandatory GUARDED-STEP cell** (`A0 PRE_GATE → A1 WAIT_READY → A2 INTERRUPT_SCAN → A3 ACT → A4 READBACK_VERIFY → A5 COMMIT | RECOVERY LADDER`), extracted into `guarded_step.py` so verify-and-recover is impossible to skip. Three nested FSMs: TASK-RUN → SUBGOAL → GUARDED-STEP cell.

- **A4 read-back = external verification, three-of-a-kind:** (1) state-delta via `_sig` (code); (2) typed-field `.value == intent` (code) — defeats silent-write; (3) validator VLM (Holo1.5-7B) UI-VQA on the post-action screenshot only for canvas/non-WCAG. For irreversible artifacts, `confirm_stable_artifact` (delayed *repeated* read-back). **This is the same seam that gates skill admission (§6).**
- **Risk-tiered human gate (blast-radius):** READ_ONLY/REVERSIBLE/COMPENSATABLE → auto; **MUST_ASK (send/checkout/calendar-create/wire/print)** → pause → text → resume with the *specific* artifact ("okay to send this draft?" with the actual body). FutureAGI scores irreversibility 1.0 only when the confirm surfaces actual line items.
- **Idempotency:** each MUST_ASK action carries an `idem_key` persisted in the breadcrumb; on resume, if it already fired, A3 is a no-op. Breadcrumb schema (HANSEL): `{step, action, descriptor, pre_sig, post_sig, verdict, idem_key, ts}`.
- **Anti-fragility property:** each contingency handled once is logged as a reusable handler/skill → recovers ≥90% next time. Failures make the handler library grow.

**Anticipy's structural advantage:** because the hand runs on the user's **real, already-logged-in Chrome** (browser-only extension, not the Arcade/API arm), walls #5–7 are rare, and the correct default is always pause→text, never evasion. The ~40% infra floor is unbeatable by reasoning — the mitigation is the real profile + human handoff.

**Build-timing caveat (honoring 2026-07-02):** deeper safety-gating is *design-only* for now — do not build new gates into the trunk; the existing `PURCHASE_GUARD` + must-ask on send/checkout are the current floor.

**Sources:** [Where LLM Agents Fail](https://arxiv.org/pdf/2509.25370) · [Why Web Agents Fail (hierarchical planning)](https://arxiv.org/html/2603.14248) · [Long-horizon self-conditioning](https://arxiv.org/html/2605.02572v1) · [MIRAGE-Bench hallucination](https://arxiv.org/pdf/2507.21017) · [AgentRewardBench](https://arxiv.org/pdf/2504.08942) · [ReflexGrad](https://arxiv.org/pdf/2511.14584) · [VLAA-GUI](https://arxiv.org/pdf/2604.21375) · [Self-reflection can hurt](https://arxiv.org/pdf/2405.06682) · [Graph self-healing routing](https://arxiv.org/pdf/2603.01548) · [HANSEL breadcrumbs](https://arxiv.org/pdf/2606.18671) · [ReFlect training-free recovery](https://dev.to/jangwook_kim_e31e7291ad98/reflect-training-free-error-recovery-for-long-horizon-llm-reasoning-dj1) · [Silent-failure patterns (jztan)](https://blog.jztan.com/ai-agent-error-handling-patterns/) · [FutureAGI six failure modes](https://futureagi.com/blog/evaluating-browser-use-agents-2026/) · [Web agent authentication (browser-use)](https://browser-use.com/posts/web-agent-authentication) · [Browserbase identity/CAPTCHA](https://docs.browserbase.com/platform/identity/overview) · [Web Bench (Skyvern)](https://www.skyvern.com/blog/web-bench-a-new-way-to-compare-ai-browser-agents/) · [LangGraph interrupts/checkpointing](https://docs.langchain.com/oss/python/langgraph/interrupts) · [deepchecks silent failures](https://deepchecks.com/ai-agent-failing-hidden-issues/)

---

## 6. Skill acquisition & skill memory

**Core thesis [HIGH]:** the win comes from **curation and verification, not generation.** Indiscriminately admitting self-generated skills **degrades** agents by **−1.3pp** (only 1 of 5 configs improved); **curated** skills raise pass rates **+16.2pp** — "a smaller model with curated skills can outperform a larger model without them." "Acquire before the task, never hardcode" is only safe with a verification gate on every acquisition.

### 6.1 The research lineage
- **DreamCoder** — wake/sleep library learning; hierarchical abstractions where each function calls earlier ones; text-editing 3.7%→79.6% after library learning. *Skills = composable code referencing earlier skills; refactor the library, don't just append.*
- **Voyager** — automatic curriculum + ever-growing **executable-code skill library** (each indexed by an embedding of its description) + self-verification; **only self-verified programs are added back.** 3.3× more items, 15.3× faster milestones, zero-shot to new worlds. *Retrieval = embedding of a description; admission = self-verification; composition = LLM writes new code from retrieved skills.*
- **AWM (Agent Workflow Memory)** — induces reusable workflows offline/online; **abstracts example-specific values into parameterized placeholders** and extracts finer-grained sub-routines (functional overlap driven to **0.08–0.20**). WebArena **35.5% vs 23.5%** (+51.1% rel), 5.9 steps/task vs 46.7; cross-domain +91% rel. *Parameterize and decompose — never store the raw trajectory.*
- **ASI (programmatic skills)** — skills as **executable Python in the action space**; admission verification-gated by execution on three criteria (correctness / usage / validity). WebArena **+23.5% vs vanilla, +11.3% vs AWM**; longer-horizon **+38.9% / +20.7%**. Cross-site reuse but needs a **refine-on-failure** path. *Executable + execution-verified beats text workflows.*
- **ACE (evolving context playbooks)** — Generator/Reflector/Curator with **deterministic non-LLM merge**; names **"context collapse"** (step 60 = 18,282 tok @66.7% → next step collapsed to 122 tok @57.1%). Fix = **incremental delta updates + grow-and-refine + embedding-dedup.** *Never let an LLM rewrite the whole memory.*
- **Reflexion** — Actor/Evaluator/Self-Reflection, verbal episodic memory, bounded to last-3; 91.0 pass@1 HumanEval; bounded by test quality, can settle in local minima. *Cheap self-improvement loop, but bound it + external verifier.*
- **Anthropic Agent Skills** — folder + `SKILL.md` (YAML `name`+`description` required), **3-level progressive disclosure** (name+desc at startup → full body when task matches → bundled files on demand); bundled executable code → **effectively unbounded** context while resident stays tiny. *The deployable runtime/packaging shell.*

**Two failure modes the design must defeat:**
1. **Context rot** (Chroma, 18 frontier models): reliability degrades with input length **even on trivial tasks**, far below the max window; **even one distractor hurts**; a coherent haystack is *worse* than a shuffled one. More skills in context ≠ better — irrelevant-but-plausible skills act as distractors.
2. **Skill debt**: unbounded memory goes stale/redundant; needs dedup + conflict-resolution + forgetting. Admission is a **software-supply-chain problem** — a real marketplace saw **~1,200 malicious skills** exfiltrating credentials [LOW, 2026 preprint].

### 6.2 Two design laws
- **Law 1 — generalize by abstraction, never memorize the trajectory:** (a) parameterize concretes into typed slots, (b) decompose into small reusable sub-routines. Lift a single run before storage.
- **Law 2 — admission is the whole ballgame:** curated +16.2pp vs self-gen −1.3pp. Never let an agent's own "I succeeded" admit a skill; admit only through a **deterministic external verifier.**

### 6.3 Anticipy skills pipeline (extends `recipes.py`)
`recipes.py` is already Voyager-lite (records a verified PROGRESS trace keyed by `(domain, normalized-task)`, stores **stable descriptors** not volatile indices, replays via `match_index`, **self-heals to the live loop on divergence** — a bad replay can't make the agent wrong). Four gaps to close:
- **LIFT** — on a verified success (read-back passed, not self-claim), convert the PROGRESS `_trace` to a skill: parameterize concretes → typed slots, decompose, **reject any hardcoded selector/ID/value** (force to a param or `locate()` helper). Keeps the anti-cheat grep clean — the skill bank is *data, not code*.
- **ADMISSION GATE (CI for skills)** — quarantine → shadow → promote: (1) re-execute passes `verify.py` on real state; (2) skill actually invoked & non-trivial; (3) every action causes a real change (no no-ops); (4) **held-out 2–5 sibling tasks** pass before reusable. The **global generic tier only accepts skills with zero user data** (supply-chain isolation); everything else stays per-user in Supabase.
- **DELTA STORAGE** — deterministic curator does append/patch + embedding-dedup; versioned, deprecate-never-delete (beats context collapse).
- **RETRIEVE-BEFORE-TASK** — embed intent → top-k *descriptions* (L1 only) → **hard rerank (precision ≫ recall)** → load full body for 1–3 survivors → site-tagged first, generic fallback → replay if match (~$0), else live loop whose verified trace becomes a new candidate. Cap active skills per turn; resident context = task + last-3 reflections + 1–3 active bodies.
- **GENERALIZE (two tiers + refine-on-failure)** — site-specific vs generic; when a generic fails on a new layout, branch a site-specialized version rather than overwrite.
- **LIFECYCLE (hygiene)** — merge near-duplicates whose verifiers agree; refine on failure from error feedback; prune by `usage_count` + rolling `success_rate`.

**Skill representation:** Agent-Skills directory (`SKILL.md` YAML + `steps.json` parameterized trace + `verify.py` deterministic gate + `examples.jsonl` L3). Progressive disclosure is the structural anti-context-rot defense.

**Sources:** [Voyager](https://arxiv.org/abs/2305.16291) · [AWM](https://arxiv.org/html/2409.07429v1) · [ASI](https://arxiv.org/html/2504.06821v1) · [ACE](https://arxiv.org/html/2510.04618v1) · [DreamCoder](https://arxiv.org/abs/2006.08381) · [Reflexion](https://arxiv.org/html/2303.11366) · [Anthropic Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) · [Chroma Context Rot](https://www.trychroma.com/research/context-rot) · [SoK: Agentic Skills](https://arxiv.org/html/2602.20867v1) · [MUSE-Autoskill](https://arxiv.org/pdf/2605.27366) · [Agent Memory survey](https://arxiv.org/html/2606.06448v1)

---

## 7. Cost, models, hosting

**Bottom line:** hitting "1/15 of Opus cost" is the *easy* part (a GUI-specialist open VLM is 20–60× cheaper on raw token math). The hard part is quality — the answer is a **two-tier planner/grounder split + recipe-replay caching.** Do **not** LoRA first.

### 7.1 Frontier baseline (Opus-in-Chrome)
Claude Opus 4.8/4.6: SS-Pro **0.879** (#1), OSWorld ~72.7%, WebArena ~64.5%. **$5 in / $25 out per Mtok.** Cost driver = image input tokens (every step re-sends a screenshot ~1,000–1,600 tok, up to ~4,784 at full 2576px). Prompt caching → cache reads 0.1× ($0.50/Mtok), cache writes 1.25×/2×, Batch −50%, min cacheable prefix 4,096 tok. [HIGH — confirmed]

### 7.2 Cheap open VLMs
| Model | in/out $/Mtok | Role |
|---|---|---|
| **UI-TARS-1.5 7B** | **$0.10 / $0.20** | Grounding specialist (91.6 ScreenSpot-v2; but OSWorld only 24.6 — weak planner) |
| **Qwen3-VL 235B-A22B** | **$0.20 / $0.88** | Cheap generalist planner (strong reasoning; pro-grounding ~0.70 trails Opus) |
| **GUI-Actor-7B** | self-host | Coordinate-free grounder, 44.6 SS-Pro (> UI-TARS-72B's 38.1) — for dense/pro UIs |
| GLM-4.5V | $0.60 / $1.80 | Vision-agent generalist |
| **UI-Venus-1.5 / EvoCUA** | self-host | Open #1 (69.6 SS-Pro) — **both fine-tuned from Qwen3-VL** = the LoRA ceiling |

**Key read:** UI-TARS-7B is a brilliant grounder but weak planner; Qwen3-VL is the inverse. Neither alone matches Opus; **the split preserves task success.**

### 7.3 Hosting / self-host break-even
- **Serverless:** DeepInfra (cheapest), Together (price leader at scale), Fireworks (best LoRA workflow), Cerebras (fastest 600–3,000 tok/s but 2–3× price — buy only when latency is the product), Modal (per-second, scale-to-zero; **L40S ~$1.95/hr**).
- **Break-even:** below **~30–50M tok/day**, serverless API wins (no idle burn). Above it, self-host **only the 7B grounder** on Modal L40S (SGLang ~29% faster than vLLM; 7B fits one card ~1,000+ tok/s single-stream). **Never self-host Opus/Qwen3-VL-235B** — H100/H200 idle burn never pays back at product volume.

### 7.4 LoRA — worth it? Not first.
AgentTrek: **$0.55/trajectory**; Qwen2-VL-7B grounding **30.7%→67.4%** (2.2×) after fine-tuning; ~5–6k trajectories ≈ **$3–4k** all-in (Fireworks). **Verdict: don't LoRA first.** Pays off only when (a) surface is narrow/stable (your own recurring Chrome flows) and (b) off-the-shelf grounding provably misses *your* UIs from real failure logs. It's the last optimization, not the first.

### 7.5 Caching / recipe-replay — highest-leverage cheap win
- **Deterministic recipe-replay:** record a successful trajectory for a recurring flow, replay the action sequence with **zero VLM calls**, fall to the model only on divergence → per-task VLM cost toward **~$0**.
- **Agentic Plan Caching:** reuse plan templates → **−50% cost, −27% latency.**
- **Prompt-prefix caching:** free on vLLM; 0.1× cache reads on Anthropic (keep the volatile screenshot after the last `cache_control` breakpoint).

### 7.6 Locked five-tier routing + $/task
| Tier | Model | in/out $/Mtok | When |
|---|---|---|---|
| **T0 Search/read** | Brave/Serper + **Haiku 4.5** ($1/$5) | ~$0.003/query | Every READ intent, first |
| **T1 Planner** | **Qwen3-VL 235B** | $0.20/$0.88 | Every step's "what next" (off AX-tree text) |
| **T2 Grounder** | **UI-TARS-1.5 7B** (GUI-Actor for dense UIs) | $0.10/$0.20 | Every UI action (screenshot) |
| **T3 Escalation** | **Claude Opus 4.8** | $5/$25 | Failure/low-confidence only, **≤2/task capped** |
| **T4 Recipe-replay** | — (no VLM) | ~$0 | Screen/DOM matches a cached cassette |

| Config | $/task | × under Opus |
|---|---|---|
| Opus 4.8 solo | $0.425 | 1× |
| Split (T1 plan + T2 ground), no escalation | ~$0.013 | ~33× |
| **Split + rare T3 escalation** | **~$0.02–0.03** | **~15–20×** |
| **Split + T4 replay (known flow)** | **~$0.002–0.008** | **~50–200×** |

**Locked target: ~$0.02–0.03/task cold, ~$0.002–0.008 warm.** Both clear the 1/15 (~$0.028) bar. The ≤2 Opus escalation cap matters — uncapped escalation is the one thing that silently reinflates cost toward Opus-solo.

**The governing KPI = hand-launch-rate / tier-mix** (fraction of steps reaching T2 pixels and T3 Opus) — simultaneously the cost driver and the flakiness driver. A success-rate that rises while tier-mix shifts toward T3 is **flagged, not celebrated.**

**Sources:** [SS-Pro leaderboard](https://llm-stats.com/benchmarks/screenspot-pro) · [UI-Venus-1.5](https://arxiv.org/pdf/2602.09082) · [UI-TARS-7B pricing](https://openrouter.ai/bytedance/ui-tars-1.5-7b) · [Qwen3-VL 235B pricing](https://pricepertoken.com/pricing-page/model/qwen-qwen3-vl-235b-a22b-instruct) · [GUI-Actor](https://arxiv.org/pdf/2506.03143) · [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) · [inference pricing matrix Q2 2026](https://www.digitalapplied.com/blog/ai-inference-providers-pricing-matrix-q2-2026) · [Modal pricing](https://modal.com/pricing) · [self-host vs API](https://www.aipricingmaster.com/blog/self-hosting-ai-models-cost-vs-api) · [AgentTrek](https://openreview.net/pdf/e95d923ccea15b1bab268aeeb8b3845547e3dafe.pdf) · [Agentic Plan Caching](https://arxiv.org/abs/2506.14852) · [Trajectory reduction](https://arxiv.org/pdf/2509.23586)

---

## 8. Search/browser split + the autonomous test harness

### 8.1 The read-vs-act lane split
**Cost asymmetry (why the split exists):** a 1920×1080 screenshot ≈1,500–3,000 input tokens vs a structured DOM/aXtree extract ≈300–800 (a 5× floor; compressed diffs 10–50 tok). Screenshot-driven ≈1.5–3 s/step vs DOM-driven ≈0.3–0.8 s/step. Hidden JSON (the site's own backend) is cheapest of all. Goal: **answer as much as possible without launching the hand.**

**Three-tier lane model (cheapest-first):**
1. **Web-search lane** (Brave/Serper/Firecrawl + lightweight fetch-extract) — read-only, never launches a browser.
2. **Shadow-API lane** (the site's own JSON/XHR endpoints) — deterministic JSON, no DOM/pixels. Discover via traffic interception (HAR/CDP `Network.*` during any hand session), `/.well-known/agents.json`, WebMCP; cache in a **route/skill graph** so future tasks skip the browser entirely.
3. **Browser-hand lane** — the full DOM/vision agent on the real session, last resort.

**Measured payoff (WebArena):** browser-only **14.8%** → API-only **29.2%** → **hybrid 38.9%**; API-solvable tasks needed only **2.1 calls** avg. The hybrid wins by using the browser as a *backup*, not the default.

**Router:** explicit READ/ACT classifier in front of the ladder. READ → lane 1 then 2, never the hand unless both fail. ACT → lane 2 (safe endpoint) then lane 3, **always ask-first gated**.

**Anticipy refinement:** the product is deliberately **browser-only via the extension** (not the Arcade/API arm that caused calendar spam). This does NOT contradict the split — lane 1 (search) and lane 2 (the *site's own* XHRs observed through the extension's own network traffic on the real session) are the browser hand's cheap *modes*, not a third-party API arm. The split is *inside* the browser-only world: cheap read modes vs the expensive click/vision mode, preserving the "one hand, real account" invariant.

### 8.2 The `context_eval` harness (un-gameable)
**Central fact:** benchmarks massively overstate real capability — Online-Mind2Web found agents scoring 60–90% on old benchmarks hit **~30%** under honest human eval. So the harness is engineered to resist the ways evals lie. **Six invariants:**
1. **Every task ships a machine-checkable functional postcondition** — a real artifact exists in the real account (message in Sent, row in the Sheet, event on calendar). No task grades the agent's "done." Judge-only allowed *only* where judge κ ≥ threshold, proven by `judge_calibration.py`.
2. **Verification is active, not passive** (ProRe: a reasoner schedules state-probing tasks; evaluators re-interrogate real world state; +5.3% reward accuracy, +19.4% F1, up to +22.4% downstream). The grader **re-opens the account and independently confirms** the artifact — never reads the transcript. This is R1→R2→R3 live-readback, mechanized.
3. **Two lanes of truth:** `replay_ci` ("is my agent broken?", $0, deterministic, mitmproxy/Agent-VCR cassettes) and `live_canary` ("does it work in reality?", variance-reported, BrowserArena-style step-level human eval). **A green replay suite never counts as "works end-to-end."**
4. **Multi-objective scorecard:** success cannot be reported without cost-of-pass, hand-launch-rate (tier-mix), and injection-refusal rate.
5. **The judge is a calibrated instrument with a known error bar** — WebVoyager GPT-4V judge κ≈0.70; **BrowserArena VLM judges 58–68% and *worse* with GIFs** (GPT-4o 79%→68%). Use WebJudge's staged design (key-point → key-screenshot → outcome, 85.7% agreement, 3.8% gap). Policy model and judge never share prompt lineage or model family.
6. **Curation gate before promotion:** enter the reusable set only after 2–5 held-out siblings pass (SoK +16.2 vs −1.3). Quarantine → shadow → promote.

**The four real-world tasks** (Agent-Skills-compatible bundles): (A) **Amazon-return** — irreversible-ACT template solved via test accounts + a `commit_boundary=pre_submit` (drive to review, assert state, don't finalize; a rare weekly full-commit canary on a burner account tests the last click); (B) **Sheets** — fully-reversible gold-standard, deterministic Sheets-API ground truth, the `replay_ci` workhorse; (C) **Gmail→WhatsApp** — cross-app, key-point-match (right facts extracted + right message landed, both re-read independently, grader-owned echo number); (D) **form-fill** — self-hosted grader form, exact backend assert, plus an `isTrusted` check that the fill went through CDP `Input.dispatch*` not JS `dispatchEvent`.

**Benchmark subset (functional-checker-only):** ~120 ScreenSpot-Pro/v2 points weighted to Anticipy's real surfaces (decides UI-TARS vs GUI-Actor per surface, catches grounder drift, every PR); 60–80 `webarena-verified` (ServiceNow) tasks nightly N=3 seeds report variance; the 4 tasks × siblings; 8–12 live canary weekly; ~15 injection variants every PR. Unified via **BrowserGym**.

**Cost as a co-equal metric:** cost-of-pass = Σ($)/completions; hand-launch-rate; frontier-rate; tier-mix. **Cost-regression gate:** a PR fails if cost-of-pass rises >15% OR frontier-rate rises >3pp at equal-or-lower success. Sandbox every task (container → gVisor → Firecracker → WASM). The eval's tier-mix *is* the routing cost KPI — it tells the router when T0/shadow-API/T4 are under-firing and when a surface's grounding is chronically failing (the LoRA trigger).

**Sources (split):** [Internal APIs shadow APIs](https://arxiv.org/pdf/2604.00694) · [Beyond Browsing: API-Based Agents](https://yueqis.github.io/API-Based-Agent/) · [Agent-E](https://arxiv.org/pdf/2407.13032) · [WebMCP](https://www.webfuse.com/blog/what-is-webmcp-the-practical-guide-to-the-web-model-context-protocol) · [agents.json](https://studiomeyer.io/en/blog/agents-json-explained) · [DOM vs screenshot cost](https://karatelabs.io/blog/dom-vs-screenshot-ai-testing) · [browser-agent latency benchmark](https://www.ytyng.com/en/blog/ai-browser-automation-tools-comparison-2026)
**Sources (harness):** [WebArena](https://arxiv.org/html/2307.13854v4) · [webarena-verified](https://github.com/ServiceNow/webarena-verified/blob/main/README.md) · [WebVoyager judge κ=0.70](https://arxiv.org/html/2401.13919v3) · [Illusion of Progress / Online-Mind2Web / WebJudge](https://arxiv.org/html/2504.01382v4) · [BrowserArena](https://arxiv.org/html/2510.02418v2) · [ProRe](https://arxiv.org/abs/2509.21823) · [RewardHackingAgents](https://arxiv.org/pdf/2603.11337) · [EvilGenie](https://arxiv.org/pdf/2511.21654) · [BrowserGym](https://arxiv.org/pdf/2412.05467) · [Agent VCR](https://github.com/Jarvis2021/agent-vcr) · [mitmproxy replay](https://speedscale.com/blog/mitmproxy-vs-proxymock-for-replay/) · [WebMall cost metrics](https://arxiv.org/pdf/2508.13024) · [AI agent sandboxing (Firecrawl)](https://www.firecrawl.dev/blog/ai-agent-sandbox) · [sandbox isolation primitives](https://zylos.ai/research/2026-04-04-ai-agent-sandboxing-security-isolation/)

---

## 9. Extension / CDP engineering (driving the user's real logged-in Chrome)

**Recommended architecture:** an **MV3 extension that attaches `chrome.debugger` to the target tab and drives it over CDP, against the user's real profile,** CDP hand kept local, only high-level intent to/from the cloud.

**The load-bearing fact [HIGH]:** CDP `Input.dispatchMouseEvent`/`dispatchKeyEvent` inject at the browser's input pipeline, so events carry **`isTrusted=true`** — indistinguishable from a human at the event layer. JS `dispatchEvent()`/content-script clicks are permanently `isTrusted=false` by spec, and `chrome.debugger` is essentially the *only* way an extension emits trusted events. (One search snippet claiming CDP inherits `isTrusted=false` is **wrong** — it conflated JS dispatch with CDP injection.)

**The two "obvious" alternatives are dead/dangerous for the real-profile case:**
- **Remote-debugging-port attach** (Playwright/Puppeteer `connectOverCDP`) is **dead on the default profile: since Chrome 136, `--remote-debugging-port`/`--remote-debugging-pipe` are ignored on the default user-data-dir** and require a non-standard `--user-data-dir` = a different, logged-out profile. Also a documented cookie-dump vector — keep it off entirely.
- **Native-messaging host for cookie/session access** is exactly the pattern 2026 malware uses to hijack sessions and bypass MFA — the wrong tool for credential access.

### 9.1 `chrome.debugger` + CDP mechanics
Declare `"permissions":["debugger"]` + `host_permissions`; `attach({tabId},"1.3")` → `sendCommand(...)` → `detach()`. Auto-detaches on tab close or when the user opens DevTools. Available: Accessibility, DOM, DOMSnapshot, Input, Page, Network, Runtime, Emulation, Fetch, Target, Storage, WebAuthn. Restricted (need real DevTools): `Debugger.*`, `Profiler.*`, `HeapProfiler.*`. Cannot attach to `chrome://*`, the Web Store, or other extensions. **Flat sessions (Chrome 125+):** attach to child targets (OOPIFs, workers) via `sessionId` without separate `attach()`. Key typing needs `keyDown → char → keyUp`. `Page.captureScreenshot` with `captureBeyondViewport` for full-page; `Accessibility.getFullAXTree` + `DOM.*` (with `pierce` for shadow/iframes) for structured state.

**The warning bar:** attaching shows a persistent **"⟨Extension⟩ started debugging this browser"** infobar the extension cannot hide (anti-abuse). Suppressions: launch flag **`--silent-debugger-extension-api`** (every shortcut, full restart) or enterprise **`ExtensionInstallForcelist`** policy. This is a live pain point for Anthropic's own Claude-in-Chrome. **Decision:** ship the honest default (banner = trust signal) + offer the launch-flag/policy path for power users.

### 9.2 isTrusted / anti-bot on real logged-in sites
`isTrusted` is table stakes, not a cloak. Modern anti-bot (Cloudflare/DataDome/Akamai/Kasada) score TLS/JA3 + IP reputation + fingerprint + **behavioral telemetry** (mouse acceleration, scroll dynamics, inter-click timing, keystroke cadence).
- **The `Runtime.enable` leak:** Puppeteer/Playwright auto-issue `Runtime.enable` on every frame → detectable via `Runtime.consoleAPICalled`. **With `chrome.debugger` you control exactly which CDP commands you send — you never have to globally `Runtime.enable`, sidestepping the #1 classic CDP tell by construction.**
- The `console.debug`+`Error.stack` CDP signal was **neutralized May 2025** by V8 changes.
- **Human-motion layer:** feed `Input.*` a Bézier path (`ghost-cursor`, Fitts's-Law timing, overshoot-and-correct) + micro-jitter, variable dwell (~40–120ms), ±30ms band. **This is exactly the DEV-FINAL `humanlike.py` to graft into the extension's `cdpClick`/`cdpType`.**
- **Anticipy's advantage:** it runs on the user's **real machine, real residential IP, real profile, real cookies, established history** — the exact signals anti-bots use to *trust* a session. The thing most likely to trip detection is robotic timing, which `Input.*` + humanlike motion neutralizes. Plan for the industry's move toward **agent-trust/allowlisting**, not permanent invisibility.

### 9.3 Session/token security
**Drive INSIDE the user's own authenticated session; never exfiltrate cookies/tokens.** The moment you pull cookies to a server you've rebuilt the malware session-hijack kill chain. No `--remote-debugging-port`, no native-messaging cookie access. Credential-handling taxonomy: stored profile = highest risk; just-in-time handoff (1Password Secure Agentic Autofill); direct-API replay = lowest blast radius. For any fresh login/2FA/CAPTCHA wall, **pause and hand off to the user** — never type credentials or solve challenges. Keep the CDP socket local; send intents down, compact state (screenshots/AX summaries) up.

### 9.4 CDP reliability on real pages
- **Transient execution contexts:** `ExecutionContextId`s invalidate on reload/navigation and SPA re-renders — track and re-resolve before evaluating.
- **Frame ≠ target:** same-process frames share a target; OOPIFs spawn new targets — use flat sessions.
- **Shadow DOM/iframes:** `DOM.*` `pierce`/`depth` flags.
- **SPA timing:** never fixed-sleep; wait on real signals (`Page.frameStoppedLoading`, network-idle, DOM/AX stabilization). Industry pattern: **record-once/replay-many with a vision-CUA fallback** for the long tail.
- **DevTools conflict:** opening DevTools force-detaches — handle `onDetach`, reconnect. Keep the session attached for the whole task (attach/detach cycles add latency).

### 9.5 Alternatives compared
| Approach | Real profile? | Trusted input? | Verdict |
|---|---|---|---|
| **MV3 + `chrome.debugger` (CDP)** | **Yes** | **Yes** (`Input.*`) | **Recommended** |
| Content-script DOM automation | Yes | **No** (`isTrusted=false`) | Fallback for benign reads only |
| Playwright `connectOverCDP` (remote-debug port) | **No** (Chrome 136 blocks default dir) | Yes | Rejected for real-profile |
| Native-messaging host | Bridge only | delegates | **Dangerous for cookie/session access**; only as optional local launcher |
| Computer-use / OS-level | Yes | Yes | Last-resort fallback (slow, brittle) |
| Custom Chromium fork (browser-use) | No | Yes | Wrong shape for "drive MY Chrome" |

**Confidence:** HIGH on the decisive facts (trusted CDP input; Chrome-136 remote-debug block; warning-bar suppression; Runtime.enable leak + extension advantage; native-messaging risk) — each ≥2 sources/primary docs. MED on forward anti-bot posture and per-vendor behavioral thresholds (moving targets).

**Sources:** [chrome.debugger API](https://developer.chrome.com/docs/extensions/reference/api/debugger) · [Chrome 136 remote-debug change](https://developer.chrome.com/blog/remote-debugging-port) · [MDN isTrusted](https://developer.mozilla.org/en-US/docs/Web/API/Event/isTrusted) · [chromium-dev thread](https://groups.google.com/a/chromium.org/g/chromium-dev/c/94t2J_Jylyw) · [CDP-from-extensions](https://medium.com/@dzianisv/vibe-engineering-chrome-devtools-protocol-from-extensions-you-dont-need-to-fork-chromium-72a9ffb68b6d) · [CDP Input domain](https://chromedevtools.github.io/devtools-protocol/tot/Input/) · [CDP DOM domain](https://chromedevtools.github.io/devtools-protocol/tot/DOM/) · [rebrowser Runtime.enable](https://rebrowser.net/blog/how-to-fix-runtime-enable-cdp-detection-of-puppeteer-playwright-and-other-automation-libraries) · [Castle CDP signal neutralized](https://blog.castle.io/why-a-classic-cdp-bot-detection-signal-suddenly-stopped-working-and-nobody-noticed/) · [ghost-cursor](https://github.com/Xetera/ghost-cursor) · [ghost-cursor timing](https://roundproxies.com/blog/ghost-cursor/) · [theairuntime field guide](https://theairuntime.com/p/the-complete-field-guide-to-browser) · [Open Browser Use](https://www.producthunt.com/products/open-browser-use) · [browser-use bot detection](https://browser-use.com/posts/bot-detection) · [DataDome bypass (Scrapfly)](https://scrapfly.io/blog/posts/how-to-bypass-datadome-anti-scraping) · [Claude-in-Chrome banner issue](https://github.com/anthropics/claude-code/issues/69287) · [silent-debugger flag (Voice In)](https://help.dictanote.co/help/general/hiding-the-voice-in-started-debugging-this-browser-message) · [Malwarebytes cookie theft](https://www.malwarebytes.com/blog/news/2026/06/malware-steals-chrome-session-cookies-to-take-over-your-accounts) · [Chrome native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging) · [SpecterOps cookie dumping](https://posts.specterops.io/hands-in-the-cookie-jar-dumping-cookies-with-chromiums-remote-debugger-port-34c4f468844e) · [1Password/field-guide credential models](https://theairuntime.com/p/the-complete-field-guide-to-browser) · [devtools-protocol #72 (contexts)](https://github.com/ChromeDevTools/devtools-protocol/issues/72)

---

## 10. The build delta (concrete, on `hoe/build`)

| Component | Status | Action |
|---|---|---|
| Orchestrator loop, PLAN/label/COMMIT/budgets | Exists (tangled in `webvoyager.py`) | Refactor into named 9-phase loop over explicit `RunState`; **don't rewrite** |
| Perception (SoM DOM + on-demand vision) | Exists (`background.js`) | Keep; graft `humanlike.py` into `cdpClick/cdpType` |
| Skill-fetcher / recipe flywheel | Exists (`recipes.py`) | Wire as tier0; enforce "hint not command" (verify-gated); write back verified traces |
| Escalation router (4-tier) | **Missing** | Port `vision_router.py` → phase 5 |
| Deterministic safety firewall | Fragmented (regex guards) | **Land `action_guard.py` (Nick's, 15/15) FIRST** at `engine/anticipy_engine/hands/action_guard.py` → phase 7 |
| Verifier (deterministic read-back) | Partial (`_sig`, `_verify_answer`, `proof.py`) | Formalize as VERIFIER role; add VLM tie-break via `vision_verifier.py` |
| Checkpoint/resume + wall handoff | Exists (`resume_store.py`, `handoff.py`) | Checkpoint at every subgoal boundary; enforce idempotency-before-checkpoint |
| Read-only research fan-out | Exists (`browser_use_link.py`) | Keep as the ONLY sanctioned parallel/second-context path; never the actor |
| Eval scoreboard | Both camps agree it's the gate | Build `browser_eval.py` / `context_eval` (reconcile Nick's `agent_lab/`) — decide keep-vs-replace by numbers |

**Key files to act on:** `/Users/omarebrahim/Anticipy-devin/engine/anticipy_engine/agent/webvoyager.py` (refactor into roles) · `/Users/omarebrahim/Anticipy-devin/extension/background.js` (graft humanlike) · port `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/app/action_engine/{vision_router,vision_verifier,humanlike}.py` · land Nick's `action_guard.py` from `origin/nick-sevostiyanov-demo/site:ai-guidance/browser-agent/action_guard.py`.

---

## 11. The unifying invariant (the reason this log exists)

Two interlocking systems form the flywheel:
- **System 1 (contingency):** wrap every action in a mandatory verify-and-recover cell (deterministic pre-gate → wait → interrupt-scan → act → read-back → escalation ladder → risk-tiered pause-text-resume, checkpointed + idempotent).
- **System 2 (skills):** feed each *externally-verified* pass into a lifted, admission-gated, delta-stored, self-pruning skill bank retrieved *before* the next task.

**One un-gameable seam gates both** — admission and task-done are the *same* functional read-back on real world state, actively re-verified, never self-graded. This is the single defense against an eval or skill-bank that lies, and it is literally the R1→R2→R3 live-readback discipline, mechanized. **Cost and flakiness fall monotonically while the handler library grows on every contingency** — the definition of anti-fragile.

*End of RESEARCH.md.*