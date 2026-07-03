# final/browser/PLAN.md — THE MASTER BUILD-TO-DONE PLAN for the Anticipy browser agent

> **Status:** canonical build plan for "the hands." Supersedes the old `final/browser/README.md`
> sketch (screenshot-first + per-action small-model voting on top of browser-use). Two things in
> that sketch are **explicitly reversed** here: (a) there is **no per-step voting** (dead on strong
> models), and (b) **browser-use is NOT the hand** — the MV3 `chrome.debugger` extension is. This
> plan sits under `CANON/04_DEFINITION_OF_DONE.md` (the investor walkthrough is the product bar) and
> extends, not replaces, the HoE analysis in `CANON/BROWSER_PLAN.md`.
>
> **Ground truth trunk:** `~/Anticipy-devin`, branch `hoe/build`. Live receipt of the current hand:
> `docs/guarantee/proof/F_browser.json` (real cart-prep, 7 steps, 208KB screenshot, guards proven).
> Un-gameable grader already exists: `overnight/harness.py` + `overnight/done_gate.py`.

---

## 0. THE DECISION IN ONE PARAGRAPH

**One orchestrator drives. Five roles, not five agents — and four of the five are deterministic
code.** Only the PLANNER and ACTOR ever spend an LLM call; only the PLANNER (and rare tier-3
rescue) ever spends the frontier model. It is a **hierarchical single-writer loop** on the user's
**real, logged-in Chrome**, driven through the MV3 extension's trusted `chrome.debugger`/CDP input —
never a swarm (a swarm on one live tab produces context-collapse and hallucination-cascade), never
DOM-only (blind on canvas/Sheets/non-WCAG), never screenshot-only (loses stable refs + safety
labels). Perception is a **hybrid**: a distilled DOM/accessibility Set-of-Marks index is the default
planning substrate, and **real pixels (region-cropped, then full) are first-class at the escalation
tiers** — that is the fix for the 2026-07-02 "set-of-marks is wrong" objection: SoM text is the
cheap default, not the only lane. Every single action passes through a mandatory
**verify-and-recover cell** whose admission signal is a **deterministic read-back on real world
state, never the model grading itself.** Every externally-verified success is **lifted into a
parameterized, admission-gated skill** so the same flow is ~$0 next time; every novel failure becomes
a **permanent new recovery handler**. Cost lands at **~$0.02–0.03/task cold, ~$0.002–0.008 warm**
(≈15–200× under Opus-in-Chrome), gated on money/irreversible actions with an **ask-first** pause →
text-the-user → resume. **Do not rewrite `webvoyager.py`; do not rebuild the actor on browser-use.**
Refactor `webvoyager.py`'s tangled implicit loop into these five named roles, land the deterministic
guard, graft the DEV-FINAL escalation router + humanlike motion + VLM verifier, and let the
un-gameable eval — not any camp's opinion — decide every deeper swap.

This resolves the live **Nick-vs-HoE conflict** (HoE "keep webvoyager," Nick "replace with
browser-use," Omar "set-of-marks is wrong") as **neither pure keep nor pure replace**: keep the
orchestrator skeleton, stop treating it as a monolith, make vision first-class, and let numbers rule.

---

## 1. THE DECIDED ARCHITECTURE — WHO DRIVES

### 1.1 Five roles, one hard rule

| Role | What it owns | LLM? | Model tier | Real code today |
|---|---|---|---|---|
| **PLANNER** | The task, the subgoal list, and re-planning. Strategic only. | Yes | SMART (frontier), rare | `webvoyager.py` `_plan`/`_replan` |
| **SKILL-FETCHER** | Look up a learned per-host recipe/skill; propose a replay. Pure lookup+match. | **No** | — | `agent/recipes.py` (`recipe_key`, `match_index`) |
| **ACTOR** | Turn *one* subgoal into *one* concrete page action. Tactical only. | Yes | CHEAP → escalate | `webvoyager.py` `_think`/`_act` |
| **VERIFIER/CRITIC** | Did the world actually change as intended? Deterministic read-back first, VLM tie-break, judge last. | Mostly **No** | det. → CHEAP → SMART | `webvoyager.py` `_sig`, `agent/proof.py`, `_verify_answer` |
| **GUARD / ESCALATOR** | The router + safety firewall + recovery ladder + human gate. Pure code. | **No** | — | `core/navwall.py` + (land) `action_guard.py` + (graft) `vision_router.py` |

**THE HARD RULE — single writer.** Exactly one ACTOR owns the one live tab-group for the lifetime of
one task. No role other than the ACTOR may emit an `act` envelope. PLANNER/VERIFIER/GUARD/
SKILL-FETCHER may only *read* the shared state and *write plan/label/verdict fields*. Parallelism is
allowed **only** for read-only research fan-out on a throwaway Chromium (`hands/browser_use_link.py`),
never on the user's session. A live browser session is single-threaded mutable state; exactly one
writer may touch it.

### 1.2 The shared state contract — one orchestrator-owned blackboard

Generalize today's scattered `TaskState` + `history` + `committed` locals in `webvoyager.py` into one
explicit `RunState` object the orchestrator owns; every role reads it, only the orchestrator commits
writes. **Only two fields ever come from an LLM's mouth** (`subgoals`, the ACTOR's chosen `action`).
**Every control field is computed by code from environment signal** — that single discipline is what
makes the loop both cheap and reliable.

```jsonc
RunState = {
  run_id, user_id, task, start_url,
  subgoals: [ "...", "STOP before pay → ask" ],   // PLANNER, revisable
  cursor: 2,                                        // current subgoal
  committed_target: {idx, descriptor} | null,      // COMMIT: don't re-pick the same target
  step: 7, last_sig: "url|title|els_hash|scrollY",  // _sig(): the change detector
  label: "PROGRESS|NO_CHANGE|REGRESSION",           // CODE-computed, never model-claimed
  sub_stuck: 0, churn: 3, no_progress_streak: 1,    // deterministic recovery signals
  action_hashes: { "click:14:": 1 },                // loop detector
  tier: "tier1",                                    // escalation router output
  budgets: { steps_left, wall_s_left, frontier_calls_left: 4, nav_blocks: 0 },
  recipe: {key, hit, step_ptr} | null,              // SKILL-FETCHER
  breadcrumbs: [ {step, postcondition, verified, idem_key} ],  // HANSEL trail
  obs, verdict, resume_token,
  status: "RUNNING|ASK_USER|DONE|FAILED"
}
```

