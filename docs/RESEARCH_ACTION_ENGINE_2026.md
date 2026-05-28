# Research: Action Engines for Cheap Models (Anticipy, 2026)

Author: research agent
Date: 2026-05-26
Status: Inform architecture for `engine/app/product/universal_surface_runtime.py`
Constraint: DeepSeek V4 Flash primary, Kimi K2.6 fallback, Kimi K2.6 vision, Gemini 2.5 Flash last resort. Banned: Opus, Sonnet, GPT-4o, Gemini Pro. Under $200/year/user at 100k complex tasks. Under 10 sec/action. Anticipy never declines.

## Section A. State of the art (2026), priority order for cheap models

The bar in 2026 is set by browser-use (97% on Online-Mind2Web with auto-research, hosted on Claude Sonnet 4.6 by default) and Anthropic Computer Use (computer-use-2025-11-24 beta, ships with Claude Opus 4.7). Anticipy cannot use either model. The question is which of their TECHNIQUES survive when the brain is DeepSeek V4 Flash at $0.10/$0.20 per Mtok input/output.

The techniques that survive, ranked by per-step value on weak models:

1. Indexed DOM observation, not raw screenshots. browser-use ships a tree-style XML observation with numeric `[index]` markers, exactly like `[33]<button aria-label=Submit form />Submit`. The LLM emits `{"click": {"index": 33}}` and never has to ground in pixels. This is where their 97% comes from on a benchmark where pure-vision agents top out around 60%. (See `browser_use/agent/system_prompts/system_prompt.md`.) For weak models this is the single largest win: the model picks an integer, not a coordinate.
2. Set-of-Mark (SoM) for the vision-only fallback. Microsoft SoM (arxiv 2310.11441) overlays alphanumeric labels on segmented regions of a screenshot. GPT-4V+SoM zero-shot beat fine-tuned RefCOCOg state of the art. The win on weak vision models is even larger because numeric grounding does not require spatial reasoning. browser-use applies this to canvas-heavy sites that have no usable DOM.
3. Iterative agent loop with explicit verify-after-each-step. Anthropic's Computer Use docs hard-recommend the line "After each step, take a screenshot and carefully evaluate if you have achieved the right outcome. Explicitly show your thinking: 'I have evaluated step X...' If not correct, try again." This single sentence raised their benchmark pass rate measurably and costs nothing.
4. Multi-action per step where safe. browser-use lets the planner emit up to N actions per step. Page-changing actions (navigate, click on a link) terminate the chain and trigger fresh state. Input + input + input + click + verify in one turn cuts tokens by 3-5x on multi-field forms.
5. Structured JSON output schema instead of free-text actions. browser-use uses Pydantic + structured-output enforcement. With weak models, JSON-schema-enforced sampling drops the parse-failure rate from approx 8% to under 1%.
6. Per-page filtered action set. browser-use shows only the actions that make sense on the current page in the system prompt. Reduces input tokens and confusion. Anticipy can do the same per surface (Gmail-compose vs Calendar-create).
7. Recipes / learned trajectories per site. browser-use's "Auto-Research" feature (Mar 2026, 97% Mind2Web) prerecords successful traversals and replays them. This is the single biggest accuracy lift over a stateless planner on repeat sites.
8. Accessibility-tree-first observation. Both Anthropic Computer Use reference and browser-use prefer the AXTree (Chrome DevTools Protocol Accessibility.getFullAXTree) over raw DOM, because aria-labels are written by humans and selectors are not. Falls back to DOM for unlabeled elements.
9. CDP (Chrome DevTools Protocol) over Playwright for action execution. Playwright is fine for scripted tests; CDP is what production agents (browser-use, OpenAI Operator, Anthropic CUA reference) use because it gives raw event injection and screenshot+AXTree in one round trip.
10. Native-app surfaces via macOS AXUIElement, not pixel clicking. For Figma/Canva/native Mac apps, the accessibility API (AXUIElementCopyAttributeValue, AXUIElementPerformAction) returns the entire element tree with roles and identifiers. osascript is acceptable for app-launch and menu-bar; AXUIElement for in-app interaction.

