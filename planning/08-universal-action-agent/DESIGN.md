# Universal action agent. Anticipy V7.

Planning doc. Owner: Omar. Drafted 2026-05-29. Authoritative architecture for what Anticipy does after it has resolved an intent. Supersedes anything in `planning/03-cross-app-auth/` that proposes a per-app config registry at `engine/config/auth_profiles/<app>.json`. That direction is wrong and is excised in `planning/11-hardcoded-violations-audit/EXCISE_LIST.md`.

## 1. The principle

Anticipy is a universal action agent. It looks at a page, decides the next action, executes it, observes the result, and loops. Nothing in the loop is app-specific. The loop reads the current page in two cheap forms (a screenshot for visual layout, the accessibility tree for stable named handles), sends both to a vision-language model conditioned on the user's intent, receives a single concrete next action (click coordinate, type text into element @eN, navigate URL, press key), dispatches it via CDP against the user's real Chrome, captures the after-state, verifies progress with a separate vision call, and either continues or terminates. The "skill" that ships in Anticipy is the loop itself. There are no per-app skills, no per-domain recipes, no `if site == gmail` branches, no app registries. The agent handles Gmail because it can read Gmail's UI, Salesforce because it can read Salesforce's UI, and the law firm's bespoke matter-management portal because it can read that portal's UI. Day one. Every site the user is already logged into.

This is what Claude does in computer-use mode and what Codex does in web-agent mode. It is the only architecture that scales to the long tail of B2B SaaS that a sales rep, lawyer, doctor, or construction PM actually uses every day. A 30-app recipe library is a 30-app product. The universal loop is the entire SaaS web.

## 2. The existing pieces we keep

The DSv4 Ralph Loop at `engine/app/action_engine/dsv4_skill_runner.py` is already 90% of what we need. Header at `dsv4_skill_runner.py:1-31` documents one iteration: CDP screenshot, accessibility-tree extraction (max 110 lines, each given a stable `@eN` reference at `:197-249`), page-text excerpt, a `_decide` step calling a vision LLM with screenshot+AX+page text returning one action JSON (`:798-830`), `_dispatch` over the humanlike CDP dispatcher (`:869-`), a settle, a `_vision_confirm` against the screenshot for honest completion gating (`:832-857`), and a `VisionVerifier.verify` Kimi K2.6 before/after diff on every state-changing action (`engine/app/action_engine/vision_verifier.py:103-174`). Hard cap 30 iterations, no confirmation gates inside.

The CDP dispatcher at `engine/app/action_engine/cdp_dispatcher.py` is the right substrate: talks to `localhost:9222`, dispatches mouse/key events with Bezier paths and Gaussian timing (`:1-21`), bound to a single tab via `CDPSession` (`:54-94`). The dedicated background "Anticipy Agent" window so the agent does not fight the user for foreground focus is at `dsv4_skill_runner.py:100-151`, persisted at `~/.anticipy/v4_agent_window.json`.

The vision adapter at `engine/app/product/surface_runtime_vision.py:39-74` is the Set-of-Mark capability. Calls Kimi K2.6 (live OpenRouter id `moonshotai/kimi-k2.6`, not the spec's `kimi-k2.6-vision`) to enumerate clickable bounding boxes, text-region OCR, and expected-state verification. Fallback for canvas-heavy surfaces (Figma, Canva, Sheets's drawing layer, native windows) where the AX tree returns nothing.

The DOM accessibility-tree extractor at `engine/app/product/surface_dom_extractor.py:46-64` walks actionable nodes in the live page and returns up to 200 visible nodes with bbox+role+name+value+parent_id over the `127.0.0.1:7777` loopback bridge. The runner's `_ax_tree_and_refs` does the same via direct CDP `Accessibility.getFullAXTree`; the runner's CDP-direct version is faster (no bridge hop) and is what the shipping path uses.

