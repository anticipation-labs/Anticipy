# PLAN: 73% → ~90% — Anticipy Browser Agent (cost-effective)

**Measured baseline:** 8/11 live = **72.7%** on the current live board.
**Target:** ~90% on complex real-world tasks, held at **~$0.02/task** (warm).
**Thesis (from the research):** the gap between a ~73% agent and a ~90% agent is **recovery + grounding reliability, not planning.** End-to-end success compounds multiplicatively (`success ≈ p_step^n`), so the last ~17 points come from (a) raising per-step grounding reliability and (b) verify-then-recover so one bad step doesn't kill the trajectory. Every lever below buys per-step reliability or recovery. (`final/browser/RESEARCH.md`; reliability-compounding: arXiv 2603.29231.)

This plan is grounded in two things and nothing else:
- **(a) the real diagnosed failures** — dropdown/select grounding (live fail #2), cart/state-verify (fail #4), search-submit + premature give-up (fail #5), plus two systemic bugs: **frontier ≈ 45%** (cost bleed) and **vision = 0%** (dead crop/GROUND path).
- **(b) the research** — grounding recipe (DOM-first widgets), verify-and-recover ranking, cost-routing lock, and the 73→90 leverage read.

Every file:line below was re-verified against the working tree on 2026-07-03.

---

## 0. What is actually broken (the diagnosis, in one table)

| # | Symptom (live) | Root cause · verified seam | Class |
|---|---|---|---|
| **2** | `the-internet/dropdown` — answered "Option 2", judged short | Observe serializes `<select>` as **one** element; `<option>` children never enumerated (`extension/background.js:628`, the `sel` selector includes `select` but not `option`). Actor never *sees* the options; can only echo the task. Grounding then fails: `_state_readback` (`webvoyager.py:824`) may not emit the `value=` line, and `judge()` (`webvoyager.py:1920`, drops the screenshot to `image=None` when any text/state exists, ~1937-1938) has zero grounding for the selection (a native `<select>`'s value isn't in `innerText`). | **Grounding (widgets)** |
| **4** | `saucedemo` — cart badge=1 but judged short / wrong-item | Mutation-proof (`_complete_with_artifact_proof`, `webvoyager.py:838`) only **re-reads the same inventory page** for stability — never opens `/cart.html`. The Add→Remove toggle is a plain `<button>` with no checked/value state, so `_state_readback` emits nothing binding "Backpack"→"in cart". Judge is text-only and the answer is a self-report → correctly fails. | **State-mismatch / false success** |
| **5** | `demowebshop` — "page has no product information" (gave up) | (a) Search submit fragile: `type` with enter only fires CDP `cdpKey(tab,"Enter")` (`extension/background.js:1057`); the JS `value_setter` fallback (`background.js:1031/1046`) never fires keydown or `form.requestSubmit()`. If CDP key doesn't land, page never navigates → homepage re-read → no products. (b) Give-up not caught: `_NO_ANSWER_RE` (`webvoyager.py:538`) misses "no **product** information" (the word "product" splits "no … information") → the shrug is committed as a real answer. | **Premature abandonment** |
| **S1** | `frontier ≈ 45%` (cost bleed on the paid ladder) | `escalate = (sub_stuck>=2) or (forbid is not None)` → `tier = SMART if escalate else ACT` (`webvoyager.py:1350-1351`). `forbid` is set on **any** NO_CHANGE/blocked action and only cleared on progress, so **one** no-progress step forces **every** later step onto SMART until progress. The capped ESCALATE rung is never requested anywhere → `gateway.py:131-166` is dead code; every stall pays full SMART. | **Cost / mis-routing** |
| **S2** | `vision = 0%`, region-crop + GROUND tier never fire | `VISION_MODE="always"` (`webvoyager.py:239`) makes `_wants_full_shot` always True (`webvoyager.py:635`), so `_region_crop` (`webvoyager.py:678`) and the GROUND tier are dead by construction. Compounding runtime bug: `cdpScreenshot` on a backgrounded tab returns `null` (`extension/background.js:503-510`) → `shot=None` → vision never fires and the judge loses its one image. | **Grounding (cheap-vision path dead)** |

---

## 1. The ordered levers (by leverage-per-effort)

Ordering rule: cheapest fix that closes a whole failure **class** first; expensive/selective levers last. L1–L3 convert the measured **8/11 → ~11/11** on today's board (immediate, provable). L4–L7 are what **hold ~90%** as the board expands to harder/repeated complex tasks. L8 is selective insurance.

---

### L1 — DOM-native widget grounding (select / combobox / option enumeration)

- **What to build:** In observe extraction, when `el.tagName==='SELECT'`, attach the `<option>` texts + the selected one into the element payload (new `options[]` / enriched `name`) so the actor *sees* the choices. Add an `action=select_option` path that sets the value via the DOM API (match by visible option text) rather than pixel-clicking a native overlay. Bind the confirmed selected option text into the answer at completion, and surface it as element `state` so `_state_readback` carries it. Keep the screenshot alive in `judge()` for pure action/visual-state tasks.
- **Fixes:** live fail **#2** (dropdown) and the whole native-`<select>` / ARIA-combobox class.
- **Expected lift:** the grounding recipe is unambiguous — *"never click-and-pick a native `<select>`; drive it via the DOM `selectOption`/keyboard path at $0 VLM tokens."* Set-of-marks / DOM-index **suffices** for any element with a stable role+name and is *"the cheapest single grounding win available"* (RESEARCH lever #2; DashboardQA: a11y tree **40.8%** vs pure-screenshot **<21%**). Directly converts fail #2 to a pass (+1/11 ≈ **+9pp** on today's board; class-level it removes the #1 "click-then-pick" failure mode).
- **Cost impact:** **$0 extra VLM tokens** (deterministic DOM path replaces a vision guess). Slightly *cheaper* — no full-frame needed to pick an option.
- **Code seam:** `extension/background.js:628` (the `sel` selector — enumerate `<option>`); `engine/anticipy_engine/agent/webvoyager.py:824` (`_state_readback` — emit selected value); `webvoyager.py:1920` / ~1937-1938 (`judge()` — stop nulling the screenshot for action/visual-state tasks). Keyboard type-ahead (focus → ArrowDown → type letters → Enter) is the universal fallback for the no-DOM/virtualized case (grounding recipe §1 class A/D).

---

### L2 — Search-submit robustness + premature-give-up recovery

- **What to build:** (a) A non-CDP submit fallback in the `value_setter` path: dispatch a synthetic Enter `keydown` + `form.requestSubmit()`, and after a search **verify the URL/DOM actually changed** to a results state before reading. (b) Broaden `_NO_ANSWER_RE` to catch "no product(s)/results found", "has no … information", and route a matched give-up to a **scroll / re-search retry**, not a committed answer.
- **Fixes:** live fail **#5** (search) and the premature-abandonment class.
- **Expected lift:** on Online-Mind2Web error analysis, **~51% of real-world failures are access/environment issues** (page-load/redirect/interruption) *"much of which is recoverable with a retry/replan rather than a give-up"* (RESEARCH verify-and-recover; futureagi "six failure modes" — deterministic guards, *"almost free; disproportionate real-world payoff"*). Converts fail #5 to a pass (+1/11 ≈ **+9pp** on today's board).
- **Cost impact:** **~$0** (deterministic DOM/JS; one extra re-observe only when the give-up guard trips).
- **Code seam:** `extension/background.js:1057` (`cdpKey` enter) + `background.js:1031/1046` (`value_setter` — add keydown + `requestSubmit`); `engine/anticipy_engine/agent/webvoyager.py:538` (`_NO_ANSWER_RE`) + `webvoyager.py:548` (`_looks_like_no_answer` → route to retry).

---

### L3 — Per-action read-back proof for mutations (cart / submit verification)

- **What to build:** Make the mutation-proof step actually **navigate to the resulting state and re-read** (cart page: item name + qty; form: server echo / backend `/last`) instead of re-reading the same page. Surface the Add→Remove toggle / cart-badge count as element `state` so `_state_readback` carries per-item proof. Bind the verified item name into the answer. This is *per-action read-back*: assert the intended effect (item X, qty 1, in cart), not "an action occurred."
- **Fixes:** live fail **#4** (cart) and the "added-to-cart-but-wrong" / false-success class.
- **Expected lift:** per-action read-back is a **+3 to +6pp** lever and *"kills silent no-ops and added-to-cart-wrong early, before error-compounding"*; self-critical per-step auto-validators lift a WebVoyager subset **76.2 → 81.24% (~+5pp)** (RESEARCH verify-and-recover #3). Converts fail #4 to a pass (+1/11 ≈ **+9pp** on today's board). Critically, **self-report is not evidence** — the read-back must be an independent state-grounded check (the browser_eval checkers already enforce this).
- **Cost impact:** **~$0** — one extra `observe` (a navigate + read), **no model tier bump**. Catching no-ops immediately also *saves* steps.
- **Code seam:** `engine/anticipy_engine/agent/webvoyager.py:838` (`_complete_with_artifact_proof` — navigate-to-cart re-read); `webvoyager.py:824` (`_state_readback`); `engine/anticipy_engine/agent/guarded_step.py:78` (`MUTATION_CTRL` already routes cart-add to proof — extend the proof, not the trigger).

---

### L4 — The graded cost ladder (kills frontier ≈ 45%, unlocks the recovery budget)

- **What to build:** Replace the binary escalate rule with a **graded ladder**: a *lone* `forbid`/NO_CHANGE stays on **ACT** (the stuck-note + region crop break most single loops far cheaper than a model bump); only a **genuine** stall (`sub_stuck>=2`) escalates to mid-tier **SMART**; only a **deep** stall (`sub_stuck>=3`) that SMART already failed spends one capped-frontier **ESCALATE**. Raise the subgoal-abandon wall by one so the ESCALATE step is actually reachable. Make the cost ledger reflect real per-call cost. Wire the real models via env (see §2).
- **Fixes:** systemic bug **S1** (frontier ≈ 45% cost bleed). *This is a precondition for L5/L8* — it frees the SMART/ESCALATE budget the recovery loop spends on genuine stalls instead of burning it on lone `forbid`s.
- **Expected lift:** not a quality lift — a **cost** lift that **holds quality within ~2pp of all-frontier** while cutting cost up to **78%** (Adaptive VLM Routing, warm+difficulty regime; RESEARCH cost-lock §2). Reclaims the ~45% of ACT steps that were needlessly paying SMART.
- **Cost impact:** **the** dollar lever — $0.12–0.16/task → **~$0.02/task** warm (one Opus step ≈ 55 ACT steps). Full math in §2.
- **Code seam (exact edits, cost-lock agent):**
  - `webvoyager.py:1350-1351` — replace `escalate = (sub_stuck>=2) or (forbid is not None)` / `tier = SMART if escalate else ACT` with: `ESCALATE` if `sub_stuck>=3`, `SMART` if `sub_stuck>=2`, else `ACT`.
  - `webvoyager.py:1866` — raise `sub_stuck >= 3` → `>= 4` so the single capped ESCALATE step fires before the subgoal is abandoned.
  - `gateway.py:37` — replace the flat `COST` constants with real blended per-call estimates (`ACT/GROUND 0.0004, SMART 0.003, ESCALATE 0.022`) so `frontier_pct`/`est_cost_usd` stop being fiction.
  - `gateway.py:123-132` defaults + `.env.local` — wire the locked models (§2). Escalate cap stays at 2 (`gateway.py:136-166`, already enforced).

---

### L5 — Checkpoint validator + replan-from-the-reached-page

- **What to build:** A Planner→Actor→**Validator** loop: after each subgoal, one independent state-grounded judge call confirms "did that produce the state I intended?"; on failure, **replan from the reached page** (not from the opening plan). Gate the in-loop `_verify_answer` to fire **once** (`MAX_ANSWER_CHECKS=1`) so the validator is a single grounded pass, not a per-answer SMART tax. Keep the empty-answer + multi-part completeness re-asks as-is (already narrowly gated).
- **Fixes:** the **complex-task success tail** — the "wrong path" and "thought it worked" classes that survive L1–L3, and the quality half of S1.
- **Expected lift:** **the single largest documented jump in the field.** Skyvern v1→v2 adding a Validator moved WebVoyager **~45% → 85.85%**. WebDART replan-from-page: **+8.8pp** on WebChoreArena (GPT-5), **+13.7pp Shopping, +15.4pp Reddit**, *while cutting steps 45%*, and does **not** regress easy tasks. Independent verifier that gates "done": **+5 to +7pp** downstream, ceiling = the **34–36% false-success rate** it recovers (SGV: +25pp failure-detection). (RESEARCH verify-and-recover #1/#2; 73→90 read #1.)
- **Cost impact:** **one extra SMART call per checkpoint** (not per token). Net-neutral-to-cheaper because replan cuts total steps ~45% and `MAX_ANSWER_CHECKS=1` removes the second verify tax. ~$0.003/checkpoint at the locked ladder.
- **Code seam:** `webvoyager.py:81` (`MAX_ANSWER_CHECKS` default 2→1, via `ANTICIPY_MAX_ANSWER_CHECKS=1`); `webvoyager.py:1543` (in-loop `_verify_answer` gate); `webvoyager.py:1009` (`_verify_answer`); the subgoal-completion path around `webvoyager.py:1866` (insert checkpoint-verify → replan on fail). Replan already exists (`_replan`, `caller="agent"`, SMART).

---

### L6 — Fix the screenshot-null capture + turn on cheap region-crop + wire the GROUND tier

- **What to build:** (a) Fix `cdpScreenshot` returning `null` on a backgrounded tab: log when it's null and force-attach the debugger before `Page.captureScreenshot` (the fallback path is already forbidden from grabbing the user's tab — keep that). (b) Flip `VISION_MODE` from `always` to **`auto`** so `_region_crop` fires — a few-hundred-token crop on ambiguous element decisions instead of a whole-page frame every step. (c) Wire the **GROUND** tier (`ANTICIPY_MODEL_GROUND`) into `_region_crop`'s grounding call so the cheap pixel→coord grounder runs instead of a full frame. Downscale sends to 1280×800.
- **Fixes:** systemic bug **S2** (vision = 0%, dead crop/GROUND). Backstops L1 for canvas / no-DOM / virtualized widgets where DOM grounding can't reach.
- **Expected lift:** crop-then-zoom **+7.4pp SS-Pro** (72.9 → 80.3, Mobile-Agent-v3.5) *while lowering the refine-pass token bill*; an 8B open grounder (Qwen3-VL-8B **52.7**, UI-Venus-8B **68.4** SS-Pro) lands within ~19pt of Opus — **frontier is never needed for coordinate localization** (RESEARCH grounding recipe §3; cost-lock §1). This is the fusion backstop, not the primary grounder — most widgets are solved DOM-first by L1.
- **Cost impact:** **~5× cheaper per vision step** (1280×800 ≈ 1,365 img tok vs 6,636 for a raw 4K frame) and crop replaces full frames on ambiguous steps. Precondition: (a) must land or `_wants_full_shot("always")=True` keeps the crop path dead. Quality-safe fallback if capture can't be fixed immediately: keep `always` but downscale — still ~5× cheaper, keeps the SoM lever.
- **Code seam:** `extension/background.js:503-510` (`cdpScreenshot` null → force-attach + log); `webvoyager.py:239` (`VISION_MODE` → `auto` via env); `webvoyager.py:635` (`_wants_full_shot`); `webvoyager.py:678` (`_region_crop` — call GROUND tier); `gateway.py:128` (`ground_model`).

---

### L7 — Skill / trajectory reuse + deterministic recipe-replay (the repeat-task lever)

- **What to build:** Compile a successful AI run on a known site into a stored recipe and **replay it deterministically** until the page structure changes (state-conditioned, step-level skill retrieval). This is Anticipy's *actual* domain — Gmail/Calendar/a handful of known sites hit repeatedly.
- **Fixes:** the *repeated-workflow* reliability + cost tail (and most of the warm-run cost).
- **Expected lift:** Agent Workflow Memory: **+51.1% relative on WebArena** (→35.6%), **+24.6% on Mind2Web**, *with fewer steps*; State-Grounded Dynamic Retrieval beats AWM by **~9.7 points**. *"For a product hitting Gmail/Calendar/a few sites repeatedly, this is the best points-per-dollar lever"* (RESEARCH 73→90 read #3).
- **Cost impact:** **drives warm cost toward ~$0 on repeats** (deterministic replay = no model calls until the page changes). This is what makes the warm-cascade `$0.008–0.012/task` regime real.
- **Code seam:** `engine/anticipy_engine/agent/recipes.py`, `engine/anticipy_engine/agent/skills.py` (recipe capture/replay already scaffolded — extend to state-conditioned retrieval; `replay%` is already a tier-mix field in `browser_eval`).

---

### L8 — Routed best-of-N on irreversible/hard steps only (selective insurance)

- **What to build:** For steps flagged irreversible (by `MUTATION_CTRL`, `guarded_step.py:78`) or high-difficulty, sample N candidate rollouts and pick the winner with **one O(N) "behavior-narrative" multiple-choice judge** (92.8% human agreement) — *not* N full re-evaluations. Reserve N>1 for those steps; N=1 everywhere else.
- **Fixes:** the residual hard/irreversible-step tail after L1–L6.
- **Expected lift:** Agent S3 Behavior-Best-of-N: **+7.3pp (GPT-5) / +10.4pp (GPT-5-mini)** on OSWorld at N=10 (62.6→69.9%); plateaus at N≈8–10 (RESEARCH 73→90 read #5).
- **Cost impact:** **~N× on the gated steps only** — the expensive lever. Buy selectively; the O(N) judge (cheap model) keeps selection cost linear, not N×full-eval. Ship **only after** L1–L6 and only if the scoreboard shows a residual irreversible-step failure worth the spend.
- **Code seam:** gate on `guarded_step.py:78` (`MUTATION_CTRL`); rollout+select wraps the actor loop in `webvoyager.py` (new, behind an env flag; off by default to protect $/task).

---

## 2. Locked cost-routing recipe (the cost-lock agent) — $/task math

**The tier map (code tier ≠ research tier — this mapping is the whole point).** The code has 5 rungs (`gateway.py:21-34`): `CHEAP, ACT, GROUND, SMART, ESCALATE`. SMART is the **mid-tier** planner/first-rescue (research "ESCALATE-1"); ESCALATE is the **capped frontier** (research "ESCALATE-2").

| Code tier | Locked model | $/Mtok (in/out) | SS-Pro | Role / % of steps |
|---|---|---|---|---|
| **CHEAP** | `qwen/qwen3-vl-8b-instruct` | $0.10 / $0.30 | 52.7 | non-actor cheap calls |
| **ACT** (per-step actor) | `qwen/qwen3-vl-8b-instruct` | $0.10 / $0.30 | 52.7 | **80–90% of steps** — the tier L4 reclaims |
| **GROUND** (pixel→coord) | `qwen/qwen3-vl-8b-instruct` (self-host `UI-Venus-1.5-8B` 68.4 at volume) | $0.10 / $0.30 | 52.7 (68.4) | crop/ambiguous grounding (L6) |
| **SMART** (plan/verify + 1st rescue) | `z-ai/glm-4.6v` (alt `qwen/qwen3-vl-235b-a22b`) | $0.30 / $0.90 | ~63–66 | `_plan`/`_replan`/`judge` + genuine stall |
| **ESCALATE** (capped frontier) | `anthropic/claude-opus-4-8` | ~$5 / $25 | 87.9 | **hard-capped 2/task**, deep-stall only |

**Gate:** default every step to ACT. Lone `forbid` → stays ACT. `sub_stuck>=2` → SMART (mid, not frontier). `sub_stuck>=3` → one capped ESCALATE. **Split** grounding (GROUND, never frontier) from planning (only the *plan* ever escalates). **Frontier cap = 2/task** (`gateway.py:136-166`, auto-degrades ESCALATE→SMART past cap).

**Env block (`.env.local`; prod source of truth):**
```
ANTICIPY_MODEL_ACT=qwen/qwen3-vl-8b-instruct
ANTICIPY_MODEL_GROUND=qwen/qwen3-vl-8b-instruct
ANTICIPY_MODEL_CHEAP=qwen/qwen3-vl-8b-instruct
ANTICIPY_MODEL_SMART=z-ai/glm-4.6v
ANTICIPY_MODEL_ESCALATE=anthropic/claude-opus-4-8
ANTICIPY_ESCALATE_CAP=2
ANTICIPY_VISION_MODE=auto
ANTICIPY_MAX_ANSWER_CHECKS=1
```

**Cache/compression (cost engineering):** keep the text prefix rock-stable, order `tool defs → system → reference docs → history → live query`, push volatile data (timestamps, session ids, working memory) to the **suffix**, append the screenshot **LAST** (image cache busts every step; the text KV cache must survive). Anthropic read discount 90%, break-even ~1.4 reuses → ~80% cut on the stable prefix. Downscale screenshots to 1280×800 before send (~5× cheaper/vision step).

**$/task envelope (~15 steps/task; ACT≈$0.0004, SMART≈$0.003, Opus≈$0.022):**

| Regime | escalation % | frontier calls | $/task | quality |
|---|---|---|---|---|
| All-frontier (Opus-solo) | 100% | ~15 | ~$0.33 | ceiling (uneconomic) |
| **Buggy actor today** (paid ladder) | ~45% | ~7 | **$0.12–0.16** | ceiling−2pt (the bleed) |
| **Cold** (post-fix, no cache) | ~35% | 1–2 | **$0.046–0.09** | within ~2pt |
| **Warm** (post-fix, cached + capped) | 10–15% | ~0.3 avg | **$0.016–0.025** ✅ | within ~2pt |
| **Warm pure-open** (0 Opus, L7 replay) | 10–15% → GLM only | 0 | **$0.008–0.012** | ~−2 to −4pt on hard stalls |
| ACT-only (no escalation) | 0% | 0 | ~$0.006 | **breaches 90%** — do NOT ship |

The entire gap from **$0.12 → $0.02** is (a) reclaiming the ~45% ACT steps (L4) and (b) escalating to GLM-4.6V **before** Opus behind the cap. Accuracy holds within **~2pt** of all-frontier while cutting cost up to 78% (Adaptive VLM Routing). The one config that *breaches* 90% is ACT-only — which is why the graded ladder **keeps** SMART on genuine stalls + one capped Opus rescue rather than removing escalation. L5's grounded validator and L8's routed BoN are the capability we spend that reclaimed budget on.

> **Honest note on the live env:** the *running* engine (`.env.local:107-108`) is on the Gemini free tier (`CHEAP=gemini-2.5-flash-lite`, `SMART=gemini-2.5-flash`, ACT/GROUND/ESCALATE **unset** → ACT silently falls back to flash-lite via `gateway.py:127`). On that env routine cost ≈ $0 and "45% frontier" is a **latency + quality + mis-accounting** problem, not a dollar bleed. The $0.12–0.16 bleed appears the moment you flip to the paid SOTA ladder above — which is exactly when L4 pays for itself.

---

## 3. Honest ceiling note — is 90% real, and on what distribution?

**Yes, conditionally — and only for Anticipy's actual distribution.**

- **Short-horizon, familiar/repeated single-site (Gmail/Calendar/a few known sites — Anticipy's real domain):** 90%+ is **genuinely attainable**, and the cheapest path is exactly L1 (DOM/set-of-marks grounding) + L3/L5 (read-back + checkpoint validator/replan) + L7 (recipe-replay) + L2/L6 (deterministic guards + cheap fusion), reserving L8 for irreversible steps. WebVoyager-class single-site is "solved for easy" (top tier 88–98%, though self-judged/gamed).

- **Live consumer single-site (Online-Mind2Web, 300 tasks/136 sites):** 90% is reached by a **couple** of heavily-engineered systems, but it is **judge-sensitive by 10–20 points** — the same class collapses under neutral human/WebJudge scoring (Navigator 78.7% human vs 64.7% auto; Claude 4.0 61% vs 47.7%). Honest median top-tier here is **~75–90%** and the number moves with the judge. Our browser_eval checkers are independent/state-grounded specifically to not be that soft judge.

- **Genuinely complex multi-site / long-horizon (the "frontier ≈ 45%" tasks):** **nobody hits 90% in 2026, and it's not close.** Strongest systems reach **~44.5%** on long-horizon multi-site; GAIA under neutral eval **~52%**; the real-world audit gap is **78%-benchmark → 22%-real**. The compounding math (`p_step^n`) forbids 90% on a 20-step multi-site task without a recovery loop that effectively re-rolls steps. **Every unseen site resets us from the easy regime toward the hard one.**

**Bottom line:** "~90%" in this plan means **~90% on complex-but-familiar, short-to-medium-horizon tasks on sites Anticipy repeats** — real and reachable with L1–L7. On **novel multi-site long-horizon**, the honest ceiling is **~45–55%**, and any "90%+" headline there is single-site, self-judged, or best-of-N-inflated. The target distribution is stated on the scoreboard, not assumed. The measured 8/11 today is a small board of exactly the familiar-site class where 90%+ is legitimate; the honesty risk is **letting the board stay easy** while claiming the number — which §4 guards against by growing the board with harder tasks and neutral checkers.

---

## 4. Build sequence — each step proved on the `browser_eval` scoreboard

The proof harness already exists: **`engine/scripts/browser_eval.py`** — the un-gameable browser scoreboard. Its invariant is the one the research demands: **no task grades the agent's own "done"** — every task under `final/tests/browser/tasks/<id>/` ships a `checker.py` that independently re-reads the result (server echo / backend `/last` / fresh page fetch), never the model's self-report. It reports **pass-rate · $/task · $/successful-task · steps · tier-mix (frontier% = SMART-model share, vision%, region%, replay%)**, and has a `--selftest` dry mode that proves every checker passes a real result and **fails a faked one** before any live run.

**Ground rule:** every step below lands **red→green on the scoreboard**, with the tier-mix and $/task printed. A step that doesn't move its target checker green, or that regresses $/task, doesn't ship. Never contend for the one real tab while a build agent is running — use `--selftest` for structural work, then one gated live run.

| Step | Lever | Add to `browser_eval` (task + independent checker) | Green when | Guardrail |
|---|---|---|---|---|
| **S0** | baseline | Run `browser_eval.py --selftest`, then one live pass over the current 4 bundles + the 11-task live set. Record 8/11, frontier%, $/task. | selftest GREEN; baseline logged | — |
| **S1** | **L1** | `select_dropdown/` — the-internet dropdown; checker independently reads the `<select>.value` = "Option 2". | fail #2 → PASS | no new full-frame; $/task flat/down |
| **S2** | **L2** | `search_results/` — demowebshop "computer"; checker asserts the results page (not homepage) and a product name present. | fail #5 → PASS | give-up guard fires only on real no-answer |
| **S3** | **L3** | `cart_add/` — saucedemo add Backpack; checker fetches `/cart.html`-equivalent state, asserts item+qty. | fail #4 → PASS | proof re-reads cart, not same page |
| **S4** | **L4** | Re-run S0–S3 with the paid ladder wired (§2 env). Assert tier-mix `frontier% ≤ 15` and `$/task ≤ 0.025` (warm) with **no** pass regression. | frontier 45%→≤15%, $/task→~$0.02 | quality within ~2pt (pass-rate holds) |
| **S5** | **L5** | Add 2–3 **multi-step complex** bundles (2+ subgoals) with independent checkers; enable checkpoint-validator + `MAX_ANSWER_CHECKS=1`. | complex-task pass-rate up; steps down | replan doesn't regress easy tasks |
| **S6** | **L6** | Fix `shot=null`; flip `VISION_MODE=auto`; add one canvas/no-DOM widget bundle. Assert `vision% > 0`, `region% > 0`. | vision 0%→>0, region>0 | ~5× cheaper vision step |
| **S7** | **L7** | Re-run a repeated-site bundle twice; assert `replay% > 0` on run 2 and `$/task` collapses toward ~$0. | replay fires; warm $/task → ~$0.01 | replay invalidates on page change |
| **S8** | **L8** | *(only if S3/S5 show a residual irreversible-step failure)* gate routed BoN on `MUTATION_CTRL` steps; assert the residual fail → PASS at bounded $/task. | residual → PASS | BoN off by default; $/task capped |

**Definition of done for this plan:** scoreboard shows **≥90% pass-rate on the familiar-site board (grown to ≥15 tasks incl. S5's complex bundles), `frontier% ≤ 15`, warm `$/task ≤ $0.025`, all checkers independent/state-grounded, `--selftest` GREEN** — with the honest-ceiling caveat (§3) recorded next to the number: this is 90% on the familiar/repeated distribution, not on novel multi-site long-horizon.

---

**Primary files (all verified 2026-07-03):**
`engine/anticipy_engine/agent/webvoyager.py` (L1 824/1920; L2 538/548; L3 838/824; L4 1350-1351/1866; L5 81/1009/1543/1866; L6 239/635/678) ·
`extension/background.js` (L1 628; L2 1031/1046/1057; L6 503-510) ·
`engine/anticipy_engine/core/gateway.py` (L4 37/123-132/136-166; L6 128) ·
`engine/anticipy_engine/agent/guarded_step.py` (L3/L8 78) ·
`engine/anticipy_engine/agent/recipes.py`, `skills.py` (L7) ·
`.env.local` (§2 env block) ·
`engine/scripts/browser_eval.py` + `final/tests/browser/tasks/` (§4 proof harness).