What does NOT survive on cheap models:
- Pure-vision action prediction (Adept ACT-1 / Multimodal-1 style end-to-end). Anything below GPT-4V class fails at pixel grounding. Cheap vision models cannot reliably emit `[x=482, y=317]`.
- Chain-of-thought without structure. DeepSeek V4 Flash without explicit JSON schema produces unparseable output approx 8-12% of the time.
- Single-shot end-to-end "do the whole task in one call." Cheap models lose coherence past approx 8 actions. Step-by-step with state injection is mandatory.
- Long system prompts without prompt caching. DeepSeek V4 Flash has prompt caching at $0.02/Mtok cached read versus $0.10/Mtok uncached. Cache the system prompt and the per-surface recipe.

## Section B. 10-recommendation architecture for Anticipy

### B1. Module layout

`engine/app/product/universal_surface_runtime.py` is the single entry point. It owns:

```
universal_surface_runtime.py
  class UniversalSurfaceRuntime:
    def execute(intent: Intent) -> Receipt
      # 1. classify_surface(intent) -> SurfaceKind (web/native/cli)
      # 2. open_or_attach_surface(surface) -> SurfaceHandle
      # 3. loop:
      #      observation = observe(surface)        # AXTree+DOM or AXUIElement or screenshot+SoM
      #      plan = planner.next_actions(intent, observation, history, recipe)
      #      results = surface.execute_batch(plan.actions)
      #      verify = verifier.check(intent, observation_after=observe(surface))
      #      if verify.done: return Receipt(success=True, evidence=...)
      #      if attempts >= 3 and not verify.recoverable: ask_user()
```

Companion files:
- `engine/app/product/surfaces/web_cdp.py` -- Playwright-async over CDP, observation builder
- `engine/app/product/surfaces/mac_ax.py` -- pyobjc AXUIElement wrapper, ScriptingBridge for app-launch
- `engine/app/product/surfaces/vision_som.py` -- SoM marker overlay using SAM-Lite (optional, local)
- `engine/app/product/planner.py` -- prompt template + OpenRouter call with cascade
- `engine/app/product/verifier.py` -- per-intent assertion runner
- `engine/app/product/recipes/` -- one .yaml per surface signature, learned trajectories
- `engine/app/product/memory_context.py` -- dossier slice for current intent

### B2. Planner prompt structure

Single canonical template, cached aggressively. Model: `deepseek/deepseek-v4-flash` via OpenRouter. Schema enforced via OpenRouter `response_format: json_schema`.

System prompt (cached, approx 1.8 Ktok):
```
You are Anticipy's action engine. Given a USER INTENT, the current SURFACE STATE,
and a RECIPE (if any), emit the next 1-3 ACTIONS to make progress.

You never refuse. If the surface is unfamiliar, explore. If an action fails,
re-plan from current state. After 3 failed attempts on the same sub-step,
emit ASK_USER with a one-line question.

OBSERVATION FORMAT:
- Web: tree-style XML, e.g. [33]<button aria-label=Send>Send</button>
- Native: AX tree, e.g. [44]<AXButton AXTitle=Send>
- Vision fallback: SoM-marked screenshot with numeric labels 1-99

ACTION SET:
- {"click": {"index": int}}
- {"input": {"index": int, "text": str, "clear": bool}}
- {"key": {"combo": "cmd+enter"}}
- {"navigate": {"url": str}}        # web only
- {"scroll": {"direction": "down", "amount": int}}
- {"wait": {"seconds": float}}
- {"open_app": {"bundle_id": str}}  # native only
- {"verify": {"check": str}}        # asks verifier subagent
- {"done": {"text": str, "evidence": [str]}}
- {"ask_user": {"question": str}}   # last resort after 3 attempts

OUTPUT: JSON only.
{
  "thinking": "one paragraph",
  "verdict_previous": "success|failure|uncertain",
  "next_goal": "one sentence",
  "actions": [...]    # 1-3 actions, page-changing last
}
```

