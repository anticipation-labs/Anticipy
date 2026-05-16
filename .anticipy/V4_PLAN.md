> v1 action engine FROZEN at 7f3b72e 2026-05-16. No architecture changes without explicit Omar instruction.

# ANTICIPY ACTION ENGINE V1 — BUILD BIBLE
## DeepSeek V4 Flash multimodal via OpenRouter + vision-woven Ralph Loop + real Chrome
## Single run. Smoke-gated. FINAL. No architecture revisits after this.

This file is the canonical plan. It replaces FARA_PLAN.md (Fara is
deleted in phase V4-1). The full master prompt the user gave on
2026-05-15 is the source of truth; this is the operational summary.

## Architecture (locked)

Accessibility tree as primary input. Vision verification on EVERY
state-changing action (vision-woven, not vision-fallback). Ralph Loop
iteration with feedback. Real Chrome :9222 via CDP. Humanlike
dispatcher (existing cdp_dispatcher.py). Brain = DeepSeek V4 Flash via
OpenRouter. Kimi K2.6 fallback on 2x malformed or 2x verifier
disagreement on the same step.

Engine = function: structured task prompt in, structured result out.
No audio/proactive/pendant in scope. No human-in-loop confirmation
gates (agent commits Send/Buy/Submit; Omar owns this downstream). No
throttling or caps. No partial features.

## Model routing (verified against live OpenRouter catalog 2026-05-15)

- deepseek/deepseek-v4-flash : ['text'] only. TEXT steps.
- deepseek/deepseek-v4-pro   : ['text'] only.
- moonshotai/kimi-k2.6       : ['text','image']. VISION steps + fallback.

Both are REASONING models: response has `reasoning` + `content`.
max_tokens floor >= 200 or `content` is starved (finish=length).

## Hard rules (never violated)

No fabrication. No em-dashes. No incorporation claims. No telling Omar
to run terminal commands. No "should work" without command+output in
PROGRESS.md. No five alternatives (state one, run, observe; 2-attempt
then alternative). No half-working systems (green tag or git reset).
No paid services beyond OpenRouter. No confirmation gates before
irreversible actions. No throttling/caps/silent downgrades. No
vision-skipping. No proactive engine work (TODO only if compat needs).

## Phases

- V4-0 OpenRouter confirmed .......... DONE (phase-v4-0-openrouter-confirmed)
- V4-1 Cleanup Fara/Ollama/Qwen3 ..... tag phase-v4-1-cleanup
- V4-2 OpenRouter client ............. tag phase-v4-2-client-ready
- V4-3 Vision verifier ............... tag phase-v4-3-verifier-ready
- V4-4 DSv4 skill runner (Ralph) ..... tag phase-v4-4-runner-ready
- V4-5 Wikipedia smoke gate .......... tag phase-v4-5-wikipedia-passes (HARD GATE)
- V4-6 Compound task gate ............ tag phase-v4-6-compound-passes (HARD GATE)
- V4-7 20-task push to failure ....... tag phase-v4-7-twenty-tasks-validated (15/20 GATE)
- V4-8 Trajectory logging Supabase ... tag phase-v4-8-logging-live
- V4-9 Tauri Mac app shell ........... tag phase-v4-9-mac-app-ships
- V4-10 Handoff + cost analysis ...... Aevoy [ANTICIPY-DONE]

Each phase: green tag + git push, or git reset --hard to prior tag.
Hard gates V4-5/V4-6/V4-7: on failure email Aevoy [ANTICIPY-Q], stop.

## Canonical paths

Repo: /Users/omarebrahim/Developer/Anticipy-DEV-FINAL (Desktop alias
in prompt resolves here). Env: ~/.anticipy/.env (OPENROUTER_API_KEY).
Chrome clone: ~/.anticipy/chrome-real-clone/. Call log:
~/.anticipy/openrouter_calls.jsonl. Trajectories:
~/.anticipy/trajectories/<task_id>/.