### 1.3 The wire contract (already real — keep it)

Three message shapes over the authenticated WebSocket (`core/browser_link.py` ↔
`extension/background.js`):

- **Down:** `{type:"browse_job", id, intent:"observe"|"act"|"crop", url?, action?}`
- **OBSERVATION up** (`doObserve`): `{url, title, text(≤16k), elements:[{idx,role,name,type}], scrollY, scrollMax, proof:{screenshot?}}` — DOM-first Set-of-Marks index + text, **screenshot pulled only when a tier needs pixels**. ~90% of steps never pay a screenshot token.
- **ACTION down** (the ACTOR's only verb): `{action:"click|type|select|check|scroll|navigate|back", idx, text?, enter?}`. `type` clears-then-inserts and **re-reads `.value`** in `doAct` → the read-back the VERIFIER needs is a free byproduct.

### 1.4 The main loop — the fixed guarded step (who does what, in order)

Replace the implicit `plan → act → act …` with this **9-phase guarded step**. Phases marked **[code]**
are zero-LLM. Only phase 1 (transport), phase 6 (one bounded ACT call), and the rare
SMART plan/replan cost anything.

```
run(task, start_url):
  PLANNER:      subgoals = replay_hint ? cached : SMART._plan(task)        # once
  SKILL-FETCH:  recipe   = RecipeStore.get(recipe_key(task,start_url))     # once
  for step in range(max_steps=28):
    (1) OBSERVE       ACTOR→hand: observe_ready()  → OBSERVATION
    (2) LABEL   [code] GUARD: label = diff(last_sig, obs.sig); update stuck/streak/churn/hashes
    (3) WALL    [code] GUARD: classify_wall(obs.text) → login/captcha/2FA/paywall → HANDOFF (§4.5)
    (4) DONE    [code] GUARD: subgoal postcondition met? → advance cursor / task done?
    (5) ROUTE   [code] ESCALATOR: tier = vision_router.decide_tier(RunState)   # tier0..3
    (6) PROPOSE       tier0→SKILL-FETCH replay (no LLM) | tier1→ACTOR(CHEAP,text) |
                      tier2→ACTOR(CHEAP,+doCrop ROI) | tier3→ACTOR(SMART,full shot) | recovery
    (7) PRE-GATE [code] GUARD: action_guard.classify(action,obs) BEFORE side-effect →
                      money/credential/irreversible/off-domain → BLOCK or HANDOFF
    (8) ACT           ACTOR→hand: act(action)   (trusted CDP + humanlike motion)
    (9) VERIFY  [code+] VERIFIER: read-back postcondition on REAL DOM (not self-grade)
                      pass → breadcrumb + commit sig + advance ; fail → RECOVERY LADDER (§4.3)
```

### 1.5 Voting / escalation policy (decisive)

- **NO per-step voting, ever.** Self-consistency is near-dead on strong models (+0.4% HotpotQA /
  +1.6% MATH at 20 samples) and cost scales linearly. This is why the old README's "2–3 models vote
  every action" is scrapped.
- **Escalate exactly one tier per failure signal** (tier0→1→2→3); never jump to frontier on a single
  cheap wobble. Test-time compute is spent on **re-planning and verification**, not on ensembling
  clicks (WebDART: dynamic replan lifted Shopping 18.8%→26.5% *while cutting* steps 32.9→18.2).
- **Best-of-N (N=3, verifier-selected) is permitted in exactly ONE place:** the final-answer JUDGE or
  a single high-blast-radius decision, and **only** when the judge's first pass is low-confidence.
- **The LLM plans; it can never override a code guard.** Page text is untrusted data (prompt-injection
  firewall).

---

## 2. KEEP vs SCRAP (decisive — from the machine-wide audit)

### 2.1 KEEP — the foundation (all on `~/Anticipy-devin` `hoe/build`)

| Component | Path | Why it stays |
|---|---|---|
| **Brain / orchestrator loop** | `engine/anticipy_engine/agent/webvoyager.py` | Already *is* the recommended architecture (SoM + vision-on-demand, PROGRESS/NO_CHANGE/REGRESSION, COMMIT, replanning, anti-loop, budgets). **Refactor into the 5 named roles over `RunState`; do NOT rewrite.** |
| **Hand (the moat)** | `extension/background.js`, `extension/manifest.json` | MV3 `chrome.debugger` CDP: trusted `Input.dispatch*`, `Page.captureScreenshot` on backgrounded tabs, `Storage.clearDataForOrigin`, JS-dialog auto-handle, isolated Anticipy tab-group, `doObserve`/`doAct`/`doCrop`. The only production-grade trusted-input hand on the machine. |
| **Transport** | `core/browser_link.py` | Authenticated WS (`/ws/token`→`/ws/extension`), heartbeat + auto-reconnect, `chrome.storage`-persisted state. |
| **Worker** | `hands/browser_hand.py` | Routes `browse_task`/`read_page`/`prepare_form`; refuses success without a screenshot; `prepare_form` never submits. |
| **Skill/recipe cache** | `agent/recipes.py` | Voyager-lite: verified-PROGRESS trace, stable descriptors, replay-with-self-heal. Evolve (§4.6), don't replace. |
| **Read-back proof** | `agent/proof.py` (`confirm_stable_artifact`) | Delayed repeated read-back = the only completion proof. This is the un-gameable seam. |
| **Wall handoff + resume** | `agent/handoff.py`, `agent/resume_store.py` | `classify_wall` → captcha/mfa/login/block; pause→ask→resume checkpointing. |
| **Nav gate** | `core/navwall.py` | `nav_block_reason`, sensitive-host gate. |
| **Read-only research arm** | `hands/browser_use_link.py`, `browser_use_runner.py`, `engine/.bu-venv` (browser-use 0.13.1) | The **only** sanctioned second-context / parallel path (throwaway Chromium, SSRF + money/login guards). A/B baseline for the eval. **Never the actor.** |
| **Artifact + creds** | `hands/make_artifact.py`, `hands/token_vault.py` | Real-artifact creation; encrypted per-site credential storage. |
| **Un-gameable grader** | `overnight/harness.py`, `overnight/done_gate.py`, `final/tests/context_eval.py` | The scoreboard is reconciled into `browser_eval.py` (§7). |

### 2.2 SALVAGE-GRAFT — surgical ports into the KEEP foundation

From `~/Developer/Anticipy-DEV-FINAL/engine/app/`:

| Port | From | Into |
|---|---|---|
| **Humanlike motion** (Bezier + Gaussian) | `action_engine/humanlike.py` | the extension's `cdpClick`/`cdpType` — trusted **and** human-timed input |
| **4-tier escalation router** | `action_engine/vision_router.py` + `vision_image_prep.py` | phase 5 `decide_tier` + ROI-crop token math |
| **VLM tie-break verifier** | `action_engine/vision_verifier.py` | VERIFIER layer 2 (canvas/SPA where DOM sig is blind) |
| **Cold-start inhale** | `coldstart/cdp_walker.py`, `coldstart/auto_inhale.py` | background-tab row scraper for profile bootstrap |

From `origin/nick-sevostiyanov-demo/site:ai-guidance/browser-agent/`:

| Land NOW | To | Note |
|---|---|---|
| **`action_guard.py`** (deterministic money/credential/irreversible/captcha classifier, 15/15, pure-stdlib, approach-agnostic) | `engine/anticipy_engine/hands/action_guard.py` | Unifies today's scattered regex guards. **Build-timing caveat:** per Omar 2026-07-02 the deeper safety-gating PASS is deferred — land the module + tests + wire behind a flag, keep the existing `PURCHASE_GUARD`/`navwall` floor, do **not** rip-and-replace gates now. |

### 2.3 SCRAP — decisively (Omar doesn't care which)

- `~/Anticipy` and `~/Desktop/Anticipy-executor-working` (symlink) — predecessor mirror of devin; **diff/history only**, not a build target.
- `~/Desktop/Anticipy-Browser-Hand` **==** `~/.anticipy/extension/anticipy-v6` (byte-identical, 824-line `background.js`) — synthetic content-script `.click()`/`dispatchEvent`, **0 `chrome.debugger`**; untrusted events real sites reject. Self-labeled archived. **Scrap.**
- `~/.anticipy-extension-graveyard-20260624/*`, the v4/336-line skeleton, the "Anticipy Core" service-worker, Omar-System-Test — old messaging/synthetic, 0 CDP, 0 SoM. **Scrap.**
- `hands/api_hand.py` — the per-service API arm Omar killed (the dentist/calendar-spam source). **Deprioritize/scrap from the browser path** (browser-only invariant).
- Nick's stranded `engine-checkout/` webvoyager + `ai-guidance/browser-agent/engine-port/vision_agent.py` — do **not** keep three actor loops alive. Its good ideas (mandatory-vision, cheap planner) fold into the `webvoyager.py` refactor; the loop itself is **scrapped as a parallel path.**
- The old `final/browser/README.md` plan (per-step voting + browser-use-as-hand). **Superseded by this file.**

---

## 3. PERCEPTION + MODEL ROUTING (cost-optimal, ~1/15)

### 3.1 Perception — layered hybrid (NOT DOM-only, NOT pixel-only)

- **Layer 0 — element index (primary planning substrate):** distilled AX-tree + compressed DOM as a
  Set-of-Marks index (stable `idx`, role, name, type). One cheap, cacheable request gives full-page
  semantic context (nav/forms/dialogs/errors) and is **where safety policy is enforced** (block by
  label). This is what the PLANNER reasons over.
- **Layer 1 — pixel grounding (execution surface):** every actual click/coordinate can go through a
  screenshot when the DOM index is insufficient. **Mandatory** for canvas/PDF/game/non-WCAG surfaces
  (Sheets, Figma, Canva). Fed a **region crop (`doCrop`) first, full frame only at tier3**, downscaled
  to the grounder's native resolution — the single biggest cost lever (a naive 4K shot ≈ 16k tokens).
- **Layer 2 — Set-of-Marks bridge:** when the index enumerates the target, the ACTOR picks an `idx`
  (cheaper + more reliable than free coordinates). Fall back to raw grounding only when enumeration
  misses (custom widgets).
- **Layer 3 — VLM validator:** a small VLM reads the *post-action* screenshot to confirm the click
  landed (`vision_verifier.py`), closing the loop before advancing.

### 3.2 Model routing — the five-tier stack

| Tier | Role | Exact model | $/Mtok in/out | Host | Fires |
|---|---|---|---|---|---|
| **T0 search/read** | look up a fact / read a public page — no browser | search API (Brave/Serper) + **`claude-haiku-4-5`** extractor | ~$0.003/query; $1/$5 | API | every READ intent first |
| **T1 planner** | step reasoning over AX-tree text; READ-vs-ACT; next subgoal | **Qwen3-VL 235B-A22B Instruct** | **$0.20 / $0.88** | API (DeepInfra→Together) | every "what next" |
| **T2 grounder** | screenshot → click/type coords | **UI-TARS-1.5-7B** default; **GUI-Actor-7B** for dense pro UIs | **$0.10 / $0.20** | API (DeepInfra/OpenRouter); Modal L40S only above break-even | every UI action needing pixels |
| **T3 escalation** | hard grounding / ambiguous plan the cheap tiers failed | **`claude-opus-4-8`** (#1 ScreenSpot-Pro 0.879) | **$5 / $25** | API (1P) | on failure/low-conf only, **capped ≤2/task** |
| **T4 recipe-replay** | deterministic replay of a known flow | — (no VLM) | ~$0 | local (extension/CDP) | screen/DOM matches a cached cassette |

**Why the split, not one model:** UI-TARS-7B is an elite *grounder* (91.6 ScreenSpot-v2) but a weak
*planner* (24.6 OSWorld vs Opus ~72.7); Qwen3-VL is the inverse. Two cheap specialists + rare frontier
rescue reaches open-SOTA class at ~1/20–1/30 of Opus.

**Pragmatic bridge (Phase 0, zero new infra):** the gateway (`core/gateway.py`) already reads an
OpenRouter key; start ACT on an already-wired cheap VLM (e.g. Qwen via OpenRouter) and escalate to
Claude, then migrate to the exact split above once the eval baseline exists. Today's cost bug: the
per-step `agent` caller is in `SMART_CALLERS`, so **every act step runs on the frontier model** — the
first routing fix is to introduce the ACT tier and reserve SMART for escalation.

### 3.3 The router (READ/ACT × tier ladder) and cost envelope

```
for each subgoal:
  intent = T1.classify(subgoal)                 # READ | ACT
  if READ:  T0.search→extract → if confident continue
            shadow_api_read (site's own XHR, captured live via CDP) → if confident continue
            else fall through to the hand as read-of-last-resort
  if ACT:   if T4.cassette_hit(screen_hash): replay; verify_or_fallback; continue
            plan  = T1.next_action(ax_tree, history)      # text-mostly, NO pixels to planner
            click = T2.ground(screenshot, plan.target)    # only T2 eats screenshot tokens
            if click.conf < τ or post_check_failed:
               escalate += 1
               if escalate <= 2: click = T3.opus(hi_res, plan)   # HARD CAP
               else: pause_and_text_user("stuck on <step> — take over?")
            if is_irreversible(plan): require_user_confirmation(...)   # ask-first
            execute_via_CDP(click)
```

**Locked $/task (20-step):** split (T1 plan + T2 ground) ≈ **$0.013**; + rare T3 escalation ≈
**$0.02–0.03 cold**; + T4 replay on known flows ≈ **$0.002–0.008 warm**. Both clear the 1/15
(~$0.028) bar; warm clears it 5–100×. **Uncapped escalation is the only thing that silently reinflates
cost toward Opus-solo — hence the ≤2 cap.**

**Mandatory cost controls:** prefix/prompt caching on the system prompt + tool schema (cache reads
0.1×); conversation compression (keep last ~40 actions verbatim, summarize older → tokens stabilize
~12.6k instead of growing past 43k); `doCrop` ROI over full frames; AX-tree to the planner, pixels
only to the grounder.

### 3.4 Build vs buy / hosting (decided)

- **BUY via API by default.** UI-TARS at $0.10/Mtok in is cheaper than its own GPU-seconds below very
  high utilization.
- **Self-host only the T2 grounder** on **Modal L40S ($1.95/hr, per-second, scale-to-zero)** and
  **only** above sustained **~30–50M grounder tokens/day** (thousands of concurrent tasks). Never
  self-host Opus or the 235B planner — the H100/H200 idle burn never pays back at product volume.
- **LoRA later, conditionally:** fine-tune a Qwen2.5-VL-7B / Qwen3-VL-8B grounder on OS-Genesis/
  AgentTrek-synthesized trajectories of *Anticipy's own* recurring flows (~$3–4k all-in via Fireworks)
  **only when** the eval's per-surface ScreenSpot slice shows T2 chronically missing *your* UIs from
  real failure logs, and that surface is narrow/stable. It is the last optimization, not the first.

**Cost KPI that ties to the eval:** **hand-launch-rate / tier-mix** — the fraction of steps that reach
T2 (pixels) and T3 (Opus). It is simultaneously the cost driver and the flakiness driver; the eval
reports it first-class and a success-rate that rises while tier-mix shifts toward T3 is **flagged, not
celebrated.**

---

## 4. THE CONTINGENCY SYSTEM (1000 failure modes → recovery) + SKILL-ACQUIRE-BEFORE-TASK

**The reframe:** the agent doesn't get dumber at step 8 of 12 — 0.95¹⁰ ≈ 0.60, and there is *no
natural recovery loop*. 34.2% of actions are silent no-ops the agent believes worked; execution/
grounding (not planning) is the bottleneck (perfect human plans still hit only 36.4%). **The missing
primitive is a per-action verify-and-recover cell.** System 1 (below) is that cell; System 2 makes
every verified pass cheaper and every novel failure a permanent handler.

### 4.1 The guarded-step cell (the keystone — mandatory on every action)

Extract the cell into one function (`engine/anticipy_engine/agent/guarded_step.py`) so **no action can
skip read-back**:

```
A0 PRE_GATE   [code, 0 LLM]  navwall + blast_radius risk + schema/scope; reject/pause before side-effect
A1 WAIT_READY [code]         wait on element present+visible+enabled+stable / net-idle — NEVER fixed sleep
A2 INTERRUPT_SCAN [code]     out-of-band scan for wall/modal/CAPTCHA/429/login BEFORE trusting the action
A3 ACT        [trusted CDP]  emit → extension executes (idempotency-keyed)
A4 READBACK_VERIFY [code+VLM] assert the world changed as intended — NEVER self-grade
A5 COMMIT     [code]         breadcrumb + reset ladder + advance   |  else → RECOVERY LADDER
```

### 4.2 READBACK_VERIFY — external verification (the anti-self-grading core)

Verification is **deterministic code + a separate grounder VLM**, never the acting model (audits: 90/
100 self-reflections rubber-stamp; +13–29pp from replacing self-critique with a deterministic check).
Three layers, cheapest first:

1. **State delta [code]:** `post_sig = _sig(out)` → PROGRESS/NO_CHANGE/REGRESSION off URL/DOM/scroll/
   text. Catches the **34.2% no-op** class.
2. **Typed-field read-back [code]:** after type/write, **re-read `.value` == intent**; after submit,
   assert a success token appeared. Catches the **silent-write** class (the most dangerous — it looks
   exactly like success).
3. **Validator VLM [grounder]:** UI-VQA on the post-action screenshot for canvas/non-WCAG surfaces
   where the DOM sig is blind (`vision_verifier.py`).

For irreversible artifacts (draft/cart/event), verification = `confirm_stable_artifact` (delayed
*repeated* read-back). **This is the same seam that gates skill admission (§4.7).**

### 4.3 The recovery ladder (cheapest first; resets on any PROGRESS)

| L | State | Trigger | LLM | Remedy |
|---|---|---|---|---|
| **L0** | deterministic reroute | NO_CHANGE, exec error, dedup hit, dismissible modal | **0** | switch modality (click→keyboard/scroll/zoom/other element); dismiss canonical modal then resume; mark failed edge |
| **L1** | tactical retry | transient: empty obs, 429/Cloudflare, spinner, stale ref | 0 | exponential backoff + jitter; re-observe; **do not retry into a ban** |
| **L2** | reflect + replan | 2 consecutive NO_CHANGE/REGRESSION, or circling | 1 (escalate to Opus **only here**) | brief why-failed → NEW 2–5 step plan *from the reached page* |
| **L3** | decompose / backtrack | replan didn't move; subgoal too coarse | 1–N (best-of-N 3–16, verifier-selected — **only here**) | restore checkpoint; split subgoal; try alternate branch |
| **L4** | human gate | unresolved wall, must-ask risk, or L3 exhausted | 0 | **pause → text user (Twilio) → resume** with full context + the specific artifact |
| **L5** | honest abandon | budget/step cap with no path | 0 | best-effort read-back answer + honest report; **never fake success** |

**L4 is a feature, not a cop-out — a paused task is NOT a completed task.** It resumes and finishes, or
it is L5. "Handoff = success" is a lie the metrics tell you.

### 4.4 The nine contingency classes (detector → handler → resume)

| # | Class | Detector [code] | Handler | Rung |
|---|---|---|---|---|
| 1 | silent no-op / dynamic content | `_sig` unchanged after act | wait-on-condition, re-observe, switch modality | L0 |
| 2 | loop / repeat | action-hash `(tool,args,descriptor)` 3-strike | forbid + STUCK note → reflect | L0→L2 |
| 3 | hallucinated click / off-site drift | target not in fresh obs; domain off allowlist | reject at A0; re-ground on live DOM | L0 |
| 4 | modal / cookie / paywall / A-B overlay | overlay detector (7 canonical types) | dismiss → **resume planned trajectory** | L0 |
| 5 | CAPTCHA | `BLOCK_MARKERS` ("unusual traffic") | **pause → text → resume** (never auto-solve) | L4 |
| 6 | login / session expiry | `classify_wall`→login; `navwall` sensitive-host | pause → text (real logged-in session inherited first) | L4 |
| 7 | 2FA / MFA / OTP | `classify_wall`→mfa; OTP regex | pause → text (never read the user's codes) | L4 |
| 8 | rate-limit / Cloudflare | HTTP 429 / JS-challenge | backoff + escalate path; **not** retry-into-ban | L1 |
| 9 | silent-write failure | field `.value` ≠ intent on read-back | circuit-break on *quality* not HTTP-200; re-type | L0→L1 |

**Anticipy's structural advantage:** the hand runs on the user's **real, already-logged-in Chrome**
(browser-only, extension dialing out — not the Arcade/API arm), so walls #5–7 are rare and the correct
default is always pause→text, never evasion (also ToS-safe and injection-safe). The ~40% infra-failure
floor is unbeatable by reasoning; the mitigation is the real profile + human handoff.

### 4.5 Risk-tiered human gate (blast-radius, NOT confidence)

`blast_radius(action)` gates on *what the action does*, never on model confidence ("90% sure about a
read is fine; 90% sure about deleting must ask"):

| Tier | Anticipy examples | Policy |
|---|---|---|
| READ_ONLY | search, read thread, list events | auto |
| REVERSIBLE | open a draft, add to cart, apply a filter | auto |
| COMPENSATABLE | archive, label, move file | auto + saga undo registered |
| **MUST_ASK** | **send email, checkout, calendar-create, wire, print** | **pause → text → resume; surface the *specific* artifact** ("okay to send this draft?" with the actual body / line items) |

**Checkpoint + idempotency footgun:** checkpoint at every subgoal boundary and before every pause
(`resume_store.put`, per-user Supabase in cloud). On resume, code *before* the interrupt re-runs — so
every MUST_ASK action carries an `idem_key` persisted in the breadcrumb; on resume, if the breadcrumb
shows it fired, A3 is a **no-op** (no double-send/charge/print), and A4 confirms the artifact from the
prior run. **Never place a send/pay/print before a checkpoint** (the gate enforces checkpoint-after-ask
by construction).

> **Build-timing caveat (honors CLAUDE.md + the 2026-07-02 note):** this gate is *designed* here; the
> deeper safety-gating PASS is deferred to a final manual pass. The existing `PURCHASE_GUARD` + must-ask
> on send/checkout are the current floor. Land `action_guard.py` as a tested module behind a flag; don't
> build new gates into the trunk now.

### 4.6 Detectors & budgets (deterministic, mostly already present)

action-hash dedup (1→forbid, 3→fail subgoal); no-change run (2→L2); nav blocks (`MAX_NAV_BLOCKS=3`);
step caps (`max_steps=28`, `per_subgoal=8`); **$/token/wall-clock budget** (ceiling→L5); **frontier-call
budget (≈4/run)**; **hand-launch-rate** KPI.

### 4.7 Skills: acquire-before-task, no hardcoding, no context rot

`recipes.py` is already Voyager-lite (verified trace, stable descriptors, replay-with-self-heal). Four
gaps, each with the fix:

**Representation — Anthropic Agent-Skills directory** (drops into any Claude runtime *and* stays runnable
by the extension executor), stored per-user in Supabase + a curated global generic tier:
```
skills/<skill-id>/
  SKILL.md      # YAML: name, description(=retrieval key, ONLY thing resident at startup),
                #       params[typed slots], preconditions, site_tags, tier: site|generic,
                #       version, success_metric(=verify contract), usage_count, success_rate
  steps.json    # L2: parameterized action-trace — stable descriptors + TYPED PARAM SLOTS, NO literals
  verify.py     # L2: deterministic post-condition = admission gate AND runtime read-back contract
  examples.jsonl# L3: 1–3 parameterized traces, loaded on demand only
```

1. **LIFT (acquire, on a *verified* success):** parameterize concretes → typed slots
   (`{recipient},{product},{amount}`); decompose into sub-routines (open→find→act→confirm), not a
   monolith; **reject any candidate with a hardcoded selector/ID/value** → force into a param or a
   `locate()` helper. (This keeps the anti-cheat grep clean: the skill bank is *data*, not site-specific
   trunk code.)
2. **ADMIT (the whole ballgame — CI for skills):** admit only through a deterministic external harness —
   **correctness** (re-execute → `verify.py` passes on real world state), **usage** (invoked,
   non-trivial), **validity** (every action causes a real state change), **held-out** (passes 2–5 sibling
   tasks). Curated skills = +16.2pp; blind self-generated = −1.3pp. Quarantine → shadow → promote;
   versioned, never hard-deleted. The **global generic tier accepts only skills that passed held-out AND
   contain zero user data** (blocks the ~1,200-malicious-skill supply-chain surface).
3. **REUSE (skills-BEFORE-task retrieval — beats context rot):** embed task intent → top-k skill
   *descriptions* (L1 only) → **hard rerank (precision ≫ recall; even one distractor degrades)** → load
   full body for the **1–3** survivors → site-tagged first, generic fallback → replay via `match_index`
   (self-heals to the live loop on divergence, ~$0). Cap active skills per turn; resident context = task
   + last-3 reflections + 1–3 active bodies.
4. **GENERALIZE + LIFECYCLE:** two tiers (site-specific + generic like `fill_labeled_field`,
   `dismiss_modal`, `compose_and_confirm`); **refine-on-failure is first-class** (a generic that fails on
   a new site branches a site-specialized version, never overwrites). Periodic deterministic curator
   (non-LLM) does **delta updates, not full rewrites** (an LLM rewrite collapsed 18,282→122 tokens),
   embedding-dedup merge, and usage/success-rate pruning.

### 4.8 The flywheel (why this is anti-fragile)

Every **verified success** → lifted + gated → reusable skill → same flow ~$0 next time (drives
hand-launch-rate down). Every **novel failure** (new modal/consent/wall) → handled once by the ladder →
logged as a breadcrumb → promoted to a generic micro-skill → recovers ≥90% next time. **One un-gameable
seam gates both:** admission and task-done are the *same* functional read-back on real world state —
never self-grading. That is the single defense against an eval/skill-bank that lies (the "proxies fooled
us 7M×" lesson), and it is literally the R1→R2→R3 live-readback discipline, mechanized.

---

## 5. HOW IT DRIVES THE USER'S REAL CHROME (extension + exact wiring)

### 5.1 Why this shape wins (the load-bearing fact)

CDP `Input.dispatchMouseEvent` / `dispatchKeyEvent` inject at the browser input pipeline → events carry
**`isTrusted=true`**, indistinguishable from a human. JS `dispatchEvent()`/`.click()` are permanently
`isTrusted=false` (this is why the synthetic-click extensions are scrapped). `chrome.debugger` is
essentially the **only** way an extension emits trusted events. The two "obvious" alternatives are dead
or dangerous for the real profile:
- **remote-debugging-port attach** (Playwright `connectOverCDP`) — since Chrome 136 the port is ignored
  on the default user-data-dir; it forces a *separate, logged-out* profile. Rejected.
- **native-messaging to reach cookies/session** — the exact 2026 malware pattern. Rejected for creds.

### 5.2 The wiring (end to end)

```
 cloud engine (Railway / local :8787)                      user's real Chrome
 ┌──────────────────────────────┐        WS (authenticated) ┌───────────────────────────────┐
 │ webvoyager.py (5 roles)      │  browse_job(observe/act)  │ background.js (MV3 service      │
 │  └ core/browser_link.py  ────┼──────────────────────────▶│ worker)                         │
 │     /ws/token → /ws/extension│◀─────────────────────────┤  chrome.debugger.attach(tabId)  │
 │     token=…                  │  OBSERVATION / result     │  Input.dispatch*  (isTrusted!)  │
 │ hands/browser_hand.py worker │                           │  Page.captureScreenshot (bg tab)│
 └──────────────────────────────┘                           │  Accessibility.getFullAXTree    │
                                                             │  DOM.* (pierce shadow/iframe)   │
                                                             │  isolated "Anticipy" tab-group  │
                                                             └───────────────────────────────┘
```

1. **Hand = MV3 extension driving `chrome.debugger`/CDP on the user's real tab.** Attach on task start,
   detach on completion; handle `onDetach` / DevTools-conflict reconnection. Operate inside an isolated
   **"Anticipy" tab-group** — never hijack the user's active tab. Flip `ANTICIPY_DEMO_VISIBLE=false` for
   prod (drive backgrounded).
2. **Input via `Input.dispatch*` only**, wrapped in the grafted **humanlike** Bezier + Fitts's-Law
   motion layer (±30ms jitter, 40–120ms dwell). Never fall back to content-script `dispatchEvent` for
   anything gated on trusted input.
3. **Perception via `Page.captureScreenshot` (JPEG q55, works on backgrounded tabs) +
   `Accessibility.getFullAXTree` + scoped `DOM.*` with `pierce`** for shadow/iframes; flat sessions
   (`sessionId`, Chrome 125+) for OOPIFs. Resolve execution contexts fresh; **wait on real signals
   (`frameStoppedLoading`/net-idle/element-stable), never sleeps.**
4. **Never globally `Runtime.enable`** — issue only the CDP you need, when you need it. This
   structurally avoids the #1 classic CDP detection tell (the `Runtime.enable` leak) that scrapers can't
   escape. Anticipy's real machine/IP/profile/history are the strongest *trust* signals; robotic timing
   is the main tell, which humanlike motion neutralizes.
5. **Security: stay in-session, export nothing.** No cookie/token extraction, no
   `--remote-debugging-port`, no native-messaging cookie access. The CDP socket stays on-device; the
   cloud sends *intents* and receives *compact state* (`token_vault.py` holds per-site creds encrypted;
   for a fresh login/2FA/CAPTCHA wall, pause→text, never auto-type).
6. **Warning bar:** ship the honest default (the "Anticipy started debugging this browser" banner = a
   trust signal) and offer the `--silent-debugger-extension-api` launch profile / enterprise policy for
   power users who want it gone.
7. **Transport:** `core/browser_link.py` authenticated WS with 20s pings + alarm backstop + auto-reconnect;
   all hand state in `chrome.storage` (survives service-worker idle-kill).

---

## 6. INSTALLATION

**The DoD bar (investor walkthrough step 2):** a stranger clicks "Get Anticipy" → downloads and runs
the engine in **one clean step, no terminal** → loads the extension → it just works. Two supported
tracks:

### 6.1 Cloud (product default — already live)
- **Engine:** Railway (`engine-production-eb43.up.railway.app`, Hobby tier), per-user Supabase
  sign-in + data isolation (proven: user A's cards never show for user B).
- **Extension:** installed from the Chrome Web Store (prod) or loaded unpacked (dev). On first run it
  calls the engine `/ws/token`, the user signs in once, and the extension pairs to their account via the
  session token — no port, no local Python.
- **Pairing:** `fetchToken()` in the extension → engine `/ws/token` → `/ws/extension?token=…`. The token
  scopes the hand to that user's engine session.

### 6.2 Local dev
```
# Engine
engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787
# (read-only research arm) engine/.bu-venv holds browser-use 0.13.1 — self-heals rotted Playwright pins

# Extension (unpacked)
Chrome → chrome://extensions → Developer mode ON → "Load unpacked" → select ~/Anticipy-devin/extension
# Permissions in manifest.json: storage, alarms, scripting, tabs, tabGroups, debugger + <all_urls>
# Accept the "started debugging this browser" banner (or launch Chrome with
#   --silent-debugger-extension-api to suppress it)
```

### 6.3 Keys / env the install needs (see §8 for who provides)
- Cheap-VLM host key (OpenRouter/DeepInfra) + a spend cap → `ANTICIPY_MODEL_API_KEY`/`OPENROUTER_API_KEY`.
- Frontier key (Anthropic, `claude-opus-4-8`) for T3 escalation.
- (Optional) search API key (Brave/Serper/Firecrawl) for the T0 read lane.
- Per-user Supabase project (cloud) — already provisioned.
- No model-training key (we buy, not train).

---

## 7. THE AUTONOMOUS TEST HARNESS — the un-gameable scoreboard

**Design principle, forced by Anticipy's own history ("108/0 suite while the hand couldn't open a
tab"): guarantee the measurement, not the outcome.** Reconcile the existing graders
(`overnight/harness.py`, `overnight/done_gate.py`, `final/tests/context_eval.py`,
`engine/scripts/_webvoyager_slice.py`) into one **`engine/scripts/browser_eval.py`** +
`final/tests/browser/` task bundles.

### 7.1 The six load-bearing invariants
1. **Every task ships a machine-checkable functional postcondition** — a real artifact exists in the
   real account (message in Sent, row in the Sheet, event on the calendar, RMA staged). No task grades
   the agent's own "done." Judge-only allowed *only* where judge κ ≥ threshold, proven by
   `judge_calibration.py`.
2. **Verification is active, not passive (ProRe):** the grader *re-opens the account and independently
   confirms the artifact* — never reads the agent's transcript. This is R1/R2/R3 live-readback,
   mechanized.
3. **Two lanes of truth:** `replay_ci` ("is my agent broken?", $0, deterministic, mitmproxy/VCR
   cassettes) and `live_canary` ("does it work in reality?", variance-reported). A green replay suite
   **never** counts as "works end-to-end."
4. **Multi-objective scorecard:** success cannot be reported without **cost-of-pass**,
   **hand-launch-rate (tier-mix)**, and **injection-refusal rate** beside it. A PR fails if cost-of-pass
   rises >15% OR frontier-rate rises >3pp at equal-or-lower success.
5. **The judge is a calibrated instrument with a known error bar** (WebVoyager GPT-4V judge κ≈0.70;
   BrowserArena VLM judges 58–68% and *worse* with GIFs) — re-calibrated on any judge model/prompt
   change; policy model and judge never share model family or prompt lineage.
6. **Curation gate before promotion:** a task/skill enters the reusable set only after passing 2–5
   held-out siblings. Quarantine → shadow → promote.

### 7.2 The real-world task set (Omar's examples, functional checkers, on TEST accounts)
```
final/tests/browser/tasks/<id>/  spec.yaml · precondition.py · checker.py · siblings/ · injection/
```
- **(A) Amazon return — the irreversible-ACT template.** Drive to the "Submit return" review screen and
  **STOP** (`commit_boundary: pre_submit`); `checker.py` opens a **fresh grader-owned session**, asserts
  the return-review state (item, reason, refund preview) exists and that **no completed return was
  finalized**. A separate rare weekly full-commit canary on a burner tests the last click.
- **(B) Google Sheets sum — the reversible gold standard.** Write a cell; `checker.py` reads it back via
  the Sheets API and asserts the value/formula. Perfect state reset → the `replay_ci` workhorse.
- **(C) Gmail→WhatsApp — cross-app, key-point match.** Extract planted facts from a seeded email; assert
  a WhatsApp message to a **grader-owned echo number** contains all key points and did NOT leak the whole
  inbox. Exercises the silent-write class.
- **(D) Form-fill — self-hosted, perfectly deterministic.** Point at a grader-hosted form
  (Web3Forms/`arena.local`); assert the backend received an exact-match submission **and**
  `completed_via == "trusted_input"` (catches a hand that "fills" the DOM without real CDP input events).

### 7.3 Benchmark subset (functional-checker-only; suites overstate — Online-Mind2Web 60–90%→~30% real)
| Slice | Source | Count | Cadence | Purpose |
|---|---|---|---|---|
| Grounding regression | ScreenSpot-Pro + v2, weighted to Anticipy surfaces | ~120 | every PR | decides UI-TARS vs GUI-Actor per surface; catches grounder drift |
| Agentic sealed | `webarena-verified` (ServiceNow) subset | 60–80 | nightly, N=3 seeds, variance | reproducible success + tier-mix + cost |
| Real-world | the 4 tasks × siblings | ~24 | nightly replay + weekly live | the product's actual DoD |
| Live canary | BrowserArena-style real sites | 8–12 | weekly | reality check ("does the hand open the tab") |
| Safety | hidden prompt-injection payloads | ~15 | every PR | injection-refusal on the user's real session |

Use **BrowserGym** as the unified harness; report N-seed variance, never a single number.

### 7.4 The scorecard + DoD gate
```
scorecard: success_rate(per-slice, N-seed variance) · cost_of_pass($/successful task) ·
           hand_launch_rate(T2 %) · frontier_rate(T3 %) · tier_mix(T0..T4) ·
           injection_refusal_rate · judge_kappa(per task-type)
```
Un-gameable invariants: no task without a functional postcondition; verification is an independent
re-read; green `replay_ci` ≠ "works" (a `live_canary` pass with a functional checker + human sample is
required to claim end-to-end); the scorecard is multi-objective; irreversible-ACT runs on test accounts
at a `commit_boundary`. **This eval is the feedback signal that governs §3 routing** (tier-mix creeping
up = T0/T4 under-firing; a surface chronically failing grounding = the LoRA trigger).

**Regression discipline** (aligns with CLAUDE.md GATE-S): the repo suite baseline is **109 passed / 10
failed (2026-07-02)**; the FAILED name-set **may never grow** — byte-diff the tail line every run.

---

## 8. THE ORDERED PATH — from where-we-are-now to fully-done (+ what needs Omar)

**Where we are now (honest):** the hand is real and has a live receipt (`F_browser.json`), the loop is
the right architecture but tangled in one file, per-step routing runs on the *frontier* model (the cost
bug), there is no browser eval scoreboard yet, `action_guard.py` is not landed, and the DEV-FINAL
router/verifier/humanlike parts are not grafted. WebVoyager baseline is ~43%; target 60%+.

Every step ends with a **WIRING-PROOF** (real command output in the plan box) and must not grow the
GATE-S fail-set. **Measure before changing anything.**

| # | Step | Files | Needs Omar |
|---|---|---|---|
| **0** | **Build `browser_eval.py`** (real-world set + WebVoyager subset; reports pass/$/steps/tier-mix). Baseline the current 43% and current $/task **before touching code.** | `engine/scripts/browser_eval.py` (from `_webvoyager_slice.py` + `final/tests/context_eval.py`) | **live Chrome + extension connected; Web3Forms key; test accounts (Amazon/GSuite/WhatsApp burner) + grader-owned echo number** |
| **1** | **Land `action_guard.py`** as a tested module behind a flag (don't rip existing gates — safety-gating PASS deferred). | `hands/action_guard.py` (from Nick's branch) | — |
| **2** | **Refactor `webvoyager.py` into the 5 roles over explicit `RunState`**; extract `guarded_step.py`. No behavior change; eval must hold. | `agent/webvoyager.py`, `agent/guarded_step.py` | — |
| **3** | **Fix the cost bug: add the ACT tier**, route per-step `agent` to a cheap VLM, keep SMART as escalation only; add the GROUND tier. | `core/gateway.py` | **cheap-VLM key (OpenRouter/DeepInfra) + spend cap** (gateway already reads the env var → likely just the cap) |
| **4** | **Graft DEV-FINAL parts:** `humanlike.py`→extension `cdpClick/cdpType`; `vision_router.py`+`vision_image_prep.py`→phase-5 tier decision (enforce region-crop, vision on-demand); `vision_verifier.py`→VERIFIER L2. | `extension/background.js`, `agent/*`, ports from `~/Developer/Anticipy-DEV-FINAL/engine/app/action_engine/*` | — |
| **5** | **Escalation + recovery ladder + read-back verify** wired as the mandatory cell; frontier-call cap; loop/stuck detectors. Re-run eval. | `agent/guarded_step.py`, `agent/proof.py` | **Anthropic frontier key** (T3 escalation) |
| **6** | **Add the T0 search/read lane + READ/ACT router** (search API + site's own XHR via CDP). Drives hand-launch-rate down. | `hands/` search worker, `core/control_core.py` | **(optional) Brave/Serper/Firecrawl key** (else start on the extension's $0 network-read path) |
| **7** | **Evolve `recipes.py` → the skills pipeline** (SKILL.md dirs, LIFT+parameterize, ADMIT/CI gate, retrieval-before-task, lifecycle). Warm-flow cost → ~$0. | `agent/recipes.py` (+ `skills/`) | — |
| **8** | **Iterate to 60%+** on `browser_eval.py` at ≤~$0.03/task cold; only then consider Phase-1 hosted grounding / Phase-2 LoRA. | all | — |
| **9** | **Investor-walkthrough dress rehearsal** (§6 one-clean-step install → onboarding → messy day → browser errand "return that plant" → stops at money/login → hands back), run by a stranger, unassisted. | product-wide | **a stranger + a live laptop** |

**Keys Omar must provide (consolidated):** (a) cheap-VLM host key (OpenRouter already wired) + spend
cap; (b) Anthropic frontier key for T3; (c) Web3Forms capture key (free) for the form eval; (d) optional
search API key for the T0 lane; (e) a connected extension / live Chrome for real-account runs; (f) test
accounts (Amazon, GSuite, WhatsApp burner) + a grader-owned echo number. **No training key needed —
we are buying, not training.**

---

## 9. ANTI-PATTERNS EXPLICITLY REJECTED (evidence-backed)

- ❌ **Swarm on one tab** → context collapse + hallucination cascade. One writer.
- ❌ **Model grades itself** → net-negative; verification is external + environment-grounded.
- ❌ **Per-step voting / self-consistency** → dead on strong models; buys cost not accuracy. Voting only
  at the final judge, N=3, gated.
- ❌ **One-shot rigid plan** → must re-plan from the reached page (more accurate *and* cheaper).
- ❌ **Safety by prompt** → guards are code; the LLM cannot override them; page text is untrusted.
- ❌ **"Handoff = success"** → a paused task is unfinished; only resume-and-finish counts.
- ❌ **Fixed sleeps** → wait on a condition, re-observe before asserting.
- ❌ **browser-use as the actor** → it is the read-only research arm; the trusted-CDP extension is the hand.
- ❌ **DOM-only / screenshot-only** → hybrid: AX/SoM index default, real pixels first-class at tier2/3.
- ❌ **remote-debugging-port / native-messaging cookie access** → dead on the real profile / the malware
  pattern. Drive in-session, export nothing.

---

## APPENDIX — FILE-PATH INDEX (real, on `~/Anticipy-devin` `hoe/build` unless noted)

- Brain: `engine/anticipy_engine/agent/webvoyager.py` (refactor into 5 roles) · new `agent/guarded_step.py`
- Skills: `engine/anticipy_engine/agent/recipes.py` (→ `skills/` pipeline) · `agent/proof.py`
- Walls/resume: `engine/anticipy_engine/agent/handoff.py` · `agent/resume_store.py` · `core/navwall.py`
- Guard (land): `engine/anticipy_engine/hands/action_guard.py` (from `origin/nick-sevostiyanov-demo/site:ai-guidance/browser-agent/action_guard.py`)
- Hand: `extension/background.js` · `extension/manifest.json` · `core/browser_link.py` · `hands/browser_hand.py`
- Read-only arm: `hands/browser_use_link.py` · `hands/browser_use_runner.py` · `engine/.bu-venv`
- Routing/cost: `core/gateway.py` · `core/control_core.py` · `core/scorecard.py`
- Salvage-graft (from `~/Developer/Anticipy-DEV-FINAL/engine/app/`): `action_engine/humanlike.py`,
  `action_engine/vision_router.py`, `action_engine/vision_image_prep.py`, `action_engine/vision_verifier.py`,
  `coldstart/cdp_walker.py`, `coldstart/auto_inhale.py`
- Eval: `overnight/harness.py` · `overnight/done_gate.py` · `final/tests/context_eval.py` ·
  `engine/scripts/_webvoyager_slice.py` → new `engine/scripts/browser_eval.py` · new `final/tests/browser/tasks/*`
- Live receipt: `docs/guarantee/proof/F_browser.json`
- Bar it serves: `CANON/04_DEFINITION_OF_DONE.md` (investor walkthrough)
```