The OpenRouter client at `engine/app/action_engine/openrouter_client.py` is the model substrate. Reaches OpenRouter directly when `OPENROUTER_API_KEY` is set or proxies through `https://www.anticipy.ai/api/engine/model` (`:154-169`), enforces a 256-token floor (`:122, 235-244`), disables `reasoning` on every call because V4 Flash and Kimi K2.6 are both reasoning models that starve content before reasoning (`:141-150`), logs every call to `~/.anticipy/openrouter_calls.jsonl`. Broker whitelist is exactly `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-pro`, `moonshotai/kimi-k2.6` (`src/app/api/engine/model/route.ts:8-12`) with a 2 MB payload cap (line 33) that fits one normal vision frame.

Complete: runner runs end-to-end on Gmail compose (CHECK 08-10, validated by after-action screenshot). Partial: runner is only invoked from the Gmail-draft fastpath; the natural-language `task` is string-templated in `_fastpath_plan_from_memory` (`server.py:5351-5353`) and `_fastpath_pronoun_resolve` (`:5470-5473`). The runner itself does not know about Gmail. It works because the AX tree exposes "Compose", "To", "Subject", "Body", "Send" as buttons and textboxes with stable names, and the runner picks the right `@eN`. Nothing site-specific lives inside the runner.

## 3. The pieces to add

We need one wrapper. Call it `UniversalAgent.run(intent, target_hint)`. Takes a typed intent (the `Intent` dataclass at `engine/app/product/intent_extractor.py:25` is the right shape) plus an optional `target_hint` (URL like `mail.google.com` if known, free-text app name like "the firm's case management system" if not, or empty). Returns a `TaskResult` (already at `dsv4_skill_runner.py:177-187`). Inside: (a) opens the dedicated agent background window via `_ensure_agent_window`, (b) if a URL hint present, navigates; if a free-text hint, asks the model in one short call to map the hint to a logged-in URL (read Chrome history bridge for hints); if neither, leaves on `about:blank` and lets the first `_decide` pick the destination, (c) calls `DSv4SkillRunner(cdp_port=9222, max_iters=30).run(intent.summary)`, (d) on `SUCCESS` returns; on `ITERATION_EXHAUSTED` or `HARD_FAIL` invokes the escape hatch from section 8.

This wrapper replaces the two regex-string-templating fastpaths at `engine/app/product/server.py:5276` (`_fastpath_plan_from_memory`) and `:5399` (`_fastpath_pronoun_resolve`). Those fastpaths emit a fixed-shape plan `{"mode":"act","intent":"email_draft","task":"Open Gmail and create a draft email to <recipient> about: <utterance>..."}`. That string is structurally an Intent of `type=create, target_surface=mail.google.com, body=<utterance>`. The replacement is to emit a typed Intent and call `UniversalAgent.run(intent, "mail.google.com")`. The Intent is constructed by a single fast LLM call with prompt-cached system prompt (sub-300ms on DeepSeek V4 Flash with reasoning disabled). Fastpaths can be deleted. See `planning/11-hardcoded-violations-audit/EXCISE_LIST.md`.

## 4. Vision-language model use

Every `_decide` step is a vision call. The model is conditioned on the sub-goal plus AX listing plus visible page text plus short action history (`dsv4_skill_runner.py:816-823`). The decider runs on `moonshotai/kimi-k2.6` because no DeepSeek V4 variant ships vision on OpenRouter (`dsv4_skill_runner.py:801-809`). Kimi is locked in the broker (`route.ts:11`) and pre-priced (`openrouter_client.py:55-59`). The screenshot is normalized to CSS-pixel dimensions so any `[x,y]` the model returns is a 1:1 CDP mouse coordinate (`dsv4_skill_runner.py:532-548`); without this fix every Retina device sends every click off by 2x.

Latency target: 800 ms per step. Honest measurement: with `reasoning: {enabled: false}` and the 256-token floor, Kimi K2.6 vision returns in roughly 900-1600 ms p50 in the call-log artifacts at `~/.anticipy/openrouter_calls.jsonl`. The 800 ms target is aspirational; measured median is closer to 1.2 s. Mitigation: for any step where the AX tree exposes a stable named handle, the decide call can skip the screenshot and run on `deepseek/deepseek-v4-flash` against AX-plus-text-only, sub-400 ms. The runner currently uses vision unconditionally. A two-mode decide (text-only when an AX handle suffices, vision when needed) roughly halves median latency.