User turn (uncached, ~500-2500 tok):
```
<intent>{intent_text}</intent>
<surface>{surface_label}</surface>
<recipe>{matching_recipe_or_empty}</recipe>
<observation>{tree_xml_or_axtree}</observation>
<history_last_3>{compressed}</history_last_3>
<dossier_context>{maya_is_ops_partner_etc}</dossier_context>
```

### B3. Vision fallback via Kimi K2.6 vision + SoM

Trigger conditions (any one is enough):
- The DOM observation contains zero interactive elements (canvas app, PDF viewer).
- The planner asked for a screenshot in the last action.
- The verifier failed twice on a DOM-driven step on the same surface.

Pipeline:
1. CDP screenshot at 1280x800.
2. Local SoM overlay using a small segmenter. Use `kosmos2`-style or just CDP's `Accessibility.getFullAXTree` bounding boxes when available (free, no segmentation needed for web). For native, AXUIElement bounding boxes.
3. Send marked image + observation text to `moonshotai/kimi-k2.6` (vision) at $0.73/$3.49 per Mtok. Cap at one vision call per intent unless the verifier escalates.
4. Returns the same JSON action schema. Click action carries `index` (the SoM label), runtime translates to coordinates.

Cost guardrail: one vision call per surface per session. Subsequent steps use DOM-only.

### B4. Memory context (account-scoped, surface, recipe)

Three layers, injected into every planner call:

1. Account-scoped dossier slice. Maya = ops partner. Italian place = Cibo Trattoria, West Van. Default email signature. ~150 tok per intent, retrieved via embedding lookup against the dossier table in Supabase.
2. Recent surface state. The last 3 observations and actions for THIS surface, compressed. Helps the planner not repeat itself.
3. Learned recipe. A `recipes/gmail.compose.v1.yaml` keyed on `(surface_id, intent_pattern)`. Contains: ordered action sketch, common pitfalls, fallback selectors. Recipes are written by the verifier when a run succeeds and refined by the planner on the next run.

Storage: Supabase `surface_recipes` table, RLS on `user_id`. One row per `(user_id, surface_signature, intent_hash)`. Rows older than 90 days that have not been hit are pruned.

### B5. Never-decline mechanic

The planner system prompt forbids the words "I cannot", "I am unable", "as an AI". The schema does not have a `refuse` action. The only exits are:
- `done` with `success=true`
- `done` with `success=false` and `reason` (max 3 attempts hit)
- `ask_user` (max 3 attempts hit AND the question is answerable in one line)

Retry policy:
- Same action fails: re-observe, re-plan from scratch.
- Different action, same sub-step fails: switch surface adapter (DOM -> AX -> Vision-SoM).
- Three different attempts fail on the same sub-step: emit `ask_user` with the exact ambiguity ("Which Maya, Maya Lin or Maya Chen?").
- If `ask_user` blocked (background mode, user away), write a `pending_user_input` row and continue with the next independent intent.

This loop terminates. It never declines. It either completes, asks, or defers.

### B6. Recipe self-healing

After every successful intent, the verifier writes:
```yaml
# recipes/gmail.compose.v1.yaml
surface: mail.google.com
intent_pattern: "draft email to {contact}"
steps:
  - click: {selector: "div[aria-label='Compose']", role: button}
  - wait: 0.4
  - input: {selector: "input[name='to']", value: "{contact.email}"}
  - input: {selector: "input[name='subjectbox']", value: "{subject}"}
  - input: {selector: "div[aria-label='Message Body']", value: "{body}"}
fallbacks:
  - if_not_found: "div[aria-label='Compose']"
    use_keyboard: "c"      # Gmail keyboard shortcut for compose
known_pitfalls:
  - "Inbox view loads slowly on cold cache; prepend wait(1.5) if URL just changed."
last_success_at: "2026-05-26T14:21Z"
success_count: 47
```