Set-of-Mark labeling is already implemented in `surface_runtime_vision.py` for canvas/no-DOM. We do not need it on the DOM path because `@eN` references serve the same purpose, are stable across a page (anchored to backend node IDs), and are produced server-side without a model call. Set-of-Mark for vision-only steps; `@eN` for AX steps. Route by which is available.

## 5. DOM extraction as fallback and cross-check

The accessibility tree is cheaper than the screenshot in three ways: faster to capture (CDP `Accessibility.getFullAXTree` returns in 100-300 ms vs 600-900 ms for `Page.captureScreenshot` on a heavy page), smaller in tokens (110-line cap, roughly 1.5k tokens, vs a 50-100k token vision frame after image-tokenizer expansion), and stable across visual reskins (Salesforce reorganizes its layout twice a year; AX names persist). When the page is text-heavy and the next action is on a standard element (button labeled "Send", textbox labeled "To"), use AX alone.

The cross-check pattern: each step, capture AX first. If the highest-ranked actionable element by name match against the sub-goal has confidence above 0.7 (cosine similarity between sub-goal verb-plus-object and AX node name), dispatch on that AX node, skip the vision call, and rely on `_vision_confirm` after-the-fact. If confidence is below 0.7, capture the screenshot and run the multimodal decide. Cheap first, expensive on demand.

The AX tree misses canvas apps. The runner already handles this: Sheets is detected by `_grid_fill` (`dsv4_skill_runner.py:388-500`); Maps and Canva and Figma fall through to vision-only decide. Both signals run; the loop uses whichever has signal for the current page.

## 6. The "skill" definition

A skill is not a Python module. A skill is a four-tuple: (intent statement, target URL or app hint, goal-check predicate, max-time budget). The agent figures out navigation, field-filling, button-clicking, error recovery, and confirmation gates by itself. Example: the "draft email to Dana about Friday's contract" skill is `(intent: "draft email to Dana about Friday's contract", target: "mail.google.com", goal_check: "a Gmail draft addressed to Dana exists in Drafts with the contract content in the body", budget: 90 seconds)`. The goal-check is what `_vision_confirm` already does (`dsv4_skill_runner.py:832-857`): a strict completion auditor looks at the screenshot and answers `{"done": true|false, "evidence": "..."}` against the intent. Empty fields and placeholder content mean NOT done by the model's instructed prior (`dsv4_skill_runner.py:843-844`), which kills fabricated success.

There is no skill registry, no `skills/gmail.py`, no per-domain handler. The runner is the skill. The intent is data. This is the architectural difference from a recipe library: a recipe library has N entries that grow linearly; the runner has one entry that handles all N apps.

## 7. Per-user adaptation without per-user code

The user's dossier at `~/.anticipy/v7/dossiers/<account_id>/dossier.json` (loader at `engine/app/product/dossier_active_loader.py:139`) is text. People, do-not-touch rules, writing voice, working hours, role-title: all strings. When the agent learns "Omar always uses 'thanks' not 'thank you' as a sign-off", that learning is a new memory entry of kind `preference` written via the frozen Mem0 memory at `engine/app/anticipy/memory.py` (`reconcile(user_id, "preference", ...)`). When the agent learns "Omar's firm uses this 4-paragraph demand letter template", the template is stored as a memory entry of kind `fact` with the literal template text as `value`. None is code. Rows in `~/.anticipy/system_v1/users/anticipy-user/memory.jsonl`.

At action time, the universal agent's prompt to the decide model includes (a) the typed intent, (b) the user's profile JSON (already in `_compose_task_from_memory` at `server.py:5497`), (c) the active dossier people list, and (d) the top-K active memory entries matching the intent verb plus the resolved person (Mem0 supports `active_snapshot`). The decide model reads "Omar always signs off with thanks" as a constraint on the body and types `thanks` on the last step. Learning is invoked by reading, not branching. Per-user code is excluded by the same rule as per-app code: it does not scale.

## 8. The escape hatch

Stuck (conservative: `_vision_confirm` returns `done=false` after the iteration cap, three successive `DIVERGED` verdicts on related steps, or any step that requires a credential the agent does not have) means snapshot the obstacle, describe it in one sentence, ask the user. Flow goes through the quietness UX in `planning/04-quietness-ux/DESIGN.md`: `NOTED + slow gold LED pulse` if silent-class, `haptic + earbud TTS` if confirm-class and user is in a quiet window, `IN_APP` digest accumulation otherwise. Screenshot of the obstacle is attached.

No per-app fallback. The agent itself escalates. The escalation message is generated by the same model with one prompt: "You attempted intent X in app Y. After Z iterations the screenshot looks like this. In one sentence: what is the obstacle, and what does the user need to do?" Output is the notification body. Works on a never-seen-before app the same way it works on Gmail.

The five valid synchronous halts from the user MEMORY (sudo prompt, macOS Privacy dialog, money above floor, irrecoverable credential, hardware unplugged) are detected by `_decide` itself (it sees the dialog and emits `action: ask_user` instead of `click`). The runner does not currently surface an `ask_user` exit; returning `TaskResult(status="ASK", question=..., screenshot_b64=...)` from `DSv4SkillRunner.run` is the missing piece.

## 9. Cold-start synergy

The prior planning suggested coverage of "5 of 30 apps" at launch, growing as per-app recipes are added. Wrong under the universal architecture. Agent supports any web app the user is logged into, day one. No apps to "add." Coverage equals "every app whose Chrome session is reachable at `localhost:9222`," which is every web app the user has ever signed into in their Anticipy-managed Chrome profile.

Day-zero cold-start (covered in `planning/10-instant-cold-start/DESIGN.md`) inhales Gmail, Calendar, Drive, and signature-derived facts in the background during onboarding, populating dossier text. The action agent reads that text. There is no "agent knows Gmail because we wrote Gmail code"; the agent knows what the dossier and memory tell it, and reads whatever app the user opens.

Native macOS apps (Reminders, Notes, Messages, Calendar) are not part of the web loop, but `engine/app/product/native_action_macos.py` exists as a 20 KB osascript+cliclick wrapper. The universal agent dispatches to it on `target_app` of `reminder | note | message | calendar.native`; everything web goes through the CDP loop. Two surfaces, one decider.

## 10. Risks

- **Vision-model latency on Kimi K2.6.** Measured 900-1600 ms p50 per decide step; budget says 800 ms. Mitigation: AX-only fast path when AX has high-confidence handles, vision only when needed (section 4). Alternative: Gemini 2.5 Flash on vision (already a fallback at `surface_runtime_vision.py:40`) where visual fidelity requirement is low. See open question (b).
- **Canvas-heavy apps.** Figma, Sheets's drawing layer, embedded SVG/Canvas, in-page virtual keyboards. Screenshot has no clickable structure for the AX tree. Grid-fill primitive (`dsv4_skill_runner.py:388`) handles Sheets via the universal A1-notation Name Box (general across Sheets/Excel-online/LibreOffice). Figma and Canva fall back to pure vision via `surface_runtime_vision.py`. Pure-vision dispatch is brittle and slower; escape hatch in section 8 catches the failures.
- **Login walls.** Covered in `planning/03-cross-app-auth/DESIGN.md` and `planning/05-existing-code-map/MAP.md` section 4. Agent drives the user's real Chrome at `~/.anticipy/chrome-real-clone` via the `com.anticipy.chrome` LaunchAgent; user logs in once per app, cookies persist. MFA triggers `engine/app/product/login_wall_responder.py` and surfaces to the user. Per-app config registry for MFA seeds is the wrong shape; auth state is per-cookie-jar in Chrome's storage, not in our config files.
- **Bot detection.** Ticketmaster, Kasada, Datadome. CDP dispatcher uses Bezier motion plus Gaussian inter-event delays (`engine/app/action_engine/humanlike.py`). NopeCHA covers Cloudflare. Sites that block us even with stealth go on an explicit refusal list. Bundle NopeCHA into the installer.
- **Page state changes during action.** Dedicated background Anticipy Agent window (`dsv4_skill_runner.py:100-151`), separate from the user's foreground tabs. Tab leakage asserted = 0 by `scripts/v7/z001_e2e_harness.py:50`.
- **DOM/AX changes mid-iteration.** Heavy SPAs (Salesforce, Workday, Slack) re-render aggressively. Runner re-extracts AX every iteration; coordinates fresh via `DOM.getBoxModel` per dispatch (`dsv4_skill_runner.py:237-244`).
- **Fabricated success.** `_vision_confirm` treats empty fields and placeholder content as NOT done. Vision verifier resolves mixed verdicts as DIVERGED (`vision_verifier.py:165-174`). Both gates run on Kimi K2.6, so a single Kimi failure mode could fool both, the realistic worst case.