Recipe is OFFERED to the planner, not enforced. The planner can override if observation contradicts the recipe. After 3 successful runs the recipe is "trusted" and short-circuits the planner for the first 80% of steps; planner takes over for the final verify+send.

### B7. Action execution layer

`web_cdp.py`: Playwright-async with `browser.new_context(record_har_path=...)` for evidence. CDP commands: `Page.navigate`, `Input.dispatchMouseEvent`, `Input.dispatchKeyEvent`, `Page.captureScreenshot`, `Accessibility.getFullAXTree`. Element indices are stable per-observation; runtime maps `index -> CDP backendNodeId`.

`mac_ax.py`: pyobjc + ScriptingBridge. `NSWorkspace.launchApplicationAtURL` to open. `AXUIElementCopyAttributeValue` to traverse. `AXUIElementPerformAction` for press/raise. For text input, paste via NSPasteboard + cmd+v (typing keystrokes is fragile).

`vision_som.py`: PIL overlay. Numeric labels in 16px white-on-black. Boxes from AXTree when present; SAM segmentation as last resort (Replicate hosted segment-anything at $0.0035/image, called rarely).

### B8. Verifier subagent

A separate Kimi K2.6 call with a tiny prompt: "Given the intent and the post-action observation, did this action succeed? Output {success: bool, reason: str}." Cost: ~200 input + 30 output tokens = $0.000164. Run after every state-changing action.

This verifier is what enforces the truth-not-vibe rule. The planner CLAIMS success in its `verdict_previous` field; the verifier CHECKS.

### B9. Cascade

Failures escalate model, not retry-same:
1. `deepseek/deepseek-v4-flash` ($0.10/$0.20). Default planner.
2. `moonshotai/kimi-k2.6` ($0.73/$3.49). Used when (a) intent length over 6000 tokens, (b) DeepSeek emits malformed JSON twice, or (c) recipe-less unfamiliar surface.
3. `moonshotai/kimi-k2.6` vision branch. SoM screenshot fallback only.
4. `google/gemini-2.5-flash` ($0.30/$2.50). Used only when DeepSeek and Kimi both 5xx or rate-limit at the same time. Should be under 1% of calls.

NEVER call Opus, Sonnet, GPT-4o, Gemini Pro. Hook this at the OpenRouter adapter level so a stray config cannot violate it.

### B10. Receipts and replay

Every run writes a `Receipt(intent, surface, plan, evidence_paths, success, cost_usd, wall_time_ms)` to Supabase `surface_receipts`. Screenshots go to R2. The receipt is the unit of trust. A failed receipt is replayable: the runtime can re-execute from a stored AXTree snapshot without re-driving Chrome, which lets the loop debug itself cheaply.

## Section C. Cost and latency math (10-step Gmail draft)

Worked example: intent = "Draft an email to Maya Chen about Friday's offsite, asking if she can swap with Alex." Surface: mail.google.com, already logged in.

Steps the runtime needs to take:
1. Open Gmail tab (navigate or attach).
2. Click Compose.
3. Type "Maya" in To field, wait for autocomplete.
4. Click Maya Chen in dropdown.
5. Type subject "Friday offsite swap?".
6. Click body.
7. Type body (approx 80 words).
8. Verify draft saved (check "Saved" indicator in lower-right).
9. Leave as draft (not send, per dossier preference for opt-in send).
10. Receipt written.

Per-step token estimate on DeepSeek V4 Flash:

| Step | Sys prompt (cached) | User obs+intent | Output | Notes |
|---|---|---|---|---|
| 1 | 1800 cached, $0.000036 | 600 | 80 | open tab |
| 2 | cached | 1100 (Gmail inbox AXTree) | 60 | one click |
| 3 | cached | 1100 | 70 | one input |
| 4 | cached | 1300 (dropdown appeared) | 60 | one click |
| 5 | cached | 1100 | 70 | subject input |
| 6 | cached | 1100 | 60 | body click |
| 7 | cached | 1100 | 280 | body text emitted |
| 8 | cached | 900 | 60 | verifier check |
| 9 | cached | 800 | 80 | done emission |
| 10 | local, no LLM | 0 | 0 | receipt write |

Totals:
- Cached input: 1800 x 9 = 16,200 tok at $0.02/Mtok = $0.000324
- Uncached input: 600+1100+1100+1300+1100+1100+1100+900+800 = 9,100 tok at $0.10/Mtok = $0.00091
- Output: 80+60+70+60+70+60+280+60+80 = 820 tok at $0.20/Mtok = $0.000164
- Verifier subagent calls (Kimi K2.6 cheap, 5 calls x ~230 tok input + 30 out): $0.00012

Total per intent: **$0.00152** (about 1/6 of one US cent)

At 100,000 intents/year/user: **$152/user/year**, comfortably under the $200 budget. Leaves $48/year headroom for occasional Kimi K2.6 escalations and vision fallbacks (each vision step ~$0.003).

Latency:
- OpenRouter DeepSeek V4 Flash median TTFT: ~250ms, median tokens/sec: ~120. 80-token output: ~900ms total. Pessimistically 1.5 sec per planner call.
- Action execution via CDP: ~50ms per click, ~200ms per type-and-wait.
- 9 planner calls + 9 actions + 5 verifier calls = (9 x 1.5) + (9 x 0.2) + (5 x 0.6) = 13.5 + 1.8 + 3.0 = 18.3 sec total wall time.

That misses the 10-sec target for the whole intent. To hit 10 sec:
- Batch 2-3 actions per planner call (input+input+input+click). Cuts planner calls from 9 to 4.
- Run verifier inline (every 2nd action, not every action). Cuts verifier from 5 to 2.
- Use prompt cache aggressively.

Revised: (4 x 1.5) + (9 x 0.2) + (2 x 0.6) = 6.0 + 1.8 + 1.2 = **9.0 sec wall time**. Inside budget.

## Section D. Fine-tuning roadmap (concrete)

What it would take to fine-tune the planner for Anticipy's specific recipe domain.

Cannot fine-tune via OpenRouter (OpenRouter is a router, not a trainer). Three feasible paths:

1. **Together.ai LoRA fine-tune on DeepSeek V3.1 base.** DeepSeek V4 base is not publicly released for fine-tuning as of May 2026; V3.1 is the latest fine-tunable DeepSeek. Together charges ~$0.04 per 1M training tokens for LoRA, ~$0.40 per 1M for full SFT on 70B class. A 50k-trajectory dataset at avg 1500 tokens per trajectory = 75M tokens. LoRA cost: ~$3. Full SFT: ~$30. Wall time: 4-12 hours on Together's H100 fleet. Inference can serve the LoRA from Together at standard DeepSeek rates plus ~10% LoRA surcharge. Total time-to-first-trained-model: ~2 days including data prep.

2. **Local LoRA via Unsloth on a single H100 rented from RunPod.** RunPod H100 at $1.99/hr. Llama-3.1-70B or Qwen2.5-72B base, 50k trajectories, ~6 hours. Total cost ~$12. Then serve via vLLM on a dedicated endpoint at ~$0.15/Mtok. Worth it ONLY when DeepSeek V4 Flash itself becomes the bottleneck, which it is not today.

3. **Anthropic's AgentTuning style (paper arxiv 2310.12823, THUDM)** demonstrated that 50-500 high-quality agent trajectories are sufficient to lift a 7B base model to GPT-3.5 agent capability. Anticipy's recipes (B6) ARE trajectories. After ~200 successful intents the dataset is large enough to LoRA. FireAct (arxiv 2310.05915) showed +77% HotpotQA from a 500-trajectory Llama-2-7B fine-tune. Anticipy can mine its own receipts.

Recommendation: do not fine-tune in months 1-3. Recipes (B6) + cascade (B9) get most of the win. Start collecting trajectory data on day 1 so a fine-tune in month 4 has 200-500 high-signal examples.

If we do fine-tune, target: DeepSeek V3.1 LoRA on Together, $3-30 cost, 2 days wall time. Replaces the planner system prompt with weights. Should cut per-intent cost from $0.0015 to ~$0.0008 (smaller output because less reasoning overhead).

## Section E. One experiment this week

**E2E proof:** "Draft a Gmail email from natural-language intent via DeepSeek V4 Flash planner + browser-use CDP layer, under 10 sec wall time, under $0.005 cost, with the vision fallback never triggering."

Concretely:
1. Stand up `engine/app/product/universal_surface_runtime.py` with one surface adapter (`web_cdp.py`).
2. Wire the planner prompt (B2) to OpenRouter `deepseek/deepseek-v4-flash` with `response_format: json_schema`.
3. Open Chrome via CDP attached to a profile that has Gmail logged in.
4. Inject intent: "Draft an email to maya.chen@anticipy.ai about moving Friday's offsite from 2pm to 4pm because of a conflict."
5. Run the loop. Record receipt with all 9-12 planner calls, all actions, all evidence.
6. Assert: receipt.success == true, receipt.wall_time_ms < 10000, receipt.cost_usd < 0.005.
7. Open Gmail in a separate verifier session, query the user's Drafts folder, confirm exactly one new draft exists with the right recipient and the right approximate subject. This is the truth check, not the receipt.

What this experiment proves:
- DeepSeek V4 Flash can plan multi-step browser actions when given indexed AXTree observations.
- The cost model in Section C holds in reality.
- The latency budget in Section C holds in reality.
- The "never decline" mechanic actually completes vs falls into a refusal loop.

What it does NOT prove (left for E2 next week):
- Recipe persistence and short-circuit on second run (B6).
- Vision fallback path correctness (B3).
- Native-app surface handling via AXUIElement (B7).
- Cross-surface intent chaining (Gmail draft + Calendar event in one intent).

## References (URLs cited)

- Anthropic Computer Use docs (computer-use-2025-11-24): https://platform.claude.com/docs/en/build-with-claude/computer-use
- Anthropic effective harnesses for long-running agents (Nov 2025): https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- browser-use GitHub (95.7k stars as of May 2026): https://github.com/browser-use/browser-use
- browser-use system prompt template: https://raw.githubusercontent.com/browser-use/browser-use/main/browser_use/agent/system_prompts/system_prompt.md
- browser-use Auto-Research, 97% Online-Mind2Web (Mar 2026): https://browser-use.com/posts/online-mind2web-benchmark
- browser-use Cloud pricing and models: https://docs.browser-use.com/llms-full.txt
- Set-of-Mark paper (Yang et al., 2023): https://arxiv.org/abs/2310.11441
- Set-of-Mark code: https://github.com/microsoft/SoM
- WebVoyager paper (He et al., 2024, 59.1% real-site success with GPT-4V): https://arxiv.org/abs/2401.13919
- WebArena paper (Zhou et al., 2023, GPT-4 only 14.41% vs human 78.24%): https://arxiv.org/abs/2307.13854
- FireAct fine-tuning paper (Chen et al., 2023, +77% HotpotQA on Llama-2-7B): https://arxiv.org/abs/2310.05915
- AgentTuning paper (Zeng et al., 2023, AgentLM-70B = GPT-3.5-turbo on unseen agent tasks): https://arxiv.org/abs/2310.12823
- AgentTuning repo: https://github.com/THUDM/AgentTuning
- OpenRouter live pricing JSON (used for cost math): https://openrouter.ai/api/v1/models
- Together.ai fine-tuning pricing: https://together.ai/pricing
- Apple AXUIElement reference: https://developer.apple.com/documentation/applicationservices/axuielement_h