## 11. Effort to ship

Two to three days, not weeks, because every load-bearing piece exists.

- Day 1 (4-6 hours): write `engine/app/product/universal_agent.py` (the wrapper from section 3), about 150 lines. Wraps `DSv4SkillRunner.run` with intent-to-task mapping. Add `TaskResult.status = "ASK"` to the runner (only frozen-path edit; permitted per the 2026-05-29 unfreezing).
- Day 1 (2-4 hours): wire universal agent into the act path. Delete the regex fastpaths at `server.py:5276` and `:5399`, replace `_compose_task_from_memory` at `:5479` with typed-intent emit, route to `UniversalAgent.run(intent, target_hint)`. Existing `/api/act` and `/api/act/confirm` at `:6659` and `:6782` already consume `TaskResult`.
- Day 2 (4-6 hours): two-mode decide. Add `_decide_axonly` path on `deepseek/deepseek-v4-flash` with no image; gate on AX confidence above 0.7. Latency win, not correctness. Measure `~/.anticipy/openrouter_calls.jsonl` before and after.
- Day 2 (2-4 hours): escape-hatch escalation. Runner emits `ASK` on stuck; planner consumes; notification flows through quietness cascade.
- Day 3: real-app sweep against 30 random apps the user is signed into. Measure success rate, time, escape-hatch rate. Iterate on the decide prompt for prompt-shaped failures. Deliverable is an honest scorecard.

If we discover an architecture gap, log it in `planning/08-universal-action-agent/OPEN.md` and patch.

## 12. Open questions for Omar

(a) Two-mode decide. Ship with AX-only as default and vision only on AX-confidence below 0.7, or vision on every step for safety at 2x median latency? Tradeoff: ~600 ms saved per step vs a small increase in mis-clicks on two unlabeled buttons with the same AX name.

(b) Vision model choice. Kimi K2.6 is the only multimodal in the locked broker (`route.ts:11`). Gemini 2.5 Flash is used as fallback inside `surface_runtime_vision.py:40` but is not in the broker whitelist. Open Gemini 2.5 Flash for the vision verifier so we have a real second opinion on DIVERGED, or stay single-multimodal for cost control?

(c) Escape-hatch escalation channel. Screenshot accompany the message? Default proposed: screenshot goes only to local notification surface, never to cloud, never persisted beyond the in-memory notification queue.

(d) Hard refusal list (Ticketmaster, certain bank logins, certain government portals). One-line code constant, or memory-of-kind `surface_refusal` so users can add without a code change?

(e) Confirmation taxonomy. Current irreversible-intent set at `engine/app/anticipy/irreversible_intents.json` (referenced at `server.py:5623`, file does not ship) is fixed. Universal agent can discover irreversibility from the page itself (a "Send" button is more irreversible than "Save Draft"). Want a separate doc on detecting irreversibility from the screenshot at decision time instead of an intent-name lookup? Right shape for "Donna for any SaaS" but adds one model call per state-changing dispatch.

(f) Trajectory storage. Runner logs every iteration to `~/.anticipy/trajectories/<task_id>/` (`dsv4_skill_runner.py:168`). Confirm local-only by default; existing `engine/app/action_engine/trajectory_logger.py` Supabase wiring stays silent-no-op unless user explicitly opts in (per CLAUDE.md privacy directive).
